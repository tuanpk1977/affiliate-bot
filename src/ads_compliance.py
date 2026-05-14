from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

HIGH_RISK_CATEGORIES = {"crypto", "trading", "finance"}

PAID_TRAFFIC_BLOCKERS = {
    "paid search prohibited": ["paid search is prohibited", "paid search prohibited", "no paid search"],
    "ppc prohibited": ["ppc is prohibited", "ppc prohibited", "no ppc", "pay-per-click prohibited"],
    "google ads prohibited": ["google ads prohibited", "google adwords prohibited", "no google ads"],
    "bing ads prohibited": ["bing ads prohibited", "microsoft ads prohibited", "no bing ads"],
    "trademark bidding prohibited": [
        "trademark bidding prohibited",
        "brand bidding prohibited",
        "no brand bidding",
        "do not bid on our brand",
        "may not bid on",
    ],
    "direct linking prohibited": [
        "direct linking prohibited",
        "direct linking is not allowed",
        "no direct linking",
    ],
}

PAID_TRAFFIC_ALLOWED = [
    "paid search allowed",
    "ppc allowed",
    "google ads allowed",
    "bing ads allowed",
    "microsoft ads allowed",
]

DISCLOSURE_SIGNALS = [
    "affiliate disclosure",
    "advertising disclosure",
    "risk disclosure",
    "privacy policy",
    "terms of service",
    "terms and conditions",
]


def build_ads_compliance_precheck(project: dict, timeout: int, user_agent: str) -> dict:
    category = str(project.get("category", "")).strip().lower()
    affiliate_url = str(project.get("manual_review_url") or project.get("affiliate_url") or "").strip()
    headers = {"User-Agent": user_agent}

    text = str(project.get("affiliate_text", "")).strip()
    fetch_error = ""
    if affiliate_url and len(text) < 500:
        fetched_text, fetch_error = fetch_text(affiliate_url, headers, timeout)
        if fetched_text:
            text = fetched_text

    lowered = normalize_text(text)
    findings = detect_findings(lowered)
    has_allowed_signal = any(signal in lowered for signal in PAID_TRAFFIC_ALLOWED)
    has_disclosure_signal = any(signal in lowered for signal in DISCLOSURE_SIGNALS)

    risk = determine_ads_policy_risk(
        category=category,
        findings=findings,
        has_disclosure_signal=has_disclosure_signal,
        fetch_error=fetch_error,
    )
    google_precheck = google_ads_precheck(category, risk, findings)
    microsoft_precheck = microsoft_ads_precheck(category, risk, findings)
    ads_status_override = determine_ads_status_override(category, risk)

    return {
        "auto_verification_status": determine_auto_verification_status(risk, findings, has_allowed_signal),
        "ads_policy_risk": risk,
        "ads_policy_findings": " | ".join(findings),
        "paid_traffic_allowed_signal": has_allowed_signal,
        "disclosure_signal_found": has_disclosure_signal,
        "google_ads_precheck": google_precheck,
        "microsoft_ads_precheck": microsoft_precheck,
        "safe_ads_recommendation": build_safe_ads_recommendation(category, risk, findings),
        "ads_status": ads_status_override or project.get("ads_status", ""),
        "ads_verification_source": affiliate_url,
        "ads_verification_error": fetch_error,
    }


def fetch_text(url: str, headers: dict[str, str], timeout: int) -> tuple[str, str]:
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:
        return "", str(exc)

    soup = BeautifulSoup(response.text, "lxml")
    return " ".join(soup.stripped_strings), ""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def detect_findings(text: str) -> list[str]:
    findings = []
    for label, phrases in PAID_TRAFFIC_BLOCKERS.items():
        if any(phrase in text for phrase in phrases):
            findings.append(label)
    return findings


def determine_ads_policy_risk(
    category: str,
    findings: list[str],
    has_disclosure_signal: bool,
    fetch_error: str,
) -> str:
    if findings:
        return "high"
    if category in HIGH_RISK_CATEGORIES:
        return "high"
    if fetch_error:
        return "medium"
    if not has_disclosure_signal:
        return "medium"
    return "low"


def google_ads_precheck(category: str, risk: str, findings: list[str]) -> str:
    if category in {"crypto", "trading"}:
        return "requires_google_certification_and_local_legal_review"
    if findings:
        return "blocked_until_affiliate_terms_allow_paid_search"
    if risk == "medium":
        return "manual_landing_page_review_required"
    return "eligible_for_compliant_landing_page_test"


def microsoft_ads_precheck(category: str, risk: str, findings: list[str]) -> str:
    if category in {"crypto", "trading"}:
        return "requires_microsoft_pre_approval_and_market_eligibility"
    if findings:
        return "blocked_until_affiliate_terms_allow_paid_search"
    if risk == "medium":
        return "manual_landing_page_review_required"
    return "eligible_for_compliant_landing_page_test"


def determine_ads_status_override(category: str, risk: str) -> str:
    if risk == "high":
        return "blocked_by_ads_compliance"
    if category in HIGH_RISK_CATEGORIES:
        return "manual_terms_check_required"
    return ""


def determine_auto_verification_status(
    risk: str,
    findings: list[str],
    has_allowed_signal: bool,
) -> str:
    if findings:
        return "failed_blocking_terms_found"
    if risk == "high":
        return "needs_platform_certification"
    if risk == "medium":
        return "needs_manual_ads_review"
    if has_allowed_signal:
        return "auto_verified_paid_traffic_signal"
    return "auto_verified_low_risk"


def build_safe_ads_recommendation(category: str, risk: str, findings: list[str]) -> str:
    if findings:
        return "Do not run Google/Bing ads until affiliate terms explicitly allow this traffic."
    if category in {"crypto", "trading"}:
        return (
            "Do not run ads until the advertiser/account has required crypto or financial certification, "
            "target market eligibility, legal disclosures, and brand approval."
        )
    if risk == "medium":
        return "Build a compliant landing page and manually verify disclosures, claims, privacy, terms, and traffic rules."
    return "Use a value-added landing page with disclosure, original content, privacy/terms pages, and no misleading claims."
