from __future__ import annotations

import json

try:
    from submit_indexnow import build_payload, is_allowed_url, read_all_sitemap_urls, read_key
except ModuleNotFoundError:
    from scripts.submit_indexnow import build_payload, is_allowed_url, read_all_sitemap_urls, read_key


def main() -> int:
    key = read_key()
    urls = read_all_sitemap_urls()
    invalid = [url for url in urls if not is_allowed_url(url)]
    payload = build_payload(urls, max_urls=100)
    print(f"Key exists: YES ({len(key)} characters)")
    print(f"Sitemap exists and parsed: YES ({len(urls)} eligible URLs)")
    print(f"All sitemap URLs belong to smileaireviewhub.com: {'YES' if not invalid else 'NO'}")
    print("Payload preview only; nothing was sent:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
