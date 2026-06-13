from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
REPORT = ROOT / "data" / "seo_ai_search_audit_2026.json"


def main() -> int:
    pages = sorted(SITE.rglob("index.html"))
    counts: Counter[str] = Counter()
    internal_link_counts: list[int] = []
    html_sizes: list[int] = []
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="ignore")
        html_sizes.append(page.stat().st_size)
        internal_link_counts.append(len(set(re.findall(r'href=["\'](/[^"\']*)', text, flags=re.I))))
        checks = {
            "canonical": r'rel=["\']canonical["\']',
            "meta_description": r'<meta\b[^>]*name=["\']description["\']',
            "open_graph": r'property=["\']og:',
            "twitter_card": r'name=["\']twitter:',
            "h1": r"<h1\b",
            "index_follow": r'content=["\']index,follow["\']',
            "noindex": r"noindex",
            "organization_schema": r'"@type"\s*:\s*"Organization"',
            "person_schema": r'"@type"\s*:\s*"Person"',
            "article_schema": r'"@type"\s*:\s*"Article"',
            "review_schema": r'"@type"\s*:\s*"Review"',
            "software_schema": r'"@type"\s*:\s*"SoftwareApplication"',
            "faq_schema": r'"@type"\s*:\s*"FAQPage"',
            "breadcrumb_schema": r'"@type"\s*:\s*"BreadcrumbList"',
            "affiliate_disclosure_link": r'href=["\']/(?:vi/)?affiliate-disclosure/',
            "author_visible": r"Nguyen Quoc Tuan",
            "updated_date_visible": r"Last updated|Cập nhật lần cuối",
            "pros_cons": r"\bPros\b.*\bCons\b|\bƯu điểm\b.*\bNhượcc? điểm\b",
            "pricing": r"\bPricing\b|\bGiá\b",
            "faq_visible": r"<details\b|>\s*FAQ\s*<|Câu hỏi thường gặp",
        }
        for name, pattern in checks.items():
            if re.search(pattern, text, flags=re.I | re.S):
                counts[name] += 1

    sitemap_count = 0
    sitemap = SITE / "sitemap.xml"
    if sitemap.exists():
        root = ET.fromstring(sitemap.read_text(encoding="utf-8", errors="ignore"))
        sitemap_count = len(root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"))

    images = list(SITE.rglob("*.png")) + list(SITE.rglob("*.jpg")) + list(SITE.rglob("*.jpeg")) + list(SITE.rglob("*.webp"))
    large_images = [str(path.relative_to(SITE)) for path in images if path.stat().st_size > 500_000]
    payload = {
        "pages": len(pages),
        "sitemap_urls": sitemap_count,
        "robots_exists": (SITE / "robots.txt").exists(),
        "llms_txt_exists": (SITE / "llms.txt").exists(),
        "coverage": dict(counts),
        "internal_links": {
            "minimum": min(internal_link_counts, default=0),
            "average": round(sum(internal_link_counts) / max(1, len(internal_link_counts)), 1),
            "pages_below_3": sum(value < 3 for value in internal_link_counts),
        },
        "performance_static_signals": {
            "average_html_kb": round(sum(html_sizes) / max(1, len(html_sizes)) / 1024, 1),
            "largest_html_kb": round(max(html_sizes, default=0) / 1024, 1),
            "images_over_500kb": large_images,
            "note": "Static-source audit only. Confirm Core Web Vitals with PageSpeed Insights or Search Console field data.",
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
