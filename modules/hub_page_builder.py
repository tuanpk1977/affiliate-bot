from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd

from config import settings
from modules.programmatic_page_utils import affiliate_disclosure, breadcrumb_schema, item_list_schema, shell, write_page


HUB_INDEX_COLUMNS = ["hub_slug", "hub_title", "output_path", "review_count", "comparison_count", "priority_page_count", "status"]


HUBS = [
    {
        "slug": "ai-coding",
        "title": "AI Coding Tools Hub",
        "description": "Research hub for AI coding tools, coding assistants, developer workflows, pricing pages, and comparison content.",
        "intro": "AI coding tools are not only autocomplete products. They affect how developers read unfamiliar code, refactor safely, write tests, and move through pull requests. This hub starts with workflow fit before tool preference.",
        "read_when": "Read this hub when you are deciding whether an AI-first editor, IDE assistant, or coding agent belongs in your daily development workflow.",
        "tokens": {"cursor", "github", "copilot", "windsurf", "vscode", "tabnine", "coding", "code", "developer"},
    },
    {
        "slug": "ai-seo",
        "title": "AI SEO Tools Hub",
        "description": "Research hub for SEO platforms, AI SEO workflows, content optimization tools, keyword research, and competitor analysis.",
        "intro": "SEO tools can look similar from the outside, but the real difference is usually in data depth, keyword workflow, content optimization, and how quickly a team can turn research into publishable pages.",
        "read_when": "Read this hub when you need to choose between broad SEO suites, content optimization tools, and AI-assisted keyword workflows.",
        "tokens": {"semrush", "ahrefs", "surfer", "seo", "keyword", "content", "ranking"},
    },
    {
        "slug": "ai-automation",
        "title": "AI Automation Tools Hub",
        "description": "Research hub for automation tools, no-code workflows, app connectors, and operational productivity systems.",
        "intro": "Automation platforms should be judged by the workflows they make reliable, not by the number of app logos on a landing page. This hub focuses on practical workflow design and operational risk.",
        "read_when": "Read this hub when you want to connect apps, reduce manual work, or compare no-code automation tools before building repeatable processes.",
        "tokens": {"make", "zapier", "automation", "workflow", "connector", "no-code"},
    },
    {
        "slug": "ai-presentation",
        "title": "AI Presentation Tools Hub",
        "description": "Research hub for AI presentation tools, deck builders, visual storytelling, and design-assisted content workflows.",
        "intro": "Presentation tools are useful only if they help turn messy ideas into clear communication. The best choice depends on whether you need decks, documents, social assets, or client-ready storytelling.",
        "read_when": "Read this hub when you are comparing AI presentation builders, design tools, and visual communication workflows.",
        "tokens": {"gamma", "canva", "presentation", "slides", "deck", "design"},
    },
    {
        "slug": "ai-voice",
        "title": "AI Voice Tools Hub",
        "description": "Research hub for AI voice generators, narration tools, voiceover workflows, and audio content production.",
        "intro": "Voice tools need careful evaluation because quality, licensing, language support, and commercial rights can matter more than the first demo clip.",
        "read_when": "Read this hub when you need AI narration for videos, training, podcasts, localization, or repeatable creator workflows.",
        "tokens": {"elevenlabs", "murf", "playht", "voice", "audio", "narration"},
    },
    {
        "slug": "ai-video",
        "title": "AI Video Tools Hub",
        "description": "Research hub for AI video generators, avatar video, creative editing, and short-form production workflows.",
        "intro": "AI video tools vary widely by output quality, editing control, avatar workflow, licensing, and how much manual cleanup is needed after generation.",
        "read_when": "Read this hub when you are comparing AI video generators for creative testing, training videos, social clips, or product explainers.",
        "tokens": {"runway", "pika", "synthesia", "heygen", "descript", "video", "avatar"},
    },
    {
        "slug": "crm",
        "title": "CRM Tools Hub",
        "description": "Research hub for CRM software, sales workflow tools, customer management, and startup CRM comparisons.",
        "intro": "A CRM is not just a contact database. The right choice affects sales follow-up, reporting, marketing handoff, and how cleanly a team can manage customer conversations.",
        "read_when": "Read this hub when you are comparing CRM tools for startup sales, marketing automation, pipeline management, or customer operations.",
        "tokens": {"hubspot", "pipedrive", "salesforce", "crm", "sales", "customer"},
    },
    {
        "slug": "website-builders",
        "title": "Website Builders Hub",
        "description": "Research hub for website builders, landing page tools, CMS platforms, and AI website generation workflows.",
        "intro": "Website builders should be judged by publishing speed, design control, CMS structure, SEO flexibility, and maintenance burden after the first page is live.",
        "read_when": "Read this hub when you are choosing a website builder for landing pages, review sites, CMS content, or client marketing pages.",
        "tokens": {"framer", "webflow", "durable", "website", "builder", "cms", "landing"},
    },
    {
        "slug": "ai-writing",
        "title": "AI Writing Tools Hub",
        "description": "Research hub for AI writing tools, marketing copy, content workflows, alternatives, and buyer-intent articles.",
        "intro": "AI writing tools are most useful when they support a real editorial process: briefs, drafts, rewrites, brand voice, and final human review.",
        "read_when": "Read this hub when you are comparing writing assistants for blog content, marketing copy, sales material, or team content operations.",
        "tokens": {"jasper", "copy", "copyai", "copy-ai", "notion", "chatgpt", "claude", "writing", "content"},
    },
    {
        "slug": "email-marketing",
        "title": "Email Marketing Tools Hub",
        "description": "Research hub for email marketing platforms, automation, newsletters, CRM-connected campaigns, and alternatives.",
        "intro": "Email marketing software needs to be evaluated by deliverability, automation depth, segmentation, CRM fit, reporting, and how easy it is to maintain campaigns.",
        "read_when": "Read this hub when you are comparing newsletter tools, email automation platforms, or marketing systems connected to CRM workflows.",
        "tokens": {"activecampaign", "email", "newsletter", "marketing", "automation"},
    },
    {
        "slug": "productivity",
        "title": "AI Productivity Tools Hub",
        "description": "Research hub for AI productivity, meeting tools, knowledge management, scheduling, and team workflows.",
        "intro": "Productivity tools should reduce coordination cost rather than add another dashboard. This hub focuses on practical workflows, team adoption, and time-saving use cases.",
        "read_when": "Read this hub when you are comparing AI productivity tools for meetings, notes, scheduling, knowledge management, or daily execution.",
        "tokens": {"notion", "reclaim", "meeting", "productivity", "calendar", "workflow"},
    },
    {
        "slug": "marketing",
        "title": "AI Marketing Tools Hub",
        "description": "Research hub for marketing software, ad creative tools, CRM, SEO, email marketing, and conversion workflows.",
        "intro": "Marketing tools should be evaluated by how they support campaigns from research to creative, publishing, follow-up, and measurement.",
        "read_when": "Read this hub when you are building a marketing stack and need to compare tools across SEO, email, CRM, ad creative, and automation.",
        "tokens": {"marketing", "adcreative", "ads", "crm", "seo", "email", "campaign"},
    },
]


def generate_hub_pages(output: Path, offer_scores: pd.DataFrame | None = None) -> list[dict[str, str]]:
    offers = prepare_offers(offer_scores)
    priority_pages = load_priority_pages()
    site_pages = discover_site_pages(output)
    built: list[dict[str, str]] = []
    index_rows: list[dict[str, str]] = []

    for hub in HUBS:
        related = related_content(hub["tokens"], offers, priority_pages, site_pages)
        html_text = render_hub_page(hub, related)
        page_path = write_page(output, f"hub/{hub['slug']}", html_text)
        built.append({"slug": f"hub/{hub['slug']}", "title": hub["title"], "type": "hub_page"})
        index_rows.append(
            {
                "hub_slug": hub["slug"],
                "hub_title": hub["title"],
                "output_path": str(page_path),
                "review_count": len(related["reviews"]),
                "comparison_count": len(related["comparisons"]),
                "priority_page_count": len(related["priority_pages"]),
                "status": "built",
            }
        )

    index_html = render_hub_index(index_rows)
    index_path = write_page(output, "hubs", index_html)
    built.append({"slug": "hubs", "title": "AI Tool Research Hubs", "type": "hub_index"})
    index_rows.insert(
        0,
        {
            "hub_slug": "hubs",
            "hub_title": "AI Tool Research Hubs",
            "output_path": str(index_path),
            "review_count": "",
            "comparison_count": "",
            "priority_page_count": "",
            "status": "built",
        },
    )
    pd.DataFrame(index_rows, columns=HUB_INDEX_COLUMNS).to_csv(settings.data_dir / "hub_pages_index.csv", index=False)
    return built


def prepare_offers(offer_scores: pd.DataFrame | None) -> pd.DataFrame:
    if offer_scores is None or offer_scores.empty:
        return pd.DataFrame(columns=["offer_id", "brand_name", "niche", "total_score", "risk_level", "recommendation"])
    offers = offer_scores.copy().fillna("")
    if "total_score" in offers.columns:
        offers["_sort_score"] = pd.to_numeric(offers["total_score"], errors="coerce").fillna(0)
    else:
        offers["_sort_score"] = 0
    return offers.sort_values("_sort_score", ascending=False)


def load_priority_pages() -> pd.DataFrame:
    path = settings.data_dir / "priority_pages_index.csv"
    if not path.exists():
        return pd.DataFrame(columns=["keyword", "suggested_slug", "title", "status"])
    return pd.read_csv(path).fillna("")


def discover_site_pages(output: Path) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    for path in output.rglob("index.html"):
        rel = path.relative_to(output).as_posix()
        if rel.startswith(("assets/", "go/")):
            continue
        url = "/" if rel == "index.html" else "/" + rel[: -len("index.html")]
        title = extract_title(path.read_text(encoding="utf-8", errors="ignore")) or url.strip("/").replace("-", " ").title()
        pages.append({"url": url, "title": title, "tokens": slug_tokens(url + " " + title)})
    return pages


def related_content(tokens: set[str], offers: pd.DataFrame, priority_pages: pd.DataFrame, site_pages: list[dict[str, str]]) -> dict[str, list]:
    reviews = []
    for _, row in offers.iterrows():
        haystack = slug_tokens(" ".join([str(row.get("offer_id", "")), str(row.get("brand_name", "")), str(row.get("niche", ""))]))
        if tokens & haystack:
            reviews.append(row)
    if not reviews:
        reviews = [row for _, row in offers.head(6).iterrows()]

    priority = []
    for _, row in priority_pages.iterrows():
        if str(row.get("status", "")).lower() != "built":
            continue
        haystack = slug_tokens(" ".join([str(row.get("keyword", "")), str(row.get("suggested_slug", "")), str(row.get("title", ""))]))
        if tokens & haystack:
            priority.append(row)

    comparisons = [page for page in site_pages if page["url"].startswith("/comparisons/") and page["url"] != "/comparisons/" and tokens & page["tokens"]]
    pricing = [page for page in site_pages if page["url"].strip("/").endswith("-pricing") and tokens & page["tokens"]]
    top_lists = [page for page in site_pages if page["url"].strip("/").startswith("best-") and tokens & page["tokens"]]

    return {
        "reviews": reviews[:8],
        "priority_pages": priority[:6],
        "comparisons": comparisons[:8],
        "pricing": pricing[:6],
        "top_lists": top_lists[:4],
    }


def render_hub_page(hub: dict, related: dict[str, list]) -> str:
    slug = f"/hub/{hub['slug']}/"
    title = hub["title"]
    description = hub["description"]
    review_links = render_review_cards(related["reviews"])
    priority_links = render_priority_links(related["priority_pages"])
    comparison_links = render_page_links(related["comparisons"], "Comparison pages")
    pricing_links = render_page_links(related["pricing"], "Pricing research")
    top_list_links = render_page_links(related["top_lists"], "Top lists")
    item_names = [str(row.get("brand_name", "")) for row in related["reviews"] if str(row.get("brand_name", "")).strip()]
    body = f"""
<section class='hero card'>
  <p><a href='/'>Home</a> / <a href='/hubs/'>Research hubs</a></p>
  <h1>{html.escape(title)}</h1>
  <p>{html.escape(hub.get("intro", description))}</p>
  <p>This hub is a topical map for readers comparing tools, pricing pages, alternatives, and reviews. It is built to help you move from broad research to a smaller set of pages worth reading carefully.</p>
</section>
{affiliate_disclosure()}
<section class='card'>
  <h2>When to read this hub</h2>
  <p>{html.escape(hub.get("read_when", "Read this hub when you want a structured path through the topic instead of opening many unrelated review pages."))}</p>
  <p>Start with the money-intent pages, then read individual reviews, then compare tools only after you understand the use case.</p>
  <ul>
    <li>For buyer intent: start with alternatives, pricing, and comparison pages.</li>
    <li>For product fit: read the review pages and workflow notes.</li>
    <li>For affiliate planning: check policy, disclosure, direct linking rules, and trademark bidding terms before creating ads or content.</li>
  </ul>
</section>
<section class='card'>
  <h2>How this hub is organized</h2>
  <p>The hub is arranged as a research path rather than a random directory. The priority pages help with commercial search intent, the review pages explain individual products, and the comparison pages help narrow similar options when the choice is not obvious.</p>
  <p>For a buyer, the practical path is simple: define the workflow, open one priority page, read two or three reviews, then check current pricing and terms on official websites. For an affiliate, the path is slightly different: confirm policy first, avoid fake claims, build a review or comparison page, then measure clicks through tracking links before scaling content or traffic.</p>
  <p>This structure is also useful for SEO because it connects broad topic pages to deeper intent pages. A crawler can move from this hub into reviews, comparisons, pricing pages, and alternatives pages without relying on a single navigation menu.</p>
</section>
<section class='card'>
  <h2>Priority money pages</h2>
  <p>These pages target commercial research queries and should be reviewed before building ads, affiliate content, or deeper comparison articles.</p>
  {priority_links}
</section>
<section class='card'>
  <h2>Reviews in this hub</h2>
  <div class='grid'>{review_links}</div>
</section>
{comparison_links}
{pricing_links}
{top_list_links}
<section class='card'>
  <h2>Evaluation checklist</h2>
  <p>Before choosing a tool from this hub, check whether the product solves a repeated task, whether pricing is clear enough for your expected usage, whether integrations fit the existing workflow, and whether the vendor terms create any issue for affiliate promotion or paid traffic.</p>
  <ul>
    <li><strong>Use case fit:</strong> the tool should solve a real task, not just look impressive in a demo.</li>
    <li><strong>Plan limits:</strong> check seats, usage caps, exports, projects, storage, or generation limits.</li>
    <li><strong>Switching cost:</strong> consider training time, migration effort, and team adoption.</li>
    <li><strong>Policy risk:</strong> check whether direct linking, PPC, coupons, and brand bidding are allowed.</li>
    <li><strong>Measurement:</strong> use tracked CTA links and manual notes so click quality can be reviewed later.</li>
  </ul>
</section>
<section class='card'>
  <h2>Common mistakes to avoid</h2>
  <p>The most common mistake is choosing a tool because it appears in many lists without checking if it fits the workflow. Another mistake is publishing affiliate content before confirming program approval, affiliate disclosure, and traffic rules. Paid traffic adds another layer of risk because some vendors restrict PPC, trademark bidding, direct linking, or coupon promotion.</p>
  <p>For this reason, every hub page should be treated as a map, not as a final verdict. Move from the hub to the review, from the review to the official product page, and from the product page back to your own notes before committing money or publishing promotional content.</p>
</section>
<section class='card'>
  <h2>Next research steps</h2>
  <p>Do not choose a tool only because it appears near the top of a list. Open the relevant review, check current pricing on the official site, compare at least one alternative, and review policy restrictions if you plan to promote the product as an affiliate.</p>
  <p>If a page includes a tracked CTA, it routes through the local tracking page first. If no approved affiliate link exists, the system falls back to the official URL rather than inventing an affiliate link.</p>
</section>
"""
    schemas = [breadcrumb_schema(title, slug), item_list_schema(title, item_names, slug)]
    return shell(title, description, slug, body, schemas)


def render_hub_index(index_rows: list[dict]) -> str:
    cards = "".join(
        f"<article class='card'><h2><a href='/hub/{html.escape(row['hub_slug'])}/'>{html.escape(row['hub_title'])}</a></h2><p>Reviews: {html.escape(str(row['review_count']))} | Comparisons: {html.escape(str(row['comparison_count']))} | Priority pages: {html.escape(str(row['priority_page_count']))}</p><p><a class='btn' href='/hub/{html.escape(row['hub_slug'])}/'>Open hub</a></p></article>"
        for row in index_rows
        if row["hub_slug"] != "hubs"
    )
    body = f"""
<section class='hero card'>
  <p><a href='/'>Home</a></p>
  <h1>AI Tool Research Hubs</h1>
  <p>Topical hubs for AI and SaaS affiliate research. Each hub connects priority pages, reviews, comparisons, pricing pages, and related buying guides.</p>
  <p>Use this page as the central map for the site. The hubs are designed to make research easier for buyers, affiliate publishers, and SEO planning. Each hub connects broad category intent to review pages, comparison pages, pricing checks, and priority money pages.</p>
  <p>The goal is not to send every reader straight to a vendor. The safer workflow is to start with a topic, read the supporting reviews, compare alternatives, verify current pricing, and only then use a tracked CTA when the next step is clear.</p>
</section>
<section class='card'>
  <h2>How to use these hubs</h2>
  <p>If you are buying software, start with the hub closest to your use case and open two or three related pages. If you are building affiliate content, use the hub to find internal link opportunities and to avoid publishing isolated pages that have no topical support.</p>
  <p>Every hub should help answer three questions: what problem is this category solving, which pages should be read next, and what risks should be checked before buying or promoting the tool.</p>
  <p>A practical workflow is to start from one hub, move into a priority page, then read at least one review and one comparison. This creates a more complete picture than jumping straight from a search result to a vendor website. It also helps identify where a tool is strong, where it creates friction, and whether the offer is appropriate for affiliate promotion.</p>
  <p>For SEO planning, hubs also show which parts of the site need more support. If a hub has many reviews but few comparisons, the next content task may be a comparison page. If it has priority pages but weak review coverage, the next task may be a deeper product review. If a hub has several pricing pages, the next task may be a broader buying guide that explains what to check before subscribing.</p>
</section>
<section class='card'>
  <h2>Editorial guardrails</h2>
  <p>The hub system is intentionally conservative. It does not claim that a product is the best choice for everyone, and it does not invent affiliate approval. Links that leave the site route through tracking pages so clicks can be measured, but the destination still depends on real affiliate data or official URLs.</p>
  <p>Before publishing or promoting any page, manually verify the vendor's affiliate terms, current pricing, refund policy, country restrictions, and traffic-source rules. This is especially important for paid ads because PPC, direct linking, and trademark bidding rules can change across programs.</p>
</section>
<section class='grid'>{cards}</section>
<section class='card'>
  <h2>Quality notes</h2>
  <p>These hubs are generated locally from the site's review, keyword, and page index data. They do not call external APIs, do not create fake affiliate links, and do not post content automatically. Before using any page for paid campaigns, verify affiliate approval and current vendor terms manually.</p>
</section>
"""
    schemas = [breadcrumb_schema("AI Tool Research Hubs", "/hubs/")]
    return shell("AI Tool Research Hubs", "Topical hub index for AI and SaaS reviews, comparisons, pricing pages, and affiliate research.", "/hubs/", body, schemas)


def render_review_cards(rows: list[pd.Series]) -> str:
    if not rows:
        return "<p>No matching reviews yet. Check the broader review index for more tools.</p>"
    cards = []
    for row in rows:
        brand = str(row.get("brand_name", "")).strip()
        offer_id = str(row.get("offer_id", "")).strip()
        niche = str(row.get("niche", "SaaS")).strip()
        score = str(row.get("total_score", "Research")).strip()
        cards.append(
            f"<article class='card'><h3>{html.escape(brand)}</h3><p>{html.escape(niche)} research and workflow review.</p><p><strong>Score:</strong> {html.escape(score)}</p><p><a class='btn secondary' href='/{html.escape(offer_id)}/'>Read review</a><a class='btn' href='/go/{html.escape(offer_id)}/?src=/hubs/&cta=hub_page'>Visit Official Website</a></p></article>"
        )
    return "".join(cards)


def render_priority_links(rows: list[pd.Series]) -> str:
    if not rows:
        return "<p>No dedicated priority page has been generated for this hub yet.</p>"
    items = "".join(
        f"<li><a href='/{html.escape(str(row.get('suggested_slug', '')).strip('/'))}/'>{html.escape(str(row.get('title', '') or row.get('keyword', 'Priority page')))}</a></li>"
        for row in rows
    )
    return f"<ul>{items}</ul>"


def render_page_links(pages: list[dict[str, str]], heading: str) -> str:
    if not pages:
        return ""
    links = "".join(f"<li><a href='{html.escape(page['url'])}'>{html.escape(clean_title(page['title']))}</a></li>" for page in pages)
    return f"<section class='card'><h2>{html.escape(heading)}</h2><ul>{links}</ul></section>"


def extract_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return clean_title(re.sub(r"\s+", " ", html.unescape(match.group(1))).strip())


def clean_title(title: str) -> str:
    return title.replace(f" - {settings.site_name}", "").strip()


def slug_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", str(text).lower()))
    normalized = set(tokens)
    if "copy" in tokens and "ai" in tokens:
        normalized.add("copy-ai")
    if "github" in tokens and "copilot" in tokens:
        normalized.add("github-copilot")
    if "surfer" in tokens and "seo" in tokens:
        normalized.add("surfer-seo")
    return {token for token in normalized if len(token) > 1 and token not in {"ai", "tool", "tools", "review", "reviews", "best", "pricing", "vs"}}
