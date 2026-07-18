from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.platform.site_profile import (
    DEFAULT_SITE_ID,
    SiteProfileError,
    get_active_site_profile,
    list_site_profiles,
    load_site_profile,
    validate_site_profile,
)


ROOT = Path(__file__).resolve().parents[1]


class SiteProfileTests(unittest.TestCase):
    def test_default_profile_preserves_smile_ai_compatibility(self) -> None:
        profile = load_site_profile(root=ROOT)

        self.assertEqual(profile.site_id, DEFAULT_SITE_ID)
        self.assertEqual(profile.domain, "https://smileaireviewhub.com")
        self.assertEqual(profile.output["site_output_dir"], "site_output")
        self.assertEqual(profile.output["production_output_dir"], "docs")
        self.assertEqual(
            profile.output["published_static_pages_dir"],
            "data/published_static_pages",
        )
        self.assertTrue(profile.editorial_settings["human_approval_required"])
        self.assertTrue(profile.social_platform_settings["manual_publish_only"])
        self.assertEqual(profile.source_policy["minimum_usable_sources"], 2)

    def test_load_profile_by_site_id_and_list_profiles(self) -> None:
        profile = load_site_profile("example_sports", root=ROOT)

        self.assertEqual(profile.site_id, "example_sports")
        self.assertFalse(profile.active)
        self.assertTrue(profile.example)
        self.assertEqual(
            list_site_profiles(root=ROOT),
            ["example_health", "example_sports", "smile_ai_review_hub"],
        )

    def test_inactive_profile_is_rejected_when_active_is_required(self) -> None:
        with self.assertRaisesRegex(SiteProfileError, "inactive"):
            get_active_site_profile("example_health", root=ROOT)

    def test_example_profile_cannot_be_used_for_production(self) -> None:
        with self.assertRaisesRegex(SiteProfileError, "inactive|production_enabled|Example"):
            load_site_profile("example_sports", root=ROOT, for_production=True)

    def test_missing_required_field_has_clear_error(self) -> None:
        raw = json.loads(
            (ROOT / "config" / "sites" / "smile_ai_review_hub.json").read_text(
                encoding="utf-8"
            )
        )
        del raw["domain"]

        with self.assertRaisesRegex(SiteProfileError, "domain"):
            validate_site_profile(raw)

    def test_requested_profile_does_not_silently_fallback(self) -> None:
        with self.assertRaisesRegex(SiteProfileError, "was not found"):
            load_site_profile("missing_site", root=ROOT)

    def test_secret_like_fields_are_rejected(self) -> None:
        raw = json.loads(
            (ROOT / "config" / "sites" / "smile_ai_review_hub.json").read_text(
                encoding="utf-8"
            )
        )
        raw["seo_defaults"]["api_key"] = "not-allowed"

        with self.assertRaisesRegex(SiteProfileError, "Secret-like"):
            validate_site_profile(raw)

    def test_invalid_json_reports_location(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_dir = root / "config" / "sites"
            profile_dir.mkdir(parents=True)
            (profile_dir / "broken.json").write_text("{", encoding="utf-8")

            with self.assertRaisesRegex(SiteProfileError, "line 1"):
                load_site_profile("broken", root=root)


if __name__ == "__main__":
    unittest.main()
