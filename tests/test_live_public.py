#!/usr/bin/env python3
"""The committed public snapshot must stay free of contact data and secrets."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from public_safety import find_issues, find_key_issues  # noqa: E402

LIVE = ROOT / "data/live.json"


class LivePublicTests(unittest.TestCase):
    def test_live_json_has_no_contacts_or_secrets(self):
        self.assertTrue(LIVE.is_file(), "data/live.json is missing")
        text = LIVE.read_text(encoding="utf-8")
        data = json.loads(text)
        self.assertEqual(data.get("schema"), "stinc-os.live.v1")
        self.assertEqual(find_issues(text), [])
        self.assertEqual(find_key_issues(data), [])
        self.assertNotIn("/Users/", text)
        self.assertNotIn("keychain", text.casefold())
        self.assertNotIn("smtp", text.casefold())
        self.assertGreater(len(data.get("clips") or []), 0)
        self.assertGreater(len(data.get("commerce", {}).get("products") or []), 0)
        self.assertGreater(len(data.get("commerce", {}).get("emails") or []), 0)
        self.assertIsInstance(data.get("sponsors", {}).get("sent"), int)
        for clip in data["clips"]:
            url = clip.get("watch_url") or ""
            self.assertTrue(url == "" or url.startswith("https://www.youtube.com/watch?v=") or url.startswith("https://youtu.be/"))
        self.assertTrue(any(row.get("label") == "Spotify listeners" for row in data.get("highlights") or []))


if __name__ == "__main__":
    unittest.main()
