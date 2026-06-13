from __future__ import annotations

import argparse
import time
from urllib.error import URLError
from urllib.request import urlopen

from submit_indexnow import BASE_URL, collect_incremental_urls, read_key, submit_indexnow, write_state


def wait_for_deployment(timeout: int, interval: int) -> bool:
    expected = read_key()
    deadline = time.time() + max(0, timeout)
    key_url = f"{BASE_URL}/indexnow-key.txt"
    while time.time() <= deadline:
        try:
            with urlopen(key_url, timeout=20) as response:
                live = response.read().decode("utf-8").strip()
            if live == expected:
                print(f"[post-deploy] Deployment verified at {key_url}")
                return True
            print("[post-deploy] Live key does not match repository key; waiting for deployment.")
        except (URLError, TimeoutError, OSError) as exc:
            print(f"[post-deploy] Site not ready: {exc}")
        time.sleep(max(1, interval))
    print("[post-deploy] Timed out waiting for deployment. IndexNow skipped without failing deployment.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run non-blocking IndexNow notification after Netlify deployment.")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--max-urls", type=int, default=100)
    args = parser.parse_args()
    try:
        if not wait_for_deployment(args.wait_seconds, args.interval_seconds):
            return 0
        urls, state = collect_incremental_urls()
        ok = submit_indexnow(urls, max_urls=args.max_urls)
        if ok and state:
            write_state(state)
        if not ok:
            print("[post-deploy] IndexNow failed, but post-deploy exits successfully by design.")
    except Exception as exc:
        print(f"[post-deploy] Non-blocking IndexNow error: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
