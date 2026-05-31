from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from modules.sitemap_generator import generate_sitemap, scan_index_pages


def main() -> None:
    path = generate_sitemap(settings.site_output_dir, settings.base_site_url or settings.site_domain)
    urls = scan_index_pages(settings.site_output_dir, (settings.base_site_url or settings.site_domain or "https://smileaireviewhub.com").rstrip("/"))
    print(f"Generated {path}")
    print(f"URLs: {len(urls)}")


if __name__ == "__main__":
    main()
