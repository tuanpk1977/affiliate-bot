from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from config import settings


OPPORTUNITY_COLUMNS = [
    "keyword",
    "keyword_group",
    "page_type",
    "priority_rank",
    "competition_score",
    "affiliate_intent_score",
    "ranking_opportunity",
    "commercial_value",
    "seo_priority_score",
    "recommended_action",
    "reason",
    "suggested_slug",
    "target_page_title",
]

SUMMARY_COLUMNS = [
    "total_keywords",
    "total_unique_keywords",
    "duplicate_removed",
    "high_opportunity_keywords",
    "low_competition_keywords",
    "top_affiliate_keywords",
    "top_10_money_pages",
    "top_10_supporting_articles",
    "skip_count",
]

PRIORITY_PLAN_COLUMNS = [
    "priority_rank",
    "keyword",
    "keyword_group",
    "page_type",
    "seo_priority_score",
    "suggested_slug",
    "target_page_title",
    "reason",
]

HIGH_INTENT_TERMS = [
    "pricing",
    "review",
    "alternative",
    "alternatives",
    "vs",
    "comparison",
    "best",
    "coupon",
    "discount",
    "buy",
    "deal",
    "ai tool",
]

VERY_HIGH_COMPETITION_TERMS = [
    "best ai tools",
    "top ai",
    "chatgpt alternatives",
]

KEYWORD_INTELLIGENCE_REPORT_COLUMNS = [
    "keyword",
    "topic_cluster",
    "intent",
    "page_url",
    "current_page_exists",
    "competition_level",
    "content_gap",
    "social_angle",
    "priority_score",
    "next_action",
]


def load_keywords(path: Path | None = None) -> pd.DataFrame:
    source = path or settings.keywords_file
    if not source.exists():
        return pd.DataFrame()
    return pd.read_csv(source).fillna("")


def analyze_keyword_opportunities(keywords: pd.DataFrame) -> pd.DataFrame:
    if keywords.empty:
        return pd.DataFrame(columns=OPPORTUNITY_COLUMNS)

    rows: list[dict] = []
    for _, row in keywords.iterrows():
        keyword = normalize_keyword(str(row.get("keyword", "")))
        if not keyword:
            continue
        if is_low_quality_short_keyword(keyword):
            continue
        competition_score = score_competition(keyword, row)
        affiliate_intent_score = score_affiliate_intent(keyword, row)
        commercial_value = score_commercial_value(keyword, row, affiliate_intent_score)
        ranking_opportunity = score_ranking_opportunity(competition_score, affiliate_intent_score, row)
        seo_priority_score = round(
            affiliate_intent_score * 0.35
            + commercial_value * 0.25
            + ranking_opportunity * 0.30
            + max(0, 100 - competition_score) * 0.10
        )
        keyword_group = classify_keyword_group(keyword)
        final_score = int(max(0, min(100, seo_priority_score)))
        page_type = classify_page_type(keyword_group, final_score, competition_score)
        rows.append(
            {
                "keyword": keyword,
                "keyword_group": keyword_group,
                "page_type": page_type,
                "priority_rank": 0,
                "competition_score": competition_score,
                "affiliate_intent_score": affiliate_intent_score,
                "ranking_opportunity": ranking_opportunity,
                "commercial_value": commercial_value,
                "seo_priority_score": final_score,
                "recommended_action": recommended_action(final_score),
                "reason": build_reason(final_score, competition_score, affiliate_intent_score, keyword_group),
                "suggested_slug": suggested_slug(keyword),
                "target_page_title": target_page_title(keyword, keyword_group),
            }
        )
    result = pd.DataFrame(rows, columns=OPPORTUNITY_COLUMNS)
    if result.empty:
        return result
    result = dedupe_keywords(result)
    result = result.sort_values(["seo_priority_score", "affiliate_intent_score"], ascending=False).reset_index(drop=True)
    result["priority_rank"] = range(1, len(result) + 1)
    return result[OPPORTUNITY_COLUMNS]


def build_keyword_priority_plan(opportunities: pd.DataFrame) -> pd.DataFrame:
    if opportunities.empty:
        return pd.DataFrame(columns=PRIORITY_PLAN_COLUMNS)
    plan = opportunities[opportunities["page_type"].isin(["money_page", "comparison_page", "supporting_article"])].head(30)
    return plan[PRIORITY_PLAN_COLUMNS].reset_index(drop=True)


def build_keyword_intelligence_summary(opportunities: pd.DataFrame, total_keywords: int = 0) -> pd.DataFrame:
    if opportunities.empty:
        return pd.DataFrame([{column: 0 if column not in {"top_affiliate_keywords", "top_10_money_pages", "top_10_supporting_articles"} else "" for column in SUMMARY_COLUMNS}])
    top_keywords = opportunities.sort_values("affiliate_intent_score", ascending=False).head(10)["keyword"].tolist()
    money_pages = opportunities[opportunities["page_type"].isin(["money_page", "comparison_page"])].head(10)["keyword"].tolist()
    supporting = opportunities[opportunities["page_type"] == "supporting_article"].head(10)["keyword"].tolist()
    total_unique = len(opportunities)
    original_total = total_keywords or total_unique
    return pd.DataFrame(
        [
            {
                "total_keywords": original_total,
                "total_unique_keywords": total_unique,
                "duplicate_removed": max(0, original_total - total_unique),
                "high_opportunity_keywords": int((opportunities["seo_priority_score"] >= 75).sum()),
                "low_competition_keywords": int((opportunities["competition_score"] <= 45).sum()),
                "top_affiliate_keywords": " | ".join(top_keywords),
                "top_10_money_pages": " | ".join(money_pages),
                "top_10_supporting_articles": " | ".join(supporting),
                "skip_count": int((opportunities["page_type"] == "skip").sum()),
            }
        ],
        columns=SUMMARY_COLUMNS,
    )


def run_keyword_intelligence(keywords: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = keywords if keywords is not None else load_keywords()
    opportunities = analyze_keyword_opportunities(source)
    summary = build_keyword_intelligence_summary(opportunities, total_keywords=len(source))
    priority_plan = build_keyword_priority_plan(opportunities)
    opportunities.to_csv(settings.data_dir / "keyword_opportunities.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(settings.data_dir / "keyword_intelligence_summary.csv", index=False, encoding="utf-8-sig")
    priority_plan.to_csv(settings.data_dir / "keyword_priority_plan.csv", index=False, encoding="utf-8-sig")
    return opportunities, summary


def run_keyword_intelligence_report() -> pd.DataFrame:
    """Build a page-aware keyword strategy report for SEO/AEO decisions."""
    report = build_keyword_intelligence_report()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(settings.data_dir / "keyword_intelligence_report.csv", index=False, encoding="utf-8-sig")
    return report


def build_keyword_intelligence_report() -> pd.DataFrame:
    pages = load_site_pages()
    topical = load_optional_csv(settings.data_dir / "topical_map.csv")
    social = load_optional_csv(settings.data_dir / "social_calendar.csv")
    keywords = collect_keyword_candidates(pages, topical, social)
    if not keywords:
        return pd.DataFrame(columns=KEYWORD_INTELLIGENCE_REPORT_COLUMNS)
    rows: list[dict[str, object]] = []
    page_index = build_page_index(pages)
    for keyword in sorted(set(keywords)):
        normalized = normalize_keyword(keyword)
        if not normalized or is_low_quality_short_keyword(normalized):
            continue
        intent = detect_keyword_intent(normalized)
        cluster = topic_cluster_for_keyword(normalized)
        matched_page = match_keyword_to_page(normalized, page_index)
        exists = bool(matched_page)
        competition_score = score_competition(normalized, {})
        intent_score = score_affiliate_intent(normalized, {})
        gap = keyword_content_gap(normalized, intent, matched_page)
        priority = keyword_priority_score(intent_score, competition_score, gap, exists)
        rows.append(
            {
                "keyword": normalized,
                "topic_cluster": cluster,
                "intent": intent,
                "page_url": matched_page.get("url", "") if matched_page else "",
                "current_page_exists": str(exists).lower(),
                "competition_level": competition_level_label(competition_score),
                "content_gap": gap,
                "social_angle": social_angle_for_keyword(normalized, intent),
                "priority_score": priority,
                "next_action": keyword_next_action(gap, priority, intent),
            }
        )
    report = pd.DataFrame(rows, columns=KEYWORD_INTELLIGENCE_REPORT_COLUMNS)
    if report.empty:
        return report
    return report.sort_values(["priority_score", "keyword"], ascending=[False, True]).reset_index(drop=True)


def score_affiliate_intent(keyword: str, row: pd.Series | dict | None = None) -> int:
    text = keyword.lower()
    score = 25
    for term in HIGH_INTENT_TERMS:
        if term in text:
            score += 12
    if " vs " in f" {text} " or text.count(" vs") or text.count("vs "):
        score += 16
    group = str(_row_get(row, "keyword_group", "")).lower()
    if group in {"buyer_keywords", "review_keywords", "comparison_keywords", "alternatives_keywords"}:
        score += 15
    intent_score = _safe_int(_row_get(row, "intent_score", 0), 0)
    if intent_score:
        score += min(20, max(0, int((intent_score - 50) / 2)))
    return int(max(0, min(100, score)))


def score_competition(keyword: str, row: pd.Series | dict | None = None) -> int:
    text = keyword.lower()
    if any(term in text for term in VERY_HIGH_COMPETITION_TERMS):
        return 92
    level = str(_row_get(row, "competition_level", "")).lower()
    base = {"low": 35, "medium": 58, "high": 78}.get(level, 55)
    words = [word for word in text.replace("/", " ").split() if word]
    if len(words) >= 3:
        base -= 8
    if any(term in text for term in ["pricing", "review", " vs ", "alternative", "alternatives"]):
        base -= 10
    if any(term in text for term in ["best", "top", "tools"]):
        base += 12
    if looks_niche_keyword(text):
        base -= 10
    return int(max(15, min(100, base)))


def score_ranking_opportunity(competition_score: int, affiliate_intent_score: int, row: pd.Series | dict | None = None) -> int:
    opportunity = 100 - competition_score
    if affiliate_intent_score >= 75:
        opportunity += 12
    if looks_niche_keyword(str(_row_get(row, "keyword", "")).lower()):
        opportunity += 10
    return int(max(0, min(100, opportunity)))


def score_commercial_value(keyword: str, row: pd.Series | dict | None, affiliate_intent_score: int) -> int:
    cpc = _safe_float(_row_get(row, "estimated_cpc", 2.0), 2.0)
    value = 35 + affiliate_intent_score * 0.45 + min(25, cpc * 4)
    text = keyword.lower()
    if any(term in text for term in ["pricing", "buy", "coupon", "discount", "deal"]):
        value += 12
    if any(term in text for term in ["free", "template", "examples"]):
        value -= 10
    return int(max(0, min(100, round(value))))


def recommended_action(score: float) -> str:
    if score >= 75:
        return "build_priority_page"
    if score >= 50:
        return "supporting_article"
    return "skip"


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword.strip().lower())


def is_low_quality_short_keyword(keyword: str) -> bool:
    words = keyword.split()
    if len(keyword) < 5:
        return True
    if len(words) == 1 and words[0] in {"free", "job", "jobs", "tool", "tools", "software", "app"}:
        return True
    return False


def canonical_keyword(keyword: str) -> str:
    text = normalize_keyword(keyword)
    replacements = {
        "alternatives": "alternative",
        "tools": "tool",
        "reviews": "review",
        "comparisons": "comparison",
        "software": "tool",
    }
    for old, new in replacements.items():
        text = re.sub(rf"\b{old}\b", new, text)
    return text


def dedupe_keywords(opportunities: pd.DataFrame) -> pd.DataFrame:
    if opportunities.empty:
        return opportunities
    data = opportunities.copy()
    data["_canonical_keyword"] = data["keyword"].map(canonical_keyword)
    data = data.sort_values(["seo_priority_score", "affiliate_intent_score", "commercial_value"], ascending=False)
    data = data.drop_duplicates(subset=["_canonical_keyword"], keep="first")
    return data.drop(columns=["_canonical_keyword"]).reset_index(drop=True)


def classify_keyword_group(keyword: str) -> str:
    text = normalize_keyword(keyword)
    if "alternative" in text:
        return "alternatives"
    if "pricing" in text or "price" in text or "cost" in text:
        return "pricing"
    if "review" in text:
        return "review"
    if " vs " in f" {text} " or "comparison" in text or "compare" in text:
        return "comparison"
    if "best" in text or "top" in text:
        return "best_tools"
    if "automation" in text or "automate" in text:
        return "automation"
    return "other"


def classify_page_type(keyword_group: str, score: int, competition_score: int) -> str:
    if score < 50 or competition_score >= 90:
        return "skip"
    if keyword_group == "comparison":
        return "comparison_page"
    if keyword_group in {"alternatives", "pricing", "review", "best_tools"} and score >= 60:
        return "money_page"
    if score >= 50:
        return "supporting_article"
    return "skip"


def build_reason(score: int, competition_score: int, affiliate_intent_score: int, keyword_group: str) -> str:
    if score >= 75 and competition_score <= 45 and affiliate_intent_score >= 70:
        return "High affiliate intent + low competition"
    if score >= 75:
        return "Strong commercial intent and good page opportunity"
    if score >= 50:
        return "Good supporting topic"
    if competition_score >= 80:
        return "Too broad / high competition"
    if affiliate_intent_score < 45:
        return "Low affiliate intent"
    return "Low SEO priority"


def suggested_slug(keyword: str) -> str:
    text = normalize_keyword(keyword)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def target_page_title(keyword: str, keyword_group: str) -> str:
    title_keyword = " ".join(word.upper() if word in {"ai", "seo", "crm"} else word.capitalize() for word in normalize_keyword(keyword).split())
    if keyword_group == "alternatives":
        base = title_keyword.replace(" Alternatives", "")
        return f"Best {base} Alternatives for 2026"
    if keyword_group == "pricing":
        return f"{title_keyword}: Pricing, Plans, and What to Check Before Buying"
    if keyword_group == "review":
        return f"{title_keyword}: Research-Style Review for 2026"
    if keyword_group == "comparison":
        parts = re.split(r"\s+vs\s+", normalize_keyword(keyword), flags=re.IGNORECASE)
        if len(parts) == 2:
            left = humanize_tool_name(parts[0])
            right = humanize_tool_name(parts[1])
            return f"{left} vs {right}: Which Tool Is Better?"
        return f"{title_keyword}: Tool Comparison Guide"
    if keyword_group == "best_tools":
        return f"{title_keyword} for 2026"
    if keyword_group == "automation":
        return f"{title_keyword}: Practical Automation Guide"
    return f"{title_keyword}: Research Guide"


def humanize_tool_name(value: str) -> str:
    known = {
        "github copilot": "GitHub Copilot",
        "copilot": "GitHub Copilot",
        "cursor": "Cursor",
        "semrush": "Semrush",
        "surfer seo": "Surfer SEO",
        "chatgpt": "ChatGPT",
    }
    text = normalize_keyword(value)
    if text in known:
        return known[text]
    return " ".join(word.upper() if word in {"ai", "seo", "crm"} else word.capitalize() for word in text.split())


def looks_niche_keyword(keyword: str) -> bool:
    return any(term in keyword for term in ["cursor pricing", "semrush review", "copilot vs cursor", "github copilot pricing", "surfer seo pricing"])


def _safe_int(value: object, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _row_get(row: pd.Series | dict | None, key: str, default: object = "") -> object:
    if row is None:
        return default
    try:
        return row.get(key, default)
    except Exception:
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def load_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path).fillna("")
    except Exception:
        return pd.DataFrame()


def load_site_pages() -> list[dict[str, str]]:
    output = settings.site_output_dir
    pages: list[dict[str, str]] = []
    if not output.exists():
        return pages
    for file in sorted(output.rglob("index.html")):
        rel = file.relative_to(output).as_posix()
        if rel.startswith(("assets/", "go/")):
            continue
        url = "/" if rel == "index.html" else "/" + rel.removesuffix("index.html")
        text = file.read_text(encoding="utf-8", errors="ignore")
        title = extract_tag(text, "title")
        h1 = extract_tag(text, "h1")
        body = re.sub(r"<[^>]+>", " ", text)
        body = re.sub(r"\s+", " ", body)
        pages.append({"url": url, "title": title, "h1": h1, "text": body[:6000], "slug": page_slug(url)})
    return pages


def extract_tag(html_text: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"<[^>]+>", " ", match.group(1)).strip()


def collect_keyword_candidates(pages: list[dict[str, str]], topical: pd.DataFrame, social: pd.DataFrame) -> list[str]:
    candidates: list[str] = []
    raw_keywords = load_keywords()
    if not raw_keywords.empty and "keyword" in raw_keywords.columns:
        candidates.extend(raw_keywords["keyword"].astype(str).tolist())
    for page in pages:
        candidates.extend(keyword_variants_from_page(page))
    if not topical.empty:
        for column in ["title", "page_url", "topic_group"]:
            if column in topical.columns:
                candidates.extend(topical[column].astype(str).map(keyword_from_text).tolist())
    if not social.empty:
        for column in ["post_title", "topic", "target_url"]:
            if column in social.columns:
                candidates.extend(social[column].astype(str).map(keyword_from_text).tolist())
    return [item for item in candidates if item]


def keyword_variants_from_page(page: dict[str, str]) -> list[str]:
    title = keyword_from_text(page.get("title") or page.get("h1") or page.get("slug", ""))
    slug = page.get("slug", "").replace("-", " ")
    variants = [title, slug]
    if "/pricing/" in page.get("url", ""):
        variants.append(f"{slug} pricing")
    if "/compare/" in page.get("url", "") or "/comparisons/" in page.get("url", ""):
        variants.append(slug.replace(" vs ", " vs "))
    if "review" in page.get("url", ""):
        variants.append(f"{slug} review")
    return [normalize_keyword(item) for item in variants if item]


def keyword_from_text(value: str) -> str:
    text = str(value or "")
    parsed = urlparse(text)
    if parsed.path:
        text = parsed.path.strip("/").split("/")[-1].replace("-", " ")
    text = re.sub(r"\b(2026|review|guide|pricing|plans|which tool is better)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^a-zA-Z0-9 .+-]+", " ", text)
    return normalize_keyword(text)


def build_page_index(pages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{**page, "search": normalize_keyword(" ".join([page.get("url", ""), page.get("title", ""), page.get("h1", ""), page.get("slug", "")]))} for page in pages]


def match_keyword_to_page(keyword: str, pages: list[dict[str, str]]) -> dict[str, str] | None:
    slug = suggested_slug(keyword)
    for page in pages:
        if page.get("slug") == slug or page.get("url", "").strip("/") == slug:
            return page
    key_terms = [term for term in re.split(r"\s+", keyword) if len(term) > 2]
    if not key_terms:
        return None
    scored: list[tuple[int, dict[str, str]]] = []
    for page in pages:
        search = page.get("search", "")
        score = sum(1 for term in key_terms if term in search)
        if score:
            scored.append((score, page))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored[0][0] >= max(1, min(3, len(key_terms))) else None


def detect_keyword_intent(keyword: str) -> str:
    text = normalize_keyword(keyword)
    if " vs " in f" {text} " or "comparison" in text or "compare" in text:
        return "comparison"
    if "pricing" in text or "price" in text or "cost" in text:
        return "pricing"
    if "alternative" in text:
        return "alternative"
    if "review" in text:
        return "review"
    if text.startswith("best ") or " best " in f" {text} ":
        return "best_tools"
    if any(term in text for term in ["how to", "workflow", "fix", "debug", "tutorial"]):
        return "tutorial"
    return "review"


def topic_cluster_for_keyword(keyword: str) -> str:
    text = normalize_keyword(keyword)
    if any(term in text for term in ["cursor", "copilot", "codex", "windsurf", "coding", "debug", "repo"]):
        return "AI coding tools"
    if any(term in text for term in ["seo", "semrush", "ahrefs", "surfer"]):
        return "AI SEO tools"
    if any(term in text for term in ["writing", "jasper", "copy", "content"]):
        return "AI writing tools"
    if any(term in text for term in ["automation", "make", "zapier", "workflow"]):
        return "AI automation tools"
    if "pricing" in text:
        return "pricing"
    if "alternative" in text:
        return "alternatives"
    if " vs " in f" {text} ":
        return "comparisons"
    return "general"


def keyword_content_gap(keyword: str, intent: str, page: dict[str, str] | None) -> str:
    if not page:
        return "missing_page"
    text = normalize_keyword(page.get("text", ""))
    word_count = len(text.split())
    if word_count < 800:
        return "thin_content"
    if intent == "comparison" and not any(term in text for term in ["comparison", " vs ", "tradeoff", "which"]):
        return "needs_comparison"
    if intent == "pricing" and not any(term in text for term in ["pricing", "plan", "cost", "contract"]):
        return "needs_pricing_section"
    if not any(term in text for term in ["use case", "workflow", "best for", "who should"]):
        return "needs_use_case"
    return "ready"


def keyword_priority_score(intent_score: int, competition_score: int, gap: str, exists: bool) -> int:
    gap_bonus = {
        "missing_page": 22,
        "needs_comparison": 18,
        "needs_pricing_section": 16,
        "needs_use_case": 12,
        "thin_content": 10,
        "ready": -5,
    }.get(gap, 0)
    score = intent_score * 0.45 + (100 - competition_score) * 0.30 + gap_bonus + (0 if exists else 10)
    return int(max(0, min(100, round(score))))


def competition_level_label(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def social_angle_for_keyword(keyword: str, intent: str) -> str:
    if intent == "comparison":
        return "comparison debate / practical tradeoff"
    if intent == "pricing":
        return "pricing reality / buying risk"
    if intent == "alternative":
        return "switching story / alternatives"
    if "workflow" in keyword or "debug" in keyword:
        return "builder workflow / failure case"
    if intent == "best_tools":
        return "shortlist / decision guide"
    return "practical review / use case"


def keyword_next_action(gap: str, priority: int, intent: str) -> str:
    if gap == "missing_page" and priority >= 60:
        return f"build_{intent}_page"
    if gap in {"needs_comparison", "needs_pricing_section", "needs_use_case"}:
        return f"update_existing_page_{gap}"
    if gap == "thin_content":
        return "expand_content_depth"
    if priority >= 70:
        return "promote_with_internal_links_and_social"
    return "monitor"


def page_slug(url: str) -> str:
    parsed = urlparse(str(url or ""))
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    return parts[-1] if parts else "homepage"
