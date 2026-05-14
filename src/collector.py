from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

AFFILIATE_PATHS = [
    "/affiliate",
    "/affiliates",
    "/partners",
    "/partner",
    "/referral",
    "/referrals",
]

KEYWORDS = ["affiliate", "partner", "referral", "ambassador"]


class Collector:
    def __init__(self, timeout: int, user_agent: str) -> None:
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def fetch(self, url: str) -> tuple[int | None, str, str]:
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            return response.status_code, response.text, ""
        except Exception as exc:
            return None, "", str(exc)

    def extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        return " ".join(soup.stripped_strings)

    def find_title_and_description(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else ""
        desc_tag = soup.find("meta", attrs={"name": "description"})
        desc = desc_tag.get("content", "").strip() if desc_tag else ""
        return title, desc

    def find_affiliate_page(self, website: str, homepage_html: str) -> tuple[str, str]:
        for path in AFFILIATE_PATHS:
            candidate = urljoin(website, path)
            status, html, _ = self.fetch(candidate)
            if status and status < 400 and html:
                return candidate, self.extract_text(html)

        soup = BeautifulSoup(homepage_html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True).lower()
            href_lower = href.lower()
            if any(keyword in href_lower or keyword in text for keyword in KEYWORDS):
                candidate = urljoin(website, href)
                status, html, _ = self.fetch(candidate)
                if status and status < 400 and html:
                    return candidate, self.extract_text(html)

        return "", ""

    def has_link_or_text(self, homepage_html: str, keywords: list[str]) -> bool:
        text = self.extract_text(homepage_html).lower()
        if any(keyword in text for keyword in keywords):
            return True

        soup = BeautifulSoup(homepage_html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            label = a.get_text(" ", strip=True).lower()
            if any(keyword in href or keyword in label for keyword in keywords):
                return True
        return False

    def normalize_url(self, website: str) -> str:
        website = str(website).strip()
        if not website:
            return ""
        parsed = urlparse(website)
        if parsed.scheme:
            return website
        return f"https://{website}"

    def collect_project(self, website: str) -> dict:
        website = self.normalize_url(website)
        if not website:
            return self.error_record("missing website")

        status, homepage_html, err = self.fetch(website)
        if not homepage_html:
            return self.error_record(err or f"HTTP {status}")

        title, description = self.find_title_and_description(homepage_html)

        if self.is_direct_affiliate_program_page(website, homepage_html):
            return {
                "homepage_title": title,
                "homepage_description": description,
                "affiliate_url": website,
                "affiliate_found": True,
                "affiliate_text": self.extract_text(homepage_html),
                "legal_pages_found": self.has_link_or_text(
                    homepage_html,
                    ["privacy", "terms", "legal", "security"],
                ),
                "linkedin_found": self.has_link_or_text(homepage_html, ["linkedin.com"]),
                "blog_found": self.has_link_or_text(homepage_html, ["blog", "articles", "resources"]),
                "changelog_found": self.has_link_or_text(
                    homepage_html,
                    ["changelog", "release notes", "updates"],
                ),
                "status": "ok" if status and status < 400 else "warning",
                "error": "" if status and status < 400 else f"HTTP {status}",
            }

        affiliate_url, affiliate_text = self.find_affiliate_page(website, homepage_html)

        return {
            "homepage_title": title,
            "homepage_description": description,
            "affiliate_url": affiliate_url,
            "affiliate_found": bool(affiliate_url),
            "affiliate_text": affiliate_text,
            "legal_pages_found": self.has_link_or_text(
                homepage_html,
                ["privacy", "terms", "legal", "security"],
            ),
            "linkedin_found": self.has_link_or_text(homepage_html, ["linkedin.com"]),
            "blog_found": self.has_link_or_text(homepage_html, ["blog", "articles", "resources"]),
            "changelog_found": self.has_link_or_text(
                homepage_html,
                ["changelog", "release notes", "updates"],
            ),
            "status": "ok" if status and status < 400 else "warning",
            "error": "" if status and status < 400 else f"HTTP {status}",
        }

    def is_direct_affiliate_program_page(self, website: str, html: str) -> bool:
        parsed = urlparse(website)
        domain = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        if domain == "affiliateotter.com" and path.startswith("/affiliate-programs/"):
            return True
        if any(keyword in path for keyword in ["affiliate", "affiliates", "partner", "referral"]):
            return True

        text = self.extract_text(html).lower()
        title, _ = self.find_title_and_description(html)
        title = title.lower()
        return "affiliate program" in title or "affiliate program" in text[:3000]

    def error_record(self, error: str) -> dict:
        return {
            "homepage_title": "",
            "homepage_description": "",
            "affiliate_url": "",
            "affiliate_found": False,
            "affiliate_text": "",
            "legal_pages_found": False,
            "linkedin_found": False,
            "blog_found": False,
            "changelog_found": False,
            "status": "error",
            "error": error,
        }
