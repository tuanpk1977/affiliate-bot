from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from modules.weekly_root_guard import SOCIAL_HOT_UNCONFIRMED
from modules.social.content_quality import infer_story_audience, official_source_name
from .utils import PublishedArticle

HOT_NEWS_MONITORING_PLATFORMS = [
    "facebook_en",
    "facebook_vi",
    "linkedin",
    "x",
    "quora",
    "devto",
    "pinterest",
    "blogger",
]

def _hot_news_source_host(url: str) -> str:
    host = urlsplit(str(url or "")).netloc.lower().removeprefix("www.")
    return host or "source"


def _hot_news_hashtags(title: str, summary: str, platform: str) -> list[str]:
    text = f"{title} {summary}".lower()
    if platform == "quora":
        return []
    candidates: list[str] = []
    if "github" in text:
        candidates.append("#GitHub")
    if "copilot" in text:
        candidates.append("#GitHubCopilot")
    if "jetbrains" in text:
        candidates.append("#JetBrains")
    if "agent" in text:
        candidates.append("#AIAgents")
    if not candidates and "ai" in text:
        candidates.append("#AI")
    limits = {"x": 1, "linkedin": 2, "facebook_en": 2, "facebook_vi": 2, "producthunt": 1}
    return list(dict.fromkeys(candidates))[: limits.get(platform, 3)]


def _hot_news_summary(title: str, summary: str) -> str:
    clean = " ".join(str(summary or "").split()).strip()
    if clean:
        return clean
    return (
        f"{title} is showing up in current source monitoring. The topic is worth watching, "
        "but the available details still need confirmation from primary sources."
    )


def _hot_news_title_line(title: str) -> str:
    clean = " ".join(str(title or "").split()).strip()
    if clean:
        return clean
    return "AI hot trend watchlist item"


def _hot_news_starter_drafts(
    *,
    title: str,
    summary: str,
    source_urls: list[str],
    discovery_timestamp: str,
    platform: str,
) -> dict[str, Any]:
    clean_title = _hot_news_title_line(title)
    clean_summary = _hot_news_summary(title, summary)
    urls = [str(url).strip() for url in source_urls if str(url).strip()]
    primary_url = urls[0] if urls else ""
    hashtags = _hot_news_hashtags(clean_title, clean_summary, platform)
    tags_text = " ".join(hashtags)
    source_block = "\n\n".join(
        f"Source: {official_source_name(url)}\n{url}" for url in urls[:2]
    )
    primary_source_name = official_source_name(primary_url)
    audience = infer_story_audience(clean_title, clean_summary)
    vi_audience = {
        "enterprise administrators and engineering leaders": "quản trị viên doanh nghiệp và lãnh đạo kỹ thuật",
        "developers and engineering teams": "lập trình viên và đội ngũ kỹ thuật",
        "marketers and creators": "đội ngũ marketing và nhà sáng tạo",
        "small-business operators": "người vận hành doanh nghiệp nhỏ",
        "product teams and early adopters": "đội ngũ sản phẩm và nhóm thử nghiệm sớm",
        "AI users evaluating the announcement": "người dùng đang đánh giá thông báo AI này",
    }.get(audience, "đội ngũ đang đánh giá thông báo")
    cta = (
        f"For {audience}, the practical question is which decision this announcement creates "
        "and what remains unverified."
    )
    body_a = ""
    body_b = ""
    body_c = ""

    if platform == "facebook_en":
        body_a = (
            f"{clean_title}\n\n{clean_summary}\n\n"
            f"The useful signal for {audience} is operational: confirm the documented scope before changing a team workflow. "
            "The announcement is evidence of the update, not evidence that it fits every organization. "
            "Any details beyond the cited source remain unconfirmed.\n\n"
            f"{cta}\n\n{tags_text}\n\n{source_block}"
        )
        body_b = (
            f"What changed: {clean_title}\n\n{clean_summary}\n\n"
            "What the source establishes is the announcement itself. Adoption value, rollout coverage, and workflow impact still need to be checked against the official details.\n\n"
            f"For {audience}, that makes this a verification task—not a product endorsement.\n\n{tags_text}\n\n{source_block}"
        )
        body_c = (
            f"A practical reading of {clean_title}\n\n{clean_summary}\n\n"
            "What to verify before rollout: who controls the setting, which accounts receive it, and whether the documented behavior matches your governance process. "
            "Those questions matter more than the announcement headline.\n\n"
            f"{tags_text}\n\n{source_block}"
        )
    elif platform == "facebook_vi":
        vi_fact = f"{primary_source_name} đã công bố thông tin chính thức về {clean_title}."
        body_a = (
            f"{clean_title}\n\n{vi_fact}\n\n"
            f"Điểm đáng chú ý với {vi_audience} là tác động vận hành: hãy đối chiếu phạm vi được tài liệu chính thức xác nhận trước khi thay đổi quy trình. "
            "Thông báo này xác nhận có cập nhật, nhưng chưa tự chứng minh rằng cập nhật phù hợp với mọi tổ chức.\n\n"
            f"{tags_text}\n\nNguồn chính thức:\n{source_block}"
        )
        body_b = (
            f"Có gì thay đổi trong {clean_title}?\n\n{vi_fact}\n\n"
            "Nguồn hiện xác nhận thông báo, không phải hiệu quả triển khai. Phạm vi áp dụng, quyền quản trị và ảnh hưởng tới quy trình vẫn là các điểm cần kiểm tra.\n\n"
            f"Vì vậy, đây là thông tin để đánh giá có kiểm chứng, không phải lời khuyên mua dùng.\n\n{tags_text}\n\nNguồn chính thức:\n{source_block}"
        )
        body_c = (
            f"Góc nhìn thực tế về {clean_title}\n\n{vi_fact}\n\n"
            "Trước khi áp dụng, đội ngũ nên xác minh ai kiểm soát thiết lập, tài khoản nào được hỗ trợ và hành vi được mô tả có khớp quy trình quản trị hiện tại hay không. "
            "Đó mới là phần quyết định giá trị của cập nhật.\n\n"
            f"{tags_text}\n\nNguồn chính thức:\n{source_block}"
        )
    elif platform == "linkedin":
        body_a = (
            f"{clean_title}\n\n{clean_summary}\n\n"
            "Verified fact: the official source documents the announcement.\n\n"
            f"Operational interpretation: for {audience}, the change is a prompt to identify who owns the setting and which workflow it affects.\n\n"
            "Still unverified: pricing, performance, organization-wide fit, and any behavior not stated by the source.\n\n"
            f"The useful outcome is a decision record—not a repetition of the headline.\n\n{tags_text}\n\n{source_block}"
        )
        body_b = (
            f"An early AI signal on the watchlist: {clean_title}\n\n"
            "The right posture here is disciplined curiosity. Track the source material, separate verified details from assumptions, and wait for enough evidence to judge workflow fit.\n\n"
            f"For {audience}, the next step is to map the documented change to one real control or workflow decision.\n\n{tags_text}\n\n{source_block}"
        )
        body_c = (
            f"If {clean_title} matters to your team, avoid the usual mistake: repeating the headline before validating the operating details.\n\n"
            f"{clean_summary}\n\n"
            f"The decision point is whether the official scope resolves a real governance constraint for {audience}.\n\n{tags_text}\n\n{source_block}"
        )
    elif platform == "x":
        # X gets no forced hashtags: preserving the primary-source URL and a useful
        # implication is more valuable than spending the 280-character budget on tags.
        hashtags = []
        tags_text = ""
        source_line = f"Source: {primary_source_name} {primary_url}".strip()
        prefix_a = f"{clean_title}. Official update. Before adopting, verify its documented scope and team-control impact."
        prefix_b = f"{clean_title}. Announcement confirmed. Review organization fit and rollout impact before adoption."
        prefix_c = f"{clean_title}. What to verify: does the documented change alter a real governance decision?"
        body_a = f"{prefix_a[: max(0, 278 - len(source_line))].rstrip()}\n{source_line}"
        body_b = f"{prefix_b[: max(0, 278 - len(source_line))].rstrip()}\n{source_line}"
        body_c = f"{prefix_c[: max(0, 278 - len(source_line))].rstrip()}\n{source_line}"
    elif platform == "quora":
        body_a = (
            f"What does {clean_title} mean for teams?\n\n"
            f"Short answer: {clean_summary}\n\n"
            "The official announcement confirms the change, but it does not by itself prove organization-wide fit. Check documented scope, account eligibility, and administrative ownership before changing a workflow.\n\n"
            f"For {audience}, the useful outcome is a specific governance decision, not a general endorsement.\n\n{source_block}"
        )
        body_b = (
            f"What should buyers verify before taking {clean_title} seriously?\n\n"
            "What to verify: what is actually available, who can configure it, and which limitations the documentation names. Those facts determine whether the announcement changes a real buying or governance decision.\n\n"
            f"What remains unknown should stay unknown until another reliable source resolves it.\n\n{source_block}"
        )
        body_c = (
            f"Is {clean_title} enough reason to change a team workflow?\n\n"
            "Not on the headline alone. The practical test is whether the official scope matches the team's account model, control requirements, and current process.\n\n"
            f"That separates a verified product change from an unsupported recommendation.\n\n{source_block}"
        )
    elif platform == "devto":
        body_a = (
            f"# {clean_title}\n\n"
            "## Why this matters\n\n"
            f"{clean_summary}\n\n"
            "## What is confirmed so far\n\n"
            f"- Announcement source family: {_hot_news_source_host(primary_url)}\n"
            "- Confirmation status: official announcement available; broader fit not established\n\n"
            "## Practical takeaway\n\n"
            "Treat this as an engineering or product watchlist note. Do not repeat unsupported details until the primary sources document them clearly.\n\n"
            f"For builders, the useful next step is to test the documented boundary against an actual development or administration workflow.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_b = (
            f"# Monitoring {clean_title}\n\n"
            f"{clean_summary}\n\n"
            "This is a short monitoring note for builders who want to separate confirmed product evidence from announcement noise.\n\n"
            f"For builders, the key distinction is confirmed behavior versus assumed downstream impact.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_c = (
            f"# Early note on {clean_title}\n\n"
            "The useful move is to hold this in a watchlist until documentation, access rules, and workflow evidence become clearer.\n\n"
            f"The implementation question is whether the documented change removes a real control or workflow constraint.\n\nTags: {tags_text}\n\n{source_block}"
        )
    elif platform == "pinterest":
        pin_title = clean_title[:90]
        body_a = (
            f"Pin title: {pin_title}\n\nPin description: {clean_summary} Review the documented scope and team-control impact before adoption.\n\n"
            f"Destination URL: {primary_url}\nSuggested board: AI workflow governance\nKeywords: GitHub Copilot, JetBrains, enterprise settings\n"
            f"Overlay text: What enterprise teams should verify\n\n{tags_text}\n\nSource: {primary_source_name}"
        )
        body_b = (
            f"Pin title: {pin_title}\n\nPin description: A source-backed checkpoint for teams evaluating the announcement: availability, admin ownership, and workflow impact.\n\n"
            f"Destination URL: {primary_url}\nSuggested board: AI product updates\nKeywords: AI update, admin controls, developer workflow\n"
            f"Overlay text: Confirm scope before rollout\n\n{tags_text}\n\nSource: {primary_source_name}"
        )
        body_c = (
            f"Pin title: {pin_title}\n\nPin description: The announcement is confirmed; broader organization fit is not. Use the official source to separate fact from assumption.\n\n"
            f"Destination URL: {primary_url}\nSuggested board: Enterprise AI controls\nKeywords: enterprise AI, governance, official documentation\n"
            f"Overlay text: Review fact, implication, and open question\n\n{tags_text}\n\nSource: {primary_source_name}"
        )
    elif platform == "blogger":
        body_a = (
            f"# {clean_title}\n\n"
            "## Why this hot-trend item is worth watching\n\n"
            f"{clean_summary}\n\n"
            "## What is known right now\n\n"
            f"- Source family: {_hot_news_source_host(primary_url)}\n"
            "- Current status: announcement confirmed; broader product-fit claims unverified\n\n"
            "## What readers should do next\n\n"
            "Track the primary sources, wait for clearer documentation, and avoid treating the item as a buying recommendation too early.\n\n"
            f"Disclosure: this post links to source material under review.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_b = (
            f"# Monitoring note: {clean_title}\n\n"
            f"{clean_summary}\n\n"
            "This is a companion monitoring draft, not a final product review. It exists to help readers track what is known, what is still unclear, and which source links deserve follow-up.\n\n"
            f"For {audience}, the useful output is a documented decision about scope, ownership, or rollout.\n\nTags: {tags_text}\n\n{source_block}"
        )
        body_c = (
            f"# Early watchlist entry for {clean_title}\n\n"
            f"{clean_summary}\n\nGood AI coverage is not just speed. It is disciplined follow-up. Review this item again only when the sources provide enough evidence to support a deeper recommendation.\n\n"
            f"The article should be revisited only when new evidence changes that decision.\n\nTags: {tags_text}\n\n{source_block}"
        )
    elif platform == "producthunt":
        body_a = (
            f"Discussion prompt: {clean_title}\n\n{clean_summary}\n\n"
            "Worth discussing: which documented workflow or administration problem does this solve, and for whom? This is context for the community, not an endorsement or launch claim.\n\n"
            f"{tags_text}\n\n{source_block}"
        )
        body_b = (
            f"Community context: {clean_title}\n\n"
            "The announcement is confirmed by the source below. Product fit, adoption value, and broader availability should remain separate questions until evidence supports them. "
            "What to verify: the documented user, scope, and workflow boundary.\n\n"
            f"{cta}\n\n{tags_text}\n\n{source_block}"
        )
        body_c = (
            f"A source-first look at {clean_title}\n\n{clean_summary}\n\n"
            "What to consider: the specific team decision this changes—not whether the headline sounds exciting.\n\n"
            f"{tags_text}\n\n{source_block}"
        )
    else:
        body_a = f"{clean_title}\n\n{clean_summary}\n\nSources:\n{source_block}\n\n{cta}\n\n{tags_text}"
        body_b = body_a
        body_c = body_a

    platform_title = {
        "linkedin": clean_title,
        "facebook_en": clean_title,
        "facebook_vi": clean_title,
        "x": clean_title[:72],
        "quora": clean_title,
        "devto": clean_title,
        "pinterest": clean_title[:90],
        "blogger": clean_title,
        "producthunt": clean_title,
    }.get(platform, clean_title)
    return {
        "title": platform_title,
        "cta": cta,
        "hashtags": hashtags,
        "drafts": {"A.md": body_a.strip() + "\n", "B.md": body_b.strip() + "\n", "C.md": body_c.strip() + "\n"},
    }

class SocialDraftHotNewsService:
    """Own hot-news monitoring packages, copy, and root-relative artifacts."""

    def __init__(
        self, *, draft_root: Path, generate_social_assets: Callable[..., dict[str, Any]],
        write_json: Callable[..., None], read_json: Callable[..., Any],
        now_iso: Callable[[], str], looks_like_iso_date: Callable[[str], bool],
        normalize_platforms: Callable[..., list[str]], monitoring_slug: Callable[[str], str],
        safe_asset_name: Callable[[str], str],
    ) -> None:
        self.draft_root = draft_root
        self.generate_social_assets = generate_social_assets
        self.write_json = write_json
        self.read_json = read_json
        self.now_iso = now_iso
        self.looks_like_iso_date = looks_like_iso_date
        self.normalize_platforms = normalize_platforms
        self.monitoring_slug = monitoring_slug
        self.safe_asset_name = safe_asset_name

    def hot_news_monitoring_package(
        self,
        *,
        title: str,
        batch_date: str,
        source_urls: list[str],
        discovery_timestamp: str,
        platforms: list[str],
        summary: str = "",
        queue_type: str = "SOCIAL_HOT_DRAFT",
        editorial_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        urls = [str(url).strip() for url in source_urls if str(url).strip()]
        if not urls:
            raise ValueError("SOCIAL_HOT_UNCONFIRMED requires at least one preserved source URL.")
        return {
            "schema_version": 1,
            "status": "writing_package_ready",
            "workflow": "HOT_NEWS_MONITORING",
            "content_origin": "HOT_NEWS",
            "social_mode": "STANDALONE_SOCIAL_RESEARCH",
            "queue_type": queue_type,
            "content_lane": SOCIAL_HOT_UNCONFIRMED,
            "batch_date": batch_date,
            "hot_news": {
                "title": title,
                "summary": summary,
                "source_urls": urls,
                "discovery_timestamp": discovery_timestamp,
                "confirmation_status": "unconfirmed",
            },
            "platforms": platforms,
            "editorial_selection": dict(editorial_metadata or {}),
            "required_outputs": {
                platform: ["A.md", "B.md", "C.md", "metadata.json"]
                for platform in platforms
            },
            "requirements": {
                "manual_only": True,
                "no_social_api": True,
                "no_oauth": True,
                "no_browser_automation": True,
                "include_website_url": False,
                "require_live_website_article": False,
                "must_not_create_website_draft": True,
                "must_not_modify_weekly_roots": True,
                "cautious_unconfirmed_language": True,
                "preserve_source_urls": True,
                "preserve_discovery_timestamp": True,
                "must_include_basic_intro": True,
                "must_include_what_is_known": True,
                "must_include_source_context": True,
                "must_keep_single_source_block": True,
                "must_not_duplicate_source_link_blocks": True,
                "cta_policy": "optional_story_specific_only",
                "generic_cta_forbidden": True,
            },
        }

    def hot_news_monitoring_prompt(self, package: dict[str, Any]) -> str:
        hot_news = package["hot_news"]
        source_lines = "\n".join(f"- {url}" for url in hot_news.get("source_urls") or [])
        platform_lines = "\n".join(f"- {platform}: create A.md, B.md, C.md and metadata.json" for platform in package["platforms"])
        return f"""# Social Hot-News Monitoring Package

Write cautious social-only monitoring drafts.

Rules:
- Content lane: {SOCIAL_HOT_UNCONFIRMED}
- Do not call OpenAI API or any paid API.
- Do not create a website article, website draft, weekly root, canonical URL, or fabricated website link.
- Do not publish, approve, deploy, index, or push.
- Use cautious language: "reported", "appears", "not officially confirmed", "monitoring for confirmation".
- Do not invent facts, pricing, dates, features, quotes, availability, or official confirmation.
- Preserve source URLs and discovery timestamp.
- A CTA is optional. Do not add a generic follow/read/check/visit CTA.
- If a CTA adds value, make it specific to the decision created by this story; otherwise end with an implication, concise observation, decision question, or source.
- Each platform draft must have a real hook or opening line. Do not output bare link-only or citation-only copy.
- Add a short plain-language introduction so the post makes sense even for someone who did not see the source first.
- Separate what is known from what still needs confirmation.
- Keep exactly one source-link block unless the platform format explicitly needs two source fields.
- Do not fabricate a Smile AI Review Hub article URL for this lane.
- Required platform behavior:
  - Facebook EN / VI: conversational hook + 2 short paragraphs + source context; CTA optional.
  - LinkedIn: professional framing + enough context + operational implication; no engagement bait.
  - X: one sharp hook + one source URL + minimal tags.
  - Quora: suggested question + concise answer + source context.
  - Dev.to: short structured note with headings.
  - Pinterest: pin title + pin description + destination URL = primary source URL.
  - Blogger: short companion note with sections, not just a copied link.

Hot-news item:
- Title: {hot_news.get("title") or ""}
- Discovery timestamp: {hot_news.get("discovery_timestamp") or ""}
- Summary: {hot_news.get("summary") or ""}

Source URLs:
{source_lines}

Platforms:
{platform_lines}
"""

    def prepare_hot_news_monitoring(
        self,
        *,
        batch_date: str,
        title: str,
        source_urls: list[str],
        discovery_timestamp: str | None = None,
        platforms: list[str] | None = None,
        summary: str = "",
        queue_type: str = "SOCIAL_HOT_DRAFT",
        editorial_metadata: dict[str, Any] | None = None,
        create_placeholder_drafts: bool = True,
    ) -> dict[str, Any]:
        resolved = batch_date if self.looks_like_iso_date(batch_date) else date.today().isoformat()
        platform_list = self.normalize_platforms(platforms or HOT_NEWS_MONITORING_PLATFORMS)
        slug = "hot-news-" + self.monitoring_slug(title)
        discovery = discovery_timestamp or self.now_iso()
        package = self.hot_news_monitoring_package(
            title=title,
            batch_date=resolved,
            source_urls=source_urls,
            discovery_timestamp=discovery,
            platforms=platform_list,
            summary=summary,
            queue_type=queue_type,
            editorial_metadata=editorial_metadata,
        )
        article_dir = self.draft_root / resolved / slug
        self.write_json(article_dir / "source_package.json", package)
        (article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md").write_text(
            self.hot_news_monitoring_prompt(package),
            encoding="utf-8",
        )
        seed_article = PublishedArticle(
            article_id=slug,
            title=title,
            url=package["hot_news"]["source_urls"][0],
            description=summary,
            image="",
            tags=[],
            publish_date="",
            canonical_url=package["hot_news"]["source_urls"][0],
        )
        asset_manifest = self.generate_social_assets(seed_article, batch_date=resolved)
        asset_outputs = asset_manifest.get("outputs", {}) if isinstance(asset_manifest, dict) else {}
        source_text = "\n".join(package["hot_news"]["source_urls"])
        for platform in platform_list:
            platform_dir = article_dir / platform
            platform_dir.mkdir(parents=True, exist_ok=True)
            starter = _hot_news_starter_drafts(
                title=title,
                summary=summary,
                source_urls=package["hot_news"]["source_urls"],
                discovery_timestamp=discovery,
                platform=platform,
            )
            asset_info = asset_outputs.get(self.safe_asset_name(platform), {}) if isinstance(asset_outputs, dict) else {}
            platform_image_path = str(asset_info.get("local_path") or asset_outputs.get("og", {}).get("local_path") or "")
            if create_placeholder_drafts:
                for filename, content in starter["drafts"].items():
                    (platform_dir / filename).write_text(content, encoding="utf-8")
            self.write_json(
                platform_dir / "metadata.json",
                {
                    "status": "needs_social_review" if create_placeholder_drafts else "needs_social_draft",
                    "selected_variant": "A.md",
                    "queue_type": queue_type,
                    "content_lane": SOCIAL_HOT_UNCONFIRMED,
                    "workflow": "HOT_NEWS_MONITORING",
                    "article_slug": slug,
                    "platform": platform,
                    "title": starter["title"],
                    "source_title": title,
                    "source_url": package["hot_news"]["source_urls"][0],
                    "source_urls": package["hot_news"]["source_urls"],
                    "website_url": "",
                    "canonical_url": "",
                    "image_url": "",
                    "local_image_path": platform_image_path,
                    "platform_image_path": platform_image_path,
                    "CTA": starter["cta"],
                    "cta": starter["cta"],
                    "hashtags": starter["hashtags"],
                    "discovery_timestamp": discovery,
                    "confirmation_status": "unconfirmed",
                    "editorial_selection": dict(editorial_metadata or {}),
                    "validation_warnings": [
                        "Unconfirmed hot-news monitoring draft. Do not add a website URL unless a website article is later published."
                    ],
                    "created_at": self.now_iso(),
                },
            )
        manifest_path = self.draft_root / resolved / "manifest.json"
        manifest = self.read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            manifest = {}
        items = manifest.get("items") if isinstance(manifest.get("items"), list) else []
        items = [item for item in items if not (isinstance(item, dict) and item.get("slug") == slug)]
        items.append(
            {
                "slug": slug,
                "title": title,
                "url": "",
                "content_lane": SOCIAL_HOT_UNCONFIRMED,
                "queue_type": queue_type,
                "workflow": "HOT_NEWS_MONITORING",
                "status": "writing_package_ready" if create_placeholder_drafts else "needs_social_draft",
                "platforms": platform_list,
                "source_package": str(article_dir / "source_package.json"),
                "prompt": str(article_dir / "CODEX_SOCIAL_WRITING_PROMPT.md"),
                "editorial_selection": dict(editorial_metadata or {}),
            }
        )
        manifest.update(
            {
                "schema_version": 1,
                "batch_date": resolved,
                "status": "social_writing_package_ready",
                "workflow_contracts": sorted(
                    set(list(manifest.get("workflow_contracts") or []) + ["HOT_NEWS_MONITORING"])
                ),
                "items": items,
            }
        )
        self.write_json(manifest_path, manifest)
        return manifest
