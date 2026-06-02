from __future__ import annotations

import csv
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "offer_scores.csv"
OUT = ROOT / "assets" / "screenshots"
WIDTH = 1200
HEIGHT = 720


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


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font: ImageFont.ImageFont, fill: tuple[int, int, int], width: int, spacing: int = 8) -> int:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if draw.textbbox((0, 0), trial, font=font)[2] <= width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + spacing
    return y


def make_visual(row: dict[str, str], path: Path) -> None:
    brand = row.get("brand_name", "AI Tool").strip() or "AI Tool"
    niche = row.get("niche", "AI Tool").strip() or "AI Tool"
    score = row.get("total_score", "").strip()
    risk = row.get("risk_level", "Review needed").strip() or "Review needed"
    trend = row.get("trend", "Monitor").strip() or "Monitor"
    channels = row.get("recommended_channels", "Organic research").strip() or "Organic research"
    score_text = f"{score}/100" if score else "Score pending"

    image = Image.new("RGB", (WIDTH, HEIGHT), (247, 250, 252))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        ratio = y / max(HEIGHT - 1, 1)
        r = int(248 + (226 - 248) * ratio)
        g = int(250 + (244 - 250) * ratio)
        b = int(252 + (255 - 252) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    dark = (15, 23, 42)
    muted = (71, 85, 105)
    teal = (15, 118, 110)
    line = (203, 213, 225)
    blue = (29, 78, 216)

    draw.rounded_rectangle((64, 58, 1136, 662), radius=26, fill=(255, 255, 255), outline=line, width=2)
    draw.rounded_rectangle((96, 94, 224, 222), radius=22, fill=teal)
    initials = "".join(word[0] for word in brand.replace(".", " ").split()[:2]).upper()[:3] or "AI"
    draw.text((160, 152), initials, font=load_font(42, True), fill=(255, 255, 255), anchor="mm")

    draw.text((254, 100), "MS Smile AI Review Hub", font=load_font(26, True), fill=teal)
    draw.text((254, 138), "Research visual - not a product screenshot", font=load_font(22), fill=muted)
    draw_wrapped(draw, brand, (254, 184), load_font(54, True), dark, 720, spacing=6)

    draw.rounded_rectangle((890, 96, 1068, 190), radius=18, fill=(239, 246, 255), outline=(191, 219, 254))
    draw.text((979, 122), "Score", font=load_font(20, True), fill=blue, anchor="mm")
    draw.text((979, 160), score_text, font=load_font(32, True), fill=dark, anchor="mm")

    cards = [
        ("Category", niche),
        ("Risk level", risk),
        ("Trend", trend),
        ("Channels", channels),
    ]
    x_positions = [96, 374, 652, 930]
    for x, (label, value) in zip(x_positions, cards):
        draw.rounded_rectangle((x, 328, x + 214, 496), radius=16, fill=(248, 250, 252), outline=line)
        draw.text((x + 20, 352), label, font=load_font(22, True), fill=teal)
        draw_wrapped(draw, value, (x + 20, 394), load_font(24), dark, 174, spacing=4)

    note = "Use this page as a research starting point. Verify current pricing, terms, limits, and affiliate approval on the official website before buying or promoting."
    draw.rounded_rectangle((96, 536, 1104, 618), radius=18, fill=(240, 253, 250), outline=(153, 246, 228))
    draw_wrapped(draw, note, (124, 558), load_font(24), (19, 78, 74), 950, spacing=4)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def main() -> None:
    if not DATA.exists():
        raise SystemExit(f"Missing {DATA}")
    OUT.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0
    with DATA.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            slug = (row.get("offer_id") or "").strip()
            if not slug:
                continue
            path = OUT / f"{slug}.png"
            if path.exists():
                skipped += 1
                continue
            make_visual(row, path)
            created += 1
            print(f"created {path}")
    print(f"Review visuals generated: created={created} skipped_existing={skipped}")


if __name__ == "__main__":
    main()
