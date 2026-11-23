#!/usr/bin/env python3
"""Export a sanitized public snapshot for the STINC OS site.

Stdlib only. Run on the Mac, from this repo:

    python3 tools/export_live_data.py --platform "$HOME/Projects/stinc-platform" --brand "$HOME/Projects/content-engine/brands/ralfy-the-plug"

Reads local files. Writes data/live.json and, only when the HTML twin is
clean, preview PNGs under assets/email-previews/. Refuses to write if the
snapshot still contains an email, phone number, street address, or
secret-shaped string.

Sponsor rows are counts only. Legal-hold rows (including the gambling track)
are omitted. Tribute-flagged catalog rows are omitted, and words that appear
only on those rows are used to drop other public text. An optional deny file
(~/.local/share/stinc-ralfy/public-deny.txt, one phrase per line) is applied
the same way and is never copied into the snapshot.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from public_safety import find_issues, find_key_issues  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
HOLD_STATUSES = {"on_hold_legal", "legal_hold", "hold_legal"}
SENT_STATUSES = {"sent", "followup1_sent", "followup2_sent", "delivered"}
DEAL_STATUSES = {"deal", "won", "closed"}
SKIP_STATUSES = {"skip", "skip_affiliate", "skipped"}
PUBLIC_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "kick.com", "www.kick.com", "twitch.tv", "www.twitch.tv"}
PLATFORM_WORDS = {"kick", "twitch", "youtube", "instagram", "tiktok", "spotify", "apple", "shopify", "gmail"}
GENERIC_TOKENS = {
    "shirt", "shirts", "hoodie", "hoodies", "graphic", "vintage", "black", "white",
    "green", "blue", "shorts", "skate", "skateboard", "sticker", "chain", "kids",
    "baddest", "team", "stinc", "plug", "official", "color", "large", "small",
    "medium", "product", "store",
}
HEAD_RX = re.compile(r"^- \[\s*([xX✓✔]?)\s*\] (C\d+) \|(.*)$")
VIRAL_RX = re.compile(r"viral\s+(\d+(?:\.\d+)?)", re.I)
SCORE_RX = re.compile(r"score\s+(\d+(?:\.\d+)?)", re.I)
DUR_RX = re.compile(r"(\d+(?:\.\d+)?)\s*s\b")
WORD_RX = re.compile(r"[A-Za-z][A-Za-z']{4,}")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def count_videos(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO)


def daily_cap(root: Path) -> int:
    data = load_json(root / "campaigns/ralfy-sponsors/config.json", {})
    cap = data.get("daily_cap") if isinstance(data, dict) else None
    if isinstance(cap, int) and 0 < cap < 100:
        return cap
    return 3


def is_hold(row: dict) -> bool:
    status = (row.get("status") or "").strip().lower().replace(" ", "_")
    group = (row.get("group") or "").strip().upper()
    note = f"{row.get('priority_note') or ''} {row.get('legal') or ''}"
    if status in HOLD_STATUSES or group == "H":
        return True
    return bool(re.search(r"on hold:\s*legal|gambling|sportsbook|\bab\s*831\b", note, re.I))


def needles_from_rows(rows: list[dict]) -> list[str]:
    found: set[str] = set()
    for row in rows:
        chunks = []
        brand = (row.get("brand") or "").strip()
        if brand:
            chunks.append(brand)
            chunks.extend(re.split(r"[/()]", brand))
        key = (row.get("brand_key") or "").strip()
        if key:
            chunks.append(key)
        contact = (row.get("contact_name") or "").strip()
        if len(contact) >= 8:
            chunks.append(contact)
        email = (row.get("contact_email") or "").strip()
        if "@" in email:
            chunks.append(email)
        for chunk in chunks:
            text = chunk.strip(" -,")
            if len(text) < 5 or text.lower() in PLATFORM_WORDS:
                continue
            found.add(text)
    return sorted(found, key=len, reverse=True)


def contains_needle(text: str, needles: list[str]) -> bool:
    if not text:
        return False
    hay = text.casefold()
    for needle in needles:
        token = needle.casefold()
        if len(token) >= 12:
            if token in hay:
                return True
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", hay):
            return True
    return False


def deny_phrases(root: Path, extra: Path | None) -> list[str]:
    paths = []
    if extra:
        paths.append(extra)
    env = os.environ.get("STINC_PUBLIC_DENY")
    if env:
        paths.append(Path(env).expanduser())
    paths.append(Path.home() / ".local/share/stinc-ralfy/public-deny.txt")
    paths.append(root / "data/public-deny.txt")
    phrases = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            text = line.strip()
            if text and not text.startswith("#"):
                phrases.append(text)
    return phrases


def contains_phrase(text: str, phrases: list[str]) -> bool:
    hay = (text or "").casefold()
    return any(phrase.casefold() in hay for phrase in phrases if phrase)


def tribute_tokens(products: list[dict]) -> set[str]:
    tribute = [p for p in products if p.get("tribute_merch")]
    kept = [p for p in products if not p.get("tribute_merch")]

    def words(rows: list[dict]) -> set[str]:
        blob = " ".join(f"{row.get('title') or ''} {row.get('handle') or ''}" for row in rows)
        return {match.group(0).casefold() for match in WORD_RX.finditer(blob)}

    tokens = words(tribute) - words(kept) - GENERIC_TOKENS
    return {token for token in tokens if len(token) >= 5}


def contains_token(text: str, tokens: set[str]) -> bool:
    if not text or not tokens:
        return False
    hay = text.casefold()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", hay) for token in tokens)


def blocked(text: str, needles: list[str], tokens: set[str], phrases: list[str]) -> bool:
    if find_issues(text or ""):
        return True
    if contains_needle(text, needles) or contains_token(text, tokens) or contains_phrase(text, phrases):
        return True
    return False


def clean_text(text: str, needles, tokens, phrases) -> str | None:
    value = (text or "").strip()
    if not value:
        return ""
    if blocked(value, needles, tokens, phrases):
        return None
    return value


def sponsor_counts(rows: list[dict], cap: int) -> dict:
    counts = {
        "sent": 0, "queued": 0, "pending_approval": 0, "replies": 0, "deals": 0,
        "needs_manual_form": 0, "watchlist": 0, "skipped": 0, "bounced": 0,
        "other": 0, "tracked": 0, "daily_cap": cap,
    }
    for row in rows:
        if is_hold(row):
            continue
        counts["tracked"] += 1
        status = (row.get("status") or "").strip().lower().replace(" ", "_")
        if status in DEAL_STATUSES:
            counts["deals"] += 1
        elif status in SENT_STATUSES:
            counts["sent"] += 1
        elif status == "queued":
            counts["queued"] += 1
        elif status in {"pending_approval", "pending"}:
            counts["pending_approval"] += 1
        elif status == "needs_manual_form":
            counts["needs_manual_form"] += 1
        elif status == "watchlist":
            counts["watchlist"] += 1
        elif status in SKIP_STATUSES:
            counts["skipped"] += 1
        elif status == "bounced":
            counts["bounced"] += 1
        else:
            counts["other"] += 1
        reply = (row.get("reply_status") or "").strip().lower()
        if reply and reply not in {"none", "n/a", "na", "-"}:
            counts["replies"] += 1
    return counts


def tracker_rows(root: Path) -> tuple[list[dict], str]:
    live = root / "campaigns/ralfy-sponsors/tracker.csv"
    sample = root / "campaigns/ralfy-sponsors/tracker.sample.csv"
    if live.is_file():
        return read_csv(live), "tracker.csv"
    if sample.is_file():
        return read_csv(sample), "tracker.sample.csv"
    return [], "missing"


def parse_candidates(path: Path) -> list[dict]:
    out = []
    current = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        stripped = line.strip()
        match = HEAD_RX.match(stripped)
        if match:
            rest = match.group(3)
            viral = VIRAL_RX.search(rest)
            score = SCORE_RX.search(rest)
            duration = DUR_RX.search(rest)
            title = rest.split("|")[-1].strip() if "|" in rest else rest.strip()
            title = re.sub(r"\s+", " ", title)
            current = {
                "id": match.group(2).upper(),
                "approved": bool(match.group(1)),
                "title": title,
                "viral": float(viral.group(1)) if viral else None,
                "score": float(score.group(1)) if score else None,
                "duration_s": float(duration.group(1)) if duration else None,
                "hook": "",
                "rendered": "rendered →" in rest or title.lower().startswith("rendered"),
            }
            out.append(current)
            continue
        if current and stripped.startswith("- ") and not stripped.startswith("- ["):
            key, _, val = stripped[2:].partition(":")
            key_l = key.strip().lower()
            if key_l == "on-screen hook":
                current["hook"] = val.strip()
            elif key_l == "viral signals":
                current["signals"] = parse_viral_signals(val)
            elif key_l == "source signals":
                current["source_signals"] = val.strip()
    return out


def youtube_url(stem: str) -> str:
    if not stem.startswith("yt-"):
        return ""
    video_id = stem[3:]
    if re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        return f"https://www.youtube.com/watch?v={video_id}"
    return ""


def public_url(value: str) -> str:
    text = (value or "").strip().strip("`")
    if not text.startswith(("http://", "https://")):
        return ""
    host = re.sub(r"^https?://", "", text).split("/")[0].split("?")[0].lower()
    if host not in PUBLIC_HOSTS:
        return ""
    return text.split("?")[0]


def clean_title(title: str, hook: str) -> str:
    raw = (title or "").strip()
    if raw.lower().startswith("rendered") or "/" in raw or raw.lower().endswith(".mp4"):
        return (hook or "Clip").strip()
    if raw.lower() in {"full edit", "full"} and hook:
        return hook.strip()
    return raw or (hook or "Clip").strip()


def clips_from_brand(brand: Path, needles, tokens, phrases) -> list[dict]:
    clips = []
    if not brand.is_dir():
        return clips
    for folder_name, kind in (("candidates", "stream"), ("candidates-music", "music")):
        folder = brand / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            watch = youtube_url(path.stem)
            for option in parse_candidates(path):
                title = clean_title(option["title"], option["hook"])
                hook = option["hook"] or title
                status = "Rendered" if option["rendered"] else ("Approved" if option["approved"] else "Needs review")
                fields = [title, hook, status, watch, path.stem, option["id"]]
                if any(blocked(field, needles, tokens, phrases) for field in fields):
                    continue
                row = {
                    "id": f"{path.stem}_{option['id']}",
                    "title": title,
                    "hook": hook,
                    "viral": option["viral"],
                    "score": option["score"],
                    "duration_s": option["duration_s"],
                    "kind": kind,
                    "status": status,
                    "watch_url": watch,
                    "source_label": "YouTube · public VOD" if watch else "Public source",
                }
                breakdown = clip_breakdown(option)
                if breakdown:
                    row["breakdown"] = breakdown
                clips.append(row)
    clips.sort(key=lambda row: (-(row["viral"] or 0), row["id"]))
    return clips


def pipeline_from_brand(brand: Path) -> dict:
    if not brand.is_dir():
        return {}
    rows = read_csv(brand / "tracker" / "tracker.csv")

    def status(row):
        return (row.get("status") or "").strip().lower()

    made = max(len(rows), count_videos(brand / "clips"))
    rendered = sum(1 for row in rows if status(row) == "rendered") or count_videos(brand / "clips")
    cand_stream = list((brand / "candidates").glob("*.md")) if (brand / "candidates").is_dir() else []
    cand_music = list((brand / "candidates-music").glob("*.md")) if (brand / "candidates-music").is_dir() else []
    streams_scanned = count_videos(brand / "inbox") + count_videos(brand / "transcribed")
    music_scanned = count_videos(brand / "inbox-music") + len(cand_music)
    return {
        "source_videos": streams_scanned + count_videos(brand / "inbox-music"),
        "streams_scanned": streams_scanned,
        "music_videos_scanned": music_scanned,
        "candidate_files": len(cand_stream) + len(cand_music),
        "clips_rendered": rendered or made,
        "approved": sum(1 for row in rows if row.get("approved_at") or status(row) in {"approved", "posted"}),
        "posted": sum(1 for row in rows if row.get("posted_at") or status(row) == "posted"),
        "ready": count_videos(brand / "ready"),
    }


def clips_from_dashboard(root: Path, needles, tokens, phrases) -> tuple[list[dict], dict]:
    data = load_json(root / "dashboard/data/dashboard.json", {})
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, dict):
        return [], {}
    clips = []
    for video in content.get("studio") or []:
        if not isinstance(video, dict):
            continue
        stem = str(video.get("stem") or "")
        kind = video.get("kind") if video.get("kind") in {"stream", "music"} else "stream"
        watch = youtube_url(stem)
        for option in video.get("options") or []:
            if not isinstance(option, dict):
                continue
            hook = str(option.get("hook") or "")
            title = clean_title(str(option.get("title") or ""), hook)
            rendered = bool(option.get("rendered")) or str(option.get("title") or "").lower().startswith("rendered")
            approved = bool(option.get("approved"))
            status = "Rendered" if rendered else ("Approved" if approved else "Needs review")
            fields = [title, hook, stem, str(option.get("id") or ""), watch]
            if any(blocked(field, needles, tokens, phrases) for field in fields):
                continue
            viral = option.get("viral")
            duration = option.get("duration_s")
            clips.append({
                "id": f"{stem}_{option.get('id') or 'clip'}",
                "title": title,
                "hook": hook or title,
                "viral": viral if isinstance(viral, (int, float)) else None,
                "score": option.get("score") if isinstance(option.get("score"), (int, float)) else None,
                "duration_s": duration if isinstance(duration, (int, float)) else None,
                "kind": kind,
                "status": status,
                "watch_url": watch,
                "source_label": "YouTube · public VOD" if watch else "Public source",
            })
    plan = content.get("plan") if isinstance(content.get("plan"), dict) else {}
    counts = plan.get("counts") if isinstance(plan.get("counts"), dict) else {}
    queue = counts.get("queued")
    if not isinstance(queue, int):
        queue = len(plan.get("items") or []) if isinstance(plan.get("items"), list) else 0
    summary = {
        "source_videos": content.get("source_videos") if isinstance(content.get("source_videos"), int) else 0,
        "candidate_files": content.get("candidates") if isinstance(content.get("candidates"), int) else 0,
        "clips_rendered": content.get("clips_made") if isinstance(content.get("clips_made"), int) else 0,
        "approved": content.get("approved") if isinstance(content.get("approved"), int) else 0,
        "posted": content.get("posted") if isinstance(content.get("posted"), int) else 0,
        "ready": content.get("ready") if isinstance(content.get("ready"), int) else 0,
        "queue": queue if isinstance(queue, int) else 0,
    }
    clips.sort(key=lambda row: (-(row["viral"] or 0), row["id"]))
    return clips, summary


def first_stat(stat: str) -> str:
    match = re.match(r"\s*([0-9][0-9,]*(?:\.[0-9]+)?(?:\s*[KMB]\b)?)", stat or "", re.I)
    return match.group(1).replace(" ", "") if match else ""


def platforms_block(root: Path, needles, tokens, phrases) -> tuple[dict, list]:
    data = load_json(root / "data/platforms.json", {"items": []})
    items = []
    for row in data.get("items") or []:
        if not isinstance(row, dict):
            continue
        kept = {}
        ok = True
        for key in ("platform", "handle", "url", "stat", "detail", "date", "source"):
            value = clean_text(str(row.get(key) or ""), needles, tokens, phrases)
            if value is None:
                ok = False
                break
            kept[key] = value
        if ok and kept.get("platform"):
            items.append(kept)
    videos = []
    for row in data.get("videos") or []:
        if not isinstance(row, dict):
            continue
        title = clean_text(str(row.get("title") or ""), needles, tokens, phrases)
        url = public_url(str(row.get("url") or ""))
        views = row.get("views")
        if title and isinstance(views, int) and url:
            videos.append({"title": title, "views": views, "url": url})
    return {"as_of": str(data.get("as_of") or ""), "items": items}, videos


def highlights_for(platforms: dict, product_count: int, product_as_of: str) -> list[dict]:
    by = {(row.get("platform") or "").lower(): row for row in platforms.get("items") or []}
    specs = (
        ("youtube", "YouTube subscribers", "play"),
        ("spotify", "Spotify listeners", "headphones"),
        ("instagram", "Instagram followers", "people"),
    )
    rows = []
    for key, label, icon in specs:
        item = by.get(key)
        if not item:
            continue
        value = first_stat(item.get("stat") or "")
        if not value:
            continue
        dated = str(item.get("date") or platforms.get("as_of") or "")
        if "/" in dated:
            dated = dated.split("/")[-1].strip()
        rows.append({"label": label, "value": value, "as_of": f"As of {dated}".strip(), "icon": icon, "sample": False})
    if product_count:
        rows.append({"label": "Store products", "value": f"{product_count:,}", "as_of": f"Public rack · {product_as_of}".strip(), "icon": "bag", "sample": False})
    return rows


def catalog_block(root: Path, needles, tokens, phrases) -> dict:
    data = load_json(root / "ecommerce/data/catalog.json", {})
    products_in = data.get("products") if isinstance(data, dict) else None
    meta = data.get("meta") if isinstance(data, dict) and isinstance(data.get("meta"), dict) else {}
    tokens = set(tokens) | tribute_tokens(products_in or [])
    shown = []
    for row in products_in or []:
        if not isinstance(row, dict) or row.get("tribute_merch"):
            continue
        title = clean_text(str(row.get("title") or ""), needles, tokens, phrases)
        handle = clean_text(str(row.get("handle") or ""), needles, tokens, phrases)
        url = str(row.get("url") or "")
        if title is None or handle is None or not title:
            continue
        if not url.startswith("https://"):
            continue
        image = str(row.get("image") or "")
        if image and not image.startswith("https://"):
            image = ""
        price = row.get("price_min")
        if not isinstance(price, (int, float)):
            continue
        sizes = [str(size) for size in (row.get("instock_sizes") or []) if isinstance(size, str)]
        shown.append({
            "title": title,
            "handle": handle,
            "url": url.split("?")[0],
            "price_min": price,
            "price_max": row.get("price_max") if isinstance(row.get("price_max"), (int, float)) else price,
            "available": bool(row.get("available")),
            "instock_sizes": sizes[:8],
            "image": image,
            "category": clean_text(str(row.get("category") or ""), needles, tokens, phrases) or "",
        })
    shown.sort(key=lambda row: row["title"].lower())
    in_stock_prices = [row["price_min"] for row in shown if row["available"]]
    return {
        "store_url": "https://stincteamtgf.com",
        "store_name": "STINCTEAMTGF",
        "as_of": str(meta.get("inspected_at") or ""),
        "store_published_count": meta.get("published_count") if isinstance(meta.get("published_count"), int) else len(products_in or []),
        "store_in_stock_count": meta.get("in_stock_count") if isinstance(meta.get("in_stock_count"), int) else None,
        "shown_count": len(shown),
        "shown_in_stock": sum(1 for row in shown if row["available"]),
        "price_min": min(in_stock_prices) if in_stock_prices else None,
        "price_max": max(in_stock_prices) if in_stock_prices else None,
        "products": shown,
        "_tokens": tokens,
    }


def email_block(root: Path, needles, tokens, phrases) -> tuple[dict, list[tuple[Path, str]]]:
    specs = sorted((root / "ecommerce/emails/specs").glob("*.json"))
    cards = []
    copied = 0
    withheld = 0
    pending: list[tuple[Path, str]] = []
    for spec_path in specs:
        spec = load_json(spec_path, {})
        if not isinstance(spec, dict):
            continue
        subject = clean_text(str(spec.get("subject") or ""), needles, tokens, phrases)
        if not subject:
            continue
        preheader = clean_text(str(spec.get("preheader") or ""), needles, tokens, phrases)
        series = clean_text(str(spec.get("series") or ""), needles, tokens, phrases) or ""
        segment = clean_text(str(spec.get("segment") or ""), needles, tokens, phrases) or ""
        stem = spec_path.stem
        html_path = root / "ecommerce/emails" / f"{stem}.html"
        preview = ""
        html = ""
        try:
            html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
        except OSError:
            html = ""
        html_ok = bool(html) and not blocked(html, needles, tokens, phrases)
        mobile = root / "ecommerce/emails/previews" / f"{stem}-mobile.png"
        if html_ok and mobile.is_file():
            dest_name = f"{stem}-mobile.png"
            pending.append((mobile, dest_name))
            preview = f"assets/email-previews/{dest_name}"
            copied += 1
        elif mobile.is_file() or html:
            withheld += 1
        cards.append({
            "id": stem,
            "series": series,
            "segment": segment,
            "subject": subject,
            "preheader": preheader or "",
            "preview": preview,
        })
    if withheld and not copied:
        reason = "Preview images stay off this public site because the draft HTML includes a contact email, phone number, or street address."
        state = "withheld"
    elif withheld:
        reason = "Some preview images were withheld because their HTML includes a contact email, phone number, or street address."
        state = "partial"
    elif copied:
        reason = ""
        state = "copied"
    else:
        reason = "No verified preview image was copied."
        state = "none"
    return {
        "emails_built": len(specs),
        "emails": cards,
        "previews": state,
        "previews_reason": reason,
    }, pending


FORMS_QUEUE = Path("campaigns/ralfy-sponsors/outbox/current/forms/queue.json")
FORMS_LOG = Path("campaigns/ralfy-sponsors/outbox/current/forms/log.csv")
SEND_LOG = Path("campaigns/ralfy-sponsors/send_log.csv")
SIG_RX = re.compile(r"(hook|moment|audio|chat|replay|traction)\s+(\d+(?:\.\d+)?)", re.I)
MUSIC_STEMS = ("yt-aINQ_DN8GJU",)
FAN_URLS = {
    "instagram": "https://www.instagram.com/ralfyclips.daily/",
    "tiktok": "https://www.tiktok.com/@ralfyclips.daily",
}
PLATFORM_LABEL = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "x": "X",
    "youtube": "YouTube Shorts",
}


def parse_viral_signals(text: str) -> dict:
    found = {m.group(1).lower(): float(m.group(2)) for m in SIG_RX.finditer(text or "")}
    return {
        "hook": found.get("hook"),
        "moment": found.get("moment"),
        "audio": found.get("audio"),
        "chat_hype": found.get("chat"),
        "traction": found.get("traction") or found.get("replay"),
    }


def clip_kind(clip_file: str, explicit=None, folder_kind: str | None = None) -> str:
    if explicit in {"stream", "music"}:
        return explicit
    if folder_kind in {"stream", "music"}:
        return folder_kind
    name = (clip_file or "").lower()
    if any(stem.lower() in name for stem in MUSIC_STEMS):
        return "music"
    return "stream"


def clip_breakdown(option: dict) -> dict | None:
    sigs = option.get("signals") if isinstance(option.get("signals"), dict) else {}
    story = option.get("score")
    if not isinstance(story, (int, float)):
        story = sigs.get("moment")
    hook = sigs.get("hook")
    audio = sigs.get("audio")
    chat = sigs.get("chat_hype")
    traction = sigs.get("traction")
    label = str(option.get("source_signals") or "").strip()
    if not any(isinstance(v, (int, float)) for v in (story, hook, audio, chat, traction)) and not label:
        return None
    out = {
        "story": story if isinstance(story, (int, float)) else None,
        "hook": hook if isinstance(hook, (int, float)) else None,
        "audio": audio if isinstance(audio, (int, float)) else None,
        "chat_hype": chat if isinstance(chat, (int, float)) else None,
        "traction": traction if isinstance(traction, (int, float)) else None,
    }
    if label:
        out["traction_label"] = label
    return out


def parse_dt(value: str):
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def format_et(value: str) -> str:
    dt = parse_dt(value)
    if not dt:
        return ""
    return dt.strftime("%a %b %-d, %-I:%M %p ET").replace(" 0", " ")


def needles_from_forms(root: Path) -> list[str]:
    found: set[str] = set()
    queue = load_json(root / FORMS_QUEUE, [])
    if isinstance(queue, list):
        for row in queue:
            if not isinstance(row, dict):
                continue
            for key in ("brand", "key", "brand_key"):
                val = str(row.get(key) or "").strip()
                if val and len(val) >= 4:
                    found.add(val)
    for row in read_csv(root / FORMS_LOG):
        for key in ("brand", "key", "brand_key"):
            val = str(row.get(key) or "").strip()
            if val and len(val) >= 4:
                found.add(val)
    return sorted(found, key=len, reverse=True)


def form_aggregates(root: Path) -> dict:
    queue = load_json(root / FORMS_QUEUE, [])
    queued = len(queue) if isinstance(queue, list) else 0
    today = datetime.now(ET).date().isoformat()
    submitted = 0
    submitted_today = 0
    for row in read_csv(root / FORMS_LOG):
        status = (row.get("status") or "").strip().lower()
        if status not in {"submitted", "sent", "ok", "success"}:
            continue
        submitted += 1
        if (row.get("date") or "").strip()[:10] == today:
            submitted_today += 1
    return {
        "forms_queued": queued,
        "forms_submitted": submitted,
        "forms_submitted_today": submitted_today,
        "forms_daily_cap": 10,
        "forms_min_spacing_min": 30,
    }


def outreach_by_channel(rows: list[dict], forms: dict, cap: int) -> list[dict]:
    email = {"channel": "email", "sent": 0, "queued": 0, "replies": 0, "tracked": 0, "daily_cap": cap}
    form_from_tracker = {"needs_manual_form": 0, "tracked": 0}
    for row in rows:
        if is_hold(row):
            continue
        channel = (row.get("channel") or "").strip().lower()
        status = (row.get("status") or "").strip().lower().replace(" ", "_")
        reply = (row.get("reply_status") or "").strip().lower()
        replied = bool(reply and reply not in {"none", "n/a", "na", "-"})
        if channel == "form" or status == "needs_manual_form":
            form_from_tracker["tracked"] += 1
            if status == "needs_manual_form":
                form_from_tracker["needs_manual_form"] += 1
            continue
        email["tracked"] += 1
        if status in SENT_STATUSES:
            email["sent"] += 1
        elif status == "queued":
            email["queued"] += 1
        if replied:
            email["replies"] += 1
    form = {
        "channel": "form",
        "queued": forms.get("forms_queued") or 0,
        "submitted": forms.get("forms_submitted") or 0,
        "submitted_today": forms.get("forms_submitted_today") or 0,
        "daily_cap": forms.get("forms_daily_cap") or 10,
        "min_spacing_min": forms.get("forms_min_spacing_min") or 30,
        "needs_manual_form": form_from_tracker["needs_manual_form"],
    }
    return [email, form]


def upcoming_queue(brand: Path, needles, tokens, phrases) -> list[dict]:
    if not brand.is_dir():
        return []
    items = []
    log = load_json(brand / "posting" / "post-log.json", {})
    posts = log.get("posts") if isinstance(log, dict) else []
    if not isinstance(posts, list):
        posts = []
    for row in posts:
        if not isinstance(row, dict) or (row.get("status") or "") != "scheduled":
            continue
        clip = str(row.get("clip_file") or "").split("/")[-1]
        title = str(row.get("hook") or row.get("title") or clip).strip()
        when = str(row.get("publish_at") or row.get("posted_at") or "")
        platform = str(row.get("platform") or "")
        kind = clip_kind(clip, row.get("kind"))
        if any(blocked(field, needles, tokens, phrases) for field in (title, clip, platform)):
            continue
        items.append({
            "platform": platform,
            "kind": kind,
            "title": clean_title(title, title),
            "scheduled_at": when,
            "scheduled_label": format_et(when),
            "status": "scheduled",
        })
    queue = load_json(brand / "posting" / "queue.json", {})
    seen = {(r["platform"], r["title"], (r["scheduled_at"] or "")[:16]) for r in items}
    for plat, rows in (queue.get("by_channel") or {}).items() if isinstance(queue, dict) else []:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (row.get("status") or "") not in {"planned", "queued", "pending"}:
                continue
            if (row.get("channel_ready") is False) or (row.get("channel_enabled") is False):
                # Keep coming-soon planned items out of the public upcoming list.
                continue
            clip = str(row.get("clip_file") or "").split("/")[-1]
            title = str(row.get("hook") or row.get("title") or clip).strip()
            when = str(row.get("scheduled_at") or "")
            platform = str(row.get("platform") or plat)
            kind = clip_kind(clip, row.get("kind"))
            key = (platform, title, when[:16])
            if key in seen:
                continue
            if any(blocked(field, needles, tokens, phrases) for field in (title, clip, platform)):
                continue
            items.append({
                "platform": platform,
                "kind": kind,
                "title": clean_title(title, title),
                "scheduled_at": when,
                "scheduled_label": format_et(when),
                "status": "planned",
            })
            seen.add(key)
    items.sort(key=lambda row: row.get("scheduled_at") or "")
    return items[:16]


def published_counts(brand: Path) -> dict:
    log = load_json(brand / "posting" / "post-log.json", {})
    posts = log.get("posts") if isinstance(log, dict) else []
    if not isinstance(posts, list):
        posts = []
    today = datetime.now(ET).date()
    out = {}
    for name in PLATFORM_LABEL:
        sent = [p for p in posts if isinstance(p, dict) and p.get("platform") == name and p.get("status") == "sent"]
        scheduled = [p for p in posts if isinstance(p, dict) and p.get("platform") == name and p.get("status") == "scheduled"]
        today_n = 0
        for row in sent:
            dt = parse_dt(str(row.get("publish_at") or row.get("posted_at") or ""))
            if dt and dt.date() == today:
                today_n += 1
        out[name] = {"published": len(sent), "scheduled": len(scheduled), "published_today": today_n}
    return out


def activity_feed(brand: Path, root: Path, needles, tokens, phrases) -> list[dict]:
    events = []
    log = load_json(brand / "posting" / "post-log.json", {}) if brand.is_dir() else {}
    posts = log.get("posts") if isinstance(log, dict) else []
    if not isinstance(posts, list):
        posts = []
    for row in posts:
        if not isinstance(row, dict):
            continue
        platform = PLATFORM_LABEL.get(str(row.get("platform") or ""), str(row.get("platform") or "fan page"))
        status = (row.get("status") or "").strip().lower()
        when = str(row.get("posted_at") or row.get("publish_at") or "")
        dt = parse_dt(when)
        title = str(row.get("hook") or row.get("title") or "").strip()
        if title and blocked(title, needles, tokens, phrases):
            title = ""
        if status != "sent":
            continue
        if not dt:
            dt = parse_dt(str(row.get("publish_at") or ""))
        if not dt:
            continue
        detail = f"{platform}: {title}" if title else f"{platform} fan page"
        events.append({
            "at": dt.isoformat(timespec="seconds"),
            "at_label": dt.strftime("%a %-I:%M %p ET").replace(" 0", " "),
            "label": "Clip posted",
            "detail": detail,
        })
    # One aggregate for what is already scheduled ahead (details live in the queue).
    scheduled_n = sum(1 for row in posts if isinstance(row, dict) and (row.get("status") or "") == "scheduled")
    if scheduled_n:
        now = datetime.now(ET)
        events.append({
            "at": now.isoformat(timespec="seconds"),
            "at_label": now.strftime("%a %-I:%M %p ET").replace(" 0", " "),
            "label": "Clips scheduled",
            "detail": f"{scheduled_n} fan-page posts queued ahead",
            "count": scheduled_n,
        })
    # Outreach as counts only — never brand names.
    sent_by_day: dict[str, int] = {}
    for row in read_csv(root / SEND_LOG):
        result = (row.get("result") or "").strip().lower()
        dry = (row.get("dry_run") or "").strip().lower()
        if result != "sent" or dry in {"1", "true", "yes"}:
            continue
        stamp = (row.get("time_et") or "").strip()
        day = stamp[:10]
        if day:
            sent_by_day[day] = sent_by_day.get(day, 0) + 1
    for day, count in sent_by_day.items():
        try:
            stamp = datetime.fromisoformat(day).replace(tzinfo=ET, hour=12)
        except ValueError:
            continue
        events.append({
            "at": stamp.isoformat(timespec="seconds"),
            "at_label": stamp.strftime("%a %b %-d ET").replace(" 0", " "),
            "label": "Outreach sent",
            "detail": f"{count} email{'s' if count != 1 else ''} (count only)",
            "count": count,
        })
    form_by_day: dict[str, int] = {}
    form_total = 0
    for row in read_csv(root / FORMS_LOG):
        status = (row.get("status") or "").strip().lower()
        if status not in {"submitted", "sent", "ok", "success"}:
            continue
        form_total += 1
        day = (row.get("date") or "").strip()[:10]
        if day:
            form_by_day[day] = form_by_day.get(day, 0) + 1
    for day, count in form_by_day.items():
        try:
            stamp = datetime.fromisoformat(day).replace(tzinfo=ET, hour=15)
        except ValueError:
            continue
        events.append({
            "at": stamp.isoformat(timespec="seconds"),
            "at_label": stamp.strftime("%a %b %-d ET").replace(" 0", " "),
            "label": "Forms submitted",
            "detail": f"{count} application{'s' if count != 1 else ''} (count only)",
            "count": count,
        })
    clips_dir = brand / "clips" if brand.is_dir() else None
    if clips_dir and clips_dir.is_dir():
        newest = None
        n = 0
        for path in clips_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO:
                n += 1
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=ET)
                if newest is None or mtime > newest:
                    newest = mtime
        if n and newest:
            events.append({
                "at": newest.isoformat(timespec="seconds"),
                "at_label": newest.strftime("%a %-I:%M %p ET").replace(" 0", " "),
                "label": "Clips rendered",
                "detail": f"{n} vertical clips on disk",
                "count": n,
            })
    events.sort(key=lambda row: row.get("at") or "", reverse=True)
    return events[:16]


def posting_cfg(brand: Path) -> dict:
    return load_json(brand / "posting.json", {}) if brand.is_dir() else {}


def extract_thumbs(brand: Path, clips: list[dict], out: Path, limit: int = 6) -> None:
    if not brand.is_dir():
        return
    thumb_dir = out / "assets" / "clip-thumbs"
    ffmpeg = next((Path(p) for p in ("/opt/homebrew/bin/ffmpeg", "/usr/bin/ffmpeg") if Path(p).is_file()), None)
    if ffmpeg is None:
        return
    written = set()
    count = 0
    clips_dir = brand / "clips"
    if not clips_dir.is_dir():
        return
    for clip in clips:
        if count >= limit:
            break
        cid = str(clip.get("id") or "")
        if not cid or "/" in cid or ".." in cid:
            continue
        # id is like yt-xxxxx_C4 ; files are ralfy-the-plug_yt-xxxxx_C4.mp4 or _C4-v2.mp4
        matches = sorted(clips_dir.glob(f"*{cid}*.mp4")) + sorted(clips_dir.glob(f"*{cid}*.mov"))
        if not matches:
            continue
        src = matches[0]
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", cid) + ".jpg"
        dest = thumb_dir / name
        thumb_dir.mkdir(parents=True, exist_ok=True)
        try:
            import subprocess
            proc = subprocess.run(
                [str(ffmpeg), "-y", "-ss", "1", "-i", str(src), "-frames:v", "1",
                 "-vf", "scale=320:-2", "-q:v", "6", str(dest)],
                check=False, capture_output=True, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 200:
            if dest.exists():
                dest.unlink()
            continue
        rel = f"assets/clip-thumbs/{name}"
        clip["thumb"] = rel
        written.add(name)
        count += 1
    if thumb_dir.is_dir():
        for stale in thumb_dir.glob("*.jpg"):
            if stale.name not in written and not any(c.get("thumb") == f"assets/clip-thumbs/{stale.name}" for c in clips):
                # Keep previously referenced thumbs that belong to remaining top clips.
                keep = False
                for clip in clips:
                    cid = re.sub(r"[^A-Za-z0-9_-]+", "-", str(clip.get("id") or ""))
                    if cid and stale.name == cid + ".jpg":
                        clip.setdefault("thumb", f"assets/clip-thumbs/{stale.name}")
                        keep = True
                        break
                if not keep:
                    # Do not delete all on a test run with no matches; only prune unmatched leftovers
                    # when we wrote at least one new thumb this pass.
                    if written:
                        stale.unlink()


def fan_block(root: Path, platforms: dict, needles, tokens, phrases, brand: Path | None = None) -> dict:
    data = load_json(root / "data/fan_pages.json", {})
    cfg = posting_cfg(brand) if brand else {}
    channels_cfg = cfg.get("channels") if isinstance(cfg.get("channels"), dict) else {}
    mix_cfg = cfg.get("content_mix") if isinstance(cfg.get("content_mix"), dict) else {}
    stream_per = mix_cfg.get("stream_per_music") or 3
    autopilot = bool(cfg.get("enabled") and cfg.get("live") and not cfg.get("dry_run"))
    posting = "on" if autopilot else (str(data.get("posting") or "off") if isinstance(data, dict) else "off")
    if posting not in {"off", "on"}:
        posting = "off"
    counts = published_counts(brand) if brand else {}
    accounts = []
    if channels_cfg:
        for key, label in PLATFORM_LABEL.items():
            ch = channels_cfg.get(key) if isinstance(channels_cfg.get(key), dict) else {}
            enabled = bool(ch.get("enabled") and ch.get("account_created"))
            handle = clean_text(str(ch.get("handle") or ""), needles, tokens, phrases)
            if enabled:
                handle = handle or "@ralfyclips.daily"
                url = FAN_URLS.get(key, "")
                status = "Live"
            else:
                handle = handle or "Coming soon"
                url = ""
                status = "Coming soon"
            stats = counts.get(key) or {}
            accounts.append({
                "platform": label,
                "handle": handle or "",
                "url": url,
                "status": status,
                "kind": "fan",
                "posts_published": int(stats.get("published") or 0),
                "posts_scheduled": int(stats.get("scheduled") or 0),
                "posts_published_today": int(stats.get("published_today") or 0),
                "per_day": int(ch.get("per_day") or 2),
                "slot_times_et": list(ch.get("slot_times_et") or []),
            })
    else:
        for row in (data.get("accounts") or []) if isinstance(data, dict) else []:
            if not isinstance(row, dict):
                continue
            platform = clean_text(str(row.get("platform") or ""), needles, tokens, phrases)
            handle = clean_text(str(row.get("handle") or ""), needles, tokens, phrases)
            status = clean_text(str(row.get("status") or ""), needles, tokens, phrases) or ""
            url = str(row.get("url") or "")
            if url and not url.startswith("https://"):
                url = ""
            if platform and handle is not None:
                accounts.append({"platform": platform, "handle": handle, "url": url, "status": status, "kind": "fan"})
    official = []
    for row in platforms.get("items") or []:
        official.append({
            "platform": row.get("platform") or "",
            "handle": row.get("handle") or "",
            "url": row.get("url") or "",
            "status": row.get("stat") or "",
            "kind": "official",
        })
    return {
        "name": "Ralfy Clips",
        "posting": posting,
        "autopilot": autopilot or posting == "on",
        "mix": f"1 music teaser per {int(stream_per)} stream clips",
        "warmup": "2 posts per day per live channel, 30-minute stagger",
        "channels_live": sum(1 for a in accounts if (a.get("status") or "") == "Live"),
        "channels_total": max(len(accounts), 4),
        "posts_published_total": sum(int(a.get("posts_published") or 0) for a in accounts),
        "posts_scheduled_total": sum(int(a.get("posts_scheduled") or 0) for a in accounts),
        "accounts": accounts,
        "official": official,
    }


def build(platform: Path, brand: Path, out: Path, deny_path: Path | None) -> dict:
    rows, tracker_source = tracker_rows(platform)
    needles = needles_from_rows(rows) + needles_from_forms(platform)
    phrases = deny_phrases(platform, deny_path)
    catalog = catalog_block(platform, needles, set(), phrases)
    tokens = catalog.pop("_tokens")
    # Re-filter products now that tribute tokens are known. catalog_block already
    # merged tribute tokens internally; pop removed the private helper.
    sponsors = sponsor_counts(rows, daily_cap(platform))
    forms = form_aggregates(platform)
    sponsors.update(forms)
    sponsors["email_daily_cap"] = sponsors.get("daily_cap") or 3
    sponsors["by_channel"] = outreach_by_channel(rows, forms, sponsors["email_daily_cap"])
    platforms, videos = platforms_block(platform, needles, tokens, phrases)
    brand_clips = clips_from_brand(brand, needles, tokens, phrases)
    dash_clips, dash_summary = clips_from_dashboard(platform, needles, tokens, phrases)
    if brand.is_dir() and (any((brand / name).is_dir() for name in ("candidates", "candidates-music", "clips", "inbox"))):
        clips = brand_clips
        summary = pipeline_from_brand(brand)
        summary["queue"] = dash_summary.get("queue", 0)
        content_source = "content-engine"
    elif dash_clips or dash_summary:
        clips = dash_clips
        summary = dash_summary
        content_source = "dashboard-snapshot"
    else:
        clips = []
        summary = {}
        content_source = "missing"
    emails, pending_previews = email_block(platform, needles, tokens, phrases)
    pipeline = {
        "source_videos": int(summary.get("source_videos") or 0),
        "streams_scanned": int(summary.get("streams_scanned") or 0),
        "music_videos_scanned": int(summary.get("music_videos_scanned") or 0),
        "candidate_files": int(summary.get("candidate_files") or 0),
        "clip_options": len(clips),
        "clips_ticked": sum(1 for clip in clips if clip["status"] == "Approved"),
        "clips_rendered": int(summary.get("clips_rendered") or 0),
        "approved": int(summary.get("approved") or 0),
        "posted": int(summary.get("posted") or 0),
        "ready": int(summary.get("ready") or 0),
        "queue": int(summary.get("queue") or 0),
        "emails_built": emails["emails_built"],
        "mix": "1 music teaser per 3 stream clips",
    }
    highlights = highlights_for(platforms, int(catalog.get("store_published_count") or 0), catalog.get("as_of") or "")
    pipeline_highlights = [
        {"label": "Clip options", "value": f"{pipeline['clip_options']:,}", "as_of": "Scored for the fan-page mix", "icon": "play", "sample": False},
        {"label": "Clips rendered", "value": f"{pipeline['clips_rendered']:,}", "as_of": "Local files only", "icon": "play", "sample": False},
        {"label": "Sponsors sent", "value": f"{sponsors['sent']:,}", "as_of": f"Queued {sponsors['queued']} · email cap {sponsors['daily_cap']}/day", "icon": "target", "sample": False},
        {"label": "Merch email drafts", "value": f"{pipeline['emails_built']:,}", "as_of": "Drafts, not sending", "icon": "bag", "sample": False},
    ]
    fans = fan_block(platform, platforms, needles, tokens, phrases, brand)
    queue = upcoming_queue(brand, needles, tokens, phrases)
    activity = activity_feed(brand, platform, needles, tokens, phrases)
    extract_thumbs(brand, clips, out, limit=6)
    generated = datetime.now(ET).isoformat(timespec="seconds")
    # Prefer live Buffer publish counts when the older clip tracker is still at zero.
    if fans.get("posts_published_total"):
        pipeline["posted"] = max(int(pipeline.get("posted") or 0), int(fans["posts_published_total"]))
    pipeline["queue"] = max(int(pipeline.get("queue") or 0), len(queue), int(fans.get("posts_scheduled_total") or 0))
    if "streams_scanned" not in pipeline:
        pipeline["streams_scanned"] = 0
        pipeline["music_videos_scanned"] = 0
    doc = {
        "schema": "stinc-os.live.v1",
        "generated_at": generated,
        "sources": {"platform": platform.is_dir(), "tracker": tracker_source, "content": content_source},
        "highlights": highlights,
        "pipeline_highlights": pipeline_highlights,
        "platforms": platforms,
        "videos": videos,
        "pipeline": pipeline,
        "clips": clips,
        "queue": queue,
        "activity": activity,
        "sponsors": sponsors,
        "fans": fans,
        "commerce": {key: value for key, value in {**catalog, **emails}.items() if key != "_tokens"},
    }
    issues = find_key_issues(doc)
    blob = json.dumps(doc, ensure_ascii=False)
    issues.extend(find_issues(blob))
    if contains_needle(blob, needles) or contains_token(blob, tokens) or contains_phrase(blob, phrases):
        issues.append("private-term")
    if "/Users/" in blob or "api_key" in blob or "keychain" in blob.casefold():
        issues.append("secret")
    if issues:
        raise SystemExit("refusing to write live.json: " + ",".join(sorted(set(issues))))
    preview_dir = out / "assets/email-previews"
    written = {name for _, name in pending_previews}
    if written:
        preview_dir.mkdir(parents=True, exist_ok=True)
        for src, name in pending_previews:
            (preview_dir / name).write_bytes(src.read_bytes())
    if preview_dir.is_dir():
        for stale in preview_dir.glob("*.png"):
            if stale.name not in written:
                stale.unlink()
    return doc


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a sanitized data/live.json for the public STINC OS site.")
    parser.add_argument("--platform", default=str(Path.home() / "Projects/stinc-platform"))
    parser.add_argument("--brand", default=str(Path.home() / "Projects/content-engine/brands/ralfy-the-plug"))
    parser.add_argument("--out", default=str(ROOT))
    parser.add_argument("--deny", default="")
    args = parser.parse_args()
    out = Path(args.out).expanduser()
    doc = build(Path(args.platform).expanduser(), Path(args.brand).expanduser(), out, Path(args.deny).expanduser() if args.deny else None)
    atomic_write(out / "data/live.json", json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    sponsors = doc["sponsors"]
    print(
        f"wrote {out / 'data/live.json'} clips={doc['pipeline']['clip_options']} "
        f"products_shown={doc['commerce']['shown_count']} emails={len(doc['commerce']['emails'])} "
        f"sponsors_sent={sponsors['sent']} sponsors_queued={sponsors['queued']} "
        f"content={doc['sources']['content']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
