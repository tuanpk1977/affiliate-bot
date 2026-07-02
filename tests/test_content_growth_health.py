from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.content_growth_health import (
    assign_cluster,
    refresh_queue,
    write_auto_repair_report,
    write_social_drafts,
    write_topic_clusters,
)
from modules.operational_health import HealthAudit, PageHealth


def article(url: str, title: str, *, complete: bool = True) -> PageHealth:
    schema = ["Article", "BreadcrumbList", "FAQPage"] if complete else ["Article"]
    return PageHealth(
        url=url,
        file="index.html",
        indexable=True,
        title=title,
        description="Description",
        canonical=url,
        h1=[title],
        schema_types=schema,
        internal_links=["https://smileaireviewhub.com/related/"] if complete else [],
        external_links=["https://example.com/reference"] if complete else [],
        word_count=1200 if complete else 300,
    )


class ContentGrowthHealthTest(unittest.TestCase):
    def test_cluster_and_refresh_outputs(self) -> None:
        coding = article("https://smileaireviewhub.com/cursor-review/", "Cursor AI Coding Review")
        weak = article("https://smileaireviewhub.com/weak-review/", "Weak Review", complete=False)
        audit = HealthAudit(
            pages=[coding, weak],
            sitemap_urls=[coding.url, weak.url],
            sitemap_status="PASS",
            robots_status="PASS",
            duplicate_titles={},
            duplicate_h1={},
            orphan_pages=[],
        )
        self.assertEqual(assign_cluster(coding), "AI Coding Tools")
        self.assertEqual(refresh_queue(audit)[0]["url"], weak.url)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            cluster_md, cluster_json = write_topic_clusters(audit, root)
            social_dir = write_social_drafts([coding], root)
            repair_md, repair_json = write_auto_repair_report(
                {"status": "FAIL"},
                {"repaired": [], "unresolved": {}},
                {"status": "FAIL"},
                root,
            )
            self.assertTrue(cluster_md.exists())
            self.assertTrue(cluster_json.exists())
            self.assertTrue(any(social_dir.glob("*.txt")))
            self.assertTrue(repair_md.exists())
            self.assertTrue(repair_json.exists())


if __name__ == "__main__":
    unittest.main()
