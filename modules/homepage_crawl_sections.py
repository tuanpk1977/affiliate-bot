from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PageItem:
    url: str
    title: str
    kind: str
    text: str
    mtime: float


def enrich_homepage_crawl_sections(output: Path) -> dict[str, int]:
    output = Path(output)
    home = output / "index.html"
    if not home.exists():
        return {"homepage_crawl_sections": 0}
    pages = discover_pages(output)
    if not pages:
        return {"homepage_crawl_sections": 0}
    source = home.read_text(encoding="utf-8", errors="ignore")
    source = remove_existing(source)
    block = render_sections(pages)
    if "</main>" in source:
        source = source.replace("</main>", block + "\n</main>", 1)
    elif "<footer" in source:
        source = source.replace("<footer", block + "\n<footer", 1)
    else:
        source += block
    home.write_text(source, encoding="utf-8")
    return {"homepage_crawl_sections": 1}


def discover_pages(output: Path) -> list[PageItem]:
    pages: list[PageItem] = []
    for file in sorted(output.rglob("index.html")):
        rel = file.relative_to(output).as_posix()
        if rel == "index.html" or rel.startswith(("assets/", "go/", "vi/")):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        if "noindex" in robots_content(text).lower():
            continue
        url = "/" + rel[: -len("index.html")]
        title = clean_title(extract_title(text) or url.strip("/").replace("-", " ").title())
        pages.append(PageItem(url=url, title=title, kind=classify(url), text=f"{url} {title}".lower(), mtime=file.stat().st_mtime))
    return pages


def render_sections(pages: list[PageItem]) -> str:
    recent = sorted(pages, key=lambda item: item.mtime, reverse=True)
    sections = [
        ("Latest AI Reviews", [p for p in recent if p.kind == "review"][:6]),
        ("Latest Tutorials", [p for p in recent if p.kind in {"blog", "tutorial"}][:6]),
        ("Trending AI Tools", keyword_pages(recent, ("ai", "tools", "review"))[:6]),
        ("AI Coding Tools", keyword_pages(recent, ("coding", "cursor", "windsurf", "copilot", "developer"))[:6]),
        ("AI SEO Tools", keyword_pages(recent, ("seo", "surfer", "semrush", "ahrefs", "frase"))[:6]),
        ("AI Video Tools", keyword_pages(recent, ("video", "youtube", "synthesia", "runway", "descript"))[:6]),
        ("Recently Updated", recent[:6]),
    ]
    cards = "".join(section_card(title, items) for title, items in sections if items)
    return "\n<!-- auto-homepage-crawl:start -->\n<section class='card homepage-crawl-sections' data-auto-homepage-crawl='1'><h2>Explore AI Tool Research</h2><div class='grid'>" + cards + "</div></section>\n<!-- auto-homepage-crawl:end -->\n"


def section_card(title: str, items: list[PageItem]) -> str:
    links = "".join(f"<li><a href='{html.escape(item.url)}'>{html.escape(item.title)}</a></li>" for item in items)
    return f"<section class='mini-card'><h3>{html.escape(title)}</h3><ul>{links}</ul></section>"


def keyword_pages(pages: list[PageItem], keywords: tuple[str, ...]) -> list[PageItem]:
    matched = []
    for page in pages:
        score = sum(1 for keyword in keywords if keyword in page.text)
        if score:
            matched.append((score, page.mtime, page))
    matched.sort(key=lambda row: (-row[0], -row[1], row[2].title))
    return [page for _, _, page in matched]


def remove_existing(text: str) -> str:
    text = re.sub(
        r"\n?<!-- auto-homepage-crawl:start -->.*?<!-- auto-homepage-crawl:end -->\n?",
        "",
        text,
        flags=re.I | re.S,
    )
    start = text.find("<section class='card homepage-crawl-sections'")
    if start == -1:
        start = text.find('<section class="card homepage-crawl-sections"')
    if start != -1:
        end = text.find("</div></section>", start)
        if end != -1:
            text = text[:start] + text[end + len("</div></section>") :]
    legacy_start = text.find("<section class='mini-card'><h3>Latest Tutorials</h3>")
    if legacy_start != -1:
        legacy_end = text.find("</div></section>", legacy_start)
        if legacy_end != -1:
            text = text[:legacy_start] + text[legacy_end + len("</div></section>") :]
    return text


def extract_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).strip() if match else ""


def clean_title(title: str) -> str:
    return re.sub(r"\s+[-|]\s+MS Smile AI Review Hub$", "", title).strip()


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
    return "page"
