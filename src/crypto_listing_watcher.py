from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

CRYPTO_LISTING_SOURCE_FILE = "data/input/crypto_listing_sources.csv"
CRYPTO_CREDIBILITY_SIGNAL_FILE = "data/input/crypto_credibility_signals.csv"
CRYPTO_LISTING_OUTPUT = "data/output/crypto_listing_watchlist.csv"
CRYPTO_LISTING_SUMMARY = "data/output/crypto_listing_summary.txt"

POSITIVE_SIGNALS = [
    "spot trading",
    "new listing",
    "gets listed",
    "will list",
    "to list",
    "world premiere listing",
    "launchpool",
    "launchpad",
    "pre-market",
]

GENERIC_TITLES = {
    "new listings",
    "spot trading",
    "our new listings process",
}

NARRATIVE_SIGNALS = {
    "ai": ["ai", "artificial intelligence", "agent"],
    "rwa": ["rwa", "real world asset", "tokenized"],
    "defi": ["defi", "dex", "liquidity"],
    "dep in": ["depin", "infrastructure"],
    "gaming": ["game", "gaming"],
    "meme": ["meme", "cat", "dog", "pepe"],
    "layer2": ["layer 2", "l2", "rollup"],
}

RISK_SIGNALS = [
    "closed",
    "ended",
    "delist",
    "migration",
    "suspension",
    "maintenance",
    "futures",
    "perpetual",
    "margin",
    "convert",
    "payment",
]


class CryptoListingWatcher:
    def __init__(self, timeout: int, user_agent: str, limit: int = 80) -> None:
        self.timeout = timeout
        self.limit = limit
        self.headers = {"User-Agent": user_agent}
        self.credibility_signals = self.load_credibility_signals()

    def run(self) -> pd.DataFrame:
        sources = self.load_sources()
        rows = []
        for _, source in sources.iterrows():
            source_name = str(source.get("source_name", "")).strip()
            source_url = str(source.get("source_url", "")).strip()
            exchange_tier = str(source.get("exchange_tier", "")).strip()
            logging.info("Checking crypto listing source: %s", source_url)
            rows.extend(self.fetch_source(source_name, source_url, exchange_tier))

        df = pd.DataFrame(rows)
        if df.empty:
            df = self.empty_df()
        else:
            df = df.drop_duplicates(subset=["title", "source_name"])
            df = self.filter_low_quality_rows(df)
            df = df.sort_values(["priority_score", "listing_score", "exchange_score"], ascending=[False, False, False]).head(self.limit)

        df.to_csv(CRYPTO_LISTING_OUTPUT, index=False)
        self.write_summary(df)
        return df

    def load_sources(self) -> pd.DataFrame:
        try:
            return pd.read_csv(CRYPTO_LISTING_SOURCE_FILE)
        except FileNotFoundError:
            return pd.DataFrame(columns=["source_name", "source_url", "exchange_tier", "notes"])

    def load_credibility_signals(self) -> pd.DataFrame:
        try:
            return pd.read_csv(CRYPTO_CREDIBILITY_SIGNAL_FILE)
        except FileNotFoundError:
            return pd.DataFrame(columns=["signal_type", "name", "score", "notes"])

    def fetch_source(self, source_name: str, source_url: str, exchange_tier: str) -> list[dict]:
        try:
            response = requests.get(source_url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:
            logging.info("Crypto listing source failed: %s - %s", source_url, exc)
            return []

        soup = BeautifulSoup(response.text, "lxml")
        candidates = []
        seen_titles = set()

        for item in soup.find_all(["a", "article", "li", "h2", "h3"]):
            title = item.get_text(" ", strip=True)
            title = normalize_space(title)
            if not self.is_listing_candidate(title, source_name):
                continue
            if title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())

            href = item.get("href", "") if item.name == "a" else ""
            url = urljoin(source_url, href) if href else source_url
            candidates.append(self.build_row(source_name, source_url, url, exchange_tier, title))

            if len(candidates) >= self.limit:
                break

        for row in soup.find_all("tr"):
            title = normalize_space(row.get_text(" ", strip=True))
            if not self.is_listing_candidate(title, source_name):
                continue
            if title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            link = row.find("a", href=True)
            url = urljoin(source_url, link["href"]) if link else source_url
            candidates.append(self.build_row(source_name, source_url, url, exchange_tier, title))
            if len(candidates) >= self.limit:
                break

        candidates.extend(self.extract_structured_text_candidates(source_name, source_url, exchange_tier, soup))

        return candidates

    def extract_structured_text_candidates(
        self,
        source_name: str,
        source_url: str,
        exchange_tier: str,
        soup: BeautifulSoup,
    ) -> list[dict]:
        text = normalize_space(soup.get_text(" ", strip=True))
        rows = []

        if "coinmarketcap upcoming" in source_name.lower():
            pattern = r"(\d+)\s+([A-Za-z0-9 .()_-]+?)\s+([A-Z0-9]{2,12})\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}(?:,\s+\d{2}:\d{2}:\d{2})?|\d{4})"
            for match in re.finditer(pattern, text):
                title = f"CoinMarketCap upcoming: {match.group(2).strip()} ({match.group(3)}) first listing date {match.group(4)}"
                rows.append(self.build_row(source_name, source_url, source_url, exchange_tier, title))

        if "coinmarketcap new" in source_name.lower():
            pattern = r"\|\s*(\d+)\s+([A-Za-z0-9 .()_-]+?)\s+\2?\s*([A-Z0-9]{2,12})\s+\|"
            for match in re.finditer(pattern, text):
                title = f"CoinMarketCap recently added: {match.group(2).strip()} ({match.group(3)})"
                rows.append(self.build_row(source_name, source_url, source_url, exchange_tier, title))

        if "coinlist" in source_name.lower():
            for match in re.finditer(r"([A-Za-z0-9 ._-]+?)\s+Token Sale", text):
                project = normalize_space(match.group(1))
                project_lower = project.lower()
                if (
                    len(project) < 2
                    or project_lower in {"token sales", "join the next big", "coinlist"}
                    or "resources" in project_lower
                    or "get tokens before" in project_lower
                    or "login" in project_lower
                ):
                    continue
                title = f"CoinList token sale: {project}"
                rows.append(self.build_row(source_name, source_url, source_url, exchange_tier, title))

        return rows[: self.limit]

    def is_listing_candidate(self, title: str, source_name: str) -> bool:
        lowered = title.lower()
        if len(title) < 12:
            return False
        if lowered in GENERIC_TITLES:
            return False
        if "our new listings process" in lowered:
            return False
        if any(signal in lowered for signal in ["delisting", "delist", "maintenance", "migration completed"]):
            return False
        if self.is_research_source_title(title, source_name):
            return True
        if not any(signal in lowered for signal in POSITIVE_SIGNALS):
            return False
        published_at = parse_date(title)
        if not published_at:
            return (
                "coinlist" in lowered
                or "token sale" in lowered
                or "coinmarketcap upcoming" in lowered
                or "coinmarketcap recently added" in lowered
            )
        return published_at >= datetime.now() - timedelta(days=60)

    def build_row(
        self,
        source_name: str,
        source_url: str,
        article_url: str,
        exchange_tier: str,
        title: str,
    ) -> dict:
        token_name, token_symbol = extract_token(title)
        published_at = parse_date(title)
        exchange_score = exchange_tier_score(exchange_tier)
        listing_stage = detect_listing_stage(source_name, title)
        expected_exchange = expected_exchange_label(source_name, listing_stage)
        credibility = self.evaluate_credibility(title=title, article_url=article_url)
        signal_score = listing_signal_score(title)
        narrative = detect_narrative(title)
        narrative_score = 10 if narrative else 0
        risk_flags = detect_risk_flags(title)
        risk_penalty = risk_penalty_score(risk_flags)
        data_score = data_quality_score(token_name, token_symbol, published_at, expected_exchange)
        stage_score = listing_stage_score(listing_stage)
        listing_score = max(
            0,
            min(
                100,
                exchange_score
                + signal_score
                + narrative_score
                + data_score
                + credibility["credibility_score"]
                - risk_penalty,
            ),
        )
        priority_score = max(0, min(100, listing_score + stage_score - risk_penalty))

        return {
            "source_name": source_name,
            "source_url": source_url,
            "article_url": article_url,
            "exchange_tier": exchange_tier,
            "title": title,
            "token_name": token_name,
            "token_symbol": token_symbol,
            "expected_exchange": expected_exchange,
            "listing_stage": listing_stage,
            "narrative": narrative,
            "risk_flags": " | ".join(risk_flags),
            "exchange_score": exchange_score,
            "signal_score": signal_score,
            "narrative_score": narrative_score,
            "data_score": data_score,
            **credibility,
            "stage_score": stage_score,
            "risk_penalty": risk_penalty,
            "listing_score": listing_score,
            "priority_score": priority_score,
            "research_priority": priority_label(priority_score),
            "research_action": research_action(priority_score, listing_stage, risk_flags),
            "bot_note": bot_note(priority_score, risk_flags),
            "published_at": published_at.strftime("%Y-%m-%d") if published_at else "",
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def is_research_source_title(self, title: str, source_name: str) -> bool:
        source = source_name.lower()
        if not any(name in source for name in ["coinmarketcap", "coinlist"]):
            return False
        lowered = title.lower()
        if any(generic in lowered for generic in ["privacy policy", "terms", "log in", "sign up"]):
            return False
        if "coinlist" in source and any(bad in lowered for bad in ["resources", "login", "get tokens before they list anywhere else"]):
            return False
        if "token sale" in lowered:
            return True
        if re.search(r"\b(upcoming|recently added|first listing date)\b", lowered):
            return True
        if parse_date(title) and re.search(r"\b[A-Z0-9]{2,12}\b", title):
            return True
        return False

    def evaluate_credibility(self, title: str, article_url: str) -> dict:
        text = title
        if article_url:
            text += " " + self.fetch_article_text(article_url)
        lowered = normalize_space(text).lower()

        signals = []
        risks = []
        score = 0
        for _, row in self.credibility_signals.iterrows():
            name = str(row.get("name", "")).strip()
            signal_type = str(row.get("signal_type", "")).strip()
            signal_score = int(row.get("score", 0) or 0)
            if not name or name.lower() not in lowered:
                continue
            if signal_score < 0 or signal_type == "risk_signal":
                risks.append(name)
            else:
                signals.append(name)
            score += signal_score

        score = max(-30, min(35, score))
        return {
            "credibility_score": score,
            "credibility_signals": " | ".join(dict.fromkeys(signals)),
            "credibility_risks": " | ".join(dict.fromkeys(risks)),
            "team_backer_note": team_backer_note(score, signals, risks),
        }

    def fetch_article_text(self, url: str) -> str:
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
        except Exception:
            return ""
        soup = BeautifulSoup(response.text, "lxml")
        return " ".join(soup.stripped_strings)[:20000]

    def empty_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "source_name",
                "source_url",
                "article_url",
                "exchange_tier",
                "title",
                "token_name",
                "token_symbol",
                "expected_exchange",
                "listing_stage",
                "narrative",
                "risk_flags",
                "exchange_score",
                "signal_score",
                "narrative_score",
                "data_score",
                "credibility_score",
                "credibility_signals",
                "credibility_risks",
                "team_backer_note",
                "stage_score",
                "risk_penalty",
                "listing_score",
                "priority_score",
                "research_priority",
                "research_action",
                "bot_note",
                "published_at",
                "checked_at",
            ]
        )

    def filter_low_quality_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        title = df["title"].astype(str).str.lower()
        token_name = df["token_name"].astype(str)
        token_symbol = df["token_symbol"].astype(str)
        has_token = (token_name.str.strip() != "") | (token_symbol.str.strip() != "")
        generic = title.isin(
            {
                "recently added",
                "upcoming sales",
                "upcoming icos",
                "# name first listing date more information",
            }
        ) | title.str.contains("no upcoming projects", regex=False)
        malformed = token_name.str.contains("--", regex=False) | token_name.str.contains(r"\b\d{4}\b", regex=True)
        return df[(has_token | (df["priority_score"] >= 55)) & ~generic & ~malformed]

    def write_summary(self, df: pd.DataFrame) -> None:
        lines = [
            "TÓM TẮT COIN SẮP/ MỚI LIST SÀN",
            "",
            "Lưu ý: Đây là watchlist nghiên cứu, không phải khuyến nghị mua bán. Coin mới list có biến động rất mạnh và có thể giảm sâu.",
            "",
        ]
        if df.empty:
            lines.append("Chưa tìm thấy thông báo listing phù hợp từ nguồn cấu hình.")
        else:
            for index, (_, row) in enumerate(df.head(15).iterrows(), start=1):
                lines.extend(
                    [
                        f"{index}. {row.get('token_symbol') or row.get('token_name') or 'Chưa rõ token'} | Điểm ưu tiên {row.get('priority_score')} | Ưu tiên: {row.get('research_priority')}",
                        f"   Nguồn: {row.get('source_name')}",
                        f"   Sàn/nguồn dự kiến: {row.get('expected_exchange') or 'chưa rõ'} | Giai đoạn: {row.get('listing_stage') or 'chưa rõ'}",
                        f"   Tiêu đề: {row.get('title')}",
                        f"   Ngày tin: {row.get('published_at') or 'chưa rõ'}",
                        f"   Narrative: {row.get('narrative') or 'chưa rõ'} | Rủi ro: {row.get('risk_flags') or 'chưa thấy trong tiêu đề'}",
                        f"   Team/backer: {row.get('team_backer_note')}",
                        f"   Tín hiệu uy tín: {row.get('credibility_signals') or 'chưa phát hiện'} | Rủi ro uy tín: {row.get('credibility_risks') or 'chưa phát hiện'}",
                        f"   Link: {row.get('article_url')}",
                        f"   Hành động nên làm: {row.get('research_action')}",
                        f"   Ghi chú bot: {row.get('bot_note')}",
                    ]
                )
        with open(CRYPTO_LISTING_SUMMARY, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_token(title: str) -> tuple[str, str]:
    symbol_match = re.search(r"\(([A-Z0-9]{2,12})\)", title)
    symbol = symbol_match.group(1) if symbol_match else ""

    name_patterns = [
        r"CoinMarketCap upcoming:\s+([A-Za-z0-9 ._-]+?)\s+\(",
        r"CoinMarketCap recently added:\s+([A-Za-z0-9 ._-]+?)\s+\(",
        r"CoinList token sale:\s+([A-Za-z0-9 ._-]+)$",
        r"to list\s+([A-Za-z0-9 ._-]+?)(?:\s+\(|\s+for|\s+on|$)",
        r"will launch\s+([A-Z0-9]{2,12})(?:/| for|$)",
        r"gets listed on [A-Za-z]+!\s*([A-Za-z0-9 ._-]+)?",
        r"World Premiere Listing on [A-Za-z]+!\s*([A-Za-z0-9 ._-]+)?",
    ]
    name = ""
    for pattern in name_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            name = normalize_space(match.group(1) or "")
            break

    if not symbol:
        slash_match = re.search(r"\b([A-Z0-9]{2,12})/(?:USDT|USD|BTC|TRY)\b", title)
        symbol = slash_match.group(1) if slash_match else ""
    return name, symbol


def parse_date(title: str) -> datetime | None:
    patterns = [
        (r"Published on\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", ["%d %b %Y", "%d %B %Y"]),
        (r"(\d{1,2}/\d{1,2}/\d{4})", ["%m/%d/%Y", "%d/%m/%Y"]),
        (r"\((\d{4}-\d{2}-\d{2})\)", ["%Y-%m-%d"]),
        (r"first listing date\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", ["%B %d, %Y", "%b %d, %Y"]),
        (r"first listing date\s+([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4},\s+\d{2}:\d{2}:\d{2})", ["%B %d, %Y, %H:%M:%S", "%b %d, %Y, %H:%M:%S"]),
    ]
    for pattern, formats in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def exchange_tier_score(tier: str) -> int:
    if tier == "tier1":
        return 45
    if tier == "tier2":
        return 35
    if tier == "launchpad":
        return 32
    if tier == "research":
        return 22
    return 25


def listing_signal_score(title: str) -> int:
    lowered = title.lower()
    score = 0
    if "spot trading" in lowered:
        score += 25
    if any(signal in lowered for signal in ["will list", "to list", "gets listed", "new listing"]):
        score += 20
    if any(signal in lowered for signal in ["launchpool", "launchpad", "world premiere"]):
        score += 15
    if "pre-market" in lowered:
        score += 8
    return min(score, 40)


def detect_narrative(title: str) -> str:
    lowered = title.lower()
    found = []
    for narrative, keywords in NARRATIVE_SIGNALS.items():
        if any(keyword in lowered for keyword in keywords):
            found.append(narrative)
    return " | ".join(found)


def detect_risk_flags(title: str) -> list[str]:
    lowered = title.lower()
    return [signal for signal in RISK_SIGNALS if signal in lowered]


def risk_penalty_score(risk_flags: list[str]) -> int:
    penalty = 0
    for flag in risk_flags:
        if flag in {"closed", "ended", "delist"}:
            penalty += 25
        elif flag in {"futures", "perpetual", "margin"}:
            penalty += 12
        else:
            penalty += 8
    return penalty


def expected_exchange_label(source_name: str, listing_stage: str) -> str:
    lowered = source_name.lower()
    if "binance" in lowered:
        return "Binance"
    if "okx" in lowered:
        return "OKX"
    if "kucoin" in lowered:
        return "KuCoin"
    if "coinbase" in lowered:
        return "Coinbase"
    if "coinlist" in lowered:
        return "CoinList token sale; sàn CEX sau TGE chưa công bố"
    if "coinmarketcap upcoming" in lowered:
        return "CoinMarketCap Upcoming; sàn list cần kiểm tra trong trang dự án"
    if "coinmarketcap new" in lowered:
        return "CoinMarketCap Recently Added; đã xuất hiện trên CMC, sàn giao dịch cần kiểm tra"
    if "ico" in lowered:
        return "ICO/IDO; sàn sau khi TGE chưa chắc chắn"
    return listing_stage


def detect_listing_stage(source_name: str, title: str) -> str:
    source = source_name.lower()
    lowered = title.lower()
    if "coinlist" in source or "token sale" in lowered:
        return "token_sale_before_exchange_listing"
    if "coinmarketcap upcoming" in source or "first listing date" in lowered:
        return "upcoming_release"
    if "coinmarketcap new" in source or "recently added" in lowered:
        return "recently_added_to_cmc"
    if "spot trading" in lowered:
        return "spot_listing_announced"
    if "futures" in lowered or "perpetual" in lowered:
        return "futures_or_perpetual_only"
    if "pre-market" in lowered:
        return "pre_market"
    return "listing_signal"


def listing_stage_score(stage: str) -> int:
    mapping = {
        "spot_listing_announced": 18,
        "token_sale_before_exchange_listing": 14,
        "upcoming_release": 10,
        "pre_market": 8,
        "recently_added_to_cmc": 6,
        "listing_signal": 4,
        "futures_or_perpetual_only": -18,
    }
    return mapping.get(stage, 0)


def data_quality_score(
    token_name: str,
    token_symbol: str,
    published_at: datetime | None,
    expected_exchange: str,
) -> int:
    score = 0
    if token_name:
        score += 6
    if token_symbol:
        score += 8
    if published_at:
        score += 6
    if expected_exchange:
        score += 5
    return score


def team_backer_note(score: int, signals: list[str], risks: list[str]) -> str:
    if risks:
        return "Có tín hiệu rủi ro về team/backer; cần kiểm tra kỹ trước khi nghiên cứu tiếp."
    if score >= 25:
        return "Có tín hiệu backer/team mạnh; tăng độ ưu tiên nghiên cứu."
    if score >= 10:
        return "Có một số tín hiệu uy tín về team/backer/audit."
    if score > 0:
        return "Có tín hiệu uy tín nhẹ nhưng chưa đủ kết luận."
    return "Chưa phát hiện tín hiệu team/backer lớn từ dữ liệu đã crawl."


def priority_label(score: int) -> str:
    if score >= 75:
        return "Cao - đáng nghiên cứu ngay"
    if score >= 55:
        return "Trung bình - theo dõi thêm"
    return "Thấp - chưa ưu tiên"


def research_action(score: int, stage: str, risk_flags: list[str]) -> str:
    if risk_flags:
        return "Chỉ theo dõi. Ưu tiên bỏ qua nếu chỉ là futures/perpetual hoặc margin."
    if stage == "token_sale_before_exchange_listing":
        return "Kiểm tra điều kiện tham gia token sale, vesting, FDV, TGE và sàn dự kiến sau TGE."
    if stage == "spot_listing_announced":
        return "Kiểm tra thời gian mở deposit/trading, thanh khoản, market cap và dùng limit order nếu nghiên cứu tiếp."
    if stage == "upcoming_release":
        return "Mở trang dự án, kiểm tra chain, tokenomics, lịch unlock, audit và sàn dự kiến."
    if score >= 75:
        return "Đưa vào danh sách nghiên cứu ưu tiên cao trong ngày."
    if score >= 55:
        return "Theo dõi thêm thông báo chính thức và dữ liệu thanh khoản."
    return "Chưa ưu tiên."


def bot_note(score: int, risk_flags: list[str]) -> str:
    if risk_flags:
        return "Có tín hiệu rủi ro trong tiêu đề; chỉ theo dõi, không mua vội."
    if score >= 75:
        return "Nguồn tương đối mạnh; cần kiểm tra tokenomics, vesting, thanh khoản, market cap, audit và cộng đồng trước khi mua."
    if score >= 55:
        return "Có tín hiệu listing nhưng chưa đủ mạnh; nên theo dõi thêm nguồn chính thức."
    return "Tín hiệu yếu hoặc thiếu dữ liệu; chưa nên ưu tiên."
