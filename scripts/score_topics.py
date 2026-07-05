from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.content_planner import DailyContentPlanner
from modules.content_strategy import ContentStrategyEngine
from modules.social_score import SocialValueEstimator
from modules.topic_ranker import TopicRanker
from modules.topic_scorer import TopicFeatureSet, TopicScorer, TopicScore
from modules.video_priority import VideoPriorityEngine


NUMERIC_FEATURES = {
    "trend_score",
    "search_intent",
    "seo_opportunity",
    "competition_level",
    "affiliate_value",
    "buyer_intent",
    "cpc_potential",
    "evergreen_potential",
    "freshness",
    "social_share_potential",
    "reddit_discussion_potential",
    "quora_potential",
    "linkedin_potential",
    "youtube_potential",
    "internal_linking_opportunity",
    "brand_fit",
    "difficulty",
    "estimated_traffic",
    "estimated_conversion",
}

LEVEL_SCORES = {
    "very high": 90,
    "high": 75,
    "medium": 55,
    "moderate": 55,
    "low": 35,
    "very low": 20,
}

INTENT_SCORES = {
    "transactional": 82,
    "commercial": 76,
    "commercial investigation": 76,
    "comparison": 74,
    "review": 72,
    "pricing": 80,
    "alternative": 72,
    "free trial": 70,
    "informational": 48,
    "tutorial": 50,
    "navigational": 42,
}


def clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def score_value(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return 100 if value else 0
    if isinstance(value, (int, float)):
        return clamp_score(float(value))
    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", " ").replace("-", " ")
        if not normalized:
            return default
        if normalized in LEVEL_SCORES:
            return LEVEL_SCORES[normalized]
        if normalized in INTENT_SCORES:
            return INTENT_SCORES[normalized]
        try:
            return clamp_score(float(normalized))
        except ValueError:
            return default
    if isinstance(value, list):
        return clamp_score(min(100, len(value) * 15))
    return default


def extract_topic_items(raw_topics: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_topics, list):
        return [item for item in raw_topics if isinstance(item, dict)]
    if isinstance(raw_topics, dict):
        for key in ("all_candidates", "selected_topics", "topics", "candidates"):
            value = raw_topics.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Topic input must be a list or a JSON object containing selected_topics/topics/candidates.")


def source_contains(item: Dict[str, Any], needle: str) -> bool:
    sources = item.get("sources", [])
    if isinstance(sources, str):
        sources = [sources]
    return any(needle.lower() in str(source).lower() for source in sources)


def text_contains(item: Dict[str, Any], needles: Iterable[str]) -> bool:
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("topic", "slug", "search_intent", "content_type", "suggested_article_angle", "suggested_video_angle")
    ).lower()
    return any(needle in haystack for needle in needles)


BUYER_TERMS = (
    "review",
    "comparison",
    "best",
    "alternatives",
    "alternative",
    "pricing",
    " vs ",
    "discount",
    "coupon",
    "lifetime deal",
    "promo",
    "features",
    "pros and cons",
    "tutorial",
    "guide",
    "how to",
    "top tools",
)

NEWS_TERMS = (
    "breaking news",
    "funding",
    "launch",
    "launched",
    "announced",
    "announces",
    "unveils",
    "warns",
    "show hn",
    "today",
    "yesterday",
    "aws says",
    "anthropic says",
    "openai says",
    "stock movement",
    "stock",
    "stocks",
    "rallying",
    "buy now",
    "at risk",
    "press release",
)


def adapt_topic_item(item: Dict[str, Any]) -> TopicFeatureSet:
    topic = str(item.get("topic", "")).strip()
    content_type = str(item.get("content_type", item.get("search_intent", ""))).strip().lower()
    buyer_topic = text_contains(item, BUYER_TERMS)
    news_topic = text_contains(item, NEWS_TERMS)
    search_intent = score_value(item.get("search_intent"), default=score_value(content_type, 50))
    affiliate_value = score_value(item.get("affiliate_opportunity", item.get("affiliate_potential", item.get("affiliate_value"))), 45)
    competition = score_value(item.get("competition", item.get("competition_level")), 50)
    traffic = score_value(item.get("search_volume_potential", item.get("estimated_traffic")), 50)
    cpc = score_value(item.get("cpc_potential"), 45)
    evergreen = score_value(item.get("evergreen_value", item.get("evergreen_potential")), 50)
    freshness = score_value(item.get("news_freshness", item.get("freshness", item.get("freshness_level"))), 50)
    trend = score_value(item.get("trend_score", item.get("total_score")), freshness)

    buyer_intent = score_value(item.get("buyer_intent"), default=0)
    if buyer_intent == 0:
        buyer_intent = clamp_score((search_intent + affiliate_value + cpc) / 3)
    if buyer_topic:
        search_intent = clamp_score(search_intent + 12)
        affiliate_value = clamp_score(affiliate_value + 14)
        buyer_intent = clamp_score(buyer_intent + 16)
        cpc = clamp_score(cpc + 10)
        evergreen = clamp_score(evergreen + 10)
    if text_contains(item, ("saas", "software", "platform", "subscription", "recurring", "tool", "tools")):
        affiliate_value = clamp_score(affiliate_value + 8)
        buyer_intent = clamp_score(buyer_intent + 6)

    link_count = item.get("suggested_internal_links", [])
    internal_links = score_value(link_count, default=45)

    social = clamp_score(
        freshness * 0.35
        + trend * 0.25
        + (70 if source_contains(item, "reddit") else 35) * 0.15
        + (70 if source_contains(item, "youtube") else 35) * 0.15
        + (65 if source_contains(item, "linkedin") else 35) * 0.1
    )

    youtube = score_value(item.get("youtube_potential"), 0)
    if youtube == 0:
        video_bonus = 75 if content_type in {"review", "comparison", "pricing", "alternative", "tutorial"} else 45
        youtube = clamp_score((video_bonus + trend + freshness) / 3)
    if buyer_topic or text_contains(item, ("demo", "walkthrough", "top 10", "best tools")):
        youtube = clamp_score(youtube + 12)

    seo_opportunity = score_value(item.get("seo_opportunity"), 0)
    if seo_opportunity == 0:
        seo_opportunity = clamp_score((traffic + evergreen + (100 - competition)) / 3)

    brand_fit = score_value(item.get("brand_fit"), 0)
    if brand_fit == 0:
        preferred = ("ai", "seo", "saas", "automation", "coding", "productivity", "marketing", "software", "tool")
        brand_fit = 78 if text_contains(item, preferred) else 48

    if news_topic:
        search_intent = clamp_score(search_intent - 18)
        affiliate_value = clamp_score(affiliate_value - 25)
        buyer_intent = clamp_score(buyer_intent - 25)
        evergreen = clamp_score(evergreen - 25)
        youtube = clamp_score(youtube - 15)
        brand_fit = clamp_score(brand_fit - 10)

    estimated_conversion = score_value(item.get("estimated_conversion"), 0)
    if estimated_conversion == 0:
        estimated_conversion = clamp_score((buyer_intent + affiliate_value + cpc) / 3)

    classifications = item.get("classifications", [])
    if isinstance(classifications, str):
        classifications = [classifications]
    tags = [str(tag) for tag in classifications if str(tag).strip()]
    if content_type and content_type not in tags:
        tags.append(content_type)

    sources = item.get("sources", "trending_topics")
    if isinstance(sources, list):
        source = ", ".join(str(source) for source in sources if str(source).strip()) or "trending_topics"
    else:
        source = str(sources or "trending_topics")

    feature_values = {
        "trend_score": trend,
        "search_intent": search_intent,
        "seo_opportunity": seo_opportunity,
        "competition_level": competition,
        "affiliate_value": affiliate_value,
        "buyer_intent": buyer_intent,
        "cpc_potential": cpc,
        "evergreen_potential": evergreen,
        "freshness": freshness,
        "social_share_potential": social,
        "reddit_discussion_potential": 72 if source_contains(item, "reddit") else clamp_score(social * 0.75),
        "quora_potential": 62 if text_contains(item, ("review", "comparison", "pricing", "alternative")) else 45,
        "linkedin_potential": 70 if text_contains(item, ("saas", "b2b", "business", "marketing", "automation")) else 50,
        "youtube_potential": youtube,
        "internal_linking_opportunity": internal_links,
        "brand_fit": brand_fit,
        "difficulty": competition,
        "estimated_traffic": traffic,
        "estimated_conversion": estimated_conversion,
    }

    # Preserve explicit demo-style numeric values when present while still accepting
    # discovery-style text fields such as "medium" or "comparison".
    for field in NUMERIC_FEATURES:
        if field in item and field not in {"search_intent", "competition_level"}:
            feature_values[field] = score_value(item.get(field), feature_values[field])

    return TopicFeatureSet(topic=topic, tags=tags, source=source, **feature_values)


def load_topic_inputs(path: str) -> List[TopicFeatureSet]:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"Topic input file not found: {json_path}")
    with json_path.open("r", encoding="utf-8") as handle:
        raw_topics = json.load(handle)
    return [adapt_topic_item(item) for item in extract_topic_items(raw_topics)]


def save_json(data: object, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def build_dashboard(scores: List[TopicScore], ranker: TopicRanker) -> object:
    ranked = sorted(scores, key=lambda score: score.total_score, reverse=True)
    dashboard = ranker.dashboard_summary(scores)
    dashboard["priority_decisions"] = [priority_decision(score, index) for index, score in enumerate(ranked[:25], 1)]
    return dashboard


def score_social_average(score: TopicScore) -> float:
    if not score.social_scores:
        return 0.0
    return round(sum(score.social_scores.values()) / max(len(score.social_scores), 1), 1)


def priority_decision(score: TopicScore, rank: int) -> Dict[str, object]:
    if rank == 1 and score.total_score >= 70:
        action = "TOP 1: Write now"
    elif rank in {2, 3} and score.total_score >= 70:
        action = "TOP 2-3: Write today"
    elif "YouTube" in str(score.content_decision) or score.features.youtube_potential >= 70:
        action = "Video candidate"
    elif score.features.evergreen_potential >= 70:
        action = "Evergreen candidate"
    elif 60 <= score.total_score < 70:
        action = "Watch"
    else:
        action = "Skip"
    return {
        "rank": rank,
        "topic": score.topic,
        "total_score": round(score.total_score, 1),
        "decision": action,
        "recommendation": score.recommendation,
        "content_decision": score.content_decision,
        "video_priority": score.video_priority,
    }


def score_to_plan_item(score: TopicScore) -> Dict[str, object]:
    return {
        "topic": score.topic,
        "total_score": round(score.total_score, 1),
        "score_grade": score.as_dict().get("score_grade"),
        "recommendation": score.recommendation,
        "content_decision": score.content_decision,
        "traffic_score": round(score.traffic_score, 1),
        "revenue_score": round(score.revenue_score, 1),
        "seo_score": round(score.seo_score, 1),
        "video_score": score.features.youtube_potential,
        "social_score": score_social_average(score),
        "evergreen_score": score.features.evergreen_potential,
        "trend_score": score.features.trend_score,
        "video_priority": score.video_priority,
        "source": score.features.source,
        "reason": score.reason,
    }


def build_plan(scores: List[TopicScore], planner: DailyContentPlanner) -> object:
    ranked = sorted(scores, key=lambda score: score.total_score, reverse=True)
    eligible = [score for score in ranked if score.total_score >= 70]
    return {
        "generated_mode": "planning_only_no_publish",
        "priority_decisions": [priority_decision(score, index) for index, score in enumerate(ranked[:25], 1)],
        "todays_top_10": [score_to_plan_item(score) for score in eligible[:10]],
        "top_3": [score_to_plan_item(score) for score in eligible[:3]],
        "highest_revenue": [score_to_plan_item(score) for score in sorted(scores, key=lambda score: score.revenue_score, reverse=True)[:10]],
        "highest_seo": [score_to_plan_item(score) for score in sorted(scores, key=lambda score: score.seo_score, reverse=True)[:10]],
        "highest_video": [score_to_plan_item(score) for score in sorted(scores, key=lambda score: score.features.youtube_potential, reverse=True)[:10]],
        "highest_social": [score_to_plan_item(score) for score in sorted(scores, key=score_social_average, reverse=True)[:10]],
        "evergreen": [score_to_plan_item(score) for score in sorted(scores, key=lambda score: score.features.evergreen_potential, reverse=True)[:10]],
        "trending": [score_to_plan_item(score) for score in sorted(scores, key=lambda score: score.features.trend_score, reverse=True)[:10]],
        "monitor": [score_to_plan_item(score) for score in ranked if 60 <= score.total_score < 70][:25],
        "skip": [score_to_plan_item(score) for score in ranked if score.total_score < 60][:50],
        "legacy_weekly_plan_preview": planner.summarize_plan(planner.build_plan(eligible[:10])),
    }


def score_topic_file(input_path: str, output_path: str, dashboard_output: str, plan_output: str, rules_path: str) -> List[TopicScore]:
    scorer = TopicScorer(rules_path=rules_path)
    strategy = ContentStrategyEngine()
    video_engine = VideoPriorityEngine()
    social_estimator = SocialValueEstimator()
    ranker = TopicRanker()
    planner = DailyContentPlanner()

    topics = load_topic_inputs(input_path)
    scored: List[TopicScore] = []

    for features in topics:
        score = scorer.score_topic(features)
        score.content_decision, _ = strategy.decide_content_type(score)
        score.video_priority = video_engine.prioritize(score)
        score.social_scores = social_estimator.estimate(features.topic, features.as_dict()).as_dict()
        scored.append(score)

    scored = ranker.rank_topics(scored)
    save_json([score.as_dict() for score in scored], Path(output_path))
    save_json(build_dashboard(scored, ranker), Path(dashboard_output))
    save_json(build_plan(scored, planner), Path(plan_output))
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(description="Score and prioritize topics for articles, video, and social planning.")
    parser.add_argument("--input", type=str, default="data/topic_inputs.json", help="Path to topic input JSON file.")
    parser.add_argument("--output", type=str, default="data/topic_scores.json", help="Path to write scored topic data.")
    parser.add_argument("--dashboard-output", type=str, default="data/topic_dashboard.json", help="Path to write dashboard JSON data.")
    parser.add_argument("--plan-output", type=str, default="data/topic_plan.json", help="Path to write daily plan JSON data.")
    parser.add_argument("--rules", type=str, default="data/topic_scoring_rules.json", help="Path to topic scoring rules.")
    parser.add_argument("--update-history", action="store_true", help="Append/update hottrend history CSV/Excel outputs after scoring.")
    args = parser.parse_args()

    scored = score_topic_file(args.input, args.output, args.dashboard_output, args.plan_output, args.rules)
    history_result = None
    if args.update_history:
        from scripts.update_hottrend_tracking import update_hottrend_tracking

        history_result = update_hottrend_tracking(scores_path=Path(args.output))

    print(f"Scored {len(scored)} topics and wrote to {args.output}")
    print(f"Dashboard output: {args.dashboard_output}")
    print(f"Plan output: {args.plan_output}")
    if history_result:
        print(f"Hottrend history CSV: {history_result['history']}")
        print(f"Hottrend latest dashboard CSV: {history_result['latest_dashboard']}")
        print(f"Hottrend weekly summary CSV: {history_result['weekly']}")
        print(f"Hottrend monthly summary CSV: {history_result['monthly']}")
        print(f"Hottrend Excel written: {history_result['excel_written']}")
        print(f"Hottrend master Excel written: {history_result['master_excel_written']}")
        print(f"Hottrend HTML dashboard: {history_result['html_dashboard']}")
    for idx, score in enumerate(scored, 1):
        print(
            f"{idx:02d}. {score.topic} | total={score.total_score} | traffic={score.traffic_score} | revenue={score.revenue_score} | seo={score.seo_score} | recommendation={score.recommendation} | decision={score.content_decision} | video={score.video_priority}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
