from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html import unescape
from pathlib import Path
import json
import re
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


BASE_URL = "https://smileaireviewhub.com"
HOST = "smileaireviewhub.com"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
JSON_LD_RE = re.compile(
    r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
    flags=re.I | re.S,
)
CANONICAL_RE = re.compile(
    r"<link\b(?=[^>]*\brel=['\"]canonical['\"])(?=[^>]*\bhref=['\"]([^'\"]+)['\"])[^>]*>",
    flags=re.I,
)
HREF_RE = re.compile(r"\bhref=['\"]([^'\"]+)['\"]", flags=re.I)
VALID_AUTHOR_TYPES = {"Person", "Organization"}


@dataclass
class PageValidation:
    url: str
    file: str
    canonical: str = ""
    schema_types: list[str] = field(default_factory=list)
    internal_links: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class SitemapValidation:
    path: str
    total_urls: int = 0
    duplicate_urls: list[str] = field(default_factory=list)
    published_urls_missing: list[str] = field(default_factory=list)
    invalid_lastmod: list[str] = field(default_factory=list)
    canonical_mismatches: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.errors
            or self.duplicate_urls
            or self.published_urls_missing
            or self.invalid_lastmod
            or self.canonical_mismatches
        )


@dataclass
class BatchValidation:
    published_urls: list[str]
    sitemap: SitemapValidation
    pages: list[PageValidation]

    @property
    def ok(self) -> bool:
        return self.sitemap.ok and all(page.ok for page in self.pages)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "published_urls": self.published_urls,
            "sitemap": {**asdict(self.sitemap), "ok": self.sitemap.ok},
            "pages": [{**asdict(page), "ok": page.ok} for page in self.pages],
        }


def normalize_public_url(value: str) -> str:
    value = str(value or "").strip().split("#", 1)[0]
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != HOST:
        return ""
    if parsed.query:
        return ""
    path = parsed.path or "/"
    if path != "/" and not path.endswith("/"):
        path += "/"
    return f"{BASE_URL}{path}"


def url_to_file(url: str, publish_root: Path) -> Path:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path == "/":
        return publish_root / "index.html"
    return publish_root / path.strip("/") / "index.html"


def schema_nodes(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_nodes(child)


def parse_json_ld(source: str) -> tuple[list[dict], list[str]]:
    payloads: list[dict] = []
    errors: list[str] = []
    for index, match in enumerate(JSON_LD_RE.finditer(source), start=1):
        try:
            payload = json.loads(unescape(match.group(1)))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON-LD block {index}: {exc}")
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        elif isinstance(payload, list):
            payloads.extend(item for item in payload if isinstance(item, dict))
    return payloads, errors


def validate_author(node: dict, label: str) -> list[str]:
    author = node.get("author")
    if not isinstance(author, dict):
        return [f"{label}.author must be an object"]
    errors: list[str] = []
    if author.get("@type") not in VALID_AUTHOR_TYPES:
        errors.append(f"{label}.author @type must be Person or Organization")
    if not str(author.get("name") or "").strip():
        errors.append(f"{label}.author.name is missing")
    return errors


def validate_schema_payloads(payloads: list[dict]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    types: list[str] = []
    for payload in payloads:
        for node in schema_nodes(payload):
            schema_type = node.get("@type")
            if isinstance(schema_type, str):
                types.append(schema_type)
            if schema_type in {"Article", "BlogPosting", "Review"}:
                errors.extend(validate_author(node, schema_type))
            if schema_type == "Review":
                item = node.get("itemReviewed")
                rating = node.get("reviewRating")
                if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                    errors.append("Review.itemReviewed.name is missing")
                if not isinstance(rating, dict):
                    errors.append("Review.reviewRating is missing")
                else:
                    try:
                        float(rating.get("ratingValue"))
                    except (TypeError, ValueError):
                        errors.append("Review.reviewRating.ratingValue is invalid")
            if schema_type == "FAQPage":
                entities = node.get("mainEntity")
                if not isinstance(entities, list) or not entities:
                    errors.append("FAQPage.mainEntity is missing")
                else:
                    for entity in entities:
                        if not isinstance(entity, dict) or not str(entity.get("name") or "").strip():
                            errors.append("FAQPage contains a question without name")
                        answer = entity.get("acceptedAnswer") if isinstance(entity, dict) else None
                        if not isinstance(answer, dict) or not str(answer.get("text") or "").strip():
                            errors.append("FAQPage contains a question without acceptedAnswer.text")
            if schema_type == "BreadcrumbList":
                items = node.get("itemListElement")
                if not isinstance(items, list) or not items:
                    errors.append("BreadcrumbList.itemListElement is missing")
    return sorted(set(types)), errors


def validate_page(url: str, publish_root: Path) -> PageValidation:
    target = url_to_file(url, publish_root)
    result = PageValidation(url=url, file=str(target))
    if not target.exists():
        result.errors.append("published HTML file is missing")
        return result

    source = target.read_text(encoding="utf-8", errors="replace")
    canonicals = CANONICAL_RE.findall(source)
    if len(canonicals) != 1:
        result.errors.append(f"canonical count must be 1, found {len(canonicals)}")
    else:
        result.canonical = normalize_public_url(canonicals[0])
        if result.canonical != url:
            result.errors.append(f"canonical mismatch: {canonicals[0]} != {url}")

    payloads, schema_errors = parse_json_ld(source)
    result.errors.extend(schema_errors)
    result.schema_types, schema_errors = validate_schema_payloads(payloads)
    result.errors.extend(schema_errors)

    if not any(item in result.schema_types for item in ("Article", "BlogPosting")):
        result.errors.append("Article or BlogPosting schema is missing")
    for required in ("BreadcrumbList",):
        if required not in result.schema_types:
            result.errors.append(f"{required} schema is missing")
    if ("<details" in source.lower() or "frequently asked questions" in source.lower()) and "FAQPage" not in result.schema_types:
        result.errors.append("visible FAQ exists but FAQPage schema is missing")

    internal_links = set()
    for href in HREF_RE.findall(source):
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != HOST:
            continue
        if not href.startswith("/") and not parsed.netloc:
            continue
        path = parsed.path or "/"
        if path.startswith(("/assets/", "/go/")):
            continue
        internal_links.add(path)
        candidate = url_to_file(f"{BASE_URL}{path}", publish_root)
        if not candidate.exists() and path not in {"/sitemap.xml", "/robots.txt", "/rss.xml", "/llms.txt"}:
            result.errors.append(f"broken internal link: {href}")
    result.internal_links = len(internal_links)
    return result


def parse_sitemap(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    errors: list[str] = []
    if not path.exists():
        return [], [f"sitemap is missing: {path}"]
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="strict"))
    except (ET.ParseError, UnicodeError, OSError) as exc:
        return [], [f"sitemap XML is invalid: {exc}"]
    if root.tag != f"{SITEMAP_NS}urlset":
        errors.append(f"unexpected sitemap root: {root.tag}")
    rows: list[tuple[str, str]] = []
    for item in root.findall(f"{SITEMAP_NS}url"):
        loc = item.find(f"{SITEMAP_NS}loc")
        lastmod = item.find(f"{SITEMAP_NS}lastmod")
        rows.append(
            (
                str(loc.text or "").strip() if loc is not None else "",
                str(lastmod.text or "").strip() if lastmod is not None else "",
            )
        )
    return rows, errors


def validate_sitemap(
    sitemap_path: Path,
    publish_root: Path,
    published_urls: Iterable[str],
    *,
    expected_lastmod: date | None = None,
    validate_all_canonicals: bool = True,
) -> SitemapValidation:
    result = SitemapValidation(path=str(sitemap_path))
    rows, parse_errors = parse_sitemap(sitemap_path)
    result.errors.extend(parse_errors)
    result.total_urls = len(rows)
    if not rows:
        result.errors.append("sitemap contains no URLs")
        return result

    locations = [url for url, _ in rows]
    seen: set[str] = set()
    for url in locations:
        if url in seen and url not in result.duplicate_urls:
            result.duplicate_urls.append(url)
        seen.add(url)
        if normalize_public_url(url) != url:
            result.errors.append(f"non-canonical or invalid sitemap URL: {url}")

    row_map = {url: lastmod for url, lastmod in rows}
    normalized_published = [normalize_public_url(url) for url in published_urls]
    normalized_published = [url for url in normalized_published if url]
    result.published_urls_missing = [url for url in normalized_published if url not in row_map]

    check_lastmod_urls = normalized_published or locations
    for url in check_lastmod_urls:
        value = row_map.get(url, "")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            result.invalid_lastmod.append(f"{url}: {value or '(missing)'}")
            continue
        if expected_lastmod is not None and parsed < expected_lastmod:
            result.invalid_lastmod.append(f"{url}: {value} is older than {expected_lastmod.isoformat()}")

    canonical_urls = locations if validate_all_canonicals else normalized_published
    for url in canonical_urls:
        target = url_to_file(url, publish_root)
        if not target.exists():
            result.canonical_mismatches.append(f"{url}: local page missing")
            continue
        source = target.read_text(encoding="utf-8", errors="replace")
        canonicals = CANONICAL_RE.findall(source)
        if len(canonicals) != 1 or normalize_public_url(canonicals[0]) != url:
            result.canonical_mismatches.append(f"{url}: canonical={canonicals!r}")
    return result


def validate_batch(
    publish_root: Path,
    sitemap_path: Path,
    published_urls: Iterable[str],
    *,
    expected_lastmod: date | None = None,
    validate_all_canonicals: bool = True,
) -> BatchValidation:
    urls = []
    seen = set()
    for value in published_urls:
        normalized = normalize_public_url(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    sitemap = validate_sitemap(
        sitemap_path,
        publish_root,
        urls,
        expected_lastmod=expected_lastmod,
        validate_all_canonicals=validate_all_canonicals,
    )
    pages = [validate_page(url, publish_root) for url in urls]
    return BatchValidation(published_urls=urls, sitemap=sitemap, pages=pages)


def fetch_url(url: str, timeout: int = 30) -> tuple[int, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "SmileAIReviewHub-PublishingHealth/1.0",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), ""
    except (URLError, TimeoutError, OSError):
        return 0, ""


def wait_for_live_urls(
    urls: Iterable[str],
    *,
    timeout_seconds: int = 600,
    interval_seconds: int = 15,
) -> dict[str, int]:
    normalized = [normalize_public_url(url) for url in urls]
    normalized = [url for url in normalized if url]
    statuses: dict[str, int] = {url: 0 for url in normalized}
    deadline = time.time() + max(0, timeout_seconds)
    while time.time() <= deadline:
        for url in normalized:
            if statuses[url] == 200:
                continue
            status, source = fetch_url(f"{url}?deployment_check={int(time.time())}")
            canonical = CANONICAL_RE.findall(source)
            if status == 200 and len(canonical) == 1 and normalize_public_url(canonical[0]) == url:
                statuses[url] = 200
            else:
                statuses[url] = status
        if statuses and all(status == 200 for status in statuses.values()):
            return statuses
        time.sleep(max(1, interval_seconds))
    return statuses


def validate_live_sitemap(sitemap_url: str, published_urls: Iterable[str]) -> tuple[bool, int, list[str]]:
    status, source = fetch_url(f"{sitemap_url}?deployment_check={int(time.time())}")
    if status != 200:
        return False, 0, [f"live sitemap returned HTTP {status}"]
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        return False, 0, [f"live sitemap XML is invalid: {exc}"]
    locations = [
        str(node.text or "").strip()
        for node in root.findall(f".//{SITEMAP_NS}loc")
        if node.text
    ]
    errors: list[str] = []
    if len(locations) != len(set(locations)):
        errors.append("live sitemap contains duplicate URLs")
    for url in published_urls:
        normalized = normalize_public_url(url)
        if normalized and normalized not in locations:
            errors.append(f"live sitemap missing {normalized}")
    return not errors, len(locations), errors
