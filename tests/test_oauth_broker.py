#!/usr/bin/env python3
"""OAuth broker stays disabled until a client id exists outside the repo."""
from __future__ import annotations

import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oauth_broker as broker_mod  # noqa: E402


class BrokerTests(unittest.TestCase):
    def test_disabled_without_client_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            broker = broker_mod.Broker(Path(tmp) / "missing.json", Path(tmp) / "tokens")
            status = broker.status()
            youtube = next(row for row in status["providers"] if row["id"] == "youtube")
            self.assertEqual(youtube["state"], "disabled")
            self.assertFalse(youtube["connected"])
            started = broker.start("youtube", "http://127.0.0.1:8791/oauth/callback")
            self.assertEqual(started["status"], 403)
            self.assertNotIn("url", started)
            manual = broker.start("tiktok", "http://127.0.0.1:8791/oauth/callback")
            self.assertEqual(manual["error"], "coming_soon")
            artists = broker.start("spotify_for_artists", "http://127.0.0.1:8791/oauth/callback")
            self.assertEqual(artists["status"], 403)

    def test_pkce_start_hides_verifier_and_tokens_stay_outside_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "oauth-clients.json"
            tokens = Path(tmp) / "tokens"
            config.write_text(json.dumps({"youtube": {"client_id": "test-client"}}), encoding="utf-8")
            broker = broker_mod.Broker(config, tokens)
            verifier, challenge = broker_mod.pkce_pair()
            self.assertNotEqual(verifier, challenge)
            self.assertNotIn("=", challenge)
            started = broker.start("youtube", "http://127.0.0.1:8791/oauth/callback")
            self.assertTrue(started["ok"])
            self.assertIn("code_challenge=", started["url"])
            self.assertNotIn(broker.consume_state(started["state"])["verifier"], started["url"])
            self.assertIsNone(broker.consume_state(started["state"]))
            path = broker.write_token("youtube", {"access_token": "local-only"})
            self.assertTrue(str(path).startswith(str(tokens)))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(broker.disconnect("youtube")["connected"], False)
            self.assertFalse(path.exists())

    def test_default_paths_are_outside_a_checkout(self):
        self.assertIn(".local/share/stinc-os", str(broker_mod.DEFAULT_CONFIG))
        self.assertNotIn("stinc-os-demo", str(broker_mod.DEFAULT_TOKEN_DIR))


if __name__ == "__main__":
    unittest.main()
