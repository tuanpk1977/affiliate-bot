from __future__ import annotations

import math
import random
import re
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "screenshots"
WIDTH = 1200
HEIGHT = 720

TOOLS = [
    ("activecampaign", "ActiveCampaign", "Email Marketing"),
    ("make", "Make", "Automation"),
    ("surfer-seo", "Surfer SEO", "AI SEO"),
    ("github-copilot", "GitHub Copilot", "AI Coding"),
    ("semrush", "Semrush", "SEO Platform"),
    ("elevenlabs", "ElevenLabs", "AI Voice"),
    ("zapier", "Zapier", "Automation"),
    ("webflow-ai", "Webflow AI", "Website Builder"),
    ("hubspot", "HubSpot", "CRM"),
    ("cursor", "Cursor", "AI Coding"),
    ("canva", "Canva", "AI Design"),
    ("gamma", "Gamma", "AI Presentation"),
    ("notion-ai", "Notion AI", "Productivity"),
    ("jasper", "Jasper", "AI Writing"),
    ("copy-ai", "Copy.ai", "AI Writing"),
    ("descript", "Descript", "AI Video"),
    ("runway", "Runway", "AI Video"),
]

PALETTES = [
    ((15, 118, 110), (236, 253, 245), (20, 184, 166)),
    ((37, 99, 235), (239, 246, 255), (96, 165, 250)),
    ((124, 58, 237), (245, 243, 255), (167, 139, 250)),
    ((202, 138, 4), (254, 252, 232), (250, 204, 21)),
    ((220, 38, 38), (254, 242, 242), (248, 113, 113)),
    ((22, 101, 52), (240, 253, 244), (74, 222, 128)),
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tools = merge_tools_with_offer_data()
    for index, (slug, brand, niche) in enumerate(tools):
        image = render_tool_mockup(slug, brand, niche, index)
        path = OUTPUT_DIR / f"{slug}.png"
        image.save(path, "PNG", optimize=True)
        print(f"created {path.relative_to(ROOT)}")
    print(f"Done. Generated {len(tools)} PNG mockup screenshots in {OUTPUT_DIR.relative_to(ROOT)}")


def merge_tools_with_offer_data() -> list[tuple[str, str, str]]:
    items = {slug: (slug, brand, niche) for slug, brand, niche in TOOLS}
    offer_scores = ROOT / "data" / "offer_scores.csv"
    if offer_scores.exists():
        try:
            df = pd.read_csv(offer_scores)
            for _, row in df.iterrows():
                brand = str(row.get("brand_name", "")).strip()
                if not brand:
                    continue
                slug = slugify(brand)
                niche = str(row.get("niche", "SaaS")).strip() or "SaaS"
                if slug in items:
                    items[slug] = (slug, brand, niche)
        except Exception:
            pass
    return list(items.values())


def render_tool_mockup(slug: str, brand: str, niche: str, index: int) -> Image.Image:
    random.seed(slug)
    primary, soft, accent = PALETTES[index % len(PALETTES)]
    img = Image.new("RGB", (WIDTH, HEIGHT), (246, 248, 251))
    draw = ImageDraw.Draw(img)
    font_regular = load_font(24)
    font_small = load_font(18)
    font_tiny = load_font(15)
    font_bold = load_font(30, bold=True)
    font_title = load_font(46, bold=True)
    font_metric = load_font(38, bold=True)

    gradient_background(draw, primary, accent)
    rounded(draw, (54, 42, 1146, 678), 34, (255, 255, 255), outline=(218, 226, 236), width=2)
    draw_topbar(draw, brand, niche, primary, font_title, font_regular, font_small)
    draw_sidebar(draw, primary, soft, font_small, font_tiny)

    score = 74 + (stable_hash(slug) % 19)
    cpc = 1.4 + ((stable_hash(slug + "cpc") % 36) / 10)
    conv = 2.1 + ((stable_hash(slug + "conv") % 32) / 10)
    roi = 8 + (stable_hash(slug + "roi") % 42)

    metric_cards = [
        ("Score", f"{score}/100", "Research fit"),
        ("Pricing", f"${cpc:.1f} CPC", "Verify current plan"),
        ("Features", "Strong", "Workflow signals"),
        ("ROI", f"+{roi}%", "Estimated only"),
    ]
    x = 294
    for label, value, note in metric_cards:
        draw_metric_card(draw, x, 170, label, value, note, primary, soft, font_small, font_metric, font_tiny)
        x += 198

    draw_panel(draw, (294, 324, 674, 586), "Feature signals", [
        "Workflow support",
        "Team usage potential",
        "Integration needs",
        "Pricing verification",
    ], primary, font_bold, font_small)
    draw_panel(draw, (704, 324, 1092, 586), "Review notes", [
        "Pros: clear category fit",
        "Cons: terms need review",
        "CTA: official website",
        "Disclosure: affiliate safe",
    ], primary, font_bold, font_small)
    draw_chart(draw, (320, 612, 1060, 644), primary, accent)

    watermark = f"{brand} review mockup - generated locally"
    draw.text((300, 646), watermark, fill=(100, 116, 139), font=font_tiny)
    return img


def draw_topbar(draw: ImageDraw.ImageDraw, brand: str, niche: str, primary: tuple[int, int, int], font_title: ImageFont.ImageFont, font_regular: ImageFont.ImageFont, font_small: ImageFont.ImageFont) -> None:
    rounded(draw, (84, 72, 1116, 136), 20, (248, 250, 252))
    rounded(draw, (108, 86, 154, 122), 12, primary)
    initial = brand[:1].upper() or "A"
    draw.text((124, 90), initial, fill=(255, 255, 255), font=font_regular)
    draw.text((178, 78), brand, fill=(15, 23, 42), font=font_title)
    draw.text((178, 118), f"{niche} research dashboard", fill=(100, 116, 139), font=font_small)
    draw_status_pill(draw, (906, 88, 1088, 122), "Editorial review", primary, font_small)


def draw_sidebar(draw: ImageDraw.ImageDraw, primary: tuple[int, int, int], soft: tuple[int, int, int], font_small: ImageFont.ImageFont, font_tiny: ImageFont.ImageFont) -> None:
    rounded(draw, (84, 158, 250, 644), 24, (248, 250, 252), outline=(226, 232, 240))
    draw.text((112, 190), "Review OS", fill=(15, 23, 42), font=font_small)
    items = ["Overview", "Pricing", "Features", "Pros", "Cons", "Score"]
    y = 238
    for idx, item in enumerate(items):
        fill = soft if idx == 0 else (255, 255, 255)
        rounded(draw, (106, y, 228, y + 38), 12, fill)
        dot = primary if idx == 0 else (148, 163, 184)
        draw.ellipse((120, y + 14, 130, y + 24), fill=dot)
        draw.text((140, y + 9), item, fill=(51, 65, 85), font=font_tiny)
        y += 52


def draw_metric_card(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, note: str, primary: tuple[int, int, int], soft: tuple[int, int, int], font_small: ImageFont.ImageFont, font_metric: ImageFont.ImageFont, font_tiny: ImageFont.ImageFont) -> None:
    rounded(draw, (x, y, x + 168, y + 124), 22, (255, 255, 255), outline=(226, 232, 240))
    draw.text((x + 18, y + 16), label, fill=(71, 85, 105), font=font_small)
    draw.text((x + 18, y + 48), value, fill=primary, font=font_metric)
    rounded(draw, (x + 18, y + 92, x + 144, y + 112), 10, soft)
    draw.text((x + 28, y + 94), note[:18], fill=(51, 65, 85), font=font_tiny)


def draw_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, rows: list[str], primary: tuple[int, int, int], font_bold: ImageFont.ImageFont, font_small: ImageFont.ImageFont) -> None:
    rounded(draw, box, 24, (255, 255, 255), outline=(226, 232, 240))
    x1, y1, x2, _ = box
    draw.text((x1 + 24, y1 + 22), title, fill=(15, 23, 42), font=font_bold)
    y = y1 + 78
    for row in rows:
        draw.ellipse((x1 + 26, y + 8, x1 + 38, y + 20), fill=primary)
        draw.text((x1 + 52, y), row, fill=(71, 85, 105), font=font_small)
        draw.line((x1 + 24, y + 34, x2 - 24, y + 34), fill=(241, 245, 249), width=2)
        y += 44


def draw_chart(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], primary: tuple[int, int, int], accent: tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = box
    points = []
    steps = 18
    for i in range(steps + 1):
        x = x1 + int((x2 - x1) * i / steps)
        wave = math.sin(i / 2.2) * 8
        y = y2 - 10 - int((i / steps) * 24 + wave)
        points.append((x, y))
    draw.line(points, fill=primary, width=5)
    for x, y in points[::3]:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=accent)


def draw_status_pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, primary: tuple[int, int, int], font: ImageFont.ImageFont) -> None:
    rounded(draw, box, 17, primary)
    draw.text((box[0] + 18, box[1] + 7), text, fill=(255, 255, 255), font=font)


def gradient_background(draw: ImageDraw.ImageDraw, primary: tuple[int, int, int], accent: tuple[int, int, int]) -> None:
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(248 * (1 - ratio) + 234 * ratio)
        g = int(250 * (1 - ratio) + 244 * ratio)
        b = int(252 * (1 - ratio) + 255 * ratio)
        draw.line((0, y, WIDTH, y), fill=(r, g, b))
    draw.ellipse((-220, -190, 360, 310), fill=(*primary,))
    draw.ellipse((920, 520, 1320, 860), fill=(*accent,))


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int], outline: tuple[int, int, int] | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def stable_hash(text: str) -> int:
    value = 0
    for char in text:
        value = (value * 131 + ord(char)) % 100000
    return value


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "tool"


if __name__ == "__main__":
    main()
