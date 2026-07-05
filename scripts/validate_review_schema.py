from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


JSON_LD_RE = re.compile(
    r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
    flags=re.I | re.S,
)
VALID_AUTHOR_TYPES = {"Person", "Organization"}


def schema_nodes(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from schema_nodes(child)


def parse_page(path: Path) -> tuple[list[dict], list[str]]:
    payloads: list[dict] = []
    errors: list[str] = []
    source = path.read_text(encoding="utf-8", errors="replace")
    for index, match in enumerate(JSON_LD_RE.finditer(source), start=1):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"JSON-LD block {index} is invalid: {exc}")
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        elif isinstance(payload, list):
            payloads.extend(item for item in payload if isinstance(item, dict))
    return payloads, errors


def number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_review(review: dict) -> list[str]:
    errors: list[str] = []
    author = review.get("author")
    if not isinstance(author, dict):
        errors.append("author must be an object")
    else:
        if author.get("@type") not in VALID_AUTHOR_TYPES:
            errors.append("author @type must be Person or Organization")
        if not str(author.get("name") or "").strip():
            errors.append("author.name is missing")

    item = review.get("itemReviewed")
    if not isinstance(item, dict) or not str(item.get("name") or "").strip():
        errors.append("itemReviewed.name is missing")

    rating = review.get("reviewRating")
    if not isinstance(rating, dict):
        errors.append("reviewRating is missing")
    else:
        rating_value = number(rating.get("ratingValue"))
        best = number(rating.get("bestRating"))
        worst = number(rating.get("worstRating"))
        if rating_value is None:
            errors.append("reviewRating.ratingValue is not numeric")
        if best is not None and worst is not None and best < worst:
            errors.append("reviewRating bestRating is lower than worstRating")
        if rating_value is not None and best is not None and rating_value > best:
            errors.append("reviewRating.ratingValue exceeds bestRating")
        if rating_value is not None and worst is not None and rating_value < worst:
            errors.append("reviewRating.ratingValue is lower than worstRating")

    publisher = review.get("publisher")
    if publisher is not None:
        if not isinstance(publisher, dict) or not str(publisher.get("name") or "").strip():
            errors.append("publisher.name is missing")

    for field in ("url",):
        if field in review and not str(review.get(field) or "").strip():
            errors.append(f"{field} is empty")
    return errors


def validate_output(root: Path) -> tuple[int, int, list[str]]:
    pages = 0
    reviews = 0
    errors: list[str] = []
    for page in sorted(root.rglob("*.html")):
        pages += 1
        payloads, page_errors = parse_page(page)
        errors.extend(f"{page}: {error}" for error in page_errors)
        for payload in payloads:
            for node in schema_nodes(payload):
                if node.get("@type") != "Review":
                    continue
                reviews += 1
                errors.extend(f"{page}: Review: {error}" for error in validate_review(node))
    return pages, reviews, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Review JSON-LD in generated HTML.")
    parser.add_argument("root", nargs="?", default="site_output", help="Generated site directory")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.exists():
        print(f"FAIL: directory not found: {root}")
        return 2

    pages, reviews, errors = validate_output(root)
    print(f"HTML pages checked: {pages}")
    print(f"Review objects checked: {reviews}")
    if errors:
        print(f"Validation errors: {len(errors)}")
        for error in errors[:100]:
            print(f"- {error}")
        if len(errors) > 100:
            print(f"- ... {len(errors) - 100} more")
        print("STATUS: FAIL")
        return 1
    print("Validation errors: 0")
    print("STATUS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
