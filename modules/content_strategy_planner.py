from __future__ import annotations

import re
import urllib.parse
from collections import Counter, defaultdict
from typing import Any


CONTENT_TYPES = {
    "Pillar Guide",
    "Review",
    "Comparison",
    "Best List",
    "Alternatives",
    "Buying Guide",
    "Tutorial",
    "Workflow",
    "FAQ",
    "Use Case",
    "Industry Guide",
    "Case Study",
}

STOPWORDS = {
    "a",
    "ai",
    "and",
    "are",
    "best",
    "by",
    "for",
    "from",
    "guide",
    "how",
    "in",
    "is",
    "of",
    "on",
    "review",
    "software",
    "the",
    "to",
    "tool",
    "tools",
    "with",
    "without",
}


def enrich_topics_with_content_strategy(topics: list[dict[str, Any]], *, week_start: str = "", batch_date: str = "") -> dict[str, Any]:
    """Attach planning metadata without changing editorial state or gate behavior."""
    planner = ContentStrategyPlanner()
    enriched = [dict(item) for item in topics]
    quality_warnings = planner.build_quality_guard(enriched)
    for item in enriched:
        item["content_strategy"] = planner.plan_topic(item, enriched)
        slug = str(item.get("slug") or "")
        item["content_quality_warnings"] = quality_warnings.get(slug, [])
    cluster_map = planner.build_cluster_map(enriched, week_start=week_start, batch_date=batch_date)
    return {
        "topics": enriched,
        "topic_cluster_map": cluster_map,
        "content_quality_guard": {
            "mode": "warning_only",
            "warning_count": sum(len(row) for row in quality_warnings.values()),
            "warnings_by_slug": quality_warnings,
        },
    }


class ContentStrategyPlanner:
    """Rule-based content strategy planner for weekly editorial topic metadata."""

    def plan_topic(self, topic: dict[str, Any], weekly_topics: list[dict[str, Any]]) -> dict[str, Any]:
        title = self._title(topic)
        slug = str(topic.get("slug") or "")
        content_type = self._content_type(topic)
        search_intent = self._search_intent(topic, content_type)
        audience = self._audience(title)
        funnel = self._marketing_funnel(content_type, search_intent)
        primary_keyword = str(topic.get("primary_keyword") or topic.get("keyword") or title)
        semantic_keywords = self._semantic_keywords(topic, primary_keyword)
        related = self._related_weekly_topics(topic, weekly_topics)
        cluster_health = self._cluster_health(topic, weekly_topics, related)
        faq_count = self._recommended_faq_count(content_type)
        schema = self._schema_recommendation(content_type)
        return {
            "content_type": content_type,
            "audience": audience,
            "search_intent": search_intent,
            "marketing_funnel": funnel,
            "primary_keyword": primary_keyword,
            "secondary_semantic_keywords": semantic_keywords,
            "suggested_internal_links": related,
            "related_weekly_topics": related,
            "recommended_cta": self._recommended_cta(content_type, funnel),
            "estimated_search_intent": search_intent,
            "suggested_external_link_count": self._suggested_external_link_count(topic, content_type),
            "recommended_faq_count": faq_count,
            "suggested_heading_count": self._suggested_heading_count(content_type),
            "reading_level": "Grade 8-10",
            "target_audience": audience,
            "content_freshness": self._content_freshness(topic),
            "topical_authority_score": self._topical_authority_score(topic, related),
            "entity_keywords": self._entity_keywords(topic, semantic_keywords),
            "schema_recommendation": schema,
            "cluster_health": cluster_health,
            "planning_scope": "weekly_batch_only",
        }

    def build_cluster_map(self, topics: list[dict[str, Any]], *, week_start: str = "", batch_date: str = "") -> dict[str, Any]:
        clusters: dict[str, list[dict[str, str]]] = defaultdict(list)
        for topic in topics:
            key = self._cluster_key(topic)
            clusters[key].append(
                {
                    "slug": str(topic.get("slug") or ""),
                    "title": self._title(topic),
                    "content_type": self._content_type(topic),
                    "search_intent": self._search_intent(topic, self._content_type(topic)),
                }
            )
        duplicate_slugs = [slug for slug, count in Counter(str(item.get("slug") or "") for item in topics).items() if slug and count > 1]
        duplicate_titles = [
            title
            for title, count in Counter(self._normalize(self._title(item)) for item in topics).items()
            if title and count > 1
        ]
        weak_clusters = [name for name, rows in clusters.items() if len(rows) == 1]
        orphan_topics = [rows[0]["slug"] for rows in clusters.values() if len(rows) == 1 and rows[0].get("slug")]
        tree_lines = ["weekly_topic_cluster"]
        for name, rows in sorted(clusters.items()):
            tree_lines.append(f"- {name}")
            for row in rows:
                tree_lines.append(f"  - {row['slug']} ({row['content_type']})")
        return {
            "week_start": week_start,
            "batch_date": batch_date,
            "mode": "planning_only",
            "tree": "\n".join(tree_lines),
            "clusters": [{"name": name, "topics": rows, "topic_count": len(rows)} for name, rows in sorted(clusters.items())],
            "duplicate_topics": {"slugs": duplicate_slugs, "titles": duplicate_titles},
            "missing_content_reviews": self._missing_content_reviews(topics),
            "weak_clusters": weak_clusters,
            "orphan_topics": orphan_topics,
        }

    def build_quality_guard(self, topics: list[dict[str, Any]]) -> dict[str, list[str]]:
        warnings: dict[str, list[str]] = {str(item.get("slug") or ""): [] for item in topics}
        self._add_duplicate_warning(topics, warnings, key_fn=lambda item: str(item.get("slug") or ""), label="duplicate slug")
        self._add_duplicate_warning(topics, warnings, key_fn=lambda item: self._normalize(self._title(item)), label="duplicate weekly topic")
        self._add_duplicate_warning(topics, warnings, key_fn=lambda item: self._title_pattern(self._title(item)), label="duplicate title pattern")
        self._add_duplicate_warning(topics, warnings, key_fn=lambda item: self._search_intent(item, self._content_type(item)), label="duplicate search intent")
        self._add_duplicate_warning(topics, warnings, key_fn=lambda item: self._recommended_cta(self._content_type(item), self._marketing_funnel(self._content_type(item), self._search_intent(item, self._content_type(item)))), label="duplicate CTA")
        self._add_duplicate_warning(topics, warnings, key_fn=lambda item: str(self._recommended_faq_count(self._content_type(item))), label="duplicate FAQ pattern")
        return warnings

    def _add_duplicate_warning(self, topics: list[dict[str, Any]], warnings: dict[str, list[str]], *, key_fn: Any, label: str) -> None:
        keys = [key_fn(item) for item in topics]
        counts = Counter(key for key in keys if key)
        for topic, key in zip(topics, keys):
            if key and counts[key] > 1:
                slug = str(topic.get("slug") or "")
                warnings.setdefault(slug, []).append(f"Warning only: {label} appears {counts[key]} times in this weekly batch.")

    def _title(self, topic: dict[str, Any]) -> str:
        return str(topic.get("title") or topic.get("article_title") or topic.get("keyword") or topic.get("primary_keyword") or "").strip()

    def _content_type(self, topic: dict[str, Any]) -> str:
        text = f"{self._title(topic)} {topic.get('content_type') or ''}".lower()
        if "alternative" in text:
            return "Alternatives"
        if any(marker in text for marker in (" vs ", " versus ", "comparison", "compare")):
            return "Comparison"
        if any(marker in text for marker in ("best ", "top ", "platforms", "tools")):
            return "Best List"
        if "review" in text:
            return "Review"
        if any(marker in text for marker in ("buying", "pricing", "price", "cost")):
            return "Buying Guide"
        if any(marker in text for marker in ("tutorial", "how to", "setup", "implement")):
            return "Tutorial"
        if "workflow" in text:
            return "Workflow"
        if "faq" in text or "questions" in text:
            return "FAQ"
        if "use case" in text or "use cases" in text:
            return "Use Case"
        if "industry" in text:
            return "Industry Guide"
        if "case study" in text:
            return "Case Study"
        return "Pillar Guide"

    def _search_intent(self, topic: dict[str, Any], content_type: str) -> str:
        existing = str(topic.get("search_intent") or "").strip()
        if existing:
            return existing
        if content_type in {"Review", "Comparison", "Best List", "Alternatives", "Buying Guide"}:
            return "commercial investigation"
        if content_type in {"Tutorial", "Workflow", "FAQ", "Use Case"}:
            return "informational"
        return "informational"

    def _audience(self, title: str) -> str:
        text = title.lower()
        if any(marker in text for marker in ("developer", "coding", "github", "api", "python")):
            return "Developers and technical teams"
        if "marketing" in text:
            return "Marketing teams"
        if any(marker in text for marker in ("sales", "crm", "lead")):
            return "Sales and revenue teams"
        if "agency" in text:
            return "Agencies"
        if any(marker in text for marker in ("enterprise", "security", "compliance")):
            return "Enterprise operators"
        return "Small business operators"

    def _marketing_funnel(self, content_type: str, search_intent: str) -> str:
        text = f"{content_type} {search_intent}".lower()
        if any(marker in text for marker in ("pricing", "buying", "transactional")):
            return "Bottom of funnel"
        if any(marker in text for marker in ("review", "comparison", "best", "alternatives", "commercial")):
            return "Middle of funnel"
        return "Top of funnel"

    def _semantic_keywords(self, topic: dict[str, Any], primary_keyword: str) -> list[str]:
        values: list[str] = []
        for field in ("related_keywords", "entities", "matched_products"):
            for value in list(topic.get(field) or []):
                if value and str(value).strip():
                    values.append(str(value).strip())
        values.extend(self._tokens(primary_keyword))
        unique = []
        for value in values:
            normalized = self._normalize(value)
            if normalized and normalized not in {self._normalize(item) for item in unique}:
                unique.append(value)
        return unique[:12]

    def _related_weekly_topics(self, topic: dict[str, Any], weekly_topics: list[dict[str, Any]]) -> list[dict[str, str]]:
        current_slug = str(topic.get("slug") or "")
        current_tokens = set(self._tokens(self._title(topic)))
        scored: list[tuple[int, dict[str, str]]] = []
        for other in weekly_topics:
            other_slug = str(other.get("slug") or "")
            if not other_slug or other_slug == current_slug:
                continue
            other_tokens = set(self._tokens(self._title(other)))
            overlap = len(current_tokens & other_tokens)
            if overlap <= 0:
                continue
            scored.append(
                (
                    overlap,
                    {
                        "slug": other_slug,
                        "title": self._title(other),
                        "reason": f"Shares {overlap} weekly-batch topic term(s).",
                    },
                )
            )
        return [item for _, item in sorted(scored, key=lambda row: (-row[0], row[1]["slug"]))[:4]]

    def _cluster_health(self, topic: dict[str, Any], weekly_topics: list[dict[str, Any]], related: list[dict[str, str]]) -> str:
        if any(str(other.get("slug") or "") == str(topic.get("slug") or "") for other in weekly_topics if other is not topic):
            return "duplicate_warning"
        if not related:
            return "orphan"
        if len(related) == 1:
            return "weak"
        return "healthy"

    def _recommended_cta(self, content_type: str, funnel: str) -> str:
        if content_type == "Review":
            return "Read the full review"
        if content_type in {"Comparison", "Best List", "Alternatives"}:
            return "Compare the shortlisted options"
        if content_type == "Buying Guide":
            return "Use the buyer checklist"
        if content_type in {"Tutorial", "Workflow", "Use Case"}:
            return "Follow the practical workflow"
        if funnel == "Bottom of funnel":
            return "Review the decision checklist"
        return "Read the full guide"

    def _suggested_external_link_count(self, topic: dict[str, Any], content_type: str) -> int:
        source_count = len(list(topic.get("source_urls") or topic.get("sources") or []))
        base = 3 if content_type in {"Review", "Comparison", "Best List"} else 2
        return max(base, min(source_count, 6))

    def _recommended_faq_count(self, content_type: str) -> int:
        if content_type in {"Review", "Comparison", "Best List", "Buying Guide"}:
            return 5
        if content_type == "FAQ":
            return 8
        return 3

    def _suggested_heading_count(self, content_type: str) -> int:
        if content_type in {"Review", "Comparison", "Best List", "Buying Guide"}:
            return 8
        if content_type in {"Tutorial", "Workflow"}:
            return 7
        return 6

    def _content_freshness(self, topic: dict[str, Any]) -> str:
        score = int(float(topic.get("content_freshness_score") or topic.get("trend_score") or 0))
        if score >= 75:
            return "fresh"
        if score >= 45:
            return "current"
        return "evergreen_or_needs_refresh"

    def _topical_authority_score(self, topic: dict[str, Any], related: list[dict[str, str]]) -> int:
        source_count = len(list(topic.get("source_urls") or topic.get("sources") or []))
        score = 45 + min(source_count, 5) * 6 + min(len(related), 4) * 5
        if topic.get("matched_products"):
            score += 8
        return max(0, min(score, 100))

    def _entity_keywords(self, topic: dict[str, Any], semantic_keywords: list[str]) -> list[str]:
        entities = [str(value).strip() for value in list(topic.get("entities") or topic.get("matched_products") or []) if str(value).strip()]
        if not entities:
            entities = [value for value in semantic_keywords if len(value) > 3][:6]
        return entities[:10]

    def _schema_recommendation(self, content_type: str) -> list[str]:
        schema = ["Article", "BreadcrumbList", "Organization", "WebSite"]
        if content_type in {"Review", "Comparison", "Best List", "Buying Guide", "FAQ"}:
            schema.append("FAQPage")
        if content_type in {"Review", "Comparison", "Best List"}:
            schema.append("Product")
        return schema

    def _missing_content_reviews(self, topics: list[dict[str, Any]]) -> list[str]:
        content_types = {self._content_type(item) for item in topics}
        missing = []
        for required in ("Pillar Guide", "Review", "Comparison", "Best List"):
            if required not in content_types:
                missing.append(required)
        return missing

    def _cluster_key(self, topic: dict[str, Any]) -> str:
        tokens = self._tokens(self._title(topic))
        if not tokens:
            return "general"
        return " ".join(tokens[:2])

    def _title_pattern(self, title: str) -> str:
        normalized = self._normalize(title)
        words = normalized.split()
        if len(words) <= 3:
            return normalized
        return " ".join(words[:2] + words[-2:])

    def _tokens(self, text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in STOPWORDS and len(token) > 2]

    def _normalize(self, text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def source_domains(topic: dict[str, Any]) -> list[str]:
        domains: list[str] = []
        for url in list(topic.get("source_urls") or topic.get("sources") or []):
            domain = urllib.parse.urlparse(str(url)).netloc.lower().removeprefix("www.")
            if domain and domain not in domains:
                domains.append(domain)
        return domains
