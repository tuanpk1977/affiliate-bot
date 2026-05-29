from __future__ import annotations

import html
import json
import re
from pathlib import Path

from config import settings
from modules.site_builder import analytics_snippet, base_css, base_schemas, footer_html, nav_html, site_url


BASE_URL = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")


def publish_markdown_articles() -> list[Path]:
    """Publish approved local markdown content into the static site output."""
    root = settings.base_dir / "content" / "comparisons"
    if not root.exists():
        return []
    published: list[Path] = []
    for source in sorted(root.glob("*.md")):
        page = publish_comparison_markdown(source)
        if page:
            published.append(page)
    return published


def publish_comparison_markdown(source: Path) -> Path | None:
    raw = source.read_text(encoding="utf-8")
    meta = extract_markdown_meta(raw)
    slug = meta.get("slug") or source.stem
    title = meta.get("seo_title") or meta.get("h1") or slug.replace("-", " ").title()
    description = meta.get("meta_description") or f"Practical comparison guide for {title}."
    canonical_path = f"/comparisons/{slug}/"
    canonical = f"{BASE_URL}{canonical_path}"
    body_markdown = strip_meta_lines(raw)
    article_html = markdown_to_html(body_markdown)
    faq_items = extract_faq_items(body_markdown)
    related_html = related_links_html()
    breadcrumb_html = (
        "<nav class='breadcrumb'>"
        "<a href='/'>Home</a> / <a href='/comparisons/'>Comparisons</a> / "
        f"<span>{html.escape(meta.get('h1') or 'Copilot vs Codex')}</span></nav>"
    )
    page_html = page_shell(
        title=title,
        description=description,
        canonical=canonical,
        breadcrumb_name=meta.get("h1") or "Copilot vs Codex",
        article_html=f"{breadcrumb_html}<article class='review-layout'><aside class='card toc'><h2>Contents</h2>{toc_html(body_markdown)}</aside><div>{article_html}{related_html}</div></article>",
        faq_items=faq_items,
    )
    output_dir = settings.site_output_dir / "comparisons" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(page_html, encoding="utf-8")
    update_comparisons_index(slug, meta.get("h1") or title, description)
    return output_path


def extract_markdown_meta(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        meta["h1"] = h1.group(1).strip()
    patterns = {
        "seo_title": r"\*\*SEO title:\*\*\s*(.+)",
        "meta_description": r"\*\*Meta description:\*\*\s*(.+)",
        "slug": r"\*\*Slug:\*\*\s*`?([^`\n]+)`?",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            meta[key] = match.group(1).strip()
    return meta


def strip_meta_lines(text: str) -> str:
    lines = []
    skip_prefixes = ("**SEO title:**", "**Meta description:**", "**Slug:**")
    for line in text.splitlines():
        if line.strip().startswith(skip_prefixes):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def markdown_to_html(markdown: str) -> str:
    blocks = split_blocks(markdown)
    html_parts: list[str] = []
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("|") and "\n|" in stripped:
            html_parts.append(render_table(stripped))
        elif stripped.startswith(">"):
            quote = "\n".join(line.lstrip("> ").strip() for line in stripped.splitlines())
            html_parts.append(f"<blockquote class='card trust'>{inline_markdown(quote)}</blockquote>")
        elif stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 3)
            text = stripped[level:].strip()
            html_parts.append(f"<h{level} id='{html.escape(slugify(text), quote=True)}'>{inline_markdown(text)}</h{level}>")
        elif re.match(r"^[-*]\s+", stripped):
            items = [f"<li>{inline_markdown(line[2:].strip())}</li>" for line in stripped.splitlines() if re.match(r"^[-*]\s+", line)]
            html_parts.append("<ul>" + "".join(items) + "</ul>")
        elif re.match(r"^\d+\.\s+", stripped):
            items = [f"<li>{inline_markdown(re.sub(r'^\\d+\\.\\s+', '', line).strip())}</li>" for line in stripped.splitlines() if re.match(r"^\d+\.\s+", line)]
            html_parts.append("<ol>" + "".join(items) + "</ol>")
        else:
            paragraphs = [line.strip() for line in stripped.splitlines() if line.strip()]
            html_parts.extend(f"<p>{inline_markdown(paragraph)}</p>" for paragraph in paragraphs)
    return "\n".join(wrap_sections(html_parts))


def split_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines():
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

    def link_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.unescape(match.group(2))
        rel = ' rel="nofollow sponsored"' if url.startswith("/go/") else ""
        return f'<a href="{html.escape(url, quote=True)}"{rel}>{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, escaped)
    return escaped


def render_table(block: str) -> str:
    rows = [line.strip().strip("|").split("|") for line in block.splitlines() if line.strip()]
    rows = [[inline_markdown(cell.strip()) for cell in row] for row in rows]
    if len(rows) < 2:
        return ""
    headers = rows[0]
    body_rows = [row for row in rows[2:] if row]
    head = "<thead><tr>" + "".join(f"<th>{cell}</th>" for cell in headers) + "</tr></thead>"
    body = "<tbody>" + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in body_rows) + "</tbody>"
    return f"<table>{head}{body}</table>"


def wrap_sections(parts: list[str]) -> list[str]:
    wrapped: list[str] = []
    section: list[str] = []
    for part in parts:
        if part.startswith("<h2") and section:
            wrapped.append("<section class='card'>" + "\n".join(section) + "</section>")
            section = [part]
        else:
            section.append(part)
    if section:
        wrapped.append("<section class='card'>" + "\n".join(section) + "</section>")
    return wrapped


def extract_faq_items(markdown: str) -> list[dict[str, str]]:
    faq_match = re.search(r"## FAQ\s*(.+)$", markdown, flags=re.DOTALL | re.IGNORECASE)
    if not faq_match:
        return []
    content = faq_match.group(1)
    chunks = re.split(r"^###\s+", content, flags=re.MULTILINE)
    items: list[dict[str, str]] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        question = lines[0].strip()
        answer = " ".join(line.strip() for line in lines[1:] if line.strip() and not line.startswith("###"))
        if question and answer:
            items.append({"question": question, "answer": re.sub(r"\s+", " ", answer)})
    return items


def toc_html(markdown: str) -> str:
    links = []
    for heading in re.findall(r"^##\s+(.+)$", markdown, flags=re.MULTILINE):
        if heading.lower().strip() == "faq":
            links.append(f"<a href='#faq'>FAQ</a>")
        else:
            links.append(f"<a href='#{html.escape(slugify(heading), quote=True)}'>{html.escape(heading)}</a>")
    return "".join(links[:14])


def related_links_html() -> str:
    links = [
        ("Best AI Coding Tools 2026", "/best-ai-coding-tools-2026/"),
        ("GitHub Copilot review", "/review/github-copilot/"),
        ("Cursor review", "/review/cursor/"),
        ("Reviews index", "/reviews/"),
        ("Comparisons index", "/comparisons/"),
        ("Pricing index", "/pricing/"),
    ]
    items = "".join(f"<li><a href='{html.escape(url)}'>{html.escape(label)}</a></li>" for label, url in links)
    return f"<section class='card related'><h2>Related internal links</h2><ul>{items}</ul></section>"


def page_shell(title: str, description: str, canonical: str, breadcrumb_name: str, article_html: str, faq_items: list[dict[str, str]]) -> str:
    schemas = base_schemas(title, description, canonical)
    schemas.append(json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Comparisons", "item": f"{BASE_URL}/comparisons/"},
            {"@type": "ListItem", "position": 3, "name": breadcrumb_name, "item": canonical},
        ],
    }, ensure_ascii=False))
    if faq_items:
        schemas.append(json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                }
                for item in faq_items
            ],
        }, ensure_ascii=False))
    schema_html = "\n".join(f'<script type="application/ld+json">{schema}</script>' for schema in schemas)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {html.escape(settings.site_name)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
  <meta property="og:title" content="{html.escape(title)} - {html.escape(settings.site_name)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:image" content="{html.escape(site_url('/assets/og/site.svg'), quote=True)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{html.escape(site_url('/assets/og/site.svg'), quote=True)}">
  {analytics_snippet()}
  {schema_html}
  <style>{base_css()}</style>
</head>
<body>{nav_html()}<main class="wrap legal">{article_html}</main>{footer_html()}{click_timer_script()}</body>
</html>"""


def update_comparisons_index(slug: str, title: str, description: str) -> None:
    index_path = settings.site_output_dir / "comparisons" / "index.html"
    if not index_path.exists():
        return
    text = index_path.read_text(encoding="utf-8")
    href = f"/comparisons/{slug}/"
    if href in text:
        return
    card = (
        "<section class='card'>"
        "<h2>New practical comparison</h2>"
        f"<p><a href='{html.escape(href)}'>{html.escape(title)}</a></p>"
        f"<p>{html.escape(description)}</p>"
        "</section>"
    )
    text = text.replace("</main>", f"{card}</main>", 1)
    index_path.write_text(text, encoding="utf-8")


def click_timer_script() -> str:
    return """<script id="aiip_click_timer">
(function(){
  const startedAt = Date.now();
  document.addEventListener("click", function(event) {
    const anchor = event.target && event.target.closest ? event.target.closest("a[href^='/go/']") : null;
    if (!anchor) return;
    try {
      const url = new URL(anchor.getAttribute("href"), window.location.origin);
      if (!url.searchParams.get("pls")) {
        url.searchParams.set("pls", Math.max(0, (Date.now() - startedAt) / 1000).toFixed(2));
        anchor.setAttribute("href", url.pathname + url.search + url.hash);
      }
    } catch (err) {}
  }, true);
})();
</script>"""


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

