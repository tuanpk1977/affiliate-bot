from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from config import settings

NOINDEX_EXACT_PATHS = {
    "sitemap",
    "media-kit",
    "about-author",
    "author-profile",
    "affiliate-disclosure",
    "editorial-policy",
}

NOINDEX_PREFIXES = {
    "assets",
    "__pycache__",
    "go",
}


def generate_sitemap(output_dir: Path | None = None, base_url: str | None = None) -> Path:
    output = output_dir or settings.site_output_dir
    base = (base_url or settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
    output.mkdir(parents=True, exist_ok=True)
    urls = scan_index_pages(output, base)
    xml = build_sitemap_xml(urls)
    path = output / "sitemap.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def scan_index_pages(output: Path, base_url: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    for index_file in sorted(output.rglob("index.html")):
        if should_skip(index_file, output):
            continue
        parent = index_file.parent
        rel = parent.relative_to(output)
        if str(rel) == ".":
            loc = f"{base_url}/"
        else:
            url_path = "/".join(rel.parts)
            loc = f"{base_url}/{url_path}/"
        pages.append({"loc": loc, "lastmod": file_lastmod(index_file)})

    seen = set()
    unique_pages = []
    for page in pages:
        if page["loc"] in seen:
            continue
        seen.add(page["loc"])
        unique_pages.append(page)
    unique_pages.sort(key=lambda item: (item["loc"] != f"{base_url}/", item["loc"]))
    return unique_pages


def should_skip(path: Path, output: Path) -> bool:
    rel_parts = path.relative_to(output).parts
    if not rel_parts:
        return False
    if rel_parts[0] in NOINDEX_PREFIXES:
        return True
    if rel_parts[0] == "reviews" and len(rel_parts) > 2:
        return True
    url_path = "/".join(rel_parts[:-1]) if rel_parts[-1] == "index.html" else "/".join(rel_parts)
    return url_path.strip("/") in NOINDEX_EXACT_PATHS


def file_lastmod(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def build_sitemap_xml(urls: list[dict[str, str]]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for item in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(item['loc'])}</loc>")
        lines.append(f"    <lastmod>{escape(item['lastmod'])}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"
