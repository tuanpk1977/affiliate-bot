from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from modules.editorial_operations_console import EditorialOperationsConsole


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _seed_console_state(root: Path) -> EditorialOperationsConsole:
    data_dir = root / "data"
    site_output = root / "site_output"
    published_dir = data_dir / "published_static_pages"
    slug = "best-ai-productivity-software"
    draft_dir = data_dir / "production_article_drafts" / slug
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "article.md").write_text("# Draft\n", encoding="utf-8")
    (draft_dir / "index.html").write_text(
        "<html><body><h2>Affiliate disclosure</h2><p>We may earn a commission.</p></body></html>",
        encoding="utf-8",
    )
    (draft_dir / "review_summary.md").write_text("# Review Summary\n", encoding="utf-8")
    (draft_dir / "publish_readiness_report.md").write_text("# Publish Readiness Report\n", encoding="utf-8")

    review = {
        "slug": slug,
        "topic": "best ai productivity software",
        "url": "https://example.com/best-ai-productivity-software/",
        "status": "needs_human_review",
        "reviewed_at": "2026-07-07T11:51:48+00:00",
        "word_count": 3418,
        "factual_quality": 70.0,
        "source_quality": 89.5,
        "seo_title_meta_quality": 100,
        "affiliate_disclosure_present": True,
        "internal_link_count": 5,
        "duplicate_content_risk": 10.0,
        "readability": 58.37,
        "business_value": 61.35,
        "publish_readiness": 83.65,
        "publishable": True,
        "requires_human_approval": True,
        "failures": [],
    }
    human = {
        "slug": slug,
        "topic": "best ai productivity software",
        "status": "needs_human_review",
        "required": True,
        "reviewed_at": "2026-07-07T11:51:48+00:00",
        "approved_at": "",
        "approved_by": "",
        "reason": "",
    }
    publish = {
        "slug": slug,
        "topic": "best ai productivity software",
        "status": "blocked",
        "checked_at": "2026-07-07T11:51:49+00:00",
        "failures": ["human approval missing"],
        "research_quality_passed": True,
        "verified_source_score_passed": True,
        "knowledge_freshness_passed": True,
        "ai_review_passed": True,
        "human_approval_passed": False,
        "broken_links": [],
        "duplicate_title_meta": False,
        "affiliate_disclosure_present": True,
        "minimum_business_score_passed": True,
        "minimum_readability_score_passed": True,
        "business_score": 61.35,
        "readability_score": 58.37,
        "publish_ready": False,
        "url": "https://example.com/best-ai-productivity-software/",
        "title": "best ai productivity software 2026: Pricing, Pros, Cons",
        "description": "Independent best ai productivity software guide with pricing checks, pros, cons, alternatives, FAQs, and buyer-focused workflow advice.",
    }
    metadata = {
        "slug": slug,
        "title": publish["title"],
        "description": publish["description"],
        "url": publish["url"],
        "review": review,
        "human_approval": human,
        "publish_gate": publish,
        "research_quality_gate": {"passed": True, "score": 62.36, "threshold": 60.0, "status": "passed"},
    }

    _write_json(data_dir / "content_review_queue.json", [review])
    _write_json(data_dir / "human_approval_queue.json", [human])
    _write_json(data_dir / "publish_queue.json", [publish])
    _write_json(draft_dir / "metadata.json", metadata)
    site_output.mkdir(parents=True, exist_ok=True)
    published_dir.mkdir(parents=True, exist_ok=True)
    return EditorialOperationsConsole(data_dir=data_dir, site_output_dir=site_output, published_dir=published_dir)


class EditorialOperationsConsoleTests(unittest.TestCase):
    def test_list_pending_approvals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            console = _seed_console_state(Path(temp_dir))
            pending = console.list_pending_approvals()

            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["slug"], "best-ai-productivity-software")

    def test_approve_slug_updates_human_and_publish_queue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = _seed_console_state(root)

            result = console.approve_slug("best-ai-productivity-software", approver="editor")

            self.assertEqual(result["human_approval"]["status"], "human_approved")
            self.assertEqual(result["review"]["status"], "human_approved")
            self.assertEqual(result["publish_gate"]["status"], "approved_for_publish")
            publish_queue = json.loads((root / "data" / "publish_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(publish_queue[0]["status"], "approved_for_publish")

    def test_reject_slug_updates_status_and_reason(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = _seed_console_state(root)

            result = console.reject_slug("best-ai-productivity-software", approver="editor", reason="Needs pricing fix")

            self.assertEqual(result["human_approval"]["status"], "rejected")
            self.assertEqual(result["review"]["status"], "rejected")
            self.assertEqual(result["publish_gate"]["status"], "blocked")
            self.assertIn("Needs pricing fix", " ".join(result["publish_gate"]["failures"]))

    def test_build_console_writes_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = _seed_console_state(root)

            payload = console.build_console()

            self.assertEqual(payload["summary"]["drafts"], 1)
            self.assertTrue((root / "data" / "editorial_operations_console.json").exists())
            self.assertTrue((root / "data" / "editorial_operations_console.csv").exists())
            self.assertTrue((root / "data" / "editorial_operations_console.html").exists())

    def test_publish_queue_transition_to_published_local(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = _seed_console_state(root)
            console.approve_slug("best-ai-productivity-software", approver="editor")

            result = console.publish_slug("best-ai-productivity-software")

            self.assertEqual(result["publish_gate"]["status"], "published_local")
            self.assertTrue((root / "data" / "published_static_pages" / "best-ai-productivity-software" / "index.html").exists())
            self.assertTrue((root / "site_output" / "best-ai-productivity-software" / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
