from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
DATA = ROOT / "data"
BASE_URL = "https://smileaireviewhub.com"

CHANNELS = ["Facebook", "LinkedIn", "X", "Quora", "DEV", "Reddit", "Qiita", "Hashnode", "Velog"]
COMMON_ENGLISH_UI = [
    "Affiliate disclosure",
    "Quick Verdict",
    "Comparison Table",
    "Visit Official Website",
    "Check Current Pricing",
    "Compare Alternatives",
    "Research Methodology",
    "Community Channels",
    "Our Community Signals",
    "Pricing checked",
    "Documentation reviewed",
    "Community feedback reviewed",
    "Tool A score",
    "Tool B score",
    "Visual comparison table",
]


def visible_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def url_for_page(path: Path) -> str:
    rel = path.relative_to(SITE).as_posix()
    if rel == "index.html":
        return BASE_URL + "/"
    return BASE_URL + "/" + rel.removesuffix("index.html")


def is_content_page(path: Path) -> bool:
    rel = path.relative_to(SITE).as_posix()
    return not rel.startswith(("assets/", "go/"))


def is_comparison_page(path: Path) -> bool:
    rel = path.relative_to(SITE).as_posix().removeprefix("vi/")
    if rel in {"comparisons/index.html", "compare/index.html"}:
        return False
    return rel.startswith(("comparisons/", "compare/"))


def main() -> None:
    if not SITE.exists():
        raise SystemExit("site_output does not exist. Run the build first.")
    errors: list[str] = []
    urls: list[str] = []
    pages = sorted(SITE.rglob("index.html"))
    for page in pages:
        if not is_content_page(page):
            continue
        html = page.read_text(encoding="utf-8", errors="ignore")
        text = visible_text(html)
        rel = page.relative_to(SITE).as_posix()
        urls.append(url_for_page(page))
        if "community-channel-list" not in html:
            errors.append(f"{rel}: missing global community footer")
        for channel in CHANNELS:
            if channel not in html:
                errors.append(f"{rel}: footer missing {channel}")
        if not re.search(r"<section\b[^>]*\bauthor-trust-card\b", html, flags=re.I):
            errors.append(f"{rel}: missing author box")
        if not re.search(r"<section\b[^>]*\bresearch-methodology\b", html, flags=re.I):
            errors.append(f"{rel}: missing research methodology")
        if not re.search(r"<section\b[^>]*\bcommunity-signals\b", html, flags=re.I):
            errors.append(f"{rel}: missing community proof")
        if is_comparison_page(page) and not re.search(r"<section\b[^>]*\bcomparison-scorecard\b", html, flags=re.I):
            errors.append(f"{rel}: missing comparison scorecard")
        if rel.startswith("vi/"):
            for phrase in COMMON_ENGLISH_UI:
                if phrase in text:
                    errors.append(f"{rel}: Vietnamese page still contains English UI phrase: {phrase}")

    DATA.mkdir(parents=True, exist_ok=True)
    report = DATA / "regenerated_urls_trust_localization.csv"
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["url"])
        for url in urls:
            writer.writerow([url])

    if errors:
        print("Trust/localization verification failed:")
        for error in errors[:200]:
            print(f"- {error}")
        if len(errors) > 200:
            print(f"- ... {len(errors) - 200} more")
        raise SystemExit(1)
    print(f"Trust/localization verification passed for {len(urls)} pages.")
    print(f"Regenerated URL report: {report}")


if __name__ == "__main__":
    main()
