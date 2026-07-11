from __future__ import annotations


def classify_intent(keyword: str) -> dict[str, object]:
    text = keyword.lower()
    rules = [
        ("transactional", ("buy", "coupon", "discount", "deal", "subscribe")),
        ("commercial", ("best", "review", "vs", "alternative", "pricing", "software", "tool")),
        ("navigational", ("login", "website", "app", "dashboard")),
    ]
    for intent, terms in rules:
        matches = [term for term in terms if term in text]
        if matches:
            return {"search_intent": intent, "intent_confidence": min(0.95, 0.6 + 0.1 * len(matches)), "intent_evidence": matches}
    return {"search_intent": "informational", "intent_confidence": 0.6, "intent_evidence": ["default informational pattern"]}
