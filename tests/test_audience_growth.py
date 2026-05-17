from __future__ import annotations

import json
import unittest

from config import settings
from modules.audience_growth import (
    checklist_items,
    email_capture_setup_faq,
    ensure_email_capture_config,
    ensure_subscribers_csv,
    formspree_setup_faq,
    lead_form,
    page_shell,
    social_plan_content,
)


class AudienceGrowthTests(unittest.TestCase):
    def test_email_capture_config_is_local_safe(self) -> None:
        ensure_email_capture_config()
        payload = json.loads((settings.base_dir / "config" / "email_capture.json").read_text(encoding="utf-8"))
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["provider"], "formspree")
        self.assertEqual(payload["form_endpoint"], "")
        self.assertEqual(payload["honeypot_field"], "_gotcha")
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

    def test_email_capture_setup_faq_is_static_honest(self) -> None:
        faq = dict(email_capture_setup_faq("en"))
        combined = " ".join(faq.values()).lower()
        self.assertIn("static", combined)
        self.assertIn("cannot write", combined)
        self.assertIn("formspree", combined)

    def test_formspree_setup_faq_mentions_no_api_key(self) -> None:
        combined = " ".join(dict(formspree_setup_faq("en")).values()).lower()
        self.assertIn("api key", combined)
        self.assertIn("endpoint", combined)

    def test_lead_form_setup_mode_does_not_post(self) -> None:
        form = lead_form("en")
        self.assertIn('data-email-capture-mode="setup"', form)
        self.assertIn('name="email"', form)
        self.assertIn('name="source_page"', form)
        self.assertIn('name="language"', form)
        self.assertIn('name="lead_magnet"', form)
        self.assertIn('name="_gotcha"', form)
        self.assertNotIn("https://formspree.io", form)
        self.assertNotIn('method="POST"', form)

    def test_social_plan_has_no_fake_affiliate_link(self) -> None:
        content = social_plan_content("Cursor cleanup", "linkedin", "en", "story/comparison/case study")
        lowered = content.lower()
        self.assertIn("workflow checklist", lowered)
        self.assertNotIn("affiliate link here", lowered)
        self.assertNotIn("example.com", lowered)


if __name__ == "__main__":
    unittest.main()
