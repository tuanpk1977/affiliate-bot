from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urlsplit


FUTURE_PROMISE_RE = re.compile(
    r"\b(?:tomorrow|check back tomorrow|more tomorrow|come back tomorrow|"
    r"stay tuned(?: for tomorrow)?|i['\u2019]?ll (?:post|share)|ng\u00e0y mai|h\u00e3y quay l\u1ea1i)\b",
    re.I,
)
STALE_RELATIVE_DATE_RE = re.compile(
    r"\b(?:today|yesterday|tomorrow|this (?:morning|afternoon|evening|week)|"
    r"hôm nay|hôm qua|ngày mai|tuần này)\b",
    re.I,
)
FAKE_URGENCY_RE = re.compile(
    r"\b(?:act now|don['\u2019]?t miss(?: out)?|breaking|this changes everything|"
    r"game[ -]?changer|today is the day|limited time|hành động ngay|đừng bỏ lỡ)\b",
    re.I,
)
GENERIC_CTA_RE = re.compile(
    r"^(?:use|check(?: out)?|learn more|try|start|read|visit|don['\u2019]?t miss|"
    r"follow|click|open|save|xem|đọc|truy cập|theo dõi|hãy (?:đọc|xem|thử|truy cập))\b",
    re.I,
)
CLICKBAIT_TITLE_RE = re.compile(
    r"\b(?:you won['\u2019]?t believe|shocking|secret|must see|game[ -]?changer|"
    r"changes everything|breaking|đừng bỏ lỡ|gây sốc|bí mật)\b",
    re.I,
)
ABSTRACT_TITLE_RE = re.compile(
    r"\b(?:missing artifact|hidden layer|quiet shift|bigger story|what nobody tells you)\b",
    re.I,
)
UNSUPPORTED_PROMOTION_RE = re.compile(
    r"\b(?:best(?: in class)?|must[- ]have|revolutionary|guaranteed|buy now|"
    r"industry[- ]leading|no[- ]brainer|tốt nhất|mang tính cách mạng)\b",
    re.I,
)
AFFILIATE_CLAIM_RE = re.compile(
    r"\b(?:affiliate (?:link|program|commission)|earn (?:a )?commission|"
    r"hoa hồng|liên kết tiếp thị)\b",
    re.I,
)
PRICE_ASSERTION_RE = re.compile(
    r"(?:[$€£]\s?\d|\b(?:costs?|priced at|starts at|free plan|per month|monthly price|"
    r"giá từ|mỗi tháng)\b)",
    re.I,
)
SPECULATION_RE = re.compile(
    r"\b(?:probably|likely means|must mean|guarantees?|will definitely|ch\u1eafc ch\u1eafn s\u1ebd)\b",
    re.I,
)
GENERIC_SOURCE_RE = re.compile(
    r"\b(?:check|verify|read|consult|see)\s+(?:the\s+)?(?:official\s+)?(?:source|changelog|documentation)\b|"
    r"\b(?:don['\u2019]?t|do not)\s+(?:assume|rely)\b|"
    r"\b(?:ki\u1ec3m tra|x\u00e1c minh|\u0111\u1ecdc)\s+(?:ngu\u1ed3n|changelog|t\u00e0i li\u1ec7u)\b",
    re.I,
)
WHY_RE = re.compile(
    r"\b(?:why (?:it|this) matters|matters (?:to|for)|this means|so (?:teams|developers|users)|"
    r"impact|relevant|useful for|workflow|v\u00ec sao|\u0111i\u1ec1u n\u00e0y (?:quan tr\u1ecdng|c\u00f3 ngh\u0129a)|t\u00e1c \u0111\u1ed9ng)\b",
    re.I,
)
TAKEAWAY_RE = re.compile(
    r"\b(?:takeaway|what to (?:check|do|verify)|before (?:adopting|relying|using)|"
    r"review|compare|test|confirm|save this|consider|watch for|ki\u1ec3m tra|x\u00e1c minh|"
    r"th\u1eed nghi\u1ec7m|c\u00e2n nh\u1eafc|l\u01b0u (?:b\u00e0i|l\u1ea1i))\b",
    re.I,
)
HAPPENED_RE = re.compile(
    r"\b(?:announc(?:e|ed|ement)|publish(?:ed)?|release(?:d)?|launch(?:ed)?|update(?:d)?|"
    r"introduc(?:e|ed)|changelog|rollout|ph\u00e1t h\u00e0nh|c\u00f4ng b\u1ed1|c\u1eadp nh\u1eadt|ra m\u1eaft)\b",
    re.I,
)

SOCIAL_PLATFORM_WRITING_GUIDANCE: dict[str, str] = {
    "linkedin": "Professional context and an operational implication; no engagement bait.",
    "facebook_en": "Conversational, clear, and easy to scan; explain why the story matters.",
    "facebook_vi": "Natural Vietnamese with full diacritics; conversational and easy to scan.",
    "x": "One concise factual core plus one useful implication; complete within 280 characters.",
    "pinterest": "Search-friendly standalone title and description; clear visual points without clickbait.",
    "quora": "Answer a real audience question directly; avoid promotional framing.",
    "devto": "Developer-relevant technical or workflow framing only when supported by evidence.",
    "blogger": "A compact explanatory note with context, implication, and primary source.",
    "producthunt": "Product/community framing without endorsement, hype, or invented adoption claims.",
}

_AUDIENCE_RULES = (
    (("enterprise", "admin", "managed settings", "governance"), "enterprise administrators and engineering leaders"),
    (("github", "copilot", "jetbrains", "developer", "code", "api"), "developers and engineering teams"),
    (("marketing", "seo", "campaign", "creator"), "marketers and creators"),
    (("small business", "smb", "accounting", "sales"), "small-business operators"),
    (("product", "launch", "roadmap"), "product teams and early adopters"),
)


def infer_story_audience(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".casefold()
    matches = [label for tokens, label in _AUDIENCE_RULES if any(token in text for token in tokens)]
    # Prefer the most specific matching audience. Joining every matching segment
    # creates mechanical copy such as "developers and ... and administrators".
    return matches[0] if matches else "AI users evaluating the announcement"


def validate_social_title(title: str, *, story_title: str = "", platform: str = "") -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", title or "").strip()
    warnings: list[str] = []
    reasons: list[str] = []
    if not clean:
        reasons.append("TITLE_REQUIRED")
    if CLICKBAIT_TITLE_RE.search(clean):
        reasons.append("CLICKBAIT_TITLE_REWRITE_REQUIRED")
    if ABSTRACT_TITLE_RE.search(clean):
        warnings.append("VAGUE_TITLE_REWRITE_RECOMMENDED: name the entity or concrete change")
    story_tokens = {
        token for token in re.findall(r"[a-z0-9]+", (story_title or "").casefold())
        if len(token) >= 4 and token not in {"with", "from", "that", "this", "settings", "enterprise"}
    }
    title_tokens = set(re.findall(r"[a-z0-9]+", clean.casefold()))
    if story_tokens and not story_tokens.intersection(title_tokens):
        warnings.append("TITLE_GROUNDING_RECOMMENDED: include the entity or announced subject")
    limit = 90 if platform == "pinterest" else 80 if platform in {"x", "facebook_en", "facebook_vi"} else 110
    if len(clean) > limit:
        warnings.append(f"TITLE_TOO_LONG_FOR_{platform.upper() or 'PLATFORM'}: rewrite for clarity")
    return {
        "status": "BLOCKED" if reasons else ("WARNING" if warnings else "PASS"),
        "reasons": reasons,
        "warnings": warnings,
    }


def normalized_cross_platform_copy(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.casefold().startswith(("source:", "nguồn:", "tags:")):
            continue
        if stripped.startswith("#") and " " not in stripped.lstrip("#"):
            continue
        if stripped.startswith(("http://", "https://")):
            continue
        lines.append(stripped)
    return re.sub(r"\W+", " ", " ".join(lines).casefold()).strip()


def cross_platform_similarity(left: str, right: str) -> float:
    a = normalized_cross_platform_copy(left)
    b = normalized_cross_platform_copy(right)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def official_source_name(url: str, provided: str = "") -> str:
    if provided.strip():
        return provided.strip()
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    known = {
        "github.blog": "GitHub Changelog",
        "docs.github.com": "GitHub Docs",
        "openai.com": "OpenAI",
        "developers.google.com": "Google for Developers",
        "learn.microsoft.com": "Microsoft Learn",
    }
    if host in known:
        return known[host]
    if not host:
        return ""
    label = host.split(".")[-2] if "." in host else host
    return label.replace("-", " ").title()


def has_future_promise(text: str) -> bool:
    return bool(FUTURE_PROMISE_RE.search(text or ""))


def evergreen_cta(platform: str) -> str:
    return {
        "linkedin": "Follow for practical, source-backed breakdowns of AI tool updates.",
        "facebook": "Save this post and follow for more source-backed AI tool updates.",
        "facebook_en": "Save this post and follow for more source-backed AI tool updates.",
        "facebook_vi": "L\u01b0u b\u00e0i vi\u1ebft v\u00e0 theo d\u00f5i c\u00e1c b\u1ea3n tin c\u00f4ng c\u1ee5 AI c\u00f3 d\u1eabn ngu\u1ed3n.",
        "x": "Official source below. Follow for concise, source-backed AI updates.",
        "quora": "For current details, use the official source as the canonical reference.",
        "devto": "Use the official changelog as the canonical reference for current behavior.",
        "pinterest": "Save this Pin as a source-first reference for the update.",
        "blogger": "Follow future source-backed updates from Smile AI Review Hub.",
    }.get(platform, "Follow for practical AI tool updates backed by official sources.")


def rewrite_future_promise(text: str, platform: str, *, scheduled_followup_exists: bool) -> str:
    if scheduled_followup_exists or not has_future_promise(text):
        return text
    lines = [line for line in (text or "").splitlines() if not FUTURE_PROMISE_RE.search(line)]
    # Removal is safer than silently replacing a stale promise with a generic CTA.
    # The writer or operator can add a story-specific ending during review.
    return "\n".join(lines).strip()


def _source_visible(text: str, source_name: str, source_url: str, platform: str) -> bool:
    body = text or ""
    named = bool(source_name and source_name.casefold() in body.casefold())
    labelled = bool(re.search(r"\b(?:source|ngu\u1ed3n)\s*:\s*\S+", body, re.I))
    url_required = platform not in {"pinterest"}
    return named and (not url_required or bool(source_url and source_url in body)) and labelled


def validate_social_value(
    text: str,
    *,
    platform: str,
    official_source_name_value: str = "",
    official_source_url: str = "",
    source_render_required: bool = True,
    scheduled_followup_exists: bool = False,
    title: str = "",
    story_title: str = "",
    hashtags: Iterable[str] = (),
    verified_pricing: bool = False,
    affiliate_claims_supported: bool = False,
) -> dict[str, Any]:
    body = (text or "").strip()
    what_happened = bool(HAPPENED_RE.search(body))
    why_matters = bool(WHY_RE.search(body))
    practical = bool(TAKEAWAY_RE.search(body))
    source_present = (
        _source_visible(body, official_source_name_value, official_source_url, platform)
        if source_render_required
        else True
    )
    future = has_future_promise(body) and not scheduled_followup_exists
    speculation = bool(SPECULATION_RE.search(body))
    fake_urgency = bool(FAKE_URGENCY_RE.search(body) or FAKE_URGENCY_RE.search(title or ""))
    stale_relative_date = bool(STALE_RELATIVE_DATE_RE.search(body)) and not scheduled_followup_exists
    public_lines = [line.strip() for line in body.splitlines() if line.strip()]
    last_line = public_lines[-1] if public_lines else ""
    closing_candidate = next(
        (
            line for line in reversed(public_lines)
            if not line.startswith("#")
            and not line.startswith(("http://", "https://"))
            and not line.casefold().startswith(("source:", "nguồn:", "tags:"))
        ),
        "",
    )
    generic_cta = bool(GENERIC_CTA_RE.search(closing_candidate))
    unsupported_promotion = bool(UNSUPPORTED_PROMOTION_RE.search(body))
    unsupported_affiliate = bool(AFFILIATE_CLAIM_RE.search(body)) and not affiliate_claims_supported
    unsupported_pricing = bool(PRICE_ASSERTION_RE.search(body)) and not verified_pricing
    character_overflow = platform == "x" and len(body) > 280
    title_review = validate_social_title(title, story_title=story_title, platform=platform) if title else {
        "status": "PASS",
        "reasons": [],
        "warnings": [],
    }
    tag_list = [str(tag).strip() for tag in hashtags if str(tag).strip()]
    hashtag_limit = {
        "quora": 0,
        "x": 2,
        "linkedin": 3,
        "facebook_en": 3,
        "facebook_vi": 3,
        "devto": 4,
        "pinterest": 5,
        "blogger": 3,
        "producthunt": 2,
    }.get(platform, 3)
    generic_hits = len(GENERIC_SOURCE_RE.findall(body))
    useful_count = sum((what_happened, why_matters, practical))
    generic_only = generic_hits >= 2 and useful_count < 2
    score = 25 * sum((what_happened, why_matters, practical, source_present))
    if generic_only:
        score -= 25
    if future:
        score -= 25
    if speculation:
        score -= 25
    score = max(0, min(100, score))
    reasons: list[str] = []
    if source_render_required and not source_present:
        reasons.append("SOURCE_RENDERING_REQUIRED")
    if future:
        reasons.append("UNSUPPORTED_FUTURE_PROMISE")
    if generic_only:
        reasons.append("GENERIC_COMPLIANCE_ONLY")
    if speculation:
        reasons.append("UNSUPPORTED_SPECULATION")
    if useful_count < 2:
        reasons.append("SOCIAL_VALUE_REWRITE_REQUIRED")
    if fake_urgency:
        reasons.append("FAKE_URGENCY_REWRITE_REQUIRED")
    if stale_relative_date:
        reasons.append("STALE_RELATIVE_DATE_REWRITE_REQUIRED: use an exact date when timing matters")
    if generic_cta:
        reasons.append("GENERIC_CTA_REWRITE_REQUIRED: end with an implication, decision question, observation, or source")
    if unsupported_promotion:
        reasons.append("UNSUPPORTED_PROMOTIONAL_LANGUAGE")
    if unsupported_affiliate:
        reasons.append("UNSUPPORTED_AFFILIATE_CLAIM")
    if unsupported_pricing:
        reasons.append("UNSUPPORTED_PRICING_CLAIM")
    if character_overflow:
        reasons.append(f"X_CHARACTER_LIMIT_EXCEEDED: {len(body)}/280; shorten copy without removing the source")
    reasons.extend(title_review["reasons"])
    warnings = list(title_review["warnings"])
    if len(tag_list) > hashtag_limit:
        warnings.append(
            f"EXCESSIVE_HASHTAGS_FOR_{platform.upper()}: use at most {hashtag_limit}; zero is acceptable"
        )
    status = "BLOCKED" if reasons else ("WARNING" if score < 75 or warnings else "PASS")
    generic_risk = "HIGH" if generic_only else ("MEDIUM" if generic_hits else "LOW")
    return {
        "what_happened_present": what_happened,
        "why_it_matters_present": why_matters,
        "practical_takeaway_present": practical,
        "official_source_present": source_present,
        "unsupported_future_promise": future,
        "generic_compliance_only": generic_only,
        "unsupported_speculation": speculation,
        "fake_urgency": fake_urgency,
        "stale_relative_date": stale_relative_date,
        "generic_cta": generic_cta,
        "unsupported_promotional_language": unsupported_promotion,
        "unsupported_affiliate_claim": unsupported_affiliate,
        "unsupported_pricing_claim": unsupported_pricing,
        "character_overflow": character_overflow,
        "title_validation": title_review,
        "hashtag_count": len(tag_list),
        "hashtag_limit": hashtag_limit,
        "ending_type": (
            "source_reference" if last_line.casefold().startswith(("source:", "nguồn:"))
            or (
                last_line.startswith(("http://", "https://"))
                and len(public_lines) >= 2
                and public_lines[-2].casefold().startswith(("source:", "nguồn:"))
            )
            else "decision_question" if last_line.endswith("?")
            else "generic_cta" if generic_cta
            else "operational_takeaway_or_observation"
        ),
        "generic_content_risk": generic_risk,
        "value_score": score,
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
    }


def validate_pinterest_visual(
    *,
    headline: str,
    subhead: str = "",
    points: Iterable[str] = (),
    source_name: str = "",
    verified_facts: Iterable[str] = (),
    empty_area_ratio: float | None = None,
) -> dict[str, Any]:
    point_list = [str(point).strip() for point in points if str(point).strip()]
    allowed = {re.sub(r"\W+", " ", str(fact).casefold()).strip() for fact in verified_facts if str(fact).strip()}
    unsupported: list[str] = []
    for point in point_list:
        normalized = re.sub(r"\W+", " ", point.casefold()).strip()
        if not allowed or normalized not in allowed:
            unsupported.append(point)
    headline_readable = 12 <= len(headline.strip()) <= 90
    meaningful_density = bool(subhead.strip()) and len(point_list) >= 2
    excessive_empty = (empty_area_ratio is not None and empty_area_ratio > 0.68) or not meaningful_density
    source_present = bool(source_name.strip())
    reasons: list[str] = []
    if not headline_readable:
        reasons.append("PINTEREST_HEADLINE_REWRITE_REQUIRED")
    if excessive_empty:
        reasons.append("PINTEREST_VISUAL_DENSITY_REQUIRED")
    if not source_present:
        reasons.append("PINTEREST_SOURCE_INDICATOR_REQUIRED")
    if unsupported:
        reasons.append("PINTEREST_UNSUPPORTED_VISUAL_CLAIM")
    status = "BLOCKED" if unsupported or not source_present else ("WARNING" if reasons else "PASS")
    return {
        "headline_readable": headline_readable,
        "excessive_empty_area": excessive_empty,
        "meaningful_text_density": meaningful_density,
        "source_indicator_present": source_present,
        "unsupported_claims": unsupported,
        "status": status,
        "reasons": reasons,
    }
