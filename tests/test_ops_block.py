import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ops_block  # noqa: E402

ET = ops_block.ET


class OpsBlockTests(unittest.TestCase):
    def test_sanitize_email_html_strips_contact_and_address(self):
        html = ('<html><head></head><body><a href="mailto:someone@example.com">someone@example.com</a>'
                '<p>1234 Main St, Springfield, CA 90000 ({{MAILING_ADDRESS}})</p>'
                '<p>Postal address from the refund policy. Confirm legal sender.</p>'
                '<p>Call 555-123-4567</p></body></html>')
        out = ops_block.sanitize_email_html(html)
        self.assertNotIn("@example.com", out)
        self.assertNotIn("Main St", out)
        self.assertNotIn("Postal address from", out)
        self.assertNotIn("555-123-4567", out)
        self.assertIn('name="robots"', out)

    def test_today_posts_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand = Path(tmp)
            (brand / "posting").mkdir()
            posts = [
                {"platform": "instagram", "status": "sent", "url": "https://www.instagram.com/reel/x/", "publish_at": "2026-11-23T17:00:00Z", "hook": "A"},
                {"platform": "instagram", "status": "scheduled", "publish_at": "2026-11-24T00:30:00Z", "hook": "B"},
                {"platform": "tiktok", "status": "scheduled", "publish_at": "2026-11-23T17:30:00Z", "hook": "C"},
                {"platform": "tiktok", "status": "scheduled", "publish_at": "2026-11-24T17:30:00Z", "hook": "D"},
            ]
            (brand / "posting" / "post-log.json").write_text(json.dumps({"posts": posts}))
            cfg = {"channels": {"instagram": {"enabled": True, "per_day": 2}, "tiktok": {"enabled": True, "per_day": 2}, "x": {"enabled": False}}}
            now = datetime(2026, 11, 23, 13, 0, tzinfo=ET)
            out = ops_block.today_posts(brand, lambda t: t, cfg, lambda f, k=None: "stream", now)
            ch = {c["key"]: c for c in out["channels"]}
            self.assertEqual((ch["instagram"]["published"], ch["instagram"]["upcoming"]), (1, 1))
            self.assertEqual((ch["tiktok"]["due"], ch["tiktok"]["planned"]), (1, 2))
            self.assertEqual(ch["x"]["planned"], 0)
            self.assertFalse(ch["x"]["live"])

    def test_next_calendar_weekday(self):
        now = datetime(2026, 11, 23, 16, 0, tzinfo=ET)  # Monday
        nxt = ops_block._next_calendar([{"Weekday": 1, "Hour": 10, "Minute": 0}], now)
        self.assertEqual(nxt.date().isoformat(), "2026-11-30")


if __name__ == "__main__":
    unittest.main()
