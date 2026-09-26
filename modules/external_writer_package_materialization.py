from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

EXPORTABLE_RESEARCH_SUFFIXES = {".csv", ".json", ".md", ".txt"}
SECRET_NAME_RE = re.compile(
    r"(^|[._-])(credential|credentials|secret|secrets|token|tokens|api[_-]?key|id_rsa|private[_-]?key)([._-]|$)",
    re.I,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExternalWriterPackageMaterializer:
    """Materialize local inputs and guidance into an external-writer package."""

    def __init__(
        self,
        *,
        root: Path,
        affiliate_brief_builder: Callable[[Path, str], dict[str, Any]],
    ) -> None:
        self.root = root
        self.affiliate_brief_builder = affiliate_brief_builder

    def copy_inputs(
        self,
        package_dir: Path,
        tasks: list[dict[str, Any]],
        *,
        copy_website_research_artifacts: Callable[[Path, str], None] | None = None,
        copy_existing_article_snapshot: Callable[[Path, dict[str, Any]], None] | None = None,
        copy_series_history: Callable[[Path, dict[str, Any]], None] | None = None,
    ) -> None:
        website_research = copy_website_research_artifacts or self.copy_website_research_artifacts
        existing_snapshot = copy_existing_article_snapshot or self.copy_existing_article_snapshot
        series_history = copy_series_history or self.copy_series_history
        for task in tasks:
            slug = task["article_slug"]
            task_id = task["task_id"]
            strict_verified_package = bool(_text(task.get("legacy_queue_file")))
            for fact_root in (
                self.root / "data" / "write_queue" / task_id,
                self.root / "data" / "intelligence" / "verified_facts" / task_id,
            ):
                for name in ("verified_facts.json", "facts_to_verify.json", "fact_conflicts.json"):
                    source = fact_root / name
                    if source.is_file():
                        target = package_dir / "research" / slug / "verified_facts" / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
            if not strict_verified_package:
                for raw in list(task.get("research_files") or []):
                    source = self.root / raw
                    if source.is_file():
                        target = package_dir / "research" / slug / source.name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
            if _text(task.get("task_type")).startswith("WEBSITE_"):
                website_research(package_dir, slug)
            if _text(task.get("task_type")) == "WEBSITE_UPDATE":
                existing_snapshot(package_dir, task)
            for raw in list(task.get("source_files") or []):
                source = self.root / raw
                if source.is_file():
                    target = package_dir / "official_sources" / slug / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            for asset_root in (
                self.root / "data" / "social_drafts" / task["batch_date"] / slug / "assets",
                self.root / "data" / "production_article_drafts" / slug / "assets",
            ):
                if not asset_root.exists():
                    continue
                target_root = package_dir / "images" / slug
                target_root.mkdir(parents=True, exist_ok=True)
                for source in asset_root.iterdir():
                    if source.is_file() and source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                        shutil.copy2(source, target_root / source.name)
            if task["task_type"] == "WEBSITE_ADVANCED":
                series_history(package_dir, task)

    def copy_existing_article_snapshot(self, package_dir: Path, task: dict[str, Any]) -> None:
        """Supply a read-only current-article snapshot for in-place refresh tasks."""
        slug = _text(task.get("article_slug"))
        source_root = self.root / "data" / "production_article_drafts" / slug
        target_root = package_dir / "existing_article" / slug
        copied: list[str] = []
        for source_name, target_name in (
            ("article.md", "article.md"),
            ("metadata.json", "metadata.json"),
        ):
            source = source_root / source_name
            if source.is_file():
                target_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target_root / target_name)
                copied.append(target_name)
        if not copied:
            html_source = source_root / "index.html"
            if html_source.is_file():
                target_root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(html_source, target_root / "current_article.html")
                copied.append("current_article.html")
        _write_json(
            target_root / "refresh_contract.json",
            {
                "schema_version": "existing_article_refresh_contract_v1",
                "task_type": "UPDATE EXISTING ARTICLE",
                "existing_slug": slug,
                "preserve_slug": True,
                "create_new_url": False,
                "refresh_reason": list(task.get("refresh_reason") or []),
                "refresh_scope": list(task.get("refresh_scope") or []),
                "snapshot_files": copied,
                "human_approval_required": True,
            },
        )

    def copy_website_research_artifacts(self, package_dir: Path, slug: str) -> None:
        """Copy the prepared local research package that external writers need."""
        source_root = self.root / "data" / "research" / slug
        if not source_root.is_dir():
            return
        target_root = package_dir / "research" / slug
        copied: list[dict[str, Any]] = []
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            if source.suffix.lower() not in EXPORTABLE_RESEARCH_SUFFIXES:
                continue
            if SECRET_NAME_RE.search(source.name):
                continue
            if source.name == "AFFILIATE_OPPORTUNITY_BRIEF.json":
                continue
            try:
                relative = source.relative_to(source_root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(
                {
                    "path": f"research/{slug}/{relative.as_posix()}",
                    "source": _relative(self.root, source),
                    "sha256": _sha256(source),
                }
            )
        _write_json(
            target_root / "AFFILIATE_OPPORTUNITY_BRIEF.json",
            self.affiliate_brief_builder(self.root, slug),
        )
        if copied:
            _write_json(
                target_root / "research_inventory.json",
                {
                    "schema_version": "external_writer_research_inventory_v1",
                    "slug": slug,
                    "artifact_count": len(copied),
                    "artifacts": copied,
                },
            )

    def copy_series_history(self, package_dir: Path, task: dict[str, Any]) -> None:
        """Copy prior same-root drafts as read-only differentiation evidence."""
        root_topic_id = _text(task.get("root_topic_id"))
        current_slug = _text(task.get("article_slug"))
        if not root_topic_id:
            return
        draft_root = self.root / "data" / "production_article_drafts"
        matches: list[tuple[str, Path, dict[str, Any]]] = []
        if not draft_root.exists():
            return
        for metadata_path in draft_root.glob("*/metadata.json"):
            metadata = _read_json(metadata_path, {})
            if not isinstance(metadata, dict):
                continue
            prior_slug = _text(metadata.get("slug") or metadata_path.parent.name)
            if prior_slug == current_slug or _text(metadata.get("root_topic_id")) != root_topic_id:
                continue
            article_path = metadata_path.parent / "article.md"
            if article_path.is_file():
                matches.append((prior_slug, article_path, metadata))
        history_root = package_dir / "research" / current_slug / "series_history"
        for prior_slug, article_path, metadata in sorted(matches)[:7]:
            target = history_root / prior_slug
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(article_path, target / "article.md")
            safe_metadata = {
                key: metadata.get(key)
                for key in (
                    "slug",
                    "title",
                    "root_topic_id",
                    "series_id",
                    "batch_date",
                    "daily_angle",
                    "article_type",
                    "content_goal",
                    "search_intent",
                )
                if metadata.get(key) not in (None, "", [], {})
            }
            _write_json(target / "context.json", safe_metadata)

    def copy_guidance(self, package_dir: Path) -> None:
        guidance = (
            "AI_ONBOARDING.md",
            "PROJECT_GUIDE.md",
            "AI_WRITER_INSTRUCTIONS.md",
            "EDITORIAL_MEMORY.md",
            "WRITING_DNA.md",
            "STRUCTURE_DNA.md",
            "VOICE_DNA.md",
            "ARTICLE_FINGERPRINT.md",
            "DECISION_ENGINE.md",
            "STYLE_ENGINE.md",
            "ARTICLE_BLUEPRINT_ENGINE.md",
            "SELF_VALIDATION_ENGINE.md",
            "QUALITY_SCORE_ENGINE.md",
            "docs/editorial/CHATGPT_WRITER_READ_FIRST.md",
            "docs/editorial/UNIVERSAL_WRITING_STANDARD.md",
            "docs/editorial/WEBSITE_WRITING_STANDARD.md",
            "docs/editorial/CHATGPT_WEBSITE_WRITING_PLAYBOOK.md",
            "docs/editorial/SOCIAL_WRITING_STANDARD.md",
            "docs/editorial/CHATGPT_SOCIAL_WRITING_PLAYBOOK.md",
            "docs/editorial/PLATFORM_STYLE_MATRIX.md",
            "docs/editorial/ARTICLE_TYPE_MATRIX.md",
            "docs/editorial/CODEX_STYLE_FINGERPRINT.json",
            "docs/editorial/GOLD_STANDARD_INDEX.md",
            "docs/editorial/CHATGPT_EXECUTION_ORDER.md",
            "docs/editorial/SELF_REVIEW_CHECKLIST.md",
            "docs/editorial/STYLE_FINGERPRINT_V2.json",
            "docs/editorial/ARTICLE_TEMPLATE.md",
            "docs/editorial/QUALITY_CHECKLIST.md",
        )
        for raw in guidance:
            source = self.root / raw
            if source.is_file():
                target = package_dir / "templates" / raw.replace("/", "__")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        examples = self.root / "docs" / "examples"
        if examples.exists():
            for source in examples.glob("*.md"):
                target = package_dir / "examples" / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        self.copy_guidance_tree(
            self.root / "docs" / "editorial" / "editorial_brain",
            package_dir / "editorial_brain",
        )
        self.copy_guidance_tree(self.root / "editorial_memory", package_dir / "editorial_memory")
        self.copy_guidance_tree(self.root / "gold_library", package_dir / "gold_library")

    @staticmethod
    def copy_guidance_tree(source_root: Path, target_root: Path) -> None:
        if not source_root.exists():
            return
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in {".md", ".json", ".txt"}:
                continue
            target = target_root / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
