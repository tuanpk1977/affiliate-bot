from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from config import settings
from modules.comparison_page_builder import build_tool_map, ensure_tracking_links
from modules.pricing_page_builder import EXISTING_REVIEW_SLUGS, PRICING_FALLBACK_TOOLS, ensure_pricing_tracking_links
from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, faq_html, faq_schema, item_list_schema, shell, write_page


INDEX_COLUMNS = ["category_slug", "title", "tool_count", "output_path", "status"]


CATEGORY_DEFINITIONS = [
    {
        "slug": "ai-coding-tools",
        "title": "AI Coding Tools",
        "tools": ["cursor", "github-copilot", "windsurf", "codeium"],
        "hub": "/hub/ai-coding/",
        "toplist": "/best-ai-coding-tools/",
        "angle": "developer productivity, code review, repository context, and team policy",
    },
    {
        "slug": "seo-tools",
        "title": "SEO Tools",
        "tools": ["semrush", "ahrefs", "surfer-seo"],
        "hub": "/hub/ai-seo/",
        "toplist": "/best-ai-seo-tools/",
        "angle": "keyword research, competitor analysis, technical audits, and content planning",
    },
    {
        "slug": "email-marketing-tools",
        "title": "Email Marketing Tools",
        "tools": ["activecampaign", "mailchimp", "hubspot"],
        "hub": "/hub/email-marketing/",
        "toplist": "/best-crm-tools/",
        "angle": "list growth, segmentation, lifecycle automation, and deliverability discipline",
    },
    {
        "slug": "automation-tools",
        "title": "Automation Tools",
        "tools": ["make", "zapier", "reclaim-ai"],
        "hub": "/hub/ai-automation/",
        "toplist": "/best-ai-automation-tools/",
        "angle": "workflow mapping, task volume, integrations, and operational reliability",
    },
    {
        "slug": "design-tools",
        "title": "Design Tools",
        "tools": ["canva", "adcreative-ai", "gamma"],
        "hub": "/hub/ai-presentation/",
        "toplist": "/best-ai-presentation-tools/",
        "angle": "visual production, brand consistency, ad creative testing, and presentation workflows",
    },
    {
        "slug": "video-tools",
        "title": "Video Tools",
        "tools": ["synthesia", "runway", "pictory", "descript"],
        "hub": "/hub/ai-video/",
        "toplist": "/best-ai-video-tools/",
        "angle": "video generation, editing speed, export rights, and review workflows",
    },
    {
        "slug": "writing-tools",
        "title": "Writing Tools",
        "tools": ["jasper", "copy-ai", "grammarly", "quillbot", "notion-ai"],
        "hub": "/hub/ai-writing/",
        "toplist": "/best-ai-writing-tools/",
        "angle": "drafting, editing, brand voice, repurposing, and content QA",
    },
    {
        "slug": "website-builder-tools",
        "title": "Website Builder Tools",
        "tools": ["webflow-ai", "framer", "durable"],
        "hub": "/hub/website-builders/",
        "toplist": "/best-website-builders/",
        "angle": "site structure, CMS needs, launch speed, design control, and maintenance",
    },
]

EXISTING_PRICING_SLUGS = {
    "cursor",
    "github-copilot",
    "semrush",
    "make",
    "zapier",
    "canva",
    "activecampaign",
    "mailchimp",
    "pictory",
    "grammarly",
}


def generate_category_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    tool_map = build_tool_map(offer_scores)
    for slug, data in PRICING_FALLBACK_TOOLS.items():
        tool_map.setdefault(slug, normalize_tool(data))
    ensure_tracking_links(tool_map)
    ensure_pricing_tracking_links(tool_map)

    pages: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []
    for category in CATEGORY_DEFINITIONS:
        tools = [normalize_tool(tool_map[slug]) for slug in category["tools"] if slug in tool_map]
        if not tools:
            continue
        page_path = write_page(output, f"category/{category['slug']}", render_category_page(category, tools))
        pages.append({"slug": f"category/{category['slug']}", "title": category["title"], "type": "category_landing"})
        index_rows.append(
            {
                "category_slug": category["slug"],
                "title": category["title"],
                "tool_count": str(len(tools)),
                "output_path": str(page_path),
                "status": "built",
            }
        )

    safe_write_index(pd.DataFrame(index_rows, columns=INDEX_COLUMNS))
    return pages


def normalize_tool(row: dict) -> dict[str, str]:
    slug = str(row.get("offer_id") or row.get("tool_slug") or "").strip()
    return {
        "offer_id": slug,
        "brand_name": str(row.get("brand_name") or row.get("tool_name") or slug.replace("-", " ").title()).strip(),
        "niche": str(row.get("niche") or "AI/SaaS").strip(),
        "website": str(row.get("website") or row.get("official_url") or "").strip(),
        "score": str(row.get("total_score") or row.get("score") or "Research required").strip(),
        "risk": str(row.get("risk_level") or row.get("risk") or "Needs review").strip(),
        "competition": str(row.get("competition") or "Medium").strip(),
    }


def safe_write_index(index: pd.DataFrame) -> None:
    path = settings.data_dir / "category_pages_index.csv"
    try:
        index.to_csv(path, index=False)
    except PermissionError:
        if not path.exists():
            raise
        print(f"WARNING: {path} is locked. Keeping existing category_pages_index.csv.")


def render_category_page(category: dict, tools: list[dict[str, str]]) -> str:
    path = f"/category/{category['slug']}/"
    title = f"Best {category['title']} to Research Before You Buy"
    description = f"Research guide to {category['title'].lower()} with best tools table, solo/team/agency fit, mistakes to avoid, reviews, comparisons, pricing notes, and affiliate disclosure."
    questions = faq_questions(category["title"])
    body = "\n".join(
        [
            hero_block(category, tools),
            affiliate_disclosure(),
            best_tools_table(category, tools),
            buyer_fit_block(category, tools),
            how_to_choose_block(category, tools),
            common_mistakes_block(category),
            related_reviews_block(tools),
            related_comparisons_block(category, tools),
            related_pricing_block(tools),
            category_cta_block(category, tools),
            faq_block(questions),
        ]
    )
    schemas = [faq_schema(questions), breadcrumb_schema(title, path), item_list_schema(title, [tool["brand_name"] for tool in tools], path)]
    return shell(title, description, path, body, schemas)


def hero_block(category: dict, tools: list[dict[str, str]]) -> str:
    title = html.escape(category["title"])
    slug = html.escape(category["slug"])
    angle = html.escape(category["angle"])
    primary = tools[0]
    primary_slug = html.escape(primary["offer_id"])
    primary_name = html.escape(primary["brand_name"])
    return f"""
<section class='hero card'>
  <p><a href='/'>Home</a> / <a href='/hubs/'>Hubs</a> / {title}</p>
  <p class='badge'>Category research hub</p>
  <h1>{title}: Research Guide and Shortlist</h1>
  <p>This category page is for buyers comparing {title.lower()} with a practical lens: {angle}. Instead of ranking tools only by brand awareness, it looks at workflow fit, pricing risk, team adoption, alternatives, and whether the next click should be a review, comparison, pricing page, or official website.</p>
  <p>Use this page as a research starting point. The goal is not to claim one product is perfect for everyone; the goal is to help you build a short list, avoid common buying mistakes, and verify official terms before spending money or promoting an offer.</p>
  <p><a class='btn' href='/go/{primary_slug}/?src=category/{slug}&cta=category_page'>Visit {primary_name}</a><a class='btn secondary' href='{html.escape(category["hub"])}'>Open related hub</a></p>
</section>
"""


def best_tools_table(category: dict, tools: list[dict[str, str]]) -> str:
    rows = []
    for idx, tool in enumerate(tools, start=1):
        slug = html.escape(tool["offer_id"])
        brand = html.escape(tool["brand_name"])
        fit_text = html.escape(best_for(tool, category))
        caution = html.escape(tool_caution(tool, category))
        review = review_url(tool["offer_id"])
        rows.append(
            f"<tr><td>{idx}</td><td><strong>{brand}</strong></td><td>{fit_text}</td><td>{html.escape(tool['risk'])}</td><td>{caution}</td><td><a href='{review}'>Read review</a> <a href='/go/{slug}/?src=category/{html.escape(category['slug'])}&cta=category_page'>Visit Official Website</a></td></tr>"
        )
    return f"""
<section class='card'>
  <h2>Best tools table</h2>
  <p>The table below is a shortlist, not a final recommendation. Check current pricing, feature limits, affiliate policy, and the exact workflow you need before buying or promoting any tool.</p>
  <table>
    <thead><tr><th>#</th><th>Tool</th><th>Best for</th><th>Risk signal</th><th>What to verify</th><th>Next step</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def buyer_fit_block(category: dict, tools: list[dict[str, str]]) -> str:
    title = html.escape(category["title"])
    solo = html.escape(f"Solo users should start with the tool that solves one repeated {category['angle'].split(',')[0]} task without forcing a large setup.")
    team = html.escape("Teams should prioritize permissions, repeatable templates, shared reporting, and whether non-technical teammates can use the workflow after onboarding.")
    agency = html.escape("Agencies and businesses should check client separation, predictable billing, export rights, support, and whether the tool can survive handoff between team members.")
    return f"""
<section class='card'>
  <h2>Best for solo / team / agency</h2>
  <div class='grid'>
    <div class='card'><h3>Solo user</h3><p>{solo} Pick a low-commitment plan first, complete one real project, and only upgrade if the result saves measurable time.</p></div>
    <div class='card'><h3>Small team</h3><p>{team} A {title} platform is only useful for a team if it reduces review friction rather than adding another dashboard to maintain.</p></div>
    <div class='card'><h3>Agency or business</h3><p>{agency} The cheapest plan is rarely the best signal; contract clarity, usage limits, and admin controls matter more at scale.</p></div>
  </div>
</section>
"""


def how_to_choose_block(category: dict, tools: list[dict[str, str]]) -> str:
    title = html.escape(category["title"])
    names = ", ".join(tool["brand_name"] for tool in tools[:4])
    return f"""
<section class='card'>
  <h2>How to choose {title}</h2>
  <p>Start by writing one concrete workflow before comparing {html.escape(names)} or any other tool in this category. A vague goal like "use AI more" is not enough. A better buying test is specific: publish one landing page, audit one SEO cluster, automate one lead handoff, create one video, or edit one article without losing quality.</p>
  <p>Next, compare each tool against five practical questions. Does it complete the workflow with less manual cleanup? Does it integrate with the tools you already use? Is pricing predictable after the first month? Can a teammate understand the output and process? Are the terms, affiliate rules, and commercial usage rights clear enough for the traffic source you plan to use?</p>
  <p>Finally, avoid choosing only from screenshots or social media demos. Read the review page, open at least one comparison, check a pricing page, and visit the official site through the tracking route so your own system can measure which categories and CTAs attract buyer interest.</p>
</section>
"""


def common_mistakes_block(category: dict) -> str:
    title = html.escape(category["title"])
    return f"""
<section class='card'>
  <h2>Common mistakes</h2>
  <ul>
    <li>Buying a {title} subscription before testing one real workflow end to end.</li>
    <li>Comparing only monthly price while ignoring usage limits, team seats, exports, and cancellation rules.</li>
    <li>Assuming a popular tool is approved for every affiliate traffic source, including paid search or direct linking.</li>
    <li>Skipping alternatives because the first tool has better branding or a better demo video.</li>
    <li>Choosing a tool for advanced features when the team has not mastered the basic workflow yet.</li>
    <li>Publishing affiliate content without disclosure, review context, or a clear note that pricing can change.</li>
  </ul>
</section>
"""


def related_reviews_block(tools: list[dict[str, str]]) -> str:
    links = []
    for tool in tools:
        links.append(f"<a href='{review_url(tool['offer_id'])}'>{html.escape(tool['brand_name'])} review</a>")
    return f"<section class='card'><h2>Related reviews</h2><p>{' '.join(links)}</p><p>Review pages explain workflow fit, pricing checks, risks, alternatives, and the final recommendation in more detail than a category shortlist can.</p></section>"


def related_comparisons_block(category: dict, tools: list[dict[str, str]]) -> str:
    links = comparison_links(category["slug"])
    link_html = " ".join(f"<a href='{html.escape(url)}'>{html.escape(label)}</a>" for label, url in links)
    return f"<section class='card'><h2>Related comparisons</h2><p>{link_html or '<a href=\"/comparisons/\">Browse all comparisons</a>'}</p><p>Comparison pages are useful when two tools look similar on the surface but differ in workflow, pricing risk, team fit, or implementation style.</p></section>"


def related_pricing_block(tools: list[dict[str, str]]) -> str:
    links = []
    for tool in tools:
        slug = tool["offer_id"]
        if slug in EXISTING_PRICING_SLUGS:
            links.append(f"<a href='/pricing/{html.escape(slug)}/'>{html.escape(tool['brand_name'])} pricing guide</a>")
    if not links:
        links.append("<a href='/comparisons/'>Browse comparison and pricing research</a>")
    return f"<section class='card'><h2>Related pricing pages</h2><p>{' '.join(links)}</p><p>Pricing guides avoid fixed price claims and focus on plan fit, trial checks, hidden cost risks, and official pricing verification.</p></section>"


def category_cta_block(category: dict, tools: list[dict[str, str]]) -> str:
    buttons = []
    for tool in tools[:3]:
        slug = html.escape(tool["offer_id"])
        brand = html.escape(tool["brand_name"])
        buttons.append(f"<a class='btn' href='/go/{slug}/?src=category/{html.escape(category['slug'])}&cta=category_page'>Visit {brand}</a>")
    return f"""
<section class='card trust'>
  <h2>Next step</h2>
  <p>Shortlist two or three tools, read their review pages, check current pricing, and use the official website only after you know what workflow you want to test. If a tool does not have an approved affiliate link yet, the tracking route still points to the official site and marks the status as pending or official-only.</p>
  <p>{''.join(buttons)}</p>
</section>
"""


def faq_block(questions: list[str]) -> str:
    return f"<section class='card'><h2>FAQ</h2>{faq_html(questions)}</section>"


def faq_questions(category_title: str) -> list[str]:
    return [
        f"How should I choose between {category_title}?",
        f"Which {category_title} are best for solo users?",
        f"Which {category_title} are safer for small teams?",
        f"What pricing risks should I check before buying {category_title}?",
        f"Can I promote {category_title} with affiliate links?",
        f"What should I compare before choosing a {category_title} platform?",
    ]


def best_for(tool: dict[str, str], category: dict) -> str:
    brand = tool["brand_name"]
    slug = tool["offer_id"]
    specific = {
        "cursor": "AI-first coding workflows where the editor itself becomes part of the assistant experience",
        "github-copilot": "developers who already work heavily inside GitHub and mainstream IDEs",
        "semrush": "SEO and marketing teams that need broad keyword, competitor, and reporting workflows",
        "make": "visual automation workflows with branching, multi-step logic, and careful maintenance",
        "zapier": "quick automation setup across many business apps with a beginner-friendly workflow",
        "canva": "broad design production, social visuals, presentations, and brand assets",
        "activecampaign": "email automation and CRM-style lifecycle marketing for growing lists",
        "synthesia": "avatar-led video, training content, and repeatable business video workflows",
        "jasper": "marketing content teams that need structured drafting and brand voice review",
        "webflow-ai": "website teams that need stronger design control, CMS structure, and production pages",
    }
    return specific.get(slug, f"{brand} buyers who need {category['angle']} in a repeatable workflow")


def tool_caution(tool: dict[str, str], category: dict) -> str:
    slug = tool["offer_id"]
    cautions = {
        "cursor": "Check repository privacy, team policy, and whether AI suggestions reduce or increase review time.",
        "github-copilot": "Check seat billing, organization controls, and whether developers use supported environments.",
        "semrush": "Check project, export, and keyword limits before assuming the lowest plan is enough.",
        "make": "Check operation volume and whether someone else can maintain the automation.",
        "zapier": "Check task volume, premium app access, and cost once automations run daily.",
        "canva": "Check brand control, export needs, and whether AI/design features are on the plan you choose.",
        "activecampaign": "Check contact tiers, automation limits, deliverability tools, and CRM needs.",
        "mailchimp": "Check list size, automation depth, and upgrade pressure as contacts grow.",
        "pictory": "Check video minutes, export quality, asset rights, and watermark rules.",
        "grammarly": "Check team writing controls, privacy needs, and whether rewriting support is enough.",
    }
    return cautions.get(slug, "Check official pricing, plan limits, affiliate rules, and current vendor terms.")


def review_url(slug: str) -> str:
    if slug in EXISTING_REVIEW_SLUGS:
        return f"/review/{html.escape(slug)}/"
    return "/reviews/"


def comparison_links(category_slug: str) -> list[tuple[str, str]]:
    return {
        "ai-coding-tools": [("Cursor vs GitHub Copilot", "/compare/cursor-vs-github-copilot/"), ("Cursor vs Windsurf", "/compare/cursor-vs-windsurf/")],
        "seo-tools": [("Semrush vs Ahrefs", "/compare/semrush-vs-ahrefs/")],
        "email-marketing-tools": [("ActiveCampaign vs Mailchimp", "/compare/activecampaign-vs-mailchimp/")],
        "automation-tools": [("Make vs Zapier", "/compare/make-vs-zapier/")],
        "design-tools": [("Canva vs AdCreative AI", "/compare/canva-vs-adcreative-ai/"), ("Canva vs Gamma", "/comparisons/canva-vs-gamma/")],
        "video-tools": [("Synthesia vs Pictory", "/compare/synthesia-vs-pictory/"), ("Synthesia vs Runway", "/comparisons/synthesia-vs-heygen/")],
        "writing-tools": [("Jasper vs Copy.ai", "/compare/jasper-vs-copy-ai/"), ("Grammarly vs QuillBot", "/compare/grammarly-vs-quillbot/")],
        "website-builder-tools": [("Framer vs Webflow", "/comparisons/framer-vs-webflow/")],
    }.get(category_slug, [])
