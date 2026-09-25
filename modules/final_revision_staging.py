from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modules.content_growth_pipeline import (
    article_schema,
    breadcrumb_schema,
    build_editorial_metadata,
    html_shell,
    render_community_signals,
    render_editorial_byline,
)
from modules.revision_binding import binding_for_content


def render_metadata_complete_revision(
    source_html: str,
    *,
    title: str,
    description: str,
    canonical: str,
    topic: str,
    date_published: str,
    date_modified: str,
) -> tuple[str, dict[str, Any]]:
    """Re-render an approved editorial article with production metadata only."""
    match = re.search(r"<article\b[^>]*>(?P<body>.*?)</article>", source_html, flags=re.I | re.S)
    if not match:
        match = re.search(r"<main\b[^>]*>(?P<body>.*?)</main>", source_html, flags=re.I | re.S)
    if not match:
        match = re.search(r"<body\b[^>]*>(?P<body>.*?)</body>", source_html, flags=re.I | re.S)
    if not match:
        raise ValueError("Attempt source does not contain renderable article, main, or body content.")
    article_body = match.group("body").strip()
    disclosure_cards = len(re.findall(r'class=["\'][^"\']*\bdisclosure-card\b', article_body, flags=re.I))
    if disclosure_cards == 0:
        disclosure_pattern = re.compile(
            r"<p(?P<attrs>[^>]*)>(?P<body>\s*<strong>\s*Affiliate disclosure\s*:\s*</strong>.*?</p>)",
            flags=re.I | re.S,
        )
        article_body, disclosure_count = disclosure_pattern.subn(
            lambda item: f'<p class="disclosure-card"{item.group("attrs")}>{item.group("body")}',
            article_body,
            count=1,
        )
        disclosure_cards = disclosure_count
    if disclosure_cards > 1:
        raise ValueError("Attempt source contains more than one affiliate disclosure card.")

    def normalize_table(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        if re.search(r"\bclass\s*=", attrs, flags=re.I):
            attrs = re.sub(
                r"\bclass=(['\"])(.*?)\1",
                lambda value: f'class={value.group(1)}{value.group(2)} article-table{value.group(1)}'
                if "article-table" not in value.group(2).split()
                else value.group(0),
                attrs,
                count=1,
                flags=re.I,
            )
        else:
            attrs = f'{attrs} class="article-table"'
        return f'<div class="table-wrapper"><table{attrs}>{match.group("body")}</table></div>'

    if "table-wrapper" not in article_body:
        article_body = re.sub(
            r"<table(?P<attrs>[^>]*)>(?P<body>.*?)</table>",
            normalize_table,
            article_body,
            flags=re.I | re.S,
        )

    def normalize_cta(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        if re.search(r"\bclass\s*=", attrs, flags=re.I):
            attrs = re.sub(
                r"\bclass=(['\"])(.*?)\1",
                lambda value: f'class={value.group(1)}{value.group(2)} cta-button{value.group(1)}'
                if "cta-button" not in value.group(2).split()
                else value.group(0),
                attrs,
                count=1,
                flags=re.I,
            )
        else:
            attrs = f'{attrs} class="cta-button"'
        return f'<a{attrs}>{match.group("label")}</a>'

    article_body = re.sub(
        r"<a(?P<attrs>[^>]*)>(?P<label>\s*(?:Visit official website|Check current pricing)\s*)</a>",
        normalize_cta,
        article_body,
        flags=re.I | re.S,
    )

    editorial = build_editorial_metadata(
        reviewed_by="Smile AI Review Hub editorial team",
        last_updated=date_modified,
    )
    schema = article_schema(title, description, canonical, topic, editorial)
    schema["datePublished"] = date_published
    schema["dateModified"] = date_modified
    byline = "" if "author-card" in article_body else render_editorial_byline(editorial).strip()
    community_signals = "" if "community-signals" in article_body else render_community_signals().strip()
    body = (
        '<main class="article-layout"><article class="article-container">\n'
        f"{article_body}\n{community_signals}\n{byline}\n"
        "</article></main>"
    )
    rendered = html_shell(
        title,
        description,
        canonical,
        body,
        [schema, breadcrumb_schema(title, canonical)],
    )
    return rendered, {"editorial": editorial, "article_schema": schema}


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_stage_revision(
    *,
    attempt_dir: Path,
    production_dir: Path,
    backup_dir: Path,
) -> dict[str, Any]:
    """Back up the current draft once, then atomically stage exact attempt bytes."""
    required = ("article.md", "index.html")
    for name in required:
        if not (attempt_dir / name).is_file():
            raise FileNotFoundError(f"Missing attempt artifact: {attempt_dir / name}")
    if backup_dir.exists():
        raise FileExistsError(f"Refusing to overwrite staging backup: {backup_dir}")
    if not production_dir.is_dir():
        raise FileNotFoundError(f"Missing production draft directory: {production_dir}")

    shutil.copytree(production_dir, backup_dir)
    for name in required:
        _atomic_write_bytes(production_dir / name, (attempt_dir / name).read_bytes())

    staged_html = (production_dir / "index.html").read_text(encoding="utf-8")
    expected_html = (attempt_dir / "index.html").read_text(encoding="utf-8")
    staged_binding = binding_for_content(staged_html)
    expected_binding = binding_for_content(expected_html)
    if staged_binding != expected_binding:
        raise RuntimeError("Atomic staging verification failed: production bytes differ from attempt bytes.")
    return {
        "production_dir": str(production_dir),
        "backup_dir": str(backup_dir),
        "staged_revision_id": staged_binding["revision_id"],
        "staged_content_hash": staged_binding["content_hash"],
        "exact_bytes_match": True,
    }


def prepare_production_ready_review_revision(
    *,
    production_dir: Path,
    revision_root: Path,
) -> dict[str, Any]:
    """Stage a complete production-layout revision before human approval.

    This is deliberately a pre-approval operation.  It preserves the prior
    draft as evidence and never changes approval or publication records.
    """
    source_html_path = production_dir / "index.html"
    source_markdown_path = production_dir / "article.md"
    metadata_path = production_dir / "metadata.json"
    for path in (source_html_path, source_markdown_path, metadata_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing production draft artifact: {path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rendered, render_metadata = render_metadata_complete_revision(
        source_html_path.read_text(encoding="utf-8"),
        title=str(metadata.get("title") or "").strip(),
        description=str(metadata.get("description") or "").strip(),
        canonical=str(metadata.get("canonical_url") or metadata.get("url") or "").strip(),
        topic=str(metadata.get("topic") or metadata.get("title") or "").strip(),
        date_published=str(metadata.get("datePublished") or "").strip(),
        date_modified=str(metadata.get("dateModified") or datetime.now(UTC).isoformat()).strip(),
    )
    binding = binding_for_content(rendered)
    attempt_dir = revision_root / binding["content_hash"]
    attempt_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes(attempt_dir / "index.html", rendered.encode("utf-8"))
    _atomic_write_bytes(attempt_dir / "article.md", source_markdown_path.read_bytes())
    write_json_atomic(
        attempt_dir / "revision_manifest.json",
        {
            "schema_version": "production_ready_review_revision_v1",
            "created_at": datetime.now(UTC).isoformat(),
            "source_revision": binding_for_content(source_html_path.read_text(encoding="utf-8")),
            "staged_revision": binding,
            "render_metadata": render_metadata,
            "approval_changed": False,
            "published": False,
        },
    )
    backup_dir = attempt_dir / "production_draft_backup"
    if backup_dir.exists():
        current = binding_for_content(source_html_path.read_text(encoding="utf-8"))
        if current == binding:
            return {
                "production_dir": str(production_dir),
                "attempt_dir": str(attempt_dir),
                "staged_revision_id": binding["revision_id"],
                "staged_content_hash": binding["content_hash"],
                "exact_bytes_match": True,
                "already_staged": True,
            }
        raise FileExistsError(f"Refusing to overwrite staging evidence: {backup_dir}")
    staged = atomic_stage_revision(
        attempt_dir=attempt_dir,
        production_dir=production_dir,
        backup_dir=backup_dir,
    )
    return {**staged, "attempt_dir": str(attempt_dir), "already_staged": False}


def write_json_atomic(path: Path, payload: Any) -> None:
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write_bytes(path, encoded)
