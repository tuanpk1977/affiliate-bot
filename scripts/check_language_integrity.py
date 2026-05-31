from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BASE_URL = "https://smileaireviewhub.com"

PRIORITY_PATHS = [
    "/",
    "/cursor/",
    "/windsurf-review/",
    "/comparisons/cursor-vs-windsurf/",
    "/comparisons/copilot-vs-cursor/",
    "/best-ai-coding-tools-2026/",
]

ENGLISH_FORBIDDEN = [
    "Trang chủ",
    "Đánh giá",
    "So sánh",
    "Giá",
    "Danh mục",
    "Trung tâm",
    "Liên hệ",
    "Nội dung",
    "Tóm tắt",
    "Ưu điểm",
    "Hạn chế",
    "Kết luận",
]

VI_FORBIDDEN = [
    "Contents",
    "Overview",
    "Features",
    "Pros and Cons",
    "Pricing",
    "Who Should Use It",
    "Alternatives",
    "Final Verdict",
    "Visit official website",
    "Visit Official Website",
]


def file_for_url(url_path: str) -> Path:
    if url_path == "/":
        return DOCS / "index.html"
    return DOCS / url_path.strip("/") / "index.html"


def visible_text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", html)


def assert_contains(html: str, needle: str, label: str, errors: list[str]) -> None:
    if needle not in html:
        errors.append(f"{label}: missing {needle}")


def check_page(path: Path, url_path: str, lang: str, errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"{url_path}: missing file {path}")
        return
    html = path.read_text(encoding="utf-8", errors="ignore")
    text = visible_text(html)
    if lang == "en":
        for word in ENGLISH_FORBIDDEN:
            if word in text:
                errors.append(f"{url_path}: English page contains Vietnamese UI word: {word}")
    else:
        for word in VI_FORBIDDEN:
            if word in text:
                errors.append(f"{url_path}: Vietnamese page contains English UI word: {word}")

    en_path = "/" if url_path == "/vi/" else url_path.removeprefix("/vi")
    if not en_path.startswith("/"):
        en_path = "/" + en_path
    vi_path = "/vi/" if en_path == "/" else "/vi" + en_path
    en_url = BASE_URL + en_path
    vi_url = BASE_URL + vi_path
    expected_canonical = vi_url if lang == "vi" else en_url
    assert_contains(html, f'rel="canonical" href="{expected_canonical}"', url_path, errors)
    assert_contains(html, f'hreflang="en" href="{en_url}"', url_path, errors)
    assert_contains(html, f'hreflang="vi" href="{vi_url}"', url_path, errors)
    assert_contains(html, f'hreflang="x-default" href="{en_url}"', url_path, errors)
    assert_contains(html, "language-switcher", url_path, errors)


def main() -> None:
    errors: list[str] = []
    for path in PRIORITY_PATHS:
        check_page(file_for_url(path), path, "en", errors)
        vi_path = "/vi/" if path == "/" else "/vi" + path
        check_page(file_for_url(vi_path), vi_path, "vi", errors)

    if errors:
        print("Language integrity check failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(
        f"Language integrity validation passed for {len(PRIORITY_PATHS)} English "
        f"and {len(PRIORITY_PATHS)} Vietnamese pages."
    )


if __name__ == "__main__":
    main()
