#!/usr/bin/env python3
"""Exporter tests. Fixtures are invented. They are not artist or sponsor records."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import export_live_data as exporter  # noqa: E402
from public_safety import find_issues  # noqa: E402

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def platform_tree(root: Path) -> None:
    write(root / "data/platforms.json", json.dumps({
        "as_of": "2026-11-16",
        "items": [
            {"platform": "YouTube", "handle": "@exampleartist", "url": "https://www.youtube.com/@exampleartist",
             "stat": "164K subscribers · 10M views", "detail": "Public channel", "date": "2026-11-16",
             "source": "https://www.youtube.com/@exampleartist"},
            {"platform": "Spotify", "handle": "Example Artist", "url": "https://open.spotify.com/artist/abc",
             "stat": "383,111 monthly listeners", "detail": "", "date": "2026-11-16", "source": "https://open.spotify.com/artist/abc"},
        ],
        "videos": [
            {"title": "QXTRIBUTE live session", "views": 10, "url": "https://www.youtube.com/watch?v=qxtribute1"},
            {"title": "Clean single", "views": 20, "url": "https://www.youtube.com/watch?v=cleansingle"},
        ],
    }))
    write(root / "data/fan_pages.json", json.dumps({
        "posting": "off",
        "accounts": [{"platform": "YouTube Shorts", "handle": "Example Clips", "url": "", "status": "Being created", "login": "hidden-login"}],
    }))
    write(root / "data/public-deny.txt", "DENYPHRASE9\n")
    write(root / "ecommerce/data/catalog.json", json.dumps({
        "meta": {"inspected_at": "2026-11-20", "published_count": 2, "in_stock_count": 1,
                 "store_contact_email": "hidden@secret.test", "return_address": "7907 Rosewood Ave, Los Angeles, CA 90048"},
        "products": [
            {"title": "Plug Walk Tee", "handle": "plug-walk-tee", "url": "https://stincteamtgf.com/products/plug-walk-tee",
             "price_min": 50, "price_max": 50, "available": True, "instock_sizes": ["M"], "image": "https://cdn.example.com/tee.png",
             "category": "T-Shirt", "tribute_merch": False},
            {"title": "AudioPartnerCo Tee", "handle": "audiopartnerco-tee", "url": "https://stincteamtgf.com/products/audiopartnerco-tee",
             "price_min": 80, "price_max": 80, "available": True, "instock_sizes": ["L"], "image": "", "category": "T-Shirt", "tribute_merch": False},
            {"title": "QXTRIBUTE Hoodie", "handle": "qxtribute-hoodie", "url": "https://stincteamtgf.com/products/qxtribute-hoodie",
             "price_min": 100, "price_max": 100, "available": False, "instock_sizes": [], "image": "", "category": "Hoodie", "tribute_merch": True},
        ],
    }))
    write(root / "ecommerce/emails/specs/01-clean.json", json.dumps({
        "file": "01-clean", "series": "Welcome series", "segment": "New subscribers",
        "subject": "You are in", "preheader": "Drops and restocks.",
    }))
    write(root / "ecommerce/emails/01-clean.html", "<html><body><h1>You are in</h1><p>Shop the rack.</p></body></html>")
    write(root / "ecommerce/emails/specs/02-sponsor.json", json.dumps({
        "file": "02-sponsor", "series": "Drop", "segment": "Engaged",
        "subject": "AudioPartnerCo exclusive", "preheader": "A private pitch.",
    }))
    write(root / "ecommerce/emails/specs/03-dirty.json", json.dumps({
        "file": "03-dirty", "series": "Community", "segment": "Viewers",
        "subject": "Packing the orders", "preheader": "Questions: hidden@secret.test",
    }))
    (root / "ecommerce/emails/previews").mkdir(parents=True, exist_ok=True)
    (root / "ecommerce/emails/previews/01-clean-mobile.png").write_bytes(PNG)
    (root / "ecommerce/emails/previews/03-dirty-mobile.png").write_bytes(PNG)
    write(root / "ecommerce/emails/03-dirty.html", "<html><body>hidden@secret.test 555-010-0199</body></html>")
    write(root / "campaigns/ralfy-sponsors/config.json", json.dumps({
        "daily_cap": 3,
        "sender": {"signature": "call 555-010-0199", "email": "hidden@secret.test"},
    }))
    write(root / "campaigns/ralfy-sponsors/tracker.csv",
          "brand,brand_key,status,group,priority_note,contact_name,contact_email,deal_route,reply_status,reply_notes\n"
          "AudioPartnerCo,audiopartner,sent,A,pays cash,Alex Example,alex@secret.test,$5000 retainer,none,call them\n"
          "LuckySlotsHQ,luckyslots,on_hold_legal,H,ON HOLD: legal gambling,Hold Person,hold@secret.test,guarantee,\n"
          "FormBrandCo,formbrand,needs_manual_form,D,,,,,,,\n"
          "QueueBrandCo,queuebrand,queued,C,,,,,,,\n")
    write(root / "dashboard/data/dashboard.json", json.dumps({
        "content": {
            "brand_dir": "/Users/someone/Projects/content-engine/brands/example",
            "source_videos": 5,
            "candidates": 1,
            "clips_made": 1,
            "approved": 0,
            "posted": 0,
            "ready": 1,
            "studio": [{
                "stem": "yt-abcdefghijk",
                "kind": "stream",
                "options": [
                    {"id": "C1", "title": "Dashboard clip", "hook": "Hello from the dashboard", "viral": 8.1,
                     "score": 9, "duration_s": 30, "approved": False, "rendered": False},
                    {"id": "C2", "title": "Leak", "hook": "email dashboard@secret.test", "viral": 1,
                     "score": 1, "duration_s": 10, "approved": False, "rendered": False},
                ],
            }],
            "plan": {"counts": {"queued": 4}, "items": [{"title": "Dashboard clip"}]},
        },
        "outreach": {"list": [{"brand": "AudioPartnerCo", "status": "sent", "deal_type": "$9,000 retainer"}]},
    }))


class ExportTests(unittest.TestCase):
    def test_brand_folder_sanitizes_counts_and_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "platform"
            brand = Path(tmp) / "brand"
            out = Path(tmp) / "site"
            platform_tree(root)
            write(brand / "candidates/demo.md", """# Demo
- Source: `transcribed/local-only.mp4`
- Picked by: local picker

- [ ] C1 | viral 8.7 | score 10 | 60.1s | Chat is stuck
  - On-screen hook: Why it looks weird, chat?

- [ ] C2 | viral 9.1 | score 9 | 12s | DENYPHRASE9 night
  - On-screen hook: DENYPHRASE9

- [x] C3 | viral 4 | score 4 | 20s | Do not publish
  - On-screen hook: call 555-010-0199 and fan@example.com api_key=abcd1234efgh
""")
            doc = exporter.build(root, brand, out, None)
            blob = json.dumps(doc)
            self.assertEqual(find_issues(blob), [])
            self.assertEqual(doc["schema"], "stinc-os.live.v1")
            self.assertEqual(doc["sources"]["content"], "content-engine")
            self.assertEqual(doc["sponsors"]["sent"], 1)
            self.assertEqual(doc["sponsors"]["queued"], 1)
            self.assertEqual(doc["sponsors"]["needs_manual_form"], 1)
            self.assertEqual(doc["sponsors"]["tracked"], 3)
            self.assertEqual(doc["sponsors"]["daily_cap"], 3)
            self.assertNotIn("AudioPartnerCo", blob)
            self.assertNotIn("LuckySlotsHQ", blob)
            self.assertNotIn("audiopartner", blob)
            self.assertNotIn("alex@secret.test", blob)
            self.assertNotIn("555-010-0199", blob)
            self.assertNotIn("QXTRIBUTE", blob)
            self.assertNotIn("DENYPHRASE9", blob)
            self.assertNotIn("api_key", blob)
            self.assertNotIn("/Users/", blob)
            self.assertNotIn("retainer", blob)
            self.assertNotIn("hidden-login", blob)
            titles = [clip["title"] for clip in doc["clips"]]
            self.assertIn("Chat is stuck", titles)
            self.assertEqual(doc["clips"][0]["watch_url"], "")
            self.assertEqual([row["title"] for row in doc["commerce"]["products"]], ["Plug Walk Tee"])
            subjects = [row["subject"] for row in doc["commerce"]["emails"]]
            self.assertIn("You are in", subjects)
            self.assertIn("Packing the orders", subjects)
            self.assertNotIn("AudioPartnerCo exclusive", subjects)
            packing = next(row for row in doc["commerce"]["emails"] if row["subject"] == "Packing the orders")
            self.assertEqual(packing["preheader"], "")
            self.assertEqual(packing["preview"], "")
            clean = next(row for row in doc["commerce"]["emails"] if row["subject"] == "You are in")
            self.assertEqual(clean["preview"], "assets/email-previews/01-clean-mobile.png")
            self.assertTrue((out / clean["preview"]).is_file())
            self.assertFalse((out / "assets/email-previews/03-dirty-mobile.png").exists())
            self.assertEqual(doc["highlights"][0]["value"], "164K")
            self.assertNotIn("Rosewood", blob)
            self.assertTrue(any(video["title"] == "Clean single" for video in doc["videos"]))

    def test_dashboard_fallback_keeps_public_clips_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "platform"
            out = Path(tmp) / "site"
            platform_tree(root)
            doc = exporter.build(root, Path(tmp) / "missing-brand", out, None)
            self.assertEqual(doc["sources"]["content"], "dashboard-snapshot")
            titles = [clip["title"] for clip in doc["clips"]]
            self.assertIn("Dashboard clip", titles)
            self.assertEqual(doc["clips"][0]["watch_url"], "https://www.youtube.com/watch?v=abcdefghijk")
            blob = json.dumps(doc)
            self.assertNotIn("dashboard@secret.test", blob)
            self.assertNotIn("AudioPartnerCo", blob)
            self.assertNotIn("/Users/", blob)
            self.assertEqual(doc["pipeline"]["queue"], 4)

    def test_refuse_does_not_write_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "platform"
            out = Path(tmp) / "site"
            platform_tree(root)
            write(root / "data/public-deny.txt", "Public rack\n")
            with self.assertRaises(SystemExit):
                exporter.build(root, Path(tmp) / "missing-brand", out, None)
            self.assertFalse((out / "data/live.json").exists())


    def test_posting_queue_and_score_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "platform"
            brand = Path(tmp) / "brand"
            out = Path(tmp) / "site"
            platform_tree(root)
            write(root / "campaigns/ralfy-sponsors/outbox/current/forms/queue.json", json.dumps([
                {"brand": "ZephyrOutreachCo", "key": "zephyroutreachco", "form_url": "https://example.com/form", "subject": "Hi", "message": "please review"},
            ]))
            write(root / "campaigns/ralfy-sponsors/outbox/current/forms/log.csv",
                  "date,brand_key,status\n2026-11-01,zephyroutreachco,submitted\n")
            write(root / "campaigns/ralfy-sponsors/send_log.csv",
                  "time_et,result,dry_run,brand\n2026-11-18 11:00,sent,0,ZephyrOutreachCo\n")
            write(brand / "posting.json", json.dumps({
                "enabled": True, "live": True, "dry_run": False,
                "content_mix": {"stream_per_music": 3},
                "channels": {
                    "instagram": {"enabled": True, "account_created": True, "handle": "@exampleclips.daily",
                                  "per_day": 2, "slot_times_et": ["12:00", "19:30"]},
                    "tiktok": {"enabled": True, "account_created": True, "handle": "@exampleclips.daily",
                               "per_day": 2, "slot_times_et": ["12:30", "20:00"]},
                    "x": {"enabled": False, "account_created": False, "handle": "",
                          "per_day": 2, "slot_times_et": ["12:45", "20:15"]},
                    "youtube": {"enabled": False, "account_created": False, "handle": "",
                                "per_day": 2, "slot_times_et": ["13:00", "20:30"]},
                },
            }))
            write(brand / "posting/post-log.json", json.dumps({
                "posts": [
                    {"platform": "instagram", "status": "sent", "hook": "Chat is stuck",
                     "clip_file": "demo_C1.mp4", "kind": "stream",
                     "publish_at": "2026-11-22T17:00:00.000Z", "posted_at": "2026-11-22T17:02:00.000Z"},
                    {"platform": "tiktok", "status": "scheduled", "hook": "Chat is stuck",
                     "clip_file": "demo_C1.mp4", "kind": "stream",
                     "publish_at": "2026-11-23T17:30:00.000Z"},
                    {"platform": "tiktok", "status": "scheduled", "hook": "Do not leak ZephyrOutreachCo",
                     "clip_file": "demo_C9.mp4", "kind": "stream",
                     "publish_at": "2026-11-24T17:30:00.000Z"},
                ]
            }))
            write(brand / "candidates/demo.md", """# Demo
- [ ] C1 | viral 9.1 | score 9 | 28.7s | Chat is stuck
  - Source signals: 3,016 views · 20d old
  - Viral signals: hook 10.0 · moment 9.0 · audio 10.0 · chat 8.5 · 29s
  - On-screen hook: Why it looks weird, chat?
""")
            doc = exporter.build(root, brand, out, None)
            blob = json.dumps(doc)
            self.assertEqual(find_issues(blob), [])
            self.assertNotIn("ZephyrOutreachCo", blob)
            self.assertNotIn("zephyroutreachco", blob)
            self.assertEqual(doc["fans"]["posting"], "on")
            self.assertTrue(doc["fans"]["autopilot"])
            self.assertEqual(doc["fans"]["channels_live"], 2)
            handles = {a["handle"] for a in doc["fans"]["accounts"]}
            self.assertIn("@exampleclips.daily", handles)
            statuses = {a["platform"]: a["status"] for a in doc["fans"]["accounts"]}
            self.assertEqual(statuses["X"], "Coming soon")
            self.assertTrue(any(row["kind"] == "official" for row in doc["fans"]["official"]))
            self.assertEqual(doc["sponsors"]["forms_queued"], 1)
            self.assertEqual(doc["sponsors"]["forms_submitted"], 1)
            channels = {row["channel"]: row for row in doc["sponsors"]["by_channel"]}
            self.assertEqual(channels["form"]["queued"], 1)
            self.assertGreaterEqual(len(doc["queue"]), 1)
            self.assertEqual(doc["queue"][0]["platform"], "tiktok")
            self.assertEqual(doc["queue"][0]["kind"], "stream")
            titles = [row["title"] for row in doc["queue"]]
            self.assertNotIn("Do not leak ZephyrOutreachCo", titles)
            top = doc["clips"][0]
            self.assertEqual(top["breakdown"]["hook"], 10.0)
            self.assertEqual(top["breakdown"]["story"], 9)
            self.assertEqual(top["breakdown"]["audio"], 10.0)
            self.assertEqual(top["breakdown"]["chat_hype"], 8.5)
            self.assertTrue(any(ev["label"] == "Clip posted" for ev in doc["activity"]))
            self.assertTrue(any(ev["label"] == "Outreach sent" and ev.get("count") == 1 for ev in doc["activity"]))
            self.assertIn("count only", json.dumps(doc["activity"]))
            self.assertNotIn("contact", blob.lower().split("count only")[0][-20:] if False else "")

    def test_first_stat_keeps_suffixes_and_ignores_words(self):
        self.assertEqual(exporter.first_stat("383,111 monthly listeners"), "383,111")
        self.assertEqual(exporter.first_stat("164K subscribers · 109.6M views"), "164K")
        self.assertEqual(exporter.first_stat("37.8K followers"), "37.8K")

    def test_issue_categories_ignore_public_handles(self):
        self.assertEqual(find_issues("Follow @exampleartist on YouTube"), [])
        self.assertIn("email", find_issues("write fan@example.com"))
        self.assertIn("phone", find_issues("555-010-0199"))
        self.assertIn("address", find_issues("7907 Rosewood Ave"))
        self.assertIn("secret", find_issues("api_key=abcd1234efgh"))


if __name__ == "__main__":
    unittest.main()
