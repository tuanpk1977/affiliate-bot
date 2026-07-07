from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from modules.content_analytics import ContentAnalytics
from modules.editorial_automation import CandidateTopicRecord
from modules.self_optimization import SelfOptimization


class SelfOptimizationTests(unittest.TestCase):
    def test_reweights_candidates_and_writes_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            tracking_csv = data_dir / "content_growth_performance_log.csv"
            tracking_csv.parent.mkdir(parents=True, exist_ok=True)
            tracking_csv.write_text(
                "\n".join(
                    [
                        "publish_date,url,topic,article_type,source_keyword,google_indexed_status,bing_discovered_status,bing_indexed_status,yandex_index_status,impressions,clicks,ctr,average_position,social_views,youtube_views,affiliate_clicks,revenue,notes",
                        "2026-07-01,https://example.com/validation-editorial-topic-2/,validation editorial topic 2,comparison,validation editorial topic 2,pending,pending,pending,pending,300,20,6,14,0,0,12,60,fixture",
                    ]
                ),
                encoding="utf-8",
            )
            analytics = ContentAnalytics(data_dir=data_dir, tracking_csv=tracking_csv, config={"enabled": True})
            analytics.build_performance_report()
            optimizer = SelfOptimization(data_dir=data_dir, config={"enabled": True}, analytics=analytics)
            candidates = [
                CandidateTopicRecord(
                    generated_at="2026-07-07T00:00:00+00:00",
                    keyword="validation editorial topic 1",
                    title="validation editorial topic 1",
                    slug="validation-editorial-topic-1",
                    intent="commercial",
                    category="AI Software",
                    cluster="cluster 1",
                    score=80,
                    popularity=70,
                    freshness=70,
                    seo_opportunity=65,
                    affiliate_opportunity=60,
                    commercial_intent=68,
                    competition=35,
                    existing_website_coverage=0,
                    source_count=3,
                    source_list=["static"],
                    priority="P1",
                    article_type="comparison",
                    affiliate_score="high",
                    estimated_article_count=7,
                    related_keywords=[],
                    planning_reasoning=[],
                    already_published=False,
                ),
                CandidateTopicRecord(
                    generated_at="2026-07-07T00:00:00+00:00",
                    keyword="validation editorial topic 2",
                    title="validation editorial topic 2",
                    slug="validation-editorial-topic-2",
                    intent="commercial",
                    category="AI Software",
                    cluster="cluster 2",
                    score=75,
                    popularity=70,
                    freshness=70,
                    seo_opportunity=65,
                    affiliate_opportunity=60,
                    commercial_intent=68,
                    competition=35,
                    existing_website_coverage=0,
                    source_count=3,
                    source_list=["static"],
                    priority="P1",
                    article_type="comparison",
                    affiliate_score="high",
                    estimated_article_count=7,
                    related_keywords=[],
                    planning_reasoning=[],
                    already_published=False,
                ),
            ]

            weighted = optimizer.reweight_candidates(candidates)
            report = optimizer.generate_report()

            boosted = next(item for item in weighted if item.slug == "validation-editorial-topic-2")
            self.assertGreater(boosted.score, 75)
            self.assertTrue((data_dir / "optimization_report.json").exists())
            self.assertTrue((data_dir / "optimization_report.csv").exists())
            self.assertTrue((data_dir / "optimization_report.md").exists())
            self.assertIn("actions", report)


if __name__ == "__main__":
    unittest.main()
