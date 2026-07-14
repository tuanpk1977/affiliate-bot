from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.codex_writer_workflow import WRITER_METADATA, CodexDailyArticleWriter
from modules.research_intelligence import ResearchPackage

EDITORIAL_CONSOLE_PATH = Path(__file__).resolve().parents[1] / "editorial_console.py"
EDITORIAL_CONSOLE_SPEC = spec_from_file_location("root_editorial_console_for_codex_writer", EDITORIAL_CONSOLE_PATH)
assert EDITORIAL_CONSOLE_SPEC and EDITORIAL_CONSOLE_SPEC.loader
EDITORIAL_CONSOLE_MODULE = module_from_spec(EDITORIAL_CONSOLE_SPEC)
EDITORIAL_CONSOLE_SPEC.loader.exec_module(EDITORIAL_CONSOLE_MODULE)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _package(root: Path, slug: str, *, source_count: int = 2) -> ResearchPackage:
    rows = []
    for index in range(source_count):
        domain = f"source{index + 1}.example.com"
        rows.append(
            {
                "brand": slug.replace("-", " "),
                "slug": slug,
                "source_type": "validated_topic_source",
                "source_name": domain,
                "source_url": f"https://{domain}/{slug}",
                "url": f"https://{domain}/{slug}",
                "status": "verified",
                "source_status": "verified",
                "verification_status": "verified",
                "confidence": 85,
                "trust_score": 85,
                "freshness_score": 85,
            }
        )
    package_dir = root / "data" / "research" / slug
    package = ResearchPackage(
        keyword=slug.replace("-", " "),
        slug=slug,
        generated_at="2026-07-14T00:00:00+00:00",
        package_dir=str(package_dir),
        keyword_intelligence={
            "primary_keyword": slug.replace("-", " "),
            "secondary_keywords": [f"{slug.replace('-', ' ')} pricing"],
            "cluster": {"keywords": [slug.replace("-", " ")]},
        },
        keyword_summary={"keyword": slug.replace("-", " "), "slug": slug, "intent": "commercial research", "article_type": "review"},
        outline={
            "seo_outline": ["Who it is best for", "Feature review", "Pricing checks", "Alternatives", "Implementation notes"],
            "article_structure": ["buyer fit", "feature proof", "pricing proof", "alternatives", "workflow"],
            "recommended_cta": "Compare official pricing",
        },
        faq={
            "beginner": [f"What is {slug.replace('-', ' ')} best for?"],
            "pricing": [f"How should teams verify {slug.replace('-', ' ')} pricing?"],
        },
        entities={"products": [slug.replace("-", " ")], "companies": [slug.split("-")[0]]},
        competitors={"competitors": []},
        sources={"verified_sources": rows, "reference_count": len(rows), "source_confidence": 85},
        writing_plan={"confidence": 80},
        quality={
            "overall_score": 75,
            "coverage": 70,
            "source_quality": 75,
            "total_verified_source_score": 80 if rows else 0,
            "source_confidence": 80 if rows else 0,
            "affiliate_readiness": 50,
        },
    )
    _write_json(package_dir / "package.json", asdict(package))
    return package


class CodexWriterWorkflowTests(unittest.TestCase):
    def test_editorial_console_exposes_prepare_research_and_codex_write_commands(self) -> None:
        parser = EDITORIAL_CONSOLE_MODULE.build_parser()
        prepare_args = parser.parse_args(["prepare-research", "--date", "2026-07-14"])
        codex_args = parser.parse_args(["codex-write", "--date", "2026-07-14", "--count", "10", "--depth", "deep", "--dry-run"])
        publish_args = parser.parse_args(["publish-ready", "--date", "2026-07-14"])
        self.assertEqual(prepare_args.command, "prepare-research")
        self.assertEqual(codex_args.command, "codex-write")
        self.assertTrue(codex_args.dry_run)
        self.assertEqual(publish_args.command, "publish-ready")

    def test_dry_run_selects_source_ready_topics_without_writing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            batch = "2026-07-14"
            _package(root, "source-ready-one", source_count=2)
            _package(root, "thin-source-topic", source_count=1)
            _write_json(
                root / "data" / "editorial_queue" / batch / "topics.json",
                {
                    "date": batch,
                    "topics": [
                        {"slug": "source-ready-one", "keyword": "source ready one", "search_intent": "commercial research"},
                        {"slug": "thin-source-topic", "keyword": "thin source topic", "search_intent": "commercial research"},
                    ],
                },
            )
            before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            writer = CodexDailyArticleWriter(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            result = writer.write_daily_articles(batch_date=batch, count=10, dry_run=True)
            after = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertEqual(result["selected"], 1)
            self.assertEqual(result["articles_written"], 0)
            self.assertEqual(result["openai_writer_calls"], 0)
            self.assertEqual(result["github_pushes"], 0)
            self.assertEqual(result["deploy_runs"], 0)
            self.assertIn("thin-source-topic", {row["slug"] for row in result["held_topics"]})

    def test_codex_writer_creates_dashboard_readable_draft_without_approval_or_publish(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            batch = "2026-07-14"
            _package(root, "source-ready-one", source_count=2)
            _write_json(
                root / "data" / "editorial_queue" / batch / "topics.json",
                {"date": batch, "topics": [{"slug": "source-ready-one", "keyword": "source ready one", "search_intent": "commercial research"}]},
            )
            writer = CodexDailyArticleWriter(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            with patch("urllib.request.urlopen", side_effect=AssertionError("network API call was not expected")):
                result = writer.write_daily_articles(batch_date=batch, count=10, dry_run=False)
            self.assertEqual(result["articles_written"], 1)
            metadata = _read_json(root / "data" / "production_article_drafts" / "source-ready-one" / "metadata.json")
            self.assertEqual(metadata["writer"], WRITER_METADATA)
            self.assertEqual(metadata["human_approval"]["status"], "needs_human_review")
            self.assertNotEqual(metadata["publish_gate"]["status"], "approved_for_publish")
            self.assertTrue((root / "site_output" / "review" / batch / "source-ready-one" / "index.html").exists())
            queue = _read_json(root / "data" / "editorial_queue" / batch / "topics.json")
            topic = queue["topics"][0]
            self.assertEqual(topic["status"], "drafted")
            self.assertEqual(topic["writer"], WRITER_METADATA)

    def test_rewriting_existing_approved_draft_requires_reapproval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            batch = "2026-07-14"
            _package(root, "source-ready-one", source_count=2)
            _write_json(
                root / "data" / "editorial_queue" / batch / "topics.json",
                {"date": batch, "topics": [{"slug": "source-ready-one", "keyword": "source ready one", "search_intent": "commercial research"}]},
            )
            _write_json(
                root / "data" / "human_approval_queue.json",
                [{"slug": "source-ready-one", "status": "human_approved", "approved_by": "editor", "approved_at": "2026-07-14T01:00:00+00:00"}],
            )
            writer = CodexDailyArticleWriter(root=root, data_dir=root / "data", site_output_dir=root / "site_output")
            writer.write_daily_articles(batch_date=batch, count=10, dry_run=False)
            human_queue = _read_json(root / "data" / "human_approval_queue.json")
            self.assertEqual(human_queue[0]["status"], "needs_human_review")
            self.assertEqual(human_queue[0]["approved_by"], "")


if __name__ == "__main__":
    unittest.main()
