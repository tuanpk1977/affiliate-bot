from __future__ import annotations


HIGH_VALUE_CATEGORIES = {
    "ai",
    "saas",
    "crypto",
    "trading",
    "marketplace",
    "devtools",
    "dev tools",
    "finance",
    "marketing",
}
MID_VALUE_CATEGORIES = {"education", "ecommerce", "productivity", "creator", "health"}


def score_project(project: dict) -> dict:
    category = normalize_category(project.get("category", ""))
    homepage_desc = str(project.get("homepage_description", "")).strip()
    commission_text = str(project.get("commission_text", "")).strip()
    payout_text = str(project.get("payout_text", "")).strip()
    commission_type = str(project.get("commission_type", "")).strip()
    status = str(project.get("status", "")).strip()

    affiliate_found = bool(project.get("affiliate_found", False))
    legal_pages_found = bool(project.get("legal_pages_found", False))
    linkedin_found = bool(project.get("linkedin_found", False))
    blog_found = bool(project.get("blog_found", False))
    changelog_found = bool(project.get("changelog_found", False))
    recurring = bool(project.get("recurring", False))
    cookie_days = int(project.get("cookie_days", 0) or 0)
    commission_percent = float(project.get("commission_percent", 0) or 0)
    flat_commission_amount = float(project.get("flat_commission_amount", 0) or 0)

    program_score = 0
    program_score += 25 if affiliate_found else 0
    program_score += 20 if commission_text else 0
    program_score += 10 if cookie_days >= 30 else 5 if cookie_days > 0 else 0
    program_score += 10 if payout_text else 0

    economics_score = 0
    economics_score += 20 if recurring else 0
    economics_score += commission_percent_score(commission_percent)
    economics_score += flat_commission_score(flat_commission_amount)
    economics_score += 5 if commission_type in {"recurring", "percentage", "flat"} else 0

    trust_score = 0
    trust_score += 15 if status == "ok" else 0
    trust_score += 8 if legal_pages_found else 0
    trust_score += 7 if linkedin_found else 0

    market_score = market_fit_score(category)
    activity_score = 0
    activity_score += 8 if blog_found else 0
    activity_score += 7 if changelog_found else 0
    activity_score += 5 if homepage_desc else 0

    affiliate_quality_score = min(
        100,
        program_score + economics_score + trust_score + market_score + activity_score,
    )

    data_product_value_score = min(
        100,
        affiliate_quality_score
        + (10 if recurring else 0)
        + (10 if commission_percent >= 30 or flat_commission_amount >= 50 else 0)
        + (5 if cookie_days >= 60 else 0),
    )

    ad_readiness_score = min(
        100,
        market_score
        + (20 if affiliate_found and commission_text else 0)
        + (15 if recurring or commission_percent >= 30 or flat_commission_amount >= 50 else 0)
        + (10 if cookie_days >= 30 else 0)
        + (10 if status == "ok" else 0)
        + (5 if homepage_desc else 0),
    )

    total_score = round(
        affiliate_quality_score * 0.5
        + data_product_value_score * 0.3
        + ad_readiness_score * 0.2
    )

    verdict = build_verdict(total_score, affiliate_found, commission_text)
    recommended_action = build_recommended_action(total_score, ad_readiness_score, affiliate_found)
    target_audience = suggest_target_audience(category)
    selling_angle = build_selling_angle(
        category,
        affiliate_found,
        recurring,
        commission_percent,
        flat_commission_amount,
        cookie_days,
    )
    reasoning = build_reasoning(
        category,
        affiliate_found,
        recurring,
        commission_text,
        cookie_days,
        blog_found,
        changelog_found,
        payout_text,
    )

    return {
        "program_score": program_score,
        "economics_score": economics_score,
        "trust_score": trust_score,
        "market_score": market_score,
        "activity_score": activity_score,
        "affiliate_quality_score": affiliate_quality_score,
        "data_product_value_score": data_product_value_score,
        "ad_readiness_score": ad_readiness_score,
        "total_score": total_score,
        "verdict": verdict,
        "recommended_action": recommended_action,
        "target_audience": target_audience,
        "selling_angle": selling_angle,
        "reasoning": reasoning,
    }


def normalize_category(category: object) -> str:
    return str(category).strip().lower()


def commission_percent_score(percent: float) -> int:
    if percent >= 50:
        return 25
    if percent >= 30:
        return 20
    if percent >= 20:
        return 15
    if percent > 0:
        return 8
    return 0


def flat_commission_score(amount: float) -> int:
    if amount >= 100:
        return 25
    if amount >= 50:
        return 20
    if amount >= 20:
        return 12
    if amount > 0:
        return 6
    return 0


def market_fit_score(category: str) -> int:
    if category in HIGH_VALUE_CATEGORIES:
        return 20
    if category in MID_VALUE_CATEGORIES:
        return 12
    return 6


def build_verdict(total_score: int, affiliate_found: bool, commission_text: str) -> str:
    if total_score >= 80:
        return "Premium lead"
    if total_score >= 65:
        return "Good lead"
    if total_score >= 50:
        return "Research more"
    if affiliate_found and not commission_text:
        return "Needs manual commission check"
    return "Low priority"


def build_recommended_action(total_score: int, ad_readiness_score: int, affiliate_found: bool) -> str:
    if total_score >= 80 and ad_readiness_score >= 70:
        return "Package as paid lead and prepare ad test"
    if total_score >= 65:
        return "Package as paid lead after manual verification"
    if affiliate_found:
        return "Manually verify terms before selling"
    return "Keep in watchlist"


def suggest_target_audience(category: str) -> str:
    mapping = {
        "ai": "AI tool reviewers, newsletter owners, YouTube educators",
        "saas": "SaaS affiliates, B2B creators, software comparison sites",
        "devtools": "developer creators, technical bloggers, coding channels",
        "dev tools": "developer creators, technical bloggers, coding channels",
        "crypto": "crypto communities, trading educators, finance newsletters",
        "trading": "trading educators, finance newsletters, Telegram communities",
        "marketplace": "deal bloggers, eCommerce creators, comparison sites, coupon communities",
        "ecommerce": "deal bloggers, shopping communities, product reviewers",
        "education": "course creators, tutorial blogs, study communities",
        "marketing": "growth marketers, agency owners, marketing newsletters",
        "finance": "finance bloggers, comparison sites, investing newsletters",
    }
    return mapping.get(category, "affiliate marketers, niche bloggers, content creators")


def build_selling_angle(
    category: str,
    affiliate_found: bool,
    recurring: bool,
    commission_percent: float,
    flat_commission_amount: float,
    cookie_days: int,
) -> str:
    benefits = []
    if recurring:
        benefits.append("recurring revenue")
    if commission_percent >= 30:
        benefits.append(f"high {commission_percent:g}% commission")
    if flat_commission_amount >= 50:
        benefits.append(f"${flat_commission_amount:g} flat payout")
    if cookie_days >= 60:
        benefits.append("lifetime cookie" if cookie_days >= 9999 else f"{cookie_days}-day cookie")
    if affiliate_found and not benefits:
        benefits.append("affiliate program found")
    if not benefits:
        benefits.append("needs affiliate program verification")

    label = category.upper() if category else "GENERAL"
    return f"{label} lead with " + ", ".join(benefits)


def build_reasoning(
    category: str,
    affiliate_found: bool,
    recurring: bool,
    commission_text: str,
    cookie_days: int,
    blog_found: bool,
    changelog_found: bool,
    payout_text: str,
) -> str:
    reasoning = []
    if affiliate_found:
        reasoning.append("affiliate page found")
    if commission_text:
        reasoning.append(f"commission: {commission_text}")
    if recurring:
        reasoning.append("recurring signal")
    if cookie_days:
        reasoning.append(f"cookie: {cookie_days} days")
    if payout_text:
        reasoning.append(f"payout: {payout_text}")
    if category:
        reasoning.append(f"category: {category}")
    if blog_found or changelog_found:
        reasoning.append("activity signal found")
    return "; ".join(reasoning)
