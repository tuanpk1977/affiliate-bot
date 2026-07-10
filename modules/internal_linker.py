from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from config import settings


TOOL_ALIASES = {
    "copyai": "copy-ai",
    "copilot": "github-copilot",
    "webflow": "webflow-ai",
    "pipedrive-crm": "pipedrive",
}

STOPWORDS = {
    "ai",
    "tool",
    "tools",
    "review",
    "reviews",
    "features",
    "pros",
    "cons",
    "pricing",
    "notes",
    "best",
    "which",
    "should",
    "choose",
    "what",
    "check",
    "before",
    "buying",
    "hub",
    "saas",
}

CATEGORY_KEYWORDS = {
    "ai-coding": {"cursor", "github", "copilot", "windsurf", "vscode", "tabnine", "coding", "code"},
    "ai-seo": {"semrush", "ahrefs", "surfer", "seo"},
    "ai-automation": {"make", "zapier", "automation"},
    "ai-presentation": {"gamma", "canva", "presentation"},
    "ai-voice": {"elevenlabs", "murf", "playht", "voice"},
    "ai-video": {"runway", "pika", "synthesia", "heygen", "descript", "video"},
    "crm": {"hubspot", "pipedrive", "salesforce", "crm"},
    "website-builders": {"framer", "webflow", "durable", "website", "builder"},
    "ai-writing": {"jasper", "copy", "copyai", "notion", "chatgpt", "claude", "writing"},
}


@dataclass
class PageInfo:
    path: Path
    url: str
    slug: str
    title: str
    kind: str
    tokens: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)


def post_process_internal_links(output: Path) -> dict[str, int]:
    pages = discover_pages(output)
    if not pages:
        return {"pages": 0, "links_added": 0}

    footer_links = seo_footer_links(pages)
    links_added = 0
    pages_updated = 0
    for page in pages:
        if page.kind in {"asset", "tracking"}:
            continue
        text = page.path.read_text(encoding="utf-8", errors="ignore")
        text = remove_previous_block(text)
        if not is_canonical_article(text):
            related = related_for_page(page, pages)
            block = related_block(page, related)
            if block:
                text = inject_before_footer(text, block)
                links_added += block.count("<a ")
            text = inject_seo_footer(text, footer_links, page.url)
        text = ensure_breadcrumb_schema(text, page)
        text = ensure_visible_breadcrumb(text, page)
        text = ensure_sticky_toc(text, page)
        text = ensure_go_link_attributes(text)
        page.path.write_text(text, encoding="utf-8")
        pages_updated += 1
    return {"pages": pages_updated, "links_added": links_added}


def discover_pages(output: Path) -> list[PageInfo]:
    pages: list[PageInfo] = []
    for file in sorted(output.rglob("index.html")):
        rel = file.relative_to(output).as_posix()
        if rel.startswith("assets/"):
            continue
        url = "/" if rel == "index.html" else "/" + rel[: -len("index.html")]
        slug = url.strip("/").split("/")[-1] if url != "/" else "home"
        text = file.read_text(encoding="utf-8", errors="ignore")
        title = extract_title(text) or slug.replace("-", " ").title()
        tokens = token_set(slug + " " + title)
        kind = classify(url, slug)
        pages.append(PageInfo(file, url, slug, title, kind, tokens, categories_for(tokens)))
    return pages


def classify(url: str, slug: str) -> str:
    if url == "/":
        return "home"
    if url.startswith("/go/"):
        return "tracking"
    if url.startswith("/review/"):
        return "review"
    if url.startswith("/compare/"):
        return "comparison"
    if url.startswith("/comparisons/") and slug != "comparisons":
        return "comparison"
    if url.startswith("/blog/") and slug != "blog":
        return "blog"
    if url.startswith("/hub/"):
        return "hub"
    if slug == "hubs":
        return "hub_index"
    if url.startswith("/pricing/"):
        return "pricing"
    if slug.endswith("-pricing"):
        return "pricing"
    if slug.startswith("best-"):
        return "toplist"
    if url.startswith("/category/"):
        return "category"
    static = {
        "reviews",
        "comparisons",
        "about",
        "about-author",
        "author-profile",
        "editorial-policy",
        "how-we-review-tools",
        "testing-methodology",
        "privacy-policy",
        "terms",
        "contact",
        "affiliate-disclosure",
        "sitemap",
        "media-kit",
        "aeo-action-plan",
        "blog",
    }
    if slug in static:
        return "static"
    return "review"


def related_for_page(page: PageInfo, pages: list[PageInfo]) -> dict[str, list[PageInfo]]:
    candidates = [item for item in pages if item.url != page.url and item.kind not in {"asset", "home", "tracking"}]
    if not page.url.startswith("/vi/"):
        candidates = [item for item in candidates if not item.url.startswith("/vi/") and not contains_vietnamese_label(item.title)]
    if page.kind == "review":
        return {
            "Popular reviews": rank(page, candidates, {"review"}, 5),
            "Popular comparisons": rank(page, candidates, {"comparison"}, 5),
            "Top categories": rank(page, candidates, {"toplist", "category", "hub"}, 5),
        }
    if page.kind == "comparison":
        return {
            "Related reviews": rank(page, candidates, {"review"}, 4),
            "Pricing pages": rank(page, candidates, {"pricing"}, 4),
            "Best category pages": rank(page, candidates, {"toplist", "category"}, 4),
            "Related comparisons": rank(page, candidates, {"comparison"}, 4),
        }
    if page.kind == "pricing":
        return {
            "Review": rank(page, candidates, {"review"}, 3),
            "Alternatives": rank(page, candidates, {"review"}, 4),
            "Related comparisons": rank(page, candidates, {"comparison"}, 4),
            "Best category page": rank(page, candidates, {"toplist", "category"}, 3),
        }
    if page.kind == "toplist":
        return {
            "Reviews in this category": rank(page, candidates, {"review"}, 8),
            "Comparison pages": rank(page, candidates, {"comparison"}, 6),
            "Pricing pages": rank(page, candidates, {"pricing"}, 6),
        }
    if page.kind == "category":
        return {
            "Related reviews": rank(page, candidates, {"review"}, 8),
            "Related comparisons": rank(page, candidates, {"comparison"}, 6),
            "Related pricing pages": rank(page, candidates, {"pricing"}, 6),
            "Related hubs": rank(page, candidates, {"hub", "toplist"}, 4),
        }
    if page.kind in {"hub", "hub_index"}:
        return {
            "Priority pages": rank(page, candidates, {"review"}, 4),
            "Related comparisons": rank(page, candidates, {"comparison"}, 5),
            "Pricing research": rank(page, candidates, {"pricing"}, 4),
            "Top lists": rank(page, candidates, {"toplist", "category"}, 4),
        }
    return {
        "Popular reviews": rank(page, candidates, {"review"}, 4),
        "Popular comparisons": rank(page, candidates, {"comparison"}, 4),
        "Top categories": rank(page, candidates, {"toplist", "category", "hub"}, 4),
    }


def rank(page: PageInfo, candidates: list[PageInfo], kinds: set[str], limit: int) -> list[PageInfo]:
    scored = []
    for item in candidates:
        if item.kind not in kinds:
            continue
        score = len(page.tokens & item.tokens) * 4 + len(page.categories & item.categories) * 3
        if page.kind == "comparison" and item.kind == "review":
            score += len(extract_tool_tokens(page.slug) & item.tokens) * 8
        if page.kind == "review" and item.kind in {"comparison", "pricing"}:
            score += len(extract_tool_tokens(item.slug) & page.tokens) * 8
        if score <= 0 and item.kind in {"toplist", "category"} and page.categories & item.categories:
            score = 2
        if score > 0:
            scored.append((score, item.title, item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in scored[:limit]]


def related_block(page: PageInfo, groups: dict[str, list[PageInfo]]) -> str:
    sections = []
    seen: set[str] = {page.url}
    for label, items in groups.items():
        links = []
        for item in items:
            if item.url in seen:
                continue
            seen.add(item.url)
            title = html.escape(clean_title(item.title))
            description = html.escape(related_description(item))
            links.append(f"<article class='related-card'><h3>{title}</h3><p>{description}</p><a href='{html.escape(item.url)}'>Read guide</a></article>")
        if links:
            sections.append(f"<div class='related-card-section'><h3>{html.escape(label)}</h3><div class='related-grid'>{''.join(links)}</div></div>")
    if not sections:
        return ""
    return "\n<section class='article-card article-section internal-links related-research' data-auto-internal-links='1'><h2>Related research</h2>" + "".join(sections) + "</section>\n"


def related_description(item: PageInfo) -> str:
    if item.kind == "review":
        return "Review notes, pricing checks, alternatives, and buyer-fit signals."
    if item.kind == "comparison":
        return "Side-by-side research to help shortlist tools before clicking out."
    if item.kind == "pricing":
        return "Pricing and plan checks to verify before buying or promoting."
    if item.kind in {"toplist", "category", "hub"}:
        return "Category research with practical tool options and buying checks."
    return "Related AI tool research from SmileAIReviewHub."


def seo_footer_links(pages: list[PageInfo]) -> dict[str, list[PageInfo]]:
    pages = [p for p in pages if not p.url.startswith("/vi/") and not contains_vietnamese_label(p.title)]
    return {
        "Popular reviews": [p for p in pages if p.kind == "review"][:6],
        "Popular comparisons": [p for p in pages if p.kind == "comparison"][:6],
        "Pricing pages": [p for p in pages if p.kind == "pricing"][:6],
        "Top categories": [p for p in pages if p.kind in {"toplist", "category", "hub"}][:6],
    }


def inject_seo_footer(text: str, groups: dict[str, list[PageInfo]], current_url: str) -> str:
    text = re.sub(r"<section class=['\"]seo-footer-links['\"].*?</section>", "", text, flags=re.DOTALL)
    blocks = []
    for label, items in groups.items():
        links = "".join(f"<li><a href='{html.escape(item.url)}'>{html.escape(clean_title(item.title))}</a></li>" for item in items if item.url != current_url)
        if links:
            blocks.append(f"<div><h3>{html.escape(label)}</h3><ul>{links}</ul></div>")
    if not blocks:
        return text
    block = "<section class='seo-footer-links'><div class='wrap grid'>" + "".join(blocks) + "</div></section>"
    return text.replace("<footer", block + "\n<footer", 1)


def ensure_breadcrumb_schema(text: str, page: PageInfo) -> str:
    if page.kind not in {"review", "comparison", "pricing", "toplist", "category", "hub"} or '"@type": "BreadcrumbList"' in text:
        return text
    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{base}/"},
            {"@type": "ListItem", "position": 2, "name": clean_title(page.title), "item": f"{base}{page.url}"},
        ],
    }
    script = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'
    return text.replace("</head>", script + "</head>", 1)


def ensure_visible_breadcrumb(text: str, page: PageInfo) -> str:
    if page.kind not in {"review", "comparison", "pricing", "toplist", "category", "hub"}:
        return text
    if "data-auto-breadcrumb=\"1\"" in text or "data-auto-breadcrumb='1'" in text:
        return text
    if re.search(r"<nav\b[^>]*class=['\"][^'\"]*\b(?:breadcrumb|breadcrumbs)\b[^'\"]*['\"]", text, flags=re.IGNORECASE):
        return text
    parent_label = {
        "review": "Reviews",
        "comparison": "Comparisons",
        "pricing": "Pricing",
        "toplist": "Best Tools",
        "category": "Categories",
        "hub": "Hubs",
    }.get(page.kind, "Research")
    parent_url = {
        "review": "/reviews/",
        "comparison": "/comparisons/",
        "pricing": "/pricing/",
        "toplist": "/categories/",
        "category": "/categories/",
        "hub": "/hubs/",
    }.get(page.kind, "/")
    crumb = (
        f"<nav class='breadcrumbs' data-auto-breadcrumb='1' aria-label='Breadcrumb'>"
        f"<a href='/'>Home</a> / <a href='{html.escape(parent_url)}'>{html.escape(parent_label)}</a> / "
        f"<span>{html.escape(clean_title(page.title))}</span></nav>"
    )
    main_match = re.search(r"(<main\b[^>]*>)", text, flags=re.IGNORECASE)
    if main_match:
        return text[: main_match.end()] + crumb + text[main_match.end() :]
    return crumb + text


def ensure_sticky_toc(text: str, page: PageInfo) -> str:
    if page.kind not in {"review", "comparison", "pricing", "toplist", "category", "hub"}:
        return text
    if has_existing_toc(text):
        return text
    if "data-auto-toc=\"1\"" in text or "data-auto-toc='1'" in text:
        return text
    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", text, flags=re.IGNORECASE | re.DOTALL)
    clean_headings = [re.sub(r"<[^>]+>", "", html.unescape(item)).strip() for item in headings]
    clean_headings = [item for item in clean_headings if item and item.lower() not in {"related research"}]
    if len(clean_headings) < 5:
        return text
    links = []
    updated = text
    for heading in clean_headings[:10]:
        anchor = slugify_fragment(heading)
        pattern = re.compile(rf"(<h2)([^>]*)(>{re.escape(heading)}</h2>)", flags=re.IGNORECASE)
        if f'id="{anchor}"' not in updated and pattern.search(updated):
            updated = pattern.sub(rf'\1 id="{anchor}"\2\3', updated, count=1)
        links.append(f"<a href='#{html.escape(anchor)}'>{html.escape(heading)}</a>")
    toc = "<section class='article-card toc-links auto-toc-block' data-auto-toc='1'><h2>Contents</h2>" + "".join(links) + "</section>"
    main_match = re.search(r"(<main\b[^>]*>)", updated, flags=re.IGNORECASE)
    if main_match:
        return updated[: main_match.end()] + toc + updated[main_match.end() :]
    return toc + updated


def has_existing_toc(text: str) -> bool:
    toc_markers = [
        "class=\"card toc\"",
        "class='card toc'",
        "class=\"toc card\"",
        "class='toc card'",
        "class=\"table-of-contents\"",
        "class='table-of-contents'",
        "class=\"article-card toc-links\"",
        "class='article-card toc-links'",
        "review-layout",
    ]
    return any(marker in text for marker in toc_markers)


def ensure_go_link_attributes(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if re.search(r"\brel=", tag, flags=re.IGNORECASE):
            return re.sub(r"\brel=(['\"])(.*?)\1", lambda rel: f'rel={rel.group(1)}{merge_rel(rel.group(2))}{rel.group(1)}', tag, count=1, flags=re.IGNORECASE)
        return tag[:-1] + ' rel="nofollow sponsored">'

    return re.sub(r"<a\b(?=[^>]*href=['\"]/go/)[^>]*>", repl, text, flags=re.IGNORECASE)


def merge_rel(value: str) -> str:
    tokens = set(str(value or "").split())
    tokens.update({"nofollow", "sponsored", "noopener", "noreferrer"})
    return " ".join(sorted(tokens))


def is_canonical_article(text: str) -> bool:
    return "article-layout" in text and ("article-container" in text or "/assets/article.css" in text)


def contains_vietnamese_label(text: str) -> bool:
    lowered = html.unescape(str(text or "")).lower()
    markers = (
        "đánh giá",
        "giá",
        "lựa chọn",
        "những điểm",
        "kiểm tra trước khi mua",
        "thay thế",
        "Ä",
        "giã",
    )
    return any(marker.lower() in lowered for marker in markers)


def slugify_fragment(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "section"


def inject_before_footer(text: str, block: str) -> str:
    if "<footer" in text:
        return text.replace("<footer", block + "<footer", 1)
    if "</main>" in text:
        return text.replace("</main>", block + "</main>", 1)
    return text + block


def remove_previous_block(text: str) -> str:
    return re.sub(r"\n?<section class=['\"][^'\"]*\binternal-links\b[^'\"]*['\"] data-auto-internal-links=['\"]1['\"].*?</section>\n?", "", text, flags=re.DOTALL)


def extract_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()


def clean_title(title: str) -> str:
    return title.replace(f" - {settings.site_name}", "").strip()


def token_set(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    normalized = set(tokens)
    for token in list(tokens):
        normalized.add(TOOL_ALIASES.get(token, token))
    if "copy" in tokens and "ai" in tokens:
        normalized.add("copy-ai")
    if "github" in tokens and "copilot" in tokens:
        normalized.add("github-copilot")
    if "surfer" in tokens and "seo" in tokens:
        normalized.add("surfer-seo")
    return {token for token in normalized if len(token) > 1 and token not in STOPWORDS}


def extract_tool_tokens(slug: str) -> set[str]:
    tokens = token_set(slug)
    return {token for token in tokens if token not in {"vs", "pricing", "best", "tools", "ai"}}


def categories_for(tokens: set[str]) -> set[str]:
    categories = set()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if tokens & keywords:
            categories.add(category)
    return categories
