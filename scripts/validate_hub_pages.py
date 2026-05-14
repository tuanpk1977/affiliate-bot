from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
INDEX = DATA / "hub_pages_index.csv"
OUTPUT = DATA / "hub_pages_qa.csv"
SITEMAP = SITE / "sitemap.xml"
DOMAIN = "https://review.mssmileenglish.com"


@dataclass
class HubQaRow:
    hub_slug: str
    url_path: str
    status: str
    has_file: bool
    has_h1: bool
    has_meta_description: bool
    has_schema: bool
    internal_link_count: int
    in_sitemap: bool
    passed: bool
    issue: str


def fail(message: str) -> None:
    print(f"Hub page validation failed: {message}")
    raise SystemExit(1)


def page_path(slug: str) -> Path:
    if slug == "hubs":
        return SITE / "hubs" / "index.html"
    return SITE / "hub" / slug / "index.html"


def url_path(slug: str) -> str:
    if slug == "hubs":
        return "/hubs/"
    return f"/hub/{slug}/"


def validate_row(row: pd.Series, sitemap_text: str) -> HubQaRow:
    slug = str(row.get("hub_slug", "")).strip("/")
    path = page_path(slug)
    issues: list[str] = []
    text = ""
    if not path.exists():
        issues.append("missing_file")
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")

    has_h1 = bool(re.search(r"<h1\b", text, re.IGNORECASE))
    has_meta = 'name="description"' in text
    has_schema = "application/ld+json" in text and '"@type": "BreadcrumbList"' in text
    links = {
        link.split("#")[0].split("?")[0]
        for link in re.findall(r"href=['\"]([^'\"]+)['\"]", text)
        if link.startswith("/") and not link.startswith(("/assets/", "//"))
    }
    current = url_path(slug)
    links.discard(current)
    in_sitemap = f"{DOMAIN}{current}" in sitemap_text

    if not has_h1:
        issues.append("missing_h1")
    if not has_meta:
        issues.append("missing_meta_description")
    if not has_schema:
        issues.append("missing_breadcrumb_schema")
    if len(links) < 5:
        issues.append("fewer_than_5_internal_links")
    if not in_sitemap:
        issues.append("missing_from_sitemap")

    return HubQaRow(
        hub_slug=slug,
        url_path=current,
        status=str(row.get("status", "")),
        has_file=path.exists(),
        has_h1=has_h1,
        has_meta_description=has_meta,
        has_schema=has_schema,
        internal_link_count=len(links),
        in_sitemap=in_sitemap,
        passed=not issues,
        issue="|".join(issues) or "ok",
    )


def main() -> int:
    if not INDEX.exists():
        fail("missing data/hub_pages_index.csv")
    if not SITEMAP.exists():
        fail("missing site_output/sitemap.xml")
    df = pd.read_csv(INDEX).fillna("")
    required = {"hub_slug", "hub_title", "output_path", "status"}
    missing = required.difference(df.columns)
    if missing:
        fail(f"missing hub index columns: {', '.join(sorted(missing))}")

    sitemap_text = SITEMAP.read_text(encoding="utf-8", errors="ignore")
    if "/go/" in sitemap_text:
        fail("sitemap contains /go/")
    results = [validate_row(row, sitemap_text) for _, row in df.iterrows()]

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(HubQaRow.__dataclass_fields__.keys()))
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)

    failed = [result for result in results if not result.passed]
    print(f"Hub page validation checked {len(results)} pages")
    print(f"Output: {OUTPUT}")
    if failed:
        for result in failed:
            print(f"- FAIL {result.url_path}: {result.issue}")
        return 1
    print("Hub page validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
