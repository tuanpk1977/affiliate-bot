from __future__ import annotations

import csv
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_OUTPUT = ROOT / "site_output"
REPORT_PATH = ROOT / "data" / "social_preview_report.csv"


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        content = values.get("content", "").strip()
        if not content:
            return
        key = values.get("property") or values.get("name")
        if key:
            self.meta[key.strip().lower()] = content


def page_url(path: Path) -> str:
    relative = path.relative_to(SITE_OUTPUT)
    if relative.name.lower() == "index.html":
        parent = relative.parent.as_posix().strip("/")
        return "/" if not parent else f"/{parent}/"
    return f"/{relative.as_posix()}"


def check_page(path: Path) -> dict[str, str]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    parser = MetaParser()
    parser.feed(html)
    required = [
        "og:title",
        "og:description",
        "og:image",
        "og:url",
        "og:type",
        "twitter:card",
        "twitter:title",
        "twitter:description",
        "twitter:image",
    ]
    missing = [key for key in required if not parser.meta.get(key)]
    return {
        "url": page_url(path),
        "status": "PASS" if not missing else "WARNING",
        "missing": "|".join(missing),
        "og_title": parser.meta.get("og:title", ""),
        "og_description": parser.meta.get("og:description", ""),
        "og_image": parser.meta.get("og:image", ""),
        "og_url": parser.meta.get("og:url", ""),
        "og_type": parser.meta.get("og:type", ""),
        "twitter_card": parser.meta.get("twitter:card", ""),
        "twitter_title": parser.meta.get("twitter:title", ""),
        "twitter_description": parser.meta.get("twitter:description", ""),
        "twitter_image": parser.meta.get("twitter:image", ""),
    }


def main() -> int:
    if not SITE_OUTPUT.exists():
        print("WARNING: site_output does not exist")
        return 1
    rows = []
    for path in sorted(SITE_OUTPUT.rglob("*.html")):
        rel = path.relative_to(SITE_OUTPUT).as_posix()
        if rel.startswith("go/"):
            continue
        rows.append(check_page(path))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "url",
                "status",
                "missing",
                "og_title",
                "og_description",
                "og_image",
                "og_url",
                "og_type",
                "twitter_card",
                "twitter_title",
                "twitter_description",
                "twitter_image",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    warning_count = sum(1 for row in rows if row["status"] == "WARNING")
    print(f"Checked {len(rows)} HTML pages")
    print(f"PASS: {len(rows) - warning_count}")
    print(f"WARNING: {warning_count}")
    print(f"Report: {REPORT_PATH}")
    return 0 if warning_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
