from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.source_connectors import SOURCE_STATUSES, SourceConnectorFramework


class SourceConnectorsTests(unittest.TestCase):
    def test_connector_status_labels_are_safe_and_deterministic(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            offers = root / "offers.csv"
            affiliate = root / "affiliate_links.csv"
            offers.write_text(
                "\n".join(
                    [
                        "offer_id,brand_name,website,affiliate_url,niche,commission_type,commission_rate,flat_commission,cookie_days,recurring,traffic_policy,direct_linking_allowed,brand_bidding_allowed,vendor_trust,buyer_intent,notes",
                        "cursor,Cursor,https://cursor.com,https://cursor.com/aff,AI Coding,recurring,25,0,30,True,allowed,False,False,88,84,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            affiliate.write_text(
                "\n".join(
                    [
                        "tool_slug,tool_name,brand,slug,official_url,affiliate_url,affiliate_status,status,notes,commission_note,network,approved",
                        "cursor,Cursor,Cursor,cursor,https://cursor.com,https://cursor.com/aff,active,active,fixture,25% recurring,PartnerStack,True",
                    ]
                ),
                encoding="utf-8",
            )
            framework = SourceConnectorFramework(offers_file=offers, affiliate_links_file=affiliate)
            result = framework.collect("cursor pricing", {"products": ["Cursor"], "competitors": ["Cursor"]})

            self.assertIn("pricing_page", result)
            self.assertTrue(result["pricing_page"])
            statuses = {item["status"] for items in result.values() for item in items}
            self.assertTrue(statuses.issubset(SOURCE_STATUSES))
            self.assertIn("verified", statuses)
            self.assertIn("missing", statuses)


if __name__ == "__main__":
    unittest.main()
