from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from config import settings
from modules.indexing_policy import is_public_sitemap_base_url, rel_path_for_html, should_include_in_sitemap


def generate_sitemap(
    output_dir: Path | None = None,
    base_url: str | None = None,
    *,
    updated_urls: Iterable[str] | None = None,
    preserve_existing_lastmod: bool = True,
) -> Path:
    output = output_dir or settings.site_output_dir
    base = (base_url or settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    output.mkdir(parents=True, exist_ok=True)
    path = output / "sitemap.xml"
    previous = read_lastmod_map(path) if preserve_existing_lastmod else {}
    urls = scan_index_pages(output, base)
    changed = {str(url).strip() for url in (updated_urls or []) if str(url).strip()}
    today = datetime.now().date().isoformat()
    for item in urls:
        if item["loc"] in changed:
            item["lastmod"] = today
        elif item["loc"] in previous:
            item["lastmod"] = previous[item["loc"]]
    xml = build_sitemap_xml(urls)
    path.write_text(xml, encoding="utf-8")
    return path


def scan_index_pages(output: Path, base_url: str) -> list[dict[str, str]]:
    if not is_public_sitemap_base_url(base_url):
        raise ValueError(f"Sitemap base URL must be a public HTTP(S) URL: {base_url}")
    pages: list[dict[str, str]] = []
    for index_file in sorted(output.rglob("index.html")):
        url_path = rel_path_for_html(index_file, output)
        if not should_include_in_sitemap(url_path):
            continue
        if url_path == "/":
            loc = f"{base_url}/"
        else:
            loc = f"{base_url}{url_path}"
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

def file_lastmod(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def read_lastmod_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="strict"))
    except (ET.ParseError, UnicodeError, OSError):
        return {}
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    result: dict[str, str] = {}
    for item in root.findall(f"{namespace}url"):
        loc = item.find(f"{namespace}loc")
        lastmod = item.find(f"{namespace}lastmod")
        if loc is not None and loc.text and lastmod is not None and lastmod.text:
            result[loc.text.strip()] = lastmod.text.strip()
    return result


def build_sitemap_xml(urls: list[dict[str, str]]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for item in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(item['loc'])}</loc>")
        lines.append(f"    <lastmod>{escape(item['lastmod'])}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"
