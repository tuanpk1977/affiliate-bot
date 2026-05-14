from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OPPORTUNITIES = ROOT / "data" / "keyword_opportunities.csv"
SUMMARY = ROOT / "data" / "keyword_intelligence_summary.csv"
PRIORITY_PLAN = ROOT / "data" / "keyword_priority_plan.csv"

OPPORTUNITY_COLUMNS = {
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
}

SUMMARY_COLUMNS = {
    "total_keywords",
    "total_unique_keywords",
    "duplicate_removed",
    "high_opportunity_keywords",
    "low_competition_keywords",
    "top_affiliate_keywords",
    "top_10_money_pages",
    "top_10_supporting_articles",
    "skip_count",
}

PRIORITY_PLAN_COLUMNS = {
    "priority_rank",
    "keyword",
    "keyword_group",
    "page_type",
    "seo_priority_score",
    "suggested_slug",
    "target_page_title",
    "reason",
}

TRUNCATED_ENDINGS = {"mark", "bui", "al", "soft", "prod", "autom", "altern", "compar"}
EXPECTED_FULL_PHRASES = {
    "email marketing alternatives",
    "website builder alternatives",
    "ai coding alternatives",
}


def main() -> int:
    errors: list[str] = []
    errors.extend(validate_csv(OPPORTUNITIES, OPPORTUNITY_COLUMNS, "keyword_opportunities.csv"))
    errors.extend(validate_csv(SUMMARY, SUMMARY_COLUMNS, "keyword_intelligence_summary.csv"))
    errors.extend(validate_csv(PRIORITY_PLAN, PRIORITY_PLAN_COLUMNS, "keyword_priority_plan.csv"))
    if errors:
        print("Keyword intelligence validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    opportunities = pd.read_csv(OPPORTUNITIES).fillna("")
    summary = pd.read_csv(SUMMARY).fillna("")
    priority_plan = pd.read_csv(PRIORITY_PLAN).fillna("")
    if opportunities["keyword"].duplicated().any():
        print("Keyword intelligence validation failed:")
        print("- data/keyword_opportunities.csv contains duplicate keywords")
        return 1
    integrity_errors = validate_text_integrity(opportunities, "keyword_opportunities.csv")
    integrity_errors.extend(validate_text_integrity(priority_plan, "keyword_priority_plan.csv"))
    if integrity_errors:
        print("Keyword intelligence validation failed:")
        for error in integrity_errors:
            print(f"- {error}")
        return 1
    if len(priority_plan) > 30:
        print("Keyword intelligence validation failed:")
        print("- data/keyword_priority_plan.csv has more than 30 rows")
        return 1
    print("Keyword intelligence validation passed.")
    print(f"- opportunities: {len(opportunities)}")
    print(f"- priority_plan: {len(priority_plan)}")
    print(f"- summary: {summary.iloc[0].to_dict() if not summary.empty else {}}")
    return 0


def validate_text_integrity(df: pd.DataFrame, label: str) -> list[str]:
    errors: list[str] = []
    required = {"keyword", "suggested_slug", "target_page_title"}
    if not required.issubset(df.columns):
        return errors
    for idx, row in df.iterrows():
        keyword = str(row.get("keyword", "")).strip()
        slug = str(row.get("suggested_slug", "")).strip()
        title = str(row.get("target_page_title", "")).strip()
        words = keyword.split()
        if len(keyword) < 5 or not words:
            errors.append(f"{label} row {idx + 2}: keyword too short: {keyword!r}")
            continue
        last_word = words[-1].lower()
        if last_word in TRUNCATED_ENDINGS:
            errors.append(f"{label} row {idx + 2}: keyword appears truncated: {keyword!r}")
        for word in words:
            if word.lower() in TRUNCATED_ENDINGS:
                errors.append(f"{label} row {idx + 2}: keyword contains truncated token {word!r}: {keyword!r}")
                break
        if not slug or slug.endswith(tuple(f"-{ending}" for ending in TRUNCATED_ENDINGS)) or slug in TRUNCATED_ENDINGS:
            errors.append(f"{label} row {idx + 2}: suggested_slug appears truncated: {slug!r}")
        if len(title) < len(keyword) or any(f" {ending.title()} " in f" {title} " for ending in TRUNCATED_ENDINGS):
            errors.append(f"{label} row {idx + 2}: target_page_title may be truncated: {title!r}")
    existing_keywords = set(str(value).strip().lower() for value in df["keyword"])
    missing_expected = EXPECTED_FULL_PHRASES & existing_keywords
    for phrase in missing_expected:
        expected_slug = phrase.replace(" ", "-")
        row = df[df["keyword"].astype(str).str.lower() == phrase].iloc[0]
        if str(row.get("suggested_slug", "")) != expected_slug:
            errors.append(f"{label}: expected full slug {expected_slug!r} for keyword {phrase!r}")
    return errors


def validate_csv(path: Path, required_columns: set[str], label: str) -> list[str]:
    if not path.exists():
        return [f"missing data/{label}"]
    try:
        df = pd.read_csv(path).fillna("")
    except Exception as exc:
        return [f"cannot read data/{label}: {exc}"]
    errors: list[str] = []
    missing = required_columns - set(df.columns)
    if missing:
        errors.append(f"data/{label} missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        errors.append(f"data/{label} is empty")
    return errors


if __name__ == "__main__":
    sys.exit(main())
