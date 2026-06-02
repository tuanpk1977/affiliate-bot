from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


VIEWPORTS = [1366, 1440, 1920, 375, 768]
PAGES = [
    ("runway", Path("site_output/runway/index.html"), "legacy_review"),
    ("review_chatgpt", Path("site_output/review/chatgpt/index.html"), "programmatic_review"),
    ("review_cursor", Path("site_output/review/cursor/index.html"), "programmatic_review"),
    ("review_zapier", Path("site_output/review/zapier/index.html"), "programmatic_review"),
]


def main() -> int:
    output = Path("data/layout_audit_report.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    failures: list[str] = []

    for page_name, path, page_type in PAGES:
        text = path.read_text(encoding="utf-8", errors="ignore")
        css = extract_css(text)
        page_failures = audit_page(page_name, page_type, text, css)
        failures.extend(page_failures)
        screenshot_count = text.count('class="screenshot"') + text.count("class='screenshot'")
        for viewport in VIEWPORTS:
            wrap_width = min(viewport, 1120)
            content_width = max(0, wrap_width - 40)
            card_content_width = max(0, content_width - 36)
            if page_name == "runway":
                image_width = card_content_width if viewport <= 900 else max(0, card_content_width - 260 - 16)
                grid = "single content column; rating image/text split only above 900px"
            else:
                image_width = card_content_width if viewport <= 760 else max(0, (card_content_width - 14) / 2)
                grid = "single content column; visual cards split only above 760px"
            rows.append(
                {
                    "page": page_name,
                    "viewport_px": str(viewport),
                    "wrap_width_px": f"{wrap_width:.0f}",
                    "content_width_px": f"{content_width:.0f}",
                    "max_screenshot_width_px": f"{image_width:.0f}",
                    "grid_behavior": grid,
                    "screenshots_found": str(screenshot_count),
                    "overflow_risk": "no" if not page_failures else "review",
                }
            )

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "page",
                "viewport_px",
                "wrap_width_px",
                "content_width_px",
                "max_screenshot_width_px",
                "grid_behavior",
                "screenshots_found",
                "overflow_risk",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Layout audit report: {output}")
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS")
    print(f"Audited {len(PAGES)} pages across {len(VIEWPORTS)} viewport widths.")
    return 0


def extract_css(text: str) -> str:
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, flags=re.DOTALL | re.IGNORECASE))


def audit_page(page_name: str, page_type: str, text: str, css: str) -> list[str]:
    failures: list[str] = []
    if ".wrap{max-width:1120px" not in compact(css):
        failures.append(f"{page_name}: missing shared 1120px wrapper")
    if "overflow-wrap:break-word" not in css and page_type == "legacy_review":
        failures.append(f"{page_name}: legacy cards do not protect long text")
    if page_type == "legacy_review":
        if "grid-template-columns:1.5fr .9fr" in css:
            failures.append(f"{page_name}: old two-column hero grid still present")
        if ".hero-grid{display:grid;grid-template-columns:minmax(0,1fr)" not in compact(css):
            failures.append(f"{page_name}: hero grid is not normalized to one column")
        if ".review-layout{display:grid;grid-template-columns:minmax(0,1fr)" not in compact(css):
            failures.append(f"{page_name}: review layout is not normalized to one column")
        if ".rating-summary{display:grid;grid-template-columns:minmax(0,1fr)260px" not in compact(css):
            failures.append(f"{page_name}: rating summary does not use bounded grid")
        if "object-fit:contain" not in css or "height:auto" not in css or "max-width:100%" not in css:
            failures.append(f"{page_name}: screenshot sizing can still clip or overflow")
        if 'class="card rating-summary"' not in text:
            failures.append(f"{page_name}: rating summary markup was not updated")
    else:
        if ".visual-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" not in compact(css):
            failures.append(f"{page_name}: programmatic visual grid differs from expected review layout")
        if "@media(max-width:760px)" not in compact(css):
            failures.append(f"{page_name}: mobile breakpoint missing")
        if ".visual-cardimg{width:100%;height:auto" not in compact(css):
            failures.append(f"{page_name}: visual images are not fluid")
    return failures


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


if __name__ == "__main__":
    sys.exit(main())
