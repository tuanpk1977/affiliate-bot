from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.indexing_policy import is_redirect_page, rel_path_for_html  # noqa: E402

SITE = ROOT / "site_output"
DATA = ROOT / "data"
REPORT_CSV = DATA / "final_predeploy_report.csv"
SUMMARY_TXT = DATA / "final_predeploy_summary.txt"
BASE_URL = "https://smileaireviewhub.com"
PLACEHOLDER_PATTERNS = [
    r"\blorem\b",
    r"\btodo\b",
    r"your api key",
    r"example\.com",
    r"affiliate link here",
]
SKIP_LINK_PREFIXES = ("/assets/", "/rss.xml", "/sitemap.xml", "/robots.txt", "/llms.txt")


@dataclass
class CheckRow:
    check: str
    status: str
    details: str


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])


def main() -> int:
    rows: list[CheckRow] = []
    errors: list[str] = []
    warnings: list[str] = []

    required_paths = {
        "site_output": SITE,
        "index.html": SITE / "index.html",
        "sitemap.xml": SITE / "sitemap.xml",
        "robots.txt": SITE / "robots.txt",
    }
    for label, path in required_paths.items():
        ok = path.exists()
        add_row(rows, label, ok, str(path))
        if not ok:
            errors.append(f"missing {label}")

    if errors:
        write_outputs(rows, errors, warnings, {})
        print_result(errors, warnings, {})
        return 1

    html_files = sorted(SITE.rglob("*.html"))
    sitemap_urls = parse_sitemap(SITE / "sitemap.xml")
    sitemap_text = (SITE / "sitemap.xml").read_text(encoding="utf-8", errors="ignore")
    go_pages = sorted((SITE / "go").glob("*/index.html")) if (SITE / "go").exists() else []

    add_row(rows, "sitemap_has_no_go", "/go/" not in sitemap_text, "sitemap.xml must not include tracking URLs")
    if "/go/" in sitemap_text:
        errors.append("sitemap contains /go/ URLs")
    add_row(rows, "go_pages_exist", len(go_pages) > 0, f"{len(go_pages)} go tracking pages")
    if not go_pages:
        errors.append("no /go/ tracking pages found")

    missing_sitemap_targets = validate_sitemap_targets(sitemap_urls)
    for item in missing_sitemap_targets:
        errors.append(item)
    add_row(rows, "sitemap_targets_exist", not missing_sitemap_targets, f"{len(sitemap_urls)} sitemap URLs checked")

    placeholder_hits = scan_placeholders(html_files)
    for hit in placeholder_hits:
        errors.append(hit)
    add_row(rows, "placeholder_scan", not placeholder_hits, f"{len(placeholder_hits)} placeholder hits")

    metadata_errors = validate_metadata(html_files)
    for item in metadata_errors:
        errors.append(item)
    add_row(rows, "metadata_scan", not metadata_errors, f"{len(metadata_errors)} canonical/meta issues")

    robots_errors = validate_robots_policy(SITE / "robots.txt")
    for item in robots_errors:
        errors.append(item)
    add_row(rows, "robots_indexing_policy", not robots_errors, f"{len(robots_errors)} robots policy issues")

    robots_meta_errors = validate_robots_meta_policy(html_files)
    for item in robots_meta_errors:
        errors.append(item)
    add_row(rows, "robots_meta_policy", not robots_meta_errors, f"{len(robots_meta_errors)} robots meta issues")

    broken_links = validate_internal_links(html_files)
    for item in broken_links:
        errors.append(item)
    add_row(rows, "internal_link_scan", not broken_links, f"{len(broken_links)} broken internal links")

    tracking_errors = validate_tracking_outputs()
    for item in tracking_errors:
        errors.append(item)
    add_row(rows, "affiliate_tracking_outputs", not tracking_errors, f"{len(tracking_errors)} tracking report issues")

    keyword_errors = validate_keyword_report()
    for item in keyword_errors:
        errors.append(item)
    add_row(rows, "keyword_intelligence_report", not keyword_errors, f"{len(keyword_errors)} keyword report issues")

    counts = page_counts(html_files, sitemap_urls, go_pages)
    for key, value in counts.items():
        add_row(rows, key, True, str(value))

    write_outputs(rows, errors, warnings, counts)
    print_result(errors, warnings, counts)
    return 1 if errors else 0


def add_row(rows: list[CheckRow], check: str, ok: bool, details: str) -> None:
    rows.append(CheckRow(check=check, status="PASS" if ok else "FAIL", details=details))


def parse_sitemap(path: Path) -> list[str]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    urls = []
    for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
        if loc.text:
            urls.append(loc.text.strip())
    return urls


def validate_sitemap_targets(urls: list[str]) -> list[str]:
    errors = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != "smileaireviewhub.com":
            errors.append(f"sitemap external/unexpected host: {url}")
            continue
        path = parsed.path or "/"
        if path == "/":
            target = SITE / "index.html"
        else:
            target = SITE / path.strip("/") / "index.html"
        if not target.exists():
            errors.append(f"sitemap URL missing file: {url}")
    return errors


def scan_placeholders(html_files: list[Path]) -> list[str]:
    hits = []
    for file in html_files:
        rel = file.relative_to(SITE).as_posix()
        text = file.read_text(encoding="utf-8", errors="ignore")
        visible = strip_scripts_styles_comments(text).lower()
        for pattern in PLACEHOLDER_PATTERNS:
            if re.search(pattern, visible, flags=re.IGNORECASE):
                hits.append(f"{rel}: placeholder pattern {pattern}")
    return hits


def validate_metadata(html_files: list[Path]) -> list[str]:
    errors = []
    for file in html_files:
        rel = file.relative_to(SITE).as_posix()
        if rel.startswith("go/") or is_verification_file(rel):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        if '<link rel="canonical"' not in text:
            errors.append(f"{rel}: missing canonical")
        if 'name="description"' not in text:
            errors.append(f"{rel}: missing meta description")
    return errors


def validate_robots_policy(path: Path) -> list[str]:
    if not path.exists():
        return ["robots.txt missing"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors = []
    if "User-agent: *" not in text:
        errors.append("robots.txt missing User-agent: *")
    if "Allow: /" not in text:
        errors.append("robots.txt missing Allow: /")
    if re.search(r"(?im)^\s*Disallow\s*:", text):
        errors.append("robots.txt contains Disallow directive")
    if f"Sitemap: {BASE_URL}/sitemap.xml" not in text:
        errors.append("robots.txt missing canonical sitemap reference")
    return errors


def validate_robots_meta_policy(html_files: list[Path]) -> list[str]:
    errors = []
    for file in html_files:
        text = file.read_text(encoding="utf-8", errors="ignore")
        rel = file.relative_to(SITE).as_posix()
        if is_verification_file(rel):
            continue
        page_path = rel_path_for_html(file, SITE)
        match = re.search(r"<meta[^>]+name=['\"]robots['\"][^>]+content=['\"]([^'\"]+)['\"]", text, flags=re.I)
        robots = (match.group(1).strip().lower() if match else "")
        if is_redirect_page(page_path):
            if "noindex" not in robots or "follow" not in robots or "nofollow" in robots:
                errors.append(f"{rel}: redirect page must use robots noindex,follow")
            continue
        if "noindex" in robots:
            errors.append(f"{rel}: non-redirect page contains robots noindex")
        if not robots:
            errors.append(f"{rel}: missing robots meta")
    return errors


def is_verification_file(rel: str) -> bool:
    return bool(re.fullmatch(r"(?:yandex_[a-z0-9]+|BingSiteAuth)\.html", rel, flags=re.I))


def validate_internal_links(html_files: list[Path]) -> list[str]:
    errors = []
    for file in html_files:
        rel = file.relative_to(SITE).as_posix()
        text = file.read_text(encoding="utf-8", errors="ignore")
        parser = LinkParser()
        parser.feed(text)
        for link in parser.links:
            normalized = normalize_internal_link(link)
            if not normalized:
                continue
            if normalized.startswith(SKIP_LINK_PREFIXES):
                continue
            target = SITE / normalized.strip("/")
            if normalized.endswith("/") or "." not in Path(normalized).name:
                target = target / "index.html"
            if not target.exists():
                errors.append(f"{rel}: broken internal link {link}")
    return sorted(set(errors))


def validate_tracking_outputs() -> list[str]:
    errors = []
    redirect_path = DATA / "redirect_map.csv"
    report_path = DATA / "affiliate_tracking_report.csv"
    if not redirect_path.exists():
        errors.append("missing data/redirect_map.csv")
        return errors
    if not report_path.exists():
        errors.append("missing data/affiliate_tracking_report.csv")
    try:
        with redirect_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        return [f"redirect_map.csv unreadable: {exc}"]
    ids = [str(row.get("tracking_id", "")).strip() for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("redirect_map.csv has duplicate tracking_id")
    for row in rows:
        tracking_id = str(row.get("tracking_id", "")).strip()
        tracked_url = str(row.get("tracked_url", "")).strip()
        if not tracking_id:
            errors.append("redirect_map.csv row missing tracking_id")
            continue
        if not tracked_url:
            errors.append(f"redirect_map.csv {tracking_id}: empty tracked_url")
        if not (SITE / "go" / tracking_id / "index.html").exists():
            errors.append(f"redirect page missing: /go/{tracking_id}/")
    sitemap_text = (SITE / "sitemap.xml").read_text(encoding="utf-8", errors="ignore") if (SITE / "sitemap.xml").exists() else ""
    if "/go/" in sitemap_text:
        errors.append("sitemap contains /go/ URLs")
    return errors


def validate_keyword_report() -> list[str]:
    path = DATA / "keyword_intelligence_report.csv"
    if not path.exists():
        return ["missing data/keyword_intelligence_report.csv"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        return [f"keyword_intelligence_report.csv unreadable: {exc}"]
    if not rows:
        return ["keyword_intelligence_report.csv is empty"]
    required = {"keyword", "topic_cluster", "intent", "priority_score", "content_gap", "next_action"}
    missing = required - set(rows[0].keys())
    return [f"keyword_intelligence_report.csv missing columns: {', '.join(sorted(missing))}"] if missing else []


def normalize_internal_link(link: str) -> str:
    if not link.startswith("/") or link.startswith("//"):
        return ""
    return link.split("#")[0].split("?")[0] or "/"


def strip_scripts_styles_comments(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def page_counts(html_files: list[Path], sitemap_urls: list[str], go_pages: list[Path]) -> dict[str, int]:
    rels = [file.relative_to(SITE).as_posix() for file in html_files]
    return {
        "homepage": 1 if (SITE / "index.html").exists() else 0,
        "review_pages": count_prefix(rels, "review/"),
        "comparison_pages": count_prefix(rels, "compare/") + count_prefix(rels, "comparisons/") - (1 if "comparisons/index.html" in rels else 0),
        "pricing_pages": count_prefix(rels, "pricing/") - (1 if "pricing/index.html" in rels else 0),
        "category_pages": count_prefix(rels, "category/") + (1 if "categories/index.html" in rels else 0),
        "hub_pages": count_prefix(rels, "hub/") + (1 if "hubs/index.html" in rels else 0),
        "priority_pages": count_priority_pages(),
        "go_tracking_pages": len(go_pages),
        "total_sitemap_urls": len(sitemap_urls),
        "total_html_files": len(html_files),
    }


def count_prefix(rels: list[str], prefix: str) -> int:
    return sum(1 for rel in rels if rel.startswith(prefix) and rel.endswith("/index.html"))


def count_priority_pages() -> int:
    index = DATA / "priority_pages_index.csv"
    if not index.exists():
        return 0
    try:
        with index.open(newline="", encoding="utf-8") as handle:
            return max(sum(1 for _ in csv.DictReader(handle)), 0)
    except Exception:
        return 0


def write_outputs(rows: list[CheckRow], errors: list[str], warnings: list[str], counts: dict[str, int]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with REPORT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "details"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    summary = [
        "FINAL PREDEPLOY CHECK",
        f"status: {'FAIL' if errors else 'PASS'}",
        f"errors: {len(errors)}",
        f"warnings: {len(warnings)}",
        "",
        "COUNTS",
    ]
    for key, value in counts.items():
        summary.append(f"- {key}: {value}")
    summary.extend(["", "ERRORS"])
    summary.extend([f"- {error}" for error in errors] or ["- none"])
    summary.extend(["", "WARNINGS"])
    summary.extend([f"- {warning}" for warning in warnings] or ["- none"])
    SUMMARY_TXT.write_text("\n".join(summary) + "\n", encoding="utf-8")


def print_result(errors: list[str], warnings: list[str], counts: dict[str, int]) -> None:
    status = "FAIL" if errors else "PASS"
    print(f"Final predeploy check: {status}")
    for key in [
        "total_html_files",
        "total_sitemap_urls",
        "go_tracking_pages",
        "review_pages",
        "comparison_pages",
        "pricing_pages",
        "category_pages",
        "hub_pages",
        "priority_pages",
    ]:
        if key in counts:
            print(f"- {key}: {counts[key]}")
    print(f"- broken_internal_links: {sum(1 for error in errors if 'broken internal link' in error)}")
    print(f"- placeholder_count: {sum(1 for error in errors if 'placeholder pattern' in error)}")
    print(f"- report_csv: {REPORT_CSV}")
    print(f"- summary_txt: {SUMMARY_TXT}")
    if errors:
        print("Top errors:")
        for error in errors[:20]:
            print(f"- {error}")


if __name__ == "__main__":
    sys.exit(main())
