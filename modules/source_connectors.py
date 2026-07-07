from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import settings


SOURCE_STATUSES = {"verified", "estimated", "missing", "needs_review"}
CONNECTOR_TYPES = (
    "official_docs",
    "pricing_page",
    "product_page",
    "release_notes",
    "affiliate_program_page",
    "competitor_article",
    "api_docs",
)


@dataclass(frozen=True)
class SourceCandidate:
    connector_type: str
    label: str
    url: str
    status: str
    evidence: str


class SourceConnectorFramework:
    def __init__(
        self,
        *,
        offers_file: Path | None = None,
        affiliate_links_file: Path | None = None,
    ) -> None:
        self.offers_file = offers_file or settings.offers_file
        self.affiliate_links_file = affiliate_links_file or settings.affiliate_links_file
        self.offer_rows = self._load_rows(self.offers_file)
        self.affiliate_rows = self._load_rows(self.affiliate_links_file)

    def collect(self, keyword: str, entities: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        return {connector: [asdict(item) for item in self._run_connector(connector, keyword, entities)] for connector in CONNECTOR_TYPES}

    def _run_connector(self, connector_type: str, keyword: str, entities: dict[str, Any]) -> list[SourceCandidate]:
        brands = self._brands_for_entities(entities)
        results: list[SourceCandidate] = []
        if connector_type in {"product_page", "pricing_page", "affiliate_program_page"}:
            for brand in brands:
                row = self._find_brand_row(brand)
                url = str(row.get("website") or row.get("official_url") or "").strip()
                affiliate_url = str(row.get("affiliate_url") or "").strip()
                if connector_type == "product_page":
                    results.append(self._candidate(connector_type, f"{brand} product page", url, "Brand website from local offers/affiliate data"))
                elif connector_type == "pricing_page":
                    results.append(self._candidate(connector_type, f"{brand} pricing page", url, "Pricing should be verified on official site; local source only"))
                else:
                    results.append(self._candidate(connector_type, f"{brand} affiliate program page", affiliate_url, "Affiliate page from local offers/affiliate data"))
        elif connector_type == "official_docs":
            for brand in brands:
                row = self._find_brand_row(brand)
                url = str(row.get("official_url") or row.get("website") or "").strip()
                status = "needs_review" if url else "missing"
                results.append(SourceCandidate(connector_type, f"{brand} official docs", url, status, "No live fetch; requires manual confirmation"))
        elif connector_type == "release_notes":
            for brand in brands:
                results.append(SourceCandidate(connector_type, f"{brand} release notes", "", "missing", "No offline release-note source available"))
        elif connector_type == "competitor_article":
            results.append(SourceCandidate(connector_type, f"{keyword} competitor article", "", "missing", "Requires local competitor snapshot input"))
        elif connector_type == "api_docs":
            brands_with_api = [brand for brand in brands if any(token in keyword.lower() for token in ("api", "sdk", "integration", "developer"))]
            if not brands_with_api:
                results.append(SourceCandidate(connector_type, f"{keyword} API docs", "", "missing", "No API signal in keyword"))
            else:
                for brand in brands_with_api:
                    results.append(SourceCandidate(connector_type, f"{brand} API docs", "", "needs_review", "API docs path cannot be verified offline"))
        return self._dedupe(results)

    def _candidate(self, connector_type: str, label: str, url: str, evidence: str) -> SourceCandidate:
        if url:
            status = "verified"
        else:
            status = "missing"
        return SourceCandidate(connector_type, label, url, status, evidence)

    def _brands_for_entities(self, entities: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("products", "companies", "ai_tools", "competitors", "alternatives"):
            raw = entities.get(key, [])
            if isinstance(raw, list):
                values.extend(str(item).strip() for item in raw if str(item).strip())
        seen: set[str] = set()
        result: list[str] = []
        for item in values:
            norm = item.lower()
            if norm in seen:
                continue
            seen.add(norm)
            result.append(item)
        return result[:8]

    def _load_rows(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _find_brand_row(self, brand: str) -> dict[str, Any]:
        for row in [*self.offer_rows, *self.affiliate_rows]:
            candidate = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").strip()
            if candidate.lower() == brand.lower():
                return row
        return {}

    def _dedupe(self, rows: list[SourceCandidate]) -> list[SourceCandidate]:
        seen: set[tuple[str, str, str]] = set()
        result: list[SourceCandidate] = []
        for row in rows:
            key = (row.connector_type, row.label.lower(), row.url)
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result
