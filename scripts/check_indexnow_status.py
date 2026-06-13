from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from submit_indexnow import BASE_URL, KEY_FILE, SITEMAP, read_key, read_sitemap_urls
except ModuleNotFoundError:
    from scripts.submit_indexnow import BASE_URL, KEY_FILE, SITEMAP, read_key, read_sitemap_urls


ROOT = Path(__file__).resolve().parents[1]
ROBOTS = ROOT / "site_output" / "robots.txt"


def live_status(url: str) -> tuple[str, str]:
    try:
        request = Request(url, headers={"User-Agent": "SmileAIReviewHub-IndexNow/1.0"})
        with urlopen(request, timeout=20) as response:
            return str(response.status), response.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        return str(exc.code), ""
    except (URLError, TimeoutError, OSError) as exc:
        return "ERROR", str(exc)


def main() -> int:
    errors = 0
    print(f"Local key: {'OK' if KEY_FILE.exists() else 'MISSING'} - {KEY_FILE}")
    print(f"Local sitemap: {'OK' if SITEMAP.exists() else 'MISSING'} - {SITEMAP}")
    print(f"Local robots: {'OK' if ROBOTS.exists() else 'MISSING'} - {ROBOTS}")
    if not KEY_FILE.exists() or not SITEMAP.exists() or not ROBOTS.exists():
        errors += 1
    try:
        key = read_key()
        urls = read_sitemap_urls()
        print(f"Eligible sitemap URLs: {len(urls)}")
        robots_text = ROBOTS.read_text(encoding="utf-8", errors="ignore")
        sitemap_reference = f"Sitemap: {BASE_URL}/sitemap.xml"
        print(f"Robots references sitemap: {'YES' if sitemap_reference in robots_text else 'NO'}")
        if sitemap_reference not in robots_text:
            errors += 1
        bing_blocked = robots_blocks_bingbot(robots_text)
        print(f"Robots blocks Bingbot: {'YES' if bing_blocked else 'NO'}")
        if bing_blocked:
            errors += 1
    except Exception as exc:
        print(f"Local validation error: {exc}")
        return 1

    for name, url in (
        ("key", f"{BASE_URL}/indexnow-key.txt"),
        ("sitemap", f"{BASE_URL}/sitemap.xml"),
        ("robots", f"{BASE_URL}/robots.txt"),
    ):
        status, body = live_status(url)
        print(f"Live {name}: HTTP {status} - {url}")
        if status != "200":
            errors += 1
        if name == "key" and status == "200" and body.strip() != key:
            print("Live key mismatch.")
            errors += 1
    return 1 if errors else 0


def robots_blocks_bingbot(text: str) -> bool:
    active_agents: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            active_agents = []
            continue
        name, _, value = line.partition(":")
        directive = name.strip().lower()
        value = value.strip()
        if directive == "user-agent":
            active_agents.append(value.lower())
        elif directive == "disallow" and value == "/" and any(agent in {"*", "bingbot"} for agent in active_agents):
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
