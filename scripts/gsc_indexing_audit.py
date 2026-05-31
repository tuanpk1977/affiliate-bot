from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
BASE_URL = "https://smileaireviewhub.com"

IMPORTANT_URLS = [
    "/",
    "/best-ai-coding-tools-2026/",
    "/windsurf-review/",
    "/comparisons/cursor-vs-windsurf/",
    "/comparisons/copilot-vs-cursor/",
    "/cursor/",
    "/github-copilot/",
    "/semrush/",
    "/canva/",
    "/zapier/",
    "/make/",
    "/elevenlabs/",
]

NOINDEX_PATHS = [
    "/rss.xml",
    "/sitemap/",
    "/media-kit/",
    "/about-author/",
    "/author-profile/",
    "/affiliate-disclosure/",
    "/editorial-policy/",
]

REDIRECTS = {
    "/reviews/windsurf-review/": "/windsurf-review/",
}

DUPLICATE_CANDIDATES = [
    ("/jasper-ai/", "/jasper/", "Possible duplicate brand page. Prefer one canonical Jasper review unless the AI-specific page is expanded."),
    ("/pipedrive-crm/", "/pipedrive/", "Possible duplicate CRM page. Prefer one canonical Pipedrive review unless CRM page has unique intent."),
    ("/notion-ai/", "/notion/", "Keep both only if Notion AI has distinct AI workflow content and internal links."),
]


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    sitemap_urls = read_sitemap_urls()
    target_errors = validate_sitemap_targets(sitemap_urls)
    noindex_rows = build_noindex_rows()
    redirect_rows = build_redirect_rows()
    duplicate_rows = build_duplicate_rows()
    keep_rows = build_keep_rows(sitemap_urls)

    write_csv(DATA / "gsc_index_keep_urls.csv", keep_rows)
    write_csv(DATA / "gsc_noindex_urls.csv", noindex_rows)
    write_csv(DATA / "gsc_redirect_urls.csv", redirect_rows)
    write_csv(DATA / "gsc_404_fixed_urls.csv", target_errors or [{"url": "", "status": "none", "note": "No missing sitemap targets found"}])
    write_csv(DATA / "gsc_final_sitemap_urls.csv", [{"url": url} for url in sitemap_urls])
    write_csv(DATA / "duplicate_thin_page_recommendations.csv", duplicate_rows)

    summary = [
        f"sitemap_urls={len(sitemap_urls)}",
        f"index_keep_urls={len(keep_rows)}",
        f"noindex_urls={len(noindex_rows)}",
        f"redirect_rules={len(redirect_rows)}",
        f"sitemap_missing_targets={len(target_errors)}",
        f"duplicate_review_recommendations={len(duplicate_rows)}",
    ]
    (DATA / "gsc_indexing_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("GSC indexing audit")
    for line in summary:
        print(f"- {line}")
    return 1 if target_errors else 0


def read_sitemap_urls() -> list[str]:
    sitemap = SITE / "sitemap.xml"
    if not sitemap.exists():
        return []
    root = ET.fromstring(sitemap.read_text(encoding="utf-8", errors="ignore"))
    urls = []
    for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
        if loc.text:
            urls.append(loc.text.strip())
    return urls


def validate_sitemap_targets(urls: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for url in urls:
        parsed = urlparse(url)
        rel = parsed.path.strip("/")
        target = SITE / "index.html" if not rel else SITE / rel / "index.html"
        if not target.exists():
            rows.append({"url": url, "status": "missing_file", "note": str(target)})
    return rows


def build_keep_rows(sitemap_urls: list[str]) -> list[dict[str, str]]:
    rows = []
    url_set = set(sitemap_urls)
    for path in IMPORTANT_URLS:
        url = BASE_URL + path
        rows.append(
            {
                "url": url,
                "in_sitemap": "yes" if url in url_set else "no",
                "page_type": classify_path(path),
                "priority": "high",
                "reason": priority_reason(path),
                "suggested_action": "Submit in Google Search Console URL Inspection",
            }
        )
    for url in sitemap_urls:
        if url in {row["url"] for row in rows}:
            continue
        path = urlparse(url).path
        rows.append(
            {
                "url": url,
                "in_sitemap": "yes",
                "page_type": classify_path(path),
                "priority": "normal",
                "reason": "Included in final SEO sitemap",
                "suggested_action": "Let Google crawl through sitemap and internal links",
            }
        )
    return rows


def build_noindex_rows() -> list[dict[str, str]]:
    rows = []
    for path in NOINDEX_PATHS:
        target = SITE / path.strip("/") / "index.html" if path.endswith("/") else SITE / path.strip("/")
        has_noindex = False
        if target.exists() and target.suffix == ".html":
            text = target.read_text(encoding="utf-8", errors="ignore").lower()
            has_noindex = 'name="robots"' in text and "noindex" in text
        rows.append(
            {
                "url": BASE_URL + path,
                "status": "noindex" if has_noindex or path.endswith(".xml") else "needs_check",
                "reason": "Secondary utility/trust/feed page; not a primary SEO landing page",
                "local_file_exists": "yes" if target.exists() else "no",
            }
        )
    return rows


def build_redirect_rows() -> list[dict[str, str]]:
    rows = []
    for source, target in REDIRECTS.items():
        local = SITE / source.strip("/") / "index.html"
        rows.append(
            {
                "source_url": BASE_URL + source,
                "target_url": BASE_URL + target,
                "redirect_type": "301 on Netlify/Cloudflare _redirects; static meta/js fallback on GitHub Pages",
                "local_fallback_exists": "yes" if local.exists() else "no",
            }
        )
    return rows


def build_duplicate_rows() -> list[dict[str, str]]:
    rows = []
    for candidate, canonical, note in DUPLICATE_CANDIDATES:
        candidate_file = SITE / candidate.strip("/") / "index.html"
        canonical_file = SITE / canonical.strip("/") / "index.html"
        rows.append(
            {
                "candidate_url": BASE_URL + candidate,
                "recommended_canonical": BASE_URL + canonical,
                "candidate_exists": "yes" if candidate_file.exists() else "no",
                "canonical_exists": "yes" if canonical_file.exists() else "no",
                "recommendation": "merge_or_expand",
                "note": note,
            }
        )
    return rows


def classify_path(path: str) -> str:
    if path == "/":
        return "homepage"
    if path.startswith("/comparisons/") or path.startswith("/compare/"):
        return "comparison"
    if path.startswith("/pricing/") or path.endswith("-pricing/"):
        return "pricing"
    if path.startswith("/category/"):
        return "category"
    if path.startswith("/hub/"):
        return "hub"
    if path.startswith("/best-"):
        return "best_tools"
    if path.startswith("/review/"):
        return "review"
    return "article_or_review"


def priority_reason(path: str) -> str:
    if any(token in path for token in ["cursor", "windsurf", "copilot", "coding"]):
        return "AI coding tool money page or comparison requested for priority indexing"
    if any(token in path for token in ["semrush", "canva", "zapier", "make", "elevenlabs"]):
        return "High-intent affiliate review page"
    return "Core site page"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
