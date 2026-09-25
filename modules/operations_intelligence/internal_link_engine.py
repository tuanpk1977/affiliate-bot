from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .inventory import PUBLIC_BASE_URL, article_inventory, internal_slug
from .storage import atomic_write_json, atomic_write_text


SCHEMA_VERSION = "internal_link_recommendations_v1"


class InternalLinkRecommendationEngine:
    """Recommend links without editing HTML or workflow state."""

    def __init__(
        self,
        *,
        root: Path,
        minimum_inbound_links: int = 2,
        maximum_suggestions_per_article: int = 5,
    ) -> None:
        self.root = root.resolve()
        self.minimum_inbound_links = minimum_inbound_links
        self.maximum_suggestions = maximum_suggestions_per_article

    def analyze(self, records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        records = records if records is not None else article_inventory(self.root)
        published = {
            row["slug"]: row
            for row in records
            if row.get("is_published_local") and str(row.get("canonical") or "").startswith(PUBLIC_BASE_URL)
        }
        inbound: Counter[str] = Counter()
        outbound: dict[str, set[str]] = defaultdict(set)
        invalid: list[dict[str, Any]] = []
        for slug, record in published.items():
            html = record.get("html") if isinstance(record.get("html"), dict) else {}
            for link in html.get("links") or []:
                if not isinstance(link, dict):
                    continue
                href = str(link.get("href") or "")
                target = internal_slug(urljoin(record["canonical"], href))
                if not target:
                    continue
                if target == slug:
                    invalid.append({"source_slug": slug, "href": href, "reason": "self link"})
                    continue
                if target not in published:
                    invalid.append(
                        {
                            "source_slug": slug,
                            "href": href,
                            "target_slug": target,
                            "reason": "target is not a published local canonical page",
                        }
                    )
                    continue
                outbound[slug].add(target)
                inbound[target] += 1

        suggestions: list[dict[str, Any]] = []
        for slug, record in published.items():
            candidates: list[tuple[int, str, str]] = []
            for target_slug, target in published.items():
                if target_slug == slug or target_slug in outbound[slug]:
                    continue
                score = 0
                evidence: list[str] = []
                if record.get("root_topic_id") and record.get("root_topic_id") == target.get("root_topic_id"):
                    score += 4
                    evidence.append("same weekly root topic")
                if record.get("daily_angle") and record.get("daily_angle") == target.get("daily_angle"):
                    score += 2
                    evidence.append("same editorial angle")
                source_words = set(str(record.get("title") or "").casefold().split())
                target_words = set(str(target.get("title") or "").casefold().split())
                overlap = len(source_words & target_words)
                if overlap >= 2:
                    score += min(overlap, 3)
                    evidence.append(f"{overlap} shared title terms")
                if score:
                    candidates.append((score, target_slug, "; ".join(evidence)))
            for score, target_slug, evidence in sorted(candidates, reverse=True)[: self.maximum_suggestions]:
                suggestions.append(
                    {
                        "source_slug": slug,
                        "target_slug": target_slug,
                        "target_url": published[target_slug]["canonical"],
                        "suggested_anchor": published[target_slug]["title"],
                        "score": score,
                        "evidence": evidence,
                        "apply": False,
                    }
                )
        orphans = [
            {
                "slug": slug,
                "canonical": record["canonical"],
                "inbound_count": inbound[slug],
            }
            for slug, record in published.items()
            if inbound[slug] < self.minimum_inbound_links
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "published_pages_analyzed": len(published),
            "suggestions": suggestions,
            "orphan_pages": orphans,
            "invalid_internal_links": invalid,
            "summary": {
                "suggestion_count": len(suggestions),
                "orphan_count": len(orphans),
                "invalid_count": len(invalid),
            },
            "recommendation_only": True,
            "html_modified": False,
        }

    def write(self, payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
        json_path = output_dir / "internal_link_recommendations.json"
        md_path = output_dir / "internal_link_recommendations.md"
        atomic_write_json(json_path, payload, intelligence_root=self.root / "data")
        lines = ["# Internal Link Recommendations", "", "No HTML was changed.", ""]
        lines.extend(
            f"- `{row['source_slug']}` -> `{row['target_slug']}` ({row['evidence']})"
            for row in payload["suggestions"]
        )
        atomic_write_text(md_path, "\n".join(lines) + "\n", intelligence_root=self.root / "data")
        return {"json": str(json_path), "markdown": str(md_path)}

