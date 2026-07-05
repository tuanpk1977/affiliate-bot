import unittest

from modules.content_operations import build_authority_score


class AuthorityScoreTests(unittest.TestCase):
    def test_groups_seo_cluster(self):
        inventory = [
            {"slug": "surfer-seo-review", "topic": "Surfer SEO Review", "index_status": "Tracked", "impressions": 100, "google_clicks": 4, "avg_position": 12},
            {"slug": "semrush-vs-ahrefs", "topic": "Semrush vs Ahrefs", "index_status": "Tracked", "impressions": 50, "google_clicks": 2, "avg_position": 18},
        ]
        rows = build_authority_score(inventory)
        clusters = {row["cluster"] for row in rows}
        self.assertIn("AI SEO", clusters)


if __name__ == "__main__":
    unittest.main()
