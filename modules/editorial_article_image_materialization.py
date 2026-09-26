from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Callable


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


class EditorialArticleImageMaterialization:
    """Own local article-cover assets and their HTML/metadata representation."""

    def __init__(
        self,
        *,
        root: Path,
        site_output_dir: Path,
        base_site_url: str,
        article_bundle_paths: Callable[[str], dict[str, Path]],
    ) -> None:
        self.root = root
        self.site_output_dir = site_output_dir
        self.base_site_url = base_site_url
        self.article_bundle_paths = article_bundle_paths

    @staticmethod
    def required_image_src(slug: str) -> str:
        return f"/assets/og/pages/{slug}.svg"

    def required_image_asset_paths(self, slug: str) -> list[Path]:
        rel = Path("assets") / "og" / "pages" / f"{slug}.svg"
        return [self.root / rel, self.site_output_dir / rel, self.root / "docs" / rel]

    @staticmethod
    def render_local_cover_svg(*, title: str, slug: str) -> str:
        safe_title = html.escape(title[:120])
        safe_slug = html.escape(slug)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
  <title id="title">{safe_title}</title>
  <desc id="desc">Smile AI Review Hub editorial cover for {safe_slug}</desc>
  <rect width="1200" height="630" fill="#0f172a"/>
  <rect x="48" y="48" width="1104" height="534" rx="28" fill="#f8fafc"/>
  <text x="92" y="132" fill="#0f766e" font-family="Arial, sans-serif" font-size="34" font-weight="700">Smile AI Review Hub</text>
  <text x="92" y="288" fill="#111827" font-family="Arial, sans-serif" font-size="58" font-weight="700">{safe_title}</text>
  <text x="92" y="420" fill="#475569" font-family="Arial, sans-serif" font-size="30">Source-backed AI software review</text>
  <circle cx="1010" cy="422" r="76" fill="#14b8a6"/>
  <path d="M973 421l26 27 55-70" fill="none" stroke="#fff" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

    def ensure_required_article_image(
        self,
        *,
        slug: str,
        title: str,
        dry_run: bool = False,
        required_image_src: Callable[[str], str] | None = None,
        required_image_asset_paths: Callable[[str], list[Path]] | None = None,
        render_local_cover_svg: Callable[..., str] | None = None,
        html_has_local_image: Callable[[str], bool] | None = None,
        inject_required_image_html: Callable[..., str] | None = None,
        upsert_meta_property: Callable[[str, str, str], str] | None = None,
        upsert_meta_name: Callable[[str, str, str], str] | None = None,
    ) -> dict[str, Any]:
        image_src_for = required_image_src or self.required_image_src
        asset_paths_for = required_image_asset_paths or self.required_image_asset_paths
        render_svg = render_local_cover_svg or self.render_local_cover_svg
        has_image = html_has_local_image or self.html_has_local_image
        inject_image = inject_required_image_html or self.inject_required_image_html
        upsert_property = upsert_meta_property or self.upsert_meta_property
        upsert_name = upsert_meta_name or self.upsert_meta_name

        paths = self.article_bundle_paths(slug)
        draft_path = paths["draft_html"]
        if not draft_path.exists():
            raise FileNotFoundError(f"Missing draft HTML for {slug}: {draft_path}")
        html_text = draft_path.read_text(encoding="utf-8", errors="ignore")
        if has_image(html_text):
            return {"slug": slug, "status": "already_has_image", "changed_files": []}
        image_src = image_src_for(slug)
        asset_paths = asset_paths_for(slug)
        changed_files = [str(path) for path in asset_paths]
        changed_files.extend([str(draft_path), str(paths["metadata"])])
        if dry_run:
            return {
                "slug": slug,
                "status": "would_generate",
                "image_src": image_src,
                "changed_files": changed_files,
            }

        svg = render_svg(title=title, slug=slug)
        for asset_path in asset_paths:
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            if not asset_path.exists():
                asset_path.write_text(svg, encoding="utf-8")
        image_html = (
            f'<img class="article-hero-image" src="{html.escape(image_src)}" '
            f'width="1200" height="630" alt="{html.escape(title)} cover image" '
            f'loading="eager" decoding="async">'
        )
        updated_html = inject_image(html_text, image_html=image_html)
        absolute_image = f"{self.base_site_url.rstrip('/')}{image_src}"
        updated_html = upsert_property(updated_html, "og:image", absolute_image)
        updated_html = upsert_name(updated_html, "twitter:image", absolute_image)
        draft_path.write_text(updated_html, encoding="utf-8")

        metadata = _read_json(paths["metadata"], {})
        if isinstance(metadata, dict):
            metadata["image"] = {
                "src": image_src,
                "alt": f"{title} cover image",
                "width": 1200,
                "height": 630,
                "generated_by": "local_svg_cover_generator",
            }
            metadata["og_image"] = absolute_image
            metadata["twitter_image"] = absolute_image
            _write_json(paths["metadata"], metadata)
        return {
            "slug": slug,
            "status": "generated",
            "image_src": image_src,
            "changed_files": changed_files,
        }

    def html_has_local_image(self, html_text: str) -> bool:
        for match in re.finditer(
            r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>",
            html_text,
            flags=re.IGNORECASE,
        ):
            src = match.group(1).strip()
            if not src or src.startswith(("http://", "https://", "data:")):
                return bool(src)
            if src.startswith("/"):
                rel = src.lstrip("/")
                if (
                    (self.site_output_dir / rel).exists()
                    or (self.root / "docs" / rel).exists()
                    or (self.root / rel).exists()
                ):
                    return True
                return False
            return True
        return False

    @staticmethod
    def inject_required_image_html(html_text: str, *, image_html: str) -> str:
        h1_match = re.search(r"</h1>", html_text, flags=re.IGNORECASE)
        if h1_match:
            insert_at = h1_match.end()
            return html_text[:insert_at] + "\n" + image_html + html_text[insert_at:]
        body_match = re.search(r"<body[^>]*>", html_text, flags=re.IGNORECASE)
        if body_match:
            insert_at = body_match.end()
            return html_text[:insert_at] + "\n" + image_html + html_text[insert_at:]
        return image_html + "\n" + html_text

    @staticmethod
    def upsert_meta_property(html_text: str, property_name: str, content: str) -> str:
        pattern = rf"<meta\b[^>]*\bproperty=[\"']{re.escape(property_name)}[\"'][^>]*>"
        replacement = f'<meta property="{html.escape(property_name)}" content="{html.escape(content)}">'
        if re.search(pattern, html_text, flags=re.IGNORECASE):
            return re.sub(pattern, replacement, html_text, count=1, flags=re.IGNORECASE)
        return html_text.replace("</head>", f"  {replacement}\n</head>", 1)

    @staticmethod
    def upsert_meta_name(html_text: str, name: str, content: str) -> str:
        pattern = rf"<meta\b[^>]*\bname=[\"']{re.escape(name)}[\"'][^>]*>"
        replacement = f'<meta name="{html.escape(name)}" content="{html.escape(content)}">'
        if re.search(pattern, html_text, flags=re.IGNORECASE):
            return re.sub(pattern, replacement, html_text, count=1, flags=re.IGNORECASE)
        return html_text.replace("</head>", f"  {replacement}\n</head>", 1)
