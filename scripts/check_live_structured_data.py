from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


JSON_LD_RE = re.compile(
    r"<script\s+type=['\"]application/ld\+json['\"]\s*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def flatten_json_ld(value) -> list[dict]:
    payloads: list[dict] = []
    if isinstance(value, dict):
        payloads.append(value)
        for child in value.values():
            if isinstance(child, (dict, list)):
                payloads.extend(flatten_json_ld(child))
    elif isinstance(value, list):
        for child in value:
            payloads.extend(flatten_json_ld(child))
    return payloads


def fetch_html(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": "MS-Smile-Structured-Data-Check/1.0"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_payloads(html: str) -> tuple[list[dict], int]:
    payloads: list[dict] = []
    parse_errors = 0
    for match in JSON_LD_RE.finditer(html):
        try:
            payloads.extend(flatten_json_ld(json.loads(match.group(1))))
        except json.JSONDecodeError:
            parse_errors += 1
    return payloads, parse_errors


def validate_faq_schema(schema: dict) -> list[str]:
    errors: list[str] = []
    entities = schema.get("mainEntity")
    if not isinstance(entities, list) or not entities:
        return ["FAQPage mainEntity is missing or empty"]
    for index, item in enumerate(entities, start=1):
        if not isinstance(item, dict):
            errors.append(f"FAQ item {index} is not an object")
            continue
        if item.get("@type") != "Question":
            errors.append(f"FAQ item {index} missing @type Question")
        if not str(item.get("name", "")).strip():
            errors.append(f"FAQ item {index} missing name")
        answer = item.get("acceptedAnswer")
        if not isinstance(answer, dict):
            errors.append(f"FAQ item {index} missing acceptedAnswer")
            continue
        if answer.get("@type") != "Answer":
            errors.append(f"FAQ item {index} acceptedAnswer missing @type Answer")
        if not str(answer.get("text", "")).strip():
            errors.append(f"FAQ item {index} acceptedAnswer.text is empty")
    return errors


def check_url(url: str) -> int:
    try:
        html = fetch_html(url)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"FETCH_ERROR {url}: {exc}")
        return 2

    payloads, parse_errors = extract_payloads(html)
    faq_schemas = [payload for payload in payloads if payload.get("@type") == "FAQPage"]
    errors: list[str] = []
    if len(faq_schemas) > 1:
        errors.append(f"duplicate FAQPage blocks: {len(faq_schemas)}")
    for schema_index, schema in enumerate(faq_schemas, start=1):
        for error in validate_faq_schema(schema):
            errors.append(f"FAQPage {schema_index}: {error}")

    print(f"URL: {url}")
    print(f"JSON-LD parse errors: {parse_errors}")
    print(f"FAQPage count: {len(faq_schemas)}")
    for schema_index, schema in enumerate(faq_schemas, start=1):
        entities = schema.get("mainEntity") if isinstance(schema.get("mainEntity"), list) else []
        print(f"FAQPage {schema_index} items: {len(entities)}")
        for item_index, item in enumerate(entities, start=1):
            name = str(item.get("name", "")).strip() if isinstance(item, dict) else ""
            answer = item.get("acceptedAnswer", {}) if isinstance(item, dict) else {}
            answer_text = str(answer.get("text", "")).strip() if isinstance(answer, dict) else ""
            print(f"  {item_index}. name={bool(name)} answer_text={bool(answer_text)} question={name[:90]}")

    if errors or parse_errors:
        print("STATUS: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("STATUS: PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Check live JSON-LD structured data for a public URL.")
    parser.add_argument("urls", nargs="+", help="Live URLs to check")
    args = parser.parse_args()
    status = 0
    for url in args.urls:
        status = max(status, check_url(url))
    sys.exit(status)


if __name__ == "__main__":
    main()
