from __future__ import annotations

import json
import re
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_site  # noqa: E402
from modules import content_growth_pipeline as pipeline  # noqa: E402


VALIDATION_TOPICS = [
    {
        "category": "AI Coding",
        "topic": "best ai coding assistants for teams",
        "slug": "best-ai-coding-assistants-for-teams-production-validation",
        "content_type": "comparison",
        "related_keywords": [
            "ai coding tools for teams",
            "cursor for teams",
            "copilot for developers",
        ],
        "suggested_internal_links": [
            "/comparisons/cursor-vs-windsurf/",
            "/category/ai-coding-tools/",
            "/reviews/",
        ],
    },
    {
        "category": "SEO",
        "topic": "surfer seo free trial",
        "slug": "surfer-seo-free-trial-production-validation",
        "content_type": "pricing guide",
        "related_keywords": [
            "surfer seo pricing",
            "surfer seo trial",
            "surfer seo alternatives",
        ],
        "suggested_internal_links": [
            "/pricing/surfer-seo/",
            "/comparisons/surfer-seo-vs-frase/",
            "/category/seo-tools/",
        ],
    },
    {
        "category": "Website Builder",
        "topic": "best website builder for small business",
        "slug": "best-website-builder-for-small-business-production-validation",
        "content_type": "best list",
        "related_keywords": [
            "small business website builder",
            "best website builder 2026",
            "webflow vs framer",
        ],
        "suggested_internal_links": [
            "/best-website-builder-2026/",
            "/comparisons/framer-vs-webflow/",
            "/category/website-builder-tools/",
        ],
    },
    {
        "category": "CRM",
        "topic": "hubspot vs salesforce pricing",
        "slug": "hubspot-vs-salesforce-pricing-production-validation",
        "content_type": "comparison",
        "related_keywords": [
            "hubspot pricing",
            "salesforce pricing",
            "hubspot vs salesforce",
        ],
        "suggested_internal_links": [
            "/comparisons/hubspot-vs-salesforce/",
            "/category/crm-tools/",
            "/comparisons/notion-vs-clickup/",
        ],
    },
    {
        "category": "AI Video",
        "topic": "best ai video generator for youtube",
        "slug": "best-ai-video-generator-for-youtube-production-validation",
        "content_type": "best list",
        "related_keywords": [
            "ai video generator for youtube",
            "runway vs pika",
            "synthesia alternatives",
        ],
        "suggested_internal_links": [
            "/comparisons/runway-vs-pika/",
            "/comparisons/synthesia-vs-runway/",
            "/category/video-tools/",
        ],
    },
]


@dataclass
class PageValidation:
    topic: str
    slug: str
    url: str
    title: str
    meta_description: str
    canonical: str
    internal_links: list[str] = field(default_factory=list)
    broken_links: list[str] = field(default_factory=list)
    missing_metadata: list[str] = field(default_factory=list)
    h1_count: int = 0
    h2_count: int = 0


def html_targets_for_links(topics: list[dict[str, str]]) -> set[str]:
    defaults = {
        "/",
        "/about/",
        "/affiliate-disclosure/",
        "/contact/",
        "/privacy/",
        "/reviews/",
        "/comparisons/",
        "/categories/",
        "/best-website-builder-2026/",
        "/review/surfer-seo/",
    }
    targets = set(defaults)
    for topic in topics:
        targets.update(str(link).strip() for link in topic.get("suggested_internal_links", []))
    return {normalize_href(link) for link in targets if str(link).strip()}


def normalize_href(href: str) -> str:
    clean = "/" + str(href).strip().strip("/").replace("\\", "/")
    return "/" if clean == "/" else clean + "/"


def copy_seed_pages(target_site_output: Path, hrefs: set[str]) -> None:
    source_root = ROOT / "site_output"
    for href in hrefs:
        source = source_root / href.strip("/") / "index.html" if href != "/" else source_root / "index.html"
        if not source.exists():
            continue
        destination = target_site_output / href.strip("/") / "index.html" if href != "/" else target_site_output / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def extract_single(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1).strip() if match else ""


def extract_links(text: str) -> list[str]:
    return re.findall(r"""href=["']([^"'#]+)["']""", text, flags=re.I)


def validate_generated_page(page: dict[str, str], site_output_dir: Path) -> PageValidation:
    article_path = Path(page["article_file"])
    text = article_path.read_text(encoding="utf-8")
    title = extract_single(r"<title\b[^>]*>(.*?)</title>", text)
    meta_description = extract_single(r"""<meta\b[^>]*name=["']description["'][^>]*content=["']([^"']*)["']""", text)
    canonical = extract_single(r"""<link\b[^>]*rel=["']canonical["'][^>]*href=["']([^"']+)["']""", text)
    validation = PageValidation(
        topic=str(page["topic"]),
        slug=str(page["slug"]),
        url=str(page["url"]),
        title=title,
        meta_description=meta_description,
        canonical=canonical,
    )

    required_markers = {
        "planning metadata": "Content planning snapshot",
        "outline": "Planned outline sections",
        "seo title": "<title>",
        "meta description": '<meta name="description"',
        "canonical url": 'rel="canonical"',
        "related keywords": "Related keywords:",
    }
    for label, marker in required_markers.items():
        if marker not in text:
            validation.missing_metadata.append(label)

    validation.h1_count = len(re.findall(r"<h1\b", text, flags=re.I))
    validation.h2_count = len(re.findall(r"<h2\b", text, flags=re.I))
    if validation.h1_count < 1:
        validation.missing_metadata.append("structured headings:h1")
    if validation.h2_count < 5:
        validation.missing_metadata.append("structured headings:h2")

    internal_links: list[str] = []
    broken_links: list[str] = []
    for href in extract_links(text):
        normalized = href
        if href.startswith(pipeline.BASE_URL):
            normalized = href[len(pipeline.BASE_URL):] or "/"
        if not normalized.startswith("/"):
            continue
        normalized = normalize_href(normalized)
        internal_links.append(normalized)
        target = site_output_dir / normalized.strip("/") / "index.html" if normalized != "/" else site_output_dir / "index.html"
        if not target.exists():
            broken_links.append(normalized)
    validation.internal_links = sorted(set(internal_links))
    validation.broken_links = sorted(set(broken_links))
    return validation


def duplicate_map(values: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for slug, value in values.items():
        grouped.setdefault(value, []).append(slug)
    return {value: slugs for value, slugs in grouped.items() if value and len(slugs) > 1}


def write_report(report_dir: Path, report: dict[str, object]) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = report_dir / f"production-pipeline-validation-{stamp}.json"
    md_path = report_dir / f"production-pipeline-validation-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Production Pipeline Validation",
        "",
        f"- Pages generated: {report['pages_generated']}",
        f"- Generation time seconds: {report['generation_time_seconds']}",
        f"- Build time seconds: {report['build_time_seconds']}",
        f"- Build succeeded: {report['build_succeeded']}",
        f"- Errors: {len(report['errors'])}",
        f"- Missing metadata entries: {sum(len(item['missing_metadata']) for item in report['pages'])}",
        f"- Broken links: {sum(len(item['broken_links']) for item in report['pages'])}",
        f"- Duplicate titles: {len(report['duplicate_titles'])}",
        f"- Duplicate descriptions: {len(report['duplicate_descriptions'])}",
        "",
        "## Pages",
    ]
    for page in report["pages"]:
        lines.append(f"- {page['slug']}: missing={len(page['missing_metadata'])}, broken_links={len(page['broken_links'])}")
    if report["errors"]:
        lines.extend(["", "## Errors"])
        lines.extend([f"- {item}" for item in report["errors"]])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    start = time.perf_counter()
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        temp_data = temp_root / "data"
        temp_site_output = temp_root / "site_output"
        temp_published = temp_data / "published_static_pages"
        temp_video = temp_root / "video_output"
        temp_social = temp_root / "social_drafts"
        temp_reports = temp_data / "content_growth_reports"
        temp_tracking = temp_data / "content_growth_performance_log.csv"
        temp_trending = temp_data / "trending_topics.json"

        copy_seed_pages(temp_site_output, html_targets_for_links(VALIDATION_TOPICS))

        generated_pages: list[dict[str, object]] = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, "ROOT", temp_root))
            stack.enter_context(patch.object(pipeline, "DATA_DIR", temp_data))
            stack.enter_context(patch.object(pipeline, "SITE_OUTPUT", temp_site_output))
            stack.enter_context(patch.object(pipeline, "PUBLISHED_DIR", temp_published))
            stack.enter_context(patch.object(pipeline, "VIDEO_OUTPUT", temp_video))
            stack.enter_context(patch.object(pipeline, "SOCIAL_DRAFTS", temp_social))
            stack.enter_context(patch.object(pipeline, "REPORT_DIR", temp_reports))
            stack.enter_context(patch.object(pipeline, "TRACKING_CSV", temp_tracking))
            stack.enter_context(patch.object(pipeline, "TRENDING_JSON", temp_trending))
            stack.enter_context(patch.object(pipeline, "_CONTENT_PLANNER", None))

            for raw_topic in VALIDATION_TOPICS:
                normalized = pipeline.normalize_topic_record(raw_topic)
                generated_pages.append(pipeline.page_to_dict(pipeline.generate_topic_package(normalized)))

            generation_time = round(time.perf_counter() - start, 3)

            fake_settings = SimpleNamespace(
                data_dir=temp_data,
                site_output_dir=temp_site_output,
                base_site_url=pipeline.BASE_URL,
                site_domain=pipeline.BASE_URL,
            )
            build_start = time.perf_counter()
            with patch.object(build_site, "settings", fake_settings):
                build_result = build_site.incremental_build()
            build_time = round(time.perf_counter() - build_start, 3)

        pages = [validate_generated_page(page, temp_site_output) for page in generated_pages]
        title_map = {page.slug: page.title for page in pages}
        description_map = {page.slug: page.meta_description for page in pages}
        duplicate_titles = duplicate_map(title_map)
        duplicate_descriptions = duplicate_map(description_map)

        errors: list[str] = []
        if build_result.get("sitemap") is None:
            errors.append("incremental build did not produce a sitemap path")
        if any(page.missing_metadata for page in pages):
            errors.append("one or more generated pages are missing required metadata")
        if any(page.broken_links for page in pages):
            errors.append("one or more generated pages contain broken internal links")
        if duplicate_titles:
            errors.append("duplicate titles detected across generated pages")
        if duplicate_descriptions:
            errors.append("duplicate meta descriptions detected across generated pages")

        report = {
            "keywords": [topic["topic"] for topic in VALIDATION_TOPICS],
            "categories": {topic["topic"]: topic["category"] for topic in VALIDATION_TOPICS},
            "pages_generated": len(generated_pages),
            "generation_time_seconds": generation_time,
            "build_time_seconds": build_time,
            "build_succeeded": True,
            "build_result": build_result,
            "errors": errors,
            "duplicate_titles": duplicate_titles,
            "duplicate_descriptions": duplicate_descriptions,
            "pages": [asdict(page) for page in pages],
        }
        report_dir = ROOT / "data" / "content_growth_reports"
        json_path, md_path = write_report(report_dir, report)
        print(json.dumps({"report_json": str(json_path), "report_md": str(md_path), **report}, indent=2, ensure_ascii=False))
        return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
