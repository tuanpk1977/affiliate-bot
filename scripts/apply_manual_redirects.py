from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.site_builder import write_static_redirect_pages


SITE = ROOT / "site_output"
MANUAL_REDIRECTS = {
    "/semrush-vs-ahrefs-2026/": "/compare/semrush-vs-ahrefs/",
    "/semrush-vs-ahrefs-2026": "/compare/semrush-vs-ahrefs/",
    "/vi/semrush-vs-ahrefs-2026/": "/vi/compare/semrush-vs-ahrefs/",
    "/vi/semrush-vs-ahrefs-2026": "/vi/compare/semrush-vs-ahrefs/",
}


def main() -> None:
    redirects_path = SITE / "_redirects"
    lines = redirects_path.read_text(encoding="utf-8").splitlines() if redirects_path.exists() else []
    existing_sources = {line.split()[0] for line in lines if line.strip() and not line.lstrip().startswith("#")}
    for source, target in MANUAL_REDIRECTS.items():
        if source not in existing_sources:
            lines.append(f"{source} {target} 301")
    redirects_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_static_redirect_pages(SITE, MANUAL_REDIRECTS)
    print(f"Applied {len(MANUAL_REDIRECTS)} redirect rules.")


if __name__ == "__main__":
    main()
