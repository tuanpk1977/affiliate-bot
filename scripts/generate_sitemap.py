from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from modules.sitemap_generator import generate_sitemap, scan_index_pages


def read_updated_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload if isinstance(payload, list) else payload.get("articles", payload.get("rows", []))
    else:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    return [
        str(row.get("published_url") or row.get("article_url") or row.get("url") or "").strip()
        for row in rows
        if isinstance(row, dict)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a sitemap from the selected static publish root.")
    parser.add_argument(
        "--publish-root",
        default=str(settings.site_output_dir),
        help="Static site directory to scan. Use docs for the active Cloudflare Pages output.",
    )
    parser.add_argument(
        "--mirror-to",
        default="",
        help="Optional second directory that should receive the validated sitemap.xml.",
    )
    parser.add_argument(
        "--updated-urls-file",
        default="",
        help="CSV/JSON report containing URLs whose lastmod should be set to today.",
    )
    args = parser.parse_args()

    publish_root = Path(args.publish_root)
    base_url = (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/")
    updated_urls = read_updated_urls(Path(args.updated_urls_file)) if args.updated_urls_file else []
    path = generate_sitemap(publish_root, base_url, updated_urls=updated_urls)
    urls = scan_index_pages(publish_root, base_url)
    if args.mirror_to:
        mirror = Path(args.mirror_to)
        mirror.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, mirror / "sitemap.xml")
    print(f"Generated {path}")
    print(f"URLs: {len(urls)}")
    if args.mirror_to:
        print(f"Mirrored sitemap to {Path(args.mirror_to) / 'sitemap.xml'}")


if __name__ == "__main__":
    main()
