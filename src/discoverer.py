from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

DISCOVERY_SOURCE_FILE = "data/input/discovery_sources.csv"
DISCOVERED_OUTPUT = "data/output/discovered_projects.csv"

BLOCKED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "support.partnerstack.com",
}

AFFILIATE_HINTS = [
    "affiliate",
    "partner",
    "referral",
    "ambassador",
    "commission",
    "cookie",
    "payout",
    "recurring",
    "revenue share",
]

BAD_LABELS = {
    "about",
    "about us",
    "back",
    "categories",
    "compare",
    "docs",
    "documentation",
    "explore",
    "features",
    "home",
    "log in",
    "login",
    "lost your password?",
    "programs",
    "rankings",
    "skip to content",
    "submit",
    "visit official website",
}

BAD_PATHS = {
    "/about",
    "/categories",
    "/compare",
    "/docs",
    "/documentation",
    "/explore",
    "/features",
    "/login",
    "/programs",
    "/rankings",
    "/submit",
}


@dataclass
class DiscoveryCandidate:
    brand_name: str
    website: str
    category: str
    source: str
    notes: str


class Discoverer:
    def __init__(self, timeout: int, user_agent: str, limit: int) -> None:
        self.timeout = timeout
        self.limit = limit
        self.headers = {"User-Agent": user_agent}

    def discover(self) -> pd.DataFrame:
        sources = self.load_sources()
        candidates: list[DiscoveryCandidate] = []
        source_limit = max(5, self.limit // max(len(sources), 1) + 2)

        for _, source in sources.iterrows():
            source_name = str(source.get("source_name", "")).strip()
            source_url = str(source.get("source_url", "")).strip()
            category = str(source.get("category", "")).strip()
            trust_level = str(source.get("trust_level", "")).strip()

            logging.info("Discovering candidates from %s - %s", source_name, source_url)
            source_candidates = self.discover_from_source(
                source_name=source_name,
                source_url=source_url,
                category=category,
                trust_level=trust_level,
                source_limit=source_limit,
            )
            candidates.extend(source_candidates)

        df = self.dedupe(pd.DataFrame([candidate.__dict__ for candidate in candidates]))
        if len(df) > self.limit:
            df = df.head(self.limit)
        df.to_csv(DISCOVERED_OUTPUT, index=False)
        return df

    def load_sources(self) -> pd.DataFrame:
        try:
            return pd.read_csv(DISCOVERY_SOURCE_FILE)
        except FileNotFoundError:
            return pd.DataFrame(columns=["source_name", "source_url", "category", "trust_level", "notes"])

    def discover_from_source(
        self,
        source_name: str,
        source_url: str,
        category: str,
        trust_level: str,
        source_limit: int,
    ) -> list[DiscoveryCandidate]:
        status, html, error = self.fetch(source_url)
        if not html:
            logging.info("Discovery source failed: %s - %s", source_url, error or status)
            return []

        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(" ", strip=True).lower()
        candidates = []

        direct_candidate = self.build_direct_candidate(
            source_name=source_name,
            source_url=source_url,
            category=category,
            trust_level=trust_level,
            page_text=page_text,
        )
        if direct_candidate:
            candidates.append(direct_candidate)

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            label = link.get_text(" ", strip=True)
            if self.is_bad_label(label):
                continue
            url = self.normalize_candidate_url(source_url, href)
            if not self.is_candidate_url(url):
                continue

            context = f"{label} {href}".lower()
            if not self.has_discovery_signal(source_url, context):
                continue

            brand = self.guess_brand_name(label, url)
            if not brand:
                continue

            candidates.append(
                DiscoveryCandidate(
                    brand_name=brand,
                    website=url,
                    category=category,
                    source=f"auto:{source_name}",
                    notes=f"Discovered from trusted source ({trust_level})",
                )
            )

            if len(candidates) >= source_limit:
                break

        return candidates

    def build_direct_candidate(
        self,
        source_name: str,
        source_url: str,
        category: str,
        trust_level: str,
        page_text: str,
    ) -> DiscoveryCandidate | None:
        if not (
            "official affiliate program example" in trust_level.lower()
            or "official" in source_name.lower()
            or source_name.lower().endswith("program")
        ):
            return None
        if not any(hint in page_text for hint in AFFILIATE_HINTS):
            return None

        domain = self.domain(source_url)
        if not domain or domain in BLOCKED_DOMAINS:
            return None

        return DiscoveryCandidate(
            brand_name=self.brand_from_domain(domain),
            website=self.site_root(source_url),
            category=category,
            source=f"auto:{source_name}",
            notes=f"Source page itself contains affiliate signals ({trust_level})",
        )

    def fetch(self, url: str) -> tuple[int | None, str, str]:
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            return response.status_code, response.text, ""
        except Exception as exc:
            return None, "", str(exc)

    def normalize_candidate_url(self, base_url: str, href: str) -> str:
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")

    def is_candidate_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        domain = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower().rstrip("/")

        if path in BAD_PATHS:
            return False

        if domain == "affiliateotter.com":
            return path.startswith("/affiliate-programs/") and path != "/affiliate-programs"

        if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS):
            return False
        if re.search(r"\.(jpg|jpeg|png|gif|svg|webp|pdf|zip)$", parsed.path, re.IGNORECASE):
            return False
        return True

    def has_discovery_signal(self, source_url: str, context: str) -> bool:
        if any(hint in context for hint in AFFILIATE_HINTS):
            return True
        domain = self.domain(source_url)
        path = urlparse(source_url).path.lower()
        known_directory = (
            domain in {
                "affiliateotter.com",
                "commissiondex.com",
                "openaffiliate.dev",
                "affiliatenetwork.me",
                "affiliates8.com",
            }
            or "affiliate-programs" in path
            or "crypto-affiliate-programs" in path
        )
        return known_directory

    def guess_brand_name(self, label: str, url: str) -> str:
        affiliateotter_brand = self.affiliateotter_brand(url)
        if affiliateotter_brand:
            return affiliateotter_brand

        label = re.sub(r"\s+", " ", label).strip()
        if 2 <= len(label) <= 60 and not label.lower().startswith(
            ("learn more", "read more", "click here", "back to")
        ):
            return label

        domain = self.domain(url)
        return self.brand_from_domain(domain)

    def is_bad_label(self, label: str) -> bool:
        normalized = re.sub(r"\s+", " ", label).strip().lower()
        if normalized in BAD_LABELS:
            return True
        return normalized.startswith(("back to", "sign in", "log in", "read more", "learn more"))

    def domain(self, url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def site_root(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def brand_from_domain(self, domain: str) -> str:
        if not domain:
            return ""
        name = domain.split(".")[0]
        return re.sub(r"[-_]+", " ", name).title()

    def affiliateotter_brand(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        if domain != "affiliateotter.com":
            return ""

        match = re.search(r"/affiliate-programs/([^/?#]+)", parsed.path)
        if not match:
            return ""
        slug = match.group(1)
        return re.sub(r"[-_]+", " ", slug).title()

    def dedupe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["brand_name", "website", "category", "source", "notes"])
        df = df.dropna(subset=["website"])
        df["website_key"] = df["website"].str.lower().str.replace(r"/$", "", regex=True)
        df = df.drop_duplicates(subset=["website_key"])
        return df.drop(columns=["website_key"])
