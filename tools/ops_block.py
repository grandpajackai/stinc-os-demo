"""Operations snapshot for the public STINC OS site: today's planned vs executed
posts, outreach done vs due today, running processes with health and run times,
and sanitized copies of the designed merch emails.

Stdlib only. Counts and generic labels only: no brand names, contacts, paths or
secrets leave this module.
"""
from __future__ import annotations

import csv
import json
import plistlib
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HOME = Path.home()
PROFILE = {
    "instagram": "https://www.instagram.com/ralfyclips.daily/",
    "tiktok": "https://www.tiktok.com/@ralfyclips.daily",
}
CHANNEL_LABEL = {"instagram": "Instagram", "tiktok": "TikTok", "x": "X", "youtube": "YouTube Shorts"}
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")
STREET_RX = re.compile(r"\b\d{2,6}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+(?:Ave|Avenue|St|Street|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Ln|Lane)\b\.?(?:,\s*[A-Za-z .]+,\s*[A-Z]{2}\s*\d{5})?")
FEATURED_EMAILS = ("05-drop-general", "08-seasonal-bfcm", "01-welcome-1-join", "13-community-clip-of-the-week")
# Only designs whose copy is final enough to show a client. Others keep
# production notes or many unfilled fields and stay private.
FILLS = {
    "{{BACK_IN_STOCK_URL}}": "https://stincteamtgf.com/",
    "{{BTS_CLIP_URL}}": "https://www.instagram.com/ralfyclips.daily/",
    "{{CLAIM_DAYS}}": "[7]",
    "{{CLIP_TITLE}}": "This week’s top clip",
    "{{CLIP_URL}}": "https://www.instagram.com/ralfyclips.daily/",
    "{{DISCOUNT_CODE}}": "[VIPCODE]",
    "{{DRAW_DATE}}": "[Draw date]",
    "{{END_DATETIME}}": "[End time]",
    "{{ENTER_URL}}": "https://www.youtube.com/@ralfytheplug",
    "{{KEYWORD}}": "[STINC]",
    "{{MAILING_ADDRESS}}": "",
    "{{NOTIFY_DAYS}}": "[3]",
    "{{OFFER}}": "[Drop offer]",
    "{{PREFERENCES_URL}}": "#",
    "{{PRIZE_ARV}}": "[Modest prize value]",
    "{{PRIZE_DESCRIPTION}}": "[Sealed pack bundle]",
    "{{RULES_URL}}": "#",
    "{{SHORT_CODE}}": "[55555]",
    "{{START_DATETIME}}": "[Start time]",
    "{{STREAM_DAY}}": "[Day]",
    "{{STREAM_PLATFORM}}": "YouTube",
    "{{STREAM_TIME}}": "[Time]",
    "{{STREAM_TZ}}": "ET",
    "{{STREAM_URL}}": "https://www.youtube.com/@ralfytheplug",
    "{{UNSUBSCRIBE_URL}}": "#",
    "{{VIEW_IN_BROWSER_URL}}": "#",
    "{{VIP_CODE}}": "[VIP24H]",
    "{{VIP_END_TIME}}": "[24h window]",
    "{{WELCOME_OFFER}}": "[Welcome offer]",
}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _dt(value: str):
    if not value:
        return None
    try:
        v = value.strip().replace("Z", "+00:00")
        d = datetime.fromisoformat(v)
        return d.astimezone(ET) if d.tzinfo else d.replace(tzinfo=ET)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip()[:19].replace(" EST", "").replace(" EDT", ""), fmt).replace(tzinfo=ET)
        except ValueError:
            continue
    return None


def _label(d: datetime | None, with_day: bool = False) -> str:
    if not d:
        return ""
    t = d.strftime("%-I:%M %p")
    return f"{d.strftime('%a %b %-d')}, {t} ET" if with_day else f"{t} ET"


def today_posts(brand: Path, clean, cfg: dict, kind_fn, now: datetime | None = None) -> dict:
    """Per-channel planned vs executed for today's ET date, from the post log."""
    now = now or datetime.now(ET)
    log = _load(brand / "posting" / "post-log.json", {})
    posts = log.get("posts") if isinstance(log, dict) else []
    chans = (cfg.get("channels") or {}) if isinstance(cfg, dict) else {}
    out = []
    for name in ("instagram", "tiktok", "x", "youtube"):
        ch = chans.get(name) or {}
        live = bool(ch.get("enabled"))
        items = []
        for p in posts if isinstance(posts, list) else []:
            if not isinstance(p, dict) or p.get("platform") != name:
                continue
            d = _dt(str(p.get("publish_at") or ""))
            if not d or d.date() != now.date():
                continue
            title = clean(str(p.get("hook") or p.get("title") or ""))
            if title is None:
                continue
            url = str(p.get("url") or "")
            if p.get("status") == "sent" and url.startswith("https://"):
                state = "published"
            elif d <= now:
                state = "due"
            else:
                state = "upcoming"
            items.append({"time": _label(d), "at": d.isoformat(), "title": title, "state": state,
                          "url": url if state == "published" else "", "kind": kind_fn(str(p.get("clip_file") or ""), p.get("kind"))})
        items.sort(key=lambda r: r["at"])
        planned = int(ch.get("per_day") or 2) if live else 0
        out.append({
            "channel": CHANNEL_LABEL[name], "key": name, "live": live,
            "planned": max(planned, len(items)) if live else 0,
            "published": sum(1 for i in items if i["state"] == "published"),
            "due": sum(1 for i in items if i["state"] == "due"),
            "upcoming": sum(1 for i in items if i["state"] == "upcoming"),
            "slots": list(ch.get("slot_times_et") or []),
            "profile_url": PROFILE.get(name, "") if live else "",
            "items": items,
        })
    return {"date": now.strftime("%a %b %-d"), "channels": out}


def published_posts(brand: Path, clean, kind_fn, limit: int = 12) -> list[dict]:
    log = _load(brand / "posting" / "post-log.json", {})
    rows = []
    for p in (log.get("posts") or []) if isinstance(log, dict) else []:
        if not isinstance(p, dict) or p.get("status") != "sent" or not str(p.get("url") or "").startswith("https://"):
            continue
        title = clean(str(p.get("hook") or p.get("title") or ""))
        if title is None:
            continue
        d = _dt(str(p.get("posted_at") or p.get("publish_at") or ""))
        rows.append({"platform": p.get("platform"), "title": title, "url": p["url"], "at": d.isoformat() if d else "",
                     "at_label": _label(d, True), "kind": kind_fn(str(p.get("clip_file") or ""), p.get("kind"))})
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows[:limit]


def outreach_today(root: Path, tracker: list[dict], hold, cap: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(ET)
    today = now.date().isoformat()
    due = 0
    for r in tracker:
        if hold(r):
            continue
        for key, sent_status in (("planned_send_date", {"sent", "followup1_sent", "followup2_sent"}),
                                 ("followup1_date", {"followup1_sent", "followup2_sent"}),
                                 ("followup2_date", {"followup2_sent"})):
            if (r.get(key) or "")[:10] == today:
                due += 1
    sent_today = 0
    sent_total = 0
    try:
        with (root / "campaigns/ralfy-sponsors/send_log.csv").open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("dry_run") or "").strip().lower() in {"true", "1", "yes"}:
                    continue
                if (row.get("result") or "").strip().lower() not in {"sent", "ok", "success"}:
                    continue
                sent_total += 1
                if (row.get("time_et") or "")[:10] == today:
                    sent_today += 1
    except OSError:
        pass
    return {"emails_due_today": min(due, cap) if due else 0, "emails_sent_today": sent_today,
            "emails_sent_total": sent_total, "email_daily_cap": cap}


def _launchctl() -> dict:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return {}
    res = {}
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 3:
            res[parts[2]] = {"pid": parts[0], "exit": parts[1]}
    return res


def _next_calendar(cal, now: datetime) -> datetime | None:
    cal = cal if isinstance(cal, list) else [cal]
    best = None
    for day in range(0, 8):
        d = now + timedelta(days=day)
        for c in cal:
            if not isinstance(c, dict):
                continue
            wd = c.get("Weekday")
            if wd is not None and (d.isoweekday() % 7) != int(wd) % 7:
                continue
            cand = d.replace(hour=int(c.get("Hour", 0)), minute=int(c.get("Minute", 0)), second=0, microsecond=0)
            if cand > now and (best is None or cand < best):
                best = cand
        if best:
            return best
    return best


PROCESSES = [
    ("com.gilventures.contentengine.ralfy.post", "Fan-page poster", "Hands finished clips to the scheduler for Instagram and TikTok at the warm-up pace (2 a day per channel) and records each post’s live link."),
    ("com.gilventures.contentengine.ralfy.watchdog", "Posting watchdog", "Checks the poster every 15 minutes and flags anything stuck."),
    ("com.gilventures.contentengine.ralfy", "Content engine", "Scans new streams and videos, scores the moments and cuts vertical clips."),
    ("com.gilventures.stinc.ralfysponsors", "Brand email sender", "Sends partner emails on weekdays, 3 a day at most, with one follow-up after 7 days."),
    ("com.gilventures.stinc.osdata", "Public snapshot refresh", "Refreshes this dashboard from the live system."),
]
ROUTINES = [
    ("Partner-form routine", "Fills brand contact forms, hourly 10:15 AM–7:15 PM ET on weekdays. Up to 10 a day, 30+ minutes apart.", "hourly-forms"),
    ("Outreach check-in", "Confirms the day’s brand emails went out, weekdays at 3:30 PM ET.", "send-confirm"),
    ("Warm-up ramp review", "Reviews posting pace each Monday and raises it only when the accounts are ready.", "warmup"),
]


def _routine_next(kind: str, now: datetime) -> datetime | None:
    if kind == "hourly-forms":
        cal = [{"Weekday": wd, "Hour": h, "Minute": 15} for wd in range(1, 6) for h in range(10, 20)]
    elif kind == "send-confirm":
        cal = [{"Weekday": wd, "Hour": 15, "Minute": 30} for wd in range(1, 6)]
    else:
        cal = [{"Weekday": 1, "Hour": 10, "Minute": 0}]
    return _next_calendar(cal, now)


def processes(root: Path, now: datetime | None = None, agents_dir: Path | None = None) -> list[dict]:
    now = now or datetime.now(ET)
    agents_dir = agents_dir or HOME / "Library/LaunchAgents"
    lc = _launchctl()
    cooldown = _load(HOME / ".local/share/stinc-ralfy/buffer-cooldown.json", {})
    cd_until = _dt(str(cooldown.get("until") or "")) if isinstance(cooldown, dict) else None
    out = []
    for label, name, desc in PROCESSES:
        plist = agents_dir / f"{label}.plist"
        try:
            pl = plistlib.loads(plist.read_bytes())
        except Exception:
            continue
        logp = Path(str(pl.get("StandardOutPath") or ""))
        last = datetime.fromtimestamp(logp.stat().st_mtime, ET) if logp.is_file() else None
        if pl.get("StartInterval"):
            iv = int(pl["StartInterval"])
            nxt = (last + timedelta(seconds=iv)) if last else None
            if nxt and nxt < now:
                nxt = now + timedelta(seconds=iv - ((now - last).seconds % iv))
            cadence = f"Every {iv // 60} minutes"
        elif pl.get("StartCalendarInterval"):
            nxt = _next_calendar(pl["StartCalendarInterval"], now)
            cal = pl["StartCalendarInterval"]
            cal = cal if isinstance(cal, list) else [cal]
            hours = sorted({(c.get("Hour", 0), c.get("Minute", 0)) for c in cal})
            times = ", ".join(datetime(2000, 1, 1, h, m).strftime("%-I:%M %p") for h, m in hours)
            weekdays = all("Weekday" in c for c in cal)
            cadence = ("Weekdays " if weekdays else "Daily ") + times + " ET"
        else:
            nxt, cadence = None, "Always on"
        info = lc.get(label)
        if not info:
            health, note = "Stopped", "Not loaded"
        elif info["exit"] not in ("0", "-") and not (label.endswith(".post") and cd_until and cd_until > now):
            health, note = "Attention", "Last run reported a problem"
        else:
            health, note = "Healthy", ""
        if label.endswith(".post") and cd_until and cd_until > now:
            note = f"Scheduled posts publish on time. Live-link check resumes {_label(cd_until, True)}."
        out.append({"name": name, "what": desc, "cadence": cadence, "health": health, "note": note,
                    "last_run": _label(last, True) if last else "", "next_run": _label(nxt, True) if nxt else ""})
    for name, desc, kind in ROUTINES:
        nxt = _routine_next(kind, now)
        out.append({"name": name, "what": desc, "cadence": "Scheduled routine", "health": "Scheduled", "note": "",
                    "last_run": "", "next_run": _label(nxt, True) if nxt else ""})
    return out


def sanitize_email_html(html: str) -> str:
    html = re.sub(r"<[^>]*>\s*Postal address from[^<]*</[^>]+>", "", html)
    html = re.sub(r"Postal address from[^<]*", "", html)
    html = re.sub(r"Confirm legal sender[^<]*", "", html)
    html = STREET_RX.sub("Mailing address", html)
    html = EMAIL_RX.sub("support email", html).replace("mailto:support email", "#")
    html = PHONE_RX.sub("", html)
    html = html.replace("({{MAILING_ADDRESS}})", "")
    html = html.replace("DEMO DRAFT &middot; DO NOT SEND", "DESIGN PREVIEW")
    html = html.replace(" &middot; Managed in demo by Gil Ventures LLC", "")
    html = re.sub(r"\s*<strong[^>]*>Demo draft only[^<]*</strong>[^<]*", "", html)
    html = re.sub(r"If a welcome offer is later approved[^<]*(?:<br\s*/?>\s*)*", "", html)
    html = re.sub(r"If EVOL approves[^<]*(?:<br\s*/?>\s*)*", "", html)
    html = re.sub(r"If EVOL cuts[^<]*(?:<br\s*/?>\s*)*", "", html)
    html = re.sub(r"OPERATOR GUARDRAIL[^<]*", "", html)
    html = re.sub(r"Optional promo slot:[^<]*", "", html)
    html = re.sub(r"No invented (?:promo codes|discount)[^<]*", "New drops reach this list first.", html)
    html = html.replace("OPTIONAL WELCOME OFFER SLOT", "FIRST LOOK")
    html = re.sub(r"If no time is confirmed[^<]*", "", html)
    html = re.sub(r"Note: Replace[^<]*", "", html)
    html = html.replace("Draft rules inside.", "Sample giveaway layout.")
    html = html.replace("This sweepstakes draft is built for equal odds", "Sample fan giveaway built for equal odds")
    html = re.sub(r"https://stincteamtgf\.com/products/[^\"\s]*asaali[^\"\s]*", "https://stincteamtgf.com/", html, flags=re.I)
    html = re.sub(r"asaali", "Partner brand", html, flags=re.I)
    html = re.sub(r"most requested", "Top pick", html, flags=re.I)
    html = re.sub(r"questions:", "Help:", html, flags=re.I)
    html = html.replace("sweepstakes", "giveaway").replace("Sweepstakes", "Giveaway")
    for key, value in FILLS.items():
        html = html.replace(key, value)
    return html.replace("<head>", '<head><meta name="robots" content="noindex,nofollow">', 1)


def email_pages(root: Path, out: Path, blocked) -> list[dict]:
    """Write sanitized HTML copies of all 14 designed emails. Returns public links."""
    src = root / "ecommerce/emails"
    dest = out / "assets/emails"
    thumbs = out / "assets/email-thumbs"
    links = []
    written = set()
    for html_path in sorted(src.glob("[0-9][0-9]-*.html")):
        stem = html_path.stem
        try:
            html = sanitize_email_html(html_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if EMAIL_RX.search(html) or PHONE_RX.search(html) or "{{" in html or blocked(html):
            continue
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{stem}.html").write_text(html, encoding="utf-8")
        written.add(f"{stem}.html")
        thumb = f"assets/email-thumbs/{stem}.jpg" if (thumbs / f"{stem}.jpg").is_file() else ""
        links.append({"id": stem, "html": f"assets/emails/{stem}.html", "thumb": thumb, "featured": stem in FEATURED_EMAILS})
    if dest.is_dir():
        for stale in dest.glob("*.html"):
            if stale.name not in written:
                stale.unlink()
    return links
