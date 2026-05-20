from __future__ import annotations

import csv
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


SITE_BASE = "https://review.mssmileenglish.com"
DATA_DIR = Path("data")
SITEMAP_PATH = Path("docs/sitemap.xml")


@dataclass(frozen=True)
class ReplyResult:
    title: str
    url: str
    tracked_url: str
    page_type: str
    score: int


def _tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) > 1]


def _title_from_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.strip("/")
    if not path:
        return "MS Smile AI Review Hub"
    slug = path.split("/")[-1]
    return slug.replace("-", " ").title()


def _page_type_from_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    if "/comparisons/" in path or "/compare/" in path:
        return "comparison"
    if "/review/" in path or "/reviews/" in path:
        return "review"
    if "/blog/" in path:
        return "blog"
    if "/category/" in path:
        return "category"
    if "/pricing/" in path:
        return "pricing"
    return "page"


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sitemap_urls() -> list[str]:
    if not SITEMAP_PATH.exists():
        return []
    try:
        root = ET.fromstring(SITEMAP_PATH.read_text(encoding="utf-8"))
    except ET.ParseError:
        return []
    urls: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text and "/go/" not in loc.text:
            urls.append(loc.text.strip())
    return urls


def _tracked_url(url: str, query: str, source: str = "quick_reply") -> str:
    parsed = urllib.parse.urlsplit(url)
    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("utm_source", source)
    params.setdefault("utm_medium", "social_comment")
    params.setdefault("utm_campaign", "quick_reply")
    params.setdefault("utm_content", re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")[:80] or "comment")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(params), parsed.fragment))


def build_article_index() -> list[dict[str, str]]:
    items: dict[str, dict[str, str]] = {}

    for url in _sitemap_urls():
        if "/vi/" in urllib.parse.urlsplit(url).path:
            continue
        if any(part in url for part in ["/go/", "/rss.xml", "/sitemap/"]):
            continue
        items[url] = {
            "title": _title_from_url(url),
            "url": url,
            "page_type": _page_type_from_url(url),
            "keywords": _title_from_url(url),
            "topic": "",
        }

    for row in _read_csv_rows(DATA_DIR / "topical_map.csv"):
        url = row.get("page_url", "").strip()
        if not url or "/vi/" in url or "/go/" in url:
            continue
        items[url] = {
            "title": row.get("title", "") or _title_from_url(url),
            "url": url,
            "page_type": row.get("page_type", "") or _page_type_from_url(url),
            "keywords": " ".join([row.get("title", ""), row.get("topic_group", "")]),
            "topic": row.get("topic_group", ""),
        }

    for row in _read_csv_rows(DATA_DIR / "comparison_pages_index.csv"):
        slug = row.get("comparison_slug", "").strip()
        if not slug:
            continue
        url = f"{SITE_BASE}/comparisons/{slug}/"
        items.setdefault(url, {
            "title": row.get("title", "") or _title_from_url(url),
            "url": url,
            "page_type": "comparison",
            "keywords": " ".join([slug, row.get("tool_a_name", ""), row.get("tool_b_name", ""), row.get("title", "")]),
            "topic": row.get("category", ""),
        })

    for row in _read_csv_rows(DATA_DIR / "review_pages_index.csv"):
        slug = row.get("review_slug", "").strip()
        if not slug:
            continue
        url = f"{SITE_BASE}/reviews/{slug}/"
        items.setdefault(url, {
            "title": row.get("title", "") or _title_from_url(url),
            "url": url,
            "page_type": "review",
            "keywords": " ".join([slug, row.get("brand_name", ""), row.get("title", "")]),
            "topic": row.get("category", ""),
        })

    codex_openclaw_url = f"{SITE_BASE}/comparisons/codex-vs-openclaw/"
    items[codex_openclaw_url] = {
        "title": "Codex vs OpenClaw",
        "url": codex_openclaw_url,
        "page_type": "comparison",
        "keywords": "codex openclaw codex vs openclaw codex workflow openclaw prototype AI coding workflow debugging repair",
        "topic": "AI coding tools",
    }

    return list(items.values())


def find_related_articles(query: str, limit: int = 3) -> list[ReplyResult]:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []
    results: list[ReplyResult] = []
    for item in build_article_index():
        haystack = " ".join([item.get("title", ""), item.get("url", ""), item.get("keywords", ""), item.get("topic", "")])
        tokens = set(_tokenize(haystack))
        overlap = query_tokens & tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        lowered = haystack.lower()
        for phrase in [query.lower(), query.lower().replace(" ", "-")]:
            if phrase and phrase in lowered:
                score += 35
        if item.get("page_type") == "comparison" and any(word in query.lower() for word in ["vs", "versus", "compare"]):
            score += 15
        if item.get("page_type") == "review" and "review" in query.lower():
            score += 15
        url = item["url"]
        results.append(ReplyResult(
            title=item.get("title", "") or _title_from_url(url),
            url=url.replace(SITE_BASE, ""),
            tracked_url=_tracked_url(url, query),
            page_type=item.get("page_type", "page"),
            score=score,
        ))
    results.sort(key=lambda result: (-result.score, result.url))
    return results[:limit]


def generate_reply_examples(query: str, results: list[ReplyResult]) -> list[str]:
    if not results:
        return [
            f"I do not have a perfect link for '{query}' yet, but I would compare the tools by workflow stage: first build, debugging, cleanup, and publishing.",
        ]
    primary = results[0]
    link = primary.tracked_url
    lower = query.lower()
    if "openclaw" in lower or ("codex" in lower and "workflow" in lower):
        first = (
            "I would split this by workflow stage. OpenClaw is worth testing for quick prototype exploration, "
            f"while Codex is stronger for focused cleanup and repair tasks. Practical breakdown: {link}"
        )
        second = (
            "The useful question is not which tool is magic. It is which one handles the second failed fix better. "
            f"I wrote a non-hype comparison here: {link}"
        )
        third = (
            "My take: use OpenClaw for trying the shape of an idea, then use Codex when the repo needs careful fixes. "
            f"This comparison explains the workflow: {link}"
        )
        return [first, second, third]
    if "vs" in lower or "codex" in lower or "copilot" in lower:
        first = (
            "I would compare them by the cleanup phase, not just autocomplete speed. "
            f"I wrote a practical note that may help here: {link}"
        )
    elif "review" in lower or "worth" in lower:
        first = (
            "My quick take: check the real workflow fit before judging the tool from demos. "
            f"This practical review/comparison may help: {link}"
        )
    else:
        first = (
            "I would start with the use case first, then pick the tool. "
            f"I documented a related workflow here: {link}"
        )
    second = (
        "One thing that helped me: test what happens after the first failed fix. "
        f"This page has the closest example I have published: {link}"
    )
    third = (
        "If you are deciding now, I would shortlist by workflow: draft speed, debugging, cleanup, and deployment. "
        f"This might save you some time: {link}"
    )
    return [first, second, third]


def generate_platform_reply_examples(query: str, results: list[ReplyResult]) -> dict[str, list[str]]:
    if not results:
        fallback = "I would compare the tools by workflow stage first: prototype, debugging, cleanup, and publishing."
        return {"facebook": [fallback], "reddit": [fallback], "quora": [fallback]}
    link = results[0].tracked_url
    lower = query.lower()
    if "openclaw" in lower or "codex" in lower:
        facebook = [
            "I would not judge this from demos only. OpenClaw seems more interesting for rough exploration, while Codex is better when the repo needs focused cleanup. I wrote a practical breakdown here: " + link,
            "My take: the workflow matters more than picking one winner. Prototype first, then use the stronger repair tool when bugs show up. This may help: " + link,
            "I have been comparing this by the second-fix test, not first-output speed. That changes the answer quite a bit: " + link,
        ]
        reddit = [
            "I would be careful calling either one the winner. OpenClaw looks more useful for rough experimentation; Codex is where I would put focused repair/cleanup tasks. I wrote a deeper breakdown here if useful: " + link,
            "For me the real benchmark is not the first generated answer. It is whether the tool can recover after a messy second fix. This comparison covers that angle: " + link,
            "I would split the workflow: use OpenClaw to explore the shape, then Codex for targeted fixes. Not flashy, but more practical in real projects: " + link,
        ]
        quora = [
            "A practical way to compare them is by workflow stage. Use OpenClaw-style tools for fast prototype exploration, then use Codex when the project needs focused repair, refactoring, or validation. I wrote a detailed comparison here: " + link,
            "The best choice depends on whether you need a first draft or a cleanup pass. Codex is stronger for focused fixes; OpenClaw is worth testing for early exploration. More detail: " + link,
            "I would not choose only by benchmark demos. Test a real task, then see which tool handles cleanup better. This breakdown may help: " + link,
        ]
        return {"facebook": facebook, "reddit": reddit, "quora": quora}
    replies = generate_reply_examples(query, results)
    return {"facebook": replies, "reddit": replies, "quora": replies}


def quick_reply(query: str, limit: int = 3) -> dict[str, object]:
    results = find_related_articles(query, limit=limit)
    return {
        "query": query,
        "results": results,
        "replies": generate_reply_examples(query, results),
        "platform_replies": generate_platform_reply_examples(query, results),
    }
