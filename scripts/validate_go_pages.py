from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
AFFILIATE_LINKS = ROOT / "data" / "affiliate_links.csv"
SITEMAP = SITE / "sitemap.xml"


def main() -> int:
    errors: list[str] = []
    if not SITE.exists():
        return fail(["site_output does not exist. Run python main.py first."])
    if not AFFILIATE_LINKS.exists():
        return fail(["data/affiliate_links.csv does not exist."])

    links = pd.read_csv(AFFILIATE_LINKS).fillna("")
    slugs = sorted({str(row.get("tool_slug") or row.get("slug") or "").strip() for _, row in links.iterrows() if str(row.get("tool_slug") or row.get("slug") or "").strip()})

    required_examples = {"cursor", "github-copilot", "semrush"}
    if len(slugs) < 27:
        errors.append(f"expected at least 27 tracking pages from affiliate_links.csv, found {len(slugs)}")

    for slug in sorted(required_examples | set(slugs)):
        go_file = SITE / "go" / slug / "index.html"
        if not go_file.exists():
            errors.append(f"missing /go/{slug}/ index file")
            continue
        text = go_file.read_text(encoding="utf-8", errors="ignore")
        for needle in [
            "sendTrackingEvent",
            "sendDirectWebhook",
            "redirectAfterTracking",
            "debug-payload",
            "webhook_url_configured",
            "debug-webhook-status",
            "debug-function-status",
            "fallbackWebhookUrl",
        ]:
            if needle not in text:
                errors.append(f"/go/{slug}/ missing {needle}")
        if '"target_url": ""' in text or '"target_url":""' in text:
            errors.append(f"/go/{slug}/ has empty target_url")

    if SITEMAP.exists():
        sitemap_text = SITEMAP.read_text(encoding="utf-8", errors="ignore")
        if "/go/" in sitemap_text:
            errors.append("sitemap.xml contains /go/ tracking URLs")
    else:
        errors.append("site_output/sitemap.xml does not exist")

    for slug in required_examples:
        review = SITE / slug / "index.html"
        if not review.exists():
            errors.append(f"missing review page /{slug}/")
            continue
        review_text = review.read_text(encoding="utf-8", errors="ignore")
        if f'href="/go/{slug}/' not in review_text and f"href='/go/{slug}/" not in review_text:
            errors.append(f"/{slug}/ review page does not link to /go/{slug}/")

    if errors:
        return fail(errors)
    print(f"Go page validation passed. Checked {len(slugs)} tracking pages.")
    return 0


def fail(errors: list[str]) -> int:
    print("Go page validation failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
