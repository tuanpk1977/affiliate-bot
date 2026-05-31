from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from config import settings


PRIORITY_PAGES = [
    ("/cursor/", "Cursor review", "Cursor", "review", "A practical Cursor review for developers comparing AI coding workflows."),
    ("/windsurf-review/", "Windsurf review", "Windsurf", "review", "A hands-on Windsurf review focused on scaffolding speed, cleanup risk, and AI coding workflow fit."),
    ("/comparisons/cursor-vs-windsurf/", "Cursor vs Windsurf", "Cursor vs Windsurf", "comparison", "A practical comparison of Cursor and Windsurf for real AI coding projects."),
    ("/comparisons/copilot-vs-cursor/", "Copilot vs Cursor", "GitHub Copilot vs Cursor", "comparison", "A practical comparison of Copilot and Cursor for teams, solo builders, and repository-aware coding."),
    ("/best-ai-coding-tools-2026/", "Best AI Coding Tools 2026", "AI coding tools", "best_tools", "A practical buying guide for Cursor, Windsurf, Copilot, and AI coding workflows."),
]

PLATFORMS = ["facebook", "linkedin", "twitter", "short_video"]


@dataclass(frozen=True)
class SocialDraft:
    post_id: str
    language: str
    platform: str
    title: str
    url: str
    content: str
    output_path: str


def generate_social_seo_assets() -> dict[str, int]:
    root = settings.base_dir / "social_assets"
    root.mkdir(parents=True, exist_ok=True)
    rows: list[SocialDraft] = []
    for path, title, tool, page_type, summary in PRIORITY_PAGES:
        for language in ["en", "vi"]:
            localized_path = path if language == "en" else "/vi" + path
            url = full_url(localized_path)
            slug = slugify(localized_path.strip("/") or "home")
            folder = root / slug
            folder.mkdir(parents=True, exist_ok=True)
            for platform in PLATFORMS:
                content = render_post(language, platform, title, tool, page_type, summary, url)
                post_id = f"{slug}-{platform}-{language}"
                filename = f"{post_id}.md"
                output = folder / filename
                output.write_text(content, encoding="utf-8")
                rows.append(SocialDraft(post_id, language, platform, title, url, content, str(output)))

    report = settings.data_dir / "seo_social_assets_report.csv"
    with report.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=["post_id", "language", "platform", "title", "url", "character_count", "output_path"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "post_id": row.post_id,
                    "language": row.language,
                    "platform": row.platform,
                    "title": row.title,
                    "url": row.url,
                    "character_count": len(row.content),
                    "output_path": row.output_path,
                }
            )
    return {"social_assets": len(rows)}


def render_post(language: str, platform: str, title: str, tool: str, page_type: str, summary: str, url: str) -> str:
    if language == "vi":
        return render_vi(platform, title, tool, page_type, url)
    return render_en(platform, title, tool, page_type, summary, url)


def render_en(platform: str, title: str, tool: str, page_type: str, summary: str, url: str) -> str:
    tracked_url = add_utm(url, platform)
    if platform == "linkedin":
        return f"""I keep seeing AI coding tool discussions turn into feature checklists.

The more useful question is simpler: where does the tool actually help inside a messy repo?

I put together this {page_type.replace('_', ' ')} because {tool} decisions should be based on workflow fit, not demo speed. {summary}

What I would check before choosing:
- Does it understand the files that matter, or only the current tab?
- Does the second failed fix get better or just create more noise?
- Can the team review the diff without cleaning up a giant patch?
- Are pricing and policy clear enough before rollout?

This is not a hype post. It is a practical research note for builders comparing AI coding workflows.

Read it here: {tracked_url}

#AICoding #DeveloperTools #Cursor #Windsurf #GitHubCopilot"""
    if platform == "facebook":
        return f"""I wrote a practical note on {title}.

The point is not “which AI tool looks best in a demo?”

The real test is what happens after the repo gets messy:
- one bug fix fails twice
- the assistant starts repeating itself
- deployment breaks because of config, not code
- the diff becomes too large to trust

That is where tools like Cursor, Windsurf, and Copilot start to feel very different.

I kept the post research-style and avoided fake guarantees. It should help if you are comparing AI coding tools for a real project.

Read it here: {tracked_url}"""
    if platform == "twitter":
        return f"""1/ AI coding tools should not be judged by the first clean demo.

2/ The real benchmark is the second failed fix: does the tool reason better, or just write more code?

3/ I wrote a practical breakdown of {title} for builders comparing real repo workflows.

4/ Read the research note: {tracked_url}

#AICoding #DevTools"""
    return f"""Short video script: {title}

Hook: The first AI coding fix is easy. The second failed fix is the real test.
Scene 1: show a messy repo and a failing build.
Scene 2: explain where {tool} helps and where it can still create cleanup work.
Scene 3: show the practical takeaway: choose tools by workflow stage, not hype.
CTA: Read the full research note at {tracked_url}"""


def render_vi(platform: str, title: str, tool: str, page_type: str, url: str) -> str:
    tracked_url = add_utm(url, platform)
    if platform == "linkedin":
        return f"""Mình không còn đánh giá AI coding tool bằng demo đẹp nữa.

Câu hỏi thực tế hơn là: khi repo bắt đầu rối, tool đó giúp mình sửa nhanh hơn hay làm diff phình to hơn?

Mình đã chuẩn bị bài {title} theo hướng thực chiến cho người đang build project thật. Trọng tâm là workflow, debugging, pricing risk, context trong repo và khả năng kiểm soát thay đổi.

Khi so sánh các tool như Cursor, Windsurf hoặc Copilot, mình thường kiểm tra:
- tool có hiểu đúng file liên quan không
- lỗi sửa lần hai có tốt hơn không
- có tạo logic trùng lặp không
- diff cuối cùng có dễ review không
- pricing/policy có phù hợp trước khi rollout không

Không phải bài quảng cáo. Đây là ghi chú nghiên cứu để chọn tool tỉnh táo hơn.

Xem bài tại: {tracked_url}

#AICoding #LapTrinh #DeveloperTools"""
    if platform == "facebook":
        return f"""Mình vừa viết một bài thực tế về {title}.

Điểm mình quan tâm không phải tool nào “ngầu” hơn trong demo.

Mà là khi làm dự án thật:
- bug sửa mãi chưa xong
- tool bắt đầu lặp lại cùng một hướng
- build/deploy lỗi vì config
- code sinh ra quá nhiều, khó review

Lúc đó Cursor, Windsurf, Copilot... khác nhau khá rõ.

Bài này viết theo hướng research, không hứa hẹn quá đà, không affiliate giả. Nếu bạn đang chọn AI coding tool cho workflow thật thì có thể dùng làm checklist ban đầu.

Link bài: {tracked_url}"""
    if platform == "twitter":
        return f"""1/ Demo đầu tiên của AI coding tool thường rất đẹp.

2/ Nhưng bài test thật là lần sửa lỗi thứ hai: tool hiểu vấn đề hơn hay chỉ viết thêm code?

3/ Mình viết bài {title} theo góc nhìn build project thật.

4/ Xem tại: {tracked_url}

#AICoding #LapTrinh"""
    return f"""Kịch bản video ngắn: {title}

Hook: Lần sửa lỗi đầu tiên chưa nói lên nhiều. Lần sửa lỗi thứ hai mới là bài test thật.
Ý chính: so sánh {tool} theo workflow thực tế, không theo demo.
Takeaway: chọn AI coding tool theo từng giai đoạn của dự án.
CTA: đọc bài đầy đủ tại {tracked_url}"""


def add_utm(url: str, platform: str) -> str:
    separator = "&" if "?" in url else "?"
    source = "twitter" if platform == "twitter" else platform
    return f"{url}{separator}utm_source={source}&utm_medium=organic_social&utm_campaign=seo_content&utm_content={source}_draft"


def full_url(path: str) -> str:
    base = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    return base + path


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "home"

