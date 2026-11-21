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
            if key.strip().lower() == "on-screen hook":
                current["hook"] = val.strip()
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
                clips.append({
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
                })
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
    return {
        "source_videos": count_videos(brand / "inbox") + count_videos(brand / "transcribed") + count_videos(brand / "inbox-music"),
        "candidate_files": len(list((brand / "candidates").glob("*.md"))) + len(list((brand / "candidates-music").glob("*.md"))) if brand.is_dir() else 0,
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


def fan_block(root: Path, platforms: dict, needles, tokens, phrases) -> dict:
    data = load_json(root / "data/fan_pages.json", {})
    accounts = []
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
    for row in platforms.get("items") or []:
        accounts.append({
            "platform": row.get("platform") or "",
            "handle": row.get("handle") or "",
            "url": row.get("url") or "",
            "status": row.get("stat") or "",
            "kind": "official",
        })
    posting = str(data.get("posting") or "off") if isinstance(data, dict) else "off"
    if posting not in {"off", "on"}:
        posting = "off"
    return {"name": "Ralfy Clips", "posting": posting, "accounts": accounts}


def build(platform: Path, brand: Path, out: Path, deny_path: Path | None) -> dict:
    rows, tracker_source = tracker_rows(platform)
    needles = needles_from_rows(rows)
    phrases = deny_phrases(platform, deny_path)
    catalog = catalog_block(platform, needles, set(), phrases)
    tokens = catalog.pop("_tokens")
    # Re-filter products now that tribute tokens are known. catalog_block already
    # merged tribute tokens internally; pop removed the private helper.
    sponsors = sponsor_counts(rows, daily_cap(platform))
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
        "candidate_files": int(summary.get("candidate_files") or 0),
        "clip_options": len(clips),
        "clips_ticked": sum(1 for clip in clips if clip["status"] == "Approved"),
        "clips_rendered": int(summary.get("clips_rendered") or 0),
        "approved": int(summary.get("approved") or 0),
        "posted": int(summary.get("posted") or 0),
        "ready": int(summary.get("ready") or 0),
        "queue": int(summary.get("queue") or 0),
        "emails_built": emails["emails_built"],
    }
    highlights = highlights_for(platforms, int(catalog.get("store_published_count") or 0), catalog.get("as_of") or "")
    pipeline_highlights = [
        {"label": "Clip options", "value": f"{pipeline['clip_options']:,}", "as_of": "Scored, not posted", "icon": "play", "sample": False},
        {"label": "Clips rendered", "value": f"{pipeline['clips_rendered']:,}", "as_of": "Local files only", "icon": "play", "sample": False},
        {"label": "Sponsors sent", "value": f"{sponsors['sent']:,}", "as_of": f"Queued {sponsors['queued']} · cap {sponsors['daily_cap']}/day", "icon": "target", "sample": False},
        {"label": "Merch email drafts", "value": f"{pipeline['emails_built']:,}", "as_of": "Drafts, not sending", "icon": "bag", "sample": False},
    ]
    fans = fan_block(platform, platforms, needles, tokens, phrases)
    generated = datetime.now(ET).isoformat(timespec="seconds")
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
