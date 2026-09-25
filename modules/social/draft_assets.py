from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional local image helper
    Image = None
    ImageDraw = None
    ImageFont = None

from .utils import PublishedArticle


SOCIAL_ASSET_FORMATS = {
    "master": (1200, 1200),
    "og": (1200, 630),
    "facebook": (1200, 630),
    "linkedin": (1200, 630),
    "x": (1200, 675),
    "pinterest": (1000, 1500),
    "threads": (1080, 1080),
    "bluesky": (1200, 675),
    "medium": (1200, 630),
    "hashnode": (1200, 630),
    "blogger": (1200, 630),
    "telegram": (1280, 720),
    "devto": (1200, 630),
    "quora": (1200, 630),
    "producthunt": (1200, 630),
}

PLATFORM_ASSET_NAME = {
    "twitter": "x",
    "facebook_en": "facebook",
    "facebook_vi": "facebook",
}


def _wrap_card_text(text: str, *, max_chars: int = 34, max_lines: int = 4) -> list[str]:
    words = re.sub(r"\s+", " ", text or "").strip().split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines or ["Smile AI Review Hub"]


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_asset_name(platform: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "", (platform or "").lower())
    return PLATFORM_ASSET_NAME.get(clean, clean or "og")


class SocialDraftAssetService:
    def __init__(
        self,
        *,
        draft_root: Path,
        read_json: Callable[[Path, Any], Any],
        write_json: Callable[[Path, object], None],
        now_iso: Callable[[], str],
        official_source_name: Callable[[str], str],
        validate_pinterest_visual: Callable[..., dict[str, Any]],
        image: Any,
        image_draw: Any,
        image_font: Any,
    ) -> None:
        self.draft_root = draft_root
        self.read_json = read_json
        self.write_json = write_json
        self.now_iso = now_iso
        self.official_source_name = official_source_name
        self.validate_pinterest_visual = validate_pinterest_visual
        self.image = image
        self.image_draw = image_draw
        self.image_font = image_font

    def _asset_fingerprint(self, article: PublishedArticle) -> str:
        payload = {
            "version": 3,
            "title": article.title,
            "description": article.description,
            "url": article.url,
            "image": article.image,
            "formats": SOCIAL_ASSET_FORMATS,
            "key_points": article.key_points or [],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _render_social_asset(
        self,
        path: Path,
        *,
        title: str,
        subtitle: str,
        size: tuple[int, int],
        points: list[str] | None = None,
        source_name: str = "",
    ) -> None:
        if self.image is None or self.image_draw is None or self.image_font is None:
            raise RuntimeError("Pillow is required for local social asset generation.")
        width, height = size
        image = self.image.new("RGB", size, "#0f172a")
        draw = self.image_draw.Draw(image)
        try:
            title_font = self.image_font.truetype("arial.ttf", max(44, int(width * 0.046)))
            brand_font = self.image_font.truetype("arial.ttf", max(28, int(width * 0.028)))
            small_font = self.image_font.truetype("arial.ttf", max(22, int(width * 0.022)))
        except Exception:
            title_font = self.image_font.load_default()
            brand_font = self.image_font.load_default()
            small_font = self.image_font.load_default()
        margin = max(44, int(min(width, height) * 0.075))
        draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=34, fill="#f8fafc")
        x = margin + max(34, int(width * 0.035))
        y = margin + max(34, int(height * 0.055))
        draw.text((x, y), "Smile AI Review Hub", fill="#0f766e", font=brand_font)
        max_chars = max(18, int(width / max(22, int(width * 0.046)) * 1.25))
        max_lines = 5 if height >= 1000 else 3
        y += max(86, int(height * 0.16))
        for line in _wrap_card_text(title, max_chars=max_chars, max_lines=max_lines):
            draw.text((x, y), line, fill="#0f172a", font=title_font)
            y += max(54, int(width * 0.058))
        if height >= 1200:
            y += max(20, int(height * 0.025))
            for point in list(points or [])[:4]:
                wrapped = _wrap_card_text(f"• {point}", max_chars=max_chars + 4, max_lines=2)
                for line in wrapped:
                    draw.text((x, y), line, fill="#334155", font=small_font)
                    y += max(36, int(width * 0.036))
                y += max(14, int(height * 0.012))
        footer_y = height - margin - max(78, int(height * 0.1))
        footer = f"Source: {source_name}" if source_name else (subtitle or "Source-backed AI software review")
        draw.text((x, footer_y), footer, fill="#475569", font=small_font)
        radius = max(42, int(min(width, height) * 0.06))
        cx = width - margin - max(86, int(width * 0.08))
        cy = height - margin - max(86, int(height * 0.08))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill="#14b8a6")
        draw.line(
            (cx - radius * 0.45, cy, cx - radius * 0.12, cy + radius * 0.34, cx + radius * 0.48, cy - radius * 0.42),
            fill="white",
            width=max(8, int(radius * 0.16)),
            joint="curve",
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "PNG")

    def generate_social_assets(
        self,
        article: PublishedArticle,
        *,
        batch_date: str,
        force: bool = False,
        asset_fingerprint: Callable[[PublishedArticle], str] | None = None,
        render_social_asset: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        assets_dir = self.draft_root / batch_date / article.article_id / "assets"
        manifest_path = assets_dir / "manifest.json"
        fingerprint = (asset_fingerprint or self._asset_fingerprint)(article)
        existing = self.read_json(manifest_path, {})
        outputs = existing.get("outputs") if isinstance(existing, dict) else {}
        if (
            not force
            and existing.get("fingerprint") == fingerprint
            and isinstance(outputs, dict)
            and all((assets_dir / f"{name}.png").exists() for name in SOCIAL_ASSET_FORMATS)
        ):
            return existing
        if self.image is None or self.image_draw is None or self.image_font is None:
            raise RuntimeError("Pillow is required for local social asset generation.")
        subtitle = "What changed • Why it matters • What to verify"
        source_name = self.official_source_name(article.url)
        visual_points = list(article.key_points or [])[:4]
        if len(visual_points) < 2:
            visual_points = [
                f"Official update from {source_name}" if source_name else "Official source-backed update",
                "Check scope and applicability for your workflow",
                "Use the official source as the canonical reference",
            ]
        outputs = {}
        warnings = []
        if article.image.lower().endswith(".svg"):
            warnings.append("source image is SVG; generated local PNG assets instead of relying on social preview")
        for name, size in SOCIAL_ASSET_FORMATS.items():
            path = assets_dir / f"{name}.png"
            (render_social_asset or self._render_social_asset)(
                path,
                title=article.title,
                subtitle=subtitle,
                size=size,
                points=visual_points if name == "pinterest" else [],
                source_name=source_name if name == "pinterest" else "",
            )
            with self.image.open(path) as img:
                width, height = img.size
            outputs[name] = {
                "filename": f"{name}.png",
                "width": width,
                "height": height,
                "mime_type": "image/png",
                "file_size": path.stat().st_size,
                "local_path": str(path),
                "checksum": _sha256_file(path),
                "validation_status": "PASS" if (width, height) == size and path.stat().st_size > 0 else "FAIL",
                "public_url": "",
            }
            if name == "pinterest":
                outputs[name]["visual_validation"] = self.validate_pinterest_visual(
                    headline=article.title,
                    subhead=subtitle,
                    points=visual_points,
                    source_name=source_name,
                    verified_facts=visual_points,
                    empty_area_ratio=0.35,
                )
        manifest = {
            "schema_version": 1,
            "source_image": article.image,
            "generation_method": "local_pillow_branded_asset",
            "fingerprint": fingerprint,
            "master_dimensions": {"width": SOCIAL_ASSET_FORMATS["master"][0], "height": SOCIAL_ASSET_FORMATS["master"][1]},
            "outputs": outputs,
            "warnings": warnings,
            "validation_status": "PASS" if all(item["validation_status"] == "PASS" for item in outputs.values()) else "FAIL",
            "pinterest_visual_facts": visual_points,
            "created_at": existing.get("created_at") or self.now_iso(),
            "updated_at": self.now_iso(),
        }
        self.write_json(manifest_path, manifest)
        return manifest

    def _ensure_local_social_card(
        self,
        *,
        batch_date: str,
        slug: str,
        title: str,
        generate_social_assets: Callable[..., dict[str, Any]] | None = None,
    ) -> str:
        article = PublishedArticle(
            article_id=slug,
            title=title,
            url=f"https://smileaireviewhub.com/{slug}/",
            description="",
            image="",
            tags=[],
            publish_date="",
        )
        manifest = (generate_social_assets or self.generate_social_assets)(article, batch_date=batch_date)
        output = manifest.get("outputs", {}).get("og", {})
        return str(output.get("local_path") or "")
