from __future__ import annotations

import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE_DIR = ROOT / "docs"
DEFAULT_REPORT_DIR = ROOT / "reports"
BASE_URL = "https://smileaireviewhub.com"

CONTENT_AUDIT_FIELDS = [
    "URL",
    "Title",
    "Category",
    "Word Count",
    "Internal Links",
    "External Sources",
    "Traffic",
    "Impressions",
    "Clicks",
    "CTR",
    "Position",
    "AI Readiness Score",
    "Priority",
]

SEARCH_OPPORTUNITY_FIELDS = [
    "Keyword",
    "Impressions",
    "Clicks",
    "CTR",
    "Position",
    "Page URL",
    "Opportunity Score",
]

AI_CITATION_FIELDS = [
    "Date",
    "Keyword",
    "Google AI Overview",
    "ChatGPT Search",
    "Perplexity",
    "Bing Copilot",
    "Mentioned? (Yes/No)",
    "Source URL",
]

CLUSTER_FIELDS = ["Cluster", "Topic", "Recommended Slug", "Intent", "Priority", "Notes"]
UPGRADE_QUEUE_FIELDS = [
    "URL",
    "Title",
    "Priority",
    "AI Readiness Score",
    "Impressions",
    "Clicks",
    "Category",
    "Missing Sections",
    "Suggested Upgrade",
]

REQUIRED_MARKERS = {
    "direct_answer": [r"direct answer", r"quick answer", r"summary", r"bottom line"],
    "comparison_table": [r"<table", r"comparison"],
    "what_it_is": [r"what it is", r"overview"],
    "key_features": [r"key features", r"features"],
    "pricing": [r"pricing", r"price", r"free plan"],
    "pros_cons": [r"pros", r"cons"],
    "who_should_use": [r"who should use", r"best for", r"not ideal"],
    "alternatives": [r"alternatives"],
    "verdict": [r"final verdict", r"verdict"],
    "faq": [r"faq", r"frequently asked"],
    "sources": [r"official website", r"official docs", r"official pricing", r"sources"],
    "updated": [r"last updated", r"updated"],
}


@dataclass
class Page:
    path: Path
    url: str
    title: str
    text: str
    html_text: str
    internal_links: int
    external_sources: int
    robots: str
    canonical: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI-search domination reports for Smile AI Review Hub.")
    parser.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    reports_dir = args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)

    pages = scan_pages(args.site_dir, args.base_url.rstrip("/"))
    sitemap_urls = read_sitemap(args.site_dir / "sitemap.xml")
    page_metrics = load_page_metrics()
    query_metrics = load_query_metrics()
    keyword_fallback = load_keyword_fallback()

    content_rows = build_content_audit(pages, page_metrics)
    opportunity_rows = build_search_opportunities(query_metrics, keyword_fallback)
    citation_rows = build_ai_citation_monitor(opportunity_rows, content_rows)
    cluster_rows = build_content_clusters()
    upgrade_rows = build_upgrade_queue(pages, page_metrics)
    report_md = render_upgrade_report(content_rows, opportunity_rows, sitemap_urls)

    write_csv(reports_dir / "content-audit.csv", CONTENT_AUDIT_FIELDS, content_rows)
    write_csv(reports_dir / "search-opportunities.csv", SEARCH_OPPORTUNITY_FIELDS, opportunity_rows)
    write_csv(reports_dir / "ai-citation-monitor.csv", AI_CITATION_FIELDS, citation_rows)
    write_csv(reports_dir / "answer-engine-content-clusters.csv", CLUSTER_FIELDS, cluster_rows)
    write_csv(reports_dir / "article-upgrade-queue.csv", UPGRADE_QUEUE_FIELDS, upgrade_rows)
    (reports_dir / "content-upgrade-report.md").write_text(report_md, encoding="utf-8")

    print(f"Content audit rows: {len(content_rows)}")
    print(f"Search opportunity rows: {len(opportunity_rows)}")
    print(f"AI citation monitor rows: {len(citation_rows)}")
    print(f"Article upgrade queue rows: {len(upgrade_rows)}")
    print(f"Reports written to: {reports_dir}")
    return 0


def scan_pages(site_dir: Path, base_url: str) -> list[Page]:
    pages: list[Page] = []
    for path in sorted(site_dir.rglob("*.html")):
        rel = path.relative_to(site_dir).as_posix()
        if should_skip_html(rel):
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        url_path = html_path_to_url_path(rel)
        robots = extract_meta(raw, "robots")
        if "noindex" in robots.lower() or url_path.startswith("/go/"):
            continue
        text = html_to_text(raw)
        pages.append(
            Page(
                path=path,
                url=f"{base_url}{url_path}",
                title=extract_title(raw),
                text=text,
                html_text=raw,
                internal_links=count_internal_links(raw),
                external_sources=count_external_sources(raw),
                robots=robots,
                canonical=extract_canonical(raw),
            )
        )
    return pages


def should_skip_html(rel: str) -> bool:
    name = Path(rel).name.lower()
    if rel.startswith("assets/"):
        return True
    if name.startswith(("yandex_", "google", "bing")) and name.endswith(".html"):
        return True
    if name in {"404.html"}:
        return True
    return False


def html_path_to_url_path(rel: str) -> str:
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    if rel.endswith(".html"):
        return "/" + rel[: -len(".html")]
    return "/" + rel


def extract_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if not match:
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.I | re.S)
        return clean_text(h1.group(1)) if h1 else ""
    return clean_text(match.group(1))


def extract_meta(text: str, name: str) -> str:
    match = re.search(
        rf"<meta\b(?=[^>]*\bname=['\"]{re.escape(name)}['\"])[^>]*\bcontent=['\"]([^'\"]*)['\"]",
        text,
        flags=re.I,
    )
    return html.unescape(match.group(1).strip()) if match else ""


def extract_canonical(text: str) -> str:
    match = re.search(r"<link\b(?=[^>]*\brel=['\"]canonical['\"])[^>]*\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I)
    return html.unescape(match.group(1).strip()) if match else ""


def html_to_text(text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    return clean_text(text)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def count_internal_links(text: str) -> int:
    count = 0
    for href in re.findall(r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I):
        parsed = urlparse(href)
        if href.startswith("/") or parsed.netloc == "smileaireviewhub.com":
            if not href.startswith("/go/"):
                count += 1
    return count


def count_external_sources(text: str) -> int:
    count = 0
    for href in re.findall(r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"]", text, flags=re.I):
        parsed = urlparse(href)
        if parsed.scheme in {"http", "https"} and parsed.netloc and parsed.netloc != "smileaireviewhub.com":
            count += 1
    return count


def category_for(url: str, title: str) -> str:
    path = urlparse(url).path.lower()
    value = f"{path} {title}".lower()
    if "/compare/" in path or "/comparisons/" in path or " vs " in value:
        return "Comparison"
    if "pricing" in value:
        return "Pricing"
    if "alternative" in value:
        return "Alternatives"
    if "coding" in value or "developer" in value:
        return "AI Coding"
    if "seo" in value or "keyword" in value:
        return "AI SEO"
    if "video" in value:
        return "AI Video"
    if "writing" in value or "writer" in value:
        return "AI Writing"
    if "/review/" in path or "/reviews/" in path or "review" in value:
        return "Review"
    return "General"


def ai_readiness_score(page: Page) -> int:
    haystack = page.html_text.lower()
    score = 0
    for patterns in REQUIRED_MARKERS.values():
        if any(re.search(pattern, haystack, flags=re.I) for pattern in patterns):
            score += 6
    if page.external_sources >= 2:
        score += 8
    if page.internal_links >= 5:
        score += 8
    wc = word_count(page.text)
    if wc >= 1200:
        score += 6
    if wc >= 2000:
        score += 6
    if "application/ld+json" in haystack:
        score += 6
    if "summary" in haystack or "quick answer" in haystack:
        score += 4
    return min(100, score)


def priority_for(score: int, impressions: float, clicks: float, category: str) -> str:
    if score < 65 or impressions >= 100 or clicks >= 5 or category in {"Comparison", "Pricing", "Alternatives"}:
        return "HIGH"
    if score < 80 or impressions >= 20:
        return "MEDIUM"
    return "LOW"


def build_content_audit(pages: list[Page], metrics: dict[str, dict[str, float]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for page in pages:
        path = normalize_url_path(page.url)
        metric = metrics.get(path, {})
        impressions = float(metric.get("impressions", 0))
        clicks = float(metric.get("clicks", 0))
        ctr = float(metric.get("ctr", 0))
        position = float(metric.get("position", 0))
        category = category_for(page.url, page.title)
        readiness = ai_readiness_score(page)
        rows.append(
            {
                "URL": page.url,
                "Title": page.title,
                "Category": category,
                "Word Count": word_count(page.text),
                "Internal Links": page.internal_links,
                "External Sources": page.external_sources,
                "Traffic": int(clicks),
                "Impressions": int(impressions),
                "Clicks": int(clicks),
                "CTR": round(ctr, 4),
                "Position": round(position, 2),
                "AI Readiness Score": readiness,
                "Priority": priority_for(readiness, impressions, clicks, category),
            }
        )
    rows.sort(key=lambda row: (priority_rank(str(row["Priority"])), -float(row["Impressions"]), -float(row["Clicks"]), float(row["AI Readiness Score"])))
    return rows


def build_upgrade_queue(pages: list[Page], metrics: dict[str, dict[str, float]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for page in pages:
        path = normalize_url_path(page.url)
        metric = metrics.get(path, {})
        impressions = float(metric.get("impressions", 0))
        clicks = float(metric.get("clicks", 0))
        category = category_for(page.url, page.title)
        readiness = ai_readiness_score(page)
        priority = priority_for(readiness, impressions, clicks, category)
        if priority == "LOW":
            continue
        missing = missing_answer_engine_sections(page)
        suggested = "Refresh for answer-engine structure" if missing else "Improve citations, pricing checks, and internal links"
        rows.append(
            {
                "URL": page.url,
                "Title": page.title,
                "Priority": priority,
                "AI Readiness Score": readiness,
                "Impressions": int(impressions),
                "Clicks": int(clicks),
                "Category": category,
                "Missing Sections": "; ".join(missing),
                "Suggested Upgrade": suggested,
            }
        )
    rows.sort(
        key=lambda row: (
            priority_rank(str(row["Priority"])),
            -float(row["Impressions"]),
            -float(row["Clicks"]),
            float(row["AI Readiness Score"]),
        )
    )
    return rows


def missing_answer_engine_sections(page: Page) -> list[str]:
    haystack = page.html_text.lower()
    missing: list[str] = []
    labels = {
        "direct_answer": "Direct Answer",
        "comparison_table": "Quick Comparison Table",
        "who_should_use": "Who Should Use It",
        "alternatives": "Alternatives",
        "faq": "FAQ",
        "sources": "Official Sources",
        "updated": "Published/Updated Dates",
    }
    for key, label in labels.items():
        if not any(re.search(pattern, haystack, flags=re.I) for pattern in REQUIRED_MARKERS[key]):
            missing.append(label)
    return missing


def load_page_metrics() -> dict[str, dict[str, float]]:
    rows = read_csv_dicts(ROOT / "data" / "traffic_performance_report.csv")
    metrics: dict[str, dict[str, float]] = {}
    for row in rows:
        path = normalize_path(row.get("page") or row.get("Page URL") or row.get("URL") or "")
        if not path:
            continue
        metrics[path] = {
            "impressions": number(row.get("impressions")),
            "clicks": number(row.get("clicks")),
            "ctr": number(row.get("ctr")),
            "position": number(row.get("avg_position") or row.get("average_position") or row.get("position")),
        }
    for row in read_csv_dicts(ROOT / "data" / "gsc_page_performance_report.csv"):
        path = normalize_path(row.get("page") or "")
        if not path:
            continue
        metrics[path] = {
            "impressions": number(row.get("impressions")),
            "clicks": number(row.get("clicks")),
            "ctr": number(row.get("average_ctr")),
            "position": number(row.get("average_position")),
        }
    return metrics


def load_query_metrics() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in [ROOT / "data" / "gsc_query_performance_report.csv", ROOT / "data" / "gsc_performance_queries.csv"]:
        for row in read_csv_dicts(source):
            keyword = str(row.get("query") or row.get("keyword") or "").strip()
            if not keyword:
                continue
            rows.append(
                {
                    "Keyword": keyword,
                    "Impressions": number(row.get("impressions")),
                    "Clicks": number(row.get("clicks")),
                    "CTR": number(row.get("average_ctr") or row.get("ctr")),
                    "Position": number(row.get("average_position") or row.get("position")),
                    "Page URL": absolute_url(row.get("page") or ""),
                }
            )
    return rows


def load_keyword_fallback() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in [ROOT / "data" / "keyword_opportunities.csv", ROOT / "data" / "keyword_intelligence_report.csv"]:
        for row in read_csv_dicts(source):
            keyword = str(row.get("keyword") or "").strip()
            if not keyword:
                continue
            score = number(row.get("seo_priority_score") or row.get("priority_score") or row.get("ranking_opportunity"))
            page = row.get("page_url") or row.get("target_page_title") or row.get("suggested_slug") or ""
            rows.append(
                {
                    "Keyword": keyword,
                    "Impressions": 0,
                    "Clicks": 0,
                    "CTR": 0,
                    "Position": 0,
                    "Page URL": page_to_url(page),
                    "Opportunity Score": int(score or 40),
                }
            )
    return rows


def build_search_opportunities(query_rows: list[dict[str, object]], fallback_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if query_rows:
        rows = []
        for row in query_rows:
            impressions = float(row["Impressions"])
            clicks = float(row["Clicks"])
            ctr = float(row["CTR"])
            position = float(row["Position"])
            score = opportunity_score(impressions, clicks, ctr, position)
            rows.append({**row, "Opportunity Score": score})
        rows.sort(key=lambda row: float(row["Opportunity Score"]), reverse=True)
        return rows
    rows = fallback_rows[:]
    rows.sort(key=lambda row: float(row["Opportunity Score"]), reverse=True)
    return rows


def opportunity_score(impressions: float, clicks: float, ctr: float, position: float) -> int:
    impression_score = min(45, impressions / 20)
    ctr_score = 25 if impressions > 0 and ctr < 0.02 else 15 if ctr < 0.05 else 5
    position_score = 30 if 5 <= position <= 30 else 15 if 1 <= position < 5 else 5
    click_penalty = min(10, clicks / 5)
    return int(max(0, min(100, impression_score + ctr_score + position_score - click_penalty)))


def build_ai_citation_monitor(opportunities: list[dict[str, object]], content_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    today = date.today().isoformat()
    if opportunities:
        source = opportunities[:50]
        for row in source:
            rows.append(
                {
                    "Date": today,
                    "Keyword": row["Keyword"],
                    "Google AI Overview": "",
                    "ChatGPT Search": "",
                    "Perplexity": "",
                    "Bing Copilot": "",
                    "Mentioned? (Yes/No)": "No",
                    "Source URL": row.get("Page URL", ""),
                }
            )
        return rows
    for row in content_rows[:50]:
        rows.append(
            {
                "Date": today,
                "Keyword": str(row["Title"]).replace(" - MS Smile AI Review Hub", "")[:120],
                "Google AI Overview": "",
                "ChatGPT Search": "",
                "Perplexity": "",
                "Bing Copilot": "",
                "Mentioned? (Yes/No)": "No",
                "Source URL": row["URL"],
            }
        )
    return rows


def build_content_clusters() -> list[dict[str, object]]:
    clusters = {
        "Best For Articles": [
            "Best AI Tools For Students",
            "Best AI Tools For Teachers",
            "Best AI Tools For Freelancers",
            "Best AI Tools For Startups",
            "Best AI Tools For Small Business",
            "Best AI Tools Under $10",
            "Best AI Tools Under $20",
            "Best AI Tools Under $50",
            "Best AI Coding Tools For Beginners",
            "Best AI Coding Tools For Non Developers",
        ],
        "Comparison Articles": [
            "Cursor vs GitHub Copilot",
            "Cursor vs Windsurf",
            "Cursor vs Claude Code",
            "Claude vs ChatGPT",
            "Gemini vs ChatGPT",
            "Copy.ai vs Jasper",
            "Midjourney vs Leonardo AI",
            "HeyGen vs Synthesia",
        ],
        "Decision Articles": [
            "Which AI Coding Tool Should You Choose?",
            "Which AI Writer Is Best For Beginners?",
            "Which AI Image Generator Is Worth Paying For?",
            "Which AI Video Generator Is Best In 2026?",
            "Which AI Tool Is Best For Affiliate Marketing?",
        ],
    }
    rows: list[dict[str, object]] = []
    for cluster, topics in clusters.items():
        for index, topic in enumerate(topics, start=1):
            rows.append(
                {
                    "Cluster": cluster,
                    "Topic": topic,
                    "Recommended Slug": slugify(topic),
                    "Intent": intent_for_topic(topic),
                    "Priority": "HIGH" if index <= 3 else "MEDIUM",
                    "Notes": "Create only if no existing canonical page covers this exact intent.",
                }
            )
    return rows


def render_upgrade_report(content_rows: list[dict[str, object]], opportunity_rows: list[dict[str, object]], sitemap_urls: list[str]) -> str:
    total = len(content_rows)
    avg_readiness = round(sum(float(row["AI Readiness Score"]) for row in content_rows) / total, 1) if total else 0
    high_priority = [row for row in content_rows if row["Priority"] == "HIGH"]
    top_perplexity = sorted(content_rows, key=lambda row: (-float(row["AI Readiness Score"]), -float(row["Internal Links"]), -float(row["External Sources"])))[:50]
    top_google = sorted(content_rows, key=lambda row: (-float(row["Impressions"]), -float(row["Clicks"]), -float(row["AI Readiness Score"])))[:50]
    backlink_needs = sorted(content_rows, key=lambda row: (float(row["External Sources"]), float(row["Internal Links"]), -float(row["AI Readiness Score"])))[:50]

    return f"""# AI Search Domination Content Upgrade Report

Generated from local published output and available local search data.

## Summary

- Total articles scanned: {total}
- Articles upgraded: 0
- Articles created: 0
- Sitemap URLs detected: {len(sitemap_urls)}
- Average AI Readiness before: {avg_readiness}
- Average AI Readiness after: {avg_readiness}
- High priority pages needing answer-engine upgrade: {len(high_priority)}

No content was rewritten by this report. It identifies the safest upgrade order for answer engines.

## Highest Search Opportunities

{table(opportunity_rows[:25], ["Keyword", "Opportunity Score", "Page URL"])}

## Top 50 Pages Likely To Be Cited By Perplexity

{table(top_perplexity, ["URL", "Title", "AI Readiness Score", "External Sources", "Internal Links"])}

## Top 50 Pages Likely To Rank On Google

{table(top_google, ["URL", "Title", "Impressions", "Clicks", "AI Readiness Score"])}

## Top 50 Pages Needing Additional Backlinks Or Citations

{table(backlink_needs, ["URL", "Title", "External Sources", "Internal Links", "AI Readiness Score"])}

## Recommended Weekly Automation

1. Refresh the top 10 `HIGH` priority pages from `reports/content-audit.csv`.
2. Use `reports/search-opportunities.csv` to improve titles/meta for high-impression low-CTR queries.
3. Add official sources and visible FAQ sections before adding affiliate CTAs.
4. Add 5-10 internal links from hubs and related reviews to every refreshed page.
5. Track answer-engine citations in `reports/ai-citation-monitor.csv`.
"""


def table(rows: list[dict[str, object]], fields: list[str]) -> str:
    if not rows:
        return "_No rows available._\n"
    header = "| " + " | ".join(fields) + " |"
    sep = "| " + " | ".join("---" for _ in fields) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(escape_md(str(row.get(field, ""))) for field in fields) + " |")
    return "\n".join([header, sep] + body) + "\n"


def read_sitemap(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except ET.ParseError:
        return []
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [node.text.strip() for node in root.findall(f".//{ns}loc") if node.text]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            with path.open("r", newline="", encoding=encoding) as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        except UnicodeDecodeError:
            continue
    return []


def number(value: object) -> float:
    text = str(value or "").strip().replace("%", "")
    if not text:
        return 0.0
    try:
        result = float(text)
    except ValueError:
        return 0.0
    if "%" in str(value):
        return result / 100
    return result


def normalize_url_path(value: str) -> str:
    return normalize_path(urlparse(value).path if value.startswith("http") else value)


def normalize_path(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    path = parsed.path if parsed.scheme or parsed.netloc else text
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return path


def absolute_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("http"):
        return text
    return f"{BASE_URL}{normalize_path(text)}"


def page_to_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("http"):
        return text
    if "/" in text:
        return absolute_url(text)
    return f"{BASE_URL}/{slugify(text)}/"


def slugify(value: str) -> str:
    text = value.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "topic"


def intent_for_topic(topic: str) -> str:
    lowered = topic.lower()
    if " vs " in lowered:
        return "comparison"
    if lowered.startswith("best "):
        return "best-list"
    if lowered.startswith("which "):
        return "decision"
    return "review"


def priority_rank(value: str) -> int:
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(value, 3)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")[:220]


if __name__ == "__main__":
    raise SystemExit(main())
