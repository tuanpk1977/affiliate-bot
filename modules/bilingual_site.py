from __future__ import annotations

import re
import shutil
import html as html_lib
import json
from pathlib import Path

from config import settings
from modules.indexing_policy import robots_meta_for_path
from modules.vietnamese_localizer import localize_html


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")


SKIP_PREFIXES = {"assets", "go", "vi", "__pycache__"}

FAQ_SCHEMA_DISABLED_URLS = {
    "/comparisons/framer-vs-webflow/",
    "/vi/comparisons/framer-vs-webflow/",
}


def add_bilingual_pages(output: Path | None = None, base_url: str | None = None) -> dict[str, int]:
    """Create static Vietnamese copies under /vi/ and add hreflang links.

    The source pages remain English at their normal routes. Vietnamese pages are
    generated from the same HTML and then passed through the localizer. This is
    intentionally local/static only; no translation widget or external service is
    used.
    """
    root = output or settings.site_output_dir
    base = (base_url or BASE_URL).rstrip("/")
    if not root.exists():
        return {"english_pages": 0, "vietnamese_pages": 0}

    remove_existing_vi(root)
    english_pages = list(iter_english_pages(root))
    for page in english_pages:
        rel_url = url_for_page(page, root)
        html = page.read_text(encoding="utf-8", errors="ignore")
        html = ensure_english_ui(html)
        html = ensure_robots_meta(html, robots_meta_for_path(rel_url))
        html = set_language_switcher(html, rel_url, "en")
        html = set_seo_language_tags(html, rel_url, "en", base)
        html = set_html_lang(html, "en")
        html = normalize_faq_schema_to_visible_faq(html, rel_url)
        page.write_text(html, encoding="utf-8")

        vi_page = root / "vi" / page.relative_to(root)
        vi_page.parent.mkdir(parents=True, exist_ok=True)
        vi_html = localize_html(html)
        vi_html = prefix_internal_links_for_vi(vi_html)
        vi_html = cleanup_vietnamese_after_link_prefix(vi_html)
        vi_html = ensure_robots_meta(vi_html, robots_meta_for_path(vi_url_for(rel_url)))
        vi_html = set_language_switcher(vi_html, rel_url, "vi")
        vi_html = set_seo_language_tags(vi_html, rel_url, "vi", base)
        vi_html = set_html_lang(vi_html, "vi")
        vi_html = normalize_faq_schema_to_visible_faq(vi_html, vi_url_for(rel_url))
        vi_page.write_text(vi_html, encoding="utf-8")

    return {"english_pages": len(english_pages), "vietnamese_pages": len(english_pages)}


def remove_existing_vi(root: Path) -> None:
    vi = root / "vi"
    if vi.exists():
        shutil.rmtree(vi)


def iter_english_pages(root: Path):
    for page in sorted(root.rglob("index.html")):
        rel = page.relative_to(root).parts
        if not rel:
            continue
        if rel[0] in SKIP_PREFIXES:
            continue
        yield page


def url_for_page(page: Path, root: Path) -> str:
    rel = page.relative_to(root)
    if rel.as_posix() == "index.html":
        return "/"
    return "/" + rel.parent.as_posix().strip("/") + "/"


def vi_url_for(en_url: str) -> str:
    return "/vi/" if en_url == "/" else "/vi" + en_url


def set_html_lang(html: str, lang: str) -> str:
    if re.search(r"<html\b[^>]*>", html, flags=re.I):
        return re.sub(r"<html\b[^>]*>", f'<html lang="{lang}">', html, count=1, flags=re.I)
    return html


def set_language_switcher(html: str, en_url: str, active: str) -> str:
    vi_url = vi_url_for(en_url)
    if active == "vi":
        switcher = (
            f"<div class='language-switcher' aria-label='Language switcher'>"
            f"<a href='{en_url}'>English</a><span>|</span>"
            f"<a class='active' href='{vi_url}'>Tiếng Việt</a></div>"
        )
    else:
        switcher = (
            f"<div class='language-switcher' aria-label='Language switcher'>"
            f"<a class='active' href='{en_url}'>English</a><span>|</span>"
            f"<a href='{vi_url}'>Tiếng Việt</a></div>"
        )
    if "language-switcher" in html:
        return re.sub(r"<div class=['\"]language-switcher['\"][^>]*>.*?</div>", switcher, html, count=1, flags=re.S)
    return html.replace("</div></div><div class='wrap'><p class='note'>", f"{switcher}</div></div><div class='wrap'><p class='note'>", 1)

def set_seo_language_tags(html: str, en_url: str, lang: str, base: str) -> str:
    vi_url = vi_url_for(en_url)
    canonical = base + (vi_url if lang == "vi" else en_url)
    en_href = base + en_url
    vi_href = base + vi_url
    html = re.sub(r"\s*<link rel=['\"]alternate['\"][^>]*hreflang=['\"][^'\"]+['\"][^>]*>\n?", "", html, flags=re.I)
    html = re.sub(r"<link rel=['\"]canonical['\"][^>]*>", f'<link rel="canonical" href="{canonical}">', html, count=1, flags=re.I)
    alternates = (
        f'  <link rel="alternate" hreflang="en" href="{en_href}">\n'
        f'  <link rel="alternate" hreflang="vi" href="{vi_href}">\n'
        f'  <link rel="alternate" hreflang="x-default" href="{en_href}">'
    )
    if "</head>" in html:
        html = html.replace("</head>", alternates + "\n</head>", 1)
    return html


def prefix_internal_links_for_vi(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        quote = match.group(1)
        href = match.group(2)
        if (
            not href.startswith("/")
            or href.startswith("/vi/")
            or href.startswith("/go/")
            or href.startswith("/assets/")
            or href.startswith("/downloads/")
            or href.startswith("//")
        ):
            return match.group(0)
        return f"href={quote}/vi{href}{quote}"

    return re.sub(r"href=(['\"])(/[^'\"]*)\1", repl, html)


def cleanup_vietnamese_after_link_prefix(html: str) -> str:
    """Clean phrases that only become matchable after /vi/ link prefixing."""
    replacements = {
        'Bạn cũng có thể so sánh <a href="/vi/comparisons/runway-vs-pika/">Runway vs Pika</a> and <a href="/vi/comparisons/synthesia-vs-heygen/">Synthesia vs HeyGen</a> before choosing a video quy trình.':
            'Bạn cũng có thể so sánh <a href="/vi/comparisons/runway-vs-pika/">Runway vs Pika</a> và <a href="/vi/comparisons/synthesia-vs-heygen/">So sánh Synthesia và HeyGen</a> trước khi chọn quy trình video.',
        '<a href="/vi/comparisons/synthesia-vs-heygen/">Synthesia vs HeyGen</a>':
            '<a href="/vi/comparisons/synthesia-vs-heygen/">So sánh Synthesia và HeyGen</a>',
        "<a href='/vi/comparisons/synthesia-vs-heygen/'>Synthesia vs HeyGen</a>":
            "<a href='/vi/comparisons/synthesia-vs-heygen/'>So sánh Synthesia và HeyGen</a>",
        "Which Công cụ AI videos should you choose?":
            "Nên chọn công cụ AI video nào?",
        "activechiến dịch":
            "activecampaign",
        "Activechiến dịch":
            "ActiveCampaign",
        "chatgpt-windsurf-codex-quy trình":
            "chatgpt-windsurf-codex-workflow",
        "windsurf-to-codex-quy trình":
            "windsurf-to-codex-workflow",
        "ai-tools-for-content-nhà sáng tạos":
            "ai-tools-for-content-creators",
    }
    for source, target in replacements.items():
        html = html.replace(source, target)
    return html


def ensure_robots_meta(html: str, value: str) -> str:
    tag = f'<meta name="robots" content="{value}">'
    if re.search(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])[^>]*>", html, flags=re.I):
        return re.sub(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])[^>]*>", tag, html, count=1, flags=re.I)
    if "</head>" in html:
        return html.replace("</head>", f"{tag}\n</head>", 1)
    return html


def ensure_english_ui(html: str) -> str:
    """Normalize common Vietnamese UI labels that may exist in older generated pages."""
    replacements = {
        "Trang chủ": "Home",
        "Đánh giá": "Reviews",
        "So sánh": "Comparisons",
        "Bảng giá": "Pricing",
        "Giá cả": "Pricing",
        "Giá": "Pricing",
        "Thể loại": "Categories",
        "Danh mục": "Categories",
        "Trung tâm": "Hubs",
        "Liên hệ": "Contact",
        "Nội dung": "Contents",
        "Tóm tắt": "Summary",
        "Ưu điểm": "Pros",
        "Nhược điểm": "Cons",
        "Hạn chế": "Limitations",
        "Kết luận": "Final Verdict",
        "Câu hỏi thường gặp": "FAQ",
        "Tổng quan": "Overview",
        "Tính năng": "Features",
        "Ai nên dùng?": "Who Should Use It",
        "Lựa chọn thay thế": "Alternatives",
        "Truy cập website chính thức": "Visit Official Website",
        "Kiểm tra giá hiện tại": "Verify Current Pricing",
        "Một số liên kết có thể là liên kết tiếp thị liên kết. Chúng tôi có thể nhận được hoa hồng mà không phát sinh thêm chi phí nào cho bạn.": "Some links may be affiliate links. We may earn a commission at no extra cost to you.",
        "Một số liên kết có thể là liên kết tiếp thị liên kết.": "Some links may be affiliate links.",
        "Chúng tôi có thể nhận được hoa hồng mà không phát sinh thêm chi phí nào cho bạn.": "We may earn a commission at no extra cost to you.",
        "Các bài đánh giá chỉ nhằm mục đích nghiên cứu.": "Reviews are for research purposes only.",
        "Tiết lộ liên kết": "Affiliate Disclosure",
        "Chính sách bảo mật": "Privacy Policy",
        "Điều khoản": "Terms",
        "Giới thiệu": "About",
        "nên chọn công cụ nào?": "which tool should you choose?",
        "Nên chọn công cụ nào?": "Which tool should you choose?",
        "phù hợp với ai?": "who is it for?",
        "Phù hợp với ai?": "Who is it for?",
        "Nên so sánh pricing như thế nào?": "How should you compare pricing?",
        "Trang này có affiliate link không?": "Does this page use affiliate links?",
    }
    for src, dst in replacements.items():
        html = html.replace(src, dst)
    html = html.replace("MS Smile AI Đánh giá Hub", "MS Smile AI Review Hub")
    html = html.replace("Trung tâm đánh giá MS Smile AI", "MS Smile AI Review Hub")
    return html


def normalize_faq_schema_to_visible_faq(html: str, url_path: str | None = None) -> str:
    """Keep one FAQPage JSON-LD block and align it with visible FAQ details."""
    if url_path in FAQ_SCHEMA_DISABLED_URLS:
        return remove_faqpage_jsonld(html)
    faq_items = extract_visible_faq_items(html)
    if not faq_items:
        return html
    html = remove_faqpage_jsonld(html)
    entities = [
        {
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {"@type": "Answer", "text": answer},
        }
        for question, answer in faq_items
        if question.strip() and answer.strip()
    ]
    if not entities:
        return html
    schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}
    script = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>'
    if "</head>" in html:
        return html.replace("</head>", f"  {script}\n</head>", 1)
    return script + "\n" + html


def extract_visible_faq_items(html: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for match in re.finditer(r"<details\b[^>]*>\s*<summary[^>]*>(.*?)</summary>(.*?)</details>", html, flags=re.I | re.S):
        question = clean_html_text(match.group(1))
        body = match.group(2)
        paragraph = re.search(r"<p[^>]*>(.*?)</p>", body, flags=re.I | re.S)
        answer = clean_html_text(paragraph.group(1) if paragraph else body)
        if question and answer:
            items.append((question, answer))
    return items


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def remove_faqpage_jsonld(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        content = match.group(1)
        try:
            payload = json.loads(content)
        except Exception:
            return match.group(0)
        payloads = payload if isinstance(payload, list) else [payload]
        if any(contains_faqpage_schema(item) for item in payloads):
            return ""
        return match.group(0)

    return re.sub(
        r"<script\s+type=['\"]application/ld\+json['\"]\s*>(.*?)</script>\s*",
        repl,
        html,
        flags=re.I | re.S,
    )


def contains_faqpage_schema(value) -> bool:
    if isinstance(value, dict):
        if value.get("@type") == "FAQPage":
            return True
        return any(contains_faqpage_schema(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_faqpage_schema(child) for child in value)
    return False

