#!/usr/bin/env python3
"""Local OAuth broker for STINC OS connectors.

Binds to 127.0.0.1 only. Client IDs stay in
~/.local/share/stinc-os/oauth-clients.json. Tokens stay in
~/.local/share/stinc-os/tokens/ with mode 0600. Neither path is in git.

Nothing starts until a client id is present for that provider. Spotify for
Artists, Apple Music analytics, TikTok, and X are not startable: there is no
free public API for those artist analytics. This process does not post, send,
or call a provider unless a later phase enables a configured provider.

Stdlib only. Default port 8791, next to the admin portal on 8790.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

HOME_DIR = Path.home() / ".local/share/stinc-os"
DEFAULT_CONFIG = HOME_DIR / "oauth-clients.json"
DEFAULT_TOKEN_DIR = HOME_DIR / "tokens"
HOST = "127.0.0.1"
PORT = 8791

# provider id -> whether a free OAuth client can ever be configured here.
PROVIDERS = {
    "youtube": {"label": "YouTube / YouTube Music", "mode": "oauth", "auth_url": "https://accounts.google.com/o/oauth2/v2/auth", "scope": "https://www.googleapis.com/auth/youtube.readonly"},
    "shopify": {"label": "Shopify", "mode": "oauth", "auth_url": "", "scope": "read_products,read_orders"},
    "instagram": {"label": "Instagram", "mode": "oauth", "auth_url": "https://www.facebook.com/v19.0/dialog/oauth", "scope": "instagram_basic,pages_show_list"},
    "spotify_for_artists": {"label": "Spotify for Artists", "mode": "manual", "reason": "Spotify for Artists has no public API."},
    "apple_music": {"label": "Apple Music", "mode": "manual", "reason": "Apple Music analytics are not a free public API."},
    "tiktok": {"label": "TikTok", "mode": "manual", "reason": "TikTok API access needs app review and is not an open free connector."},
    "x": {"label": "X", "mode": "manual", "reason": "X does not offer this workspace a free analytics API."},
}


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class Broker:
    def __init__(self, config_path: Path | None = None, token_dir: Path | None = None):
        self.config_path = Path(config_path or DEFAULT_CONFIG)
        self.token_dir = Path(token_dir or DEFAULT_TOKEN_DIR)
        self._pending: dict[str, dict] = {}

    def client_id(self, provider: str) -> str:
        data = self._config()
        block = data.get(provider) or {}
        if not isinstance(block, dict):
            return ""
        return str(block.get("client_id") or "").strip()

    def shop_domain(self) -> str:
        block = (self._config().get("shopify") or {})
        if not isinstance(block, dict):
            return ""
        return str(block.get("shop") or "").strip()

    def status(self) -> dict:
        items = []
        for pid, meta in PROVIDERS.items():
            if meta["mode"] != "oauth":
                items.append({"id": pid, "label": meta["label"], "state": "coming_soon", "reason": meta["reason"], "connected": False})
                continue
            cid = self.client_id(pid)
            connected = self._token_path(pid).is_file()
            if not cid:
                state = "disabled"
                reason = "Disabled until a client id is set on this Mac. No login will start."
            elif connected:
                state = "connected"
                reason = "A token file exists on this Mac. The token is not in git and is not sent to the public site."
            else:
                state = "ready"
                reason = "Client id is set. Connect only from the operator Mac."
            items.append({"id": pid, "label": meta["label"], "state": state, "reason": reason, "connected": connected and bool(cid)})
        return {"bind": HOST, "port": PORT, "providers": items}

    def start(self, provider: str, redirect_uri: str) -> dict:
        meta = PROVIDERS.get(provider)
        if not meta:
            return {"ok": False, "status": 404, "error": "unknown provider"}
        if meta["mode"] != "oauth":
            return {"ok": False, "status": 403, "error": "coming_soon", "reason": meta["reason"]}
        cid = self.client_id(provider)
        if not cid:
            return {"ok": False, "status": 403, "error": "disabled", "reason": "Client id is not configured."}
        if provider == "shopify" and not self.shop_domain():
            return {"ok": False, "status": 403, "error": "disabled", "reason": "Shopify shop domain is not configured."}
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        self._pending[state] = {"provider": provider, "verifier": verifier, "created": time.time()}
        params = {
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if provider != "shopify":
            params["scope"] = meta["scope"]
        auth = meta["auth_url"]
        if provider == "shopify":
            shop = self.shop_domain()
            auth = f"https://{shop}/admin/oauth/authorize"
        return {"ok": True, "status": 200, "url": auth + "?" + urlencode(params), "state": state}

    def consume_state(self, state: str) -> dict | None:
        row = self._pending.pop(state, None)
        if not row:
            return None
        if time.time() - row["created"] > 600:
            return None
        return row

    def disconnect(self, provider: str) -> dict:
        if provider not in PROVIDERS:
            return {"ok": False, "status": 404, "error": "unknown provider"}
        path = self._token_path(provider)
        if path.is_file():
            path.unlink()
        return {"ok": True, "status": 200, "connected": False}

    def write_token(self, provider: str, payload: dict) -> Path:
        """Store a token file outside the repo. Tests use a temp token_dir."""
        self.token_dir.mkdir(parents=True, exist_ok=True)
        path = self._token_path(provider)
        data = json.dumps(payload).encode("utf-8")
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
        return path

    def _token_path(self, provider: str) -> Path:
        safe = "".join(ch for ch in provider if ch.isalnum() or ch in "-_")
        return self.token_dir / f"{safe}.json"

    def _config(self) -> dict:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}


def make_handler(broker: Broker):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/status":
                self._send(200, broker.status())
                return
            if parsed.path == "/oauth/start":
                qs = parse_qs(parsed.query)
                provider = (qs.get("provider") or [""])[0]
                result = broker.start(provider, f"http://{HOST}:{PORT}/oauth/callback")
                # Never echo the verifier. The URL carries only the challenge.
                self._send(result["status"], {k: v for k, v in result.items() if k != "status"})
                return
            if parsed.path == "/oauth/disconnect":
                qs = parse_qs(parsed.query)
                provider = (qs.get("provider") or [""])[0]
                result = broker.disconnect(provider)
                self._send(result["status"], {k: v for k, v in result.items() if k != "status"})
                return
            self._send(404, {"ok": False, "error": "not_found"})

    return Handler


def main() -> int:
    broker = Broker()
    server = ThreadingHTTPServer((HOST, PORT), make_handler(broker))
    print(f"STINC OS OAuth broker on http://{HOST}:{PORT}/status (disabled until client ids exist)")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
