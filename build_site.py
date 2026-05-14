from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path

from config import settings
from modules.content_approval import publish_static_draft
from modules.sitemap_generator import generate_sitemap


def copy_if_changed(source: Path, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and filecmp.cmp(source, target, shallow=False):
        return False
    shutil.copy2(source, target)
    return True


def sync_published_pages() -> dict[str, int]:
    source_root = settings.data_dir / "published_static_pages"
    changed = 0
    scanned = 0
    if not source_root.exists():
        return {"scanned": 0, "changed": 0}
    for source in sorted(source_root.glob("*/index.html")):
        scanned += 1
        slug = source.parent.name
        target = settings.site_output_dir / slug / "index.html"
        if copy_if_changed(source, target):
            changed += 1
    return {"scanned": scanned, "changed": changed}


def incremental_build() -> dict[str, object]:
    settings.site_output_dir.mkdir(parents=True, exist_ok=True)
    sync_stats = sync_published_pages()
    sitemap_path = generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    return {
        "mode": "incremental",
        "published_pages_scanned": sync_stats["scanned"],
        "published_pages_changed": sync_stats["changed"],
        "sitemap": str(sitemap_path),
    }


def full_build() -> dict[str, object]:
    from main import main

    main()
    return {"mode": "full", "site_output": str(settings.site_output_dir)}


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Build AI Tool Review Hub static output.")
    parser.add_argument("--full", action="store_true", help="Run the full legacy pipeline.")
    parser.add_argument("--publish-draft", default="", help="Publish one Approved draft id before syncing.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting an existing slug when publishing a draft.")
    args = parser.parse_args()

    if args.full:
        result = full_build()
    else:
        if args.publish_draft:
            ok, message = publish_static_draft(args.publish_draft, overwrite=args.overwrite)
            print(f"publish_draft={args.publish_draft} ok={ok} message={message}")
            if not ok:
                raise SystemExit(1)
        result = incremental_build()

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main_cli()
