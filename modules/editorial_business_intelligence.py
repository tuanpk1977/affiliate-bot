from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable

from config import settings


UTC = timezone.utc
STATUS_ORDER = ("Fresh", "Needs Review", "Needs Update", "Outdated", "Deprecated", "Broken")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize_csv(value) for key, value in row.items()})
    return path


def _write_md(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _serialize_csv(value: Any) -> Any:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return value


def _extract_single(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1).strip() if match else ""


def _strip_html(text: str) -> str:
    clean = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    clean = re.sub(r"<style\b.*?</style>", " ", clean, flags=re.I | re.S)
    clean = re.sub(r"<[^>]+>", " ", clean)
    return re.sub(r"\s+", " ", unescape(clean)).strip()


def _slug_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel == "index.html":
        return ""
    if rel.endswith("/index.html"):
        return rel[: -len("/index.html")]
    return rel.rsplit(".", 1)[0]


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _load_offer_index(offers_file: Path, affiliate_links_file: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in (offers_file, affiliate_links_file):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows.extend(dict(row) for row in reader)
    return rows


def _find_links(text: str) -> list[str]:
    return re.findall(r"""href=["']([^"'#]+)["']""", text, flags=re.I)


def _normalize_href(href: str) -> str:
    value = href.split("#")[0].split("?")[0].strip()
    if not value.startswith("/"):
        return value
    value = "/" + value.strip("/")
    return "/" if value == "/" else value + "/"


def _parse_iso_date(value: str) -> date | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _iso_from_stat(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).date().isoformat()


def _current_year() -> int:
    return date.today().year


def _priority_from_score(score: float) -> str:
    if score >= 80:
        return "Very High"
    if score >= 65:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


@dataclass(frozen=True)
class ArticleSnapshot:
    slug: str
    path: str
    topic: str
    cluster: str
    publish_date: str
    last_updated: str
    last_validation: str
    affiliate_products: list[str]
    traffic_estimate: int
    status: str
    word_count: int
    readability: float
    broken_links: int
    missing_schema: bool
    missing_disclosure: bool
    missing_cta: bool
    pricing_signal: bool
    version_signal: bool
    duplicate_competitors_detected: bool
    reasons: list[str]


@dataclass(frozen=True)
class AffiliateOpportunityRecord:
    keyword: str
    slug: str
    category: str
    article_type: str
    affiliate_opportunity_score: float
    monetization_priority: str
    matched_programs: list[str]
    commercial_intent: int
    search_intent: int
    existing_affiliate_programs: int
    estimated_commission: int
    estimated_conversion: int
    competition: int
    estimated_article_value: int
    content_difficulty: int
    topic_freshness: int
    seasonality: int
    reasoning: list[str]


@dataclass(frozen=True)
class LifecycleTransition:
    slug: str
    keyword: str
    from_stage: str
    to_stage: str
    changed_at: str
    context: dict[str, Any]


@dataclass(frozen=True)
class ContentGapRecord:
    keyword: str
    slug: str
    category: str
    roi_score: float
    recommended_article_type: str
    monetization_priority: str
    reason: str


@dataclass(frozen=True)
class AffiliateCoverageRecord:
    slug: str
    topic: str
    affiliate_disclosure: bool
    affiliate_links: int
    missing_products: list[str]
    expired_products: list[str]
    broken_links: int
    missing_cta: bool
    issues: list[str]


class ContentLifecycleManager:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or settings.data_dir
        self.state_path = self.data_dir / "content_lifecycle_state.json"
        self.log_path = self.data_dir / "content_lifecycle.jsonl"

    def record_transition(self, slug: str, keyword: str, to_stage: str, **context: Any) -> LifecycleTransition | None:
        state = _read_json(self.state_path, {})
        current = str(state.get(slug, "")).strip()
        if current == to_stage:
            return None
        transition = LifecycleTransition(
            slug=slug,
            keyword=keyword,
            from_stage=current or "unknown",
            to_stage=to_stage,
            changed_at=datetime.now(UTC).isoformat(),
            context=context,
        )
        state[slug] = to_stage
        _write_json(self.state_path, state)
        _append_jsonl(self.log_path, [asdict(transition)])
        return transition


class EditorialBusinessIntelligence:
    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        data_dir: Path | None = None,
        site_output_dir: Path | None = None,
        offers_file: Path | None = None,
        affiliate_links_file: Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_dir = base_dir or settings.base_dir
        self.data_dir = data_dir or settings.data_dir
        self.site_output_dir = site_output_dir or settings.site_output_dir
        self.offers_file = offers_file or settings.offers_file
        self.affiliate_links_file = affiliate_links_file or settings.affiliate_links_file
        self.config = config or settings.editorial_config
        self.lifecycle = ContentLifecycleManager(self.data_dir)
        self.offer_index = _load_offer_index(self.offers_file, self.affiliate_links_file)
        self.intelligence_config = self.config.get("business_intelligence", {})
        self.evergreen_config = self.intelligence_config.get("evergreen", {})
        self.opportunity_config = self.intelligence_config.get("affiliate_opportunity", {})
        self.coverage_config = self.intelligence_config.get("affiliate_coverage", {})
        self.gap_config = self.intelligence_config.get("content_gap", {})

    def run_weekly_intelligence(
        self,
        *,
        weekly_topics: list[dict[str, Any]],
        candidate_topics: list[dict[str, Any]],
        editorial_calendar: list[dict[str, Any]],
    ) -> dict[str, Any]:
        evergreen = self.build_evergreen_report()
        opportunities = self.build_affiliate_opportunities(weekly_topics, candidate_topics)
        gaps = self.build_content_gap_report(weekly_topics, opportunities)
        coverage = self.build_affiliate_coverage_report()
        history = self.append_weekly_history(weekly_topics)
        comparison = self.compare_topics_to_history(weekly_topics)
        dashboard = self.build_weekly_dashboard(
            weekly_topics=weekly_topics,
            opportunities=opportunities,
            gaps=gaps,
            evergreen=evergreen,
            coverage=coverage,
            editorial_calendar=editorial_calendar,
            historical_comparison=comparison,
        )
        return {
            "evergreen_report_json": str(self.data_dir / "evergreen_report.json"),
            "affiliate_opportunities_json": str(self.data_dir / "affiliate_opportunities.json"),
            "content_gap_report_json": str(self.data_dir / "content_gap_report.json"),
            "affiliate_coverage_report_json": str(self.data_dir / "affiliate_coverage_report.json"),
            "weekly_dashboard_json": str(self.data_dir / "weekly_dashboard.json"),
            "weekly_history_jsonl": str(self.data_dir / "weekly_history.jsonl"),
            "evergreen_articles": len(evergreen),
            "affiliate_opportunities": len(opportunities),
            "content_gaps": len(gaps),
            "affiliate_coverage_rows": len(coverage),
            "calendar_entries": len(editorial_calendar),
            "historical_topics_logged": history,
        }

    def build_evergreen_report(self) -> list[dict[str, Any]]:
        rows = [asdict(item) for item in self.scan_existing_articles()]
        _write_json(self.data_dir / "evergreen_report.json", rows)
        _write_csv(self.data_dir / "evergreen_report.csv", rows)
        lines = ["# Evergreen Content Manager Report", ""]
        lines.append(f"- Articles scanned: {len(rows)}")
        for status in STATUS_ORDER:
            lines.append(f"- {status}: {sum(1 for row in rows if row.get('status') == status)}")
        lines.extend(["", "## Highest Priority"])
        for row in sorted(rows, key=lambda item: STATUS_ORDER.index(item["status"]) if item["status"] in STATUS_ORDER else 0, reverse=True)[:10]:
            lines.append(f"- `{row['slug']}`: {row['status']} ({', '.join(row['reasons'][:3]) or 'no issues'})")
        _write_md(self.data_dir / "evergreen_report.md", lines)
        return rows

    def build_affiliate_opportunities(
        self,
        weekly_topics: list[dict[str, Any]],
        candidate_topics: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates_by_slug = {str(item.get("slug", "")): item for item in candidate_topics}
        records: list[AffiliateOpportunityRecord] = []
        for topic in weekly_topics:
            slug = str(topic.get("slug", ""))
            candidate = candidates_by_slug.get(slug, {})
            matches = self._matching_programs(str(topic.get("keyword", "")), str(topic.get("category", "")))
            commercial_intent = int(candidate.get("commercial_intent") or self._intent_score(str(topic.get("intent", ""))))
            search_intent = self._intent_score(str(topic.get("intent", "")))
            existing_programs = min(100, 25 * len(matches))
            estimated_commission = self._estimated_commission(matches)
            estimated_conversion = self._estimated_conversion(matches)
            competition = int(candidate.get("competition") or max(10, 100 - int(float(topic.get("score", 0)))))
            estimated_article_value = min(100, int(round(float(topic.get("score", 0)) + estimated_conversion * 0.2)))
            content_difficulty = min(100, int(round(competition * 0.7 + (100 - search_intent) * 0.3)))
            topic_freshness = int(candidate.get("freshness") or min(100, int(float(topic.get("score", 0)))))
            seasonality = self._seasonality_score(str(topic.get("keyword", "")))
            weights = {
                "commercial_intent": float(self.opportunity_config.get("commercial_intent_weight", 0.18)),
                "search_intent": float(self.opportunity_config.get("search_intent_weight", 0.10)),
                "existing_programs": float(self.opportunity_config.get("existing_programs_weight", 0.14)),
                "estimated_commission": float(self.opportunity_config.get("estimated_commission_weight", 0.12)),
                "estimated_conversion": float(self.opportunity_config.get("estimated_conversion_weight", 0.10)),
                "competition": float(self.opportunity_config.get("competition_weight", 0.10)),
                "estimated_article_value": float(self.opportunity_config.get("estimated_article_value_weight", 0.12)),
                "content_difficulty": float(self.opportunity_config.get("content_difficulty_weight", 0.08)),
                "topic_freshness": float(self.opportunity_config.get("topic_freshness_weight", 0.04)),
                "seasonality": float(self.opportunity_config.get("seasonality_weight", 0.02)),
            }
            score = (
                commercial_intent * weights["commercial_intent"]
                + search_intent * weights["search_intent"]
                + existing_programs * weights["existing_programs"]
                + estimated_commission * weights["estimated_commission"]
                + estimated_conversion * weights["estimated_conversion"]
                + (100 - competition) * weights["competition"]
                + estimated_article_value * weights["estimated_article_value"]
                + (100 - content_difficulty) * weights["content_difficulty"]
                + topic_freshness * weights["topic_freshness"]
                + seasonality * weights["seasonality"]
            )
            article_type = self._recommended_article_type(str(topic.get("keyword", "")), str(topic.get("article_type", "")))
            records.append(
                AffiliateOpportunityRecord(
                    keyword=str(topic.get("keyword", "")),
                    slug=slug,
                    category=str(topic.get("category", "")),
                    article_type=article_type,
                    affiliate_opportunity_score=round(score, 2),
                    monetization_priority=_priority_from_score(score),
                    matched_programs=[match.get("brand_name") or match.get("brand") or match.get("tool_name") or "" for match in matches][:5],
                    commercial_intent=commercial_intent,
                    search_intent=search_intent,
                    existing_affiliate_programs=existing_programs,
                    estimated_commission=estimated_commission,
                    estimated_conversion=estimated_conversion,
                    competition=competition,
                    estimated_article_value=estimated_article_value,
                    content_difficulty=content_difficulty,
                    topic_freshness=topic_freshness,
                    seasonality=seasonality,
                    reasoning=[
                        f"Matched {len(matches)} affiliate programs.",
                        f"Commercial intent scored {commercial_intent}.",
                        f"Competition scored {competition}.",
                    ],
                )
            )
        rows = [asdict(item) for item in sorted(records, key=lambda row: (-row.affiliate_opportunity_score, row.keyword.lower()))]
        _write_json(self.data_dir / "affiliate_opportunities.json", rows)
        _write_csv(self.data_dir / "affiliate_opportunities.csv", rows)
        return rows

    def build_content_gap_report(
        self,
        weekly_topics: list[dict[str, Any]],
        opportunities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        existing = self._existing_article_slugs()
        opportunity_by_slug = {str(item.get("slug", "")): item for item in opportunities}
        records: list[ContentGapRecord] = []
        for topic in weekly_topics:
            slug = str(topic.get("slug", ""))
            if slug in existing:
                continue
            opportunity = opportunity_by_slug.get(slug, {})
            score = float(opportunity.get("affiliate_opportunity_score", topic.get("score", 0)))
            records.append(
                ContentGapRecord(
                    keyword=str(topic.get("keyword", "")),
                    slug=slug,
                    category=str(topic.get("category", "")),
                    roi_score=round(score, 2),
                    recommended_article_type=str(opportunity.get("article_type") or topic.get("article_type", "")),
                    monetization_priority=str(opportunity.get("monetization_priority") or "Medium"),
                    reason="Weekly trend is not covered by an existing published article.",
                )
            )
        rows = [asdict(item) for item in sorted(records, key=lambda row: (-row.roi_score, row.keyword.lower()))]
        _write_json(self.data_dir / "content_gap_report.json", rows)
        _write_csv(self.data_dir / "content_gap_report.csv", rows)
        _write_md(
            self.data_dir / "content_gap_report.md",
            ["# Content Gap Report", "", *[f"- `{row['slug']}`: ROI {row['roi_score']} ({row['reason']})" for row in rows[:20]]],
        )
        return rows

    def build_affiliate_coverage_report(self) -> list[dict[str, Any]]:
        snapshots = self.scan_existing_articles()
        rows: list[dict[str, Any]] = []
        for item in snapshots:
            missing_products = self._expected_products(item.topic, item.cluster, item.affiliate_products)
            expired = [product for product in item.affiliate_products if re.search(r"\b20(1\d|2[0-5])\b", item.topic)]
            issues: list[str] = []
            if item.missing_disclosure:
                issues.append("missing affiliate disclosure")
            if not item.affiliate_products:
                issues.append("missing affiliate links")
            if missing_products:
                issues.append("missing products")
            if expired:
                issues.append("expired products")
            if item.broken_links:
                issues.append("broken links")
            if item.missing_cta:
                issues.append("missing CTA")
            rows.append(
                asdict(
                    AffiliateCoverageRecord(
                        slug=item.slug,
                        topic=item.topic,
                        affiliate_disclosure=not item.missing_disclosure,
                        affiliate_links=len(item.affiliate_products),
                        missing_products=missing_products,
                        expired_products=expired,
                        broken_links=item.broken_links,
                        missing_cta=item.missing_cta,
                        issues=issues,
                    )
                )
            )
        _write_json(self.data_dir / "affiliate_coverage_report.json", rows)
        _write_csv(self.data_dir / "affiliate_coverage_report.csv", rows)
        _write_md(
            self.data_dir / "affiliate_coverage_report.md",
            ["# Affiliate Coverage Report", "", *[f"- `{row['slug']}`: {', '.join(row['issues']) or 'OK'}" for row in rows[:20]]],
        )
        return rows

    def append_weekly_history(self, weekly_topics: list[dict[str, Any]]) -> int:
        stamp = datetime.now(UTC).isoformat()
        rows = [{"logged_at": stamp, **topic} for topic in weekly_topics]
        _append_jsonl(self.data_dir / "weekly_history.jsonl", rows)
        return len(rows)

    def compare_topics_to_history(self, weekly_topics: list[dict[str, Any]]) -> dict[str, list[str]]:
        path = self.data_dir / "weekly_history.jsonl"
        seen: list[dict[str, Any]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    seen.append(json.loads(line))
                except Exception:
                    continue
        previous_keywords = [str(item.get("keyword", "")) for item in seen[:-len(weekly_topics)] if item.get("keyword")]
        lower_previous = [item.lower() for item in previous_keywords]
        result = {
            "returning_topics": [],
            "evergreen_topics": [],
            "seasonal_topics": [],
            "emerging_topics": [],
            "dead_topics": [],
        }
        for topic in weekly_topics:
            keyword = str(topic.get("keyword", ""))
            lower = keyword.lower()
            if lower in lower_previous:
                result["returning_topics"].append(keyword)
            if any(token in lower for token in ("best", "guide", "review", "pricing", "comparison")):
                result["evergreen_topics"].append(keyword)
            if any(token in lower for token in ("holiday", "black friday", "summer", "winter", "monday")):
                result["seasonal_topics"].append(keyword)
            if lower not in lower_previous:
                result["emerging_topics"].append(keyword)
        current_keywords = {str(topic.get("keyword", "")).lower() for topic in weekly_topics}
        for previous in previous_keywords:
            if previous.lower() not in current_keywords:
                result["dead_topics"].append(previous)
        return {key: sorted(dict.fromkeys(value))[:10] for key, value in result.items()}

    def build_weekly_dashboard(
        self,
        *,
        weekly_topics: list[dict[str, Any]],
        opportunities: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        evergreen: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        editorial_calendar: list[dict[str, Any]],
        historical_comparison: dict[str, list[str]],
    ) -> dict[str, Any]:
        production_summary = {
            "weekly_topics": len(weekly_topics),
            "calendar_entries": len(editorial_calendar),
            "gaps": len(gaps),
            "articles_needing_updates": sum(1 for row in evergreen if row.get("status") in {"Needs Update", "Outdated", "Deprecated", "Broken"}),
        }
        validation_summary = self._latest_validation_summary()
        evergreen_score = round(sum(self._evergreen_points(row.get("status", "")) for row in evergreen) / max(1, len(evergreen)), 2)
        business_score = round(sum(float(row.get("affiliate_opportunity_score", 0)) for row in opportunities[:10]) / max(1, min(10, len(opportunities))), 2)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "top_topics": weekly_topics[:10],
            "affiliate_opportunities": opportunities[:10],
            "content_gaps": gaps[:10],
            "articles_needing_updates": [row for row in evergreen if row.get("status") != "Fresh"][:10],
            "evergreen_score": evergreen_score,
            "business_score": business_score,
            "production_summary": production_summary,
            "validation_summary": validation_summary,
            "historical_comparison": historical_comparison,
            "affiliate_coverage_issues": [row for row in coverage if row.get("issues")][:10],
        }
        _write_json(self.data_dir / "weekly_dashboard.json", payload)
        _write_csv(
            self.data_dir / "weekly_dashboard.csv",
            [
                {"section": "top_topics", "count": len(payload["top_topics"])},
                {"section": "affiliate_opportunities", "count": len(payload["affiliate_opportunities"])},
                {"section": "content_gaps", "count": len(payload["content_gaps"])},
                {"section": "articles_needing_updates", "count": len(payload["articles_needing_updates"])},
                {"section": "affiliate_coverage_issues", "count": len(payload["affiliate_coverage_issues"])},
                {"section": "evergreen_score", "count": evergreen_score},
                {"section": "business_score", "count": business_score},
            ],
        )
        lines = [
            "# Weekly Executive Report",
            "",
            f"- Evergreen score: {evergreen_score}",
            f"- Business score: {business_score}",
            f"- Weekly topics: {len(weekly_topics)}",
            f"- Content gaps: {len(gaps)}",
            f"- Articles needing updates: {production_summary['articles_needing_updates']}",
            "",
            "## Top 10 Topics",
        ]
        for topic in payload["top_topics"]:
            lines.append(f"- `{topic['slug']}`: {topic['keyword']}")
        lines.extend(["", "## Affiliate Opportunities"])
        for row in payload["affiliate_opportunities"]:
            lines.append(f"- `{row['slug']}`: score {row['affiliate_opportunity_score']} ({row['monetization_priority']})")
        lines.extend(["", "## Content Gaps"])
        for row in payload["content_gaps"]:
            lines.append(f"- `{row['slug']}`: ROI {row['roi_score']}")
        lines.extend(["", "## Historical Comparison"])
        for label, items in historical_comparison.items():
            lines.append(f"- {label}: {', '.join(items) if items else 'None'}")
        _write_md(self.data_dir / "weekly_dashboard.md", lines)
        return payload

    def scan_existing_articles(self) -> list[ArticleSnapshot]:
        rows: list[ArticleSnapshot] = []
        similarity_threshold = float(self.evergreen_config.get("duplicate_similarity_threshold", 0.72))
        pages = sorted(self.site_output_dir.rglob("index.html")) if self.site_output_dir.exists() else []
        page_titles: list[tuple[str, str]] = []
        page_data: list[tuple[Path, str, str]] = []
        for path in pages:
            slug = _slug_from_path(path, self.site_output_dir)
            if not slug or slug.startswith(("go/", "assets/", "categories/", "hubs/")):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            title = _extract_single(r"<h1\b[^>]*>(.*?)</h1>", text) or _extract_single(r"<title\b[^>]*>(.*?)</title>", text)
            page_titles.append((slug, _strip_html(title)))
            page_data.append((path, slug, text))
        duplicate_slugs: set[str] = set()
        for left_index, (left_slug, left_title) in enumerate(page_titles):
            for right_slug, right_title in page_titles[left_index + 1 :]:
                if _similarity(left_title, right_title) >= similarity_threshold:
                    duplicate_slugs.add(left_slug)
                    duplicate_slugs.add(right_slug)
        for path, slug, text in page_data:
            title = _strip_html(_extract_single(r"<h1\b[^>]*>(.*?)</h1>", text) or _extract_single(r"<title\b[^>]*>(.*?)</title>", text) or slug)
            published = _extract_single(r'"datePublished"\s*:\s*"([^"]+)"', text) or _iso_from_stat(path.stat().st_ctime)
            modified = _extract_single(r'"dateModified"\s*:\s*"([^"]+)"', text) or _iso_from_stat(path.stat().st_mtime)
            validation = self._last_validation_for_slug(slug) or modified
            plain = _strip_html(text)
            words = re.findall(r"\b[\w'-]+\b", plain)
            sentences = [piece.strip() for piece in re.split(r"[.!?]+", plain) if piece.strip()]
            readability = self._readability_score(words, sentences)
            broken_links = self._broken_links(text)
            missing_schema = "application/ld+json" not in text
            missing_disclosure = "affiliate disclosure" not in text.lower() and "affiliate links" not in text.lower()
            missing_cta = not any(marker.lower() in text.lower() for marker in ("visit official website", "read review", "check pricing", "start free trial"))
            products = self._affiliate_products_for_page(text, title)
            reasons: list[str] = []
            status = self._classify_article_status(
                slug=slug,
                topic=title,
                publish_date=published,
                last_updated=modified,
                word_count=len(words),
                readability=readability,
                broken_links=broken_links,
                missing_schema=missing_schema,
                missing_disclosure=missing_disclosure,
                missing_cta=missing_cta,
                duplicate_competitors=slug in duplicate_slugs,
                reasons=reasons,
            )
            rows.append(
                ArticleSnapshot(
                    slug=slug,
                    path=str(path),
                    topic=title,
                    cluster=self._cluster_for_slug(slug),
                    publish_date=published[:10],
                    last_updated=modified[:10],
                    last_validation=validation[:10],
                    affiliate_products=products,
                    traffic_estimate=0,
                    status=status,
                    word_count=len(words),
                    readability=readability,
                    broken_links=broken_links,
                    missing_schema=missing_schema,
                    missing_disclosure=missing_disclosure,
                    missing_cta=missing_cta,
                    pricing_signal="pricing" in title.lower() or "pricing" in slug.lower(),
                    version_signal=bool(re.search(r"\b20(1\d|2[0-5])\b", title)),
                    duplicate_competitors_detected=slug in duplicate_slugs,
                    reasons=reasons,
                )
            )
            self.lifecycle.record_transition(slug, title, status.lower().replace(" ", "_"), source="evergreen_manager")
        return sorted(rows, key=lambda item: (-STATUS_ORDER.index(item.status), item.slug) if item.status in STATUS_ORDER else (0, item.slug))

    def _classify_article_status(
        self,
        *,
        slug: str,
        topic: str,
        publish_date: str,
        last_updated: str,
        word_count: int,
        readability: float,
        broken_links: int,
        missing_schema: bool,
        missing_disclosure: bool,
        missing_cta: bool,
        duplicate_competitors: bool,
        reasons: list[str],
    ) -> str:
        review_after_days = int(self.evergreen_config.get("review_after_days", 30))
        update_after_days = int(self.evergreen_config.get("update_after_days", 90))
        outdated_after_days = int(self.evergreen_config.get("outdated_after_days", 180))
        deprecated_after_days = int(self.evergreen_config.get("deprecated_after_days", 365))
        min_word_count = int(self.evergreen_config.get("min_word_count", 500))
        min_readability = float(self.evergreen_config.get("min_readability_score", 45))
        today = date.today()
        published_date = _parse_iso_date(publish_date) or today
        updated_date = _parse_iso_date(last_updated) or published_date
        age_days = (today - updated_date).days
        legacy_year = bool(re.search(r"\b20(1\d|2[0-5])\b", topic))

        if broken_links >= int(self.evergreen_config.get("broken_links_threshold", 1)):
            reasons.append("broken links detected")
            return "Broken"
        if age_days >= deprecated_after_days and legacy_year:
            reasons.append("legacy year marker exceeded deprecated threshold")
            return "Deprecated"
        if age_days >= outdated_after_days or ("pricing" in slug and age_days >= update_after_days):
            reasons.append("article age exceeded outdated threshold")
            return "Outdated"
        if missing_schema:
            reasons.append("missing schema")
        if word_count < min_word_count:
            reasons.append("low word count")
        if readability < min_readability:
            reasons.append("poor readability")
        if duplicate_competitors:
            reasons.append("duplicate competitors detected")
        if missing_cta:
            reasons.append("missing CTA")
        if missing_disclosure:
            reasons.append("affiliate disclosure missing")
        if reasons:
            return "Needs Update"
        if (today - published_date).days >= review_after_days:
            reasons.append("older than review threshold")
            return "Needs Review"
        return "Fresh"

    def _matching_programs(self, keyword: str, category: str) -> list[dict[str, Any]]:
        lower_keyword = keyword.lower()
        lower_category = category.lower()
        matches: list[dict[str, Any]] = []
        for row in self.offer_index:
            brand = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").strip()
            niche = str(row.get("niche") or row.get("category") or "").strip()
            if brand and brand.lower() in lower_keyword:
                matches.append(row)
            elif niche and niche.lower() in lower_category:
                matches.append(row)
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in matches:
            key = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def _estimated_commission(self, matches: list[dict[str, Any]]) -> int:
        best = 0.0
        for row in matches:
            rate = float(str(row.get("commission_rate") or 0).strip() or 0)
            flat = float(str(row.get("flat_commission") or 0).strip() or 0)
            normalized = min(100, rate if rate else flat / 10)
            best = max(best, normalized)
        return int(round(best))

    def _estimated_conversion(self, matches: list[dict[str, Any]]) -> int:
        scores: list[float] = []
        for row in matches:
            value = str(row.get("buyer_intent") or 0).strip() or "0"
            try:
                scores.append(float(value))
            except ValueError:
                continue
        return int(round(sum(scores) / len(scores))) if scores else 35

    def _intent_score(self, intent: str) -> int:
        lower = intent.lower()
        if "commercial" in lower or "buy" in lower:
            return 90
        if "comparison" in lower:
            return 82
        if "transactional" in lower:
            return 85
        if "informational" in lower:
            return 60
        return 55

    def _seasonality_score(self, keyword: str) -> int:
        lower = keyword.lower()
        if any(token in lower for token in ("black friday", "christmas", "summer", "winter", "q4")):
            return 85
        if re.search(r"\b20\d{2}\b", lower):
            return 65
        return 45

    def _recommended_article_type(self, keyword: str, article_type: str) -> str:
        lower = keyword.lower()
        if "vs" in lower or "compare" in lower:
            return "Comparison"
        if "best" in lower:
            return "Best Of"
        if "alternative" in lower:
            return "Alternative"
        if "pricing" in lower:
            return "Pricing"
        if "faq" in lower:
            return "FAQ"
        if "tutorial" in lower or "how to" in lower:
            return "Tutorial"
        if article_type:
            return article_type.title()
        return "Guide"

    def _latest_validation_summary(self) -> dict[str, Any]:
        report_dir = self.data_dir / "content_growth_reports"
        reports = sorted(report_dir.glob("production-pipeline-validation-*.json"))
        if not reports:
            return {"status": "missing", "report": ""}
        payload = _read_json(reports[-1], {})
        return {
            "status": "available",
            "report": str(reports[-1]),
            "pages_generated": payload.get("pages_generated", 0),
            "errors": payload.get("errors", []),
            "broken_links": payload.get("broken_links", []),
            "duplicate_titles": payload.get("duplicate_titles", {}),
            "duplicate_descriptions": payload.get("duplicate_descriptions", {}),
        }

    def _last_validation_for_slug(self, slug: str) -> str:
        report_dir = self.data_dir / "content_growth_reports"
        for path in sorted(report_dir.glob("production-pipeline-validation-*.json"), reverse=True):
            payload = _read_json(path, {})
            for row in payload.get("page_validations", []):
                if str(row.get("slug", "")) == slug:
                    stamp = payload.get("generated_at") or datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
                    return str(stamp)
        return ""

    def _evergreen_points(self, status: str) -> int:
        return {
            "Fresh": 100,
            "Needs Review": 75,
            "Needs Update": 50,
            "Outdated": 25,
            "Deprecated": 10,
            "Broken": 0,
        }.get(status, 0)

    def _existing_article_slugs(self) -> set[str]:
        return {item.slug for item in self.scan_existing_articles()}

    def _cluster_for_slug(self, slug: str) -> str:
        if "/" in slug:
            return slug.split("/", 1)[0]
        for token in ("review", "comparisons", "compare", "pricing", "category", "blog", "best"):
            if token in slug:
                return token
        return "general"

    def _affiliate_products_for_page(self, text: str, title: str) -> list[str]:
        links = [_normalize_href(link) for link in _find_links(text)]
        products = [link.split("/")[2] for link in links if link.startswith("/go/") and len(link.split("/")) > 2]
        for row in self.offer_index:
            brand = str(row.get("brand_name") or row.get("brand") or row.get("tool_name") or "").strip()
            if brand and brand.lower() in title.lower():
                products.append(brand)
        seen: set[str] = set()
        result: list[str] = []
        for item in products:
            normalized = item.lower()
            if not item or normalized in seen:
                continue
            seen.add(normalized)
            result.append(item)
        return result[:10]

    def _expected_products(self, topic: str, cluster: str, present: list[str]) -> list[str]:
        matches = self._matching_programs(topic, cluster)
        expected = [str(match.get("brand_name") or match.get("brand") or match.get("tool_name") or "") for match in matches]
        present_lower = {item.lower() for item in present}
        return [item for item in expected if item and item.lower() not in present_lower][:5]

    def _broken_links(self, text: str) -> int:
        count = 0
        for href in _find_links(text):
            normalized = _normalize_href(href)
            if not normalized.startswith("/") or normalized.startswith(("/assets/", "/rss.xml", "/robots.txt", "/sitemap.xml", "/llms.txt")):
                continue
            target = self.site_output_dir / normalized.strip("/") / "index.html" if normalized != "/" else self.site_output_dir / "index.html"
            if not target.exists():
                count += 1
        return count

    def _readability_score(self, words: list[str], sentences: list[str]) -> float:
        if not words:
            return 0.0
        sentence_count = max(1, len(sentences))
        avg_sentence = len(words) / sentence_count
        long_words = sum(1 for word in words if len(word) >= 7)
        penalty = avg_sentence * 1.4 + (100 * long_words / len(words)) * 0.6
        return round(max(0.0, min(100.0, 100 - penalty)), 2)

