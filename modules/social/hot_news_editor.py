from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from modules.ai_trend_discovery import TopicCandidate, TrendDiscoveryEngine, TrendSignal
from modules.affiliate_opportunity_discovery import AffiliateOpportunityDiscovery
from modules.operations_intelligence.editorial_memory import EditorialMemoryStore
from modules.operations_intelligence.feature_flags import feature_enabled
from modules.operations_intelligence.social_signal_ingestion import menu_h_signal_advisory

from .draft_workflow import HOT_NEWS_MONITORING_PLATFORMS, SocialDraftWorkflow
from .utils import ROOT, now_iso


SOCIAL_HOT_DRAFT = "SOCIAL_HOT_DRAFT"
SOCIAL_HOT_UNCONFIRMED = "SOCIAL_HOT_UNCONFIRMED"
SCORING_PROFILE = "SOCIAL_HOT_NEWS_V2"
DEFAULT_CONFIG_PATH = Path("config/social_hot.json")
FREE_CONNECTORS = {
    "google_trends",
    "bing_trending",
    "reddit",
    "hacker_news",
    "product_hunt",
    "github_trending",
    "ai_newsletters",
    "local_keyword_intelligence",
}
DEFAULT_WEIGHTS = {
    "recency": 22,
    "source_authority": 17,
    "user_business_impact": 16,
    "official_confirmation": 13,
    "novelty": 9,
    "social_discussion_potential": 8,
    "practical_relevance": 7,
    "company_significance": 5,
    "evidence_confidence": 3,
}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
DEFAULT_PENALTIES = {
    "duplicate_event": 40,
    "near_duplicate_story": 25,
    "staleness": 35,
    "low_authority_only": 25,
    "recycled_seo_content": 25,
    "opinion_without_event": 20,
    "weak_user_relevance": 15,
}
DEFAULT_COMPANY_FAMILIES = {
    "OpenAI": ("OpenAI", "ChatGPT", "Codex", "GPT", "Sora"),
    "Google": ("Google", "Google DeepMind", "Gemini", "DeepMind", "NotebookLM"),
    "Anthropic": ("Anthropic", "Claude", "Claude Code"),
    "GitHub/Copilot": ("GitHub", "GitHub Copilot", "GitHub Mobile", "GitHub Actions", "Copilot"),
    "Microsoft": ("Microsoft", "Microsoft Copilot", "Azure AI"),
    "Amazon": ("Amazon", "AWS", "Bedrock", "SageMaker"),
    "Meta": ("Meta", "Meta AI", "Llama"),
    "NVIDIA": ("NVIDIA", "CUDA", "GeForce"),
    "xAI": ("xAI", "Grok"),
    "Perplexity": ("Perplexity",),
    "Hugging Face": ("Hugging Face", "HuggingFace"),
    "Apple": ("Apple", "Apple Intelligence"),
}
DEFAULT_BREAKING_NEWS_CATEGORIES = {
    "MODEL_RELEASE",
    "MAJOR_PRODUCT_LAUNCH",
    "ACQUISITION",
    "OUTAGE_SECURITY",
}
DEFAULT_EDITORIAL_ECOSYSTEMS = {
    "AI coding tools": {
        "categories": ("CODING_AI", "DEVELOPER_PLATFORM"),
        "keywords": ("copilot", "coding agent", "claude code", "codex", "developer tools", "sdk"),
    },
    "Foundation models": {
        "categories": ("MODEL_RELEASE", "MODEL_PREVIEW"),
        "keywords": ("gpt", "claude", "gemini", "llama", "foundation model"),
    },
    "AI product access and pricing": {
        "categories": ("ACCESS_CHANGE", "PRICING_CHANGE"),
        "keywords": ("pricing", "subscription", "availability", "rollout", "access"),
    },
    "AI business and policy": {
        "categories": ("ACQUISITION", "MAJOR_PARTNERSHIP", "POLICY_REGULATION"),
        "keywords": ("acquisition", "acquire", "partnership", "regulation", "policy"),
    },
    "AI safety and reliability": {
        "categories": ("OUTAGE_SECURITY", "SAFETY_ANNOUNCEMENT"),
        "keywords": ("outage", "security", "safety", "incident", "alignment"),
    },
    "AI research and evaluation": {
        "categories": ("BENCHMARK", "RESEARCH"),
        "keywords": ("benchmark", "research", "paper", "evaluation"),
    },
}
EVENT_CATEGORIES = [
    ("PRICING_CHANGE", ("pricing", "price change", "plan change", "subscription")),
    ("OUTAGE_SECURITY", ("outage", "security incident", "breach", "vulnerability")),
    ("POLICY_REGULATION", ("regulation", "policy", "regulator", "law", "executive order")),
    ("ACQUISITION", ("acquire", "acquisition", "merger")),
    ("MAJOR_PARTNERSHIP", ("partnership", "partners with", "strategic alliance")),
    ("MODEL_PREVIEW", ("model preview", "preview model")),
    ("MODEL_RELEASE", ("model release", "releases model", "launches model", "new model")),
    ("DEVELOPER_PLATFORM", ("api launch", "developer platform", "sdk", "developer tools")),
    ("CODING_AI", ("coding agent", "copilot", "claude code", "codex", "ai coding")),
    ("ACCESS_CHANGE", ("access change", "now available", "rollout", "availability")),
    ("MAJOR_FEATURE_LAUNCH", ("major update", "new feature", "feature launch")),
    ("MAJOR_PRODUCT_LAUNCH", ("product launch", "launches", "released")),
    ("SAFETY_ANNOUNCEMENT", ("safety", "alignment", "responsible ai")),
    ("BENCHMARK", ("benchmark", "leaderboard", "evaluation")),
    ("RESEARCH", ("research", "paper", "arxiv")),
    ("GENERIC_COMPARISON", ("comparison", "alternatives", "best ai tools", "top ai tools")),
    ("GENERIC_REVIEW", (" review ", "review 2026", "pros and cons")),
]
EVENT_STOP_WORDS = {
    "ai", "the", "a", "an", "and", "for", "to", "of", "with", "new", "major",
    "launch", "launches", "release", "releases", "update", "updates", "announces",
    "announcement", "model", "official", "review", "2025", "2026",
}
AI_SCOPE_TERMS = {
    "ai", "artificial intelligence", "llm", "model", "machine learning", "openai",
    "chatgpt", "gpt", "anthropic", "claude", "gemini", "deepmind", "copilot",
    "nvidia", "cuda", "xai", "grok", "perplexity", "hugging face", "agent",
    "automation", "developer platform", "coding",
}
UNSAFE_EVENT_MARKERS = {
    "steal credentials", "build malware", "deploy ransomware", "bypass authentication",
}
CANONICAL_REASON_CODES = {
    "SELECTED_TIER_A",
    "SELECTED_TIER_B",
    "SELECTED_EDITORIAL_DIVERSITY",
    "SELECTED_DAILY_PORTFOLIO_PRIMARY",
    "SELECTED_DAILY_PORTFOLIO_DIVERSITY",
    "SELECTED_BREAKING_SAME_FAMILY_EXCEPTION",
    "REJECTED_STALE",
    "REJECTED_LOW_AUTHORITY",
    "REJECTED_DUPLICATE_EVENT",
    "REJECTED_LOW_IMPACT",
    "REJECTED_UNVERIFIABLE",
    "REJECTED_BELOW_SOCIAL_THRESHOLD",
    "REJECTED_DIVERSITY_SOFT_CAP",
    "REJECTED_INVALID_URL",
    "REJECTED_MISSING_TITLE",
    "REJECTED_MISSING_DATE",
    "REJECTED_OUT_OF_SCOPE",
    "REJECTED_UNSAFE_TO_DESCRIBE",
    "REJECTED_REUSED_SEO_CONTENT",
    "REJECTED_NOT_A_NEW_EVENT",
    "REJECTED_MAX_REACHED",
    "REJECTED_DAILY_FAMILY_DUPLICATE",
    "REJECTED_DAILY_ECOSYSTEM_DUPLICATE",
    "REJECTED_DAILY_PORTFOLIO_LIMIT",
}


def load_social_hot_config(root: Path = ROOT) -> dict[str, Any]:
    path = root / DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = payload.get("social_hot") if isinstance(payload, dict) else {}
    return config if isinstance(config, dict) else {}


def _domain(url: str) -> str:
    return urlparse(str(url or "")).netloc.lower().removeprefix("www.")


def _valid_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _event_tokens(title: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(title or "").lower())
        if len(token) > 2 and token not in EVENT_STOP_WORDS
    }


def _same_event(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("company") != right.get("company"):
        return False
    left_tokens = set(left.get("event_tokens") or [])
    right_tokens = set(right.get("event_tokens") or [])
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap >= 2 and overlap / min(len(left_tokens), len(right_tokens)) >= 0.55


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 1)


class SocialHotEditor:
    """Local-first AI news editor used only by Menu H."""

    def __init__(
        self,
        *,
        root: Path = ROOT,
        config: dict[str, Any] | None = None,
        discovery: TrendDiscoveryEngine | None = None,
        now: datetime | None = None,
    ) -> None:
        self.root = root
        self.config = dict(config if config is not None else load_social_hot_config(root))
        self.discovery = discovery or TrendDiscoveryEngine(
            max_per_source=int(self.config.get("max_per_source", 40) or 40),
            read_only=True,
        )
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self._evidence_by_url: dict[str, dict[str, Any]] = {}
        self.affiliate_discovery = AffiliateOpportunityDiscovery(self.root, now=self.now)

    def _discover_candidates(self) -> tuple[list[TopicCandidate], dict[str, dict[str, Any]], int]:
        signals = []
        enabled = [str(item) for item in self.config.get("free_sources") or []]
        for source in enabled:
            if source not in FREE_CONNECTORS:
                self.discovery.source_status[source] = {
                    "status": "rejected", "signals": 0,
                    "detail": "Source is not in the free no-key connector allowlist.",
                }
                continue
            try:
                found = getattr(self.discovery, source)()[: self.discovery.max_per_source]
                signals.extend(found)
                self.discovery.source_status[source] = {
                    "status": "ok" if found else "empty", "signals": len(found),
                }
            except Exception as exc:
                self.discovery.source_status[source] = {
                    "status": "error", "signals": 0,
                    "detail": f"{type(exc).__name__}: {exc}",
                }

        for feed in self.config.get("free_feeds") or []:
            if not isinstance(feed, dict):
                continue
            name = str(feed.get("name") or "public_feed").strip()
            url = str(feed.get("url") or "").strip()
            if not _valid_url(url):
                self.discovery.source_status[name] = {
                    "status": "rejected", "signals": 0, "detail": "Public feed URL is missing or invalid.",
                }
                continue
            try:
                found = self.discovery.rss(url, name)[: self.discovery.max_per_source]
                signals.extend(found)
                self.discovery.source_status[name] = {
                    "status": "ok" if found else "empty", "signals": len(found),
                }
            except Exception as exc:
                self.discovery.source_status[name] = {
                    "status": "error", "signals": 0,
                    "detail": f"{type(exc).__name__}: {exc}",
                }

        for page in self.config.get("free_public_pages") or []:
            if not isinstance(page, dict):
                continue
            name = str(page.get("name") or "public_page").strip()
            url = str(page.get("url") or "").strip()
            if not _valid_url(url):
                self.discovery.source_status[name] = {
                    "status": "rejected", "signals": 0, "detail": "Public page URL is missing or invalid.",
                }
                continue
            try:
                response = self.discovery.get(url)
                soup = BeautifulSoup(response.text, "html.parser")
                title = _clean_text(
                    (soup.find("h1").get_text(" ") if soup.find("h1") else "")
                    or (soup.find("title").get_text(" ") if soup.find("title") else "")
                    or str(page.get("title") or name)
                )
                description_tag = soup.find("meta", attrs={"name": "description"})
                description = _clean_text(
                    str(description_tag.get("content") or "") if description_tag else str(page.get("description") or "")
                )
                found = [TrendSignal(title, name, url, description=description)] if title else []
                signals.extend(found)
                self.discovery.source_status[name] = {
                    "status": "ok" if found else "empty", "signals": len(found),
                }
            except Exception as exc:
                self.discovery.source_status[name] = {
                    "status": "error", "signals": 0,
                    "detail": f"{type(exc).__name__}: {exc}",
                }

        for signal in signals:
            url = str(getattr(signal, "url", "") or "")
            if url:
                self._evidence_by_url[url] = {
                    "source": str(getattr(signal, "source", "") or ""),
                    "published_at": str(getattr(signal, "published_at", "") or ""),
                    "description": str(getattr(signal, "description", "") or ""),
                    "title": str(getattr(signal, "title", "") or ""),
                }
        pool_limit = max(60, int(self.config.get("max_topics", 3) or 3) * 40)
        candidates = self.discovery.enrich_candidate_sources(
            self.discovery.aggregate(signals), pool_limit=pool_limit,
        )
        return candidates, dict(self.discovery.source_status), len(signals)

    def _organization(self, title: str, urls: list[str]) -> str:
        official_domains = dict(self.config.get("official_domains") or {})
        for url in urls:
            domain = _domain(url)
            for official_domain, company in official_domains.items():
                if domain == official_domain or domain.endswith("." + official_domain):
                    return str(company)
        normalized = str(title or "").lower()
        for company, aliases in dict(self.config.get("organizations") or {}).items():
            if any(re.search(rf"(?<![a-z0-9]){re.escape(str(alias).lower())}(?![a-z0-9])", normalized) for alias in aliases):
                return str(company)
        return "Independent"

    def _company_family(self, item: dict[str, Any]) -> str:
        configured = self.config.get("company_families")
        family_map = configured if isinstance(configured, dict) and configured else DEFAULT_COMPANY_FAMILIES
        company = str(item.get("company") or "").strip()
        title = str(item.get("title") or "").strip()
        for search_value in (company, title):
            for family, raw_aliases in family_map.items():
                aliases = raw_aliases if isinstance(raw_aliases, (list, tuple)) else [raw_aliases]
                for alias in aliases:
                    token = str(alias or "").strip()
                    if not token:
                        continue
                    pattern = rf"(?<![a-z0-9]){re.escape(token.lower())}(?![a-z0-9])"
                    if re.search(pattern, search_value.lower()):
                        return str(family)
        if company and company != "Independent":
            return company
        publisher = str(item.get("publisher") or "").strip()
        return f"Independent ({publisher})" if publisher else "Independent"

    def _is_breaking_news(self, item: dict[str, Any]) -> bool:
        configured = self.config.get("breaking_news_categories")
        categories = (
            {str(value) for value in configured}
            if isinstance(configured, list) and configured
            else DEFAULT_BREAKING_NEWS_CATEGORIES
        )
        return str(item.get("category") or "") in categories

    def _editorial_ecosystem(self, item: dict[str, Any]) -> str:
        configured = self.config.get("editorial_ecosystems")
        rules = configured if isinstance(configured, dict) and configured else DEFAULT_EDITORIAL_ECOSYSTEMS
        category = str(item.get("category") or "").strip()
        title = str(item.get("title") or "").lower()
        keyword_match = ""
        for ecosystem, raw_rule in rules.items():
            rule = raw_rule if isinstance(raw_rule, dict) else {}
            categories = {str(value) for value in rule.get("categories") or []}
            if category in categories:
                return str(ecosystem)
            if not keyword_match:
                keywords = [str(value).lower() for value in rule.get("keywords") or []]
                if any(keyword and keyword in title for keyword in keywords):
                    keyword_match = str(ecosystem)
        if keyword_match:
            return keyword_match
        return category.replace("_", " ").title() if category else "General AI"

    @staticmethod
    def _confidence_rank(item: dict[str, Any]) -> int:
        return {"high": 3, "medium": 2, "low": 1}.get(str(item.get("confidence") or "").lower(), 0)

    def _qualifies_breaking_exception(
        self,
        candidate: dict[str, Any],
        same_family_selected: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> bool:
        if not bool(policy.get("allow_same_family_breaking_exception", True)):
            return False
        if str(candidate.get("selection_tier") or "") != "A":
            return False
        if bool(policy.get("require_official_confirmation_for_exception", True)) and not bool(
            candidate.get("official_confirmed")
        ):
            return False
        if float(candidate.get("final_score") or 0) < float(policy.get("breaking_exception_min_score", 92)):
            return False
        if float(candidate.get("impact_score") or 0) < float(
            policy.get("breaking_exception_min_impact_score", 75)
        ):
            return False
        if not self._is_breaking_news(candidate):
            return False
        for selected in same_family_selected:
            if str(selected.get("selection_tier") or "") != "A":
                continue
            if str(selected.get("event_cluster_id") or "") == str(candidate.get("event_cluster_id") or ""):
                continue
            if str(selected.get("category") or "") == str(candidate.get("category") or ""):
                continue
            if not self._is_breaking_news(selected):
                continue
            if bool(policy.get("require_official_confirmation_for_exception", True)) and not bool(
                selected.get("official_confirmed")
            ):
                continue
            if float(selected.get("final_score") or 0) < float(
                policy.get("breaking_exception_min_score", 92)
            ):
                continue
            if float(selected.get("impact_score") or 0) < float(
                policy.get("breaking_exception_min_impact_score", 75)
            ):
                continue
            return True
        return False

    def _daily_editorial_portfolio(
        self,
        eligible: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        raw_policy = self.config.get("daily_editorial_portfolio")
        policy = dict(raw_policy) if isinstance(raw_policy, dict) else {}
        max_selected = max(
            0,
            min(
                3,
                int(policy.get("max_selected", self.config.get("max_topics", 3)) or 0),
            ),
        )
        family_cap = max(1, int(policy.get("default_max_per_company_family", 1) or 1))
        ecosystem_cap = max(1, int(policy.get("default_max_per_editorial_ecosystem", 1) or 1))
        ordered = sorted(
            eligible,
            key=lambda item: (
                0 if str(item.get("selection_tier") or "") == "A" else 1,
                -float(item.get("final_score") or 0),
                -self._confidence_rank(item),
                -(_parse_datetime(item.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
                str(item.get("title") or "").lower(),
            ),
        )
        for rank, item in enumerate(ordered, start=1):
            item["pre_portfolio_rank"] = rank
            item["post_portfolio_rank"] = None
            item["company_family"] = self._company_family(item)
            item["editorial_ecosystem"] = self._editorial_ecosystem(item)
            item["portfolio_selection_reason"] = ""
            item["breaking_news"] = self._is_breaking_news(item)

        selected: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        family_counts: dict[str, int] = {}
        ecosystem_counts: dict[str, int] = {}
        breaking_exception_applied = False

        for item in ordered:
            family = str(item["company_family"])
            ecosystem = str(item["editorial_ecosystem"])
            if len(selected) >= max_selected:
                reason = "REJECTED_DAILY_PORTFOLIO_LIMIT"
            elif not selected:
                reason = "SELECTED_DAILY_PORTFOLIO_PRIMARY"
            elif family_counts.get(family, 0) >= family_cap:
                same_family = [value for value in selected if value["company_family"] == family]
                if self._qualifies_breaking_exception(item, same_family, policy):
                    reason = "SELECTED_BREAKING_SAME_FAMILY_EXCEPTION"
                    breaking_exception_applied = True
                else:
                    reason = "REJECTED_DAILY_FAMILY_DUPLICATE"
            elif (
                ecosystem_counts.get(ecosystem, 0) >= ecosystem_cap
                and family.startswith("Independent")
            ):
                reason = "REJECTED_DAILY_ECOSYSTEM_DUPLICATE"
            else:
                reason = "SELECTED_DAILY_PORTFOLIO_DIVERSITY"

            item["portfolio_selection_reason"] = reason
            item["selection_reason"] = reason
            item["primary_reason"] = reason
            if reason.startswith("SELECTED_"):
                selected.append(item)
                item["post_portfolio_rank"] = len(selected)
                family_counts[family] = family_counts.get(family, 0) + 1
                ecosystem_counts[ecosystem] = ecosystem_counts.get(ecosystem, 0) + 1
            else:
                rejected.append(item)

        selected_families = list(dict.fromkeys(str(item["company_family"]) for item in selected))
        selected_ecosystems = list(dict.fromkeys(str(item["editorial_ecosystem"]) for item in selected))
        distinct_families = len({str(item["company_family"]) for item in ordered})
        distinct_ecosystems = len({str(item["editorial_ecosystem"]) for item in ordered})
        if not selected:
            selection_policy = "NO_ELIGIBLE_CANDIDATES"
        elif breaking_exception_applied:
            selection_policy = "BREAKING_EXCEPTION_APPLIED"
        elif len(selected) == 3:
            selection_policy = "DIVERSE_TOP_THREE"
        elif len(selected) == 2:
            selection_policy = "TWO_FAMILY_DIVERSE_PORTFOLIO"
        elif distinct_families == 1:
            selection_policy = "SINGLE_FAMILY_PRIMARY_ONLY"
        else:
            selection_policy = "QUALITY_LIMITED_PORTFOLIO"
        metadata = {
            "eligible_count": len(ordered),
            "distinct_company_families": distinct_families,
            "distinct_editorial_ecosystems": distinct_ecosystems,
            "final_selected_count": len(selected),
            "selection_policy": selection_policy,
            "selected_families": selected_families,
            "selected_ecosystems": selected_ecosystems,
            "breaking_exception_applied": breaking_exception_applied,
        }
        return selected, rejected, metadata

    def _source_type(self, urls: list[str]) -> tuple[str, bool, float]:
        official_domains = dict(self.config.get("official_domains") or {})
        trusted = set(self.config.get("trusted_media_domains") or [])
        domains = {_domain(url) for url in urls}
        if any(any(domain == item or domain.endswith("." + item) for item in official_domains) for domain in domains):
            return "OFFICIAL_COMPANY", True, 95.0
        if any(domain in trusted for domain in domains):
            return "TRUSTED_TECH_MEDIA", False, 78.0
        if "arxiv.org" in domains:
            return "RESEARCH_PAPER", False, 65.0
        if "github.com" in domains:
            return "OFFICIAL_DEVELOPER_DOCS", True, 85.0
        if any(domain.endswith(".gov") or domain.endswith(".gov.uk") for domain in domains):
            return "OFFICIAL_GOVERNMENT", True, 92.0
        if any(domain.startswith("status.") for domain in domains):
            return "OFFICIAL_STATUS_PAGE", True, 92.0
        if domains & {"reddit.com", "news.ycombinator.com"}:
            return "COMMUNITY_SOURCE", False, 42.0
        return "UNKNOWN", False, 35.0

    def _category(self, title: str, classifications: list[str]) -> str:
        text = f" {title.lower()} {' '.join(classifications).lower()} "
        for category, markers in EVENT_CATEGORIES:
            if any(marker in text for marker in markers):
                return category
        return "OTHER_AI_EVENT"

    def _published_at(self, candidate: TopicCandidate) -> tuple[str, str]:
        for attr in ("published_at", "publication_date", "published_date"):
            parsed = _parse_datetime(getattr(candidate, attr, ""))
            if parsed:
                return parsed.isoformat(), "candidate_metadata"
        evidence_dates = [
            _parse_datetime(self._evidence_by_url.get(url, {}).get("published_at"))
            for url in candidate.source_urls
        ]
        valid = [item for item in evidence_dates if item]
        if valid:
            return max(valid).isoformat(), "source_feed"
        return "", "missing"

    def _score_candidate(self, candidate: TopicCandidate) -> dict[str, Any]:
        title = str(candidate.topic or "").strip()
        urls = list(dict.fromkeys(str(url).strip() for url in candidate.source_urls if str(url).strip()))
        domains = sorted({_domain(url) for url in urls if _domain(url)})
        source_type, official_confirmed, authority = self._source_type(urls)
        company = self._organization(title, urls)
        category = self._category(title, list(candidate.classifications or []))
        published_at, date_source = self._published_at(candidate)
        published_dt = _parse_datetime(published_at)
        age_days = (self.now - published_dt).total_seconds() / 86400 if published_dt else None

        recency = _clamp(candidate.news_freshness)
        if age_days is not None:
            recency = _clamp(100 - max(0, age_days) * 7)
        impact_terms = (
            "release", "launch", "pricing", "access", "outage", "security", "partnership",
            "acquisition", "regulation", "api", "developer", "coding", "copilot", "model",
        )
        impact = _clamp(35 + sum(term in title.lower() for term in impact_terms) * 7 + candidate.search_volume_potential * 0.25)
        if company != "Independent":
            impact = _clamp(impact + 8)
        official_score = 100.0 if official_confirmed else (55.0 if source_type.startswith("TRUSTED_") else 20.0)
        generic = category in {"GENERIC_REVIEW", "GENERIC_COMPARISON"}
        novelty = _clamp(78 if category not in {"GENERIC_REVIEW", "GENERIC_COMPARISON", "OTHER_AI_EVENT"} else 35)
        social = _clamp(30 + candidate.signals * 10 + candidate.search_volume_potential * 0.25)
        priority_categories = set(self.config.get("tier_a_categories") or [])
        practical = _clamp(78 if category in priority_categories else impact * 0.75)
        significance = 90.0 if company != "Independent" else 40.0
        evidence = _clamp(20 + len(domains) * 22 + (25 if official_confirmed else 0) + (10 if published_at else 0))

        components = {
            "recency": recency,
            "source_authority": authority,
            "user_business_impact": impact,
            "official_confirmation": official_score,
            "novelty": novelty,
            "social_discussion_potential": social,
            "practical_relevance": practical,
            "company_significance": significance,
            "evidence_confidence": evidence,
        }
        weights = {**DEFAULT_WEIGHTS, **dict(self.config.get("weights") or {})}
        weighted = sum(components[name] * float(weights[name]) for name in DEFAULT_WEIGHTS) / 100.0
        penalties: dict[str, float] = {}
        configured_penalties = {**DEFAULT_PENALTIES, **dict(self.config.get("penalties") or {})}
        stale_after = float(self.config.get("stale_after_days", 14) or 14)
        if age_days is not None and age_days > stale_after:
            penalties["staleness"] = -float(configured_penalties["staleness"])
        if authority < 45:
            penalties["low_authority_only"] = -float(configured_penalties["low_authority_only"])
        if generic:
            penalties["recycled_seo_content"] = -float(configured_penalties["recycled_seo_content"])
        if category == "OTHER_AI_EVENT":
            penalties["opinion_without_event"] = -float(configured_penalties["opinion_without_event"])
        if impact < 40:
            penalties["weak_user_relevance"] = -float(configured_penalties["weak_user_relevance"])
        final_score = _clamp(weighted + sum(penalties.values()))

        failed_gates: list[dict[str, str]] = []
        if not title:
            failed_gates.append({"gate": "title", "reason_code": "REJECTED_MISSING_TITLE", "reason": "Title is missing."})
        if not urls or any(not _valid_url(url) for url in urls):
            failed_gates.append({"gate": "source_url", "reason_code": "REJECTED_INVALID_URL", "reason": "A valid HTTP(S) source URL is required."})
        if not published_at:
            failed_gates.append({"gate": "publication_date", "reason_code": "REJECTED_MISSING_DATE", "reason": "Publication date could not be determined."})
        if evidence < float(self.config.get("minimum_evidence_confidence", 35) or 35):
            failed_gates.append({"gate": "evidence", "reason_code": "REJECTED_UNVERIFIABLE", "reason": "Evidence is insufficient for safe wording."})
        scope_text = f"{title} {' '.join(candidate.classifications or [])}".lower()
        if title and not any(term in scope_text for term in AI_SCOPE_TERMS):
            failed_gates.append({"gate": "scope", "reason_code": "REJECTED_OUT_OF_SCOPE", "reason": "The event is not materially related to AI."})
        if any(marker in scope_text for marker in UNSAFE_EVENT_MARKERS):
            failed_gates.append({"gate": "safety", "reason_code": "REJECTED_UNSAFE_TO_DESCRIBE", "reason": "The event cannot be described safely in this workflow."})

        tier_a_categories = set(self.config.get("tier_a_categories") or [])
        tier = ""
        selection_reason = ""
        stale = age_days is not None and age_days > stale_after
        if not failed_gates and not stale and not generic:
            if (
                official_confirmed
                and category in tier_a_categories
                and final_score >= float(self.config.get("tier_a_threshold", 72) or 72)
            ):
                tier = "A"
                selection_reason = "SELECTED_TIER_A"
            elif final_score >= float(self.config.get("tier_b_threshold", 55) or 55):
                tier = "B"
                selection_reason = "SELECTED_TIER_B"

        if failed_gates:
            primary_reason = failed_gates[0]["reason_code"]
        elif stale:
            primary_reason = "REJECTED_STALE"
        elif authority < 35:
            primary_reason = "REJECTED_LOW_AUTHORITY"
        elif generic:
            primary_reason = "REJECTED_REUSED_SEO_CONTENT"
        elif impact < 35:
            primary_reason = "REJECTED_LOW_IMPACT"
        elif not tier:
            primary_reason = "REJECTED_BELOW_SOCIAL_THRESHOLD"
        else:
            primary_reason = selection_reason

        what_is_known = title
        if candidate.suggested_article_angle:
            what_is_known = str(candidate.suggested_article_angle)
        what_is_not_confirmed = "" if official_confirmed else "No official confirmation was found in the selected primary source."
        safe_wording = (
            "State the announcement as confirmed and attribute details to the official source."
            if official_confirmed
            else "Attribute every material claim to its source and state clearly that official confirmation is not available."
        )
        affiliate_signal = self.affiliate_discovery.extract_signal(
            f"{title} {candidate.suggested_article_angle or ''}",
            source_url_value=urls[0] if urls else "",
            source_platform=_domain(urls[0]) if urls else source_type,
            entity="" if company == "Independent" else company,
            product="" if company == "Independent" else company,
            category=category,
            trend_context=title,
        )
        return {
            "title": title,
            "normalized_title": _normalized_title(title),
            "slug": candidate.slug,
            "summary": candidate.suggested_article_angle,
            "primary_source_url": urls[0] if urls else "",
            "supporting_source_urls": urls[1:],
            "source_urls": urls,
            "source_domains": domains,
            "source_type": source_type,
            "publisher": _domain(urls[0]) if urls else "",
            "company": company,
            "published_at": published_at,
            "publication_date_source": date_source,
            "discovered_at": self.now.isoformat(),
            "category": category,
            "official_confirmed": official_confirmed,
            "confidence": "high" if evidence >= 75 else ("medium" if evidence >= 50 else "low"),
            "recency_score": recency,
            "authority_score": authority,
            "impact_score": impact,
            "official_confirmation_score": official_score,
            "company_significance_score": significance,
            "novelty_score": novelty,
            "social_potential_score": social,
            "practical_relevance_score": practical,
            "evidence_confidence_score": evidence,
            "score_breakdown": components,
            "weights": weights,
            "penalties": penalties,
            "final_score": final_score,
            "score": final_score,
            "selection_tier": tier,
            "selection_reason": selection_reason,
            "primary_reason": primary_reason,
            "secondary_reasons": [gate["reason_code"] for gate in failed_gates[1:]],
            "failed_gate_details": failed_gates,
            "hard_gates_passed": not failed_gates,
            "safe_wording_guidance": safe_wording,
            "what_is_known": what_is_known,
            "what_is_not_confirmed": what_is_not_confirmed,
            "event_tokens": sorted(_event_tokens(title)),
            "content_lane": SOCIAL_HOT_UNCONFIRMED,
            "queue_type": SOCIAL_HOT_DRAFT,
            "website_article_required": False,
            "website_url": None,
            "manual_review_required": True,
            "manual_publish_required": True,
            "scoring_profile": SCORING_PROFILE,
            **({"affiliate_opportunity_signal": affiliate_signal} if affiliate_signal else {}),
        }

    def select(self) -> dict[str, Any]:
        empty = {
            "schema_version": 2,
            "scoring_profile": SCORING_PROFILE,
            "queue_type": SOCIAL_HOT_DRAFT,
            "content_lane": SOCIAL_HOT_UNCONFIRMED,
            "generated_at": now_iso(),
            "sources_scanned": 0,
            "source_status": {},
            "signals_found": 0,
            "candidates_found": 0,
            "normalized_candidates": 0,
            "duplicates_removed": 0,
            "clusters_created": 0,
            "tier_a_eligible": 0,
            "tier_b_eligible": 0,
            "rejected_count": 0,
            "selected_count": 0,
            "selected": [],
            "rejected": [],
            "social_signal_advisory": menu_h_signal_advisory(self.root),
            "daily_editorial_portfolio": {
                "eligible_count": 0,
                "distinct_company_families": 0,
                "distinct_editorial_ecosystems": 0,
                "final_selected_count": 0,
                "selection_policy": "NO_ELIGIBLE_CANDIDATES",
                "selected_families": [],
                "selected_ecosystems": [],
                "breaking_exception_applied": False,
            },
        }
        if not bool(self.config.get("enabled", True)) or not bool(self.config.get("auto_discovery", True)):
            empty["source_status"] = {"auto_discovery": {"status": "disabled", "signals": 0}}
            return empty

        candidates, source_status, signal_count = self._discover_candidates()
        scored = [self._score_candidate(candidate) for candidate in candidates]
        if feature_enabled(self.root, "editorial_memory.enabled"):
            try:
                memory = EditorialMemoryStore(root=self.root)
                for item in scored:
                    item["editorial_memory"] = memory.detect_duplicates(
                        {
                            "slug": item.get("slug"),
                            "title": item.get("title"),
                            "root_topic": item.get("company_family") or item.get("source_name"),
                            "angle": "social_hot_news",
                            "keyword": item.get("keyword") or item.get("title"),
                            "entities": item.get("entities") or item.get("companies") or [],
                            "claims": item.get("what_is_known") or [],
                            "cited_sources": item.get("source_urls") or item.get("url") or [],
                        }
                    )
            except (OSError, ValueError, sqlite3.Error):
                pass
        scored.sort(key=lambda item: (-item["final_score"], -item["authority_score"], item["title"].lower()))
        for item in scored:
            item["pre_portfolio_rank"] = None
            item["post_portfolio_rank"] = None
            item["company_family"] = self._company_family(item)
            item["editorial_ecosystem"] = self._editorial_ecosystem(item)
            item["portfolio_selection_reason"] = ""

        clusters: list[list[dict[str, Any]]] = []
        for item in scored:
            cluster = next((group for group in clusters if _same_event(item, group[0])), None)
            if cluster is None:
                clusters.append([item])
            else:
                cluster.append(item)
        for index, cluster in enumerate(clusters, start=1):
            for item in cluster:
                item["event_cluster_id"] = f"event-{index:03d}"
                item["cluster_size"] = len(cluster)

        rejected: list[dict[str, Any]] = []
        representatives: list[dict[str, Any]] = []
        for cluster in clusters:
            representatives.append(cluster[0])
            for duplicate in cluster[1:]:
                duplicate["primary_reason"] = "REJECTED_DUPLICATE_EVENT"
                duplicate["portfolio_selection_reason"] = "REJECTED_DUPLICATE_EVENT"
                duplicate["secondary_reasons"] = list(dict.fromkeys([*duplicate["secondary_reasons"], "same_event_cluster"]))
                rejected.append(duplicate)

        eligible_a: list[dict[str, Any]] = []
        eligible_b: list[dict[str, Any]] = []
        for item in representatives:
            if not item["hard_gates_passed"] or not item["selection_tier"]:
                item["portfolio_selection_reason"] = item["primary_reason"]
                rejected.append(item)
            elif item["selection_tier"] == "A":
                eligible_a.append(item)
            else:
                eligible_b.append(item)

        selected, portfolio_rejected, daily_portfolio = self._daily_editorial_portfolio(
            [*eligible_a, *eligible_b]
        )
        rejected.extend(portfolio_rejected)
        diversity_selected = [
            item["slug"]
            for item in selected
            if item["selection_reason"] == "SELECTED_DAILY_PORTFOLIO_DIVERSITY"
        ]
        editorial_diversity = {
            "enabled": bool(self.config.get("diversity_enabled", True)),
            "window": max(0.0, float(self.config.get("editorial_diversity_window", 5) or 0)),
            "applied": len(daily_portfolio["selected_families"]) > 1,
            "families_selected": daily_portfolio["selected_families"],
            "promoted_slugs": diversity_selected,
            "message": (
                "Optimization applied."
                if len(daily_portfolio["selected_families"]) > 1
                else "No optimization applied."
            ),
        }

        rejected.sort(key=lambda item: (-item["final_score"], item["title"].lower()))
        return {
            **empty,
            "source_status": source_status,
            "sources_scanned": len(source_status),
            "signals_found": signal_count,
            "candidates_found": len(candidates),
            "normalized_candidates": len(scored),
            "duplicates_removed": sum(max(0, len(cluster) - 1) for cluster in clusters),
            "clusters_created": len(clusters),
            "tier_a_eligible": len(eligible_a),
            "tier_b_eligible": len(eligible_b),
            "rejected_count": len(rejected),
            "selected_count": len(selected),
            "selected": selected,
            "rejected": rejected,
            "editorial_diversity": editorial_diversity,
            "daily_editorial_portfolio": daily_portfolio,
        }

    def _write_reports(self, report: dict[str, Any], batch_date: str) -> dict[str, str]:
        report_dir = self.root / "data" / "reports" / "social_hot" / batch_date
        report_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            key: value
            for key, value in report.items()
            if key not in {"selected", "rejected", "source_status"}
        }
        summary["selected"] = report["selected"]
        paths = {
            "summary": report_dir / "menu_h_summary.json",
            "full_candidates": report_dir / "menu_h_full_candidates.json",
            "rejected": report_dir / "menu_h_rejected.json",
            "console_summary": report_dir / "menu_h_console_summary.md",
        }
        paths["summary"].write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths["full_candidates"].write_text(
            json.dumps([*report["selected"], *report["rejected"]], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["rejected"].write_text(json.dumps(report["rejected"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [
            "# Menu H - AI News Editor",
            "",
            f"- Sources scanned: {report['sources_scanned']}",
            f"- Raw items discovered: {report['signals_found']}",
            f"- Normalized candidates: {report['normalized_candidates']}",
            f"- Event clusters: {report['clusters_created']}",
            f"- Tier A eligible: {report['tier_a_eligible']}",
            f"- Tier B eligible: {report['tier_b_eligible']}",
            f"- Eligible candidates: {report.get('daily_editorial_portfolio', {}).get('eligible_count', 0)}",
            (
                "- Distinct company families: "
                f"{report.get('daily_editorial_portfolio', {}).get('distinct_company_families', 0)}"
            ),
            (
                "- Distinct editorial ecosystems: "
                f"{report.get('daily_editorial_portfolio', {}).get('distinct_editorial_ecosystems', 0)}"
            ),
            f"- Selected: {report['selected_count']}",
            f"- Rejected: {report['rejected_count']}",
            "",
            "## Daily Editorial Portfolio",
            "",
            (
                "- Selection policy: "
                f"{report.get('daily_editorial_portfolio', {}).get('selection_policy', 'NO_ELIGIBLE_CANDIDATES')}"
            ),
            (
                "- Families selected: "
                + ", ".join(report.get("daily_editorial_portfolio", {}).get("selected_families", []))
                if report.get("daily_editorial_portfolio", {}).get("selected_families")
                else "- Families selected: none"
            ),
            (
                "- Ecosystems selected: "
                + ", ".join(report.get("daily_editorial_portfolio", {}).get("selected_ecosystems", []))
                if report.get("daily_editorial_portfolio", {}).get("selected_ecosystems")
                else "- Ecosystems selected: none"
            ),
            "",
            "## Selected",
            "",
        ]
        for item in report["selected"]:
            lines.append(
                f"- [Tier {item['selection_tier']}] [{item['final_score']:.1f}] "
                f"[{item['portfolio_selection_reason']}] {item['title']}"
            )
        lines.extend(["", "## Top rejected", ""])
        for item in report["rejected"][:10]:
            lines.append(f"- [{item['primary_reason']}] [{item['final_score']:.1f}] {item['title']}")
        paths["console_summary"].write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {key: str(path) for key, path in paths.items()}

    def prepare_auto(self, *, batch_date: str | None = None) -> dict[str, Any]:
        resolved = batch_date if batch_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", batch_date) else date.today().isoformat()
        report = self.select()
        report["batch_date"] = resolved
        workflow = SocialDraftWorkflow(root=self.root)
        queue_items: list[dict[str, Any]] = []
        for item in report["selected"]:
            manifest = workflow.prepare_hot_news_monitoring(
                batch_date=resolved,
                title=item["title"],
                source_urls=item["source_urls"],
                platforms=HOT_NEWS_MONITORING_PLATFORMS,
                summary=item["summary"],
                queue_type=SOCIAL_HOT_DRAFT,
                editorial_metadata=item,
                create_placeholder_drafts=False,
            )
            queue_items.append(manifest["items"][-1])
        report["queue_generated"] = len(queue_items)
        report["queue_items"] = queue_items
        report["report_paths"] = self._write_reports(report, resolved)
        report["report_path"] = report["report_paths"]["summary"]
        if queue_items:
            from scripts.codex_instruction_prompt import build_hot_social_prompt

            task_path, _, _ = build_hot_social_prompt(self.root, resolved, report)
            report["ai_task_path"] = str(task_path)
        else:
            report["ai_task_path"] = ""
        return report
