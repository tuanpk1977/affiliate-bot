from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any, Callable

from .utils import (
    PublishedArticle,
    extract_affiliate_disclosure,
    extract_article_summary,
    extract_canonical,
    extract_headings,
    extract_meta,
    extract_paragraphs,
    extract_publish_date,
    extract_tags,
    extract_title,
)


class SocialDraftSourcePackageService:
    """Read live articles and project social-writing source packages."""

    def __init__(
        self,
        *,
        root: Path,
        data_dir: Path,
        platform_playbooks: dict[str, Any],
        best_title: Callable[[str, str, str], str],
        non_social_keypoint_headings: set[str],
        research_pipeline_cls: Any,
        now_iso: Callable[[], str],
        x_max_characters: int,
    ) -> None:
        self.root = root
        self.data_dir = data_dir
        self.platform_playbooks = platform_playbooks
        self.best_title = best_title
        self.non_social_keypoint_headings = non_social_keypoint_headings
        self.research_pipeline_cls = research_pipeline_cls
        self.now_iso = now_iso
        self.x_max_characters = x_max_characters

    def article_from_live_row(self, row: dict[str, Any]) -> PublishedArticle:
        slug = str(row["slug"])
        html_path = self.root / "docs" / slug / "index.html"
        html_text = html_path.read_text(encoding="utf-8", errors="ignore") if html_path.exists() else ""
        title = self.best_title(slug, extract_meta(html_text, "og:title") or extract_title(html_text), str(row.get("title") or ""))
        description = html.unescape(extract_meta(html_text, "description") or extract_meta(html_text, "og:description"))
        image = extract_meta(html_text, "og:image") or extract_meta(html_text, "twitter:image")
        if image.startswith("/"):
            image = "https://smileaireviewhub.com" + image
        headings = [
            heading for heading in extract_headings(html_text)
            if heading.strip().lower() not in self.non_social_keypoint_headings
        ]
        paragraphs = extract_paragraphs(html_text, limit=8)
        return PublishedArticle(
            article_id=slug,
            title=title,
            url=str(row["url"]),
            description=description,
            image=image,
            tags=extract_tags(title, description),
            publish_date=extract_publish_date(html_text),
            canonical_url=extract_canonical(html_text) or str(row["url"]),
            og_title=extract_meta(html_text, "og:title"),
            og_description=extract_meta(html_text, "og:description"),
            og_image=image,
            summary=extract_article_summary(html_text, description),
            headings=headings,
            key_points=headings[:5] or paragraphs[:5],
            affiliate_disclosure=extract_affiliate_disclosure(html_text),
        )

    def source_package(
        self,
        article: PublishedArticle,
        *,
        batch_date: str,
        platforms: list[str],
        social_series: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "status": "BLOCKED_RESEARCH",
            "source_excerpts": [],
            "fact_ledger": [],
            "warnings": ["Live article HTML was not available for local evidence extraction."],
        }
        html_path = self.root / "docs" / article.article_id / "index.html"
        if not html_path.exists():
            html_path = self.root / "site_output" / article.article_id / "index.html"
        if html_path.exists():
            raw_html = html_path.read_text(encoding="utf-8", errors="replace")
            pipeline = self.research_pipeline_cls(
                root=self.root,
                data_dir=self.data_dir,
                config={"minimum_publishable_claims": 1, "maximum_publishable_claims": 100},
            )
            package_stub = {
                "slug": article.article_id,
                "keyword": article.title,
                "entities": {"products": [article.title]},
                "outline": {},
            }
            task_stub = {"slug": article.article_id, "title": article.title}
            paragraphs, _ = pipeline.extract_paragraphs(
                raw_html,
                content_type="text/html",
                task=task_stub,
                package=package_stub,
            )
            source = {
                "source_id": "live-article-001",
                "title": article.title,
                "canonical_url": article.canonical_url or article.url,
                "url": article.canonical_url or article.url,
                "source_type": "published_live_article",
                "retrieved_at": self.now_iso(),
                "http_status": 200,
                "content_hash": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
                "paragraphs": [
                    {
                        "paragraph_id": f"live-article-001-p{index:03d}",
                        "paragraph_order": index,
                        **row,
                    }
                    for index, row in enumerate(paragraphs, start=1)
                ],
                "extracted_relevant_paragraphs": [row["text"] for row in paragraphs],
                "freshness": article.publish_date or "date_not_available",
                "verification_status": "published_live",
                "confidence": "high",
            }
            claims = pipeline.extract_claims(
                [source],
                package=package_stub,
                task=task_stub,
                maximum=100,
            )
            evidence = {
                "status": "EVIDENCE_VALIDATED" if claims else "BLOCKED_RESEARCH",
                "source_excerpts": [source],
                "fact_ledger": claims,
                "warnings": [] if claims else ["No directly supported social-writing claims were extracted."],
            }
        return {
            "schema_version": 1,
            "status": "writing_package_ready",
            "batch_date": batch_date,
            "content_origin": "WEBSITE_ROOT_BASED",
            "social_mode": "SOURCE_BASED_SOCIAL",
            "social_series": social_series or {},
            "provenance": provenance or {},
            "article": {
                "slug": article.article_id,
                "title": article.title,
                "url": article.url,
                "canonical_url": article.canonical_url or article.url,
                "meta_description": article.description,
                "og_title": article.og_title,
                "og_description": article.og_description,
                "image": article.image,
                "publish_date": article.publish_date,
                "tags": article.tags,
                "summary": article.summary,
                "headings": article.headings or [],
                "key_points": article.key_points or [],
                "affiliate_disclosure": article.affiliate_disclosure,
            },
            "platforms": platforms,
            "required_outputs": {
                platform: ["A.md", "B.md", "C.md", "metadata.json"]
                for platform in platforms
            },
            "requirements": {
                "manual_only": True,
                "no_social_api": True,
                "no_oauth": True,
                "no_browser_automation": True,
                "include_website_url": True,
                "x_link_optional": True,
                "x_max_characters": self.x_max_characters,
                "x_thread_enabled": False,
                "semantic_compression_required": True,
                "include_image": True,
                "include_affiliate_disclosure_when_relevant": True,
                "include_reusable_excerpts": [150, 250, 500],
                "weekly_root_topic_lock": True,
                "advanced_daily_angle_required": True,
                "next_post_teaser_required": False,
                "content_model": "COMPLEMENTARY_COMPONENTS_V1",
                "local_platform_composer_authoritative": True,
                "future_angle_reservation": True,
            },
            "platform_playbooks": {
                platform: dict(self.platform_playbooks.get(platform) or {})
                for platform in platforms
            },
            "component_roles": {
                "A.md": "ACTIONABLE",
                "B.md": "INSIGHT",
                "C.md": "PROBLEM_SOLUTION",
            },
            "evidence": evidence,
        }

    def writing_prompt(self, package: dict[str, Any]) -> str:
        article = package["article"]
        social_series = package.get("social_series") if isinstance(package.get("social_series"), dict) else {}
        platform_lines = "\n".join(f"- {platform}: create A.md, B.md, C.md and metadata.json" for platform in package["platforms"])
        series_lines = ""
        if social_series:
            roots = ", ".join(str(slug) for slug in social_series.get("root_slugs") or [])
            series_lines = f"""
Weekly social series:
- Week start: {social_series.get("social_week_start") or ""}
- Locked root slugs: {roots}
- Current batch date: {package.get("batch_date") or ""}
- Rule: do not introduce replacement article topics during Tue-Sun. Keep the same locked roots and write a visibly different advanced angle each day.
- A/B/C remain inside today's social angle and must not consume or fully develop future Website angles.
"""
        return f"""# Codex Social Writing Package

Write manual social post drafts from this already-live website article.

Rules:
- Do not call OpenAI API or any paid API.
- Do not publish, approve, deploy, index, or push.
- Use only the article facts in `source_package.json`.
- Reuse supplied fact-ledger claim IDs. If a draft introduces a new factual claim, declare it in metadata.new_claims with an allowed evidence binding; an unsupported new claim blocks import.
- Preserve the website URL and canonical URL.
- Include the article image URL when the platform supports an image.
- Include affiliate disclosure when the post is promotional or link-forward.
- Create three complementary content components: A = ACTIONABLE, B = INSIGHT, C = PROBLEM_SOLUTION.
- A/B/C are internal building blocks for one final platform post, not competing publication variants.
- Do not concatenate components. The local Platform Composer synthesizes them into FINAL.md after import.
- Apply the platform-specific playbook in `source_package.json`; do not expand one generic post with filler.
- For X, design every draft from the start for HARD_MAX_CHARACTERS=280. Threads are disabled. If a draft is too long, rewrite it semantically; never slice or truncate it. A link is optional when the insight uses the space better.
- Store component_role, the same today_social_angle, evidence_refs, new_claims, character_count, and visual recommendation metadata.
- Save outputs under each platform folder.
- If this is a Tue-Sun continuation, make the post meaningfully different from earlier posts for the same root article.
- Do not spend a future pricing, ROI, security, or measurement angle unless it is today's source angle.

Article:
- Title: {article["title"]}
- URL: {article["url"]}
- Canonical: {article["canonical_url"]}
- Image: {article["image"]}
- Summary: {article["summary"]}

Platforms:
{platform_lines}
{series_lines}
"""
