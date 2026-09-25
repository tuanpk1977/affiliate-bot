from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlparse

from modules.entity_knowledge_base import entity_id


OFFICIAL_SOURCE_TYPES = {
    "official_docs",
    "product_page",
    "pricing_page",
    "affiliate_program_page",
    "api_docs",
    "release_notes",
    "security_page",
    "integration_page",
}

_TYPE_ALIASES = {
    "docs": "official_docs",
    "documentation": "official_docs",
    "official_documentation": "official_docs",
    "official_docs": "official_docs",
    "official_website": "product_page",
    "product_page": "product_page",
    "product_pages": "product_page",
    "pricing": "pricing_page",
    "pricing_page": "pricing_page",
    "pricing_pages": "pricing_page",
    "affiliate_page": "affiliate_program_page",
    "affiliate_pages": "affiliate_program_page",
    "affiliate_program_page": "affiliate_program_page",
    "affiliate_program_pages": "affiliate_program_page",
    "api": "api_docs",
    "api_docs": "api_docs",
    "release_notes": "release_notes",
    "changelog": "release_notes",
    "security": "security_page",
    "security_page": "security_page",
    "integration": "integration_page",
    "integrations": "integration_page",
    "integration_page": "integration_page",
    "validated_topic_source": "independent_evidence",
    "competitor_article": "independent_evidence",
    "blog_articles": "independent_evidence",
    "research_papers": "independent_evidence",
}


def canonical_source_type(value: Any, url: str = "") -> str:
    """Return one source vocabulary and correct obvious path/type conflicts.

    A homepage labelled as a pricing or documentation page remains an official
    product page, but it cannot satisfy the more specific pricing/docs gate.
    """
    raw = re.sub(r"[\s-]+", "_", str(value or "").strip().casefold())
    source_type = _TYPE_ALIASES.get(raw, raw or "independent_evidence")
    parsed = urlparse(str(url or ""))
    path = parsed.path.casefold().rstrip("/")
    host = (parsed.hostname or "").casefold()
    # Help/documentation subdomains are documentation by default.  A path such
    # as help.vendor.test/pricing must not become pricing evidence merely from
    # its URL; the exception is an explicitly named affiliate-program article,
    # whose content is validated separately after retrieval.
    if host.startswith(("help.", "docs.", "developer.", "developers.")):
        if any(token in path for token in ("/affiliate-program", "/partner-program")):
            return "affiliate_program_page"
        if any(token in path for token in ("/api", "/developers")):
            return "api_docs"
        return "official_docs"
    if any(token in path for token in ("/pricing", "/plans", "/billing")):
        return "pricing_page"
    if any(token in path for token in ("/affiliate", "/affiliates", "/partner-program")):
        return "affiliate_program_page"
    if any(token in path for token in ("/api", "/developers")):
        return "api_docs"
    if any(token in path for token in ("/docs", "/documentation", "/help", "/guide")):
        return "official_docs"
    if any(token in path for token in ("/changelog", "/release-notes", "/releases")):
        return "release_notes"
    if not path and source_type in {"pricing_page", "official_docs", "api_docs"}:
        return "product_page"
    return source_type


def source_url(row: dict[str, Any]) -> str:
    return str(
        row.get("canonical_url")
        or row.get("source_url")
        or row.get("url")
        or ""
    ).strip()


def source_status(row: dict[str, Any]) -> str:
    return str(
        row.get("verification_status")
        or row.get("source_status")
        or row.get("status")
        or ""
    ).strip().casefold()


def normalized_host(url: str) -> str:
    host = urlparse(str(url or "")).hostname or ""
    return host.casefold().removeprefix("www.")


def registrable_domain(url: str) -> str:
    host = normalized_host(url)
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _brand_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    for suffix in ("artificialintelligence", "software", "platform", "app", "ai", "inc"):
        if key.endswith(suffix) and len(key) > len(suffix) + 2:
            key = key[: -len(suffix)]
    return key


def domain_looks_owned_by(entity_name: str, url: str) -> bool:
    """Conservative brand/domain ownership heuristic, never a trust check."""
    domain_label = registrable_domain(url).split(".", 1)[0]
    brand = _brand_key(entity_name)
    domain = _brand_key(domain_label)
    return bool(
        brand
        and domain
        and (
            brand == domain
            or (len(brand) >= 5 and brand in domain)
            or (len(domain) >= 4 and domain in brand)
        )
    )


def source_directly_relevant(
    row: dict[str, Any],
    entity_names: Iterable[str],
    *,
    content: str = "",
) -> bool:
    """Require a comparison source to name an actual compared product.

    Owned product domains are intrinsically relevant.  Independent evidence
    must explicitly name a compared product; broad topic-token overlap is not
    sufficient.  The extra context requirement for very short brand names
    avoids treating ordinary uses of words such as ``make`` as brand evidence.
    """
    url = source_url(row)
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ("title", "label", "source_name", "brand", "tool_name", "source_url", "url")
    )
    haystack = f"{haystack} {content}".casefold()
    context_terms = {
        "automation", "workflow", "integration", "software", "platform",
        "pricing", "product", "review", "app", "creative", "accounting",
    }
    for name in entity_names:
        if domain_looks_owned_by(name, url):
            return True
        phrase = re.sub(r"\s+", " ", str(name or "").strip().casefold())
        if not phrase or not re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", haystack):
            continue
        if len(re.sub(r"[^a-z0-9]", "", phrase)) > 5:
            return True
        if any(re.search(rf"\b{re.escape(term)}\b", haystack) for term in context_terms):
            return True
    return False


def source_content_matches_type(row: dict[str, Any], content: str) -> bool:
    """Check that retrieved text supports its claimed official source family.

    Ownership and a plausible URL are necessary but not sufficient.  Some
    vendor sites return a generic fallback page with HTTP 200 for nonexistent
    paths; accepting that response used to let ``/pricing`` or ``/affiliate``
    satisfy a gate without containing pricing or affiliate evidence.
    """
    source_type = canonical_source_type(
        row.get("source_type") or row.get("source_family"), source_url(row)
    )
    text = re.sub(r"\s+", " ", str(content or "")).strip().casefold()
    if not text:
        return False
    fallback_markers = (
        "while we're working on it",
        "while we are working on it",
        "page not found",
        "the page you are looking for",
        "this page doesn't exist",
        "this page does not exist",
        "404 not found",
    )
    if any(marker in text for marker in fallback_markers):
        return False
    words = re.findall(r"[a-z0-9]+", text)
    if len(words) < 6:
        return False
    if source_type == "pricing_page":
        return bool(
            re.search(r"\b(pricing|price|plan|plans|billing|subscription)\b", text)
            and re.search(r"(?:[$€£]|\busd\b|\bfree\b|\bmonthly\b|\byearly\b|\bmonth\b|\byear\b)", text)
        )
    if source_type == "affiliate_program_page":
        return bool(
            re.search(r"\b(affiliate|referral|partner)\b", text)
            and re.search(r"\b(commission|refer|referral|earn|payout|program|partner)\b", text)
        )
    if source_type in {"official_docs", "api_docs"}:
        return bool(
            re.search(r"\b(help|documentation|docs|guide|workflow|integration|api|configure|setup|automation)\b", text)
        )
    if source_type == "security_page":
        return bool(
            re.search(r"\b(security|privacy|compliance|encryption|soc\s*2|gdpr|data protection)\b", text)
        )
    if source_type == "integration_page":
        return bool(
            re.search(r"\b(integration|integrations|connect|connector|workflow|automation|api)\b", text)
        )
    return True


def source_content_is_soft_404(content: str) -> bool:
    """Detect successful HTTP responses that contain an error/fallback page."""
    text = re.sub(r"\s+", " ", str(content or "")).strip().casefold()
    markers = (
        "while we're working on it",
        "while we are working on it",
        "page not found",
        "the page you are looking for",
        "this page doesn't exist",
        "this page does not exist",
        "404 not found",
        "error 404",
        "nothing here",
    )
    return not text or any(marker in text for marker in markers)


def official_seed_sources(entity_name: str, official_domains: Iterable[str]) -> list[dict[str, Any]]:
    """Build bounded, unverified public URL candidates for official families.

    These are retrieval candidates, not approvals.  A candidate contributes to
    gates only after successful retrieval, ownership matching, and source-type
    classification.
    """
    domains = []
    for value in official_domains:
        raw = str(value or "").strip()
        host = normalized_host(raw if "://" in raw else f"https://{raw}")
        if host and host not in domains:
            domains.append(host)
    rows: list[dict[str, Any]] = []
    for host in domains:
        base = f"https://{host}"
        if host.startswith(("help.", "docs.", "developer.", "developers.")):
            candidates = (
                (base, "official_docs"),
                (f"{base}/affiliate-program", "affiliate_program_page"),
            )
        else:
            candidates = (
                (base, "product_page"),
                (f"{base}/pricing", "pricing_page"),
                (f"{base}/en/pricing", "pricing_page"),
                (f"https://help.{registrable_domain(base)}", "official_docs"),
                (f"{base}/affiliate", "affiliate_program_page"),
                (f"{base}/en/affiliate", "affiliate_program_page"),
                (f"{base}/partners", "affiliate_program_page"),
                (f"{base}/l/partners", "affiliate_program_page"),
                (f"{base}/integrations", "product_page"),
                (f"{base}/security", "official_docs"),
            )
        for url, source_type in candidates:
            rows.append(
                {
                    "title": f"{entity_name} {source_type.replace('_', ' ')}",
                    "source_url": url,
                    "canonical_url": url,
                    "source_type": source_type,
                    "source_family": source_type,
                    "verification_status": "needs_review",
                    "canonical_entity_id": entity_id(entity_name),
                    "canonical_entity_name": entity_name,
                    "official_classification": "official_candidate",
                    "official_ownership_verified": False,
                    "discovery_method": "entity_official_family_seed",
                }
            )
    return rows


def flatten_source_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("verified_sources", "verified_registry_records"):
        for row in payload.get(key) or []:
            if isinstance(row, dict):
                rows.append({**row, "declared_family": row.get("source_type") or key})
    trusted = payload.get("trusted_sources")
    if isinstance(trusted, dict):
        for family, family_rows in trusted.items():
            for row in family_rows if isinstance(family_rows, list) else []:
                if isinstance(row, dict):
                    rows.append({**row, "declared_family": family})
    return rows


def comparison_entity_names(package: dict[str, Any], task: dict[str, Any]) -> list[str]:
    """Return explicit/product entities only; never generated topic alternatives."""
    values: list[Any] = []
    for key in ("comparison_entities", "products_compared", "comparator_entities"):
        raw = task.get(key)
        values.extend(raw if isinstance(raw, list) else [raw] if raw else [])
    entities = package.get("entities") if isinstance(package.get("entities"), dict) else {}
    for key in ("products", "ai_tools", "companies", "competitors"):
        raw = entities.get(key)
        values.extend(raw if isinstance(raw, list) else [raw] if raw else [])
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = re.sub(r"\s+", " ", str(value or "")).strip()
        key = entity_id(name)
        if (
            not name
            or key in seen
            or len(name) > 80
            or any(marker in name.casefold() for marker in (" worth it ", " mistakes and ", " workflows and "))
        ):
            continue
        seen.add(key)
        result.append(name)
    return result


def match_source_entity(
    row: dict[str, Any],
    entity_names: Iterable[str],
    *,
    explicit_domains: dict[str, Iterable[str]] | None = None,
) -> str:
    url = source_url(row)
    host = registrable_domain(url)
    label = " ".join(
        str(row.get(key) or "")
        for key in ("brand", "tool_name", "canonical_entity_name", "label", "source_name")
    ).casefold()
    matches: list[str] = []
    for name in entity_names:
        entity_key = entity_id(name)
        domains = {
            registrable_domain(value)
            for value in (explicit_domains or {}).get(entity_key, [])
            if value
        }
        owned = host in domains or domain_looks_owned_by(name, url)
        # A conservative brand/domain match is sufficient ownership evidence
        # even when a homepage title does not repeat the product name.
        if owned:
            matches.append(name)
    return matches[0] if len(matches) == 1 else ""


def classify_source(
    row: dict[str, Any],
    entity_names: Iterable[str],
    *,
    explicit_domains: dict[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    url = source_url(row)
    declared = row.get("source_type") or row.get("connector_type") or row.get("declared_family")
    source_type = canonical_source_type(declared, url)
    entity_name = match_source_entity(
        row, entity_names, explicit_domains=explicit_domains
    )
    parsed = urlparse(url)
    is_homepage = parsed.path.rstrip("/") == "" and not parsed.query
    declared_key = re.sub(r"[\s-]+", "_", str(declared or "").strip().casefold())
    if (
        entity_name
        and is_homepage
        and source_type == "independent_evidence"
        and declared_key in {"validated_topic_source", "independent_evidence"}
    ):
        source_type = "product_page"
    official = bool(entity_name and source_type in OFFICIAL_SOURCE_TYPES)
    return {
        **row,
        "source_url": url,
        "canonical_url": url,
        "source_type": source_type,
        "source_family": source_type,
        "canonical_entity_id": entity_id(entity_name) if entity_name else "",
        "canonical_entity_name": entity_name,
        "official_classification": "official" if official else "independent",
        "official_ownership_verified": official,
    }
