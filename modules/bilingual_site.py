from __future__ import annotations

import re
import shutil
from pathlib import Path

from config import settings
from modules.vietnamese_localizer import localize_html


BASE_URL = (settings.base_site_url or settings.site_domain or "https://review.mssmileenglish.com").rstrip("/")


SKIP_PREFIXES = {"assets", "go", "vi", "__pycache__"}


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
        html = set_language_switcher(html, rel_url, "en")
        html = set_seo_language_tags(html, rel_url, "en", base)
        html = set_html_lang(html, "en")
        page.write_text(html, encoding="utf-8")

        vi_page = root / "vi" / page.relative_to(root)
        vi_page.parent.mkdir(parents=True, exist_ok=True)
        vi_html = localize_html(html)
        vi_html = prefix_internal_links_for_vi(vi_html)
        vi_html = set_language_switcher(vi_html, rel_url, "vi")
        vi_html = set_seo_language_tags(vi_html, rel_url, "vi", base)
        vi_html = set_html_lang(vi_html, "vi")
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
            or href.startswith("//")
        ):
            return match.group(0)
        return f"href={quote}/vi{href}{quote}"

    return re.sub(r"href=(['\"])(/[^'\"]*)\1", repl, html)


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
    }
    for src, dst in replacements.items():
        html = html.replace(src, dst)
    html = html.replace("MS Smile AI Đánh giá Hub", "MS Smile AI Review Hub")
    html = html.replace("Trung tâm đánh giá MS Smile AI", "MS Smile AI Review Hub")
    return html
