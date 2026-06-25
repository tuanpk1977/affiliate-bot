from __future__ import annotations

import re
import html
import json
from datetime import date
from pathlib import Path
from typing import Any

from modules.content_operations import TODAY_WRITE_PLAN_FIELDS
from modules.performance_tracking import BASE_URL, DATA_DIR, read_csv, slugify, write_csv


ROOT = Path(__file__).resolve().parents[1]
DRAFT_DIR = ROOT / "draft_output"
ARTICLE_PACKAGE_DIR = DRAFT_DIR / "articles"
ARTICLE_VISUAL_DIR = ROOT / "assets" / "article-visuals"

OFFICIAL_LINKS = {
    "kilocode": "/go/kilocode/?src={slug}&cta=official_site",
    "hilltopads": "https://hilltopads.com/?ref=390226",
    "monetag": "https://monetag.com/?ref_id=tl16",
}

ARTICLE_DRAFT_REPORT_FIELDS = [
    "slug",
    "topic",
    "output_file",
    "status",
    "word_count_estimate",
    "article_type",
    "youtube_embed_position",
]

ARTICLE_JSON_FIELDS = [
    "slug",
    "topic",
    "title",
    "seo_title",
    "meta_description",
    "canonical",
    "status",
    "article_type",
    "youtube_embed_position",
]


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def display_name(value: str) -> str:
    words = re.sub(r"[-_]+", " ", value or "").strip().split()
    return " ".join(word.upper() if word.lower() in {"ai", "seo", "crm"} else word.capitalize() for word in words)


def official_link_for(slug: str, topic: str) -> str:
    haystack = f"{slug} {topic}".lower()
    for key, template in OFFICIAL_LINKS.items():
        if key in haystack:
            return template.format(slug=slug)
    return ""


def write_article_visuals(slug: str, topic: str, article_type: str) -> list[str]:
    ARTICLE_VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    safe_topic = html.escape(display_name(topic), quote=False)
    safe_type = html.escape(display_name(article_type or "review"), quote=False)
    visuals = {
        "buyer-checklist": (
            "Buyer Decision Snapshot",
            [
                ("Workflow fit", "Does it solve a daily business problem?"),
                ("Pricing risk", "Verify current plans, limits, and renewal terms."),
                ("Alternatives", "Compare at least two close substitutes."),
                ("Adoption", "Test with one real project before rollout."),
            ],
        ),
        "pricing-checklist": (
            "Pricing Verification Checklist",
            [
                ("Free trial", "Confirm whether a trial or free tier exists."),
                ("Usage limits", "Check credits, seats, exports, or automation caps."),
                ("Upgrade trigger", "Know when the plan becomes more expensive."),
                ("Cancellation", "Review refund and cancellation terms."),
            ],
        ),
    }
    paths: list[str] = []
    for suffix, (title, rows) in visuals.items():
        row_svg = []
        y = 322
        for label, note in rows:
            row_svg.append(
                f"<rect x='90' y='{y - 34}' width='1020' height='60' rx='12' fill='#f8fafc' stroke='#dbe3ef'/>"
                f"<text x='120' y='{y}' font-size='26' font-weight='700' fill='#0f172a'>{html.escape(label)}</text>"
                f"<text x='420' y='{y}' font-size='22' fill='#334155'>{html.escape(note)}</text>"
            )
            y += 82
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="780" viewBox="0 0 1200 780">
<rect width="1200" height="780" fill="#eef7ff"/>
<rect x="60" y="60" width="1080" height="660" rx="28" fill="#ffffff" stroke="#c8d7ee" stroke-width="2"/>
<rect x="60" y="60" width="1080" height="92" rx="28" fill="#0f766e"/>
<text x="92" y="118" font-family="Arial, sans-serif" font-size="34" font-weight="700" fill="#ffffff">MS Smile AI Review Hub</text>
<text x="92" y="205" font-family="Arial, sans-serif" font-size="36" font-weight="700" fill="#0f172a">{html.escape(title)}</text>
<text x="92" y="252" font-family="Arial, sans-serif" font-size="24" fill="#475569">{safe_topic} - {safe_type}</text>
<g font-family="Arial, sans-serif">{''.join(row_svg)}</g>
<text x="92" y="685" font-family="Arial, sans-serif" font-size="20" fill="#64748b">Use this visual as an editorial checklist. Verify live pricing on the official website.</text>
</svg>
"""
        path = ARTICLE_VISUAL_DIR / f"{slug}-{suffix}.svg"
        path.write_text(svg, encoding="utf-8")
        paths.append(f"/assets/article-visuals/{slug}-{suffix}.svg")
    return paths


def article_sections(topic: str, article_type: str, slug: str = "") -> list[tuple[str, str]]:
    base = topic.replace("  ", " ").strip()
    label = display_name(base)
    official_link = official_link_for(slug, base)
    comparison = markdown_table(
        ["Decision area", "What to verify", "Buyer impact", "Risk level"],
        [
            ["Core features", "Check the official product page and current release notes.", "Feature fit matters more than broad marketing claims.", "Medium"],
            ["Pricing", "Verify current pricing on the official website.", "Software prices and plan limits change often.", "High"],
            ["Alternatives", "Compare at least two competing tools.", "A better fit may exist for a narrower workflow.", "Medium"],
            ["Risk", "Check cancellation, data, and team permission details.", "These details affect long-term adoption.", "High"],
        ],
    )
    official = (
        f"The safest starting point is the official website: [{label} official website]({official_link}). "
        "Use this link to confirm current pricing, product positioning, free trial availability, documentation, and support terms before buying."
        if official_link
        else "For this category-style topic, use each vendor's official website before making a buying decision. Do not rely only on screenshots, social posts, or old pricing summaries because SaaS limits can change quickly."
    )
    return [
        (
            "Direct Answer",
            f"{label} is worth considering only if it solves a clear workflow problem, has pricing that fits the expected usage, and compares well against close alternatives. Buyers should verify current pricing, test the tool with one real project, and avoid committing to an annual plan until the workflow value is proven.",
        ),
        (
            "Quick Takeaways",
            f"- Best fit: teams with a defined workflow and a measurable reason to test {label}.\n- Pricing rule: verify current pricing on the official website before buying.\n- Risk check: confirm cancellation terms, data export, support, and usage limits.\n- Decision rule: compare at least two alternatives before choosing.\n- Video placement: put the video review after the intro so mobile readers can choose text or video quickly.",
        ),
        (
            "Overview",
            f"{label} should be reviewed as a business workflow decision, not only as a trend. A useful review answers three questions: what problem the tool solves, who gets the most value from it, and what a buyer should verify before spending money. This guide focuses on practical buyer fit, real workflow value, pricing risk, alternatives, and the checks that matter before a team adds another SaaS subscription.",
        ),
        (
            "Best For",
            f"{label} is best for teams that already know the workflow they want to improve. Good candidates include founders, creators, marketers, agencies, and operators who need software to save time, standardize a process, or improve output quality. It is also useful for buyers who want a structured way to compare pricing, limitations, integrations, support, and alternatives before choosing a tool.",
        ),
        (
            "Not Best For",
            "It is not best for buyers who only want the cheapest possible option, teams that have not defined their workflow, or users who expect one tool to replace a complete operating process. If the use case is unclear, start with a small trial or a manual workflow before committing to a paid plan.",
        ),
        ("Feature Comparison", comparison),
        (
            "Pricing Notes",
            "Always verify current pricing on the official website. Pricing pages can change, plan limits may differ by region, and annual discounts can affect the true cost. Treat pricing as a checklist rather than a fixed number: plan limits, seats, usage caps, cancellation terms, support level, integrations, renewal terms, and upgrade triggers. If a tool uses credits, minutes, exports, or automation runs, estimate your real usage before choosing a plan.",
        ),
        (
            "Official Website and Trial Check",
            official,
        ),
        (
            "Buyer Decision Checklist",
            "- Does the tool solve a problem that happens every week?\n- Can one person own setup and maintenance?\n- Is the first paid plan enough for the expected workflow?\n- Can data, templates, or projects be exported if the team leaves?\n- Does the tool integrate with the systems the team already uses?\n- Is support good enough for the business risk involved?",
        ),
        (
            "Best Use Cases",
            f"{label} is most useful when the buyer has a repeatable workflow, a clear owner, and a measurable reason to test the tool. Good use cases include reducing manual research, improving production quality, comparing vendors before purchase, documenting software decisions, building repeatable content operations, and helping a small team move faster without adding another full-time role.",
        ),
        (
            "Pros",
            "- Useful when it maps directly to an existing workflow.\n- Can reduce manual research, production, or operational work.\n- Often easier to test than building a custom internal system.\n- May create leverage when paired with clear SOPs and analytics.",
        ),
        (
            "Cons",
            "- Pricing and limits must be checked before buying.\n- Some features may look stronger in demos than in daily work.\n- Teams can overpay if the workflow is not clearly defined.\n- Switching costs can grow after data, templates, or automations are built inside the platform.",
        ),
        (
            "Alternatives",
            f"Before choosing {label}, compare it with related tools in the same workflow. Look for alternatives with different strengths: cheaper entry pricing, stronger integrations, better analytics, simpler onboarding, or more advanced team controls. The right alternative depends on whether the buyer values price, speed, control, collaboration, content quality, or automation depth most.",
        ),
        (
            "Internal Link Suggestions",
            "- Link to the closest review page in the same category.\n- Link to one comparison page for buyers evaluating alternatives.\n- Link to one best tools category page.\n- Link to one pricing or free trial guide if available.\n- Link back from related articles after publishing.",
        ),
        (
            "Suggested YouTube Embed Position",
            "Place the YouTube video after the introduction or immediately before the pricing section. This keeps the page useful for readers while giving video visitors a clear path to the full written review.",
        ),
        (
            "FAQ",
            f"### Is {label} worth it?\nIt can be worth it if the product solves a specific workflow problem and the current pricing fits your budget.\n\n### Where should I check the official product details?\nUse the official website before buying. Pricing, trials, plan limits, and feature availability can change.\n\n### Should I trust vendor pricing claims from old reviews?\nNo. Verify current pricing on the official website before buying.\n\n### Who should avoid this type of software?\nTeams without a defined workflow, unclear ownership, or low usage frequency should wait before paying.\n\n### What should I compare first?\nCompare pricing, core features, integrations, limitations, support, cancellation terms, and data export.\n\n### Can this replace a human workflow?\nUsually not completely. It works best when paired with clear human review and operating standards.",
        ),
        (
            "Final Verdict",
            f"{label} should be evaluated as a practical business tool, not as a trend. The strongest choices improve a measurable workflow, have clear pricing, provide reliable integrations, and can be tested without major switching costs. The best next step is to verify current details on the official website, run one real project, compare alternatives, and only then decide whether the tool deserves a long-term place in the workflow.",
        ),
    ]


def article_metadata(row: dict[str, Any]) -> dict[str, Any]:
    topic = str(row.get("topic") or row.get("suggested_title") or "").strip()
    slug = slugify(row.get("slug") or topic)
    title = str(row.get("suggested_title") or topic.title()).strip()
    seo_title = title[:58]
    meta = f"Independent guide to {topic}, covering pricing, pros, cons, alternatives, buyer fit, and practical workflow checks."
    return {
        "slug": slug,
        "topic": topic,
        "title": title,
        "seo_title": seo_title,
        "meta_description": meta[:155],
        "canonical": f"{BASE_URL}/{slug}/",
        "status": "READY_FOR_REVIEW",
        "article_type": str(row.get("article_type") or "review").strip(),
        "youtube_embed_position": "After introduction or before pricing section",
    }


def generate_article_markdown(row: dict[str, Any]) -> str:
    meta_data = article_metadata(row)
    topic = meta_data["topic"]
    slug = meta_data["slug"]
    article_type = meta_data["article_type"]
    title = meta_data["title"]
    visual_paths = write_article_visuals(slug, topic, article_type)
    parts = [
        "---",
        f"title: {title}",
        f"slug: {slug}",
        f"date: {date.today().isoformat()}",
        "status: READY_FOR_REVIEW",
        f"canonical: {meta_data['canonical']}",
        "---",
        "",
        f"# {title}",
        "",
        f"**SEO title:** {meta_data['seo_title']}",
        "",
        f"**Meta description:** {meta_data['meta_description']}",
        "",
        "**Affiliate disclosure:** Some links may be affiliate links. We may earn a commission at no extra cost to you. This does not change the evaluation method.",
        "",
        "## Author",
        "**Written by:** Nguyen Quoc Tuan, Founder - MS Smile AI Review Hub.",
        "",
        "**Last updated:** June 2026.",
        "",
        "## Watch the video review",
        "A YouTube embed can be placed here after the video is uploaded and the URL is added to upload_links.csv.",
        "",
        "## Introduction",
        f"{topic} is the kind of topic that deserves a careful, buyer-focused review. This draft is designed for editorial review before publishing. It covers what the tool or category does, who it is best for, what pricing details need verification, where alternatives may fit better, and how a reader should decide whether to test it.",
        "",
        f"![{display_name(topic)} buyer decision snapshot]({visual_paths[0]})",
        "",
        f"![{display_name(topic)} pricing verification checklist]({visual_paths[1]})",
        "",
    ]
    for heading, content in article_sections(topic, article_type, slug):
        parts.append(f"## {heading}")
        parts.append(content)
        parts.append("")
    supplemental_sections = [
        (
            "How To Test It Before Paying",
            f"Start with one realistic task instead of a broad demo. For {display_name(topic)}, define the expected output, the owner, the success metric, and the time limit before opening a trial. A good test should reveal whether the tool saves time, improves quality, or reduces operational friction. If the result is unclear after one project, the buyer should keep comparing alternatives instead of forcing adoption.",
        ),
        (
            "Implementation Plan",
            "A practical rollout should begin with a small pilot, a written checklist, and one responsible owner. Document the setup steps, the first workflow, the cost assumptions, and the decision deadline. After the pilot, review output quality, support experience, team adoption, and total cost. This prevents a tool from becoming another unused subscription.",
        ),
        (
            "Risk Notes",
            "The biggest risks are usually not the headline features. They are pricing changes, unclear usage limits, weak export options, poor support, and team adoption problems. Buyers should also check whether the tool stores sensitive business data, whether generated outputs need human review, and whether cancellation is simple if the product does not fit.",
        ),
        (
            "Editorial Methodology",
            "Smile AI Review Hub evaluates software from a buyer perspective. The review structure prioritizes workflow fit, pricing verification, product limitations, alternatives, and practical use cases. Vendor claims should be treated as inputs, not conclusions. Final recommendations should be based on current product details, hands-on testing when possible, and comparison against close substitutes.",
        ),
    ]
    if len(" ".join(parts).split()) < 2200:
        for heading, content in supplemental_sections:
            parts.append(f"## {heading}")
            parts.append(content)
            parts.append("")
    return "\n".join(parts).strip() + "\n"


def generate_article_package(row: dict[str, Any], output_dir: Path = ARTICLE_PACKAGE_DIR) -> dict[str, Any]:
    meta_data = article_metadata(row)
    slug = meta_data["slug"]
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"{slug}.md"
    json_path = output_dir / f"{slug}.json"
    markdown = generate_article_markdown(row)
    markdown_path.write_text(markdown, encoding="utf-8")
    payload = {
        **meta_data,
        "generated_date": date.today().isoformat(),
        "word_count_estimate": len(re.findall(r"\w+", markdown)),
        "sections": [heading for heading, _ in article_sections(meta_data["topic"], meta_data["article_type"], slug)],
        "internal_link_suggestions": [
            "Closest review page in the same category",
            "One comparison page",
            "One best tools category page",
            "One pricing or free trial guide",
        ],
        "source": "daily_ai_content_factory",
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "slug": slug,
        "topic": meta_data["topic"],
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "status": "READY_FOR_REVIEW",
        "word_count_estimate": payload["word_count_estimate"],
        "article_type": meta_data["article_type"],
        "youtube_embed_position": meta_data["youtube_embed_position"],
    }


def generate_drafts_from_today_plan(limit: int = 10) -> list[dict[str, Any]]:
    rows = read_csv(DATA_DIR / "today_write_plan.csv")
    candidates = [row for row in rows if row.get("action") in {"CREATE", "CONTENT GAP"}]
    reports: list[dict[str, Any]] = []
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    for row in candidates[:limit]:
        slug = slugify(row.get("slug") or row.get("topic"))
        if not slug:
            continue
        output = DRAFT_DIR / f"{slug}.md"
        content = generate_article_markdown(row)
        output.write_text(content, encoding="utf-8")
        package = generate_article_package(row)
        reports.append(
            {
                "slug": slug,
                "topic": row.get("topic", ""),
                "output_file": package["markdown_path"],
                "status": "READY_FOR_REVIEW",
                "word_count_estimate": len(re.findall(r"\w+", content)),
                "article_type": row.get("article_type", ""),
                "youtube_embed_position": "After introduction or before pricing section",
            }
        )
    write_csv(DATA_DIR / "article_draft_report.csv", reports, ARTICLE_DRAFT_REPORT_FIELDS)
    return reports
