from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

from config import settings
from modules.indexing_policy import INDEXABLE_ROBOTS_META


BASE_URL = "https://smileaireviewhub.com"


@dataclass(frozen=True)
class HubConfig:
    slug: str
    title: str
    meta: str
    intro: str
    keywords: tuple[str, ...]
    related_hubs: tuple[str, ...]


@dataclass
class PageCandidate:
    url: str
    title: str
    kind: str
    tokens: set[str]
    mtime: float


HUBS = [
    HubConfig(
        "ai-coding-tools",
        "AI Coding Tools",
        "Compare AI coding tools, developer assistants, code review helpers, and workflow automation for software teams.",
        "AI coding tools are useful only when they improve the real development loop: reading existing code, editing safely, debugging, reviewing pull requests, and respecting team policy. This hub groups practical reviews, comparisons, pricing notes, and workflow guides for developers evaluating coding assistants. Use it to shortlist tools by repository context, autocomplete quality, debugging support, privacy needs, and total switching cost before committing a team workflow.",
        ("ai", "coding", "code", "developer", "cursor", "windsurf", "copilot", "replit", "bolt"),
        ("ai-agents", "ai-productivity-tools", "ai-automation"),
    ),
    HubConfig(
        "ai-seo-tools",
        "AI SEO Tools",
        "Research AI SEO tools for keyword research, content optimization, site audits, rank tracking, and SEO workflows.",
        "AI SEO tools can speed up research, content briefs, optimization, technical audits, and reporting, but the best choice depends on workflow fit rather than a feature checklist. This hub connects reviews, pricing pages, alternatives, and comparisons for SEO software buyers. It is designed for creators, agencies, and business owners who want practical checks around keyword research, content optimization, backlink data, rank tracking, and pricing risk.",
        ("ai", "seo", "surfer", "semrush", "ahrefs", "frase", "clearscope", "keyword"),
        ("ai-writing-tools", "ai-productivity-tools", "ai-automation"),
    ),
    HubConfig(
        "ai-video-tools",
        "AI Video Tools",
        "Compare AI video tools for scripts, voiceovers, subtitles, avatars, editing, shorts, and YouTube workflows.",
        "AI video tools are becoming part of content operations, but production quality still depends on planning, editing, subtitles, and review. This hub helps compare tools for video generation, avatar videos, script support, voiceover workflows, subtitle quality, and YouTube packaging. It focuses on practical use cases for creators and small teams that need repeatable video output without losing brand control.",
        ("ai", "video", "youtube", "synthesia", "runway", "descript", "pictory", "subtitle"),
        ("ai-writing-tools", "ai-productivity-tools", "ai-automation"),
    ),
    HubConfig(
        "ai-writing-tools",
        "AI Writing Tools",
        "Explore AI writing assistants, content tools, editing software, brand voice systems, and copywriting workflows.",
        "AI writing tools are most valuable when they help with research, outlining, drafting, editing, and repurposing content without making every page sound generic. This hub links to reviews and comparisons for writers, marketers, founders, and creators who need better drafts, brand voice control, SEO support, and practical editing workflows. Pricing and output quality should always be verified in the current product before buying.",
        ("ai", "writing", "writer", "jasper", "copy", "grammarly", "wordtune", "content"),
        ("ai-seo-tools", "ai-productivity-tools", "ai-video-tools"),
    ),
    HubConfig(
        "ai-productivity-tools",
        "AI Productivity Tools",
        "Research AI productivity tools for teams, creators, workflows, meetings, search, notes, and daily operations.",
        "AI productivity tools cover a wide range of workflows: notes, search, writing, meetings, task planning, dashboards, and automation. This hub is built to help users compare practical fit across daily work instead of chasing every new release. Start here when you want to understand which tools can save time, which ones add complexity, and which reviews or comparisons deserve a closer look.",
        ("ai", "productivity", "assistant", "notion", "reclaim", "perplexity", "workflow"),
        ("ai-agents", "ai-automation", "ai-writing-tools"),
    ),
    HubConfig(
        "ai-agents",
        "AI Agents",
        "Learn how AI agents fit into automation, coding, research, marketing, and business workflows.",
        "AI agents are useful when they can reliably complete multi-step work with guardrails, context, and review checkpoints. This hub groups agent-related reviews, workflow guides, and comparisons for people evaluating autonomous or semi-autonomous systems. The goal is to separate practical agent workflows from hype and help buyers check reliability, integrations, security, and human oversight.",
        ("ai", "agent", "agents", "automation", "workflow", "coding", "assistant"),
        ("ai-coding-tools", "ai-automation", "ai-productivity-tools"),
    ),
    HubConfig(
        "ai-automation",
        "AI Automation",
        "Compare AI automation tools, workflow builders, integrations, task routing, and SaaS operations software.",
        "AI automation is most useful when it connects repeatable tasks across apps without creating hidden maintenance work. This hub covers automation tools, workflow builders, AI assistants, CRM/email automation, and related SaaS comparisons. Use it to evaluate integrations, pricing triggers, error handling, handoff logic, and where human review should remain in the workflow.",
        ("ai", "automation", "workflow", "zapier", "make", "activecampaign", "hubspot"),
        ("ai-agents", "ai-productivity-tools", "ai-seo-tools"),
    ),
]


def write_topical_hubs(output: Path) -> dict[str, int]:
    output = Path(output)
    pages = discover_pages(output)
    written = 0
    for hub in HUBS:
        target = output / hub.slug / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_hub(hub, pages), encoding="utf-8")
        written += 1
    return {"topical_hubs_written": written}


def discover_pages(output: Path) -> list[PageCandidate]:
    pages: list[PageCandidate] = []
    for file in sorted(output.rglob("index.html")):
        rel = file.relative_to(output).as_posix()
        if rel.startswith(("assets/", "go/")):
            continue
        url = "/" if rel == "index.html" else "/" + rel[: -len("index.html")]
        text = file.read_text(encoding="utf-8", errors="ignore")
        if "noindex" in robots_content(text).lower():
            continue
        title = extract_title(text) or url.strip("/").replace("-", " ").title()
        pages.append(PageCandidate(url=url, title=clean_title(title), kind=classify(url), tokens=tokens(f"{url} {title}"), mtime=file.stat().st_mtime))
    return pages


def render_hub(hub: HubConfig, pages: list[PageCandidate]) -> str:
    base = (settings.base_site_url or settings.site_domain or BASE_URL).rstrip("/")
    canonical = f"{base}/{hub.slug}/"
    matched = rank_pages(hub, pages)
    reviews = cards([p for p in matched if p.kind == "review"][:8])
    comparisons = cards([p for p in matched if p.kind == "comparison"][:6])
    tutorials = cards([p for p in matched if p.kind in {"blog", "tutorial", "guide"}][:6])
    latest = cards(sorted(matched, key=lambda p: p.mtime, reverse=True)[:6])
    related = "".join(
        f"<li><a href='/{html.escape(slug)}/'>{html.escape(title_for_hub(slug))}</a></li>"
        for slug in hub.related_hubs
    )
    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": hub.title,
        "description": hub.meta,
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": settings.site_name, "url": f"{base}/"},
        "publisher": {"@type": "Organization", "name": settings.site_name, "url": f"{base}/"},
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": p.title, "url": f"{base}{p.url}"}
                for i, p in enumerate(matched[:12])
            ],
        },
    }
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(hub.title)} | {html.escape(settings.site_name)}</title>
<meta name="description" content="{html.escape(hub.meta, quote=True)}">
<meta name="robots" content="{INDEXABLE_ROBOTS_META}">
<link rel="canonical" href="{html.escape(canonical, quote=True)}">
<link rel="alternate" type="application/rss+xml" title="{html.escape(settings.site_name)} RSS" href="{base}/rss.xml">
<meta property="og:title" content="{html.escape(hub.title, quote=True)}">
<meta property="og:description" content="{html.escape(hub.meta, quote=True)}">
<meta property="og:url" content="{html.escape(canonical, quote=True)}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>{css()}</style>
</head>
<body>
<nav><div class="wrap"><a class="logo" href="/">{html.escape(settings.site_name)}</a><a href="/reviews/">Reviews</a><a href="/comparisons/">Comparisons</a><a href="/categories/">Categories</a><a href="/contact/">Contact</a></div></nav>
<main class="wrap">
<header class="hero"><p class="eyebrow">AI software research hub</p><h1>{html.escape(hub.title)}</h1><p>{html.escape(hub.intro)}</p></header>
<section class="card"><h2>Latest reviews</h2><div class="grid">{reviews or empty_state()}</div></section>
<section class="card"><h2>Tutorials and guides</h2><div class="grid">{tutorials or empty_state()}</div></section>
<section class="card"><h2>Comparisons</h2><div class="grid">{comparisons or empty_state()}</div></section>
<section class="card"><h2>Recently updated</h2><div class="grid">{latest or empty_state()}</div></section>
<section class="card"><h2>Related hubs</h2><ul>{related}</ul></section>
</main>
<footer><div class="wrap"><p><strong>{html.escape(settings.site_name)}</strong></p><p>Contact: <a href="mailto:{html.escape(settings.contact_email, quote=True)}">{html.escape(settings.contact_email)}</a></p></div></footer>
</body>
</html>
"""


def rank_pages(hub: HubConfig, pages: list[PageCandidate]) -> list[PageCandidate]:
    hub_tokens = set(hub.keywords)
    scored: list[tuple[int, float, str, PageCandidate]] = []
    for page in pages:
        if page.url == f"/{hub.slug}/" or page.url.startswith("/vi/"):
            continue
        score = len(page.tokens & hub_tokens) * 5
        if page.kind in {"review", "comparison", "toplist", "category", "pricing", "blog"}:
            score += 2
        if score > 0:
            scored.append((score, page.mtime, page.title, page))
    scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [page for _, _, _, page in scored[:30]]


def cards(items: list[PageCandidate]) -> str:
    return "".join(
        f"<article class='mini-card'><h3>{html.escape(item.title)}</h3><p>{html.escape(description_for(item))}</p><a href='{html.escape(item.url)}'>Open guide</a></article>"
        for item in items
    )


def empty_state() -> str:
    return "<p class='muted'>Related pages will appear here as the library grows.</p>"


def description_for(item: PageCandidate) -> str:
    if item.kind == "review":
        return "Review, pricing notes, alternatives, and buyer-fit checks."
    if item.kind == "comparison":
        return "Side-by-side comparison for practical shortlisting."
    if item.kind == "pricing":
        return "Pricing research and plan verification notes."
    if item.kind == "blog":
        return "Workflow guide and practical research notes."
    return "Related research from Smile AI Review Hub."


def title_for_hub(slug: str) -> str:
    for hub in HUBS:
        if hub.slug == slug:
            return hub.title
    return slug.replace("-", " ").title()


def extract_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip() if match else ""


def clean_title(title: str) -> str:
    return re.sub(r"\s+\|\s+MS Smile AI Review Hub$", "", title).replace(" - MS Smile AI Review Hub", "").strip()


def robots_content(text: str) -> str:
    match = re.search(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])[^>]*\bcontent=['\"]([^'\"]+)['\"]", text, flags=re.I)
    return match.group(1) if match else ""


def classify(url: str) -> str:
    if url.startswith("/review/") or url.startswith("/reviews/") or "-review-" in url:
        return "review"
    if url.startswith("/compare/") or url.startswith("/comparisons/") or "-vs-" in url:
        return "comparison"
    if url.startswith("/blog/"):
        return "blog"
    if "tutorial" in url or "how-to" in url:
        return "tutorial"
    if url.startswith("/pricing/") or url.rstrip("/").endswith("-pricing"):
        return "pricing"
    if url.startswith("/category/") or url.startswith("/categories/"):
        return "category"
    if url.rstrip("/").split("/")[-1].startswith("best-"):
        return "toplist"
    return "page"


def tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}


def css() -> str:
    return """*{box-sizing:border-box}body{margin:0;background:#f7f9fc;color:#17202a;font-family:Arial,Helvetica,sans-serif;line-height:1.65}.wrap{max-width:1120px;margin:auto;padding:0 20px}nav{background:#fff;border-bottom:1px solid #dbe3ef}.logo{font-weight:800;color:#0f172a}nav .wrap{min-height:64px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}nav a,footer a{color:#0f766e;text-decoration:none;font-weight:700}.hero{padding:48px 0}.eyebrow{color:#0f766e;font-weight:800}.hero h1{font-size:42px;line-height:1.1;margin:8px 0}.card{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:20px;margin:18px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}.mini-card{border:1px solid #dbeafe;border-radius:8px;background:#f8fbff;padding:14px}.mini-card h3{font-size:17px;margin:0 0 7px}.mini-card p,.muted{color:#596579}.mini-card a{font-weight:800;color:#0f766e;text-decoration:none}footer{margin-top:36px;background:#0f172a;color:#cbd5e1;padding:28px 0}footer p{color:#cbd5e1}@media(max-width:720px){.hero h1{font-size:32px}nav .wrap{padding-top:12px;padding-bottom:12px}}"""
