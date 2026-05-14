from __future__ import annotations

import re


def parse_commission_text(text: str) -> str:
    patterns = [
        r"(?<!\w)(?:up to\s*)?\d{1,3}(?:\.\d+)?\s?%(?!\w)",
        r"(?<!\w)(?:\$|usd\s*)\d{1,5}(?:\.\d{1,2})?\s?(?:per sale|per referral|commission|cpa)?\b",
        r"(?<!\w)\d{1,3}(?:\.\d+)?\s?%\s?(?:rev share|revenue share)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group(0).strip()
            if is_positive_commission(value):
                return value
    return ""


def parse_commission_percent(text: str) -> float:
    match = re.search(r"(?<!\w)(?:up to\s*)?(\d{1,3}(?:\.\d+)?)\s?%(?!\w)", text, re.IGNORECASE)
    if not match:
        return 0.0
    return float(match.group(1))


def parse_flat_commission_amount(text: str) -> float:
    match = re.search(
        r"(?<!\w)(?:\$|usd\s*)(\d{1,5}(?:\.\d{1,2})?)\s?(?:per sale|per referral|commission|cpa)?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return 0.0
    return float(match.group(1))


def parse_cookie_text(text: str) -> str:
    patterns = [
        r"\blifetime\s?(?:cookie|tracking|referral)?\b",
        r"\b\d{1,3}\s?(?:day|days|month|months|year|years)\b",
    ]
    return first_match(text, patterns)


def parse_cookie_days(text: str) -> int:
    lowered = text.lower()
    if re.search(r"\blifetime\s?(cookie|tracking|referral)?\b", lowered):
        return 9999

    match = re.search(r"\b(\d{1,3})\s?(day|days|month|months|year|years)\b", lowered)
    if not match:
        return 0

    value = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("month"):
        return value * 30
    if unit.startswith("year"):
        return value * 365
    return value


def is_recurring(text: str) -> bool:
    lowered = text.lower()
    keywords = [
        "recurring",
        "monthly commission",
        "subscription commission",
        "lifetime commissions",
        "lifetime commission",
        "rev share",
        "revenue share",
        "for the lifetime of",
    ]
    return any(keyword in lowered for keyword in keywords)


def parse_payout_text(text: str) -> str:
    lowered = text.lower()
    methods = ["paypal", "wire", "bank", "stripe", "crypto", "wise", "payoneer"]
    schedules = re.findall(r"\bnet\s?\d{1,3}\b", lowered, flags=re.IGNORECASE)
    minimums = re.findall(r"\b(?:minimum payout|payout threshold)\s?(?:is|of)?\s?(?:\$|usd\s*)?\d{1,5}\b", lowered)

    found = [method for method in methods if method in lowered]
    found.extend(sorted(set(schedules)))
    found.extend(sorted(set(minimums)))
    return ", ".join(found)


def normalize_commission_type(recurring: bool, commission_text: str) -> str:
    lowered = commission_text.lower()
    if recurring:
        return "recurring"
    if "$" in commission_text or "usd" in lowered or "cpa" in lowered:
        return "flat"
    if "%" in commission_text:
        return "percentage"
    return "unknown"


def first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""


def is_positive_commission(value: str) -> bool:
    percent_match = re.search(r"(\d{1,3}(?:\.\d+)?)\s?%", value)
    if percent_match and float(percent_match.group(1)) <= 0:
        return False

    amount_match = re.search(r"(?:\$|usd\s*)(\d{1,5}(?:\.\d{1,2})?)", value, re.IGNORECASE)
    if amount_match and float(amount_match.group(1)) <= 0:
        return False

    return True
