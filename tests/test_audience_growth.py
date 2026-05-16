from __future__ import annotations

import json
import unittest

from config import settings
from modules.audience_growth import (
    checklist_items,
    ensure_email_capture_config,
    ensure_subscribers_csv,
    page_shell,
    social_plan_content,
)


class AudienceGrowthTests(unittest.TestCase):
    def test_email_capture_config_is_local_safe(self) -> None:
        ensure_email_capture_config()
        payload = json.loads((settings.base_dir / "config" / "email_capture.json").read_text(encoding="utf-8"))
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["storage"], "csv")
        self.assertNotIn("api_key", payload)

    def test_subscribers_csv_header(self) -> None:
        ensure_subscribers_csv()
        header = (settings.data_dir / "subscribers.csv").read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertEqual(header, "email,source_page,language,created_at,status")

    def test_checklist_has_required_ten_steps(self) -> None:
        self.assertEqual(len(checklist_items("en")), 10)
        self.assertEqual(len(checklist_items("vi")), 10)
        self.assertIn("Windsurf", checklist_items("en")[0])
        self.assertIn("Windsurf", checklist_items("vi")[0])

    def test_page_shell_has_canonical_and_hreflang(self) -> None:
        html = page_shell("Test", "Description", "/about/", "<h1>Test</h1>", "en")
        self.assertIn('rel="canonical"', html)
        self.assertIn('hreflang="en"', html)
        self.assertIn('hreflang="vi"', html)
        self.assertIn("Tiếng Việt", html)

    def test_social_plan_has_no_fake_affiliate_link(self) -> None:
        content = social_plan_content("Cursor cleanup", "linkedin", "en", "story/comparison/case study")
        lowered = content.lower()
        self.assertIn("workflow checklist", lowered)
        self.assertNotIn("affiliate link here", lowered)
        self.assertNotIn("example.com", lowered)


if __name__ == "__main__":
    unittest.main()
