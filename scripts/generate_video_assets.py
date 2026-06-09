from __future__ import annotations

import csv
import html
import json
import argparse
import tempfile
import os
import re
import shutil
import subprocess
import sys
import requests
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SITE_OUTPUT = ROOT / "site_output"
LANDING_OUTPUT = ROOT / "landing_pages" / "output"
ASSETS_DIR = ROOT / "assets"
VIDEO_OUTPUT = ROOT / "video_output"
VIDEO_RENDER_CONFIG = ROOT / "config" / "video_render.json"
SITE_STATS_CONFIG = ROOT / "config" / "siteStats.json"
RENDER_DEBUG_LOG = VIDEO_OUTPUT / "logs" / "render_debug.log"
SUBTITLE_REPORT_CSV = VIDEO_OUTPUT / "subtitle_report.csv"
RENDER_REPORT_CSV = VIDEO_OUTPUT / "render_report.csv"
BASE_URL = "https://smileaireviewhub.com"
YOUTUBE_CHANNEL_URL = "https://youtube.com/@SmileAIReviewHub"
MIN_VALID_MP4_BYTES = 100 * 1024
END_SCREEN_VOICEOVER = "Thank you for watching. For more AI reviews and comparisons, visit Smile AI Review Hub."
AUTHOR_VOICEOVER = (
    "This review was researched and prepared by Nguyen Quoc Tuan, "
    "an independent AI and SaaS researcher. Learn more at smileaireviewhub.com/about-author."
)
SLIDE_TITLE_VI = {
    "overview": "Tổng quan",
    "pricing": "Giá bán",
    "key features": "Tính năng chính",
    "pros": "Ưu điểm",
    "cons": "Nhược điểm",
}

ROOT_OUTPUT_DIRS = [
    "scripts",
    "voiceovers",
    "subtitles",
    "thumbnails",
    "videos",
    "manifests",
    "logs",
]

SECTION_LIMITS = {
    "review": ["Intro", "Overview", "Key Features", "Pros", "Cons", "Pricing", "Alternatives", "Final Verdict"],
    "comparison": [
        "Introduction",
        "Tool A",
        "Tool B",
        "Feature Comparison",
        "Pricing Comparison",
        "Best Use Cases",
        "Winner",
        "Conclusion",
    ],
    "pricing": ["Intro", "Overview", "Pricing Notes", "Plan Checks", "Best For", "Risks", "Alternatives", "Final Verdict"],
    "category": ["Intro", "Overview", "Top Tools", "How To Choose", "Pricing Checks", "Use Cases", "Alternatives", "Conclusion"],
}

DEFAULT_VIDEO_RENDER_CONFIG = {
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "default_render_limit": 3,
    "render_long_video": True,
    "render_shorts": True,
    "burn_subtitles": True,
    "watermark": "smileaireviewhub.com",
    "tts_enabled": True,
    "tts_voice": "en-US-GuyNeural",
    "tts_rate": "+0%",
    "tts_volume": "+0%",
    "background_music_path": "",
}


@dataclass(frozen=True)
class Article:
    slug: str
    title: str
    page_type: str
    output_path: Path
    url: str
    tool_a: str = ""
    tool_b: str = ""


@dataclass
class ExtractedPage:
    title: str
    description: str
    headings: dict[str, list[str]]
    all_text: list[str]
    image: str = ""


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def slugify(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def page_url_from_path(path: str | Path) -> str:
    p = Path(path)
    try:
        rel = p.resolve().relative_to(SITE_OUTPUT.resolve())
        rel_text = rel.as_posix()
        if rel_text.endswith("index.html"):
            rel_text = rel_text[: -len("index.html")]
        return f"{BASE_URL}/{rel_text}".replace("//", "/").replace("https:/", "https://")
    except ValueError:
        pass
    name = p.parent.name if p.name == "index.html" else p.stem
    return f"{BASE_URL}/{name}/"


def safe_output_path(value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.exists():
        return path
    return None


def discover_articles() -> list[Article]:
    articles: list[Article] = []
    seen_urls: set[str] = set()

    def add(article: Article) -> None:
        if not article.output_path.exists():
            return
        if "/vi/" in article.url:
            return
        if article.url in seen_urls:
            return
        seen_urls.add(article.url)
        articles.append(article)

    for row in read_csv(DATA_DIR / "review_pages_index.csv"):
        path = safe_output_path(row.get("output_path", ""))
        if not path:
            continue
        slug = row.get("review_slug") or row.get("offer_id") or path.parent.name
        add(
            Article(
                slug=f"review-{slugify(slug)}",
                title=clean_text(row.get("title") or row.get("brand_name") or slug),
                page_type="review",
                output_path=path,
                url=page_url_from_path(path),
            )
        )

    for row in read_csv(DATA_DIR / "comparison_pages_index.csv"):
        path = safe_output_path(row.get("output_path", ""))
        if not path:
            continue
        slug = row.get("comparison_slug") or path.parent.name
        add(
            Article(
                slug=f"compare-{slugify(slug)}",
                title=clean_text(row.get("title") or slug),
                page_type="comparison",
                output_path=path,
                url=page_url_from_path(path),
                tool_a=clean_text(row.get("tool_a_name", "")),
                tool_b=clean_text(row.get("tool_b_name", "")),
            )
        )

    for row in read_csv(DATA_DIR / "pricing_pages_index.csv"):
        path = safe_output_path(row.get("output_path", ""))
        if not path:
            continue
        slug = row.get("tool_slug") or path.parent.name
        add(
            Article(
                slug=f"pricing-{slugify(slug)}",
                title=clean_text(row.get("title") or row.get("tool_name") or slug),
                page_type="pricing",
                output_path=path,
                url=page_url_from_path(path),
            )
        )

    for row in read_csv(DATA_DIR / "category_pages_index.csv"):
        path = safe_output_path(row.get("output_path", ""))
        if not path:
            continue
        slug = row.get("category_slug") or path.parent.name
        add(
            Article(
                slug=f"category-{slugify(slug)}",
                title=clean_text(row.get("title") or slug),
                page_type="category",
                output_path=path,
                url=page_url_from_path(path),
            )
        )

    for row in read_csv(DATA_DIR / "landing_pages_index.csv"):
        offer_id = slugify(row.get("offer_id") or "")
        if not offer_id:
            continue
        site_path = SITE_OUTPUT / offer_id / "index.html"
        fallback_path = safe_output_path(row.get("landing_page", "")) or LANDING_OUTPUT / offer_id / "index.html"
        path = site_path if site_path.exists() else fallback_path
        if not path.exists():
            continue
        add(
            Article(
                slug=offer_id,
                title=clean_text(f"{row.get('brand_name') or offer_id} Review"),
                page_type="review",
                output_path=path,
                url=f"{BASE_URL}/{offer_id}/",
            )
        )

    return sorted(articles, key=lambda item: (item.page_type, item.slug))


def extract_page(path: Path) -> ExtractedPage:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for selector in ["nav", "footer", ".menu", ".language-switcher", ".auto-toc-block", ".breadcrumb"]:
        for tag in soup.select(selector):
            tag.decompose()

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" "))
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" "))

    description = ""
    meta_description = soup.find("meta", attrs={"name": "description"})
    if meta_description:
        description = clean_text(meta_description.get("content", ""))

    image = ""
    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image:
        image = clean_text(og_image.get("content", ""))

    headings: dict[str, list[str]] = {}
    current = "Overview"
    headings[current] = []
    for node in soup.find_all(["h2", "h3", "p", "li", "td", "th"]):
        text = clean_text(node.get_text(" "))
        if not text:
            continue
        if node.name in {"h2", "h3"}:
            current = text[:90]
            headings.setdefault(current, [])
        else:
            if not should_skip_text(text):
                headings.setdefault(current, []).append(text)

    all_text: list[str] = []
    for values in headings.values():
        for value in values:
            if value not in all_text:
                all_text.append(value)

    return ExtractedPage(title=title, description=description, headings=headings, all_text=all_text, image=image)


def should_skip_text(text: str) -> bool:
    lower = text.lower()
    skip_phrases = [
        "some links may be affiliate links",
        "real screenshots can be added later",
        "product logo placeholder",
        "pricing screenshot placeholder",
        "example workflow placeholder",
        "reviewed by ",
        "founder - ms smile ai review hub",
        "last updated:",
        "editorial score:",
        "cta status:",
        "research review ",
        "open related hub",
        "visit official website",
        "check current pricing",
        "share:",
        "home /",
        "english |",
        "tieng viet",
        "tiá",
    ]
    if len(text) < 24:
        return True
    if any(ord(char) > 127 for char in text):
        return True
    if "/assets/" in lower or "/content/images/" in lower:
        return True
    if re.search(r"[áàảãạâăéèẻẽẹêíìỉĩịóòỏõọôơúùủũụưđ][º»]", lower):
        return True
    if "áº" in lower or "á»" in lower or "nhá" in lower:
        return True
    return any(phrase in lower for phrase in skip_phrases)


def find_section_text(page: ExtractedPage, keywords: Iterable[str], fallback_count: int = 3) -> list[str]:
    matches: list[str] = []
    keyword_list = [item.lower() for item in keywords]
    for heading, values in page.headings.items():
        heading_lower = heading.lower()
        if any(keyword in heading_lower for keyword in keyword_list):
            matches.extend(values)
    if not matches:
        for text in page.all_text:
            lower = text.lower()
            if any(keyword in lower for keyword in keyword_list):
                matches.append(text)
    if not matches:
        matches = page.all_text[:fallback_count]
    return dedupe(matches)[:5]


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = clean_text(value)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def section_source(article: Article, page: ExtractedPage, section: str) -> list[str]:
    section_lower = section.lower()
    if "intro" in section_lower or "introduction" in section_lower:
        return dedupe([page.description] + page.all_text[:3])[:4]
    if "overview" in section_lower:
        return find_section_text(page, ["overview", "quick verdict", "short answer"])
    if "feature" in section_lower:
        return find_section_text(page, ["feature", "checklist", "workflow", "what stands out"])
    if "pros" in section_lower:
        return find_section_text(page, ["pros", "best for", "what stands out"])
    if "cons" in section_lower or "risks" in section_lower:
        return find_section_text(page, ["cons", "not best", "risk", "watch", "limitations"])
    if "pricing" in section_lower or "plan" in section_lower:
        return find_section_text(page, ["pricing", "price", "plan", "trial"])
    if "alternative" in section_lower:
        return find_section_text(page, ["alternatives", "compare", "related"])
    if "tool a" in section_lower and article.tool_a:
        return find_section_text(page, [article.tool_a, "choose"])
    if "tool b" in section_lower and article.tool_b:
        return find_section_text(page, [article.tool_b, "choose"])
    if "winner" in section_lower:
        return find_section_text(page, ["winner", "verdict", "choose", "recommendation"])
    if "use cases" in section_lower or "best use" in section_lower:
        return find_section_text(page, ["use case", "best for", "workflow fit"])
    if "top tools" in section_lower:
        return find_section_text(page, ["top tools", "best tools", "related reviews"])
    if "how to choose" in section_lower:
        return find_section_text(page, ["how to choose", "choose", "buyer"])
    if "verdict" in section_lower or "conclusion" in section_lower:
        return find_section_text(page, ["final verdict", "verdict", "conclusion", "quick verdict"])
    return page.all_text[:4]


def build_script(article: Article, page: ExtractedPage) -> str:
    title = page.title or article.title
    lines = [
        f"{title}",
        "",
        "This video is prepared for manual review before publishing. It does not replace official vendor documentation.",
        "",
    ]

    for section in SECTION_LIMITS[article.page_type]:
        lines.append(section)
        source_text = section_source(article, page, section)
        narration = build_section_narration(article, page, section, source_text)
        lines.append(narration)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_section_narration(article: Article, page: ExtractedPage, section: str, source_text: list[str]) -> str:
    title = page.title or article.title
    name = display_name(title)
    joined = " ".join(source_text)
    joined = trim_words(joined, 95)
    section_lower = section.lower()

    if "intro" in section_lower or "introduction" in section_lower:
        return (
            f"In this MS Smile AI Review Hub video, we look at {name} from a practical research angle. "
            f"Based on our page research, the goal is to understand workflow fit, pricing checks, alternatives, "
            f"and the limits that should be verified before buying or promoting a tool. {joined}"
        )
    if "pricing" in section_lower or "plan" in section_lower:
        return (
            f"For pricing, use the website content as a starting point, then verify current pricing on the official website. "
            f"Plans, limits, trials, cancellation terms, and affiliate approval can change over time. {joined}"
        )
    if "winner" in section_lower:
        return (
            f"The winner depends on the workflow. Based on our comparison notes, choose the tool that fits the repeated task, "
            f"the review process, and the pricing checks you can verify. {joined}"
        )
    if "verdict" in section_lower or "conclusion" in section_lower:
        return (
            f"The final verdict is to treat this as research, not a promise of results. Shortlist the tool only if it fits a real workflow, "
            f"then confirm pricing, features, policy details, and official terms before taking the next step. {joined}"
        )
    return (
        f"Based on the article notes for {name}, this section focuses on {section.lower()}. "
        f"{joined} Keep human review in the loop, and verify any fast-changing details on the official website."
    )


def display_name(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r" - MS Smile AI Review Hub$", "", title)
    return title


def trim_words(text: str, max_words: int) -> str:
    words = clean_text(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,.;:") + "."


def voiceover_from_script(script: str) -> str:
    lines = []
    for line in script.splitlines():
        stripped = clean_text(line)
        if not stripped:
            continue
        if stripped in {"Intro", "Overview", "Key Features", "Pros", "Cons", "Pricing", "Alternatives", "Final Verdict"}:
            continue
        if stripped in SECTION_LIMITS["comparison"] or stripped in SECTION_LIMITS["pricing"] or stripped in SECTION_LIMITS["category"]:
            continue
        stripped = re.sub(r"https?://\S+", "", stripped)
        stripped = re.sub(r"[*_`#>-]", "", stripped)
        lines.append(clean_text(stripped))
    return "\n\n".join(lines).strip() + "\n"


def build_youtube_voiceover(article: Article, page: ExtractedPage) -> str:
    name = display_name(page.title or article.title).replace(" - MS Smile AI Review Hub", "")
    name = re.sub(r"\s+Review.*$", "", name).strip() or display_name(article.title)
    overview = trim_words(" ".join(section_source(article, page, "Overview")), 42)
    features = [trim_words(item, 12) for item in section_source(article, page, "Key Features")[:3]]
    pros = [trim_words(item, 12) for item in section_source(article, page, "Pros")[:3]]
    cons = [trim_words(item, 12) for item in section_source(article, page, "Cons")[:3]]
    pricing = trim_words(" ".join(section_source(article, page, "Pricing")), 42)
    alternatives = [trim_words(item, 12) for item in section_source(article, page, "Alternatives")[:3]]
    verdict = trim_words(" ".join(section_source(article, page, "Final Verdict")), 46)
    lines = [
        f"If you are considering {name}, here is the short version before you spend money.",
        f"The problem is simple: SEO tools can look impressive in a demo, but the real question is whether they improve your weekly workflow. {overview}",
        f"The solution is to test {name} against one real content planning task. Look at keyword research, content briefs, competitor checks, and how much manual review is still needed.",
        "For key features, focus on the practical pieces. " + " ".join(features),
        "The strongest reasons to shortlist it are these. " + " ".join(pros),
        "But there are tradeoffs. " + " ".join(cons),
        f"For pricing, do not rely on old screenshots or old plan names. {pricing} Always verify current pricing on the official website.",
        "Before you decide, compare alternatives. " + " ".join(alternatives),
        f"My verdict: {verdict} Use this review as a research starting point, not a guarantee.",
        "Watch more AI tool reviews on the Smile AI Review Hub YouTube channel. Read the full review and affiliate links at smileaireviewhub.com.",
    ]
    return "\n\n".join(clean_text(line) for line in lines if clean_text(line)) + "\n"


def build_vietnamese_subtitles(article: Article, page: ExtractedPage) -> str:
    name = display_name(page.title or article.title).replace(" - MS Smile AI Review Hub", "")
    name = re.sub(r"\s+Review.*$", "", name).strip() or display_name(article.title)
    return "\n\n".join(
        [
            f"Nếu bạn đang cân nhắc {name}, đây là phần tóm tắt trước khi chi tiền.",
            "Vấn đề là nhiều công cụ trông rất hay trong demo.",
            "Điều cần kiểm tra là hiệu quả trong quy trình làm việc thật.",
            f"Hãy thử {name} với một nhiệm vụ thực tế trước khi quyết định.",
            "Nhìn vào nghiên cứu, brief nội dung, kiểm tra đối thủ và phần cần review thủ công.",
            "Tập trung vào tính năng chính, giới hạn gói, dữ liệu và quyền sử dụng.",
            "Điểm mạnh là giúp bạn sàng lọc công cụ nhanh hơn và có cơ sở hơn.",
            "Điểm phù hợp thường là nhóm nội dung, SEO team và người làm affiliate.",
            "Điểm cần cẩn trọng là giá, điều khoản, chất lượng đầu ra và kỳ vọng kết quả.",
            "Đừng dựa vào ảnh giá cũ hoặc tên gói cũ.",
            "Hãy xác minh giá hiện tại trên website chính thức.",
            "So sánh thêm các lựa chọn thay thế trong cùng nhóm trước khi mua.",
            "Nếu bạn cần workflow đơn giản, hãy ưu tiên công cụ dễ kiểm tra và dễ thay thế.",
            "Nếu bạn cần dữ liệu sâu, hãy kiểm tra giới hạn gói và nguồn dữ liệu.",
            "Không nên xem bài đánh giá này là cam kết kết quả.",
            "Hãy dùng nó như điểm bắt đầu để nghiên cứu trước khi mua.",
            "Kết luận: chọn công cụ dựa trên nhu cầu thật, ngân sách và quy trình kiểm chứng.",
            "Đọc bài đánh giá đầy đủ tại smileaireviewhub.com.",
            "Đăng ký kênh để xem thêm review công cụ AI thực tế.",
        ]
    ) + "\n"


def split_subtitle_event_text(text: str, max_chars: int = 34, max_lines: int = 2) -> list[str]:
    words = clean_text(text).split()
    events: list[str] = []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = clean_text(f"{current} {word}")
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) >= max_lines:
            events.append("\n".join(lines))
            lines = []
    if current and len(lines) < max_lines:
        lines.append(current)
    if lines:
        events.append("\n".join(lines))
    return events or [clean_text(text)]


def build_srt(voiceover: str, max_chars: int = 42) -> str:
    chunks = split_subtitle_chunks(voiceover)
    current = 0.0
    blocks = []
    index = 1
    for chunk in chunks:
        parts = split_subtitle_event_text(chunk, max_chars=max_chars, max_lines=2)
        words = max(4, len(chunk.split()))
        duration = max(2.5, min(7.0, words / 2.4))
        part_duration = max(2.0, duration / max(1, len(parts)))
        for part in parts:
            start = current
            end = current + part_duration
            blocks.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{part}\n")
            current = end + 0.18
            index += 1
    return "\n".join(blocks).strip() + "\n"


def build_srt_to_duration(text: str, target_seconds: float, max_chars: int = 34) -> str:
    chunks = split_subtitle_chunks(text)
    events: list[str] = []
    for chunk in chunks:
        events.extend(split_subtitle_event_text(chunk, max_chars=max_chars, max_lines=2))
    if not events:
        events = ["Đang xem phần đánh giá công cụ AI."]
    target_seconds = max(1.0, target_seconds)
    event_duration = target_seconds / len(events)
    while event_duration > 7.5:
        events = events + events[:-2]
        event_duration = target_seconds / len(events)
    event_duration = target_seconds / len(events)
    blocks = []
    current = 0.0
    final_cta_seconds = 7.0 if len(events) > 1 and "Smile AI Review Hub" in events[-1] else 0.0
    body_target_seconds = max(1.0, target_seconds - final_cta_seconds)
    body_event_duration = body_target_seconds / max(1, len(events) - (1 if final_cta_seconds else 0))
    for index, event in enumerate(events, start=1):
        if final_cta_seconds and index == len(events):
            current = body_target_seconds
            end = target_seconds
        else:
            end = target_seconds if index == len(events) else current + body_event_duration
        blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{event}\n")
        current = end
    return "\n".join(blocks).strip() + "\n"


def split_subtitle_chunks(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", clean_text(text))
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) < 105:
            current = clean_text(f"{current} {sentence}")
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def build_vietnamese_subtitles(article: Article, page: ExtractedPage) -> str:
    name = display_name(page.title or article.title).replace(" - MS Smile AI Review Hub", "")
    name = re.sub(r"\s+Review.*$", "", name).strip() or display_name(article.title)
    return build_vietnamese_subtitle_lines_for_title(name)


def build_vietnamese_subtitle_lines_for_title(title: str) -> str:
    name = display_name(title).replace(" - MS Smile AI Review Hub", "")
    name = re.sub(r"\s+Review.*$", "", name).strip() or display_name(title)
    lines = [
        f"Nếu bạn đang cân nhắc {name}, đây là tóm tắt nhanh.",
        "Nhiều công cụ AI trông rất tốt trong phần demo.",
        "Điều quan trọng là hiệu quả trong workflow thật.",
        f"Hãy thử {name} với một nhiệm vụ thực tế trước.",
        "Kiểm tra nghiên cứu, brief nội dung và dữ liệu cạnh tranh.",
        "Tập trung vào tính năng chính và giới hạn từng gói.",
        "Điểm mạnh là giúp sàng lọc công cụ nhanh hơn.",
        "Công cụ này phù hợp với đội nội dung và SEO.",
        "Người làm affiliate cũng nên kiểm tra kỹ điều khoản.",
        "Điểm cần thận trọng là giá và chất lượng đầu ra.",
        "Đừng dựa vào ảnh giá cũ hoặc tên gói cũ.",
        "Hãy xác minh giá hiện tại trên website chính thức.",
        "So sánh thêm lựa chọn thay thế trước khi mua.",
        "Nếu cần workflow đơn giản, ưu tiên công cụ dễ thay thế.",
        "Nếu cần dữ liệu sâu, hãy kiểm tra giới hạn gói.",
        "Bài review này không phải là cam kết kết quả.",
        "Hãy xem đây là điểm bắt đầu để nghiên cứu.",
        "Kết luận: chọn công cụ theo nhu cầu và ngân sách.",
        "Xem thêm review AI tại kênh Smile AI Review Hub.",
    ]
    return "\n\n".join(lines) + "\n"


def build_vietnamese_subtitles_from_voiceover(voiceover: str, title: str) -> str:
    name = display_name(title).replace(" - MS Smile AI Review Hub", "")
    name = re.sub(r"\s+Review.*$", "", name).strip() or display_name(title)
    lower_voiceover = voiceover.lower()
    is_seo = "seo" in lower_voiceover or "keyword" in lower_voiceover or "content brief" in lower_voiceover
    lines = [
        f"Nếu bạn đang cân nhắc {name}, đây là tóm tắt nhanh.",
        "Trước khi chi tiền, hãy xem công cụ này có đáng thử không.",
        "Vấn đề là công cụ SEO thường rất ấn tượng trong demo." if is_seo else "Vấn đề là nhiều công cụ AI trông rất tốt trong demo.",
        "Nhưng điều cần biết là nó có cải thiện workflow hằng tuần không.",
        "Hãy kiểm tra giới hạn gói, số lượt dùng và ghế nhóm.",
        "Trước khi mua hoặc quảng bá, hãy xem giá chính thức.",
        "Chúng tôi cập nhật giá, tính năng, ưu nhược điểm và affiliate.",
        f"{name} thuộc nhóm công cụ AI SEO." if is_seo else f"{name} cần được đánh giá theo workflow thực tế.",
        "Cách tốt nhất là thử với một nhiệm vụ lập kế hoạch nội dung.",
        "Hãy xem nghiên cứu từ khóa, brief nội dung và đối thủ." if is_seo else "Hãy xem tác vụ chính, đầu ra và phần cần kiểm tra lại.",
        "Cũng cần kiểm tra phần nào vẫn phải review thủ công.",
        "Với tính năng chính, hãy tập trung vào phần thực tế.",
        f"Dùng checklist này để đánh giá {name} có hệ thống.",
        "Search intent quyết định trang có thể chuyển đổi hay không." if "search intent" in lower_voiceover else "Hãy xem tính năng nào thật sự hỗ trợ quyết định mua.",
        "Hãy kiểm tra độ phủ từ khóa có ý định mua hàng.",
        "Lý do nên shortlist công cụ này nằm ở các use case rõ ràng.",
        "Nó phù hợp với đội SEO đang xây kế hoạch chủ đề." if is_seo else "Nó phù hợp với nhóm cần quy trình đánh giá có cấu trúc.",
        "Đội nội dung có thể dùng để so sánh đối thủ.",
        "Publisher affiliate có thể ưu tiên các trang buyer-intent.",
        "Nhưng vẫn có những điểm cần cân nhắc trước khi mua.",
        "Rủi ro thường nằm ở chính sách, giá hoặc sai workflow.",
        "Không phù hợp nếu bạn chỉ cần danh sách từ khóa một lần.",
        "Cũng không nên kỳ vọng ranking nếu thiếu biên tập.",
        "Về giá, đừng dựa vào ảnh chụp cũ hoặc tên gói cũ.",
        "Giá, ưu đãi và điều kiện payout có thể thay đổi.",
        f"Trước khi mua {name}, hãy kiểm tra trang giá chính thức.",
        "Xem kỹ giới hạn gói, ghế người dùng và điều khoản hủy.",
        "Cũng cần kiểm tra trial và tính năng bạn thật sự cần.",
        "Trước khi quyết định, hãy so sánh thêm các lựa chọn thay thế.",
        f"{name} nên được so với công cụ cùng nhóm trước khi mua.",
        "Ahrefs AI là một góc nhìn khác cho workflow AI SEO." if "ahrefs" in lower_voiceover else "Hãy chọn lựa chọn phù hợp với quy trình lặp lại.",
        "Frase cũng là một lựa chọn AI SEO đáng so sánh." if "frase" in lower_voiceover else "Đừng bỏ qua chi phí và giới hạn sử dụng thực tế.",
        f"Kết luận: {name} đáng shortlist nếu cần hỗ trợ lập kế hoạch SEO." if is_seo else f"Kết luận: {name} đáng shortlist nếu phù hợp workflow thật.",
        "Công cụ nên hỗ trợ nghiên cứu, không thay thế phán đoán biên tập.",
        "Vẫn cần kiểm tra giá, giới hạn gói và kỳ vọng hỗ trợ.",
        "Hãy xem bài review này là điểm bắt đầu để nghiên cứu.",
        "Xem thêm review AI tại:\nyoutube.com/@SmileAIReviewHub",
        "Cảm ơn bạn đã theo dõi.\nHãy ghé Smile AI Review Hub.",
    ]
    return "\n\n".join(lines) + "\n"


def ensure_end_screen_voiceover(article_dir: Path, voiceover: str) -> str:
    voiceover = voiceover.strip()
    if AUTHOR_VOICEOVER not in voiceover:
        if END_SCREEN_VOICEOVER in voiceover:
            voiceover = voiceover.replace(END_SCREEN_VOICEOVER, f"{AUTHOR_VOICEOVER}\n\n{END_SCREEN_VOICEOVER}", 1)
        else:
            voiceover = f"{voiceover}\n\n{AUTHOR_VOICEOVER}".strip()
    if END_SCREEN_VOICEOVER not in voiceover:
        voiceover = f"{voiceover}\n\n{END_SCREEN_VOICEOVER}".strip()
    (article_dir / "voiceover.txt").write_text(voiceover + "\n", encoding="utf-8")
    script_path = article_dir / "script.txt"
    script_text = read_file(script_path)
    if AUTHOR_VOICEOVER not in script_text:
        script_text = script_text.rstrip() + "\n\nAbout the Author\n" + AUTHOR_VOICEOVER
    if END_SCREEN_VOICEOVER not in script_text:
        script_text = script_text.rstrip() + "\n\nEnd Screen\n" + END_SCREEN_VOICEOVER
    script_path.write_text(script_text.lstrip() + "\n", encoding="utf-8")
    return voiceover + "\n"


def normalize_vietnamese_subtitle_event(text: str, max_chars: int = 36) -> str:
    text = clean_text(text)
    if "youtube.com/@SmileAIReviewHub" in text:
        return "Xem thêm review AI tại:\nyoutube.com/@SmileAIReviewHub"
    words = text.split()
    if len(words) <= 7 or len(text) <= max_chars:
        return text
    midpoint = len(words) // 2
    best_index = midpoint
    best_score = 999
    for index in range(3, len(words) - 2):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        if len(left) > max_chars or len(right) > max_chars:
            continue
        score = abs(len(left) - len(right)) + abs(index - midpoint) * 2
        if score < best_score:
            best_index = index
            best_score = score
    left = " ".join(words[:best_index])
    right = " ".join(words[best_index:])
    if left and right and len(left) <= max_chars and len(right) <= max_chars:
        return f"{left}\n{right}"
    return "\n".join(split_subtitle_event_text(text, max_chars=max_chars, max_lines=2)[:1])


def build_srt_to_duration(text: str, target_seconds: float, max_chars: int = 36) -> str:
    chunks = [clean_text(chunk) for chunk in re.split(r"\n\s*\n", text) if clean_text(chunk)]
    if not chunks:
        chunks = split_subtitle_chunks(text)
    events = [normalize_vietnamese_subtitle_event(chunk, max_chars=max_chars) for chunk in chunks]
    events = [event for event in events if clean_text(event)]
    if not events:
        events = ["Đang xem phần đánh giá công cụ AI."]
    target_seconds = max(1.0, target_seconds)
    event_duration = target_seconds / len(events)
    while event_duration > 7.5 and len(events) > 2:
        events = events[:-1] + events[:-2] + [events[-1]]
        event_duration = target_seconds / len(events)
    blocks = []
    current = 0.0
    terminal_events = 0
    for event in reversed(events):
        if "youtube.com/@SmileAIReviewHub" in event or "Cảm ơn" in event:
            terminal_events += 1
        else:
            break
    terminal_seconds = 8.0 if terminal_events else 0.0
    body_target_seconds = max(1.0, target_seconds - terminal_seconds)
    body_event_duration = body_target_seconds / max(1, len(events) - terminal_events)
    terminal_event_duration = terminal_seconds / max(1, terminal_events) if terminal_events else 0.0
    for index, event in enumerate(events, start=1):
        if terminal_events and index > len(events) - terminal_events:
            terminal_index = index - (len(events) - terminal_events)
            current = body_target_seconds + (terminal_index - 1) * terminal_event_duration
            end = target_seconds if index == len(events) else current + terminal_event_duration
        else:
            end = target_seconds if index == len(events) else current + body_event_duration
        blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{event}\n")
        current = end
    return "\n".join(blocks).strip() + "\n"


def srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours = millis // 3_600_000
    millis %= 3_600_000
    minutes = millis // 60_000
    millis %= 60_000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def build_vietnamese_subtitles_from_voiceover(voiceover: str, title: str) -> str:
    name = display_name(title).replace(" - MS Smile AI Review Hub", "")
    name = re.sub(r"\s+Review.*$", "", name).strip() or display_name(title)
    lower_voiceover = voiceover.lower()
    is_seo = "seo" in lower_voiceover or "keyword" in lower_voiceover or "content brief" in lower_voiceover
    lines = [
        f"Nếu bạn đang cân nhắc {name}, đây là phần tóm tắt nhanh.",
        "Trước khi chi tiền, hãy xem công cụ này có hợp workflow không.",
        "Công cụ SEO thường rất ấn tượng trong demo." if is_seo else "Nhiều công cụ AI trông rất tốt trong demo.",
        "Điều quan trọng là nó có cải thiện công việc hằng tuần không.",
        "Hãy kiểm tra giới hạn gói, lượt dùng và ghế nhóm.",
        "Trước khi mua hoặc quảng bá, hãy xem giá chính thức.",
        "Bài review này cập nhật giá, tính năng và affiliate.",
        f"{name} thuộc nhóm công cụ AI SEO." if is_seo else f"{name} nên được đánh giá theo workflow thực tế.",
        "Cách kiểm tra tốt nhất là dùng một nhiệm vụ nội dung thật.",
        "Hãy xem nghiên cứu từ khóa, brief nội dung và đối thủ." if is_seo else "Hãy xem tác vụ chính và phần cần kiểm tra lại.",
        "Đừng bỏ qua những bước vẫn cần review thủ công.",
        "Với tính năng chính, hãy tập trung vào phần thực tế.",
        f"Dùng checklist này để đánh giá {name} có hệ thống.",
        "Search intent quyết định trang có thể chuyển đổi hay không." if "search intent" in lower_voiceover else "Hãy xem tính năng nào hỗ trợ quyết định mua.",
        "Kiểm tra độ phủ từ khóa có ý định mua hàng.",
        "Lý do shortlist nằm ở các use case rõ ràng.",
        "Nó phù hợp với đội SEO xây kế hoạch chủ đề." if is_seo else "Nó phù hợp với nhóm cần quy trình đánh giá rõ ràng.",
        "Đội nội dung có thể dùng để so sánh đối thủ.",
        "Publisher affiliate có thể ưu tiên trang buyer-intent.",
        "Nhưng vẫn có vài điểm cần cân nhắc trước khi mua.",
        "Rủi ro thường nằm ở chính sách, giá hoặc sai workflow.",
        "Không phù hợp nếu bạn chỉ cần danh sách từ khóa một lần.",
        "Cũng không nên kỳ vọng ranking nếu thiếu biên tập.",
        "Về giá, đừng dựa vào ảnh chụp hoặc tên gói cũ.",
        "Giá, ưu đãi và điều kiện payout có thể thay đổi.",
        f"Trước khi mua {name}, hãy kiểm tra trang giá chính thức.",
        "Xem kỹ giới hạn gói, ghế người dùng và điều khoản hủy.",
        "Kiểm tra trial và những tính năng bạn thật sự cần.",
        "Trước khi quyết định, hãy so sánh thêm lựa chọn thay thế.",
        f"{name} nên được so với công cụ cùng nhóm trước khi mua.",
        "Ahrefs AI là một góc nhìn khác cho workflow AI SEO." if "ahrefs" in lower_voiceover else "Hãy chọn lựa chọn phù hợp với quy trình lặp lại.",
        "Frase cũng là một lựa chọn AI SEO đáng so sánh." if "frase" in lower_voiceover else "Đừng bỏ qua chi phí và giới hạn sử dụng thực tế.",
        f"Kết luận: {name} đáng shortlist nếu cần hỗ trợ lập kế hoạch SEO." if is_seo else f"Kết luận: {name} đáng shortlist nếu phù hợp workflow thật.",
        "Công cụ nên hỗ trợ nghiên cứu, không thay thế biên tập.",
        "Vẫn cần kiểm tra giá, giới hạn gói và hỗ trợ.",
        "Hãy xem bài review này là điểm bắt đầu để nghiên cứu.",
        "Xem thêm review AI tại:\nyoutube.com/@SmileAIReviewHub",
        "Cảm ơn bạn đã theo dõi.\nHãy ghé Smile AI Review Hub để xem thêm bài review AI.",
    ]
    return "\n\n".join(lines) + "\n"


def normalize_vietnamese_subtitle_event(text: str, max_chars: int = 34) -> str:
    text = clean_text(text)
    if "youtube.com/@SmileAIReviewHub" in text:
        return "Xem thêm review AI tại:\nyoutube.com/@SmileAIReviewHub"
    if "Cảm ơn" in text:
        return "Cảm ơn bạn đã theo dõi.\nXem thêm review AI tại Smile AI Review Hub."
    words = text.split()
    if len(words) <= 7 or len(text) <= max_chars:
        return text
    midpoint = len(words) // 2
    best_index = midpoint
    best_score = 999
    for index in range(3, len(words) - 2):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        if len(left) > max_chars or len(right) > max_chars:
            continue
        score = abs(len(left) - len(right)) + abs(index - midpoint) * 2
        if score < best_score:
            best_index = index
            best_score = score
    left = " ".join(words[:best_index])
    right = " ".join(words[best_index:])
    if left and right and len(left) <= max_chars and len(right) <= max_chars:
        return f"{left}\n{right}"
    return "\n".join(split_subtitle_event_text(text, max_chars=max_chars, max_lines=2)[:2])


def build_srt_to_duration(text: str, target_seconds: float, max_chars: int = 34) -> str:
    paragraphs = [clean_text(chunk) for chunk in re.split(r"\n\s*\n", text) if clean_text(chunk)]
    chunks: list[str] = []
    for paragraph in paragraphs or split_subtitle_chunks(text):
        sentences = [clean_text(item) for item in re.split(r"(?<=[.!?])\s+", paragraph) if clean_text(item)]
        chunks.extend(sentences or [paragraph])
    seen: set[str] = set()
    events: list[str] = []
    for chunk in chunks:
        for event in split_subtitle_event_text(chunk, max_chars=max_chars, max_lines=2):
            key = re.sub(r"\W+", "", clean_text(event).lower())
            is_terminal = "youtube.com/@SmileAIReviewHub" in event or "Cảm ơn" in event
            if event and (is_terminal or key not in seen):
                events.append(event)
                seen.add(key)
    if not events:
        events = ["Đang xem phần đánh giá công cụ AI."]
    target_seconds = max(1.0, target_seconds)
    terminal_events = 0
    for event in reversed(events):
        if "youtube.com/@SmileAIReviewHub" in event or "Cảm ơn" in event:
            terminal_events += 1
        else:
            break
    terminal_seconds = 8.0 if terminal_events else 0.0
    body_count = max(1, len(events) - terminal_events)
    body_target_seconds = max(1.0, target_seconds - terminal_seconds)
    body_event_duration = body_target_seconds / body_count
    terminal_event_duration = terminal_seconds / max(1, terminal_events) if terminal_events else 0.0
    blocks = []
    current = 0.0
    for index, event in enumerate(events, start=1):
        if terminal_events and index > len(events) - terminal_events:
            terminal_index = index - (len(events) - terminal_events)
            current = body_target_seconds + (terminal_index - 1) * terminal_event_duration
            end = target_seconds if index == len(events) else current + terminal_event_duration
        else:
            end = target_seconds if index == len(events) else current + body_event_duration
        blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{event}\n")
        current = end
    return "\n".join(blocks).strip() + "\n"


VI_VOICEOVER_PHRASES = {
    "If you are considering": "Nếu bạn đang cân nhắc",
    "here is the short version before you spend money": "đây là phần tóm tắt nhanh trước khi bạn chi tiền",
    "The problem is simple": "Vấn đề rất đơn giản",
    "the real question is whether they improve your weekly workflow": "câu hỏi thực sự là chúng có cải thiện quy trình làm việc hằng tuần hay không",
    "The solution is to test": "Giải pháp là thử",
    "against one real content planning task": "với một tác vụ lập kế hoạch nội dung thực tế",
    "Look at": "Hãy xem",
    "and how much manual review is still needed": "và mức độ vẫn cần kiểm tra thủ công",
    "For key features, focus on the practical pieces": "Với các tính năng chính, hãy tập trung vào phần thực tế",
    "The strongest reasons to shortlist it are these": "Đây là những lý do mạnh nhất để đưa công cụ vào danh sách cân nhắc",
    "But there are tradeoffs": "Nhưng vẫn có những điểm đánh đổi",
    "For pricing, do not rely on old screenshots or old plan names": "Về giá, đừng dựa vào ảnh chụp hoặc tên gói cũ",
    "Always verify current pricing on the official website": "Luôn xác minh giá hiện tại trên website chính thức",
    "Before you decide, compare alternatives": "Trước khi quyết định, hãy so sánh các lựa chọn thay thế",
    "My verdict": "Kết luận của tôi",
    "Use this review as a research starting point, not a guarantee": "Hãy dùng bài đánh giá này làm điểm bắt đầu nghiên cứu, không phải sự bảo đảm",
    "Watch more AI tool reviews on the Smile AI Review Hub YouTube channel": "Xem thêm bài đánh giá công cụ AI trên kênh YouTube Smile AI Review Hub",
    "Read the full review and affiliate links at smileaireviewhub.com": "Đọc bài đánh giá đầy đủ và liên kết affiliate tại smileaireviewhub.com",
    "Thank you for watching": "Cảm ơn bạn đã theo dõi",
    "For more AI reviews and comparisons, visit Smile AI Review Hub": "Để xem thêm bài đánh giá và so sánh AI, hãy truy cập Smile AI Review Hub",
    "pricing": "giá",
    "features": "tính năng",
    "alternatives": "lựa chọn thay thế",
    "workflow": "quy trình làm việc",
    "workflows": "quy trình làm việc",
    "content briefs": "brief nội dung",
    "competitor checks": "kiểm tra đối thủ",
    "keyword research": "nghiên cứu từ khóa",
    "manual review": "kiểm tra thủ công",
    "repository context": "ngữ cảnh repository",
    "team policy": "chính sách nhóm",
    "developer productivity": "năng suất lập trình viên",
    "code review": "kiểm tra mã",
    "team adoption": "khả năng áp dụng trong nhóm",
    "pricing risk": "rủi ro giá",
    "brand awareness": "độ nhận diện thương hiệu",
    "weekly": "hằng tuần",
    "buyers comparing": "người mua đang so sánh",
    "with a practical lens": "theo góc nhìn thực tế",
    "impressive in a demo": "ấn tượng trong bản demo",
    "current": "hiện tại",
    "compare": "so sánh",
    "considering": "cân nhắc",
    "shortlist": "danh sách cân nhắc",
    "and": "và",
    "or": "hoặc",
    "before": "trước khi",
    "after": "sau khi",
    "with": "với",
    "without": "không có",
    "for": "cho",
    "official website": "website chính thức",
    "review": "đánh giá",
    "tools": "công cụ",
    "tool": "công cụ",
}


def translate_voiceover_cue_to_vietnamese(text: str) -> str:
    original = clean_text(text)
    patterns = [
        (
            r"This (.+?) review is written for readers who want a practical decision page before they click through",
            r"Bài đánh giá \1 này dành cho người đọc muốn có một trang hỗ trợ quyết định thực tế trước khi nhấp sang website",
        ),
        (
            r"(.+?) sits in the (.+?) category, so the review lens is workflow fit rather than hype",
            r"\1 thuộc danh mục \2, vì vậy bài đánh giá tập trung vào mức phù hợp với quy trình làm việc thay vì quảng cáo cường điệu",
        ),
        (
            r"This category page is for buyers comparing (.+?) with a practical lens: (.+)",
            r"Trang danh mục này dành cho người mua đang so sánh \1 theo góc nhìn thực tế: \2",
        ),
        (
            r"Instead of ranking tools only by brand awareness, it looks at (.+)",
            r"Thay vì chỉ xếp hạng công cụ theo độ nhận diện thương hiệu, trang này xem xét \1",
        ),
    ]
    translated = original
    for pattern, replacement in patterns:
        updated = re.sub(pattern, replacement, translated, flags=re.I)
        if updated != translated:
            translated = updated
            break
    for source, target in sorted(VI_VOICEOVER_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.escape(source)
        if re.fullmatch(r"[A-Za-z0-9 ]+", source):
            pattern = rf"(?<!\w){pattern}(?!\w)"
        translated = re.sub(pattern, target, translated, flags=re.I)
    translated = translated.replace(":", ":").strip()
    if translated == original:
        translated = f"Nội dung đang nói về: {translated}"
    return translated


def build_paired_bilingual_srts(
    voiceover: str,
    target_seconds: float,
    english_max_chars: int = 105,
    vietnamese_max_chars: int = 115,
) -> tuple[str, str, str]:
    sentences = [clean_text(item) for item in re.split(r"(?<=[.!?])\s+|\n\s*\n", voiceover) if clean_text(item)]
    english_events: list[str] = []
    for sentence in sentences:
        english_events.extend(split_subtitle_event_text(sentence, max_chars=english_max_chars, max_lines=1))
    if not english_events:
        raise RuntimeError("English voiceover produced no subtitle cues")

    weights = [max(1, len(event.split())) for event in english_events]
    total_weight = max(1, sum(weights))
    current = 0.0
    english_blocks: list[str] = []
    vietnamese_blocks: list[str] = []
    vietnamese_text: list[str] = []
    for index, (english_event, weight) in enumerate(zip(english_events, weights), start=1):
        end = target_seconds if index == len(english_events) else current + target_seconds * weight / total_weight
        vietnamese_event = translate_voiceover_cue_to_vietnamese(english_event)
        english_blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{english_event}\n")
        vietnamese_blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{vietnamese_event}\n")
        vietnamese_text.append(vietnamese_event)
        current = end
    return (
        "\n".join(english_blocks).strip() + "\n",
        "\n".join(vietnamese_blocks).strip() + "\n",
        "\n\n".join(vietnamese_text).strip() + "\n",
    )


def paired_voiceover_cues(voiceover: str, english_max_chars: int = 105) -> list[tuple[str, str]]:
    sentences = [clean_text(item) for item in re.split(r"(?<=[.!?])\s+|\n\s*\n", voiceover) if clean_text(item)]
    pairs: list[tuple[str, str]] = []
    for sentence in sentences:
        for english_event in split_subtitle_event_text(sentence, max_chars=english_max_chars, max_lines=1):
            pairs.append((english_event, translate_voiceover_cue_to_vietnamese(english_event)))
    return pairs


def translate_paired_cues_with_google(
    pairs: list[tuple[str, str]],
    cache_path: Path,
) -> list[tuple[str, str]]:
    cache = load_json(cache_path, {})
    if not isinstance(cache, dict):
        cache = {}
    translated_pairs: list[tuple[str, str]] = []
    for english_event, _ in pairs:
        vietnamese_event = clean_text(str(cache.get(english_event) or ""))
        if not vietnamese_event:
            try:
                response = requests.get(
                    "https://translate.googleapis.com/translate_a/single",
                    params={"client": "gtx", "sl": "en", "tl": "vi", "dt": "t", "q": english_event},
                    timeout=25,
                )
                response.raise_for_status()
                data = response.json()
                vietnamese_event = clean_text("".join(str(part[0]) for part in data[0] if part and part[0]))
            except Exception as exc:
                raise RuntimeError(f"Vietnamese translation failed for cue: {english_event}") from exc
            if not vietnamese_event:
                raise RuntimeError(f"Vietnamese translation returned empty text for cue: {english_event}")
            cache[english_event] = vietnamese_event
            cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        translated_pairs.append((english_event, vietnamese_event))
    return translated_pairs


def build_paired_srts_from_durations(
    pairs: list[tuple[str, str]],
    durations: list[float],
) -> tuple[str, str, str]:
    if not pairs or len(pairs) != len(durations):
        raise RuntimeError("Paired subtitle cues and audio durations do not match")
    english_blocks: list[str] = []
    vietnamese_blocks: list[str] = []
    vietnamese_text: list[str] = []
    current = 0.0
    for index, ((english_event, vietnamese_event), duration) in enumerate(zip(pairs, durations), start=1):
        end = current + max(0.25, duration)
        english_blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{english_event}\n")
        vietnamese_blocks.append(f"{index}\n{srt_time(current)} --> {srt_time(end)}\n{vietnamese_event}\n")
        vietnamese_text.append(vietnamese_event)
        current = end
    return (
        "\n".join(english_blocks).strip() + "\n",
        "\n".join(vietnamese_blocks).strip() + "\n",
        "\n\n".join(vietnamese_text).strip() + "\n",
    )


def build_scenes(article: Article, voiceover: str) -> list[dict[str, str]]:
    sections = SECTION_LIMITS[article.page_type]
    total_words = max(1, len(voiceover.split()))
    total_seconds = max(45, int(total_words / 2.35))
    scene_duration = max(12, int(total_seconds / max(1, len(sections))))
    scenes = []
    start = 0
    for index, section in enumerate(sections):
        end = total_seconds if index == len(sections) - 1 else min(total_seconds, start + scene_duration)
        scenes.append(
            {
                "time": f"{start}-{end}",
                "type": slugify(section),
                "title": section if index else display_name(article.title),
            }
        )
        start = end
    return scenes


def classify_narration_scene(text: str, first: bool = False) -> tuple[str, str]:
    lower = clean_text(text).lower()
    if "thank you for watching" in lower or "visit smile ai review hub" in lower:
        return "end-screen", "Thank You"
    if "nguyen quoc tuan" in lower or "about-author" in lower or "independent ai and saas researcher" in lower:
        return "author", "About the Author"
    if any(phrase in lower for phrase in ["my verdict", "final verdict", "worth shortlisting", "recommended next step"]):
        return "final-verdict", "Final Verdict"
    rules = [
        ("alternatives", "Alternatives", ["alternative", "compared against", "compare with"]),
        ("cons", "Cons", ["limitation", "downside", "friction", "risk", "tradeoff", "not a fit", "not best"]),
        ("pros", "Pros", ["advantage", "strength", "strongest reason", "best reason", "stands out", "good fit"]),
        ("best-use-cases", "Best Use Cases", ["best for", "use case", "who should", "teams that"]),
        ("key-features", "Key Features", ["feature", "integration", "workflow", "dashboard", "automation"]),
        ("pricing", "Pricing", ["pricing", "price", "plan limit", "trial", "cancellation", "cost"]),
    ]
    scored = [
        (sum(lower.count(phrase) for phrase in phrases), scene_type, title)
        for scene_type, title, phrases in rules
    ]
    score, scene_type, title = max(scored)
    if score >= 2 or (scene_type in {"alternatives", "cons", "pros", "best-use-cases"} and score >= 1):
        return scene_type, title
    if first:
        return "intro", "Introduction"
    return "overview", "Overview"


def build_audio_aligned_scenes(
    cue_pairs: list[tuple[str, str]],
    cue_durations: list[float],
    target_seconds: float = 11.0,
    max_seconds: float = 15.0,
) -> list[dict[str, object]]:
    if not cue_pairs or len(cue_pairs) != len(cue_durations):
        return []
    grouped: list[dict[str, object]] = []
    current_pairs: list[tuple[str, str]] = []
    current_duration = 0.0
    current_type = ""
    for pair, duration in zip(cue_pairs, cue_durations):
        english = clean_text(pair[0])
        force_single = "thank you for watching" in english.lower()
        pair_type, _ = classify_narration_scene(english, first=not grouped and not current_pairs)
        topic_change = current_pairs and current_duration >= 7.0 and pair_type != "overview" and pair_type != current_type
        if current_pairs and (force_single or topic_change or current_duration + duration > max_seconds):
            text = " ".join(item[0] for item in current_pairs)
            scene_type, title = classify_narration_scene(text, first=not grouped)
            grouped.append({"type": scene_type, "title": title, "narration": text, "duration": current_duration})
            current_pairs = []
            current_duration = 0.0
            current_type = ""
        current_pairs.append(pair)
        current_duration += duration
        current_type, _ = classify_narration_scene(" ".join(item[0] for item in current_pairs), first=not grouped)
        if force_single or current_duration >= target_seconds:
            text = " ".join(item[0] for item in current_pairs)
            scene_type, title = classify_narration_scene(text, first=not grouped)
            grouped.append({"type": scene_type, "title": title, "narration": text, "duration": current_duration})
            current_pairs = []
            current_duration = 0.0
    if current_pairs:
        text = " ".join(item[0] for item in current_pairs)
        scene_type, title = classify_narration_scene(text, first=not grouped)
        grouped.append({"type": scene_type, "title": title, "narration": text, "duration": current_duration})
    return grouped


def thumbnail_text(article: Article, page: ExtractedPage) -> str:
    title = page.title or article.title
    if article.page_type == "comparison":
        if article.tool_a and article.tool_b:
            return f"{article.tool_a} vs {article.tool_b}"
        match = re.search(r"(.+?)\s+vs\s+(.+?)(:|$)", title, re.I)
        if match:
            return f"{clean_text(match.group(1))} vs {clean_text(match.group(2))}"
    if article.page_type == "pricing":
        return f"{display_name(title).split(':')[0]} Pricing Guide"
    if article.page_type == "category":
        return f"Best {display_name(title).replace(' to Research Before You Buy', '')}"
    name = re.sub(r"\s+Review.*$", " Review", display_name(title), flags=re.I)
    if "Review" not in name:
        name = f"{name} Review"
    return f"{name} 2026"


def create_thumbnail(path: Path, text: str, article_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), "#f8fbff")
    draw = ImageDraw.Draw(image)
    colors = {
        "review": ("#0f766e", "#dbeafe"),
        "comparison": ("#1d4ed8", "#dcfce7"),
        "pricing": ("#9a3412", "#ffedd5"),
        "category": ("#334155", "#e0f2fe"),
    }
    accent, panel = colors.get(article_type, colors["review"])
    draw.rectangle((0, 0, width, 88), fill=accent)
    draw.text((52, 28), "MS Smile AI Review Hub", fill="#ffffff", font=font(34, bold=True))
    draw.rounded_rectangle((52, 132, width - 52, height - 80), radius=28, fill=panel, outline="#bfdbfe", width=3)
    draw.text((82, 164), article_type.upper(), fill=accent, font=font(28, bold=True))
    draw_multiline(draw, text, (82, 228), width - 164, font(76, bold=True), "#0f172a", max_lines=3)
    draw.text((82, height - 138), "Research-style review. Verify current pricing and features.", fill="#475569", font=font(28))
    image.save(path)


def site_profile() -> dict[str, object]:
    stats = load_json(SITE_STATS_CONFIG, {})
    author = stats.get("author", {}) if isinstance(stats.get("author"), dict) else {}
    channels = stats.get("communityChannels", []) if isinstance(stats.get("communityChannels"), list) else []
    links = {clean_text(item.get("name", "")).lower(): clean_text(item.get("url", "")) for item in channels if isinstance(item, dict)}
    return {
        "author_name": clean_text(author.get("name", "")) or "Nguyen Quoc Tuan",
        "author_bio": clean_text(author.get("title", "")) or "Founder - MS Smile AI Review Hub",
        "website": BASE_URL,
        "youtube": YOUTUBE_CHANNEL_URL,
        "facebook": links.get("facebook") or "https://facebook.com/SmileAIReviewHub",
        "x": links.get("x") or "https://x.com/AIReviewHub",
        "linkedin": links.get("linkedin") or "https://linkedin.com",
        "quora": links.get("quora") or "https://quora.com",
    }


def compact_display_url(value: object) -> str:
    text = clean_text(str(value or ""))
    replacements = {
        "https://smileaireviewhub.com": "smileaireviewhub.com",
        "https://youtube.com/@SmileAIReviewHub": "youtube.com/@SmileAIReviewHub",
        "https://web.facebook.com/Tuanpk.AI.Workflows": "facebook.com/Tuanpk.AI.Workflows",
        "https://x.com/Tuanpk5": "x.com/Tuanpk5",
        "https://www.linkedin.com/in/tuan-nguyen-quoc-8a01ba210/": "linkedin.com/in/tuan-nguyen-quoc-8a01ba210",
        "https://www.quora.com/profile/Tuan-Nguyen-Quoc-10": "quora.com/profile/Tuan-Nguyen-Quoc-10",
    }
    if text in replacements:
        return replacements[text]
    text = re.sub(r"^https?://(www\.)?", "", text).rstrip("/")
    return text


def draw_round_mark(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, label: str, fill: str = "#0f766e") -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline="#5eead4", width=3)
    label_font = font(max(16, int(radius * 0.78)), bold=True)
    bbox = draw.textbbox((0, 0), label, font=label_font)
    draw.text((x - (bbox[2] - bbox[0]) / 2, y - (bbox[3] - bbox[1]) / 2 - 2), label, fill="#ffffff", font=label_font)


def create_research_summary_slide(path: Path, metadata: dict[str, object], tool_name: str, render_date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1920, 1080
    profile = site_profile()
    image = Image.new("RGB", (width, height), "#071827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill="#071827")
    draw.rectangle((0, 0, width, 112), fill="#0f766e")
    draw.text((64, 34), "MS Smile AI Review Hub", fill="#ffffff", font=font(38, bold=True))
    subtitle_safe_top = int(height * 0.82)
    card = (260, 150, width - 260, subtitle_safe_top - 62)
    draw.rounded_rectangle(card, radius=28, fill="#f8fbff", outline="#5eead4", width=4)
    draw_round_mark(draw, (card[0] + 78, card[1] + 78), 42, "MS")
    draw_round_mark(draw, (card[0] + 170, card[1] + 78), 36, "YT", "#dc2626")
    draw.text((card[0] + 236, card[1] + 48), "RESEARCH SUMMARY", fill="#0f172a", font=font(54, bold=True))
    rows = [
        ("Tool", trim_words(tool_name, 5)),
        ("Author", str(profile["author_name"])),
        ("Brand", "Smile AI Review Hub"),
        ("Research Date", render_date),
        ("Website", "smileaireviewhub.com"),
        ("YouTube", "@SmileAIReviewHub"),
        ("Category", "AI Tool Review"),
        ("Report Version", "2026 Edition"),
    ]
    left_x, right_x = card[0] + 90, card[0] + 780
    y = card[1] + 190
    for idx, (label, value) in enumerate(rows):
        x = left_x if idx < 4 else right_x
        yy = y + (idx if idx < 4 else idx - 4) * 80
        draw.text((x, yy), f"{label}:", fill="#0f766e", font=font(30, bold=True))
        draw_multiline(draw, value, (x + 230, yy - 1), 520, font(30), "#0f172a", max_lines=1)
    icon_y = card[3] - 122
    social_items = [
        ("FB", profile.get("facebook")),
        ("X", profile.get("x")),
        ("IN", profile.get("linkedin")),
        ("Q", profile.get("quora")),
    ]
    draw.text((card[0] + 90, icon_y - 16), "Public social links", fill="#334155", font=font(26, bold=True))
    for idx, (label, value) in enumerate(social_items):
        if not value:
            continue
        draw_round_mark(draw, (card[0] + 390 + idx * 82, icon_y), 28, label, "#102a43")
    disclaimer_y = card[3] - 54
    draw.text((card[0] + 90, disclaimer_y), "Information verified at render time. Features and pricing may change.", fill="#475569", font=font(22, bold=True))
    watermark = load_video_render_config().get("watermark", "smileaireviewhub.com")
    draw.text((width - 265, height - 54), str(watermark), fill="#93c5fd", font=font(20))
    image.save(path)


def create_end_screen_slide(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), "#071827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill="#071827")
    draw.rectangle((0, 0, width, 126), fill="#0f766e")
    draw.text((64, 38), "MS Smile AI Review Hub", fill="#ffffff", font=font(42, bold=True))
    draw.text((110, 210), "THANK YOU FOR WATCHING", fill="#ffffff", font=font(76, bold=True))
    draw.text((110, 318), "Smile AI Review Hub", fill="#5eead4", font=font(54, bold=True))
    draw.rounded_rectangle((110, 430, 1140, 606), radius=22, fill="#0b2338", outline="#155e75", width=3)
    draw.text((150, 462), "Read the full review: smileaireviewhub.com", fill="#dbeafe", font=font(34, bold=True))
    draw.text((150, 530), "YouTube: @SmileAIReviewHub", fill="#dbeafe", font=font(34, bold=True))
    draw.rounded_rectangle((110, 638, 1040, 850), radius=22, fill="#102a43", outline="#14b8a6", width=3)
    draw.text((150, 672), "Follow us for:", fill="#ffffff", font=font(36, bold=True))
    for idx, item in enumerate(["AI Reviews", "AI Comparisons", "Productivity Tools", "Automation Guides"]):
        x = 150 + (idx % 2) * 430
        y = 738 + (idx // 2) * 62
        draw.ellipse((x, y + 8, x + 20, y + 28), fill="#14b8a6")
        draw.text((x + 36, y), item, fill="#dbeafe", font=font(30))
    watermark = load_video_render_config().get("watermark", "smileaireviewhub.com")
    draw.text((width - 265, height - 54), str(watermark), fill="#93c5fd", font=font(20))
    image.save(path)


def create_author_slide(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), "#071827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill="#071827")
    draw.rectangle((0, 0, width, 126), fill="#0f766e")
    draw.text((64, 38), "MS Smile AI Review Hub", fill="#ffffff", font=font(42, bold=True))
    draw.text((110, 205), "ABOUT THE AUTHOR", fill="#ffffff", font=font(72, bold=True))
    draw.text((112, 296), "Về tác giả", fill="#5eead4", font=font(38, bold=True))
    draw_round_mark(draw, (330, 545), 145, "NT", "#0f766e")
    draw.rounded_rectangle((560, 385, 1660, 820), radius=28, fill="#f8fbff", outline="#5eead4", width=4)
    draw.text((630, 438), "Nguyen Quoc Tuan", fill="#0f172a", font=font(58, bold=True))
    draw.text((630, 522), "Independent AI & SaaS Researcher", fill="#0f766e", font=font(34, bold=True))
    draw.text((630, 592), "AI tools • SaaS software • Automation systems", fill="#334155", font=font(29))
    draw.text((630, 646), "Productivity workflows • Practical buyer research", fill="#334155", font=font(29))
    draw.text((630, 694), "Last updated: June 2026", fill="#334155", font=font(27, bold=True))
    draw.text((630, 748), "smileaireviewhub.com/about-author/", fill="#1d4ed8", font=font(27, bold=True))
    watermark = load_video_render_config().get("watermark", "smileaireviewhub.com")
    draw.text((width - 265, height - 54), str(watermark), fill="#93c5fd", font=font(20))
    image.save(path)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_multiline(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], max_width: int, fnt, fill: str, max_lines: int) -> None:
    words = text.split()
    lines = wrap_text(text, fnt, max_width, draw)
    lines = lines[:max_lines]
    if len(lines) == max_lines and len(" ".join(lines).split()) < len(words):
        lines[-1] = lines[-1].rstrip(" .") + "..."
    x, y = xy
    for line in lines:
        draw.text((x, y), line, fill=fill, font=fnt)
        y += int(fnt.size * 1.12) if hasattr(fnt, "size") else 52


def wrap_text(text: str, fnt, max_width: int, draw: ImageDraw.ImageDraw | None = None) -> list[str]:
    draw = draw or ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = clean_text(f"{current} {word}")
        bbox = draw.textbbox((0, 0), candidate, font=fnt)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def command_version(command: str) -> bool:
    try:
        subprocess.run([command, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def load_video_render_config() -> dict:
    config = dict(DEFAULT_VIDEO_RENDER_CONFIG)
    if VIDEO_RENDER_CONFIG.exists():
        try:
            loaded = json.loads(VIDEO_RENDER_CONFIG.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except Exception:
            pass
    return config


def save_video_render_config(config: dict) -> None:
    VIDEO_RENDER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_VIDEO_RENDER_CONFIG)
    merged.update(config)
    VIDEO_RENDER_CONFIG.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def where_candidates(name: str) -> list[Path]:
    try:
        result = subprocess.run(["where.exe", name], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except Exception:
        return []
    candidates = []
    for line in result.stdout.splitlines():
        path = Path(line.strip())
        if path.exists():
            candidates.append(path)
    return candidates


def common_ffmpeg_candidates(name: str) -> list[Path]:
    candidates = []
    local_appdata = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Admin/AppData/Local"))
    user_profile = Path(os.environ.get("USERPROFILE", "C:/Users/Admin"))
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    for root in [
        Path(f"C:/Program Files/FFmpeg/bin"),
        Path(f"C:/Program Files/ffmpeg/bin"),
        Path(f"C:/ffmpeg/bin"),
        local_appdata / "Microsoft" / "WindowsApps",
        local_appdata / "Microsoft" / "WinGet" / "Links",
        local_appdata / "Microsoft" / "WinGet" / "Packages",
        local_appdata / "Programs",
        user_profile / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages",
        user_profile / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        user_profile / "AppData" / "Local" / "Programs",
        program_files / "Gyan" / "FFmpeg",
        program_files / "FFmpeg",
        program_files / "ffmpeg",
        program_files / "Gyan",
        program_files_x86 / "Gyan" / "FFmpeg",
        Path("C:/ffmpeg"),
        Path("C:/ProgramData/chocolatey/bin"),
    ]:
        if not root.exists():
            continue
        if root.name == "bin":
            candidates.append(root / f"{name}.exe")
            continue
        try:
            candidates.extend(root.glob(f"**/{name}.exe"))
        except Exception:
            continue
    return candidates[:20]


def resolve_tool(name: str) -> str | None:
    config = load_video_render_config()
    override = str(config.get(f"{name}_path", "") or "").strip()
    if override:
        path = Path(override)
        if path.exists() and command_version(str(path)):
            return str(path)
    found = shutil.which(name)
    if found and command_version(found):
        return found
    for candidate in where_candidates(name):
        if candidate.exists() and command_version(str(candidate)):
            return str(candidate)
    for candidate in common_ffmpeg_candidates(name):
        if candidate.exists() and command_version(str(candidate)):
            return str(candidate)
    return None


def detect_ffmpeg() -> dict[str, str | bool]:
    ffmpeg = resolve_tool("ffmpeg")
    ffprobe = resolve_tool("ffprobe")
    return {
        "available": bool(ffmpeg and ffprobe),
        "ffmpeg": ffmpeg or "",
        "ffprobe": ffprobe or "",
    }


def split_scene_time(value: str) -> tuple[int, int]:
    match = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", str(value))
    if not match:
        return 0, 30
    start = int(match.group(1))
    end = max(start + 5, int(match.group(2)))
    return start, end


def bullet_lines_from_script(script: str, scene_title: str, count: int = 3) -> list[str]:
    lines = [clean_text(line) for line in script.splitlines()]
    candidates = []
    capture = False
    for line in lines:
        if not line:
            continue
        if line.lower() == scene_title.lower():
            capture = True
            continue
        if capture and line in sum(SECTION_LIMITS.values(), []):
            break
        if capture:
            candidates.extend(re.split(r"(?<=[.!?])\s+", line))
    if not candidates:
        candidates = re.split(r"(?<=[.!?])\s+", " ".join(lines[1:]))
    bullets = []
    for candidate in candidates:
        text = trim_words(candidate, 12)
        if len(text) >= 28:
            bullets.append(text)
        if len(bullets) >= count:
            break
    return bullets or ["Research-style review.", "Verify pricing and features.", "Review manually before publishing."]


def short_slide_title(title: str, fallback: str = "Review notes") -> str:
    clean = clean_text(title)
    clean = re.sub(r":.*$", "", clean)
    clean = re.sub(r"\bWorkflow Fit\b.*$", "", clean, flags=re.I)
    return trim_words(clean or fallback, 8)


def fit_image_contain(image: Image.Image, size: tuple[int, int], fill: str = "#f8fafc") -> Image.Image:
    target_w, target_h = size
    image = image.convert("RGB")
    scale = min(target_w / image.width, target_h / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, fill)
    left = (target_w - resized.width) // 2
    top = (target_h - resized.height) // 2
    canvas.paste(resized, (left, top))
    return canvas


def collect_visual_assets(article_dir: Path, article: Article | None = None) -> list[Path]:
    assets: list[Path] = []
    for candidate in [article_dir / "thumbnail.png"]:
        if candidate.exists():
            assets.append(candidate)
    slug_candidates = []
    if article:
        slug_candidates.append(article.slug.replace("review-", "").replace("pricing-", ""))
        if article.tool_a:
            slug_candidates.append(slugify(article.tool_a))
        if article.tool_b:
            slug_candidates.append(slugify(article.tool_b))
    slug_candidates.append(article_dir.name.replace("review-", "").replace("pricing-", ""))
    for slug in dict.fromkeys(slug_candidates):
        for folder in [ASSETS_DIR / "screenshots", ASSETS_DIR / "og" / "pages", article_dir / "editor_assets" / "visuals"]:
            if not folder.exists():
                continue
            for ext in ("png", "jpg", "jpeg", "webp"):
                for candidate in folder.glob(f"*{slug}*.{ext}"):
                    if candidate.exists() and candidate not in assets:
                        assets.append(candidate)
    return assets


SCENE_VISUAL_KEYWORDS = {
    "intro": ["quick verdict", "overview", "short answer"],
    "introduction": ["overview", "introduction", "short answer"],
    "overview": ["overview", "quick verdict", "hands-on review"],
    "key-features": ["feature", "workflow", "how it works", "standout strengths"],
    "feature-comparison": ["feature", "comparison", "workflow"],
    "pros": ["pros", "strength", "best for"],
    "cons": ["cons", "limitation", "friction", "not best", "risk"],
    "pros-cons": ["pros", "cons", "strength", "limitation"],
    "pricing": ["pricing", "price", "plan", "cost"],
    "pricing-notes": ["pricing", "price", "plan", "cost"],
    "pricing-comparison": ["pricing", "price", "plan", "cost"],
    "plan-checks": ["plan", "pricing", "check"],
    "alternatives": ["alternative", "compare", "comparison"],
    "top-tools": ["top tools", "tool", "shortlist"],
    "how-to-choose": ["choose", "buying", "consideration"],
    "best-use-cases": ["use case", "best for", "who should"],
    "use-cases": ["use case", "best for", "who should"],
    "best-for": ["best for", "who should", "audience"],
    "risks": ["risk", "cons", "limitation", "warning"],
    "winner": ["winner", "verdict", "conclusion"],
    "final-verdict": ["verdict", "conclusion", "recommended next step"],
    "conclusion": ["conclusion", "verdict", "recommended next step"],
}


def scene_visual_keywords(scene: dict[str, str]) -> list[str]:
    scene_type = slugify(clean_text(scene.get("type", "")))
    title = clean_text(scene.get("title", "")).lower()
    keywords = list(SCENE_VISUAL_KEYWORDS.get(scene_type, []))
    keywords.extend(part for part in re.split(r"[^a-z0-9]+", title) if len(part) >= 4)
    narration = clean_text(str(scene.get("narration", ""))).lower()
    keywords.extend(part for part in re.split(r"[^a-z0-9]+", narration) if len(part) >= 6)
    return list(dict.fromkeys(keywords))


def choose_page_section(page: ExtractedPage, scene: dict[str, str], used_headings: set[str]) -> tuple[str, list[str]]:
    keywords = scene_visual_keywords(scene)
    scored: list[tuple[int, str, list[str]]] = []
    for heading, values in page.headings.items():
        clean_heading = clean_text(heading)
        usable = [clean_text(value) for value in values if len(clean_text(value)) >= 28]
        if not clean_heading or not usable:
            continue
        heading_lower = clean_heading.lower()
        score = sum(5 for keyword in keywords if keyword in heading_lower)
        score += sum(1 for keyword in keywords if any(keyword in value.lower() for value in usable[:4]))
        if clean_heading in used_headings:
            score -= 4
        scored.append((score, clean_heading, usable))
    if not scored:
        return clean_text(scene.get("title", "Review notes")), page.all_text[:4]
    scored.sort(key=lambda item: (item[0], item[1] not in used_headings), reverse=True)
    _, heading, values = scored[0]
    used_headings.add(heading)
    return heading, values


def create_article_section_visual(
    path: Path,
    article_title: str,
    section_title: str,
    lines: list[str],
    scene_type: str,
) -> None:
    width, height = 1200, 720
    path.parent.mkdir(parents=True, exist_ok=True)
    palette = {
        "pros": ("#166534", "#dcfce7"),
        "cons": ("#991b1b", "#fee2e2"),
        "pricing": ("#1d4ed8", "#dbeafe"),
        "alternatives": ("#7c3aed", "#ede9fe"),
        "final-verdict": ("#0f766e", "#ccfbf1"),
    }
    accent, tint = palette.get(slugify(scene_type), ("#0f766e", "#e6fffb"))
    image = Image.new("RGB", (width, height), "#eef4f8")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((34, 28, width - 34, height - 28), radius=24, fill="#ffffff", outline="#cbd5e1", width=3)
    draw.rectangle((34, 28, width - 34, 112), fill=accent)
    draw.text((72, 52), "MS Smile AI Review Hub", fill="#ffffff", font=font(28, bold=True))
    draw.text((width - 292, 54), "ARTICLE SECTION", fill="#ffffff", font=font(22, bold=True))

    draw.text((72, 145), trim_words(article_title, 10), fill="#475569", font=font(23, bold=True))
    section_font = font(44, bold=True)
    draw_multiline(draw, section_title, (72, 184), width - 144, section_font, "#0f172a", max_lines=2)
    draw.rounded_rectangle((72, 300, width - 72, height - 82), radius=20, fill=tint, outline=accent, width=2)

    y = 334
    body_font = font(27)
    for line in lines[:4]:
        visible = trim_words(line, 18)
        wrapped = wrap_text(visible, body_font, width - 230)[:2]
        needed = max(1, len(wrapped)) * 37 + 24
        if y + needed > height - 112:
            break
        draw.ellipse((104, y + 9, 120, y + 25), fill=accent)
        draw_multiline(draw, visible, (142, y), width - 250, body_font, "#1e293b", max_lines=2)
        y += needed
    draw.text((72, height - 64), "Source: article content", fill="#64748b", font=font(20))
    image.save(path)


def build_contextual_scene_visuals(
    article_dir: Path,
    article: Article,
    page: ExtractedPage,
    scenes: list[dict[str, str]],
    visual_assets: list[Path],
) -> list[Path]:
    section_dir = article_dir / "editor_assets" / "article_sections"
    used_headings: set[str] = set()
    contextual: list[Path] = []
    product_screenshot = next(
        (path for path in visual_assets if path.parent.name == "screenshots" and path.exists()),
        None,
    )
    for index, scene in enumerate(scenes, start=1):
        scene_type = slugify(clean_text(scene.get("type", "")))
        if product_screenshot and scene_type in {"key-features", "tool-a", "tool-b"}:
            contextual.append(product_screenshot)
            continue
        heading, values = choose_page_section(page, scene, used_headings)
        output = section_dir / f"{index:02}-{scene_type}.png"
        create_article_section_visual(
            output,
            page.title or article.title,
            heading,
            values,
            scene_type,
        )
        contextual.append(output)
    return contextual


def create_video_slide(path: Path, title: str, bullets: list[str], size: tuple[int, int], label: str = "", progress: float = 0.0, slide_kind: str = "section", visual_path: Path | None = None) -> None:
    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, "#071827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill="#071827")
    subtitle_safe_top = int(height * 0.82)
    content_bottom = subtitle_safe_top - (34 if width >= 1200 else 44)
    if slide_kind in {"title", "cta", "verdict"}:
        draw.rectangle((0, 0, width, int(height * 0.12)), fill="#0f766e")
        draw.text((54, 34 if height >= 1080 else 24), "MS Smile AI Review Hub", fill="#ffffff", font=font(42 if width > 1200 else 32, bold=True))

    left_x = 96 if width >= 1200 else 64
    left_w = min(int(width * 0.35), 620 if width >= 1200 else int(width * 0.40))
    gap = 96 if width >= 1200 else 56
    title_y = int(height * 0.22)
    title_size = (96 if slide_kind in {"title", "cta", "verdict"} else 66) if width > 1200 else 56
    title_font = font(title_size, bold=True)
    title_x = left_x
    title_w = left_w
    if slide_kind == "verdict":
        title_x = left_x
        title_w = min(int(width * 0.68), width - title_x - left_x)
    while title_size > 42 and len(wrap_text(title, title_font, title_w)) > 3:
        title_size -= 4
        title_font = font(title_size, bold=True)
    title_lines = min(3, max(1, len(wrap_text(title, title_font, title_w))))
    line_height = title_font.size + 12
    title_box = (title_x, title_y, title_x + title_w, title_y + title_lines * line_height)

    visual_left = title_x + title_w + gap
    visual_bottom = min(content_bottom, int(height * 0.72) if slide_kind in {"section", "comparison", "proscons"} else int(height * 0.80))
    visual_box = (visual_left, int(height * 0.11), width - 42, visual_bottom)
    if slide_kind == "verdict":
        visual_box = (width, height, width, height)
    elif boxes_overlap(title_box, visual_box):
        visual_left = min(width - 520, title_box[2] + gap)
        visual_box = (visual_left, visual_box[1], width - 42, visual_box[3])
        if boxes_overlap(title_box, visual_box):
            shrink = boxes_overlap(title_box, visual_box)
            visual_box = (max(title_box[2] + gap, visual_box[0] + (80 if shrink else 0)), visual_box[1], width - 42, visual_box[3])
    if slide_kind != "verdict":
        draw.rounded_rectangle(visual_box, radius=34, fill="#0b2338", outline="#164e63", width=3)
    if slide_kind != "verdict" and visual_path and visual_path.exists():
        try:
            visual = fit_image_contain(Image.open(visual_path), (visual_box[2] - visual_box[0] - 28, visual_box[3] - visual_box[1] - 28))
            image.paste(visual, (visual_box[0] + 14, visual_box[1] + 14))
            draw.rounded_rectangle(visual_box, radius=34, outline="#5eead4", width=3)
        except Exception:
            draw_branded_visual(draw, visual_box, title)
    elif slide_kind != "verdict":
        draw_branded_visual(draw, visual_box, title)
    if slide_kind in {"title", "cta"}:
        draw.rounded_rectangle((54, int(height * 0.18), int(width * 0.18), int(height * 0.34)), radius=22, fill="#0f766e")
        icon_text = "AI"
        icon_font = font(52 if width > 1200 else 46, bold=True)
        icon_bbox = draw.textbbox((0, 0), icon_text, font=icon_font)
        icon_x = 54 + (int(width * 0.18) - 54 - (icon_bbox[2] - icon_bbox[0])) // 2
        icon_y = int(height * 0.18) + (int(height * 0.34) - int(height * 0.18) - (icon_bbox[3] - icon_bbox[1])) // 2
        draw.text((icon_x, icon_y), icon_text, fill="#ffffff", font=icon_font)
    if label and slide_kind in {"title", "cta"}:
        draw.text((54, int(height * 0.18)), label.upper(), fill="#5eead4", font=font(28 if width > 1200 else 24, bold=True))
    draw_multiline(draw, title, (title_x, title_y), title_w, title_font, "#ffffff", max_lines=3)
    vietnamese_title = SLIDE_TITLE_VI.get(clean_text(title).lower(), "")
    if vietnamese_title:
        vietnamese_title_y = title_y + title_lines * line_height + 8
        draw.text(
            (title_x, vietnamese_title_y),
            vietnamese_title,
            fill="#5eead4",
            font=font(34 if width > 1200 else 28, bold=True),
        )
    y = int(height * 0.43)
    bullet_font = font(36 if width > 1200 else 31)
    card_x = left_x
    card_w = left_w
    card_step = 92 if width > 1200 else 108
    if slide_kind == "verdict":
        card_x = title_x
        card_w = min(int(width * 0.68), width - card_x - left_x)
    if slide_kind in {"comparison", "proscons"}:
        colors = ["#0f766e", "#1d4ed8", "#7c3aed"]
        for idx, bullet in enumerate(bullets[:3]):
            x = card_x
            card_y = y + idx * card_step
            if card_y + 72 > content_bottom:
                break
            draw.rounded_rectangle((x, card_y - 14, x + card_w, card_y + 72), radius=20, fill="#0b2338", outline=colors[idx % len(colors)], width=3)
            draw.text((x + 28, card_y + 4), trim_words(bullet, 4), fill="#ffffff", font=bullet_font)
        bullets = []
    for bullet in bullets[:3]:
        if y + 74 > content_bottom:
            break
        visible_bullet = trim_words(bullet, 4)
        draw.rounded_rectangle((card_x, y - 14, card_x + card_w, y + 74), radius=18, fill="#0b2338", outline="#155e75", width=2)
        draw.ellipse((card_x + 22, y + 16, card_x + 42, y + 36), fill="#14b8a6")
        draw_multiline(draw, visible_bullet, (card_x + 64, y - 2), card_w - 90, bullet_font, "#dbeafe", max_lines=1)
        y += card_step
    if slide_kind == "cta":
        draw.rounded_rectangle((54, int(height * 0.58), int(width * 0.76), int(height * 0.74)), radius=18, fill="#14b8a6")
        draw.text((84, int(height * 0.60)), "Watch more AI tool reviews:", fill="#042f2e", font=font(34 if width > 1200 else 30, bold=True))
        draw.text((84, int(height * 0.65)), YOUTUBE_CHANNEL_URL, fill="#042f2e", font=font(30 if width > 1200 else 26, bold=True))
    watermark = load_video_render_config().get("watermark", "smileaireviewhub.com")
    watermark_font = font(20 if width >= 1200 else 18)
    bbox = draw.textbbox((0, 0), watermark, font=watermark_font)
    draw.text((width - (bbox[2] - bbox[0]) - 42, height - 50), watermark, fill="#93c5fd", font=watermark_font)
    bar_w = int((width - 108) * max(0.0, min(1.0, progress)))
    draw.rectangle((54, height - 18, width - 54, height - 10), fill="#1e293b")
    draw.rectangle((54, height - 18, 54 + bar_w, height - 10), fill="#14b8a6")
    image.save(path)


def draw_branded_visual(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1 + 22, y1 + 22, x2 - 22, y2 - 22), radius=28, fill="#102a43", outline="#14b8a6", width=3)
    draw.text((x1 + 58, y1 + 64), "MS Smile AI Review Hub", fill="#ffffff", font=font(34, bold=True))
    draw.text((x1 + 58, y1 + 126), trim_words(title, 8), fill="#5eead4", font=font(52, bold=True))
    draw.text((x1 + 58, y2 - 104), "Research-style AI tool review", fill="#dbeafe", font=font(28))


def ffmpeg_escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:")


def file_has_text(path: Path) -> bool:
    return path.exists() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def validate_subtitle_inputs(article_dir: Path) -> tuple[bool, str]:
    english = article_dir / "subtitles.srt"
    vietnamese = article_dir / "subtitles_vi.txt"
    missing = []
    if not file_has_text(english):
        missing.append("English subtitles.srt is missing or empty")
    if not file_has_text(vietnamese):
        missing.append("Vietnamese subtitles_vi.txt is missing or empty")
    if missing:
        return False, "; ".join(missing)
    return True, "OK"


def quality_row(article_dir: Path) -> dict[str, str]:
    video_path = article_dir / "review_video.mp4"
    audio_path = article_dir / "audio" / "voiceover.mp3"
    english_path = article_dir / "subtitles.srt"
    vietnamese_path = article_dir / "subtitles_vi.txt"
    thumbnail_path = article_dir / "thumbnail.png"
    checks = {
        "Video": video_path.exists() and video_path.stat().st_size >= MIN_VALID_MP4_BYTES,
        "Audio": audio_path.exists() and audio_path.stat().st_size > 10_000,
        "EnglishSub": file_has_text(english_path),
        "VietnameseSub": file_has_text(vietnamese_path),
        "Thumbnail": thumbnail_path.exists() and thumbnail_path.stat().st_size > 0,
    }
    status = "READY" if all(checks.values()) else "FAILED"
    if status == "READY" and not (article_dir / "exports" / "long_video_1920x1080.mp4").exists():
        status = "WARNING"
    return {
        "FolderName": article_dir.name,
        **{key: "YES" if value else "NO" for key, value in checks.items()},
        "Status": status,
    }


def subtitle_row(article_dir: Path) -> dict[str, str]:
    english_ok = file_has_text(article_dir / "subtitles.srt")
    vietnamese_ok = file_has_text(article_dir / "subtitles_vi.txt")
    if english_ok and vietnamese_ok:
        status = "OK"
    elif english_ok or vietnamese_ok:
        status = "WARNING"
    else:
        status = "FAILED"
    return {
        "FolderName": article_dir.name,
        "EnglishSubtitle": "YES" if english_ok else "NO",
        "VietnameseSubtitle": "YES" if vietnamese_ok else "NO",
        "Status": status,
    }


def write_video_quality_reports(article_dirs: Iterable[Path] | None = None) -> None:
    if article_dirs is None:
        article_dirs = [
            folder
            for folder in VIDEO_OUTPUT.iterdir()
            if folder.is_dir() and (folder / "metadata.json").exists()
        ]
    subtitle_fields = ["FolderName", "EnglishSubtitle", "VietnameseSubtitle", "Status"]
    render_fields = ["FolderName", "Video", "Audio", "EnglishSub", "VietnameseSub", "Thumbnail", "Status"]
    subtitle_rows = [subtitle_row(folder) for folder in sorted(article_dirs, key=lambda path: path.name.lower())]
    render_rows = [quality_row(folder) for folder in sorted(article_dirs, key=lambda path: path.name.lower())]
    with SUBTITLE_REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=subtitle_fields)
        writer.writeheader()
        writer.writerows(subtitle_rows)
    with RENDER_REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=render_fields)
        writer.writeheader()
        writer.writerows(render_rows)


def append_render_debug(entry: dict[str, object]) -> None:
    RENDER_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RENDER_DEBUG_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, indent=2) + "\n")


def run_ffmpeg_logged(slug: str, ffmpeg: str, ffprobe: str, command: list[str], output: Path, working_dir: Path, phase: str) -> dict[str, object]:
    result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(working_dir))
    output_exists = output.exists()
    output_size = output.stat().st_size if output_exists else 0
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "phase": phase,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "command": command,
        "working_directory": str(working_dir),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "return_code": result.returncode,
        "output_file": str(output),
        "output_exists": output_exists,
        "output_size": output_size,
    }
    append_render_debug(entry)
    return entry


def validate_mp4(path: Path) -> int:
    if not path.exists():
        raise RuntimeError(f"Output file was not created: {path}")
    size = path.stat().st_size
    if size < MIN_VALID_MP4_BYTES:
        raise RuntimeError(f"Output file is too small ({size} bytes): {path}")
    return size


def ffprobe_duration(ffprobe: str, path: Path) -> str:
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return clean_text(result.stdout)
    except Exception:
        pass
    return ""


def ffprobe_streams(ffprobe: str, path: Path) -> dict[str, bool]:
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        data = json.loads(result.stdout or "{}")
        streams = [stream.get("codec_type") for stream in data.get("streams", [])]
        return {"video": "video" in streams, "audio": "audio" in streams, "subtitle": "subtitle" in streams}
    except Exception:
        return {"video": False, "audio": False, "subtitle": False}


def estimate_voiceover_seconds(text: str) -> float:
    words = len(clean_text(text).split())
    return max(42.0, min(480.0, words / 3.05 + 8.0))


def generate_windows_tts_wav(text: str, wav_path: Path, config: dict) -> tuple[bool, str]:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    ps_script = wav_path.parent / "generate_tts.ps1"
    text_path = wav_path.parent / "voiceover_tts.txt"
    text_path.write_text(text, encoding="utf-8")
    voice = str(config.get("tts_voice", "") or "")
    ps_script.write_text(
        """
param([string]$TextPath, [string]$OutputPath, [string]$VoiceName)
Add-Type -AssemblyName System.Speech
$text = Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($VoiceName) {
  try { $synth.SelectVoice($VoiceName) } catch { }
}
$synth.Rate = 0
$synth.Volume = 100
$synth.SetOutputToWaveFile($OutputPath)
$synth.Speak($text)
$synth.Dispose()
""".strip(),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_script), str(text_path), str(wav_path), voice],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ok = result.returncode == 0 and wav_path.exists() and wav_path.stat().st_size > 10_000
    return ok, (result.stdout or "") + (result.stderr or "")


def convert_audio_to_mp3(ffmpeg: str, wav_path: Path, mp3_path: Path) -> tuple[bool, str]:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ok = result.returncode == 0 and mp3_path.exists() and mp3_path.stat().st_size > 10_000
    return ok, (result.stdout or "") + (result.stderr or "")


def generate_voiceover_audio(article_dir: Path, ffmpeg: str, config: dict) -> dict[str, str]:
    audio_dir = article_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    mp3_path = audio_dir / "voiceover.mp3"
    wav_path = audio_dir / "voiceover.wav"
    if not config.get("tts_enabled", True):
        return {"status": "tts_disabled", "mp3": "", "error": ""}
    voiceover = read_file(article_dir / "voiceover.txt")
    voiceover = trim_words(voiceover, 980)
    if not voiceover:
        return {"status": "missing_voiceover_text", "mp3": "", "error": "voiceover.txt is empty"}
    ok, tts_log = generate_windows_tts_wav(voiceover, wav_path, config)
    if not ok:
        return {"status": "audio_missing", "mp3": "", "error": tts_log[-1000:]}
    ok, ffmpeg_log = convert_audio_to_mp3(ffmpeg, wav_path, mp3_path)
    if not ok:
        return {"status": "audio_missing", "mp3": "", "error": ffmpeg_log[-1000:]}
    return {"status": "voiceover_generated", "mp3": str(mp3_path), "error": ""}


def generate_cue_aligned_voiceover_audio(
    article_dir: Path,
    ffmpeg: str,
    ffprobe: str,
    config: dict,
    pairs: list[tuple[str, str]],
) -> dict[str, object]:
    audio_dir = article_dir / "audio"
    cue_dir = audio_dir / "cues"
    cue_dir.mkdir(parents=True, exist_ok=True)
    wav_paths: list[Path] = []
    durations: list[float] = []
    for index, (english_cue, _) in enumerate(pairs, start=1):
        wav_path = cue_dir / f"cue-{index:03}.wav"
        ok, error = generate_windows_tts_wav(english_cue, wav_path, config)
        if not ok:
            return {"status": "audio_missing", "mp3": "", "durations": [], "error": error[-1000:]}
        duration = float(ffprobe_duration(ffprobe, wav_path) or "0")
        if duration <= 0:
            return {"status": "audio_missing", "mp3": "", "durations": [], "error": f"Invalid cue duration: {wav_path}"}
        wav_paths.append(wav_path)
        durations.append(duration)

    concat_file = cue_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in wav_paths) + "\n", encoding="utf-8")
    joined_wav = audio_dir / "voiceover_aligned.wav"
    join_result = subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "pcm_s16le", str(joined_wav)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if join_result.returncode != 0 or not joined_wav.exists():
        return {"status": "audio_missing", "mp3": "", "durations": [], "error": (join_result.stderr or join_result.stdout)[-1000:]}
    mp3_path = audio_dir / "voiceover.mp3"
    ok, error = convert_audio_to_mp3(ffmpeg, joined_wav, mp3_path)
    if not ok:
        return {"status": "audio_missing", "mp3": "", "durations": [], "error": error[-1000:]}
    return {"status": "voiceover_generated", "mp3": str(mp3_path), "durations": durations, "error": ""}


def generate_safe_background_music(ffmpeg: str, duration: str, output: Path, config: dict) -> dict[str, str]:
    provided = str(config.get("background_music_path", "") or "").strip()
    if provided:
        path = Path(provided)
        if path.exists():
            return {"status": "user_music_added", "path": str(path), "error": ""}
    output.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(30.0, float(duration or 60))
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=196:duration={seconds}:sample_rate=44100",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=294:duration={seconds}:sample_rate=44100",
        "-filter_complex",
        "[0:a]volume=0.035[a0];[1:a]volume=0.025[a1];[a0][a1]amix=inputs=2:duration=shortest[aout]",
        "-map",
        "[aout]",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "6",
        str(output),
    ]
    result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and output.exists() and output.stat().st_size > 10_000:
        return {"status": "generated_safe_music", "path": str(output), "error": ""}
    return {"status": "not_added", "path": "", "error": (result.stderr or result.stdout)[-500:]}


def mix_voice_with_music(ffmpeg: str, voice_mp3: Path, music_mp3: Path, output: Path) -> dict[str, str]:
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(voice_mp3),
        "-i",
        str(music_mp3),
        "-filter_complex",
        "[1:a]volume=0.12[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map",
        "[aout]",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(output),
    ]
    result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and output.exists() and output.stat().st_size > 10_000:
        return {"status": "mixed", "path": str(output), "error": ""}
    return {"status": "voice_only", "path": str(voice_mp3), "error": (result.stderr or result.stdout)[-500:]}


def mux_audio_into_video(slug: str, ffmpeg: str, ffprobe: str, video_path: Path, audio_path: Path, output_path: Path, subtitles: Path | None = None) -> dict[str, object]:
    tmp_output = output_path.with_suffix(".muxed.mp4")
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
    ]
    if subtitles and subtitles.exists():
        command += ["-i", str(subtitles)]
    command += [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
    ]
    if subtitles and subtitles.exists():
        command += ["-map", "2:0"]
    command += [
        "-c:v",
        "copy",
        "-c:a",
        "aac",
    ]
    if subtitles and subtitles.exists():
        command += ["-c:s", "mov_text"]
    command += [
        "-movflags",
        "+faststart",
        str(tmp_output),
    ]
    entry = run_ffmpeg_logged(slug, ffmpeg, ffprobe, command, tmp_output, ROOT, "mux_audio")
    if int(entry["return_code"]) != 0:
        raise RuntimeError(f"Audio mux failed: {entry['stderr']}")
    validate_mp4(tmp_output)
    shutil.move(str(tmp_output), str(output_path))
    entry["output_file"] = str(output_path)
    entry["output_size"] = output_path.stat().st_size
    entry["duration"] = ffprobe_duration(ffprobe, output_path)
    append_render_debug({**entry, "phase": "mux_audio_validated"})
    return entry


def render_concat_video(
    slug: str,
    ffmpeg: str,
    ffprobe: str,
    slides: list[tuple[Path, float]],
    output: Path,
    subtitles: Path | None,
    vietnamese_subtitles: Path | None,
    size: tuple[int, int],
    burn_subtitles: bool = True,
) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smileai_video_") as temp_dir:
        width, height = size
        segment_paths: list[Path] = []
        for index, (slide, duration) in enumerate(slides, start=1):
            frames = max(90, int(duration * 30))
            segment = Path(temp_dir) / f"segment-{index:03}.mp4"
            if index % 3 == 1:
                zoom_expr = "min(1.045,1+0.00005*on)"
                pan_x = "iw/2-(iw/zoom/2)"
                pan_y = "ih/2-(ih/zoom/2)"
            elif index % 3 == 2:
                zoom_expr = "max(1.0,1.045-0.00005*on)"
                pan_x = f"(iw-iw/zoom)*on/{frames}"
                pan_y = "ih/2-(ih/zoom/2)"
            else:
                zoom_expr = "min(1.035,1+0.00004*on)"
                pan_x = "iw/2-(iw/zoom/2)"
                pan_y = f"(ih-ih/zoom)*on/{frames}"
            fade_out_start = max(0.0, duration - 0.35)
            vf_segment = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}':d={frames}:s={width}x{height}:fps=30,"
                f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out_start:.2f}:d=0.35"
            )
            segment_command = [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                str(slide),
                "-frames:v",
                str(frames),
                "-vf",
                vf_segment,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                str(segment),
            ]
            seg_entry = run_ffmpeg_logged(slug, ffmpeg, ffprobe, segment_command, segment, ROOT, "render_zoompan_segment")
            if int(seg_entry["return_code"]) != 0:
                raise RuntimeError(f"Segment render failed: {seg_entry['stderr']}")
            if not segment.exists() or segment.stat().st_size < 10_000:
                raise RuntimeError(f"Segment output is too small ({segment.stat().st_size if segment.exists() else 0} bytes): {segment}")
            segment_paths.append(segment)
        concat_file = Path(temp_dir) / "concat.txt"
        concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in segment_paths) + "\n", encoding="utf-8")
        no_sub_output = Path(temp_dir) / "joined.mp4"
        concat_command = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(no_sub_output),
        ]
        concat_entry = run_ffmpeg_logged(slug, ffmpeg, ffprobe, concat_command, no_sub_output, ROOT, "concat_segments")
        if int(concat_entry["return_code"]) != 0:
            raise RuntimeError(f"Concat failed: {concat_entry['stderr']}")
        validate_mp4(no_sub_output)
        vf = "null"
        if burn_subtitles:
            if not (subtitles and file_has_text(subtitles)):
                raise RuntimeError("English subtitles.srt is required before rendering")
            if not (vietnamese_subtitles and file_has_text(vietnamese_subtitles)):
                raise RuntimeError("Vietnamese subtitles are required before rendering")
            english_font_size = 9 if width >= height else 13
            vietnamese_font_size = 10 if width >= height else 14
            # libass scales MarginV to the output frame. These values move English
            # about 100 rendered pixels higher while preserving an 80px+ visible gap.
            english_bottom_margin = 50 if width >= height else 70
            vietnamese_bottom_margin = 8 if width >= height else 18
            margin_lr = 16 if width >= height else 14
            vf = (
                f"subtitles='{ffmpeg_escape_filter_path(subtitles)}':"
                "force_style='"
                f"FontName=Arial,Fontsize={english_font_size},"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,"
                "Bold=1,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,"
                f"MarginV={english_bottom_margin},MarginL={margin_lr},MarginR={margin_lr}"
                "',"
                f"subtitles='{ffmpeg_escape_filter_path(vietnamese_subtitles)}':"
                "force_style='"
                f"FontName=Arial,Fontsize={vietnamese_font_size},"
                "PrimaryColour=&H0000FFFF,OutlineColour=&HDD000000,"
                "Bold=1,BorderStyle=1,Outline=1,Shadow=0,Alignment=2,"
                f"MarginV={vietnamese_bottom_margin},MarginL={margin_lr},MarginR={margin_lr}"
                "'"
            )
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(no_sub_output),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        if output.exists():
            output.unlink()
        entry = run_ffmpeg_logged(slug, ffmpeg, ffprobe, command, output, ROOT, "render_with_bilingual_subtitles" if burn_subtitles else "render")
        if int(entry["return_code"]) != 0:
            raise RuntimeError(f"FFmpeg failed with return code {entry['return_code']}: {entry['stderr']}")
        size_bytes = validate_mp4(output)
        entry["validated_size"] = size_bytes
        entry["duration"] = ffprobe_duration(ffprobe, output)
        append_render_debug({**entry, "phase": f"{entry['phase']}_validated"})
        return entry


def render_article_videos(
    article_dir: Path,
    article: Article,
    page: ExtractedPage,
    ffmpeg: str,
    ffprobe: str,
    config: dict,
    target_long_seconds: int = 300,
) -> dict[str, object]:
    metadata = load_json(article_dir / "metadata.json", {})
    metadata.pop("video_render_note", None)
    metadata.pop("video_render_error", None)
    metadata.pop("render_error", None)
    metadata["render_status"] = "started"
    metadata["ffmpeg_path"] = ffmpeg
    metadata["ffprobe_path"] = ffprobe
    (article_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    scenes = load_json(article_dir / "scenes.json", [])
    script = read_file(article_dir / "voiceover.txt") or read_file(article_dir / "script.txt")
    script = ensure_end_screen_voiceover(article_dir, script)
    status: dict[str, object] = {
        "long_video": False,
        "shorts": 0,
        "status": "failed",
        "error": "",
        "long_size": 0,
        "duration": "",
        "audio_status": "not_started",
        "commands": [],
    }
    render_dir = article_dir / "render_assets"
    exports_dir = article_dir / "exports"
    shorts_exports_dir = exports_dir / "shorts"
    render_dir.mkdir(exist_ok=True)
    exports_dir.mkdir(exist_ok=True)
    shorts_exports_dir.mkdir(exist_ok=True)
    try:
        audio_info: dict[str, object] = {"status": "not_started", "mp3": "", "durations": [], "error": ""}
        voice_mp3_path: Path | None = None
        voice_duration = 0.0
        cue_pairs = paired_voiceover_cues(script)
        cue_pairs = translate_paired_cues_with_google(cue_pairs, article_dir / "subtitle_translation_cache.json")
        if config.get("render_long_video", True):
            audio_info = generate_cue_aligned_voiceover_audio(article_dir, ffmpeg, ffprobe, config, cue_pairs)
            status["audio_status"] = audio_info["status"]
            if audio_info["status"] == "voiceover_generated":
                voice_mp3_path = Path(str(audio_info["mp3"]))
                try:
                    voice_duration = float(ffprobe_duration(ffprobe, voice_mp3_path) or "0")
                except ValueError:
                    voice_duration = 0.0
            elif audio_info.get("error"):
                metadata["audio_error"] = audio_info.get("error", "")
        subtitle_target_seconds = voice_duration or estimate_voiceover_seconds(script)
        cue_durations = [float(value) for value in audio_info.get("durations", [])]
        if cue_durations:
            english_srt, vietnamese_srt_text, subtitle_source = build_paired_srts_from_durations(cue_pairs, cue_durations)
        else:
            english_srt, vietnamese_srt_text, subtitle_source = build_paired_bilingual_srts(script, subtitle_target_seconds)
        (article_dir / "subtitles.srt").write_text(english_srt, encoding="utf-8")
        (article_dir / "subtitles_vi.txt").write_text(subtitle_source, encoding="utf-8")
        vietnamese_srt = article_dir / "subtitles_vi.srt"
        vietnamese_srt.write_text(vietnamese_srt_text, encoding="utf-8")
        subtitle_ok, subtitle_message = validate_subtitle_inputs(article_dir)
        if not subtitle_ok:
            raise RuntimeError(subtitle_message)
        metadata["subtitle_duration_seconds"] = f"{subtitle_target_seconds:.3f}"
        visual_assets = collect_visual_assets(article_dir)
        if not visual_assets:
            visual_assets = [article_dir / "thumbnail.png"]
        if not isinstance(scenes, list) or not scenes:
            scenes = [{"time": "0-300", "type": "intro", "title": metadata.get("title", article_dir.name)}]
        aligned_scenes = build_audio_aligned_scenes(cue_pairs, cue_durations)
        render_scenes = aligned_scenes or scenes
        contextual_visuals = build_contextual_scene_visuals(article_dir, article, page, render_scenes, visual_assets)
        metadata["screenshots_used"] = [str(path) for path in visual_assets if path.exists()]
        metadata["scene_visuals"] = [
            {
                "scene": clean_text(scene.get("type", "")),
                "title": clean_text(scene.get("title", "")),
                "visual": str(contextual_visuals[index]),
                "duration": f"{float(scene.get('duration', 0.0)):.3f}" if scene.get("duration") else "",
            }
            for index, scene in enumerate(render_scenes)
        ]
        metadata["unique_scene_visuals"] = len({str(path.resolve()) for path in contextual_visuals if path.exists()})
        metadata["visual_timeline_source"] = "audio_cues" if aligned_scenes else "estimated_sections"
        estimated_total = voice_duration or estimate_voiceover_seconds(script)
        research_seconds = 9.0
        end_screen_seconds = 8.0
        terminal_seconds = research_seconds + end_screen_seconds
        content_seconds = max(35.0, estimated_total - terminal_seconds)
        section_seconds = max(3.0, (content_seconds - 5.0) / max(1, len(scenes)))
        slides: list[tuple[Path, float]] = []
        for index, scene in enumerate(render_scenes, start=1):
            title = short_slide_title(clean_text(scene.get("title") or metadata.get("title") or article_dir.name), clean_text(scene.get("type", "Review")))
            narration = clean_text(str(scene.get("narration", "")))
            bullets = [
                trim_words(item, 12)
                for item in re.split(r"(?<=[.!?])\s+", narration)
                if len(clean_text(item)) >= 28
            ][:3] or bullet_lines_from_script(script, title)
            slide_path = render_dir / f"slide-{index:02}.png"
            visual = contextual_visuals[index - 1] if index - 1 < len(contextual_visuals) else None
            scene_type = clean_text(scene.get("type", "")).lower()
            if scene_type == "end-screen":
                create_end_screen_slide(slide_path)
                slides.append((slide_path, float(scene.get("duration", end_screen_seconds))))
                continue
            if scene_type == "author":
                create_author_slide(slide_path)
                slides.append((slide_path, float(scene.get("duration", section_seconds))))
                continue
            if "pros" in scene_type or "cons" in scene_type:
                slide_kind = "proscons"
            elif "pricing" in scene_type or "alternative" in scene_type or "feature" in scene_type:
                slide_kind = "comparison"
            elif "verdict" in scene_type:
                slide_kind = "verdict"
            elif scene_type == "intro":
                slide_kind = "title"
            else:
                slide_kind = "section"
            create_video_slide(slide_path, title, bullets, (1920, 1080), clean_text(scene.get("type", "")), index / max(1, len(render_scenes)), slide_kind, visual)
            slides.append((slide_path, float(scene.get("duration", section_seconds))))
        metadata["research_summary_added"] = False if aligned_scenes else True
        metadata["end_screen_added"] = any(clean_text(str(scene.get("type", ""))) == "end-screen" for scene in render_scenes)
        metadata["author_name"] = site_profile()["author_name"]
        long_output = exports_dir / "long_video_1920x1080.mp4"
        if config.get("render_long_video", True):
            if config.get("tts_enabled", True) and audio_info["status"] != "voiceover_generated":
                raise RuntimeError(f"Audio is required before export: {audio_info.get('error') or audio_info['status']}")
            if not (article_dir / "thumbnail.png").exists():
                raise RuntimeError("Thumbnail is required before export")
            long_entry = render_concat_video(
                article_dir.name,
                ffmpeg,
                ffprobe,
                slides,
                long_output,
                article_dir / "subtitles.srt",
                vietnamese_srt,
                (1920, 1080),
                bool(config.get("burn_subtitles", True)),
            )
            if audio_info["status"] == "voiceover_generated" and voice_mp3_path:
                voice_mp3 = voice_mp3_path
                music_info = generate_safe_background_music(ffmpeg, ffprobe_duration(ffprobe, voice_mp3), article_dir / "audio" / "background_music.mp3", config)
                metadata["music_status"] = music_info["status"]
                final_audio = voice_mp3
                if music_info["status"] in {"generated_safe_music", "user_music_added"}:
                    mixed = article_dir / "audio" / "voiceover_with_music.mp3"
                    mix_info = mix_voice_with_music(ffmpeg, voice_mp3, Path(music_info["path"]), mixed)
                    final_audio = Path(mix_info["path"])
                    metadata["music_mix_status"] = mix_info["status"]
                mux_entry = mux_audio_into_video(article_dir.name, ffmpeg, ffprobe, long_output, final_audio, long_output, article_dir / "subtitles.srt")
                status["commands"].append(mux_entry.get("command", []))
            else:
                metadata["audio_error"] = audio_info.get("error", "")
            shutil.copy2(long_output, article_dir / "review_video.mp4")
            shutil.copy2(article_dir / "subtitles.srt", exports_dir / "subtitles.srt")
            shutil.copy2(vietnamese_srt, exports_dir / "subtitles_vi.srt")
            status["commands"].append(long_entry.get("command", []))
            status["long_size"] = long_output.stat().st_size
            status["duration"] = long_entry.get("duration", "")
        status["long_video"] = long_output.exists() and long_output.stat().st_size >= MIN_VALID_MP4_BYTES

        if config.get("render_shorts", True):
            for index in range(1, 4):
                short_dir = article_dir / "shorts" / f"short-{index}"
                if not short_dir.exists():
                    continue
                short_meta = load_json(short_dir / "metadata.json", {})
                short_script = read_file(short_dir / "script.txt")
                short_title = clean_text(short_meta.get("title") or f"{article_dir.name} short {index}")
                short_bullets = [trim_words(short_script, 18), "Verify current details before publishing."]
                short_slide = short_dir / "short-slide.png"
                short_output = shorts_exports_dir / f"short_{index}_1080x1920.mp4"
                create_video_slide(short_slide, short_title, short_bullets, (1080, 1920), "short", 1.0, "section")
                short_vi_text = read_file(short_dir / "subtitles_vi.txt") or read_file(short_dir / "subtitles.srt")
                if not clean_text(short_vi_text):
                    raise RuntimeError(f"Vietnamese subtitles missing for short {index}")
                short_vi_srt = short_dir / "subtitles_vi.srt"
                short_vi_srt.write_text(build_srt_to_duration(short_vi_text, 45.0, max_chars=30), encoding="utf-8")
                short_entry = render_concat_video(
                    article_dir.name,
                    ffmpeg,
                    ffprobe,
                    [(short_slide, 45.0)],
                    short_output,
                    short_dir / "subtitles.srt",
                    short_vi_srt,
                    (1080, 1920),
                    bool(config.get("burn_subtitles", True)),
                )
                shutil.copy2(short_output, short_dir / "short.mp4")
                shutil.copy2(short_dir / "subtitles.srt", shorts_exports_dir / f"short_{index}.srt")
                status["commands"].append(short_entry.get("command", []))
                if short_output.exists() and short_output.stat().st_size >= MIN_VALID_MP4_BYTES:
                    status["shorts"] = int(status["shorts"]) + 1
        if not status["long_video"]:
            raise RuntimeError(f"Long video did not pass validation: {long_output}")
        streams = ffprobe_streams(ffprobe, long_output)
        if not streams["video"]:
            raise RuntimeError("Rendered MP4 has no video stream")
        if config.get("tts_enabled", True) and not streams["audio"]:
            raise RuntimeError("Rendered MP4 has no audio stream")
        if config.get("render_shorts", True) and int(status["shorts"]) < 3:
            raise RuntimeError(f"Only {status['shorts']} shorts passed validation")
        status["status"] = "success"
        metadata["render_status"] = "success"
        metadata["video_render_status"] = "enhanced_youtube_review"
        metadata["audio_status"] = status["audio_status"]
        metadata["video_style"] = "enhanced_youtube_review"
        metadata["motion_style"] = "stable_full_frame_max_zoom_1_03"
        metadata["voiceover_language"] = "en"
        metadata["subtitle_language"] = "en+vi"
        metadata["youtube_channel_url"] = YOUTUBE_CHANNEL_URL
        metadata["music_status"] = metadata.get("music_status", "not_added")
        metadata["video_render_note"] = "Playable MP4 generated with branded slides, burned subtitles when available, and voiceover audio when TTS succeeds."
        metadata["review_video_size_bytes"] = status["long_size"]
        metadata["review_video_duration_seconds"] = ffprobe_duration(ffprobe, long_output)
        metadata["render_date"] = datetime.now(timezone.utc).isoformat()
        status["duration"] = metadata["review_video_duration_seconds"]
        metadata["streams"] = ffprobe_streams(ffprobe, long_output)
        metadata["subtitle_status"] = "bilingual_burned"
        metadata["youtube_upload"] = "disabled"
        profile = site_profile()
        metadata["author"] = {
            "name": profile["author_name"],
            "bio": profile["author_bio"],
            "website": profile["website"],
            "facebook": profile["facebook"],
            "youtube": profile["youtube"],
            "x": profile["x"],
            "linkedin": profile["linkedin"],
            "quora": profile["quora"],
        }
        description = clean_text(str(metadata.get("description", "")))
        if "Research Summary included in this local render package." not in description:
            description = (
                description
                + "\n\nResearch Summary included in this local render package."
                + "\n\nWatch more AI tool reviews:\nhttps://youtube.com/@SmileAIReviewHub"
                + "\n\nWebsite:\nhttps://smileaireviewhub.com"
            ).strip()
        metadata["description"] = description
        thumb_text_path = article_dir / "thumbnail_text.txt"
        thumb_text = read_file(thumb_text_path)
        if "youtube.com/@SmileAIReviewHub" not in thumb_text:
            thumb_text_path.write_text((thumb_text.rstrip() + "\nyoutube.com/@SmileAIReviewHub\n").lstrip(), encoding="utf-8")
        (article_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        status["error"] = str(exc)
        metadata["render_status"] = "failed"
        metadata["video_render_status"] = "failed"
        metadata["video_render_error"] = str(exc)
        metadata["video_render_note"] = f"Render failed: {exc}"
        (article_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def build_metadata(article: Article, page: ExtractedPage, thumb_text: str) -> dict:
    title = youtube_title(article, page)
    tag_seed = [word for word in re.split(r"[^A-Za-z0-9]+", thumb_text) if len(word) > 2]
    tags = dedupe(tag_seed + ["AI Tools", "AI Review", "MS Smile AI Review Hub", article.page_type.title()])
    return {
        "title": title,
        "description": (
            f"Read the full review:\n\n{article.url}\n\n"
            "MS Smile AI Review Hub publishes research-style reviews, comparisons and pricing guides.\n\n"
            "Always verify current pricing and features on official vendor websites.\n\n"
            "Watch more AI tool reviews:\n"
            f"{YOUTUBE_CHANNEL_URL}\n\n"
            "Full review and affiliate links:\n"
            f"{BASE_URL}\n\n"
            "This local video package is generated for manual review before publishing."
        ),
        "tags": tags[:15],
        "category": "Science & Technology",
        "source_url": article.url,
        "youtube_channel_url": YOUTUBE_CHANNEL_URL,
        "content_type": article.page_type,
        "publish_status": "manual_review_required",
        "youtube_upload": "disabled",
    }


def youtube_title(article: Article, page: ExtractedPage) -> str:
    thumb = thumbnail_text(article, page)
    if article.page_type == "comparison":
        return f"{thumb}: Features, Pricing and Best Use Cases"
    if article.page_type == "pricing":
        return f"{thumb}: Plans, Risks and What To Verify"
    if article.page_type == "category":
        return f"{thumb}: Tools, Pricing Checks and Buyer Tips"
    return f"{thumb}: Features, Pricing and Alternatives"


def build_shorts(article: Article, page: ExtractedPage) -> list[dict[str, str]]:
    topics = [
        ("pros", "Pros"),
        ("cons", "Cons"),
        ("quick-verdict", "Quick Verdict"),
    ]
    shorts = []
    for key, label in topics:
        source = section_source(article, page, label)
        text = (
            f"{label}: {trim_words(' '.join(source), 45)} "
            "Use this as a research starting point and verify current details on the official website."
        )
        shorts.append(
            {
                "id": key,
                "title": f"{thumbnail_text(article, page)} - {label}",
                "duration_target": "20-60 seconds",
                "script": clean_text(text),
            }
        )
    return shorts


def copy_or_create_root_file(root_subdir: str, slug: str, source: Path) -> None:
    destination = VIDEO_OUTPUT / root_subdir / f"{slug}{source.suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def ffmpeg_available() -> bool:
    return bool(detect_ffmpeg()["available"])


def create_video_placeholder(path: Path, metadata: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal non-uploadable marker. The manifest records that final rendering is pending.
    if not path.exists():
        path.write_bytes(b"")
    metadata["video_render_status"] = "assets_generated"
    metadata["video_render_note"] = "Text, subtitles, thumbnails, scenes and metadata generated. Run with --render to create playable MP4 files."
    return "assets_generated"


def package_video_valid(article_dir: Path) -> bool:
    mp4_path = article_dir / "review_video.mp4"
    export_path = article_dir / "exports" / "long_video_1920x1080.mp4"
    metadata = load_json(article_dir / "metadata.json", {})
    return (
        metadata.get("render_status") == "success"
        and mp4_path.exists()
        and mp4_path.stat().st_size >= MIN_VALID_MP4_BYTES
        and export_path.exists()
        and export_path.stat().st_size >= MIN_VALID_MP4_BYTES
        and file_has_text(article_dir / "subtitles.srt")
        and file_has_text(article_dir / "subtitles_vi.txt")
        and (article_dir / "thumbnail.png").exists()
    )


def existing_package_row(article: Article, ffmpeg_info: dict[str, str | bool] | None = None) -> dict:
    article_dir = VIDEO_OUTPUT / article.slug
    metadata = load_json(article_dir / "metadata.json", {})
    mp4_path = article_dir / "review_video.mp4"
    export_path = article_dir / "exports" / "long_video_1920x1080.mp4"
    duration = str(metadata.get("review_video_duration_seconds", ""))
    render_date = str(metadata.get("render_date") or metadata.get("research_summary_date") or "")
    if not render_date and mp4_path.exists():
        render_date = datetime.fromtimestamp(mp4_path.stat().st_mtime, timezone.utc).isoformat()
    return {
        "slug": article.slug,
        "title": str(metadata.get("title") or article.title),
        "type": article.page_type,
        "url": article.url,
        "folder": article_dir.as_posix(),
        "thumbnail": (article_dir / "thumbnail.png").as_posix(),
        "status": "skipped_completed",
        "ffmpeg_status": "ready" if (ffmpeg_info or {}).get("available") else "missing",
        "long_video": "yes" if package_video_valid(article_dir) else "no",
        "short_1": "yes" if (article_dir / "exports" / "shorts" / "short_1_1080x1920.mp4").exists() else "no",
        "short_2": "yes" if (article_dir / "exports" / "shorts" / "short_2_1080x1920.mp4").exists() else "no",
        "short_3": "yes" if (article_dir / "exports" / "shorts" / "short_3_1080x1920.mp4").exists() else "no",
        "render_error": "",
        "long_video_size": str(export_path.stat().st_size if export_path.exists() else mp4_path.stat().st_size if mp4_path.exists() else ""),
        "duration": duration,
        "generated_at": render_date,
    }


def write_article_package(
    article: Article,
    render: bool = False,
    ffmpeg_info: dict[str, str | bool] | None = None,
    render_config: dict | None = None,
) -> dict:
    page = extract_page(article.output_path)
    article_title = page.title or article.title
    article_dir = VIDEO_OUTPUT / article.slug
    article_dir.mkdir(parents=True, exist_ok=True)

    script = build_script(article, page)
    voiceover = build_youtube_voiceover(article, page)
    subtitle_source = build_vietnamese_subtitles(article, page)
    subtitles = build_srt(voiceover, max_chars=42)
    scenes = build_scenes(article, voiceover)
    thumb_text = thumbnail_text(article, page)
    metadata = build_metadata(article, page, thumb_text)
    config = dict(render_config or load_video_render_config())
    shorts = build_shorts(article, page)

    cta_text = (
        "\n\nWatch more AI tool reviews:\n"
        f"{YOUTUBE_CHANNEL_URL}\n\n"
        "Full review and affiliate links:\n"
        f"{BASE_URL}\n"
    )
    (article_dir / "script.txt").write_text(script + cta_text, encoding="utf-8")
    (article_dir / "voiceover.txt").write_text(voiceover, encoding="utf-8")
    (article_dir / "subtitles_vi.txt").write_text(subtitle_source, encoding="utf-8")
    (article_dir / "subtitles.srt").write_text(subtitles, encoding="utf-8")
    (article_dir / "thumbnail_text.txt").write_text(thumb_text + "\n" + YOUTUBE_CHANNEL_URL + "\n", encoding="utf-8")
    (article_dir / "scenes.json").write_text(json.dumps(scenes, indent=2, ensure_ascii=False), encoding="utf-8")
    (article_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    thumbnail_path = article_dir / "thumbnail.png"
    create_thumbnail(thumbnail_path, thumb_text, article.page_type)

    shorts_dir = article_dir / "shorts"
    shorts_dir.mkdir(exist_ok=True)
    for index, short in enumerate(shorts, start=1):
        short_dir = shorts_dir / f"short-{index}"
        short_dir.mkdir(exist_ok=True)
        short_script = short["script"] + "\n"
        (short_dir / "script.txt").write_text(short_script, encoding="utf-8")
        (short_dir / "voiceover.txt").write_text(short_script, encoding="utf-8")
        (short_dir / "subtitles.srt").write_text(
            build_srt(short_script, max_chars=36),
            encoding="utf-8",
        )
        (short_dir / "subtitles_vi.txt").write_text(
            "Tóm tắt nhanh. Hãy kiểm tra giá, tính năng và lựa chọn thay thế trước khi quyết định.\n",
            encoding="utf-8",
        )
        (short_dir / "metadata.json").write_text(json.dumps(short, indent=2, ensure_ascii=False), encoding="utf-8")

    video_status = create_video_placeholder(article_dir / "review_video.mp4", metadata)
    (article_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    render_result: dict[str, object] = {"long_video": False, "shorts": 0, "status": video_status, "error": ""}
    if render:
        ffmpeg_info = ffmpeg_info or detect_ffmpeg()
        if ffmpeg_info.get("available"):
            render_result = render_article_videos(
                article_dir,
                article,
                page,
                str(ffmpeg_info["ffmpeg"]),
                str(ffmpeg_info["ffprobe"]),
                config,
            )
            video_status = str(render_result.get("status") or video_status)
            if render_result.get("status") == "success":
                update_render_status_tracker()
        else:
            video_status = "ffmpeg_missing"
            metadata = load_json(article_dir / "metadata.json", metadata)
            metadata["video_render_status"] = "ffmpeg_missing"
            metadata["video_render_note"] = "FFmpeg not found. Close and reopen PowerShell/VS Code, then run again."
            (article_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            render_result = {"long_video": False, "shorts": 0, "status": video_status, "error": "FFmpeg not found. Close and reopen PowerShell/VS Code, then run again."}

    copy_or_create_root_file("scripts", article.slug, article_dir / "script.txt")
    copy_or_create_root_file("voiceovers", article.slug, article_dir / "voiceover.txt")
    copy_or_create_root_file("subtitles", article.slug, article_dir / "subtitles.srt")
    copy_or_create_root_file("thumbnails", article.slug, thumbnail_path)
    copy_or_create_root_file("videos", article.slug, article_dir / "review_video.mp4")
    copy_or_create_root_file("manifests", article.slug, article_dir / "metadata.json")

    return {
        "slug": article.slug,
        "title": article_title,
        "type": article.page_type,
        "url": article.url,
        "folder": article_dir.as_posix(),
        "thumbnail": (article_dir / "thumbnail.png").as_posix(),
        "status": video_status,
        "ffmpeg_status": "ready" if (ffmpeg_info or {}).get("available") else "missing",
        "long_video": "yes" if (article_dir / "exports" / "long_video_1920x1080.mp4").exists() and (article_dir / "exports" / "long_video_1920x1080.mp4").stat().st_size > 0 else "no",
        "short_1": "yes" if (article_dir / "exports" / "shorts" / "short_1_1080x1920.mp4").exists() and (article_dir / "exports" / "shorts" / "short_1_1080x1920.mp4").stat().st_size > 0 else "no",
        "short_2": "yes" if (article_dir / "exports" / "shorts" / "short_2_1080x1920.mp4").exists() and (article_dir / "exports" / "shorts" / "short_2_1080x1920.mp4").stat().st_size > 0 else "no",
        "short_3": "yes" if (article_dir / "exports" / "shorts" / "short_3_1080x1920.mp4").exists() and (article_dir / "exports" / "shorts" / "short_3_1080x1920.mp4").stat().st_size > 0 else "no",
        "render_error": str(render_result.get("error", "")),
        "long_video_size": str(render_result.get("long_size", "")),
        "duration": str(render_result.get("duration", "")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def create_dashboard(manifest_rows: list[dict]) -> None:
    rows = []
    for item in manifest_rows:
        slug = html.escape(item["slug"])
        title = html.escape(item["title"])
        status = html.escape(item["status"])
        ffmpeg_status = html.escape(str(item.get("ffmpeg_status", "unknown")))
        generated = html.escape(item["generated_at"])
        long_label = "Long Video" if item.get("long_video") == "yes" else "Long Video Pending"
        short_1_label = "Short 1" if item.get("short_1") == "yes" else "Short 1 Pending"
        short_2_label = "Short 2" if item.get("short_2") == "yes" else "Short 2 Pending"
        short_3_label = "Short 3" if item.get("short_3") == "yes" else "Short 3 Pending"
        rows.append(
            f"""
            <article class="card">
              <img src="{slug}/thumbnail.png" alt="{title} thumbnail">
              <div>
                <p class="type">{html.escape(item["type"])}</p>
                <h2>{title}</h2>
                <p>Render status: <strong>{status}</strong> | FFmpeg: <strong>{ffmpeg_status}</strong></p>
                <p>Generated: {generated}</p>
                <p class="buttons">
                  <a href="{slug}/script.txt">Open Script</a>
                  <a href="{slug}/subtitles.srt">Open Subtitle</a>
                  <a href="{slug}/metadata.json">Open Metadata</a>
                  <a href="{slug}/exports/">Open Export Folder</a>
                  <a href="{slug}/exports/long_video_1920x1080.mp4">{long_label}</a>
                  <a href="{slug}/exports/shorts/short_1_1080x1920.mp4">{short_1_label}</a>
                  <a href="{slug}/exports/shorts/short_2_1080x1920.mp4">{short_2_label}</a>
                  <a href="{slug}/exports/shorts/short_3_1080x1920.mp4">{short_3_label}</a>
                  <a href="{slug}/">Open Video Folder</a>
                </p>
              </div>
            </article>
            """
        )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MS Smile AI Review Hub Video Pipeline</title>
  <style>
    body{{font-family:Arial,Helvetica,sans-serif;background:#f7f9fc;color:#17202a;margin:0;line-height:1.5}}
    .wrap{{max-width:1180px;margin:0 auto;padding:28px 18px}}
    h1{{margin:0 0 8px;font-size:34px}}
    .note{{color:#64748b;margin-bottom:20px}}
    .grid{{display:grid;gap:14px}}
    .card{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:16px;background:#fff;border:1px solid #dbe3ef;border-radius:8px;padding:14px}}
    .card img{{width:220px;aspect-ratio:16/9;object-fit:cover;border-radius:6px;border:1px solid #dbe3ef}}
    .type{{text-transform:uppercase;color:#0f766e;font-weight:800;font-size:12px;margin:0}}
    h2{{font-size:20px;margin:4px 0 8px}}
    .buttons{{display:flex;gap:8px;flex-wrap:wrap}}
    a{{color:#0f766e;font-weight:800;text-decoration:none}}
    .buttons a{{border:1px solid #bfdbfe;border-radius:6px;padding:7px 9px;background:#f8fbff}}
    @media(max-width:700px){{.card{{grid-template-columns:1fr}}.card img{{width:100%}}}}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>MS Smile AI Review Hub Video Pipeline</h1>
    <p class="note">Local video assets only. No YouTube API calls, no uploads, and no publishing are performed.</p>
    <section class="grid">
      {''.join(rows)}
    </section>
  </main>
</body>
</html>
"""
    (VIDEO_OUTPUT / "index.html").write_text(html_text, encoding="utf-8")


def write_review_processing_report(manifest_rows: list[dict]) -> Path:
    report_path = VIDEO_OUTPUT / "logs" / "review_render_report.csv"
    text_report_path = VIDEO_OUTPUT / "logs" / "review_render_report.txt"
    fields = ["Folder Name", "Status", "Video Generated", "Duration", "Render Date"]
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(
                {
                    "Folder Name": row.get("slug", ""),
                    "Status": row.get("status", ""),
                    "Video Generated": row.get("long_video", ""),
                    "Duration": row.get("duration", ""),
                    "Render Date": row.get("generated_at", ""),
                }
            )
    lines = [
        "MS Smile AI Review Hub Review Video Processing Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Folder Name | Status | Video Generated | Duration | Render Date",
        "--- | --- | --- | --- | ---",
    ]
    for row in manifest_rows:
        lines.append(
            f"{row.get('slug', '')} | {row.get('status', '')} | {row.get('long_video', '')} | {row.get('duration', '')} | {row.get('generated_at', '')}"
        )
    text_report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def update_render_status_tracker() -> None:
    script_path = ROOT / "scripts" / "update_render_status.py"
    if not script_path.exists():
        return
    subprocess.run([sys.executable, str(script_path)], cwd=ROOT, check=False)


def prepare_output() -> None:
    VIDEO_OUTPUT.mkdir(exist_ok=True)
    for name in ROOT_OUTPUT_DIRS:
        (VIDEO_OUTPUT / name).mkdir(exist_ok=True)
    (VIDEO_OUTPUT / "scripts" / "README.txt").write_text(
        "Run from repo root: python scripts/generate_video_assets.py\n"
        "This pipeline generates local review assets only. It does not upload or publish to YouTube.\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local video packages for MS Smile AI Review Hub.")
    parser.add_argument("--render", action="store_true", help="Render playable MP4 files locally when FFmpeg is available.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of packages generated/rendered for testing.")
    parser.add_argument("--slug", default="", help="Generate/render only one package slug, for example review-chatgpt.")
    parser.add_argument("--all", action="store_true", help="Render all discovered packages. Without --all, config default_render_limit is used for render runs.")
    parser.add_argument("--reviews-only", action="store_true", help="Process only review package folders, for example review-chatgpt.")
    parser.add_argument("--skip-shorts", action="store_true", help="Skip shorts rendering for long-video production batches.")
    parser.add_argument("--force", action="store_true", help="Rebuild packages even when a completed render already exists.")
    return parser.parse_args()


def select_articles(articles: list[Article], slug: str = "", limit: int = 0, reviews_only: bool = False) -> list[Article]:
    selected = articles
    if reviews_only:
        selected = [article for article in selected if article.slug.startswith("review-")]
    if slug:
        selected = [article for article in selected if article.slug == slug]
    if limit and limit > 0:
        selected = selected[:limit]
    return selected


def main() -> None:
    args = parse_args()
    prepare_output()
    config = load_video_render_config()
    if args.skip_shorts:
        config = dict(config)
        config["render_shorts"] = False
    ffmpeg_info = detect_ffmpeg()
    if args.render and not ffmpeg_info.get("available"):
        print("FFmpeg not found. Close and reopen PowerShell/VS Code, then run again.")
        print(f"ffmpeg detected: {bool(ffmpeg_info.get('ffmpeg'))} | ffprobe detected: {bool(ffmpeg_info.get('ffprobe'))}")
    elif args.render:
        print(f"FFmpeg detected: yes ({ffmpeg_info.get('ffmpeg')})")
        print(f"FFprobe detected: yes ({ffmpeg_info.get('ffprobe')})")
        if RENDER_DEBUG_LOG.exists():
            try:
                RENDER_DEBUG_LOG.unlink()
            except (PermissionError, FileNotFoundError):
                # Parallel batch workers may be writing or clearing the shared log.
                pass

    effective_limit = args.limit
    if args.render and not args.slug and not args.all and effective_limit <= 0:
        effective_limit = int(config.get("default_render_limit", 3) or 3)
    articles = select_articles(discover_articles(), args.slug, effective_limit, args.reviews_only)
    manifest_rows = []
    log_lines = [
        f"generated_at={datetime.now(timezone.utc).isoformat()}",
        f"article_count={len(articles)}",
        f"render={args.render}",
        f"reviews_only={args.reviews_only}",
        f"skip_shorts={args.skip_shorts}",
        f"force={args.force}",
        f"ffmpeg={ffmpeg_info.get('ffmpeg', '')}",
        f"ffprobe={ffmpeg_info.get('ffprobe', '')}",
        "youtube_upload=disabled",
    ]
    render_log_lines = [
        f"generated_at={datetime.now(timezone.utc).isoformat()}",
        f"render={args.render}",
        "youtube_upload=disabled",
    ]
    for article in articles:
        try:
            if args.render and not args.force and package_video_valid(VIDEO_OUTPUT / article.slug):
                row = existing_package_row(article, ffmpeg_info)
                manifest_rows.append(row)
                log_lines.append(f"SKIP {article.slug} completed")
                render_log_lines.append(
                    f"{article.slug} | video_generated={row.get('long_video')} | shorts_generated={row.get('short_1')},{row.get('short_2')},{row.get('short_3')} | status={row.get('status')} | size={row.get('long_video_size', '')} | duration={row.get('duration', '')} | error="
                )
                continue
            row = write_article_package(article, render=args.render, ffmpeg_info=ffmpeg_info, render_config=config)
            manifest_rows.append(row)
            log_lines.append(f"OK {article.slug} {row['status']}")
            render_log_lines.append(
                f"{article.slug} | video_generated={row.get('long_video')} | shorts_generated={row.get('short_1')},{row.get('short_2')},{row.get('short_3')} | status={row.get('status')} | size={row.get('long_video_size', '')} | duration={row.get('duration', '')} | error={row.get('render_error', '')}"
            )
        except Exception as exc:  # pragma: no cover - operational log path
            log_lines.append(f"ERROR {article.slug} {exc}")
            render_log_lines.append(f"{article.slug} | video_generated=no | shorts_generated=no,no,no | status=failed | error={exc}")
    create_dashboard(manifest_rows)
    (VIDEO_OUTPUT / "manifests" / "video_manifest.json").write_text(
        json.dumps(manifest_rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (VIDEO_OUTPUT / "logs" / "generate_video_assets.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    (VIDEO_OUTPUT / "logs" / "render_log.txt").write_text("\n".join(render_log_lines) + "\n", encoding="utf-8")
    report_path = write_review_processing_report(manifest_rows)
    write_video_quality_reports([VIDEO_OUTPUT / row["slug"] for row in manifest_rows if row.get("slug")])
    update_render_status_tracker()
    print(f"Generated video assets for {len(manifest_rows)} articles in {VIDEO_OUTPUT}")
    print(f"Processing report: {report_path}")
    print(f"Subtitle report: {SUBTITLE_REPORT_CSV}")
    print(f"Render report: {RENDER_REPORT_CSV}")
    if args.render:
        long_count = sum(1 for row in manifest_rows if row.get("long_video") == "yes")
        short_count = sum(1 for row in manifest_rows for key in ("short_1", "short_2", "short_3") if row.get(key) == "yes")
        failed = [row["slug"] for row in manifest_rows if row.get("status") == "failed"]
        print(f"Rendered long videos: {long_count}")
        print(f"Rendered shorts: {short_count}")
        if failed:
            print(f"Failed slugs: {', '.join(failed)}")
    elif not ffmpeg_available():
        print("FFmpeg not found. Close and reopen PowerShell/VS Code, then run again.")


if __name__ == "__main__":
    main()
