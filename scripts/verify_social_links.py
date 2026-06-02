from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "siteStats.json"
BAD_TOKENS = ["unavailable", "example.com", "paste_real", "localhost"]
REQUIRED_CHANNELS = ["Facebook", "LinkedIn", "X", "Quora", "DEV", "Reddit", "Qiita", "Hashnode", "Velog"]


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main() -> None:
    if not CONFIG.exists():
        raise SystemExit(f"Missing config file: {CONFIG}")
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    channels = data.get("communityChannels") or []
    by_name = {str(item.get("name", "")).strip(): item for item in channels if isinstance(item, dict)}
    errors: list[str] = []
    warnings: list[str] = []

    print("Community channel link report")
    for name in REQUIRED_CHANNELS:
        item = by_name.get(name)
        if not item:
            warnings.append(f"{name}: missing config entry")
            print(f"- {name}: missing config entry")
            continue
        url = str(item.get("url") or "").strip()
        label = str(item.get("label") or "").strip()
        if not url:
            print(f"- {name}: Coming soon ({label})")
            continue
        lowered = url.lower()
        bad = [token for token in BAD_TOKENS if token in lowered]
        if bad:
            errors.append(f"{name}: active URL contains placeholder/bad token {bad}: {url}")
            print(f"- {name}: ERROR placeholder/bad URL: {url}")
            continue
        if not is_valid_url(url):
            errors.append(f"{name}: active URL is not a valid http(s) URL: {url}")
            print(f"- {name}: ERROR invalid URL: {url}")
            continue
        print(f"- {name}: active {url}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("\nSocial link verification failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("\nSocial link verification passed. Missing URLs are rendered as Coming soon, not active links.")


if __name__ == "__main__":
    main()
