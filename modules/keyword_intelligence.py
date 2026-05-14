from __future__ import annotations

import re
from pathlib import Path

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
    opportunities.to_csv(settings.data_dir / "keyword_opportunities.csv", index=False)
    summary.to_csv(settings.data_dir / "keyword_intelligence_summary.csv", index=False)
    priority_plan.to_csv(settings.data_dir / "keyword_priority_plan.csv", index=False)
    return opportunities, summary


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
