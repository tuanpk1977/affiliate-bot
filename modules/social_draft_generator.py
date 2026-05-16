from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from config import settings


PLATFORMS = ["facebook", "linkedin", "twitter", "short_video"]
LANGUAGES = ["en", "vi"]
STATUS_DIRS = ["drafts", "approved", "rejected", "scheduled", "posted"]
DEFAULT_DOMAIN = "https://review.mssmileenglish.com"
PRIORITY_PATHS = [
    "/",
    "/cursor/",
    "/windsurf-review/",
    "/comparisons/cursor-vs-windsurf/",
    "/comparisons/copilot-vs-cursor/",
    "/best-ai-coding-tools-2026/",
    "/reviews/",
    "/comparisons/",
    "/category/ai-coding-tools/",
    "/pricing/",
]
REQUIRED_DRAFT_FIELDS = [
    "id",
    "source_url",
    "language",
    "platform",
    "title",
    "content",
    "cta_url",
    "status",
    "created_at",
    "approved_at",
    "scheduled_at",
    "posted_at",
]


def social_assets_root() -> Path:
    return settings.base_dir / "social_assets"


def social_status_dir(status_dir: str) -> Path:
    return social_assets_root() / status_dir


def ensure_social_automation_dirs() -> None:
    for name in STATUS_DIRS:
        social_status_dir(name).mkdir(parents=True, exist_ok=True)


def base_url() -> str:
    return (settings.base_site_url or settings.site_domain or DEFAULT_DOMAIN).rstrip("/")


def normalize_url(url_or_path: str) -> str:
    value = str(url_or_path or "").strip()
    if not value:
        return base_url() + "/"
    if value.startswith("http://") or value.startswith("https://"):
        return value.rstrip("/") + "/"
    return base_url() + "/" + value.strip("/") + ("/" if value.strip("/") else "")


def url_path(url: str) -> str:
    parsed = urlparse(normalize_url(url))
    return parsed.path or "/"


def vi_url_for(en_url: str) -> str:
    path = url_path(en_url)
    if path == "/":
        return base_url() + "/vi/"
    return base_url() + "/vi" + path


def local_index_for_url(url: str) -> Path:
    path = url_path(url).strip("/")
    if not path:
        return settings.site_output_dir / "index.html"
    return settings.site_output_dir / path / "index.html"


def slug_from_url(url: str) -> str:
    path = url_path(url).strip("/")
    if not path:
        return "home"
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")


def title_from_url(url: str, language: str = "en") -> str:
    slug = slug_from_url(url).replace("vi-", "")
    words = [word for word in slug.split("-") if word and word not in {"review", "comparisons", "category"}]
    title = " ".join(words).strip() or ("homepage" if language == "en" else "trang chủ")
    if language == "vi":
        return title.title().replace("Ai", "AI")
    return title.title().replace("Ai", "AI").replace("Seo", "SEO")


def build_draft_id(source_url: str, language: str, platform: str) -> str:
    slug = slug_from_url(source_url)
    if language == "vi" and slug.startswith("vi-"):
        slug = slug[3:]
    platform_slug = platform.lower().replace("/", "-").replace("_", "-")
    return f"{language}-{slug}-{platform_slug}"


def important_page_urls(limit: int = 20) -> list[str]:
    urls: list[str] = []
    priority_file = settings.data_dir / "indexing_priority.csv"
    if priority_file.exists():
        try:
            df = pd.read_csv(priority_file, encoding="utf-8-sig")
            for value in df.get("url", pd.Series(dtype=str)).astype(str).tolist():
                if value and "/go/" not in value and value.endswith("/"):
                    urls.append(normalize_url(value))
        except Exception:
            pass
    for path in PRIORITY_PATHS:
        urls.append(normalize_url(path))
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        path = url_path(url)
        if path.startswith("/vi/") or path in seen:
            continue
        if local_index_for_url(url).exists():
            deduped.append(url)
            seen.add(path)
        if len(deduped) >= limit:
            break
    return deduped


def page_language_urls(en_urls: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for en_url in en_urls:
        pairs.append(("en", en_url))
        vi_url = vi_url_for(en_url)
        if local_index_for_url(vi_url).exists():
            pairs.append(("vi", vi_url))
    return pairs


def create_social_draft(source_url: str, language: str, platform: str, created_at: str | None = None) -> dict[str, str]:
    source_url = normalize_url(source_url)
    created_at = created_at or datetime.now().isoformat(timespec="seconds")
    title = title_from_url(source_url, language)
    cta_url = source_url
    content = render_platform_content(title, source_url, language, platform)
    return {
        "id": build_draft_id(source_url, language, platform),
        "source_url": source_url,
        "language": language,
        "platform": platform,
        "title": title,
        "content": content,
        "cta_url": cta_url,
        "status": "draft",
        "created_at": created_at,
        "approved_at": "",
        "scheduled_at": "",
        "posted_at": "",
    }


def render_platform_content(title: str, source_url: str, language: str, platform: str) -> str:
    if language == "vi":
        return render_vi_content(title, source_url, platform)
    return render_en_content(title, source_url, platform)


def render_en_content(title: str, source_url: str, platform: str) -> str:
    if platform == "linkedin":
        return (
            f"I keep coming back to this when choosing AI tools: {title} is not just a feature checklist.\n\n"
            "The useful question is where the tool fits in a real workflow: setup, debugging, pricing checks, team adoption, and long-term cleanup.\n\n"
            "A few notes before shortlisting it:\n"
            "- Check the official pricing and policy before buying.\n"
            "- Compare it against alternatives, not only demos.\n"
            "- Look for the workflow cost, not just the subscription cost.\n\n"
            f"I wrote the research notes here: {source_url}\n\n"
            "#AITools #SaaS #Automation #Productivity"
        )
    if platform == "facebook":
        return (
            f"I added a practical review note for {title}.\n\n"
            "What I care about most is simple: does the tool save time after the first demo, or does it create cleanup work later?\n\n"
            "The page covers the practical checks I would make before using it seriously: pricing, alternatives, workflow fit, and policy notes.\n\n"
            f"Read it here: {source_url}\n\n"
            "#AITools #SaaS"
        )
    if platform == "twitter":
        return (
            f"1/ Tool research is easy to fake. Workflow fit is harder.\n\n"
            f"2/ {title} is worth checking through pricing, alternatives, and real usage constraints.\n\n"
            f"3/ Notes here: {source_url} #AITools #SaaS"
        )
    return (
        f"Short video script: {title}\n\n"
        "Hook: Most AI tool reviews stop at features. The real question is workflow fit.\n"
        "Scene 1: Show the problem: too many tools, unclear pricing, unclear use case.\n"
        "Scene 2: Show the checklist: pricing, alternatives, policy, practical workflow.\n"
        "Scene 3: CTA: read the full research note.\n"
        f"Link: {source_url}"
    )


def render_vi_content(title: str, source_url: str, platform: str) -> str:
    if platform == "linkedin":
        return (
            f"Khi đánh giá một công cụ AI như {title}, mình không chỉ nhìn vào tính năng.\n\n"
            "Điểm quan trọng hơn là công cụ đó có thật sự phù hợp với workflow hay không: dùng để dựng nhanh, debug, làm việc nhóm, kiểm tra giá và tránh rủi ro chính sách.\n\n"
            "Trước khi shortlist, mình thường kiểm tra:\n"
            "- Giá và điều khoản chính thức.\n"
            "- Công cụ thay thế có phù hợp hơn không.\n"
            "- Chi phí cleanup nếu dùng trong dự án thật.\n\n"
            f"Ghi chú nghiên cứu: {source_url}\n\n"
            "#AITools #SaaS #Automation"
        )
    if platform == "facebook":
        return (
            f"Mình vừa thêm ghi chú review thực tế cho {title}.\n\n"
            "Điều mình quan tâm không phải demo có đẹp hay không, mà là khi dùng vào workflow thật thì có tiết kiệm thời gian hay lại tạo thêm việc sửa về sau.\n\n"
            "Bài này tập trung vào giá, lựa chọn thay thế, độ phù hợp workflow và các điểm cần kiểm tra trước khi dùng nghiêm túc.\n\n"
            f"Đọc tại đây: {source_url}\n\n"
            "#AITools #SaaS"
        )
    if platform == "twitter":
        return (
            f"1/ Review công cụ AI rất dễ bị chung chung.\n\n"
            f"2/ Với {title}, câu hỏi đúng là: có hợp workflow thật không, giá có hợp lý không, có lựa chọn nào tốt hơn không?\n\n"
            f"3/ Ghi chú: {source_url} #AITools #SaaS"
        )
    return (
        f"Kịch bản video ngắn: {title}\n\n"
        "Hook: Đừng chọn công cụ AI chỉ vì demo đẹp.\n"
        "Cảnh 1: Vấn đề: quá nhiều công cụ, khó biết công cụ nào đáng dùng.\n"
        "Cảnh 2: Checklist: giá, lựa chọn thay thế, workflow, rủi ro chính sách.\n"
        "Cảnh 3: CTA: đọc ghi chú nghiên cứu đầy đủ.\n"
        f"Link: {source_url}"
    )


def draft_file_path(draft_id: str, status_dir: str = "drafts") -> Path:
    return social_status_dir(status_dir) / f"{draft_id}.json"


def find_draft_file(draft_id: str) -> Path | None:
    for status_dir in STATUS_DIRS:
        path = draft_file_path(draft_id, status_dir)
        if path.exists():
            return path
    return None


def save_draft_record(record: dict[str, str], status_dir: str = "drafts", overwrite: bool = False) -> Path:
    ensure_social_automation_dirs()
    draft_id = str(record["id"])
    existing = find_draft_file(draft_id)
    if existing and not overwrite:
        return existing
    path = draft_file_path(draft_id, status_dir)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_draft_file(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            for field in REQUIRED_DRAFT_FIELDS:
                payload.setdefault(field, "")
            return {key: "" if value is None else str(value) for key, value in payload.items()}
    except Exception:
        pass
    return {}


def load_all_social_drafts() -> list[dict[str, str]]:
    ensure_social_automation_dirs()
    rows: list[dict[str, str]] = []
    for status_dir in STATUS_DIRS:
        for path in sorted(social_status_dir(status_dir).glob("*.json")):
            record = load_draft_file(path)
            if record:
                record["_path"] = str(path)
                rows.append(record)
    return rows


def move_draft_status(draft_id: str, status: str, extra: dict[str, str] | None = None) -> Path | None:
    ensure_social_automation_dirs()
    current = find_draft_file(draft_id)
    if not current:
        return None
    record = load_draft_file(current)
    if not record:
        return None
    now = datetime.now().isoformat(timespec="seconds")
    record["status"] = status
    if status == "approved":
        record["approved_at"] = record.get("approved_at") or now
    elif status == "scheduled":
        record["scheduled_at"] = record.get("scheduled_at") or now
    elif status == "posted":
        record["posted_at"] = record.get("posted_at") or now
    if extra:
        record.update(extra)
    target_dir = status if status in STATUS_DIRS else f"{status}s"
    if target_dir not in STATUS_DIRS:
        target_dir = "drafts"
    target = draft_file_path(draft_id, target_dir)
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    if current != target:
        current.unlink(missing_ok=True)
    return target


def generate_social_drafts(limit: int = 20) -> list[Path]:
    ensure_social_automation_dirs()
    created_paths: list[Path] = []
    now = datetime.now().isoformat(timespec="seconds")
    for language, url in page_language_urls(important_page_urls(limit=limit)):
        for platform in PLATFORMS:
            record = create_social_draft(url, language, platform, created_at=now)
            path = save_draft_record(record, "drafts", overwrite=False)
            created_paths.append(path)
    return created_paths


def summarize_drafts(records: list[dict[str, str]] | None = None) -> dict[str, int]:
    rows = records if records is not None else load_all_social_drafts()
    summary: dict[str, int] = {"total": len(rows)}
    for language in LANGUAGES:
        summary[language] = sum(1 for row in rows if row.get("language") == language)
    for platform in PLATFORMS:
        summary[platform] = sum(1 for row in rows if row.get("platform") == platform)
    for status_dir in STATUS_DIRS:
        summary[status_dir] = sum(1 for row in rows if row.get("status") in {status_dir.rstrip("s"), status_dir})
    return summary
