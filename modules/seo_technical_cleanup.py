from __future__ import annotations

import html as html_lib
import re
from pathlib import Path
from urllib.parse import urlparse

from modules.indexing_policy import INDEXABLE_ROBOTS_META, REDIRECT_ROBOTS_META


BASE_URL = "https://smileaireviewhub.com"
GSC_LEGACY_REDIRECTS = {
    "/surfer-seo-pricing-2026/": "/surfer-seo-pricing/",
    "/surfer-seo-pricing-2026": "/surfer-seo-pricing/",
    "/vi/surfer-seo-pricing-2026/": "/surfer-seo-pricing/",
    "/vi/surfer-seo-pricing-2026": "/surfer-seo-pricing/",
    "/review/codeium/": "/compare/github-copilot-vs-codeium/",
    "/review/codeium": "/compare/github-copilot-vs-codeium/",
    "/vi/review/codeium/": "/vi/compare/github-copilot-vs-codeium/",
    "/vi/review/codeium": "/vi/compare/github-copilot-vs-codeium/",
    "/vi/marketing-software-review/": "/vi/email-marketing-software-review/",
    "/vi/marketing-software-review": "/vi/email-marketing-software-review/",
    "/vi/crm-alternatives/": "/vi/category/crm-tools/",
    "/vi/crm-alternatives": "/vi/category/crm-tools/",
}
RETIRED_GSC_LEGACY_REDIRECT_SOURCES = {
}


def promote_public_review_pages(output: Path) -> dict[str, int]:
    reviews_root = output / "reviews"
    if not reviews_root.exists():
        return {"review_pages": 0, "review_pages_changed": 0}

    scanned = 0
    changed = 0
    for page in sorted(reviews_root.glob("*/index.html")):
        scanned += 1
        source = page.read_text(encoding="utf-8", errors="ignore")
        target_path = redirect_target(source)
        if not target_path:
            continue
        target = output / target_path.strip("/") / "index.html"
        if not target.exists():
            continue

        review_path = "/" + page.parent.relative_to(output).as_posix().strip("/") + "/"
        target_url = f"{BASE_URL}{target_path}"
        review_url = f"{BASE_URL}{review_path}"
        content = target.read_text(encoding="utf-8", errors="ignore")
        content = remove_meta_refresh(content)
        content = ensure_robots(content, INDEXABLE_ROBOTS_META)
        content = replace_canonical(content, review_url)
        content = replace_meta_url(content, "og:url", review_url)
        content = content.replace(target_url, review_url)
        page.write_text(content, encoding="utf-8")
        changed += 1
    return {"review_pages": scanned, "review_pages_changed": changed}


def configure_cloudflare_redirects(output: Path) -> dict[str, int]:
    redirects_path = output / "_redirects"
    existing = redirects_path.read_text(encoding="utf-8", errors="ignore").splitlines() if redirects_path.exists() else []
    kept: list[str] = []
    seen: set[str] = set()
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            kept.append(line)
            continue
        source = stripped.split()[0]
        if source in RETIRED_GSC_LEGACY_REDIRECT_SOURCES:
            continue
        if source.startswith("/reviews/") or source.startswith("/vi/reviews/") or source.startswith("/go/"):
            continue
        if source not in seen:
            kept.append(line)
            seen.add(source)

    go_rules = 0
    for page in sorted((output / "go").glob("*/index.html")) if (output / "go").exists() else []:
        content = page.read_text(encoding="utf-8", errors="ignore")
        target = outbound_target(content)
        if not target:
            continue
        content = remove_meta_refresh(content)
        content = ensure_robots(content, REDIRECT_ROBOTS_META)
        page.write_text(content, encoding="utf-8")
        slug = page.parent.name
        for source in (f"/go/{slug}/", f"/go/{slug}"):
            if source not in seen:
                kept.append(f"{source} {target} 302")
                seen.add(source)
                go_rules += 1

    for source, target in GSC_LEGACY_REDIRECTS.items():
        if source not in seen:
            kept.append(f"{source} {target} 301")
            seen.add(source)

    redirects_path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    return {"cloudflare_go_redirect_rules": go_rules}


def redirect_target(source: str) -> str:
    match = re.search(r"<meta\b[^>]*http-equiv=['\"]?refresh['\"]?[^>]*content=['\"][^;]+;\s*url=([^'\"]+)['\"]", source, flags=re.I)
    if not match:
        match = re.search(r"window\.location\.replace\(['\"]([^'\"]+)['\"]\)", source, flags=re.I)
    if not match:
        return ""
    target = html_lib.unescape(match.group(1)).strip()
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return ""
    path = parsed.path
    return path if path.endswith("/") else f"{path}/"


def outbound_target(source: str) -> str:
    matches = re.findall(r"<a\b[^>]*\brel=['\"][^'\"]*sponsored[^'\"]*['\"][^>]*\bhref=['\"]([^'\"]+)['\"]", source, flags=re.I)
    if not matches:
        matches = re.findall(r"<a\b[^>]*\bhref=['\"](https?://[^'\"]+)['\"]", source, flags=re.I)
    for value in matches:
        target = html_lib.unescape(value).strip()
        if target.startswith(("https://", "http://")):
            return target
    return ""


def remove_meta_refresh(source: str) -> str:
    return re.sub(r"\s*<meta\b[^>]*http-equiv=['\"]?refresh['\"]?[^>]*>\s*", "\n", source, flags=re.I)


def ensure_robots(source: str, value: str) -> str:
    tag = f'<meta name="robots" content="{value}">'
    pattern = r"<meta\b(?=[^>]*\bname=['\"]robots['\"])[^>]*>"
    if re.search(pattern, source, flags=re.I):
        inserted = False

        def replace(match: re.Match[str]) -> str:
            nonlocal inserted
            if inserted:
                return ""
            inserted = True
            return tag

        return re.sub(pattern, replace, source, flags=re.I)
    return source.replace("</head>", f"{tag}\n</head>", 1)


def replace_canonical(source: str, url: str) -> str:
    tag = f'<link rel="canonical" href="{html_lib.escape(url, quote=True)}">'
    pattern = r"<link\b(?=[^>]*\brel=['\"]canonical['\"])[^>]*>"
    if re.search(pattern, source, flags=re.I):
        return re.sub(pattern, tag, source, count=1, flags=re.I)
    return source.replace("</head>", f"{tag}\n</head>", 1)


def replace_meta_url(source: str, property_name: str, url: str) -> str:
    pattern = rf"(<meta\b(?=[^>]*\bproperty=['\"]{re.escape(property_name)}['\"])[^>]*\bcontent=['\"])[^'\"]*(['\"][^>]*>)"
    if re.search(pattern, source, flags=re.I):
        return re.sub(pattern, rf"\g<1>{html_lib.escape(url, quote=True)}\g<2>", source, count=1, flags=re.I)
    return source


def apply_technical_seo_cleanup(output: Path) -> dict[str, int]:
    stats = promote_public_review_pages(output)
    stats.update(configure_cloudflare_redirects(output))
    return stats
