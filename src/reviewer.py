from __future__ import annotations


def build_review_workflow(project: dict) -> dict:
    total_score = int(project.get("total_score", 0) or 0)
    affiliate_quality_score = int(project.get("affiliate_quality_score", 0) or 0)
    data_product_value_score = int(project.get("data_product_value_score", 0) or 0)
    ad_readiness_score = int(project.get("ad_readiness_score", 0) or 0)
    commission_text = str(project.get("commission_text", "")).strip()
    payout_text = str(project.get("payout_text", "")).strip()
    affiliate_url = str(project.get("affiliate_url", "")).strip()
    status = str(project.get("status", "")).strip()

    affiliate_found = bool(project.get("affiliate_found", False))
    legal_pages_found = bool(project.get("legal_pages_found", False))
    cookie_days = int(project.get("cookie_days", 0) or 0)
    recurring = bool(project.get("recurring", False))

    checklist = build_verification_checklist(
        affiliate_found=affiliate_found,
        affiliate_url=affiliate_url,
        commission_text=commission_text,
        payout_text=payout_text,
        cookie_days=cookie_days,
        legal_pages_found=legal_pages_found,
        recurring=recurring,
        status=status,
    )

    review_status = determine_review_status(
        total_score=total_score,
        affiliate_quality_score=affiliate_quality_score,
        checklist=checklist,
    )
    sale_status = determine_sale_status(
        review_status=review_status,
        data_product_value_score=data_product_value_score,
    )
    ads_status = determine_ads_status(
        review_status=review_status,
        ad_readiness_score=ad_readiness_score,
    )

    return {
        "review_status": review_status,
        "verification_checklist": " | ".join(checklist),
        "sale_status": sale_status,
        "ads_status": ads_status,
        "manual_review_url": affiliate_url,
    }


def build_verification_checklist(
    affiliate_found: bool,
    affiliate_url: str,
    commission_text: str,
    payout_text: str,
    cookie_days: int,
    legal_pages_found: bool,
    recurring: bool,
    status: str,
) -> list[str]:
    checklist = []

    if not affiliate_found or not affiliate_url:
        checklist.append("find official affiliate page")
    else:
        checklist.append("open affiliate page and confirm program is active")

    if not commission_text:
        checklist.append("confirm commission rate")

    if recurring:
        checklist.append("confirm recurring duration and cancellation rules")

    if cookie_days == 0:
        checklist.append("confirm cookie window")

    if not payout_text:
        checklist.append("confirm payout method and payout schedule")

    if not legal_pages_found:
        checklist.append("check terms, privacy, and affiliate restrictions")

    if status != "ok":
        checklist.append("check site availability")

    checklist.append("capture proof screenshot before selling")
    checklist.append("record allowed traffic sources before ads")
    return checklist


def determine_review_status(total_score: int, affiliate_quality_score: int, checklist: list[str]) -> str:
    required_checks = set(checklist)
    blocking_checks = {
        "find official affiliate page",
        "confirm commission rate",
        "check site availability",
    }
    if required_checks.intersection(blocking_checks):
        return "needs_manual_review"
    if total_score >= 80 and affiliate_quality_score >= 80:
        return "ready_for_verification"
    if total_score >= 50:
        return "research_more"
    return "watchlist"


def determine_sale_status(review_status: str, data_product_value_score: int) -> str:
    if review_status == "ready_for_verification" and data_product_value_score >= 80:
        return "can_package_after_proof"
    if review_status in {"ready_for_verification", "research_more"} and data_product_value_score >= 65:
        return "verify_before_selling"
    if review_status == "needs_manual_review":
        return "blocked_until_verified"
    return "do_not_sell_yet"


def determine_ads_status(review_status: str, ad_readiness_score: int) -> str:
    if review_status == "ready_for_verification" and ad_readiness_score >= 75:
        return "prepare_ad_test_after_terms_check"
    if ad_readiness_score >= 60:
        return "manual_terms_check_required"
    return "not_ready_for_ads"
