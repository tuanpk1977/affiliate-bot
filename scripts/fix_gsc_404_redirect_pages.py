from __future__ import annotations

import html
from pathlib import Path


REDIRECT_PAGES = {
    "/surfer-seo-pricing-2026/": "/surfer-seo-pricing/",
    "/vi/surfer-seo-pricing-2026/": "/surfer-seo-pricing/",
    "/review/codeium/": "/compare/github-copilot-vs-codeium/",
    "/vi/review/codeium/": "/vi/compare/github-copilot-vs-codeium/",
    "/vi/marketing-software-review/": "/vi/email-marketing-software-review/",
    "/vi/crm-alternatives/": "/vi/category/crm-tools/",
}

BASE_URL = "https://smileaireviewhub.com"


def site_url(path: str) -> str:
    return BASE_URL.rstrip("/") + "/" + path.strip("/") + "/"


def write_redirect_page(root: Path, source: str, target: str) -> Path:
    folder = root / source.strip("/")
    folder.mkdir(parents=True, exist_ok=True)
    safe_target = html.escape(target, quote=True)
    safe_canonical = html.escape(site_url(target), quote=True)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Redirecting</title>
<meta name="description" content="Redirecting to {safe_target}">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="{safe_canonical}">
<meta property="og:title" content="Redirecting">
<meta property="og:description" content="Redirecting to {safe_target}">
<meta property="og:url" content="{safe_canonical}">
<style>body{{font-family:Arial,sans-serif;max-width:760px;margin:64px auto;padding:0 20px;line-height:1.6;color:#152033}}.card{{border:1px solid #d8e1ec;border-radius:12px;padding:28px;background:#fff}}a{{color:#0f766e}}.btn{{display:inline-block;margin:8px 8px 0 0;padding:10px 14px;background:#0f766e;color:#fff;text-decoration:none;border-radius:8px}}</style>
</head>
<body>
<section class="card">
  <h1>Redirecting</h1>
  <p>This page has moved to <a href="{safe_target}">{safe_target}</a>.</p>
  <p><a class="btn" href="{safe_target}">Continue to the current page</a></p>
</section>
<script>window.location.replace("{safe_target}");</script>
</body>
</html>
"""
    output = folder / "index.html"
    output.write_text(page, encoding="utf-8")
    return output


def main() -> None:
    written = []
    for root in (Path("site_output"), Path("docs")):
        for source, target in REDIRECT_PAGES.items():
            written.append(write_redirect_page(root, source, target))
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
