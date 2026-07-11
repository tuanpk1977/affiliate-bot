from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_site import generate_sitemap, sync_article_visuals, sync_public_article_assets  # noqa: E402
from config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build shared assets and sitemap for selected existing article outputs.")
    parser.add_argument("--slug", action="append", required=True)
    args = parser.parse_args()
    missing = [slug for slug in args.slug if not (settings.site_output_dir / slug / "index.html").exists()]
    if missing:
        print(json.dumps({"status": "failed", "missing": missing}), file=sys.stderr)
        return 2
    result = {
        "status": "completed",
        "mode": "targeted",
        "slugs": args.slug,
        "article_visuals_changed": sync_article_visuals(),
        "public_article_assets_changed": sync_public_article_assets(),
        "sitemap": str(generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
