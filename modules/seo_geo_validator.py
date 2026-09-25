from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

from modules.indexing_policy import should_include_in_sitemap


STATUS_ORDER = {"PASS": 0, "INFO": 0, "WARNING": 1, "BLOCKED": 2}
ARTICLE_SCHEMA_TYPES = {"Article", "BlogPosting", "NewsArticle"}
KNOWN_AI_CRAWLERS = {
    "OAI-SearchBot": ("search", "Preserve the owner-selected search visibility policy."),
    "ChatGPT-User": ("user_fetch", "Preserve explicit user-requested retrieval control."),
    "PerplexityBot": ("search", "Preserve the owner-selected answer-engine policy."),
    "ClaudeBot": ("ai_crawler", "Review periodically; this is an owner policy decision."),
    "Google-Extended": ("ai_training_control", "Keep separate from Googlebot search crawling."),
    "GPTBot": ("ai_training", "Choose explicitly if the owner wants separate training-crawler control."),
    "CCBot": ("dataset_crawler", "Choose explicitly if the owner wants separate dataset-crawler control."),
    "anthropic-ai": ("ai_training", "Choose explicitly if the owner wants separate training-crawler control."),
    "Bytespider": ("ai_training", "Choose explicitly if the owner wants separate training-crawler control."),
}
GEO_ADVISORY_PATTERNS = (
    re.compile(r"FAQ\s+schema.{0,80}(?:makes?|causes?|guarantees?|helps?).{0,50}(?:ChatGPT|AI\s+search).{0,40}rank", re.I),
    re.compile(r"AI(?:-specific)?\s+robots\.txt.{0,80}(?:guarantees?|ensures?).{0,50}(?:visibility|ranking|citations?)", re.I),
    re.compile(r"\b\d{1,3}(?:\.\d+)?%\s+of\s+AI\s+crawlers?.{0,80}(?:prefer|rank|cite|use)", re.I),
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _normalize_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if not path.endswith("/") and not Path(path).suffix:
        path += "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _schema_nodes(value: object):
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _schema_nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _schema_nodes(item)


class CandidateHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.semantic_counts = {tag: 0 for tag in ("main", "article", "section", "nav", "footer", "table", "ul", "ol")}
        self.headings: list[dict[str, Any]] = []
        self._heading_level = 0
        self._heading_parts: list[str] = []
        self.canonicals: list[str] = []
        self.robots_meta: list[str] = []
        self.links: list[dict[str, str]] = []
        self._anchor_href = ""
        self._anchor_rel = ""
        self._anchor_parts: list[str] = []
        self.json_ld_raw: list[str] = []
        self._json_ld = False
        self._script_parts: list[str] = []
        self.visible_parts: list[str] = []
        self.author_signals: list[str] = []
        self.date_signals: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        values = {str(key).casefold(): str(value or "") for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            if tag == "script" and values.get("type", "").casefold() == "application/ld+json":
                self._json_ld = True
                self._script_parts = []
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.semantic_counts:
            self.semantic_counts[tag] += 1
        if re.fullmatch(r"h[1-6]", tag):
            self._heading_level = int(tag[1])
            self._heading_parts = []
        if tag == "link":
            rel_tokens = {part.casefold() for part in values.get("rel", "").split()}
            if "canonical" in rel_tokens and values.get("href"):
                self.canonicals.append(values["href"].strip())
            if "author" in rel_tokens:
                self.author_signals.append(values.get("href") or "rel=author")
        if tag == "meta" and values.get("name", "").casefold() in {"robots", "googlebot", "bingbot"}:
            self.robots_meta.append(values.get("content", "").strip())
        if tag == "a":
            self._anchor_href = values.get("href", "").strip()
            self._anchor_rel = values.get("rel", "").strip()
            self._anchor_parts = []
            if "author" in self._anchor_rel.casefold().split() or "about-author" in self._anchor_href.casefold():
                self.author_signals.append(self._anchor_href or "author link")
        if tag == "time":
            value = values.get("datetime", "").strip()
            if value:
                self.date_signals.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript"}:
            if tag == "script" and self._json_ld:
                self.json_ld_raw.append("".join(self._script_parts).strip())
                self._json_ld = False
                self._script_parts = []
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if self._heading_level and tag == f"h{self._heading_level}":
            self.headings.append({"level": self._heading_level, "text": _clean_text(" ".join(self._heading_parts))})
            self._heading_level = 0
            self._heading_parts = []
        if tag == "a" and self._anchor_href:
            self.links.append({"href": self._anchor_href, "text": _clean_text(" ".join(self._anchor_parts))})
            self._anchor_href = ""
            self._anchor_rel = ""
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self._json_ld:
            self._script_parts.append(data)
            return
        if self.skip_depth or not data.strip():
            return
        clean = data.strip()
        self.visible_parts.append(clean)
        if self._heading_level:
            self._heading_parts.append(clean)
        if self._anchor_href:
            self._anchor_parts.append(clean)
        if re.search(r"\b(last updated|updated on|published on|date modified|cập nhật lần cuối|ngày đăng)\b", clean, flags=re.I):
            self.date_signals.append(clean)
        if re.search(r"\b(author|written by|reviewed by|tác giả)\b", clean, flags=re.I):
            self.author_signals.append(clean)


def _component(status: str, reasons: Iterable[str] = (), evidence: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "status": status,
        "reasons": [str(item) for item in reasons if str(item).strip()],
        "evidence": [str(item) for item in evidence if str(item).strip()],
    }


def _worst_status(values: Iterable[str], *, default: str = "PASS") -> str:
    return max(values, key=lambda value: STATUS_ORDER.get(value, 0), default=default)


def _local_target_exists(href: str, page_url: str, roots: Iterable[Path]) -> bool:
    parsed = urlsplit(urljoin(page_url, href))
    page_host = urlsplit(page_url).netloc.casefold()
    if parsed.scheme not in {"", "http", "https"} or (parsed.netloc and parsed.netloc.casefold() != page_host):
        return True
    path = parsed.path or "/"
    if path.startswith(("/assets/", "/go/")):
        return True
    relative = path.lstrip("/")
    candidates = []
    for root in roots:
        if not root:
            continue
        if not relative:
            candidates.append(root / "index.html")
        elif Path(relative).suffix:
            candidates.append(root / relative)
        else:
            candidates.extend((root / relative / "index.html", root / relative))
    return any(path.exists() for path in candidates)


def _duplicate_canonical_paths(expected_url: str, roots: Iterable[Path]) -> list[str]:
    expected = _normalize_url(expected_url)
    expected_path = urlsplit(expected).path.rstrip("/") or "/"
    duplicates: set[str] = set()
    if not expected:
        return []
    canonical_pattern = re.compile(
        r"<link\b(?=[^>]*\brel=['\"][^'\"]*canonical[^'\"]*['\"])(?=[^>]*\bhref=['\"]([^'\"]+)['\"])[^>]*>",
        flags=re.I,
    )
    for root in roots:
        if not root or not root.is_dir():
            continue
        for page in root.rglob("index.html"):
            rel = page.relative_to(root).as_posix()
            route = "/" if rel == "index.html" else f"/{rel[:-len('index.html')]}".rstrip("/")
            if route == expected_path:
                continue
            if not should_include_in_sitemap(route):
                continue
            try:
                source = page.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"<meta\b(?=[^>]*\bname=['\"]robots['\"])(?=[^>]*\bcontent=['\"][^'\"]*noindex)", source, flags=re.I):
                continue
            match = canonical_pattern.search(source)
            if match and _normalize_url(match.group(1)) == expected:
                duplicates.add(f"{root.name}/{rel}")
    return sorted(duplicates)


def _robots_policy(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "status": "WARNING",
            "robots_path": str(path or ""),
            "reason": "robots.txt is missing from the local output.",
            "matrix": [],
            "policy_changed": False,
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks: dict[str, list[str]] = {}
    agents: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key.casefold() == "user-agent":
            agents = [value]
            blocks.setdefault(value.casefold(), [])
        elif key.casefold() in {"allow", "disallow"}:
            for agent in agents:
                blocks.setdefault(agent.casefold(), []).append(f"{key.title()}: {value}")
    wildcard = blocks.get("*", [])
    matrix = []
    for crawler, (purpose, recommendation) in KNOWN_AI_CRAWLERS.items():
        explicit = blocks.get(crawler.casefold())
        directives = explicit if explicit is not None else wildcard
        if any(item.casefold() == "disallow: /" for item in directives):
            current = "BLOCKED"
        elif any(item.casefold() == "allow: /" for item in directives):
            current = "ALLOWED_EXPLICIT" if explicit is not None else "ALLOWED_BY_WILDCARD"
        else:
            current = "NO_EXPLICIT_RULE"
        matrix.append({
            "crawler": crawler,
            "purpose": purpose,
            "current_policy": current,
            "directives": directives,
            "recommendation": recommendation,
        })
    return {
        "status": "INFO",
        "robots_path": str(path),
        "reason": "Crawler directives are reported as owner-controlled policy; no directive was changed.",
        "matrix": matrix,
        "policy_changed": False,
    }


def validate_seo_geo_candidate(
    *,
    slug: str,
    page_url: str,
    article_type: str,
    html_text: str,
    site_output_dir: Path,
    docs_dir: Path | None = None,
    source_urls: Iterable[str] = (),
    required_internal_links: Iterable[str] = (),
    affiliate_required: bool = False,
    robots_path: Path | None = None,
    sitemap_path: Path | None = None,
) -> dict[str, Any]:
    parser = CandidateHTMLParser()
    parser.feed(html_text or "")
    visible_text = _clean_text(" ".join(parser.visible_parts))
    word_count = len(re.findall(r"\b[\w'-]+\b", visible_text, flags=re.UNICODE))
    checked_at = datetime.now(UTC).isoformat()
    expected_url = _normalize_url(page_url)
    components: dict[str, dict[str, Any]] = {}

    semantic_reasons: list[str] = []
    semantic_status = "PASS"
    if not visible_text:
        semantic_status = "BLOCKED"
        semantic_reasons.append("No machine-readable visible article text was found.")
    elif word_count < 100:
        semantic_status = "WARNING"
        semantic_reasons.append("Visible content appears thin; review it manually rather than relying on a score threshold.")
    if parser.semantic_counts["main"] == 0 and parser.semantic_counts["article"] == 0:
        semantic_status = _worst_status((semantic_status, "WARNING"))
        semantic_reasons.append("The page has neither a <main> nor an <article> landmark.")
    empty_tables = 0
    for table in re.findall(r"(?is)<table\b[^>]*>(.*?)</table>", html_text or ""):
        cells = [_clean_text(value) for value in re.findall(r"(?is)<t[hd]\b[^>]*>(.*?)</t[hd]>", table)]
        if not cells or not any(cells):
            empty_tables += 1
    if empty_tables:
        semantic_status = "BLOCKED"
        semantic_reasons.append(f"Empty HTML comparison/pricing tables found: {empty_tables}.")
    components["semantic_html"] = _component(
        semantic_status,
        semantic_reasons,
        [f"visible_words={word_count}", *(f"{key}={value}" for key, value in parser.semantic_counts.items())],
    )

    heading_reasons: list[str] = []
    heading_status = "PASS"
    h1_count = sum(1 for item in parser.headings if item["level"] == 1)
    if h1_count != 1:
        heading_status = "BLOCKED"
        heading_reasons.append(f"Exactly one H1 is required; found {h1_count}.")
    if any(not item["text"] for item in parser.headings):
        heading_status = _worst_status((heading_status, "WARNING"))
        heading_reasons.append("At least one heading is empty.")
    previous = 0
    for item in parser.headings:
        level = int(item["level"])
        if previous and level > previous + 1:
            heading_status = _worst_status((heading_status, "WARNING"))
            heading_reasons.append(f"Heading hierarchy jumps from H{previous} to H{level}.")
            break
        previous = level
    components["heading"] = _component(
        heading_status,
        heading_reasons,
        [f"H{item['level']}: {item['text']}" for item in parser.headings[:20]],
    )

    canonical_reasons: list[str] = []
    canonical_status = "PASS"
    if len(parser.canonicals) != 1:
        canonical_status = "BLOCKED"
        canonical_reasons.append(f"Exactly one canonical is required; found {len(parser.canonicals)}.")
    elif not _normalize_url(parser.canonicals[0]):
        canonical_status = "BLOCKED"
        canonical_reasons.append("Canonical must be an absolute HTTP(S) URL.")
    elif expected_url and _normalize_url(parser.canonicals[0]) != expected_url:
        canonical_status = "BLOCKED"
        canonical_reasons.append(f"Canonical mismatch: {parser.canonicals[0]} != {page_url}.")
    duplicate_canonicals = _duplicate_canonical_paths(expected_url, [site_output_dir, *([docs_dir] if docs_dir else [])])
    if duplicate_canonicals:
        canonical_status = "BLOCKED"
        canonical_reasons.append(f"Duplicate canonical is used by other local routes: {', '.join(duplicate_canonicals)}.")
    components["canonical"] = _component(canonical_status, canonical_reasons, [*parser.canonicals, *duplicate_canonicals])

    schema_payloads: list[dict[str, Any]] = []
    schema_errors: list[str] = []
    schema_types: set[str] = set()
    for raw in parser.json_ld_raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            schema_errors.append(f"Invalid JSON-LD: {exc.msg} at line {exc.lineno} column {exc.colno}.")
            continue
        for node in _schema_nodes(payload):
            schema_payloads.append(node)
            value = node.get("@type")
            if isinstance(value, str):
                schema_types.add(value)
            elif isinstance(value, list):
                schema_types.update(str(item) for item in value)
    schema_status = "BLOCKED" if schema_errors else "PASS"
    article_like = str(article_type or "").casefold() not in {"", "static", "redirect", "category", "home"}
    if article_like and not (ARTICLE_SCHEMA_TYPES & schema_types):
        schema_status = _worst_status((schema_status, "WARNING"))
        schema_errors.append("Article-like content has no Article, BlogPosting, or NewsArticle schema.")
    for node in schema_payloads:
        if node.get("@type") in ARTICLE_SCHEMA_TYPES:
            for field in ("headline", "author", "datePublished", "dateModified"):
                if not node.get(field):
                    schema_status = _worst_status((schema_status, "WARNING"))
                    schema_errors.append(f"Article schema is missing {field}.")
        rating = node.get("aggregateRating")
        if isinstance(rating, dict) and (not rating.get("ratingValue") or not rating.get("reviewCount")):
            schema_status = "BLOCKED"
            schema_errors.append("aggregateRating is incomplete and must not imply unsupported rating data.")
        if node.get("@type") == "Review" and not node.get("itemReviewed"):
            schema_status = "BLOCKED"
            schema_errors.append("Review schema is missing itemReviewed and does not truthfully identify its subject.")
    components["structured_data"] = _component(schema_status, schema_errors, sorted(schema_types))

    author_found = bool(parser.author_signals) or "Person" in schema_types or any(
        node.get("author") for node in schema_payloads if node.get("@type") in ARTICLE_SCHEMA_TYPES
    )
    date_found = bool(parser.date_signals) or any(
        node.get("dateModified") or node.get("datePublished")
        for node in schema_payloads
        if node.get("@type") in ARTICLE_SCHEMA_TYPES
    )
    trust_reasons = []
    if not author_found:
        trust_reasons.append("Author identity or author linkage is missing.")
    if not date_found:
        trust_reasons.append("Published/updated date metadata is missing.")
    components["author_trust"] = _component(
        "WARNING" if trust_reasons else "PASS",
        trust_reasons,
        [f"author_signals={len(parser.author_signals)}", f"date_signals={len(parser.date_signals)}"],
    )

    index_reasons: list[str] = []
    index_status = "PASS"
    if any("noindex" in value.casefold() for value in parser.robots_meta):
        index_status = "BLOCKED"
        index_reasons.append("The candidate contains an accidental noindex directive.")
    components["indexability"] = _component(index_status, index_reasons, parser.robots_meta or ["no robots meta restriction"])

    roots = [site_output_dir]
    if docs_dir is not None:
        roots.append(docs_dir)
    internal = []
    broken = []
    weak_anchors = []
    for link in parser.links:
        href = link["href"]
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        parsed = urlsplit(urljoin(page_url, href))
        if parsed.netloc and parsed.netloc.casefold() != urlsplit(page_url).netloc.casefold():
            continue
        internal.append(href)
        if not _local_target_exists(href, page_url, roots):
            broken.append(href)
        if link["text"].casefold() in {"click here", "here", "read more", "learn more", "xem thêm", "tại đây"}:
            weak_anchors.append(f"{link['text']}: {href}")
    normalized_internal = {_normalize_url(urljoin(page_url, href)) for href in internal}
    missing_required = [
        href for href in required_internal_links
        if _normalize_url(urljoin(page_url, str(href))) not in normalized_internal
    ]
    link_reasons = []
    link_status = "PASS"
    if missing_required:
        link_status = "BLOCKED"
        link_reasons.append(f"Required internal links are missing: {', '.join(missing_required)}.")
    if broken:
        link_status = _worst_status((link_status, "WARNING"))
        link_reasons.append(f"Broken local links detected: {', '.join(sorted(set(broken)))}.")
    if not internal:
        link_status = _worst_status((link_status, "WARNING"))
        link_reasons.append("No internal links were found.")
    if weak_anchors:
        link_status = _worst_status((link_status, "WARNING"))
        link_reasons.append("Generic anchor text reduces standalone context.")
    components["internal_links"] = _component(
        link_status,
        link_reasons,
        [f"internal_links={len(internal)}", f"broken_links={len(set(broken))}", *weak_anchors[:10]],
    )

    supplied_sources = sorted({_normalize_url(value) for value in source_urls if _normalize_url(value)})
    matched_sources = [source for source in supplied_sources if source in {_normalize_url(link["href"]) for link in parser.links}]
    citation_reasons = []
    citation_status = "PASS"
    if supplied_sources and not matched_sources:
        citation_status = "BLOCKED"
        citation_reasons.append("No supplied source URL is preserved in the candidate HTML.")
    elif supplied_sources and len(matched_sources) < len(supplied_sources):
        citation_status = "WARNING"
        citation_reasons.append("Only part of the supplied source set is cited in the candidate HTML.")
    elif not supplied_sources and article_like:
        citation_status = "WARNING"
        citation_reasons.append("No source URLs were supplied to the SEO/GEO validator; research gates remain authoritative.")
    answer_blocks = re.findall(r"(?is)<h[23]\b[^>]*>.*?</h[23]>\s*<p\b[^>]*>(.*?)</p>", html_text)
    concise_answers = [value for value in answer_blocks if 12 <= len(_clean_text(value).split()) <= 100]
    if not concise_answers:
        citation_status = _worst_status((citation_status, "WARNING"))
        citation_reasons.append("No concise answer paragraph appears directly below an H2/H3 heading.")
    components["citation_structure"] = _component(
        citation_status,
        citation_reasons,
        [f"supplied_sources={len(supplied_sources)}", f"matched_sources={len(matched_sources)}", f"concise_answer_blocks={len(concise_answers)}"],
    )

    lowered = html_text.casefold()
    disclosure_present = "affiliate disclosure" in lowered and "commission" in lowered
    disclosure_status = "BLOCKED" if affiliate_required and not disclosure_present else "PASS"
    disclosure_reasons = ["Affiliate content is missing a commission disclosure."] if disclosure_status == "BLOCKED" else []
    components["affiliate_disclosure"] = _component(disclosure_status, disclosure_reasons, [f"required={affiliate_required}", f"present={disclosure_present}"])

    geo_claims = []
    for pattern in GEO_ADVISORY_PATTERNS:
        geo_claims.extend(_clean_text(match.group(0)) for match in pattern.finditer(visible_text))
    components["geo_claim_protection"] = _component(
        "WARNING" if geo_claims else "PASS",
        ["Unverified GEO/AI-discoverability marketing claims must remain advisory until independently evidenced."] if geo_claims else [],
        geo_claims[:10],
    )

    robots = _robots_policy(robots_path)
    crawl_reasons = []
    crawl_status = "PASS"
    if robots["status"] == "WARNING":
        crawl_status = "WARNING"
        crawl_reasons.append(robots["reason"])
    if sitemap_path is None or not sitemap_path.is_file():
        crawl_status = _worst_status((crawl_status, "WARNING"))
        crawl_reasons.append("sitemap.xml is missing from the local output.")
    elif expected_url:
        sitemap_text = sitemap_path.read_text(encoding="utf-8", errors="replace")
        candidate_in_docs = _local_target_exists(page_url, page_url, [docs_dir] if docs_dir else [])
        if candidate_in_docs and page_url not in sitemap_text and expected_url not in sitemap_text:
            crawl_status = _worst_status((crawl_status, "WARNING"))
            crawl_reasons.append("The locally generated page exists but its canonical URL is absent from sitemap.xml.")
    components["crawlability"] = _component(crawl_status, crawl_reasons, [str(robots_path or ""), str(sitemap_path or "")])

    blocker_reasons: list[str] = []
    warnings: list[str] = []
    recommended_fixes: list[str] = []
    for name, component in components.items():
        for reason in component["reasons"]:
            label = f"{name}: {reason}"
            if component["status"] == "BLOCKED":
                blocker_reasons.append(label)
            elif component["status"] == "WARNING":
                warnings.append(label)
            recommended_fixes.append(reason)
    final_result = "BLOCKED" if blocker_reasons else ("WARNING" if warnings else "PASS")
    return {
        "schema_version": "seo_geo_validation_v1",
        "checked_at": checked_at,
        "slug": slug,
        "page_url": page_url,
        "article_type": article_type,
        "content_sha256": hashlib.sha256((html_text or "").encode("utf-8")).hexdigest(),
        "semantic_html_status": components["semantic_html"]["status"],
        "heading_status": components["heading"]["status"],
        "author_metadata_status": components["author_trust"]["status"],
        "structured_data_status": components["structured_data"]["status"],
        "canonical_status": components["canonical"]["status"],
        "indexability_status": components["indexability"]["status"],
        "internal_link_status": components["internal_links"]["status"],
        "source_citation_status": components["citation_structure"]["status"],
        "disclosure_status": components["affiliate_disclosure"]["status"],
        "geo_claim_protection_status": components["geo_claim_protection"]["status"],
        "crawlability_status": components["crawlability"]["status"],
        "ai_crawler_advisory": robots,
        "checks": components,
        "blocking_reasons": blocker_reasons,
        "warnings": warnings,
        "recommended_fixes": list(dict.fromkeys(recommended_fixes)),
        "final_result": final_result,
        "human_approval_required": True,
        "auto_publish": False,
        "paid_api_used": False,
        "inputs": {
            "source_urls": supplied_sources,
            "required_internal_links": [str(value) for value in required_internal_links],
            "affiliate_required": bool(affiliate_required),
        },
    }


def write_seo_geo_report(report: dict[str, Any], data_dir: Path) -> Path:
    slug = re.sub(r"[^a-z0-9-]+", "-", str(report.get("slug") or "candidate").casefold()).strip("-") or "candidate"
    path = data_dir / "seo_geo_validation" / f"{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def format_seo_geo_report(report: dict[str, Any]) -> str:
    labels = (
        ("Semantic HTML", "semantic_html_status"),
        ("Heading hierarchy", "heading_status"),
        ("Canonical", "canonical_status"),
        ("Author metadata", "author_metadata_status"),
        ("Structured data", "structured_data_status"),
        ("Indexability", "indexability_status"),
        ("Internal links", "internal_link_status"),
        ("Source attribution", "source_citation_status"),
        ("Affiliate disclosure", "disclosure_status"),
        ("GEO claim protection", "geo_claim_protection_status"),
        ("Crawlability", "crawlability_status"),
    )
    lines = ["SEO/GEO VALIDATION", "--------------------------------"]
    lines.extend(f"{label}: {report.get(key, 'NOT_RUN')}" for label, key in labels)
    lines.append("AI crawler policy: INFO")
    lines.append("")
    lines.append(f"FINAL_RESULT: {report.get('final_result', 'BLOCKED')}")
    lines.append("Human approval is still required.")
    if report.get("blocking_reasons"):
        lines.extend(["", "Blocking reasons:", *[f"- {item}" for item in report["blocking_reasons"]]])
    if report.get("warnings"):
        lines.extend(["", "Warnings:", *[f"- {item}" for item in report["warnings"]]])
    return "\n".join(lines)
