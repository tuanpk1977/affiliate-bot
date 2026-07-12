from __future__ import annotations

import html
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from config import settings
from modules.keyword_intelligence import score_affiliate_intent, score_competition


PREFERRED_TERMS = {
    "ai tools", "ai coding", "ai agent", "ai agents", "productivity", "marketing ai",
    "video ai", "image ai", "saas", "seo", "automation", "developer tools", "llm",
}
AI_SIGNAL_TERMS = {
    "ai", "artificial intelligence", "llm", "machine learning", "agentic", "copilot",
    "vector database", "generative", "prompt", "model hosting", "inference", "gpu",
}
COMMERCIAL_TERMS = {
    "review", "pricing", "alternatives", "alternative", "vs", "software", "platform",
    "tool", "tools", "automation", "builder", "assistant", "agent", "api", "saas",
}
EVERGREEN_TERMS = {
    "review", "pricing", "alternatives", "vs", "guide", "how to", "workflow", "software",
    "tool", "platform", "automation", "builder", "assistant",
}
NOISE_TERMS = {
    "stock", "shares", "lawsuit", "politics", "election", "war", "celebrity", "sports",
    "movie", "music", "crypto price", "earnings call",
}
SOURCE_WEIGHTS = {
    "google_trends": 1.0,
    "bing_trending": 0.9,
    "reddit": 0.95,
    "hacker_news": 1.0,
    "product_hunt": 1.0,
    "github_trending": 1.0,
    "x_twitter": 0.85,
    "linkedin": 0.75,
    "youtube_trending": 0.9,
    "ai_newsletters": 0.9,
    "local_keyword_intelligence": 0.55,
}


@dataclass
class TrendSignal:
    title: str
    source: str
    url: str = ""
    published_at: str = ""
    engagement: float = 0
    description: str = ""


@dataclass
class TopicCandidate:
    topic: str
    slug: str
    sources: list[str]
    source_urls: list[str]
    signals: int
    trend_score: int
    search_intent: str
    content_type: str
    affiliate_potential: str
    competition_level: str
    freshness_level: str
    estimated_business_value: str
    recommended_priority: str
    suggested_internal_links: list[str]
    suggested_article_angle: str
    suggested_video_angle: str
    classifications: list[str]
    search_volume_potential: int
    competition: int
    affiliate_opportunity: int
    evergreen_value: int
    news_freshness: int
    cpc_potential: int
    total_score: float
    confidence: str
    why_selected: list[str]
    already_published: bool = False


@dataclass
class DiscoveryResult:
    generated_at: str
    selected_topics: list[TopicCandidate]
    source_status: dict[str, dict[str, object]]
    candidates_evaluated: int
    published_topics_checked: int
    methodology: dict[str, object] = field(default_factory=dict)


class TrendDiscoveryEngine:
    def __init__(self, timeout: int | None = None, max_per_source: int = 40, read_only: bool = False) -> None:
        self.timeout = timeout or int(os.getenv("REQUEST_TIMEOUT", "20"))
        self.max_per_source = max_per_source
        self.read_only = read_only
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": os.getenv("USER_AGENT", "SmileAIReviewHub-TrendDiscovery/1.0")})
        self.source_status: dict[str, dict[str, object]] = {}
        self.published = list(discover_published_topics())
        self.affiliate_brands = set(load_affiliate_brands())

    def run(self, limit: int = 10) -> DiscoveryResult:
        signals: list[TrendSignal] = []
        connectors: list[tuple[str, Callable[[], list[TrendSignal]]]] = [
            ("google_trends", self.google_trends),
            ("bing_trending", self.bing_trending),
            ("reddit", self.reddit),
            ("hacker_news", self.hacker_news),
            ("product_hunt", self.product_hunt),
            ("github_trending", self.github_trending),
            ("x_twitter", self.x_twitter),
            ("linkedin", self.linkedin),
            ("youtube_trending", self.youtube_trending),
            ("ai_newsletters", self.ai_newsletters),
        ]
        if not self.read_only:
            connectors.append(("local_keyword_intelligence", self.local_keyword_intelligence))
        for name, connector in connectors:
            try:
                found = connector()[: self.max_per_source]
                signals.extend(found)
                self.source_status[name] = {"status": "ok" if found else "empty", "signals": len(found)}
            except MissingCredential as exc:
                self.source_status[name] = {"status": "unavailable", "signals": 0, "detail": str(exc)}
            except Exception as exc:
                self.source_status[name] = {"status": "error", "signals": 0, "detail": f"{type(exc).__name__}: {exc}"}

        candidates = self.aggregate(signals)
        eligible = [candidate for candidate in candidates if not candidate.already_published]
        selected = sorted(eligible, key=lambda item: (-item.total_score, item.competition, item.topic))[:limit]
        return DiscoveryResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            selected_topics=selected,
            source_status=self.source_status,
            candidates_evaluated=len(candidates),
            published_topics_checked=len(self.published),
            methodology={
                "weights": {
                    "search_volume_potential": 0.22,
                    "low_competition_opportunity": 0.16,
                    "affiliate_opportunity": 0.20,
                    "evergreen_value": 0.14,
                    "news_freshness": 0.16,
                    "cpc_potential": 0.12,
                },
                "published_content_filter": "Exact slug, normalized title, and token similarity >= 0.72 are excluded.",
                "note": "Scores are directional opportunity estimates, not paid keyword-volume measurements.",
            },
        )

    def aggregate(self, signals: list[TrendSignal]) -> list[TopicCandidate]:
        groups: dict[str, list[TrendSignal]] = defaultdict(list)
        for signal in signals:
            topic = normalize_topic(signal.title)
            if not is_relevant(topic + " " + signal.description):
                continue
            key = topic_key(topic)
            if key:
                groups[key].append(signal)
        candidates = [self.score_group(items) for items in groups.values()]
        return sorted(candidates, key=lambda item: (-item.total_score, item.topic))

    def score_group(self, signals: list[TrendSignal]) -> TopicCandidate:
        representative = choose_representative(signals)
        topic = editorial_topic(representative)
        scoring_text = " ".join([topic, *[signal.description for signal in signals]])
        sources = sorted({signal.source for signal in signals})
        source_strength = sum(SOURCE_WEIGHTS.get(source, 0.5) for source in sources)
        engagement = sum(max(0, signal.engagement) for signal in signals)
        preferred = keyword_hits(scoring_text, PREFERRED_TERMS)
        commercial = keyword_hits(scoring_text, COMMERCIAL_TERMS)
        evergreen_hits = keyword_hits(scoring_text, EVERGREEN_TERMS)

        search = clamp(35 + len(sources) * 9 + min(25, math.log10(engagement + 1) * 8) + preferred * 4)
        competition = score_competition(topic.lower(), {})
        if len(sources) >= 3:
            competition = clamp(competition + 8)
        affiliate = score_affiliate_intent(topic.lower(), {})
        if any(brand in topic.lower() for brand in self.affiliate_brands):
            affiliate = clamp(affiliate + 22)
        affiliate = clamp(affiliate + commercial * 5 + min(12, len(sources) * 2))
        evergreen = clamp(35 + evergreen_hits * 12 + commercial * 4 - (10 if looks_like_news_only(topic) else 0))
        freshness = clamp(30 + len(sources) * 12 + source_strength * 5 + min(20, math.log10(engagement + 1) * 6))
        cpc = clamp(25 + affiliate * 0.45 + commercial * 7 + preferred * 3)
        low_competition = 100 - competition
        total = round(
            search * 0.22
            + low_competition * 0.16
            + affiliate * 0.20
            + evergreen * 0.14
            + freshness * 0.16
            + cpc * 0.12,
            1,
        )
        published_match = published_match_for(topic, self.published)
        reasons = build_reasons(topic, sources, search, competition, affiliate, evergreen, freshness, cpc)
        content_type = classify_content_type(topic)
        classifications = classify_topic(topic, content_type, freshness, evergreen)
        confidence = "high" if len(sources) >= 3 else "medium" if len(sources) >= 2 else "low"
        return TopicCandidate(
            topic=topic,
            slug=slugify(topic),
            sources=sources,
            source_urls=unique([signal.url for signal in signals if signal.url])[:8],
            signals=len(signals),
            trend_score=freshness,
            search_intent=classify_search_intent(topic),
            content_type=content_type,
            affiliate_potential=level_from_score(affiliate),
            competition_level=competition_level(competition),
            freshness_level=level_from_score(freshness),
            estimated_business_value=business_value_level(affiliate, cpc, evergreen),
            recommended_priority=priority_level(total),
            suggested_internal_links=suggest_internal_links(topic, content_type),
            suggested_article_angle=suggest_article_angle(topic, content_type),
            suggested_video_angle=suggest_video_angle(topic, content_type),
            classifications=classifications,
            search_volume_potential=search,
            competition=competition,
            affiliate_opportunity=affiliate,
            evergreen_value=evergreen,
            news_freshness=freshness,
            cpc_potential=cpc,
            total_score=total,
            confidence=confidence,
            why_selected=reasons,
            already_published=bool(published_match),
        )

    def google_trends(self) -> list[TrendSignal]:
        return self.rss("https://trends.google.com/trending/rss?geo=US", "google_trends")

    def bing_trending(self) -> list[TrendSignal]:
        queries = ("AI software", "AI agent SaaS", "AI coding tools", "marketing automation AI")
        result: list[TrendSignal] = []
        for query in queries:
            result.extend(self.rss(f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss", "bing_trending"))
        return result

    def reddit(self) -> list[TrendSignal]:
        result: list[TrendSignal] = []
        for subreddit in ("artificial", "LocalLLaMA", "SaaS", "SEO", "productivity", "ChatGPTCoding"):
            try:
                data = self.get_json(f"https://www.reddit.com/r/{subreddit}/hot.json?limit=15")
                for child in data.get("data", {}).get("children", []):
                    item = child.get("data", {})
                    result.append(TrendSignal(item.get("title", ""), "reddit", "https://reddit.com" + item.get("permalink", ""), engagement=float(item.get("score", 0))))
            except Exception:
                try:
                    result.extend(self.rss(f"https://www.reddit.com/r/{subreddit}/hot/.rss", "reddit"))
                except Exception:
                    continue
        return result

    def hacker_news(self) -> list[TrendSignal]:
        result: list[TrendSignal] = []
        ids = self.get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:60]
        for item_id in ids:
            item = self.get_json(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
            result.append(TrendSignal(item.get("title", ""), "hacker_news", item.get("url", ""), engagement=float(item.get("score", 0))))
        return result

    def product_hunt(self) -> list[TrendSignal]:
        return self.rss("https://www.producthunt.com/feed", "product_hunt")

    def github_trending(self) -> list[TrendSignal]:
        response = self.get("https://github.com/trending?since=daily")
        soup = BeautifulSoup(response.text, "html.parser")
        result: list[TrendSignal] = []
        for article in soup.select("article.Box-row"):
            link = article.select_one("h2 a")
            if not link:
                continue
            repo = clean_text(link.get_text(" "))
            desc = clean_text(article.select_one("p").get_text(" ") if article.select_one("p") else "")
            stars = clean_text(article.select_one("span.d-inline-block.float-sm-right").get_text(" ") if article.select_one("span.d-inline-block.float-sm-right") else "")
            result.append(TrendSignal(f"{repo}: {desc}", "github_trending", "https://github.com" + link.get("href", ""), engagement=parse_number(stars), description=desc))
        return result

    def x_twitter(self) -> list[TrendSignal]:
        bearer = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
        if not bearer:
            raise MissingCredential("Set TWITTER_BEARER_TOKEN to enable X recent-search discovery.")
        headers = {"Authorization": f"Bearer {bearer}"}
        query = "(AI tool OR AI agent OR SaaS OR AI coding) lang:en -is:retweet"
        data = self.get_json("https://api.twitter.com/2/tweets/search/recent?max_results=50&tweet.fields=public_metrics&query=" + quote_plus(query), headers=headers)
        return [
            TrendSignal(item.get("text", ""), "x_twitter", engagement=sum(item.get("public_metrics", {}).values()))
            for item in data.get("data", [])
        ]

    def linkedin(self) -> list[TrendSignal]:
        token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
        if not token:
            raise MissingCredential("LinkedIn does not expose public trending search; set LINKEDIN_ACCESS_TOKEN and a permitted discovery endpoint.")
        raise MissingCredential("LinkedIn token exists, but no approved organization-post discovery endpoint is configured.")

    def youtube_trending(self) -> list[TrendSignal]:
        key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not key:
            raise MissingCredential("Set YOUTUBE_API_KEY to enable YouTube trending discovery.")
        params = f"part=snippet,statistics&chart=mostPopular&regionCode=US&videoCategoryId=28&maxResults=50&key={key}"
        data = self.get_json("https://www.googleapis.com/youtube/v3/videos?" + params)
        return [
            TrendSignal(
                item.get("snippet", {}).get("title", ""),
                "youtube_trending",
                f"https://www.youtube.com/watch?v={item.get('id', '')}",
                engagement=float(item.get("statistics", {}).get("viewCount", 0)),
                description=item.get("snippet", {}).get("description", ""),
            )
            for item in data.get("items", [])
        ]

    def ai_newsletters(self) -> list[TrendSignal]:
        feeds = [
            "https://www.deeplearning.ai/the-batch/feed/",
            "https://importai.substack.com/feed",
            "https://www.bensbites.com/feed",
            "https://www.therundown.ai/feed",
        ]
        result: list[TrendSignal] = []
        for feed in feeds:
            try:
                result.extend(self.rss(feed, "ai_newsletters"))
            except Exception:
                continue
        return result

    def local_keyword_intelligence(self) -> list[TrendSignal]:
        path = settings.data_dir / "keyword_intelligence_report.csv"
        if not path.exists():
            return []
        import csv

        result: list[TrendSignal] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("current_page_exists", "")).lower() == "true":
                    continue
                priority = parse_number(row.get("priority_score", "0"))
                if priority >= 55:
                    result.append(TrendSignal(row.get("keyword", ""), "local_keyword_intelligence", engagement=priority))
        return result

    def rss(self, url: str, source: str) -> list[TrendSignal]:
        response = self.get(url)
        root = ET.fromstring(response.content)
        result: list[TrendSignal] = []
        for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = xml_text(item, ("title", "{http://www.w3.org/2005/Atom}title"))
            link = xml_text(item, ("link", "{http://www.w3.org/2005/Atom}link"))
            if not link:
                atom_link = item.find("{http://www.w3.org/2005/Atom}link")
                link = atom_link.get("href", "") if atom_link is not None else ""
            published = xml_text(item, ("pubDate", "published", "{http://www.w3.org/2005/Atom}published"))
            description = xml_text(
                item,
                ("description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://purl.org/rss/1.0/modules/content/}encoded"),
            )
            result.append(TrendSignal(title, source, link, published, description=clean_text(description)))
        return result

    def get(self, url: str, headers: dict[str, str] | None = None) -> requests.Response:
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> object:
        return self.get(url, headers=headers).json()


class MissingCredential(RuntimeError):
    pass


@lru_cache(maxsize=1)
def discover_published_topics() -> tuple[dict[str, object], ...]:
    roots = [settings.site_output_dir, settings.base_dir / "docs", settings.data_dir / "published_static_pages"]
    records: dict[str, dict[str, object]] = {}
    for root in roots:
        if not root.exists():
            continue
        for page in root.rglob("index.html"):
            rel = page.relative_to(root).as_posix()
            if rel.startswith(("go/", "vi/")):
                continue
            source = page.read_text(encoding="utf-8", errors="ignore")
            title = clean_text(first_match(source, r"<h1\b[^>]*>(.*?)</h1>") or first_match(source, r"<title\b[^>]*>(.*?)</title>"))
            slug = rel[: -len("/index.html")] if rel != "index.html" else "home"
            key = slugify(slug)
            if title and key not in records:
                records[key] = {"slug": key, "title": title, "tokens": token_set(title + " " + slug)}
    return tuple(records.values())


@lru_cache(maxsize=1)
def load_affiliate_brands() -> frozenset[str]:
    import csv

    brands: set[str] = set()
    for filename in ("offer_scores.csv", "affiliate_links.csv", "offers.csv"):
        path = settings.data_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                brand = str(row.get("brand_name") or row.get("offer_id") or "").strip().lower()
                if brand:
                    brands.add(brand)
    return frozenset(brands)


def published_match_for(topic: str, published: list[dict[str, object]]) -> str:
    slug = slugify(topic)
    tokens = token_set(topic)
    for page in published:
        if slug == page["slug"] or slug in str(page["slug"]) or str(page["slug"]) in slug:
            return str(page["slug"])
        page_tokens = set(page["tokens"])
        union = tokens | page_tokens
        if union and len(tokens & page_tokens) / len(union) >= 0.72:
            return str(page["slug"])
    return ""


def normalize_topic(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"\s+[-|]\s+[^-|]{3,80}$", "", text)
    return text[:180].strip(" -:|")


def editorial_topic(signal: TrendSignal) -> str:
    topic = normalize_topic(signal.title)
    if signal.source == "github_trending" and ":" in topic:
        repo = re.sub(r"\s+/\s+", "/", topic.split(":", 1)[0]).strip()
        repo = repo.split("/", 1)[-1].strip()
        return f"{repo} Review 2026"
    if len(topic) > 110:
        first = re.split(r"[.!?]", topic, maxsplit=1)[0].strip()
        return (first if len(first) >= 20 else topic[:100]).strip(" -:|")
    return topic


def topic_key(topic: str) -> str:
    tokens = [token for token in token_set(topic) if token not in {"the", "a", "an", "new", "launches", "launch"}]
    return " ".join(sorted(tokens))


def is_relevant(topic: str) -> bool:
    lower = topic.lower()
    if len(topic) < 8 or any(phrase_present(lower, term) for term in NOISE_TERMS):
        return False
    return bool(keyword_hits(lower, PREFERRED_TERMS) or keyword_hits(lower, AI_SIGNAL_TERMS))


def choose_representative(signals: list[TrendSignal]) -> TrendSignal:
    return max(signals, key=lambda item: (item.engagement, len(item.title)))


def build_reasons(topic: str, sources: list[str], search: int, competition: int, affiliate: int, evergreen: int, freshness: int, cpc: int) -> list[str]:
    reasons = [f"Detected across {len(sources)} source(s): {', '.join(sources)}."]
    if search >= 65:
        reasons.append("Strong directional search-demand potential.")
    if competition <= 50:
        reasons.append("Competition estimate is low-to-medium.")
    if affiliate >= 65:
        reasons.append("High commercial and affiliate-content fit.")
    if evergreen >= 65:
        reasons.append("Can remain useful after the current news cycle.")
    if freshness >= 65:
        reasons.append("Recent multi-source activity indicates timely interest.")
    if cpc >= 65:
        reasons.append("Commercial terminology suggests above-average CPC potential.")
    return reasons


def looks_like_news_only(topic: str) -> bool:
    return bool(re.search(r"\b(raises|funding|acquires|announces|launches|released today|breaking)\b", topic.lower()))


def classify_search_intent(topic: str) -> str:
    lower = topic.lower()
    if any(term in lower for term in ("pricing", "cost", "free trial", "trial")):
        return "commercial investigation"
    if any(term in lower for term in ("alternatives", "alternative", "vs", "compare", "comparison")):
        return "comparison"
    if any(term in lower for term in ("review", "software", "platform", "tool", "tools")):
        return "commercial research"
    if any(term in lower for term in ("how to", "guide", "workflow", "tutorial")):
        return "informational"
    return "mixed informational and commercial"


def classify_content_type(topic: str) -> str:
    lower = topic.lower()
    if "alternatives" in lower or "alternative" in lower:
        return "alternative"
    if " vs " in lower or "comparison" in lower or "compare" in lower:
        return "comparison"
    if "pricing" in lower or "cost" in lower or "free trial" in lower or "trial" in lower:
        return "pricing"
    if "how to" in lower or "guide" in lower or "tutorial" in lower or "workflow" in lower:
        return "tutorial"
    if "best" in lower or "top " in lower or "tools" in lower:
        return "listicle"
    if "review" in lower:
        return "review"
    if looks_like_news_only(topic):
        return "news/update"
    return "review"


def classify_topic(topic: str, content_type: str, freshness: int, evergreen: int) -> list[str]:
    labels = {content_type}
    lower = topic.lower()
    if freshness >= 70:
        labels.add("hot trend")
    elif freshness >= 55:
        labels.add("rising trend")
    if evergreen >= 65:
        labels.add("evergreen")
    for label in ("comparison", "pricing", "alternative", "tutorial", "review", "listicle", "news/update"):
        if label == content_type:
            labels.add(label)
    if "agent" in lower or "agents" in lower:
        labels.add("ai agents")
    if "seo" in lower:
        labels.add("seo")
    if "coding" in lower or "developer" in lower:
        labels.add("ai coding")
    return sorted(labels)


def level_from_score(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def competition_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def business_value_level(affiliate: int, cpc: int, evergreen: int) -> str:
    blended = round(affiliate * 0.45 + cpc * 0.35 + evergreen * 0.20)
    return level_from_score(blended)


def priority_level(total_score: float) -> str:
    if total_score >= 70:
        return "P1"
    if total_score >= 55:
        return "P2"
    return "P3"


def suggest_internal_links(topic: str, content_type: str) -> list[str]:
    lower = topic.lower()
    links = ["/", "/reviews/", "/comparisons/"]
    if "seo" in lower:
        links.extend(["/category/seo-tools/", "/review/surfer-seo/", "/compare/semrush-vs-ahrefs/"])
    if "coding" in lower or "developer" in lower or "github" in lower or "cursor" in lower:
        links.extend(["/category/ai-coding-tools/", "/compare/cursor-vs-github-copilot-2026/", "/review/windsurf-review-2026/"])
    if "video" in lower:
        links.extend(["/category/video-tools/", "/best-ai-video-tools-2026/", "/review/synthesia/"])
    if "writing" in lower or "assistant" in lower:
        links.extend(["/category/ai-writing-tools/", "/grammarly-review-2026/", "/jasper-ai-review-2026/"])
    if "automation" in lower or "zapier" in lower:
        links.extend(["/category/automation-tools/", "/zapier-pricing/", "/compare/make-vs-zapier/"])
    if "website" in lower or "builder" in lower:
        links.extend(["/category/website-builder-tools/", "/best-website-builder-2026/", "/website-builder-software-review/"])
    if content_type == "pricing":
        links.append("/pricing/")
    return unique(links)[:10]


def suggest_article_angle(topic: str, content_type: str) -> str:
    if content_type == "comparison":
        return f"Compare {topic} through buyer-fit, workflow limits, pricing checks, and practical use cases."
    if content_type == "pricing":
        return f"Explain {topic} with current-plan verification steps, hidden cost risks, and who should pay."
    if content_type == "alternative":
        return f"Position {topic} as a shortlist guide with clear decision criteria and safer alternatives."
    if content_type == "tutorial":
        return f"Turn {topic} into a practical workflow guide with checks, examples, and mistakes to avoid."
    if content_type == "listicle":
        return f"Build {topic} as a curated buyer guide, not a generic ranked list."
    return f"Review {topic} with independent methodology, use cases, pricing cautions, pros, cons, and alternatives."


def suggest_video_angle(topic: str, content_type: str) -> str:
    if content_type == "comparison":
        return f"Fast side-by-side explainer: where each option wins, what to verify, and the safer buyer choice for {topic}."
    if content_type == "pricing":
        return f"Short pricing explainer for {topic}: what to check before paying and which users should wait."
    if content_type == "listicle":
        return f"Quick shortlist video for {topic}, with one practical use case per tool."
    return f"Three-to-five minute review video for {topic}: overview, features, pricing cautions, pros, cons, alternatives, verdict."


def keyword_hits(text: str, terms: set[str]) -> int:
    lower = text.lower()
    return sum(phrase_present(lower, term) for term in terms)


def phrase_present(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text.lower()))


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower())) - {"2025", "2026", "review", "guide", "best", "the", "and", "for", "with"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ")).strip()


def first_match(source: str, pattern: str) -> str:
    match = re.search(pattern, source, flags=re.I | re.S)
    return match.group(1) if match else ""


def xml_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def parse_number(value: object) -> float:
    match = re.search(r"[\d,.]+", str(value or "").replace(",", ""))
    return float(match.group(0)) if match else 0


def clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def save_discovery_result(result: DiscoveryResult, output: Path | None = None) -> tuple[Path, Path]:
    target = output or settings.data_dir / "trending_topics.json"
    report = settings.data_dir / "trending_topics_daily_report.md"
    archive = settings.data_dir / "trend_reports" / f"{result.generated_at[:10]}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_content = daily_report(result)
    report.write_text(report_content, encoding="utf-8")
    archive.write_text(report_content, encoding="utf-8")
    return target, report


def daily_report(result: DiscoveryResult) -> str:
    lines = [
        "# AI Trend Discovery Daily Report",
        "",
        f"Generated: {result.generated_at}",
        f"Candidates evaluated: {result.candidates_evaluated}",
        f"Published topics checked: {result.published_topics_checked}",
        "",
        "## Selected Topics",
        "",
    ]
    for rank, topic in enumerate(result.selected_topics, 1):
        lines.extend(
            [
                f"### {rank}. {topic.topic}",
                "",
                f"- Score: **{topic.total_score}/100** | Confidence: **{topic.confidence}**",
                f"- Priority: **{topic.recommended_priority}** | Intent: **{topic.search_intent}** | Type: **{topic.content_type}**",
                f"- Business value: **{topic.estimated_business_value}** | Affiliate potential: **{topic.affiliate_potential}** | Competition level: **{topic.competition_level}**",
                f"- Classifications: {', '.join(topic.classifications)}",
                f"- Sources: {', '.join(topic.sources)}",
                f"- Search potential: {topic.search_volume_potential}; Competition: {topic.competition}; Affiliate: {topic.affiliate_opportunity}",
                f"- Evergreen: {topic.evergreen_value}; Freshness: {topic.news_freshness}; CPC potential: {topic.cpc_potential}",
                f"- Article angle: {topic.suggested_article_angle}",
                f"- Video angle: {topic.suggested_video_angle}",
                f"- Suggested internal links: {', '.join(topic.suggested_internal_links)}",
                *[f"- {reason}" for reason in topic.why_selected],
                "",
            ]
        )
    lines.extend(["## Source Status", ""])
    for source, status in result.source_status.items():
        lines.append(f"- **{source}**: {status.get('status')} ({status.get('signals', 0)} signals){' - ' + str(status.get('detail')) if status.get('detail') else ''}")
    lines.extend(["", "## Methodology", "", "Scores are directional opportunity estimates. No articles were generated."])
    return "\n".join(lines) + "\n"
