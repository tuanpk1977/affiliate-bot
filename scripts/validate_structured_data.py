from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site_output"
BASE = "https://smileaireviewhub.com"


def main() -> int:
    errors: list[str] = []
    sitemap = sitemap_urls(errors)
    checked = 0
    for page in sorted(SITE.rglob("index.html")):
        source = page.read_text(encoding="utf-8", errors="ignore")
        rel = page.relative_to(SITE).as_posix()
        url = BASE + ("/" if rel == "index.html" else "/" + rel[: -len("index.html")])
        noindex = "noindex" in robots(source)
        payloads = json_ld_payloads(source, rel, errors)
        if noindex or rel.startswith("go/"):
            if payloads:
                errors.append(f"{rel}: excluded page contains JSON-LD")
            continue
        checked += 1
        canonical = canonical_url(source)
        if canonical != url:
            errors.append(f"{rel}: canonical mismatch ({canonical})")
        top_types = [str(payload.get("@type", "")) for payload in payloads]
        duplicates = [name for name, count in Counter(top_types).items() if name and count > 1]
        if duplicates:
            errors.append(f"{rel}: duplicate top-level schema types {duplicates}")
        for required in ("Organization", "WebSite"):
            if required not in top_types:
                errors.append(f"{rel}: missing {required}")
        if is_review(rel):
            require_types(errors, rel, top_types, ("Article", "BreadcrumbList", "SoftwareApplication", "Review"))
        if is_comparison(rel):
            require_types(errors, rel, top_types, ("Article", "BreadcrumbList", "ItemList"))
        if rel.startswith("vi/"):
            for payload in payloads:
                if payload.get("@type") in {"Article", "Review", "CollectionPage"} and payload.get("inLanguage") != "vi-VN":
                    errors.append(f"{rel}: {payload.get('@type')} language is not vi-VN")
        for payload in payloads:
            serialized = json.dumps(payload, ensure_ascii=False)
            if "reviewRating" in serialized or "aggregateRating" in serialized or '"offers"' in serialized:
                errors.append(f"{rel}: unsupported rating/offer schema found")
            for schema_url in schema_urls(payload):
                parsed = urlparse(schema_url)
                if parsed.netloc == "smileaireviewhub.com" and (parsed.query or parsed.path.startswith("/go/")):
                    errors.append(f"{rel}: dirty internal schema URL {schema_url}")
        if url in sitemap and noindex:
            errors.append(f"{rel}: noindex page appears in sitemap")

    if errors:
        print(f"Structured data validation FAILED: {len(errors)} issue(s)")
        for error in errors[:250]:
            print(f"- {error}")
        return 1
    print(f"Structured data validation OK: checked={checked} sitemap={len(sitemap)}")
    return 0


def json_ld_payloads(source: str, rel: str, errors: list[str]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for index, raw in enumerate(
        re.findall(r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", source, flags=re.I | re.S),
        start=1,
    ):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{rel}: invalid JSON-LD block {index}: {exc}")
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def sitemap_urls(errors: list[str]) -> set[str]:
    path = SITE / "sitemap.xml"
    if not path.exists():
        errors.append("missing sitemap.xml")
        return set()
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    return {node.text.strip() for node in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc") if node.text}


def schema_urls(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "@id", "mainEntityOfPage", "item", "contentUrl", "embedUrl"} and isinstance(item, str):
                yield item
            yield from schema_urls(item)
    elif isinstance(value, list):
        for item in value:
            yield from schema_urls(item)


def require_types(errors: list[str], rel: str, actual: list[str], required: tuple[str, ...]) -> None:
    for schema_type in required:
        if schema_type not in actual:
            errors.append(f"{rel}: missing {schema_type}")


def is_review(rel: str) -> bool:
    clean = rel[3:] if rel.startswith("vi/") else rel
    return (clean.startswith("reviews/") or clean.startswith("review/")) and clean.count("/") >= 2


def is_comparison(rel: str) -> bool:
    clean = rel[3:] if rel.startswith("vi/") else rel
    return (clean.startswith("compare/") or clean.startswith("comparisons/")) and clean.count("/") >= 2


def robots(source: str) -> str:
    match = re.search(r"<meta\b(?=[^>]*name=['\"]robots['\"])(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*>", source, flags=re.I)
    return match.group(1).lower() if match else ""


def canonical_url(source: str) -> str:
    match = re.search(r"<link\b(?=[^>]*rel=['\"]canonical['\"])(?=[^>]*href=['\"]([^'\"]+)['\"])[^>]*>", source, flags=re.I)
    return match.group(1).strip() if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
