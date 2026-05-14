from __future__ import annotations

import csv
import shutil
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from config import settings
from modules.content_approval import DRAFT_COLUMNS, load_review_queue


APPROVAL_COLUMNS = [
    "draft_id",
    "title",
    "slug",
    "content_type",
    "category",
    "status",
    "screenshot",
    "word_count",
    "cta_count",
    "internal_link_count",
    "quality_status",
    "quality_issues",
    "preview_path",
]

IMAGE_COLUMNS = ["page_path", "tool_slug", "tool_name", "image_path", "status", "alt_text"]
WORKFLOW_COLUMNS = ["area", "status", "details", "module_or_file"]


@dataclass
class PageAudit:
    rel: str
    title: str
    meta_description: str
    h1: str
    links: list[str]
    text: str


class AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.in_title = False
        self.in_h1 = False
        self.title = ""
        self.h1 = ""
        self.meta_description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.in_h1 = True
        if tag == "meta" and attrs_dict.get("name") == "description":
            self.meta_description = attrs_dict.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "h1":
            self.in_h1 = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.in_h1:
            self.h1 += data


def run_review_workflow_audit() -> dict[str, int]:
    draft_output = settings.base_dir / "draft_output"
    review_dashboard = draft_output / "review_dashboard"
    draft_output.mkdir(parents=True, exist_ok=True)
    review_dashboard.mkdir(parents=True, exist_ok=True)
    copy_draft_assets(draft_output)

    drafts = load_review_queue()
    approval_queue, approved_pages = split_approval_data(drafts)
    approval_queue = enrich_queue(approval_queue, draft_output)
    approved_pages = enrich_queue(approved_pages, draft_output)

    write_csv(settings.data_dir / "approval_queue.csv", approval_queue, APPROVAL_COLUMNS)
    write_csv(settings.data_dir / "approved_pages.csv", approved_pages, APPROVAL_COLUMNS)

    workflow_rows = workflow_audit_rows(drafts, approval_queue, approved_pages)
    write_csv(settings.data_dir / "draft_publish_workflow_report.csv", workflow_rows, WORKFLOW_COLUMNS)

    image_rows = image_usage_rows()
    write_csv(settings.data_dir / "image_usage_report.csv", image_rows, IMAGE_COLUMNS)
    missing_rows = [row for row in image_rows if row["status"] == "missing_image"]
    write_csv(settings.data_dir / "missing_images_report.csv", missing_rows, IMAGE_COLUMNS)

    write_review_dashboard(review_dashboard / "index.html", approval_queue, approved_pages, image_rows, workflow_rows)
    write_review_dashboard(draft_output / "admin_review.html", approval_queue, approved_pages, image_rows, workflow_rows)
    write_summary(approval_queue, approved_pages, missing_rows, workflow_rows)

    return {
        "pending": len(approval_queue),
        "approved": len(approved_pages),
        "missing_images": len(missing_rows),
    }


def split_approval_data(drafts: pd.DataFrame) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if drafts is None or drafts.empty:
        return [], []
    pending_statuses = {"Draft", "Pending Review", "Need Edit"}
    approved_statuses = {"Approved", "Published"}
    pending = []
    approved = []
    for _, row in drafts.fillna("").iterrows():
        record = draft_to_record(row.to_dict())
        status = record["status"]
        if status in pending_statuses:
            pending.append(record)
        elif status in approved_statuses:
            approved.append(record)
    return pending, approved


def draft_to_record(row: dict[str, str]) -> dict[str, str]:
    title = str(row.get("title", "")).strip()
    slug = slugify(str(row.get("slug") or title))
    content_type = str(row.get("content_type", "")).strip()
    content = str(row.get("draft_content", "") or "")
    category = category_from_content_type(content_type, title, content)
    screenshot = screenshot_for_slug(slug)
    issues = quality_issues(title, slug, content, screenshot)
    return {
        "draft_id": str(row.get("draft_id", "")).strip(),
        "title": title,
        "slug": slug,
        "content_type": content_type,
        "category": category,
        "status": str(row.get("status", "")).strip(),
        "screenshot": screenshot,
        "word_count": str(word_count(content)),
        "cta_count": str(count_cta(content)),
        "internal_link_count": str(count_internal_links(content)),
        "quality_status": "blocked" if issues else "ready_for_review",
        "quality_issues": " | ".join(issues),
        "preview_path": "",
    }


def enrich_queue(rows: list[dict[str, str]], draft_output: Path) -> list[dict[str, str]]:
    for row in rows:
        preview_dir = draft_output / "pages" / row["slug"]
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_file = preview_dir / "index.html"
        preview_file.write_text(render_draft_preview(row), encoding="utf-8")
        row["preview_path"] = str(preview_file)
    return rows


def render_draft_preview(row: dict[str, str]) -> str:
    screenshot = row.get("screenshot", "")
    image = ""
    if screenshot:
        src = f"../../assets/screenshots/{html.escape(Path(screenshot).name)}"
        image = f"<img src='{src}' alt='{html.escape(row['title'])} screenshot' width='1200' height='720' loading='lazy' style='max-width:100%;height:auto;border-radius:8px;border:1px solid #dbe3ef'>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(row['title'])} - Draft Preview</title><style>{dashboard_css()}</style></head><body><main class="wrap"><section class="card"><p class="badge">{html.escape(row['status'])}</p><h1>{html.escape(row['title'])}</h1><p><strong>Slug:</strong> {html.escape(row['slug'])}</p><p><strong>Category:</strong> {html.escape(row['category'])}</p>{image}<p><strong>Quality:</strong> {html.escape(row['quality_status'])}</p><p>{html.escape(row['quality_issues'] or 'No blocking issue found by local guardrails.')}</p></section></main></body></html>"""


def workflow_audit_rows(drafts: pd.DataFrame, pending: list[dict[str, str]], approved: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"area": "draft_output", "status": "exists", "details": "Draft preview pages are written to draft_output/pages/ and are not included in sitemap.", "module_or_file": "modules/review_workflow.py"},
        {"area": "review dashboard", "status": "exists", "details": "Static review dashboard is available at draft_output/admin_review.html and draft_output/review_dashboard/index.html.", "module_or_file": "modules/review_workflow.py"},
        {"area": "streamlit review dashboard", "status": "exists", "details": "Dashboard tab Duyệt nội dung can create, edit, approve, reject, and publish approved static drafts.", "module_or_file": "dashboard/app.py + modules/content_approval.py"},
        {"area": "approval queue", "status": "exists", "details": f"{len(pending)} pending/edit drafts exported to data/approval_queue.csv.", "module_or_file": "data/approval_queue.csv"},
        {"area": "approved pages", "status": "exists", "details": f"{len(approved)} approved/published drafts exported to data/approved_pages.csv.", "module_or_file": "data/approved_pages.csv"},
        {"area": "publish workflow", "status": "exists", "details": "Approved drafts can be published manually from dashboard only after quality guardrails pass; local static preview exists. Current generated site pages remain pipeline-managed.", "module_or_file": "modules/content_approval.py"},
        {"area": "quality guardrails", "status": "exists", "details": "Guardrails check screenshot, word count, CTA, internal links, duplicate title/meta, placeholders, and broken links for queue/reporting.", "module_or_file": "modules/review_workflow.py"},
        {"area": "content drafts source", "status": "exists" if not drafts.empty else "empty", "details": f"{len(drafts)} rows loaded from data/content_drafts.csv and affiliate_os_drafts.json import layer.", "module_or_file": "data/content_drafts.csv"},
    ]


def image_usage_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    site = settings.site_output_dir
    screenshots = settings.base_dir / "assets" / "screenshots"
    for page in sorted((site / "review").glob("*/index.html")):
        slug = page.parent.name
        title = title_from_page(page) or title_from_slug(slug)
        image_path = screenshots / f"{slug}.png"
        status = "ok" if image_path.exists() else "missing_image"
        rows.append(
            {
                "page_path": str(page),
                "tool_slug": slug,
                "tool_name": title.replace(" Review", "").split(" for ")[0],
                "image_path": str(image_path) if image_path.exists() else "",
                "status": status,
                "alt_text": f"{title_from_slug(slug)} dashboard screenshot",
            }
        )
    for page in sorted(site.glob("*/index.html")):
        slug = page.parent.name
        if slug in {"review", "go", "assets"} or page.parent == site:
            continue
        if slug in known_screenshot_slugs():
            image_path = screenshots / f"{slug}.png"
            rows.append(
                {
                    "page_path": str(page),
                    "tool_slug": slug,
                    "tool_name": title_from_slug(slug),
                    "image_path": str(image_path) if image_path.exists() else "",
                    "status": "ok" if image_path.exists() else "missing_image",
                    "alt_text": f"{title_from_slug(slug)} dashboard screenshot",
                }
            )
    return dedupe_rows(rows, ["page_path", "tool_slug"])


def write_review_dashboard(path: Path, pending: list[dict[str, str]], approved: list[dict[str, str]], image_rows: list[dict[str, str]], workflow_rows: list[dict[str, str]]) -> None:
    missing = [row for row in image_rows if row["status"] == "missing_image"]
    asset_prefix = "../assets/screenshots" if path.parent.name == "review_dashboard" else "assets/screenshots"
    cards = "".join(dashboard_card(row, asset_prefix) for row in pending + approved)
    workflow = "".join(f"<tr><td>{html.escape(row['area'])}</td><td>{html.escape(row['status'])}</td><td>{html.escape(row['details'])}</td><td>{html.escape(row['module_or_file'])}</td></tr>" for row in workflow_rows)
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Review Dashboard</title><style>{dashboard_css()}</style></head><body><main class="wrap"><section class="card"><h1>Local Review Dashboard</h1><p>This is a static local preview for draft -> review -> approve -> publish workflow. It does not publish or deploy anything.</p><div class="grid"><div class="metric"><strong>{len(pending)}</strong><span>Pending/Edit</span></div><div class="metric"><strong>{len(approved)}</strong><span>Approved/Published</span></div><div class="metric"><strong>{len(missing)}</strong><span>Missing screenshots</span></div></div></section><section class="card"><h2>Workflow audit</h2><table><thead><tr><th>Area</th><th>Status</th><th>Details</th><th>File/module</th></tr></thead><tbody>{workflow}</tbody></table></section><section><h2>Review queue</h2><div class="grid">{cards or '<p>No drafts in review queue.</p>'}</div></section></main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def dashboard_card(row: dict[str, str], asset_prefix: str) -> str:
    image = ""
    if row.get("screenshot"):
        image = f"<img src='{asset_prefix}/{html.escape(Path(row['screenshot']).name)}' alt='{html.escape(row['title'])} screenshot' width='1200' height='720' loading='lazy'>"
    return f"""<article class="card"><p class="badge">{html.escape(row['status'])}</p>{image}<h3>{html.escape(row['title'])}</h3><p><strong>Slug:</strong> {html.escape(row['slug'])}</p><p><strong>Category:</strong> {html.escape(row['category'])}</p><p><strong>CTA:</strong> {html.escape(row['cta_count'])} | <strong>Links:</strong> {html.escape(row['internal_link_count'])} | <strong>Words:</strong> {html.escape(row['word_count'])}</p><p><strong>Quality:</strong> {html.escape(row['quality_status'])}</p><p>{html.escape(row['quality_issues'] or 'Ready for human review.')}</p></article>"""


def write_summary(pending: list[dict[str, str]], approved: list[dict[str, str]], missing: list[dict[str, str]], workflow_rows: list[dict[str, str]]) -> None:
    pending_in_sitemap = pending_slugs_in_sitemap(pending)
    no_cta_or_links = [row for row in pending + approved if int(row.get("cta_count", "0") or 0) == 0 or int(row.get("internal_link_count", "0") or 0) < 3]
    text = "\n".join(
        [
            "REVIEW DASHBOARD SUMMARY",
            f"pending: {len(pending)}",
            f"approved_or_published: {len(approved)}",
            f"missing_images: {len(missing)}",
            f"pending_pages_in_sitemap: {len(pending_in_sitemap)}",
            f"drafts_missing_cta_or_internal_links: {len(no_cta_or_links)}",
            "",
            "Workflow:",
            *[f"- {row['area']}: {row['status']} | {row['details']}" for row in workflow_rows],
        ]
    )
    (settings.data_dir / "review_dashboard_summary.txt").write_text(text, encoding="utf-8")


def copy_draft_assets(draft_output: Path) -> None:
    source_dir = settings.base_dir / "assets" / "screenshots"
    target_dir = draft_output / "assets" / "screenshots"
    target_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.exists():
        return
    for image in source_dir.glob("*.png"):
        shutil.copy2(image, target_dir / image.name)


def quality_issues(title: str, slug: str, content: str, screenshot: str) -> list[str]:
    issues = []
    if not screenshot:
        issues.append("missing_screenshot")
    if word_count(content) < 1200:
        issues.append("word_count_under_1200")
    if count_cta(content) == 0:
        issues.append("missing_cta")
    if count_internal_links(content) < 3:
        issues.append("internal_links_under_3")
    if has_placeholder(content):
        issues.append("placeholder_text")
    if duplicate_title(title):
        issues.append("duplicate_title")
    if duplicate_meta_description(content):
        issues.append("duplicate_meta_description")
    if broken_links_in_content(content):
        issues.append("broken_internal_link")
    return issues


def count_cta(content: str) -> int:
    return len(re.findall(r"/go/|CTA:|Visit Official|Check current pricing|Read review", content, flags=re.IGNORECASE))


def count_internal_links(content: str) -> int:
    return len(set(re.findall(r"(?<!:)(/[a-z0-9][a-z0-9\-/]+/)", content, flags=re.IGNORECASE)))


def word_count(content: str) -> int:
    visible = re.sub(r"<[^>]+>", " ", str(content or ""))
    return len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", visible))


def has_placeholder(content: str) -> bool:
    return bool(re.search(r"\blorem\b|\btodo\b|your api key|example\.com|affiliate link here", str(content or ""), flags=re.IGNORECASE))


def duplicate_title(title: str) -> bool:
    if not title:
        return True
    site = settings.site_output_dir
    count = 0
    for page in site.rglob("index.html"):
        if title.strip().lower() in title_from_page(page).lower():
            count += 1
    return count > 1


def duplicate_meta_description(content: str) -> bool:
    match = re.search(r"Meta description:\s*(.+)", str(content or ""), flags=re.IGNORECASE)
    if not match:
        return False
    meta = match.group(1).strip().lower()
    if not meta:
        return False
    count = 0
    for page in settings.site_output_dir.rglob("index.html"):
        text = page.read_text(encoding="utf-8", errors="ignore").lower()
        if meta in text:
            count += 1
    return count > 1


def broken_links_in_content(content: str) -> bool:
    for link in set(re.findall(r"(?<!:)(/[a-z0-9][a-z0-9\-/]+/)", str(content or ""), flags=re.IGNORECASE)):
        if link.startswith(("/go/", "/assets/")):
            continue
        target = settings.site_output_dir / link.strip("/") / "index.html"
        if not target.exists():
            return True
    return False


def screenshot_for_slug(slug: str) -> str:
    aliases = {
        "cursor-ai-review-a-practical-guide-for-developers-and-ai-coders": "cursor",
        "windsurf-review": "windsurf",
    }
    image_slug = aliases.get(slug, slug)
    path = settings.base_dir / "assets" / "screenshots" / f"{image_slug}.png"
    return str(path) if path.exists() else ""


def known_screenshot_slugs() -> set[str]:
    folder = settings.base_dir / "assets" / "screenshots"
    if not folder.exists():
        return set()
    return {path.stem for path in folder.glob("*.png")}


def pending_slugs_in_sitemap(pending: list[dict[str, str]]) -> list[str]:
    sitemap = settings.site_output_dir / "sitemap.xml"
    if not sitemap.exists():
        return []
    text = sitemap.read_text(encoding="utf-8", errors="ignore")
    return [row["slug"] for row in pending if f"/{row['slug']}/" in text]


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def title_from_page(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"<title>(.*?)</title>", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html.unescape(match.group(1))).replace(f" - {settings.site_name}", "").strip()


def category_from_content_type(content_type: str, title: str, content: str) -> str:
    text = f"{content_type} {title} {content}".lower()
    if "coding" in text or "cursor" in text or "copilot" in text:
        return "AI Coding"
    if "comparison" in content_type.lower() or " vs " in title.lower():
        return "Comparison"
    if "review" in content_type.lower():
        return "Review"
    if "blog" in content_type.lower():
        return "Blog"
    return content_type or "Draft"


def title_from_slug(slug: str) -> str:
    known = {
        "github-copilot": "GitHub Copilot",
        "copy-ai": "Copy.ai",
        "surfer-seo": "Surfer SEO",
        "notion-ai": "Notion AI",
        "webflow-ai": "Webflow AI",
    }
    return known.get(slug, slug.replace("-", " ").title())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "draft"


def dedupe_rows(rows: list[dict[str, str]], keys: list[str]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for row in rows:
        key = tuple(row.get(item, "") for item in keys)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def dashboard_css() -> str:
    return """body{font-family:Arial,Helvetica,sans-serif;background:#f7f9fc;color:#17202a;line-height:1.6}.wrap{max-width:1160px;margin:0 auto;padding:28px 20px}.card{background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:18px;margin:14px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.badge{display:inline-block;border-radius:999px;background:#ecfdf5;color:#047857;padding:5px 10px;font-weight:800}.metric{background:#0f172a;color:#fff;border-radius:8px;padding:18px}.metric strong{display:block;font-size:34px}.metric span{color:#cbd5e1}img{max-width:100%;height:auto;border-radius:8px;border:1px solid #dbe3ef}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e6edf5;padding:10px;vertical-align:top}th{background:#f1f5f9}.btn{display:inline-block;background:#0f766e;color:white;padding:10px 14px;border-radius:6px;text-decoration:none;font-weight:800}"""
