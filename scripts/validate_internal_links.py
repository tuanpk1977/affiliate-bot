from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
SKIP_PREFIXES = ("/assets/", "/rss.xml", "/sitemap.xml", "/robots.txt", "/llms.txt")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        if href:
            self.links.append(href)


def normalize(link: str) -> str:
    if not link.startswith("/") or link.startswith("//"):
        return ""
    return link.split("#", 1)[0].split("?", 1)[0]


def target_for(link: str) -> Path | None:
    normalized = normalize(link)
    if not normalized or normalized.startswith(SKIP_PREFIXES):
        return None
    if normalized == "/":
        return SITE / "index.html"
    path = SITE / normalized.strip("/")
    if "." in path.name:
        return path
    return path / "index.html"


def main() -> int:
    if not SITE.exists():
        print("site_output does not exist. Run python main.py first.")
        return 1
    errors: list[str] = []
    html_files = sorted(SITE.rglob("*.html"))
    for file in html_files:
        rel = file.relative_to(SITE).as_posix()
        text = file.read_text(encoding="utf-8", errors="ignore")
        parser = LinkParser()
        parser.feed(text)
        for link in parser.links:
            target = target_for(link)
            if target is not None and not target.exists():
                errors.append(f"{rel}: broken internal link {link}")
    if errors:
        print("Internal link validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Internal link validation passed. Checked {len(html_files)} HTML files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
