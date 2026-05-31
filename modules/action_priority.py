from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import pandas as pd

from config import settings


ACTION_COLUMNS = [
    "priority_rank",
    "action_type",
    "topic",
    "keyword",
    "page_url",
    "platform",
    "reason",
    "expected_impact",
    "difficulty",
    "next_action",
]

ACTION_STATUS_COLUMNS = ["priority_rank", "action_type", "keyword", "status", "updated_at", "note"]
INTERNAL_LINK_PLAN_COLUMNS = ["source_page", "target_page", "anchor_text", "reason", "priority"]


def run_action_priority_report() -> pd.DataFrame:
    report = build_action_priority_report()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(settings.data_dir / "action_priority_report.csv", index=False, encoding="utf-8-sig")
    return report


def action_from_row(row: pd.Series | dict) -> dict[str, str]:
    return {column: str(row.get(column, "")).strip() for column in ACTION_COLUMNS}


def generate_article_draft(action: pd.Series | dict) -> Path:
    item = action_from_row(action)
    output_dir = settings.base_dir / "draft_output" / "action_drafts"
    output_dir.mkdir(parents=True, exist_ok=True)
    rank = safe_rank(item.get("priority_rank"))
    keyword = item.get("keyword") or "affiliate content idea"
    slug = suggested_slug(keyword)
    path = output_dir / f"priority-{rank:03d}-{slug}.md"
    path.write_text(article_draft_markdown(item, slug), encoding="utf-8")
    mark_action_status(item, "in_progress", f"article draft generated: {path.as_posix()}")
    return path


def generate_social_pack(action: pd.Series | dict) -> dict[str, Path]:
    item = action_from_row(action)
    output_dir = settings.base_dir / "draft_output" / "social_from_actions"
    output_dir.mkdir(parents=True, exist_ok=True)
    rank = safe_rank(item.get("priority_rank"))
    slug = suggested_slug(item.get("keyword") or item.get("topic") or "social-pack")
    url = public_url_for_action(item, slug)
    pack = {
        "twitter": twitter_thread(item, url),
        "linkedin": linkedin_post(item, url),
        "facebook": facebook_post(item, url),
        "telegram": telegram_post(item, url),
    }
    paths: dict[str, Path] = {}
    for platform, content in pack.items():
        path = output_dir / f"priority-{rank:03d}-{slug}-{platform}.txt"
        path.write_text(content, encoding="utf-8")
        paths[platform] = path
    mark_action_status(item, "in_progress", f"social pack generated for {slug}")
    return paths


def generate_internal_link_plan(action: pd.Series | dict) -> Path:
    item = action_from_row(action)
    path = settings.data_dir / "internal_link_action_plan.csv"
    existing = read_existing_plan(path)
    rows = existing + internal_link_plan_rows(item)
    df = pd.DataFrame(rows, columns=INTERNAL_LINK_PLAN_COLUMNS)
    df = df.drop_duplicates(subset=["source_page", "target_page", "anchor_text"], keep="last")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    mark_action_status(item, "in_progress", f"internal link plan updated: {path.as_posix()}")
    return path


def mark_action_status(action: pd.Series | dict, status: str, note: str = "") -> Path:
    item = action_from_row(action)
    status = status if status in {"pending", "in_progress", "done", "skipped"} else "pending"
    path = settings.data_dir / "action_status.csv"
    current = read_action_status()
    key = (str(item.get("priority_rank", "")), item.get("action_type", ""), item.get("keyword", ""))
    current = [
        row
        for row in current
        if (str(row.get("priority_rank", "")), row.get("action_type", ""), row.get("keyword", "")) != key
    ]
    current.append(
        {
            "priority_rank": item.get("priority_rank", ""),
            "action_type": item.get("action_type", ""),
            "keyword": item.get("keyword", ""),
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "note": note,
        }
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(current, columns=ACTION_STATUS_COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def read_action_status() -> list[dict[str, str]]:
    path = settings.data_dir / "action_status.csv"
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path).fillna("")
    except Exception:
        return []
    for column in ACTION_STATUS_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[ACTION_STATUS_COLUMNS].astype(str).to_dict("records")


def article_draft_markdown(item: dict[str, str], slug: str) -> str:
    keyword = item.get("keyword") or "affiliate content idea"
    topic = item.get("topic") or "AI tools"
    action_type = item.get("action_type") or "write_new_article"
    title = seo_title(keyword, action_type)
    meta = meta_description(keyword, topic, item.get("reason", ""))
    internal_links = suggested_internal_links(item)
    table = comparison_table(keyword) if action_type in {"create_comparison_page", "improve_existing_article"} else generic_decision_table(keyword)
    return f"""# {title}

**SEO title:** {title}

**Meta description:** {meta}

**Suggested slug:** `{slug}`

**Source action:** priority {item.get('priority_rank')} - `{action_type}`

**Reason:** {item.get('reason')}

## Intro

This draft should answer a real buyer-intent question around **{keyword}**. The angle is not to claim one tool is perfect, but to help a reader decide what to test next, what to avoid, and what tradeoffs matter before spending time or money.

For this page, keep the tone practical. Explain where the workflow breaks, what a solo builder or team should check, and why the decision matters for the broader {topic} cluster.

## Suggested H2/H3 Outline

### What this page helps you decide
- Who is actively searching for {keyword}
- What decision they are likely trying to make
- What information they need before clicking a CTA

### Quick recommendation
- Best option for solo builders
- Best option for teams
- Best option if budget or migration risk matters

### Practical comparison table

{table}

### Practical use cases
- Use case 1: starting from zero
- Use case 2: fixing or improving an existing workflow
- Use case 3: comparing cost, risk, and learning curve

### Opinion section
Add a clear editorial opinion. Do not make every option look equally good. Explain what you would test first, what you would avoid, and what would change your recommendation.

### Risks before choosing
- Pricing may change, so verify the vendor site.
- Terms, affiliate policies, and usage limits should be checked directly.
- Avoid assuming demo performance equals production performance.

### CTA section
Use a soft CTA:

> If this matches your workflow, review the official product page and compare it with the alternatives before committing.

Suggested CTA target should route through `/go/` when it points outbound.

### Affiliate disclosure note
Some links may be affiliate links. We may earn a commission at no extra cost to the reader. Recommendations should remain research-based and not depend on commission.

## Internal links to add
{format_internal_links(internal_links)}

## FAQ ideas

### Is {keyword} worth testing first?
Answer with the practical conditions where it makes sense.

### What should I check before buying?
Mention pricing, limits, integrations, support, cancellation, and terms.

### What is the safest first step?
Suggest a small test, review page, or comparison workflow instead of a large commitment.
"""


def twitter_thread(item: dict[str, str], url: str) -> str:
    keyword = item.get("keyword") or "AI tool workflow"
    return "\n\n".join(
        [
            f"1/ The interesting part of {keyword} is not the demo. It is what happens when the first answer is not enough.",
            "2/ I would judge this by workflow fit: context, debugging, pricing risk, and whether it still helps after the second failed fix.",
            "3/ The practical move: test one narrow use case before committing to the tool or workflow.",
            f"4/ Full research note: {url} #AITools #AffiliateMarketing",
        ]
    )


def linkedin_post(item: dict[str, str], url: str) -> str:
    keyword = item.get("keyword") or "AI tool workflow"
    reason = item.get("reason") or "this topic has buyer intent and needs better decision support"
    return f"""I would not treat "{keyword}" as just another SEO topic.

The reason it deserves a real page is simple: people searching this are usually trying to make a decision, not just browse.

What I would cover:
- the actual workflow problem
- where the tool or category helps
- where it breaks down
- pricing and switching risk
- what to test first

The current action reason is: {reason}.

That means the content should not be generic. It needs a clear recommendation, a practical comparison, and a soft CTA that helps the reader continue researching.

Draft angle:
Help the reader avoid the wrong first test.

Read the related page here:
{url}

#AITools #SEO #AffiliateMarketing #SaaS"""


def facebook_post(item: dict[str, str], url: str) -> str:
    keyword = item.get("keyword") or "AI tools"
    return f"""Mình đang gom các topic affiliate/SEO theo hướng thực tế hơn, không viết kiểu review chung chung.

Với chủ đề "{keyword}", điều quan trọng là người đọc cần biết:

- nên test trong trường hợp nào
- không nên dùng khi nào
- có rủi ro giá/terms/workflow gì
- nên so sánh với lựa chọn nào trước

Bài kiểu này thường kéo traffic tốt hơn vì nó trả lời đúng câu hỏi người đang chuẩn bị ra quyết định.

Link để xem/chỉnh tiếp:
{url}

#AITools #SEO #Affiliate"""


def telegram_post(item: dict[str, str], url: str) -> str:
    keyword = item.get("keyword") or "AI tool workflow"
    return f"""Action mới cần xử lý: {keyword}

Góc nên viết:
- không review chung chung
- có use-case thật
- có so sánh / pricing risk / CTA rõ
- ưu tiên quyết định: nên test hay bỏ qua

Link:
{url}"""


def internal_link_plan_rows(item: dict[str, str]) -> list[dict[str, str]]:
    target = item.get("page_url") or public_url_for_action(item, suggested_slug(item.get("keyword") or "action"))
    keyword = item.get("keyword") or "AI tools"
    topic = item.get("topic") or "general"
    candidates = [
        "/best-ai-coding-tools-2026/",
        "/categories/",
        "/comparisons/",
        "/reviews/",
        "/pricing/",
    ]
    rows = []
    for source in candidates:
        rows.append(
            {
                "source_page": source,
                "target_page": target,
                "anchor_text": keyword,
                "reason": f"Supports {topic} topical cluster and action: {item.get('action_type')}",
                "priority": "high" if item.get("expected_impact") == "high" else "medium",
            }
        )
    return rows


def read_existing_plan(path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path).fillna("")
    except Exception:
        return []
    for column in INTERNAL_LINK_PLAN_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[INTERNAL_LINK_PLAN_COLUMNS].astype(str).to_dict("records")


def suggested_internal_links(item: dict[str, str]) -> list[tuple[str, str]]:
    keyword = (item.get("keyword") or "").lower()
    links = [("Reviews index", "/reviews/"), ("Comparisons index", "/comparisons/"), ("Pricing index", "/pricing/")]
    if any(term in keyword for term in ["cursor", "copilot", "codex", "windsurf", "coding"]):
        links.extend(
            [
                ("Best AI Coding Tools 2026", "/best-ai-coding-tools-2026/"),
                ("Cursor review", "/review/cursor/"),
                ("GitHub Copilot review", "/review/github-copilot/"),
            ]
        )
    if "seo" in keyword or "semrush" in keyword:
        links.append(("Best AI SEO Tools 2026", "/best-ai-seo-tools-2026/"))
    return links


def format_internal_links(links: list[tuple[str, str]]) -> str:
    return "\n".join(f"- [{label}]({url})" for label, url in links)


def comparison_table(keyword: str) -> str:
    return f"""| Decision point | Option A | Option B | What to check |
|---|---|---|---|
| Workflow fit | Good for one use case | Better for another use case | Test against your real task |
| Pricing risk | Check current plan limits | Check current plan limits | Verify official pricing |
| Team adoption | Easier if workflow is simple | Better if process is mature | Test with one project first |
| Main risk | Overpaying or wrong fit | Switching cost | Avoid committing too early |"""


def generic_decision_table(keyword: str) -> str:
    return f"""| Section | What to include | Why it matters |
|---|---|---|
| Use case | Who should care about {keyword} | Clarifies search intent |
| Comparison | Alternatives and tradeoffs | Helps buyer decision |
| Pricing | Research note, no fake pricing | Keeps content compliant |
| CTA | Soft next step | Improves affiliate conversion |"""


def seo_title(keyword: str, action_type: str) -> str:
    cleaned = title_case(keyword)
    if action_type == "create_comparison_page":
        return f"{cleaned}: Practical Comparison and Buying Notes"
    if action_type == "create_pricing_section":
        return f"{cleaned}: Pricing Questions to Check Before Buying"
    return f"{cleaned}: Practical Review and Decision Guide"


def meta_description(keyword: str, topic: str, reason: str) -> str:
    return (
        f"Research-style guide to {keyword} for the {topic} cluster, with practical use cases, risks, "
        "comparison notes, and next steps before choosing a tool."
    )[:165]


def public_url_for_action(item: dict[str, str], slug: str) -> str:
    page_url = item.get("page_url", "")
    if page_url.startswith("http"):
        return page_url
    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    if page_url.startswith("/"):
        return base + page_url
    return f"{base}/{slug}/"


def suggested_slug(keyword: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(keyword or "").strip().lower())
    return text.strip("-") or "action-draft"


def title_case(value: str) -> str:
    return " ".join(word.upper() if word.lower() in {"ai", "seo", "crm"} else word.capitalize() for word in str(value).split())


def safe_rank(value: object) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def build_action_priority_report() -> pd.DataFrame:
    keyword_report = read_csv("keyword_intelligence_report.csv")
    quality = read_csv("content_quality_report.csv")
    affiliate = read_csv("affiliate_tracking_report.csv")
    seo_audit = read_csv("seo_audit_report.csv")

    rows: list[dict[str, object]] = []
    rows.extend(actions_from_keywords(keyword_report))
    rows.extend(actions_from_quality(quality))
    rows.extend(actions_from_affiliate_tracking(affiliate))
    rows.extend(actions_from_seo_audit(seo_audit))

    if not rows:
        return pd.DataFrame(columns=ACTION_COLUMNS)

    df = pd.DataFrame(rows)
    df["_score"] = pd.to_numeric(df.get("_score", 0), errors="coerce").fillna(0)
    df = df.sort_values(["_score", "expected_impact", "difficulty"], ascending=[False, True, True])
    df = df.drop_duplicates(subset=["action_type", "keyword", "page_url", "platform"], keep="first")
    df = df.reset_index(drop=True)
    df["priority_rank"] = range(1, len(df) + 1)
    return df[ACTION_COLUMNS]


def actions_from_keywords(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty:
        return []
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        priority = to_int(row.get("priority_score"), 0)
        gap = str(row.get("content_gap", "")).strip()
        intent = str(row.get("intent", "")).strip()
        keyword = str(row.get("keyword", "")).strip()
        page_url = str(row.get("page_url", "")).strip()
        topic = str(row.get("topic_cluster", "")).strip()
        if priority < 55 and gap == "ready":
            continue
        action_type = action_type_for_keyword(intent, gap)
        reason_parts = [f"keyword priority {priority}"]
        if gap and gap != "ready":
            reason_parts.append(f"content gap: {gap}")
        if intent in {"comparison", "review", "pricing", "alternative"}:
            reason_parts.append(f"high-intent {intent} keyword")
        rows.append(
            action_row(
                score=priority + gap_bonus(gap) + intent_bonus(intent),
                action_type=action_type,
                topic=topic,
                keyword=keyword,
                page_url=page_url,
                platform="",
                reason="; ".join(reason_parts),
                expected_impact=impact_for_score(priority),
                difficulty=difficulty_for_gap(gap),
                next_action=str(row.get("next_action", "")) or default_next_action(action_type, keyword),
            )
        )
    return rows


def actions_from_quality(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty or "recommendation" not in df.columns:
        return []
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        recommendation = str(row.get("recommendation", "")).strip()
        if not recommendation or recommendation == "ok":
            continue
        page_url = str(row.get("page_url", "")).strip()
        topic = str(row.get("topic", "")).strip()
        parts = set(recommendation.split("|"))
        if "add_cta" in parts:
            rows.append(
                action_row(
                    score=82,
                    action_type="improve_cta",
                    topic=topic,
                    keyword=slug_to_keyword(page_url),
                    page_url=page_url,
                    platform="",
                    reason="content quality check found missing or weak CTA",
                    expected_impact="high",
                    difficulty="low",
                    next_action="add clearer CTA block and route outbound links through /go/",
                )
            )
        content_missing = parts & {"add_experience", "add_use_case", "add_opinion", "add_comparison", "too_generic"}
        if content_missing:
            rows.append(
                action_row(
                    score=74 + len(content_missing) * 3,
                    action_type="improve_existing_article",
                    topic=topic,
                    keyword=slug_to_keyword(page_url),
                    page_url=page_url,
                    platform="",
                    reason="content quality issues: " + ", ".join(sorted(content_missing)),
                    expected_impact="medium",
                    difficulty="medium",
                    next_action="add hands-on experience, use cases, opinion, and comparison detail",
                )
            )
    return rows


def actions_from_affiliate_tracking(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty or "recommendation" not in df.columns:
        return []
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        rec = str(row.get("recommendation", "")).strip()
        if not rec or rec == "ready":
            continue
        action_type = {
            "priority_social_push": "push_social",
            "needs_better_cta": "improve_cta",
            "missing_tool_name": "review_affiliate_link",
            "good_for_seo_internal_link": "add_internal_links",
        }.get(rec, "review_affiliate_link")
        rows.append(
            action_row(
                score={"priority_social_push": 78, "needs_better_cta": 82, "missing_tool_name": 65, "good_for_seo_internal_link": 70}.get(rec, 60),
                action_type=action_type,
                topic=str(row.get("topic", "")),
                keyword=slug_to_keyword(str(row.get("page_slug", ""))),
                page_url=str(row.get("target_url", "")),
                platform=str(row.get("platform", "")),
                reason=f"affiliate tracking recommendation: {rec}",
                expected_impact="high" if rec in {"priority_social_push", "needs_better_cta"} else "medium",
                difficulty="low",
                next_action=tracking_next_action(rec),
            )
        )
    return rows


def actions_from_seo_audit(df: pd.DataFrame) -> list[dict[str, object]]:
    if df.empty or "warnings" not in df.columns:
        return []
    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        warnings = str(row.get("warnings", "")).strip()
        if not warnings:
            continue
        page_url = str(row.get("page_url", "")).strip()
        warning_set = set(warnings.split("|"))
        if "few_internal_links" in warning_set or "few_related_posts" in warning_set:
            rows.append(
                action_row(
                    score=64,
                    action_type="add_internal_links",
                    topic=topic_from_url(page_url),
                    keyword=slug_to_keyword(page_url),
                    page_url=page_url,
                    platform="",
                    reason=f"SEO audit warnings: {warnings}",
                    expected_impact="medium",
                    difficulty="low",
                    next_action="add 3-6 relevant internal links and related posts",
                )
            )
        if "missing_faq_schema" in warning_set:
            rows.append(
                action_row(
                    score=58,
                    action_type="improve_existing_article",
                    topic=topic_from_url(page_url),
                    keyword=slug_to_keyword(page_url),
                    page_url=page_url,
                    platform="",
                    reason="FAQ content exists but FAQ schema is missing",
                    expected_impact="medium",
                    difficulty="low",
                    next_action="add FAQPage schema for existing FAQ section",
                )
            )
    return rows


def action_row(
    *,
    score: int,
    action_type: str,
    topic: str,
    keyword: str,
    page_url: str,
    platform: str,
    reason: str,
    expected_impact: str,
    difficulty: str,
    next_action: str,
) -> dict[str, object]:
    return {
        "_score": int(max(0, min(100, score))),
        "priority_rank": 0,
        "action_type": action_type,
        "topic": topic,
        "keyword": keyword,
        "page_url": page_url,
        "platform": platform,
        "reason": reason,
        "expected_impact": expected_impact,
        "difficulty": difficulty,
        "next_action": next_action,
    }


def read_csv(name: str) -> pd.DataFrame:
    path = settings.data_dir / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except Exception:
        return pd.DataFrame()


def action_type_for_keyword(intent: str, gap: str) -> str:
    if gap == "missing_page":
        if intent == "comparison":
            return "create_comparison_page"
        if intent == "pricing":
            return "create_pricing_section"
        return "write_new_article"
    if gap == "needs_comparison":
        return "create_comparison_page"
    if gap == "needs_pricing_section":
        return "create_pricing_section"
    return "improve_existing_article"


def gap_bonus(gap: str) -> int:
    return {
        "missing_page": 14,
        "needs_comparison": 12,
        "needs_pricing_section": 10,
        "needs_use_case": 8,
        "thin_content": 6,
    }.get(gap, 0)


def intent_bonus(intent: str) -> int:
    return {"comparison": 10, "review": 8, "pricing": 8, "alternative": 7, "best_tools": 5}.get(intent, 0)


def impact_for_score(score: int) -> str:
    if score >= 72:
        return "high"
    if score >= 58:
        return "medium"
    return "low"


def difficulty_for_gap(gap: str) -> str:
    if gap == "missing_page":
        return "high"
    if gap in {"thin_content", "needs_comparison"}:
        return "medium"
    return "low"


def default_next_action(action_type: str, keyword: str) -> str:
    if action_type == "create_comparison_page":
        return f"create comparison page for {keyword}"
    if action_type == "create_pricing_section":
        return f"add pricing section/page for {keyword}"
    if action_type == "write_new_article":
        return f"write new article for {keyword}"
    return f"improve existing content for {keyword}"


def tracking_next_action(recommendation: str) -> str:
    return {
        "priority_social_push": "schedule approved social post and monitor UTM performance",
        "needs_better_cta": "rewrite CTA and ensure tracked_url is used",
        "missing_tool_name": "map tracking row to a tool name or affiliate link record",
        "good_for_seo_internal_link": "add this page as a contextual internal link target",
    }.get(recommendation, "review tracking row")


def slug_to_keyword(value: str) -> str:
    parsed = urlparse(str(value or ""))
    path = parsed.path or str(value or "")
    slug = path.strip("/").split("/")[-1] if path.strip("/") else "homepage"
    return slug.replace("-", " ")


def topic_from_url(url: str) -> str:
    text = str(url or "").lower()
    if any(term in text for term in ["cursor", "copilot", "codex", "windsurf", "coding"]):
        return "AI coding tools"
    if any(term in text for term in ["seo", "semrush", "ahrefs", "surfer"]):
        return "AI SEO tools"
    if "pricing" in text:
        return "pricing"
    if "comparison" in text or "compare" in text or "-vs-" in text:
        return "comparisons"
    return "general"


def to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default
