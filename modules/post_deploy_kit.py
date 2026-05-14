from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from config import settings


INDEXING_COLUMNS = ["url", "page_type", "priority", "reason", "suggested_action"]
SOCIAL_QUEUE_COLUMNS = ["post_id", "platform", "article_url", "text_preview", "image_path", "status", "suggested_post_time", "copy_ready"]
CLICK_REPORT_COLUMNS = ["date", "source", "platform", "article_url", "go_url", "clicks", "impressions", "ctr", "notes"]
CHECKLIST_ITEMS = [
    "Site live checked",
    "Sitemap submitted",
    "5 priority URLs inspected",
    "Social post copied",
    "Thumbnail attached",
    "/go/ link tested",
    "Google Search Console checked",
    "Click report updated",
]


def run_post_deploy_kit() -> dict[str, int]:
    indexing = build_indexing_priority()
    social = build_social_posting_queue()
    click = ensure_click_tracking_report()
    ensure_google_indexing_checklist(indexing)
    ensure_post_deploy_checklist()
    return {"priority_urls": len(indexing), "copy_ready_posts": len(social), "click_rows": len(click)}


def build_indexing_priority() -> pd.DataFrame:
    urls = read_sitemap_urls()
    rows = []
    for url in urls:
        page_type = classify_page_type(url)
        priority, reason = priority_for_url(url, page_type)
        if priority <= 0:
            continue
        rows.append(
            {
                "url": url,
                "page_type": page_type,
                "priority": str(priority),
                "reason": reason,
                "suggested_action": suggested_action(priority, page_type),
            }
        )
    rows.sort(key=lambda row: (-int(row["priority"]), row["url"]))
    df = pd.DataFrame(rows, columns=INDEXING_COLUMNS)
    write_dataframe(settings.data_dir / "indexing_priority.csv", df, INDEXING_COLUMNS)
    return df


def read_sitemap_urls() -> list[str]:
    path = settings.site_output_dir / "sitemap.xml"
    if not path.exists():
        return []
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except ET.ParseError:
        return []
    urls = []
    for loc in root.iter():
        if loc.tag.endswith("loc") and loc.text:
            text = loc.text.strip()
            if text and "/go/" not in text:
                urls.append(text)
    return urls


def classify_page_type(url: str) -> str:
    path = url_path(url)
    if path == "/":
        return "homepage"
    if path.startswith("/review/") or path.endswith("-review/") or "windsurf-review" in path:
        return "review"
    if path.startswith("/comparisons/") or path.startswith("/compare/"):
        return "comparison"
    if path.startswith("/pricing/"):
        return "pricing"
    if path.startswith("/category/"):
        return "category"
    if path.startswith("/hub/") or path.startswith("/hubs/"):
        return "hub"
    if any(term in path for term in ["workflow", "debug", "bug", "deployment", "refactor", "startup"]):
        return "workflow_problem"
    if path.startswith("/blog/"):
        return "blog"
    return "seo_page"


def priority_for_url(url: str, page_type: str) -> tuple[int, str]:
    text = url.lower()
    score = 0
    reasons = []
    for token in ["cursor", "windsurf", "codex", "copilot", "ai-coding", "coding-tools"]:
        if token in text:
            score += 25
            reasons.append(f"contains {token}")
    if page_type in {"comparison", "review", "workflow_problem"}:
        score += 25
        reasons.append(f"high-intent {page_type}")
    if page_type in {"pricing", "category"}:
        score += 12
        reasons.append(f"supporting {page_type}")
    if any(term in text for term in ["debug", "bug", "deployment", "workflow", "refactor"]):
        score += 18
        reasons.append("problem/workflow intent")
    if score == 0 and page_type in {"homepage", "hub"}:
        score = 20
        reasons.append("crawl support page")
    return min(score, 100), " + ".join(reasons)


def suggested_action(priority: int, page_type: str) -> str:
    if priority >= 75:
        return "Submit in Google Search Console URL Inspection"
    if page_type in {"comparison", "review", "workflow_problem"}:
        return "Share on social before indexing"
    if page_type in {"category", "hub"}:
        return "Add more internal links"
    return "Include in sitemap"


def ensure_google_indexing_checklist(indexing: pd.DataFrame | None = None) -> Path:
    indexing = indexing if indexing is not None else build_indexing_priority()
    top_urls = indexing.head(10)["url"].tolist() if not indexing.empty else []
    lines = [
        "# Google Indexing Checklist",
        "",
        "- Submit `https://review.mssmileenglish.com/sitemap.xml` in Google Search Console.",
        "- Inspect 5-10 priority URLs with URL Inspection.",
        "- Request indexing for new or updated pages.",
        "- Check canonical tag on each inspected page.",
        "- Check title and meta description.",
        "- Check internal links to review, comparison, pricing, category, and hub pages.",
        "- Test `/go/` links manually but do not submit `/go/` pages for indexing.",
        "- Share the highest-priority pages on social before requesting indexing if possible.",
        "",
        "## Priority URLs to inspect first",
    ]
    lines.extend([f"- {url}" for url in top_urls] or ["- No priority URLs found. Run `python main.py` first."])
    path = settings.data_dir / "google_indexing_checklist.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_social_posting_queue() -> pd.DataFrame:
    posts = read_social_posts()
    rows = []
    ready_root = settings.base_dir / "draft_output" / "social_ready"
    ready_root.mkdir(parents=True, exist_ok=True)
    for idx, row in posts.iterrows():
        platform = normalize_platform(row.get("platform", ""))
        article_slug = str(row.get("article_slug", "") or "post")
        post_id = str(row.get("post_id", "") or f"{article_slug}-{platform.lower()}")
        output_path = Path(str(row.get("output_path", "")))
        text = output_path.read_text(encoding="utf-8", errors="ignore") if output_path.exists() else ""
        title = str(row.get("title", "") or article_slug.replace("-", " ").title())
        article_url = str(row.get("article_url", ""))
        if looks_generic_social_text(text):
            text = practical_social_copy(platform, title, article_url)
        image_path = str(row.get("image_path", "") or default_social_image(article_slug))
        ready_dir = ready_root / article_slug
        ready_dir.mkdir(parents=True, exist_ok=True)
        ready_file = ready_dir / f"{platform.lower().replace('/', '-')}.txt"
        ready_file.write_text(copy_ready_text(platform, image_path, text), encoding="utf-8")
        rows.append(
            {
                "post_id": post_id,
                "platform": platform,
                "article_url": article_url,
                "text_preview": preview_text(text),
                "image_path": image_path,
                "status": "Copy Ready",
                "suggested_post_time": suggested_post_time(idx),
                "copy_ready": "yes",
            }
        )
    df = pd.DataFrame(rows, columns=SOCIAL_QUEUE_COLUMNS)
    write_dataframe(settings.data_dir / "social_posting_queue.csv", df, SOCIAL_QUEUE_COLUMNS)
    return df


def read_social_posts() -> pd.DataFrame:
    path = settings.data_dir / "social_post_report.csv"
    rows = []
    if not path.exists():
        df = pd.DataFrame(columns=["post_id", "platform", "article_url", "output_path", "image_path", "article_slug"])
    else:
        try:
            df = pd.read_csv(path).fillna("")
        except Exception:
            df = pd.DataFrame(columns=["post_id", "platform", "article_url", "output_path", "image_path", "article_slug"])
    rows.extend(df.to_dict("records") if not df.empty else [])
    known_paths = {str(row.get("output_path", "")) for row in rows}
    root = settings.base_dir / "draft_output" / "social_posts"
    base = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")
    if root.exists():
        for file in sorted(root.glob("*/*.txt")):
            if str(file) in known_paths:
                continue
            article_slug = file.parent.name
            platform = file.stem
            rows.append(
                {
                    "post_id": f"{article_slug}-{platform}",
                    "platform": platform,
                    "article_url": f"{base}/{article_slug}/",
                    "output_path": str(file),
                    "image_path": str(settings.base_dir / "draft_output" / "social_images" / f"{article_slug}.png"),
                    "article_slug": article_slug,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["post_id", "platform", "article_url", "output_path", "image_path", "article_slug"])
    return pd.DataFrame(rows).fillna("")


def copy_ready_text(platform: str, image_path: str, text: str) -> str:
    return f"Platform: {platform}\nImage path: {image_path or 'No thumbnail found'}\n\n{text.strip()}\n"


def looks_generic_social_text(text: str) -> bool:
    lower = str(text or "").lower()
    markers = [
        "a useful saas review should answer",
        "quick take:",
        "the useful question is not only features",
        "does this tool fit the buyer",
        "read the full review before buying",
    ]
    return any(marker in lower for marker in markers)


def practical_social_copy(platform: str, title: str, article_url: str) -> str:
    lower = f"{title} {article_url}".lower()
    if "cursor" in lower and "windsurf" in lower:
        angle = "Cursor is stronger when the repo is already clean. Windsurf is faster when I need rough structure from zero."
    elif "cursor" in lower:
        angle = "I stopped treating Cursor like autocomplete. The real value is workflow speed during debugging."
    elif "windsurf" in lower:
        angle = "Windsurf is fast for scaffolding, but large refactors still need careful review."
    elif "copilot" in lower:
        angle = "Copilot is useful for lightweight autocomplete, but weaker when the fix needs full project context."
    else:
        angle = "The useful test is whether the tool survives debugging, review, and deployment checks."
    platform = normalize_platform(platform)
    if platform == "Facebook":
        return f"Mình đang nhìn lại {title} theo góc build project thật.\n\n{angle}\n\nĐiều đáng hỏi: công cụ này giúp ship nhanh hơn, hay chỉ tạo thêm code phải dọn?\n\nĐọc bài: {article_url}\n\nDisclosure: Some links may be affiliate links."
    if platform == "LinkedIn":
        return f"{title}\n\nI do not judge AI coding tools by the first generated answer anymore.\n\n{angle}\n\nA good workflow is: scaffold fast, debug slowly, ship small trusted diffs.\n\nFull note: {article_url}\n\nAffiliate disclosure: some links may be affiliate links."
    if platform == "Telegram":
        return f"{title}\n\nTakeaway: {angle}\n\nĐọc tiếp: {article_url}\n\nDisclosure: may include affiliate links."
    return f"AI coding tools only matter after the first draft breaks.\n\n1/ {angle}\n2/ Fast code is not always cheaper if review time explodes.\n3/ Full note: {article_url}"


def normalize_platform(value: object) -> str:
    text = str(value or "").strip().lower()
    return {"facebook": "Facebook", "linkedin": "LinkedIn", "telegram": "Telegram", "twitter": "Twitter/X", "x": "Twitter/X"}.get(text, text.title() or "Unknown")


def suggested_post_time(index: int) -> str:
    base = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    if base < datetime.now():
        base = base + timedelta(days=1)
    return (base + timedelta(hours=2 * index)).isoformat(timespec="minutes")


def default_social_image(article_slug: str) -> str:
    path = settings.base_dir / "draft_output" / "social_images" / f"{article_slug}.png"
    return str(path) if path.exists() else ""


def ensure_click_tracking_report() -> pd.DataFrame:
    path = settings.data_dir / "click_tracking_report.csv"
    if path.exists():
        try:
            df = pd.read_csv(path).fillna("")
        except Exception:
            df = pd.DataFrame(columns=CLICK_REPORT_COLUMNS)
    else:
        df = pd.DataFrame(columns=CLICK_REPORT_COLUMNS)
    for column in CLICK_REPORT_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[CLICK_REPORT_COLUMNS]
    if df.empty:
        write_dataframe(path, df, CLICK_REPORT_COLUMNS)
    else:
        df["ctr"] = df.apply(compute_ctr, axis=1)
        write_dataframe(path, df, CLICK_REPORT_COLUMNS)
    return df


def load_click_tracking_report() -> pd.DataFrame:
    return ensure_click_tracking_report()


def compute_ctr(row: pd.Series) -> str:
    try:
        clicks = float(row.get("clicks", 0) or 0)
        impressions = float(row.get("impressions", 0) or 0)
    except ValueError:
        return str(row.get("ctr", ""))
    if impressions <= 0:
        return ""
    return f"{clicks / impressions * 100:.2f}%"


def go_page_count() -> int:
    root = settings.site_output_dir / "go"
    if not root.exists():
        return 0
    return len([path for path in root.glob("*/index.html")])


def load_post_deploy_checklist() -> dict[str, bool]:
    path = post_deploy_checklist_path()
    if not path.exists():
        return {item: False for item in CHECKLIST_ITEMS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {item: bool(data.get(item, False)) for item in CHECKLIST_ITEMS}


def save_post_deploy_checklist(values: dict[str, bool]) -> None:
    path = post_deploy_checklist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = {item: bool(values.get(item, False)) for item in CHECKLIST_ITEMS}
    path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_post_deploy_checklist() -> dict[str, bool]:
    current = load_post_deploy_checklist()
    save_post_deploy_checklist(current)
    return current


def post_deploy_checklist_path() -> Path:
    return settings.base_dir / "config" / "post_deploy_checklist.json"


def write_dataframe(path: Path, df: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
        return
    df.to_csv(path, index=False, columns=columns)


def url_path(url: str) -> str:
    match = re.match(r"https?://[^/]+(/.*)?$", str(url))
    path = match.group(1) if match else str(url)
    return path if path.startswith("/") else f"/{path}"


def preview_text(text: str, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return clean[:limit].rstrip() + ("..." if len(clean) > limit else "")
