from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import settings


BASE_URL = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
OG_IMAGE_PATH = "/assets/og/site.png"
OG_IMAGE_URL = f"{BASE_URL}{OG_IMAGE_PATH}"
OG_WIDTH = 1200
OG_HEIGHT = 630


def post_process_facebook_meta(output: Path, base_url: str | None = None) -> dict[str, int]:
    base = (base_url or BASE_URL).rstrip("/")
    pages = 0
    changed = 0
    images = 0
    for page in output.rglob("*.html"):
        pages += 1
        url = canonical_url_for_page(page, output, base)
        text = page.read_text(encoding="utf-8", errors="ignore")
        title, description = page_title_and_description(text)
        page_type = "website" if url.rstrip("/") == base else "article"
        image_url = OG_IMAGE_URL
        if page_type == "website":
            fallback_image = output / OG_IMAGE_PATH.lstrip("/")
            if not fallback_image.exists():
                write_dynamic_og_image(fallback_image, "MS Smile AI Review Hub", "AI and SaaS reviews, comparisons, pricing research, and workflow guidance.")
        else:
            image_path = og_image_path_for_page(output, page)
            if not image_path.exists():
                write_dynamic_og_image(image_path, title, description)
            image_url = f"{base}/{image_path.relative_to(output).as_posix()}"
            images += 1
        updated = ensure_open_graph_tags(text, url, title, description, image_url, page_type)
        if updated != text:
            page.write_text(updated, encoding="utf-8")
            changed += 1
    return {"pages": pages, "changed": changed, "images": images}


def canonical_url_for_page(page: Path, output: Path, base: str) -> str:
    rel = page.relative_to(output).as_posix()
    if rel == "index.html":
        return f"{base}/"
    if rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    return f"{base}/{rel.lstrip('/')}"


def ensure_open_graph_tags(text: str, url: str, title: str | None = None, description: str | None = None, image_url: str | None = None, page_type: str | None = None) -> str:
    fallback_title, fallback_description = page_title_and_description(text)
    title = title or fallback_title
    description = description or fallback_description
    image_url = image_url or OG_IMAGE_URL
    page_type = page_type or ("website" if url.rstrip("/") == BASE_URL else "article")

    text = upsert_meta_property(text, "og:title", title)
    text = upsert_meta_property(text, "og:description", description)
    text = upsert_meta_property(text, "og:url", url)
    text = upsert_meta_property(text, "og:type", page_type)
    text = upsert_meta_property(text, "og:image", image_url)
    text = upsert_meta_property(text, "og:image:secure_url", image_url)
    text = upsert_meta_property(text, "og:image:type", "image/png")
    text = upsert_meta_property(text, "og:image:width", str(OG_WIDTH))
    text = upsert_meta_property(text, "og:image:height", str(OG_HEIGHT))
    text = upsert_meta_name(text, "twitter:card", "summary_large_image")
    text = upsert_meta_name(text, "twitter:title", title)
    text = upsert_meta_name(text, "twitter:description", description)
    text = upsert_meta_name(text, "twitter:image", image_url)
    return text


def page_title_and_description(text: str) -> tuple[str, str]:
    title = first_match(text, r"<title>(.*?)</title>") or "MS Smile AI Review Hub"
    title = re.sub(r"\s+", " ", html.unescape(strip_tags(title))).strip()
    description = first_match(text, r"<meta\s+name=['\"]description['\"]\s+content=['\"]([^'\"]*)['\"][^>]*>")
    description = html.unescape(description or "AI and SaaS tool reviews, comparisons, pricing research, and workflow guidance.")
    return title, description


def og_image_path_for_page(output: Path, page: Path) -> Path:
    rel = page.relative_to(output)
    if rel.name.lower() == "index.html":
        slug = rel.parent.as_posix().strip("/").replace("/", "--") or "home"
    else:
        slug = rel.with_suffix("").as_posix().strip("/").replace("/", "--") or "page"
    return output / "assets" / "og" / "pages" / f"{slug}.png"


def write_dynamic_og_image(path: Path, title: str, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (OG_WIDTH, OG_HEIGHT), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    for y in range(OG_HEIGHT):
        ratio = y / max(OG_HEIGHT - 1, 1)
        r = int(15 + (30 - 15) * ratio)
        g = int(118 + (41 - 118) * ratio)
        b = int(110 + (59 - 110) * ratio)
        draw.line([(0, y), (OG_WIDTH, y)], fill=(r, g, b))

    font_title = load_font(64, bold=True)
    font_subtitle = load_font(30, bold=False)
    font_label = load_font(28, bold=True)

    draw.rounded_rectangle((70, 70, 1130, 560), radius=28, fill=(255, 255, 255), outline=(203, 213, 225), width=2)
    draw.text((110, 118), "MS Smile AI Review Hub", fill=(15, 118, 110), font=font_label)

    title_lines = wrap_text(title.replace(" - MS Smile AI Review Hub", ""), font_title, 940, draw, max_lines=3)
    y = 190
    for line in title_lines:
        draw.text((110, y), line, fill=(15, 23, 42), font=font_title)
        y += 76

    desc_lines = wrap_text(description, font_subtitle, 940, draw, max_lines=2)
    y = 430
    for line in desc_lines:
        draw.text((110, y), line, fill=(71, 85, 105), font=font_subtitle)
        y += 42

    draw.rounded_rectangle((890, 472, 1078, 520), radius=24, fill=(236, 253, 245), outline=(167, 243, 208))
    draw.text((918, 481), "Article", fill=(4, 120, 87), font=font_label)
    image.save(path, "PNG", optimize=True)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.ImageFont, width: int, draw: ImageDraw.ImageDraw, max_lines: int) -> list[str]:
    words = re.sub(r"\s+", " ", text).strip().split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if text_width(draw, candidate, font) <= width:
            current.append(word)
            continue
        if current:
            lines.append(" ".join(current))
        current = [word]
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = lines[-1].rstrip(" .") + "..."
    return lines or [text[:80]]


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def upsert_meta_property(text: str, prop: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    pattern = re.compile(rf"<meta\s+property=['\"]{re.escape(prop)}['\"]\s+content=['\"][^'\"]*['\"]\s*/?>", re.I)
    tag = f'<meta property="{prop}" content="{escaped}">'
    if pattern.search(text):
        return pattern.sub(tag, text, count=1)
    return insert_before_head_end(text, tag)


def upsert_meta_name(text: str, name: str, content: str) -> str:
    escaped = html.escape(content, quote=True)
    pattern = re.compile(rf"<meta\s+name=['\"]{re.escape(name)}['\"]\s+content=['\"][^'\"]*['\"]\s*/?>", re.I)
    tag = f'<meta name="{name}" content="{escaped}">'
    if pattern.search(text):
        return pattern.sub(tag, text, count=1)
    return insert_before_head_end(text, tag)


def insert_before_head_end(text: str, tag: str) -> str:
    if "</head>" in text:
        return text.replace("</head>", f"  {tag}\n</head>", 1)
    return text + "\n" + tag + "\n"


def first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1) if match else ""


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)
