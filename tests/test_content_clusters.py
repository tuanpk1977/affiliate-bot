import unittest

from modules.content_operations import build_content_clusters


class ContentClustersTests(unittest.TestCase):
    def test_creates_cluster_and_internal_link(self):
        inventory = [
            {"slug": "surfer-seo-review", "topic": "Surfer SEO Review", "article_url": "https://example.com/surfer/"},
            {"slug": "surfer-seo-pricing", "topic": "Surfer SEO Pricing", "article_url": "https://example.com/pricing/"},
        ]
        clusters, links = build_content_clusters(inventory)
        self.assertTrue(any(row["cluster"] == "AI SEO" for row in clusters))
        self.assertGreaterEqual(len(links), 1)


if __name__ == "__main__":
    unittest.main()
