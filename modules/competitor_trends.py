from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import json
import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET


USER_AGENT = "SmileAIReviewHub-CompetitorTrendScanner/1.0 (+https://smileaireviewhub.com/contact/)"
AI_TERMS = {
    "ai", "agent", "agents", "automation", "coding", "seo", "video", "image", "writing",
    "productivity", "assistant", "software", "saas", "marketing", "website", "builder",
}
COMMERCIAL_TERMS = {
    "review", "pricing", "price", "alternatives", "alternative", "best", "compare", "comparison",
    "vs", "trial", "discount", "software", "tool", "platform",
}
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "was", "how",
    "what", "why", "who", "into", "its", "our", "new", "2026", "best", "top", "using",
}


@dataclass
class CompetitorArticle:
    competitor: str
    url: str
    title: str = ""
    slug: str = ""
    description: str = ""
    h1: str = ""
    h2: list[str] = field(default_factory=list)
    published_at: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class TrendCandidate:
    competitor: str
    detected_url: str
    keyword: str
    trend_score: float
    freshness_score: float
    competitor_frequency: int
    relevance_score: float
    commercial_intent_score: float
    affiliate_potential: float
    content_gap_score: float
    internal_link_score: float
    suggested_article_title: str
    recommended_action: str
    existing_url: str = ""
    source_count: int = 1


def fetch_text(url: str, timeout: int = 20) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,text/html,*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), ""
    except (URLError, TimeoutError, OSError):
        return 0, ""


def robots_allows(url: str, fetcher: Callable[[str], tuple[int, str]] = fetch_text) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    status, source = fetcher(robots_url)
    if status != 200:
        return True
    parser = RobotFileParser()
    parser.parse(source.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def clean_text(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", unescape(value or "")).split())


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.casefold())).strip("-")


def parse_feed(source: str, competitor: str) -> list[CompetitorArticle]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return []
    output = []
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items:
        title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
        link = item.findtext("link") or ""
        if not link:
            node = item.find("{http://www.w3.org/2005/Atom}link")
            link = node.get("href", "") if node is not None else ""
        description = (
            item.findtext("description")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        )
        published = (
            item.findtext("pubDate")
            or item.findtext("{http://www.w3.org/2005/Atom}published")
            or item.findtext("{http://www.w3.org/2005/Atom}updated")
            or ""
        )
        if link and title:
            output.append(
                CompetitorArticle(
                    competitor=competitor,
                    url=link.strip(),
                    title=clean_text(title),
                    slug=slugify(urlparse(link).path),
                    description=clean_text(description),
                    published_at=published.strip(),
                )
            )
    return output


def parse_sitemap(source: str, competitor: str, limit: int) -> list[CompetitorArticle]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return []
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    rows = []
    for node in root.findall(f".//{namespace}url"):
        loc = node.findtext(f"{namespace}loc", "").strip()
        lastmod = node.findtext(f"{namespace}lastmod", "").strip()
        if loc:
            rows.append(CompetitorArticle(competitor=competitor, url=loc, slug=slugify(urlparse(loc).path), published_at=lastmod))
    return sorted(rows, key=lambda item: item.published_at, reverse=True)[:limit]


def parse_sitemap_index(source: str) -> list[str]:
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return []
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [
        str(node.text or "").strip()
        for node in root.findall(f".//{namespace}sitemap/{namespace}loc")
        if str(node.text or "").strip()
    ]


def enrich_html(article: CompetitorArticle, source: str) -> CompetitorArticle:
    title = re.search(r"<title[^>]*>(.*?)</title>", source, re.I | re.S)
    description = re.search(
        r"<meta\b(?=[^>]*name=['\"]description['\"])(?=[^>]*content=['\"]([^'\"]*)['\"])[^>]*>",
        source,
        re.I,
    )
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.I | re.S)
    h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", source, re.I | re.S)
    article.title = clean_text(title.group(1)) if title else article.title
    article.description = clean_text(description.group(1)) if description else article.description
    article.h1 = clean_text(h1.group(1)) if h1 else ""
    article.h2 = [clean_text(value) for value in h2[:12] if clean_text(value)]
    article.keywords = extract_keywords(" ".join([article.title, article.description, article.h1, *article.h2]))
    return article


def extract_keywords(text: str, limit: int = 10) -> list[str]:
    words = [word for word in re.findall(r"[a-z][a-z0-9-]{2,}", text.casefold()) if word not in STOPWORDS]
    unigrams = Counter(words)
    bigrams = Counter(f"{left} {right}" for left, right in zip(words, words[1:]) if left != right)
    ranked = sorted(
        [(score + 1, value) for value, score in bigrams.items()]
        + [(score, value) for value, score in unigrams.items()],
        reverse=True,
    )
    output = []
    for _, value in ranked:
        if value not in output:
            output.append(value)
        if len(output) >= limit:
            break
    return output


def inventory(root: Path) -> list[tuple[str, str, str]]:
    rows = []
    for path in root.rglob("index.html"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("go/", "assets/")):
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"<title[^>]*>(.*?)</title>", source, re.I | re.S)
        url = "https://smileaireviewhub.com/" if rel == "index.html" else f"https://smileaireviewhub.com/{rel[:-len('/index.html')]}/"
        rows.append((slugify(rel), clean_text(title.group(1)) if title else "", url))
    return rows


def closest_existing(topic: str, pages: list[tuple[str, str, str]]) -> tuple[float, str]:
    normalized = slugify(topic)
    best = (0.0, "")
    topic_tokens = set(normalized.split("-"))
    for slug, title, url in pages:
        candidate = f"{slug} {slugify(title)}"
        candidate_tokens = set(candidate.split("-"))
        overlap = len(topic_tokens & candidate_tokens) / max(1, len(topic_tokens | candidate_tokens))
        sequence = SequenceMatcher(None, normalized, slug).ratio()
        score = max(overlap, sequence)
        if score > best[0]:
            best = (score, url)
    return best


def score_articles(articles: list[CompetitorArticle], own_pages: list[tuple[str, str, str]]) -> list[TrendCandidate]:
    topic_sources: dict[str, set[str]] = defaultdict(set)
    topic_articles: dict[str, list[CompetitorArticle]] = defaultdict(list)
    for article in articles:
        if not article.keywords:
            article.keywords = extract_keywords(" ".join([article.title, article.description, article.h1, *article.h2]))
        for keyword in article.keywords[:6]:
            topic_sources[keyword].add(article.competitor)
            topic_articles[keyword].append(article)
    output = []
    for keyword, matched in topic_articles.items():
        sources = topic_sources[keyword]
        representative = matched[0]
        age_days = 30
        try:
            try:
                parsed = datetime.fromisoformat(representative.published_at.replace("Z", "+00:00"))
            except ValueError:
                parsed = parsedate_to_datetime(representative.published_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).days)
        except (ValueError, TypeError):
            pass
        freshness = max(20.0, 100.0 - age_days * 3)
        frequency = min(100.0, 35.0 + len(sources) * 22.0 + min(20, len(matched) * 4))
        tokens = set(keyword.split())
        relevance = 90.0 if tokens & AI_TERMS else 55.0
        commercial = 90.0 if tokens & COMMERCIAL_TERMS else 55.0
        affiliate = min(95.0, commercial * 0.65 + (20 if tokens & {"software", "tool", "platform", "builder"} else 5))
        similarity, existing_url = closest_existing(keyword, own_pages)
        content_gap = max(10.0, 100.0 - similarity * 100)
        internal_link = min(95.0, 35.0 + similarity * 60)
        score = (
            freshness * 0.18
            + frequency * 0.17
            + relevance * 0.18
            + commercial * 0.14
            + affiliate * 0.13
            + content_gap * 0.13
            + internal_link * 0.07
        )
        if similarity >= 0.72:
            action = "refresh"
        elif relevance < 60 or commercial < 50:
            action = "ignore"
        else:
            action = "create"
        output.append(
            TrendCandidate(
                competitor=", ".join(sorted(sources)),
                detected_url=representative.url,
                keyword=keyword,
                trend_score=round(score, 1),
                freshness_score=round(freshness, 1),
                competitor_frequency=len(sources),
                relevance_score=round(relevance, 1),
                commercial_intent_score=round(commercial, 1),
                affiliate_potential=round(affiliate, 1),
                content_gap_score=round(content_gap, 1),
                internal_link_score=round(internal_link, 1),
                suggested_article_title=suggest_title(keyword, action),
                recommended_action=action,
                existing_url=existing_url if action == "refresh" else "",
                source_count=len(matched),
            )
        )
    return sorted(output, key=lambda item: item.trend_score, reverse=True)


def suggest_title(keyword: str, action: str) -> str:
    title = keyword.title()
    if action == "refresh":
        return f"Update: {title} Guide 2026"
    if any(term in keyword.split() for term in ("review", "pricing", "alternatives", "comparison")):
        return f"{title} 2026"
    return f"{title}: Practical Tools and Buyer Guide 2026"


def scan_competitors(
    competitors: list[dict[str, object]],
    own_root: Path,
    *,
    max_items: int = 15,
    delay_seconds: float = 1.0,
    fetcher: Callable[[str], tuple[int, str]] = fetch_text,
) -> tuple[list[TrendCandidate], list[str]]:
    articles: list[CompetitorArticle] = []
    failures: list[str] = []
    seen_urls: set[str] = set()
    robots_cache: dict[str, RobotFileParser | None] = {}

    def allowed(url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in robots_cache:
            status, source = fetcher(f"{origin}/robots.txt")
            if status != 200:
                robots_cache[origin] = None
            else:
                parser = RobotFileParser()
                parser.parse(source.splitlines())
                robots_cache[origin] = parser
        parser = robots_cache[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    for competitor in sorted(competitors, key=lambda row: float(row.get("priority", 0)), reverse=True):
        name = str(competitor.get("name") or competitor.get("website_url") or "competitor")
        sources = [
            ("rss", str(competitor.get("rss_url") or "")),
            ("sitemap", str(competitor.get("sitemap_url") or "")),
        ]
        candidate_articles: list[CompetitorArticle] = []
        for source_type, url in sources:
            if not url:
                continue
            if not allowed(url):
                failures.append(f"{name}: robots.txt disallows {url}")
                continue
            status, source = fetcher(url)
            if status != 200:
                failures.append(f"{name}: {url} returned HTTP {status}")
                continue
            parsed = parse_feed(source, name) if source_type == "rss" else parse_sitemap(source, name, max_items)
            if source_type == "sitemap" and not parsed:
                for child_url in parse_sitemap_index(source)[:5]:
                    if not allowed(child_url):
                        failures.append(f"{name}: robots.txt disallows {child_url}")
                        continue
                    child_status, child_source = fetcher(child_url)
                    if child_status == 200:
                        parsed.extend(parse_sitemap(child_source, name, max_items))
                    else:
                        failures.append(f"{name}: {child_url} returned HTTP {child_status}")
                    if delay_seconds:
                        time.sleep(delay_seconds)
            candidate_articles.extend(parsed[:max_items])
            if delay_seconds:
                time.sleep(delay_seconds)
        for article in candidate_articles:
            if article.url in seen_urls:
                continue
            seen_urls.add(article.url)
            if article.title and article.description:
                article.keywords = extract_keywords(f"{article.title} {article.description}")
                articles.append(article)
                continue
            if not allowed(article.url):
                failures.append(f"{name}: robots.txt disallows article {article.url}")
                continue
            status, source = fetcher(article.url)
            if status == 200:
                articles.append(enrich_html(article, source))
            else:
                failures.append(f"{name}: article {article.url} returned HTTP {status}")
            if delay_seconds:
                time.sleep(delay_seconds)
    return score_articles(articles, inventory(own_root)), failures


def write_reports(candidates: list[TrendCandidate], failures: list[str], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "competitor-trends.json"
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "candidates": [asdict(item) for item in candidates],
                "failures": failures,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = ["# Competitor Trend Report", "", f"Candidates: {len(candidates)}", f"Failures: {len(failures)}", ""]
    for item in candidates:
        lines.extend(
            [
                f"## {item.suggested_article_title}",
                f"- Competitor: {item.competitor}",
                f"- Detected URL: {item.detected_url}",
                f"- Keyword/topic: {item.keyword}",
                f"- Trend score: {item.trend_score}",
                f"- Affiliate potential: {item.affiliate_potential}",
                f"- Recommended action: {item.recommended_action}",
                f"- Existing URL: {item.existing_url or 'None'}",
                "",
            ]
        )
    if failures:
        lines.extend(["## Fetch warnings", *[f"- {value}" for value in failures]])
    md_path = report_dir / "competitor-trends.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
