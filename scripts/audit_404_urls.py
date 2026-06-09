from __future__ import annotations

import csv
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
BASE_URL = "https://smileaireviewhub.com"
FULL_REPORT = ROOT / "data" / "url_status_audit_report.csv"
ERROR_REPORT = ROOT / "data" / "url_current_404_report.csv"
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def normalize_internal_url(value: str) -> str:
    value = value.strip()
    if not value or value.startswith(("#", "//", *SKIP_SCHEMES)):
        return ""
    absolute = urllib.parse.urljoin(f"{BASE_URL}/", value)
    parsed = urllib.parse.urlsplit(absolute)
    if parsed.netloc.lower() not in {"smileaireviewhub.com", "www.smileaireviewhub.com"}:
        return ""
    path = parsed.path or "/"
    return urllib.parse.urlunsplit(("https", "smileaireviewhub.com", path, "", ""))


def sitemap_urls() -> set[str]:
    path = SITE / "sitemap.xml"
    root = ET.parse(path).getroot()
    return {
        normalize_internal_url(node.text or "")
        for node in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        if normalize_internal_url(node.text or "")
    }


def internal_urls() -> set[str]:
    urls: set[str] = set()
    for path in SITE.rglob("*.html"):
        parser = LinkParser()
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        urls.update(filter(None, (normalize_internal_url(link) for link in parser.links)))
    return urls


def local_target(url: str) -> Path:
    path = urllib.parse.urlsplit(url).path
    if path == "/":
        return SITE / "index.html"
    relative = path.strip("/")
    direct = SITE / relative
    if direct.suffix:
        return direct
    return direct / "index.html"


def check_http(url: str) -> tuple[str, str, str]:
    headers = {"User-Agent": "SmileAIReviewHub-404-Audit/1.0"}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            final_url = response.geturl()
            redirect = final_url if final_url.rstrip("/") != url.rstrip("/") else ""
            return url, str(response.status), redirect
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 405}:
            try:
                request = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(request, timeout=20) as response:
                    final_url = response.geturl()
                    redirect = final_url if final_url.rstrip("/") != url.rstrip("/") else ""
                    return url, str(response.status), redirect
            except urllib.error.HTTPError as get_exc:
                return url, str(get_exc.code), get_exc.headers.get("Location", "")
            except Exception as get_exc:  # noqa: BLE001
                return url, "ERROR", str(get_exc)
        return url, str(exc.code), exc.headers.get("Location", "")
    except Exception as exc:  # noqa: BLE001
        return url, "ERROR", str(exc)


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["URL", "StatusCode", "RedirectTarget"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    public = "--public" in sys.argv
    sitemap = sitemap_urls()
    internal = internal_urls()
    urls = sorted(sitemap | internal)

    local_404s = sorted(url for url in urls if not local_target(url).exists())
    rows: list[dict[str, str]] = []

    if public:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(check_http, url): url for url in urls}
            for future in as_completed(futures):
                url, status, target = future.result()
                rows.append({"URL": url, "StatusCode": status, "RedirectTarget": target})
        rows.sort(key=lambda row: row["URL"])
    else:
        rows = [
            {
                "URL": url,
                "StatusCode": "200" if local_target(url).exists() else "404",
                "RedirectTarget": "",
            }
            for url in urls
        ]

    errors = [row for row in rows if row["StatusCode"] in {"404", "410", "ERROR"}]
    write_report(FULL_REPORT, rows)
    write_report(ERROR_REPORT, errors)

    print(f"Sitemap URLs: {len(sitemap)}")
    print(f"Unique internal URLs: {len(internal)}")
    print(f"Audited URLs: {len(urls)}")
    print(f"Local missing targets: {len(local_404s)}")
    for url in local_404s:
        print(f"- {url}")
    print(f"404/error rows: {len(errors)}")
    print(f"Full report: {FULL_REPORT}")
    print(f"404 report: {ERROR_REPORT}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
