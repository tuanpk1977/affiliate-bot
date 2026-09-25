from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import now_iso, read_json


EXTERNAL_DRAFT_SCHEMA = "external_social_draft_v1"
EXTERNAL_PLATFORMS = (
    "facebook_vi",
    "facebook_en",
    "linkedin",
    "x",
    "quora",
    "devto",
    "blogger",
    "pinterest",
)
PROTECTED_REVIEW_STATUSES = {
    "approved_for_copy",
    "pending_manual_publish",
    "published_manual",
    "rejected",
    "revision_requested",
    "not_recommended",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class PendingDraft:
    directory: Path
    metadata: dict[str, Any]
    batch_date: str
    slug: str
    fingerprint: str


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _is_http_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _hashtags(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = [str(item).strip() for item in value]
    else:
        raw = re.split(r"[\s,]+", str(value or "").strip())
    return [item if item.startswith("#") else f"#{item}" for item in raw if item]


class ExternalDraftExchange:
    """File-only exchange between external writers and the canonical social review store."""

    def __init__(self, *, root: Path) -> None:
        self.root = root
        self.pending_root = root / "drafts" / "pending"
        self.package_root = root / "chatgpt_package"
        self.canonical_root = root / "data" / "social_drafts"

    def resolve_canonical_batch(self, requested: str = "latest") -> str:
        if requested and requested != "latest":
            return requested
        candidates = [
            path.name
            for path in self.canonical_root.glob("*")
            if path.is_dir() and (path / "manifest.json").exists()
        ]
        if not candidates:
            raise RuntimeError("No social editorial queue is available. Run Menu F or Menu H first.")
        return sorted(candidates)[-1]

    def export_chatgpt_package(self, *, batch_date: str = "latest") -> dict[str, Any]:
        resolved = self.resolve_canonical_batch(batch_date)
        manifest_path = self.canonical_root / resolved / "manifest.json"
        manifest = read_json(manifest_path, {})
        items = manifest.get("items") if isinstance(manifest, dict) else []
        if not isinstance(items, list):
            items = []
        export_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = _safe_text(item.get("slug"))
            source_package_value = _safe_text(item.get("source_package"))
            source_package = Path(source_package_value) if source_package_value else Path("__missing__")
            if not slug or not source_package.is_file():
                continue
            package = read_json(source_package, {})
            article = package.get("article") if isinstance(package, dict) else {}
            article = article if isinstance(article, dict) else {}
            editorial = item.get("editorial_selection")
            editorial = editorial if isinstance(editorial, dict) else {}
            source_urls = editorial.get("source_urls")
            if not isinstance(source_urls, list):
                source_urls = []
            website_url = _safe_text(item.get("url") or article.get("url"))
            if website_url and website_url not in source_urls:
                source_urls.insert(0, website_url)
            source_urls = [url for url in dict.fromkeys(map(_safe_text, source_urls)) if _is_http_url(url)]

            export_items.append(
                {
                    "slug": slug,
                    "article_title": _safe_text(item.get("title") or article.get("title") or slug),
                    "batch_date": resolved,
                    "website_url": website_url,
                    "source_urls": source_urls,
                    "content_lane": _safe_text(item.get("content_lane") or "WEBSITE_ARTICLE"),
                    "writer_status": "awaiting_external_writer",
                    "source_package": f"official_sources/{slug}/source_package.json",
                    "_source_package_path": str(source_package),
                    "output_directory": f"drafts/pending/{slug}/",
                    "required_files": ["metadata.json", *[f"{platform}.md" for platform in EXTERNAL_PLATFORMS]],
                }
            )
        if not export_items:
            raise RuntimeError(f"No writing tasks with source packages were found for {resolved}.")

        self._reset_generated_package_content()
        for item in export_items:
            slug = item["slug"]
            official_dir = self.package_root / "official_sources" / slug
            official_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(item.pop("_source_package_path")), official_dir / "source_package.json")
            self._copy_export_images(resolved, slug)

        self.package_root.mkdir(parents=True, exist_ok=True)
        queue = {
            "schema_version": EXTERNAL_DRAFT_SCHEMA,
            "batch_date": resolved,
            "generated_at": now_iso(),
            "manual_review_required": True,
            "auto_publish": False,
            "items": export_items,
        }
        _write_json(self.package_root / "queue.json", queue)
        (self.package_root / "README.md").write_text(
            self._readme(resolved, len(export_items)), encoding="utf-8", newline="\n"
        )
        (self.package_root / "PROMPT.md").write_text(
            self._prompt(resolved, len(export_items)), encoding="utf-8", newline="\n"
        )
        (self.package_root / "validation_rules.md").write_text(
            self._validation_rules(), encoding="utf-8", newline="\n"
        )
        return {
            "batch_date": resolved,
            "package_path": str(self.package_root),
            "queue_path": str(self.package_root / "queue.json"),
            "prompt_path": str(self.package_root / "PROMPT.md"),
            "items_exported": len(export_items),
            "items": export_items,
        }

    def _reset_generated_package_content(self) -> None:
        """Remove only exchange-owned content from the previous generated package."""
        for name in ("official_sources", "images"):
            path = (self.package_root / name).resolve()
            package_root = self.package_root.resolve()
            if path.parent != package_root:
                raise RuntimeError("Refusing to clean a path outside chatgpt_package.")
            if path.exists():
                shutil.rmtree(path)

    def _copy_export_images(self, batch_date: str, slug: str) -> None:
        asset_root = self.canonical_root / batch_date / slug / "assets"
        if not asset_root.exists():
            return
        destination = self.package_root / "images" / slug
        destination.mkdir(parents=True, exist_ok=True)
        for source in asset_root.iterdir():
            if source.is_file() and source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                shutil.copy2(source, destination / source.name)

    def discover_pending(self, *, batch_date: str = "latest") -> tuple[list[PendingDraft], list[dict[str, str]]]:
        records: list[PendingDraft] = []
        rejected: list[dict[str, str]] = []
        if not self.pending_root.exists():
            return records, rejected
        for metadata_path in sorted(self.pending_root.glob("*/metadata.json")):
            try:
                record = self._validate_pending(metadata_path.parent)
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                rejected.append({"path": str(metadata_path.parent), "reason": str(exc)})
                continue
            if batch_date != "latest" and record.batch_date != batch_date:
                continue
            records.append(record)
        if batch_date == "latest" and records:
            latest = max(record.batch_date for record in records)
            records = [record for record in records if record.batch_date == latest]
        return records, rejected

    def import_pending(self, *, batch_date: str = "latest") -> dict[str, Any]:
        records, rejected = self.discover_pending(batch_date=batch_date)
        imported: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        for record in records:
            try:
                result = self._import_one(record)
            except (ValueError, OSError) as exc:
                rejected.append({"path": str(record.directory), "reason": str(exc)})
                continue
            (skipped if result["status"] == "unchanged" else imported).append(result)
        resolved = (
            records[0].batch_date
            if records
            else (self.resolve_canonical_batch(batch_date) if self.canonical_root.exists() else batch_date)
        )
        return {
            "batch_date": resolved,
            "pending_root": str(self.pending_root),
            "scanned": len(records) + len(rejected),
            "imported": imported,
            "unchanged": skipped,
            "rejected": rejected,
            "approval_changed": False,
            "published": False,
        }

    def _validate_pending(self, article_dir: Path) -> PendingDraft:
        metadata_path = article_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata.json must contain a JSON object.")
        if metadata.get("schema_version") != EXTERNAL_DRAFT_SCHEMA:
            raise ValueError(f"schema_version must be {EXTERNAL_DRAFT_SCHEMA}.")
        slug = _safe_text(metadata.get("slug"))
        if not SLUG_RE.fullmatch(slug) or article_dir.name != slug:
            raise ValueError("slug must be lowercase, path-safe, and match the article directory.")
        batch_date = _safe_text(metadata.get("batch_date"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", batch_date):
            raise ValueError("batch_date must use YYYY-MM-DD.")
        if not _safe_text(metadata.get("article_title")):
            raise ValueError("article_title is required.")
        if _safe_text(metadata.get("status") or "needs_social_review") not in {
            "draft",
            "needs_social_review",
        }:
            raise ValueError("External drafts may only enter as draft or needs_social_review.")
        source_urls = metadata.get("source_urls")
        if not isinstance(source_urls, list) or not any(_is_http_url(_safe_text(url)) for url in source_urls):
            raise ValueError("At least one HTTP(S) source URL is required.")
        platforms = metadata.get("platforms")
        if not isinstance(platforms, dict):
            raise ValueError("platforms must be an object containing per-platform metadata.")
        for platform in EXTERNAL_PLATFORMS:
            details = platforms.get(platform)
            if not isinstance(details, dict):
                raise ValueError(f"Missing metadata for {platform}.")
            path = article_dir / f"{platform}.md"
            body = path.read_text(encoding="utf-8")
            if not body.strip():
                raise ValueError(f"{platform}.md is empty.")
            if "\ufffd" in body or re.search(r"\b(?:C\?|b\?i|kh\?ng)\b", body):
                raise ValueError(f"{platform}.md appears to contain encoding damage.")
            if platform == "facebook_vi" and not _safe_text(details.get("language") or "vi").startswith("vi"):
                raise ValueError("facebook_vi language must be vi.")
        fingerprint = self._fingerprint(article_dir)
        return PendingDraft(article_dir, metadata, batch_date, slug, fingerprint)

    def _fingerprint(self, article_dir: Path) -> str:
        digest = hashlib.sha256()
        paths = [article_dir / "metadata.json", *[article_dir / f"{p}.md" for p in EXTERNAL_PLATFORMS]]
        for path in paths:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def _import_one(self, record: PendingDraft) -> dict[str, str]:
        destination = self.canonical_root / record.batch_date / record.slug
        manifest_path = self.canonical_root / record.batch_date / "manifest.json"
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            manifest = {}
        existing_items = manifest.get("items")
        if not isinstance(existing_items, list):
            existing_items = []

        for platform in EXTERNAL_PLATFORMS:
            current = read_json(destination / platform / "metadata.json", {})
            if not isinstance(current, dict):
                continue
            status = _safe_text(current.get("status"))
            if status in PROTECTED_REVIEW_STATUSES:
                raise ValueError(
                    f"Refusing to overwrite {record.slug}/{platform}: current status is {status}."
                )
            if current.get("external_source_sha256") == record.fingerprint:
                continue
            if current.get("reviewer_notes") or current.get("history"):
                raise ValueError(
                    f"Refusing to overwrite {record.slug}/{platform}: review activity already exists."
                )

        existing_fingerprints = []
        for platform in EXTERNAL_PLATFORMS:
            current = read_json(destination / platform / "metadata.json", {})
            if isinstance(current, dict):
                existing_fingerprints.append(current.get("external_source_sha256"))
        if existing_fingerprints and all(value == record.fingerprint for value in existing_fingerprints):
            return {"slug": record.slug, "status": "unchanged", "path": str(destination)}

        source_urls = [_safe_text(url) for url in record.metadata["source_urls"] if _is_http_url(_safe_text(url))]
        website_url = _safe_text(record.metadata.get("website_url"))
        content_lane = _safe_text(record.metadata.get("content_lane") or "WEBSITE_ARTICLE")
        writer_provider = _safe_text(record.metadata.get("writer_provider") or "external")
        copied_image = self._copy_import_image(record, destination)

        for platform in EXTERNAL_PLATFORMS:
            details = record.metadata["platforms"][platform]
            platform_dir = destination / platform
            platform_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(record.directory / f"{platform}.md", platform_dir / "A.md")
            metadata = {
                "schema_version": 1,
                "status": "needs_social_review",
                "status_label": "Needs Review",
                "approved_for_copy": False,
                "selected_variant": "A.md",
                "article_slug": record.slug,
                "platform": platform,
                "language": _safe_text(details.get("language") or ("vi" if platform == "facebook_vi" else "en")),
                "title": _safe_text(details.get("title") or record.metadata.get("article_title")),
                "cta": _safe_text(details.get("cta")),
                "CTA": _safe_text(details.get("cta")),
                "hashtags": _hashtags(details.get("hashtags")),
                "website_url": website_url,
                "source_url": website_url or source_urls[0],
                "source_urls": source_urls,
                "canonical_url": website_url,
                "content_lane": content_lane,
                "writer_provider": writer_provider,
                "external_package_path": str(record.directory),
                "external_source_sha256": record.fingerprint,
                "external_imported_at": now_iso(),
                "local_image_path": copied_image,
                "validation_warnings": [],
                "api_used": False,
                "oauth_used": False,
                "browser_automation_used": False,
            }
            _write_json(platform_dir / "metadata.json", metadata)

        item = next(
            (entry for entry in existing_items if isinstance(entry, dict) and entry.get("slug") == record.slug),
            None,
        )
        if item is None:
            item = {}
            existing_items.append(item)
        item.update(
            {
                "slug": record.slug,
                "title": _safe_text(record.metadata.get("article_title")),
                "url": website_url,
                "status": "needs_social_review",
                "platforms": list(EXTERNAL_PLATFORMS),
                "content_lane": content_lane,
                "writer_provider": writer_provider,
                "external_package_path": str(record.directory),
            }
        )
        manifest.update(
            {
                "schema_version": manifest.get("schema_version", 1),
                "batch_date": record.batch_date,
                "status": "social_review_ready",
                "items": existing_items,
            }
        )
        _write_json(manifest_path, manifest)
        return {"slug": record.slug, "status": "imported", "path": str(destination)}

    def _copy_import_image(self, record: PendingDraft, destination: Path) -> str:
        image_name = _safe_text(record.metadata.get("image_file"))
        source = record.directory / "images" / image_name if image_name else None
        if source is None or not source.is_file():
            return ""
        if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Imported image must be PNG, JPG, JPEG, or WebP.")
        output = destination / "assets" / source.name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        return str(output)

    def _readme(self, batch_date: str, count: int) -> str:
        return f"""# ChatGPT Editorial Package

Batch: `{batch_date}`
Tasks: `{count}`

1. Zip this `chatgpt_package` folder.
2. Upload the ZIP to ChatGPT.
3. Paste the complete contents of `PROMPT.md`.
4. Download the ZIP returned by ChatGPT and extract it at the repository root so it creates `drafts/pending/<slug>/`.
5. Run Menu W to validate and register the drafts.
6. Run Menu G to review. Human approval remains mandatory.

Menu W never publishes. Menu E shows only drafts explicitly approved in Menu G.
"""

    def _prompt(self, batch_date: str, count: int) -> str:
        platform_files = "\n".join(f"- `{platform}.md`" for platform in EXTERNAL_PLATFORMS)
        return f"""# Ready-to-copy ChatGPT writing prompt

You are the external editorial writer for batch `{batch_date}`.
Read `queue.json`, every referenced file under `official_sources/`, available images, and
`validation_rules.md`. Write all {count} queued items without inventing facts or URLs.

For each queue item, return a downloadable ZIP whose root contains:

`drafts/pending/<slug>/`

- `metadata.json`
{platform_files}
- `images/` (optional; reuse only supplied images)

Use schema `external_social_draft_v1`. The metadata object must contain:

```json
{{
  "schema_version": "external_social_draft_v1",
  "batch_date": "{batch_date}",
  "slug": "exact-queue-slug",
  "article_title": "Full source title",
  "website_url": "Exact URL from queue, or empty for social-only news",
  "source_urls": ["Only URLs supplied in queue/source package"],
  "content_lane": "Value from queue",
  "writer_provider": "chatgpt",
  "status": "needs_social_review",
  "image_file": "",
  "platforms": {{
    "facebook_vi": {{"language": "vi", "title": "...", "cta": "...", "hashtags": ["#..."]}},
    "facebook_en": {{"language": "en", "title": "...", "cta": "...", "hashtags": ["#..."]}},
    "linkedin": {{"language": "en", "title": "...", "cta": "...", "hashtags": ["#..."]}},
    "x": {{"language": "en", "title": "...", "cta": "...", "hashtags": ["#..."]}},
    "quora": {{"language": "en", "title": "...", "cta": "...", "hashtags": []}},
    "devto": {{"language": "en", "title": "...", "cta": "...", "hashtags": ["#..."]}},
    "blogger": {{"language": "en", "title": "...", "cta": "...", "hashtags": ["#..."]}},
    "pinterest": {{"language": "en", "title": "...", "cta": "...", "hashtags": ["#..."]}}
  }}
}}
```

Each Markdown file contains only the public post body. Do not include labels such as
"Draft", "Suggested question", file paths, metadata, prompt instructions, or duplicate
URLs. Make every platform version distinct. Write `facebook_vi.md` in correct Vietnamese
with full diacritics and UTF-8. Do not approve or claim to publish anything.
"""

    def _validation_rules(self) -> str:
        return """# Validation Rules

- Use only supplied topics, facts, sources, and URLs.
- Keep every slug and batch date unchanged.
- All eight platform files and all platform metadata entries are required.
- Files must be UTF-8 and non-empty.
- Facebook Vietnamese must use natural Vietnamese with full diacritics.
- Platform drafts must have distinct tone and structure.
- Do not include internal instructions, local file paths, placeholders, or fabricated claims.
- Do not duplicate a destination/source URL inside one post.
- X must fit the configured short-post limit after URL expansion.
- External packages enter as `needs_social_review`; never set approval or publish state.
- Images are optional and may only reuse supplied assets.
"""
