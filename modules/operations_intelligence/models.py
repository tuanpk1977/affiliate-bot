from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "operations_intelligence_v1"
ENTITY_TYPES = {
    "company",
    "product",
    "model",
    "developer_tool",
    "affiliate_program",
    "article",
    "topic",
    "root_topic",
    "category",
    "source",
    "competitor",
    "ai_model",
    "feature",
    "integration",
    "pricing_plan",
    "use_case",
    "claim",
    "affiliate_offer",
}
RELATION_TYPES = {
    "COMPANY_OWNS_PRODUCT",
    "PRODUCT_HAS_MODEL",
    "PRODUCT_COMPETES_WITH_PRODUCT",
    "ARTICLE_REVIEWS_ENTITY",
    "ARTICLE_COMPARES_ENTITY",
    "ARTICLE_BELONGS_TO_TOPIC",
    "TOPIC_BELONGS_TO_ROOT",
    "ARTICLE_LINKS_TO_ARTICLE",
    "ENTITY_HAS_AFFILIATE_PROGRAM",
    "ENTITY_HAS_OFFICIAL_SOURCE",
    "COMPANY_OFFERS_PRODUCT",
    "PRODUCT_HAS_FEATURE",
    "PRODUCT_SUPPORTS_INTEGRATION",
    "PRODUCT_HAS_PRICING_PLAN",
    "PRODUCT_SERVES_USE_CASE",
    "ARTICLE_DISCUSS_PRODUCT",
    "ARTICLE_CITES_SOURCE",
    "CLAIM_SUPPORTED_BY_SOURCE",
    "OFFER_REFERENCES_PRODUCT",
}


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/")
    return f"https://{host}{path}" if host else ""


def domain_of(value: str) -> str:
    normalized = normalize_url(value)
    return (urlparse(normalized).hostname or "").removeprefix("www.")


def stable_id(entity_type: str, name: str, discriminator: str = "") -> str:
    material = "|".join((entity_type, normalize_name(name), discriminator.casefold()))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"{entity_type}:{digest}"


@dataclass(frozen=True)
class Evidence:
    source: str
    source_kind: str
    observed_at: str = ""
    confidence: float = 0.5
    note: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("Evidence requires a source URL or local evidence path.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_kind": self.source_kind,
            "observed_at": self.observed_at,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "note": self.note,
        }


@dataclass
class Entity:
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: set[str] = field(default_factory=set)
    official_domain: str = ""
    official_urls: set[str] = field(default_factory=set)
    repository_urls: set[str] = field(default_factory=set)
    documentation_urls: set[str] = field(default_factory=set)
    pricing_urls: set[str] = field(default_factory=set)
    affiliate_urls: set[str] = field(default_factory=set)
    parent_company: str = ""
    products: set[str] = field(default_factory=set)
    competitors: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    related_articles: set[str] = field(default_factory=set)
    source_evidence: list[Evidence] = field(default_factory=list)
    first_seen_at: str = ""
    last_verified_at: str = ""
    confidence: float = 0.0
    verification_status: str = "unknown"
    known_facts: dict[str, dict[str, Any]] = field(default_factory=dict)
    unknown_or_unverified: list[dict[str, Any]] = field(default_factory=list)
    stale_fields: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity type: {self.entity_type}")
        if not self.canonical_name.strip():
            raise ValueError("Entity canonical_name is required.")

    def add_fact(self, key: str, value: Any, evidence: Evidence | None) -> None:
        if evidence is None:
            self.unknown_or_unverified.append(
                {"field": key, "candidate_value": value, "reason": "missing evidence"}
            )
            return
        self.known_facts[key] = {"value": value, "evidence": evidence.to_dict()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "aliases": sorted(alias for alias in self.aliases if alias != self.canonical_name),
            "entity_type": self.entity_type,
            "official_domain": self.official_domain,
            "official_urls": sorted(self.official_urls),
            "repository_urls": sorted(self.repository_urls),
            "documentation_urls": sorted(self.documentation_urls),
            "pricing_urls": sorted(self.pricing_urls),
            "affiliate_urls": sorted(self.affiliate_urls),
            "parent_company": self.parent_company,
            "products": sorted(self.products),
            "competitors": sorted(self.competitors),
            "categories": sorted(self.categories),
            "related_articles": sorted(self.related_articles),
            "source_evidence": [
                item.to_dict()
                for item in sorted(self.source_evidence, key=lambda row: (row.source, row.source_kind))
            ],
            "first_seen_at": self.first_seen_at,
            "last_verified_at": self.last_verified_at,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "verification_status": self.verification_status,
            "known_facts": {key: self.known_facts[key] for key in sorted(self.known_facts)},
            "unknown_or_unverified": sorted(
                self.unknown_or_unverified,
                key=lambda row: (str(row.get("field", "")), str(row.get("candidate_value", ""))),
            ),
            "stale_fields": sorted(self.stale_fields),
            "notes": sorted(set(self.notes)),
        }


@dataclass(frozen=True)
class Relation:
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    evidence: Evidence
    confidence: float = 0.5
    status: str = "candidate"

    def __post_init__(self) -> None:
        if self.relation_type not in RELATION_TYPES:
            raise ValueError(f"Unsupported relation type: {self.relation_type}")
        if self.status not in {"candidate", "needs_review", "verified"}:
            raise ValueError(f"Unsupported relation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_entity_id": self.source_entity_id,
            "relation_type": self.relation_type,
            "target_entity_id": self.target_entity_id,
            "evidence": self.evidence.to_dict(),
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "status": self.status,
        }


@dataclass(frozen=True)
class MergeSuggestion:
    left_entity_id: str
    right_entity_id: str
    reason: str
    confidence: float
    requires_human_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_entity_id": self.left_entity_id,
            "right_entity_id": self.right_entity_id,
            "reason": self.reason,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "requires_human_review": self.requires_human_review,
        }
