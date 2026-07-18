from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.platform.affiliate_data import (
    AffiliateCatalog,
    AffiliateValidationError,
    load_affiliate_catalog,
    validate_affiliate_link,
    validate_affiliate_partner,
    validate_affiliate_product,
)
from modules.platform.affiliate_resolver import resolve_affiliate_link
from modules.platform.site_profile import load_site_profile


ROOT = Path(__file__).resolve().parents[1]


def partner_record(**overrides: object) -> dict:
    record = {
        "partner_id": "vendor",
        "company_name": "Vendor",
        "site_id": "smile_ai_review_hub",
        "category": "AI Software",
        "program_name": "Vendor Partner Program",
        "affiliate_url": "https://tracking.partner.example/vendor",
        "destination_domain": "vendor.example",
        "supported_countries": ["US", "VN"],
        "commission_note": "Operator-verified fixture.",
        "cookie_duration_note": "30 days.",
        "disclosure_required": True,
        "status": "active",
        "last_verified_at": "2026-07-18",
        "operator_notes": "Test fixture only.",
    }
    record.update(overrides)
    return record


def product_record(**overrides: object) -> dict:
    record = {
        "product_id": "vendor-pro",
        "partner_id": "vendor",
        "product_name": "Vendor Pro",
        "category": "AI Software",
        "destination_url": "https://app.vendor.example/pro",
        "affiliate_url": "https://tracking.partner.example/vendor-pro",
        "coupon": "",
        "price_note": "Verify current price.",
        "currency": "USD",
        "availability_note": "US and VN.",
        "status": "active",
        "last_verified_at": "2026-07-18",
    }
    record.update(overrides)
    return record


def link_record(**overrides: object) -> dict:
    record = {
        "link_id": "vendor-pro-default",
        "site_id": "smile_ai_review_hub",
        "partner_id": "vendor",
        "product_id": "vendor-pro",
        "category": "AI Software",
        "affiliate_url": "https://tracking.partner.example/vendor-pro",
        "destination_url": "https://app.vendor.example/pro",
        "destination_domain": "vendor.example",
        "supported_countries": ["US", "VN"],
        "disclosure_required": True,
        "status": "active",
        "last_verified_at": "2026-07-18",
        "operator_notes": "Test fixture only.",
    }
    record.update(overrides)
    return record


class AffiliatePlatformTests(unittest.TestCase):
    def test_partner_and_product_schemas(self) -> None:
        partner = validate_affiliate_partner(partner_record())
        product = validate_affiliate_product(product_record())

        self.assertEqual(partner.partner_id, "vendor")
        self.assertEqual(partner.destination_domain, "vendor.example")
        self.assertEqual(product.product_id, "vendor-pro")

    def test_schema_rejects_missing_field(self) -> None:
        record = partner_record()
        del record["program_name"]

        with self.assertRaisesRegex(AffiliateValidationError, "program_name"):
            validate_affiliate_partner(record)

    def test_malformed_url_and_destination_domain_mismatch_are_rejected(self) -> None:
        with self.assertRaisesRegex(AffiliateValidationError, "HTTPS"):
            validate_affiliate_product(product_record(destination_url="not-a-url"))
        with self.assertRaisesRegex(AffiliateValidationError, "does not match"):
            validate_affiliate_link(
                link_record(
                    destination_url="https://unrelated.example/product",
                    destination_domain="vendor.example",
                )
            )

    def test_default_catalog_does_not_import_legacy_or_fake_links(self) -> None:
        catalog = load_affiliate_catalog("smile_ai_review_hub", root=ROOT)

        self.assertEqual(catalog.partners, ())
        self.assertEqual(catalog.products, ())
        self.assertEqual(catalog.links, ())

    def test_resolver_selects_one_active_eligible_link(self) -> None:
        profile = load_site_profile(root=ROOT)
        catalog = AffiliateCatalog(
            site_id=profile.site_id,
            partners=(validate_affiliate_partner(partner_record()),),
            products=(validate_affiliate_product(product_record()),),
            links=(validate_affiliate_link(link_record()),),
        )

        result = resolve_affiliate_link(
            catalog,
            profile,
            product_id="vendor-pro",
            country="VN",
        )

        self.assertEqual(result.status, "eligible")
        self.assertEqual(result.destination_domain, "vendor.example")
        self.assertTrue(result.disclosure_required)
        self.assertEqual(result.disclosure_text, profile.affiliate_disclosure)

    def test_resolver_returns_no_eligible_link_for_inactive_or_wrong_country(self) -> None:
        profile = load_site_profile(root=ROOT)
        catalog = AffiliateCatalog(
            site_id=profile.site_id,
            partners=(validate_affiliate_partner(partner_record()),),
            products=(validate_affiliate_product(product_record()),),
            links=(validate_affiliate_link(link_record(status="inactive")),),
        )

        inactive = resolve_affiliate_link(catalog, profile, product_id="vendor-pro")
        self.assertEqual(inactive.status, "no_eligible_affiliate_link")

        active_catalog = AffiliateCatalog(
            site_id=profile.site_id,
            partners=catalog.partners,
            products=catalog.products,
            links=(validate_affiliate_link(link_record()),),
        )
        wrong_country = resolve_affiliate_link(
            active_catalog,
            profile,
            product_id="vendor-pro",
            country="DE",
        )
        self.assertEqual(wrong_country.status, "no_eligible_affiliate_link")

    def test_resolver_does_not_guess_when_multiple_links_match(self) -> None:
        profile = load_site_profile(root=ROOT)
        catalog = AffiliateCatalog(
            site_id=profile.site_id,
            partners=(validate_affiliate_partner(partner_record()),),
            products=(validate_affiliate_product(product_record()),),
            links=(
                validate_affiliate_link(link_record()),
                validate_affiliate_link(
                    link_record(
                        link_id="vendor-pro-second",
                        affiliate_url="https://tracking.partner.example/vendor-pro-b",
                    )
                ),
            ),
        )

        result = resolve_affiliate_link(catalog, profile, category="AI Software")

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.affiliate_url, "")

    def test_catalog_loader_validates_cross_references(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_dir = root / "config" / "sites"
            profile_dir.mkdir(parents=True)
            source_profile = ROOT / "config" / "sites" / "smile_ai_review_hub.json"
            (profile_dir / source_profile.name).write_text(
                source_profile.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            affiliate_dir = (
                root
                / "data"
                / "sites"
                / "smile_ai_review_hub"
                / "affiliate"
            )
            affiliate_dir.mkdir(parents=True)
            payloads = {
                "partners.json": {"partners": [partner_record()]},
                "products.json": {
                    "products": [product_record(partner_id="missing-partner")]
                },
                "links.json": {"links": []},
            }
            for filename, payload in payloads.items():
                payload.update(
                    {"schema_version": 1, "site_id": "smile_ai_review_hub"}
                )
                (affiliate_dir / filename).write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )

            with self.assertRaisesRegex(AffiliateValidationError, "unknown partner"):
                load_affiliate_catalog("smile_ai_review_hub", root=root)


if __name__ == "__main__":
    unittest.main()
