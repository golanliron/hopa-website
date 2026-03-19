"""Base scanner — HTTP fetching + data model."""
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import (REQUEST_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
                    CATEGORY_BASE_SCORE, HOPA_KEYWORDS_HE, HOPA_KEYWORDS_EN)

logger = logging.getLogger(__name__)


@dataclass
class Call:
    title: str
    source: str
    url: str
    category: str
    region: str
    description: str = ""
    deadline: Optional[str] = None
    grant_amount: Optional[str] = None
    tags: list = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    match_score: int = 0

    def to_dict(self):
        return asdict(self)


def calc_match_score(call: "Call") -> int:
    """Calculate Hopa relevance score 0-100."""
    score = CATEGORY_BASE_SCORE.get(call.category, 10)

    text = f"{call.title} {call.description} {call.source}".lower()

    bonus = 0
    for kw in HOPA_KEYWORDS_HE:
        if kw in text:
            bonus += 5
    for kw in HOPA_KEYWORDS_EN:
        if kw in text:
            bonus += 5

    # Cap bonus at 40
    score += min(bonus, 40)
    return min(score, 100)


class BaseScanner:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)

    def fetch(self, url: str) -> Optional[BeautifulSoup]:
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = self.session.get(url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                return BeautifulSoup(r.text, "lxml")
            except Exception as e:
                logger.warning("Attempt %d/%d failed %s: %s", attempt + 1, MAX_RETRIES + 1, url, e)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        return None

    def fetch_raw(self, url: str) -> Optional[str]:
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = self.session.get(url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                return r.text
            except Exception as e:
                logger.warning("Attempt %d/%d failed %s: %s", attempt + 1, MAX_RETRIES + 1, url, e)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        return None

    def extract_calls(self, soup: BeautifulSoup, source: dict, region: str) -> list[Call]:
        calls = []
        base = source["url"]

        # Try article/list-item containers first
        containers = soup.select(
            "article, .post, .entry, .call-item, .grant-item, "
            ".views-row, .node, .item-list li, .card, li.type-post"
        )
        for c in containers:
            call = self._from_container(c, source, region, base)
            if call:
                calls.append(call)

        # Fallback: collect relevant anchor links
        if not calls:
            for a in soup.select("a[href]"):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if self._is_relevant(title):
                    calls.append(Call(
                        title=title,
                        source=source["name"],
                        url=urljoin(base, href),
                        category=source["category"],
                        region=region,
                    ))

        # Deduplicate by URL
        seen, unique = set(), []
        for c in calls:
            if c.url not in seen:
                seen.add(c.url)
                unique.append(c)
        return unique

    def _from_container(self, el, source, region, base) -> Optional[Call]:
        title_el = el.select_one("h1,h2,h3,h4,.title,.entry-title,.card-title")
        link_el  = el.select_one("a[href]")
        title = (title_el or link_el or el).get_text(strip=True)
        if not title or len(title) < 5:
            return None
        url = urljoin(base, link_el["href"]) if link_el else base
        desc_el = el.select_one(".excerpt,.summary,.description,p,.entry-content")
        desc = desc_el.get_text(strip=True)[:300] if desc_el else ""
        deadline = None
        for t in el.stripped_strings:
            if any(k in t.lower() for k in ["מועד","דדליין","deadline","תאריך אחרון","עד ליום","closing"]):
                deadline = t[:100]
                break
        return Call(title=title, source=source["name"], url=url,
                    category=source["category"], region=region,
                    description=desc, deadline=deadline)

    def _is_relevant(self, title: str) -> bool:
        if not title or len(title) < 8:
            return False
        skip = ["menu","nav","footer","cookie","privacy","צור קשר","אודות","תפריט"]
        t = title.lower()
        if any(s in t for s in skip):
            return False
        keywords = ["קול קורא","מענק","תמיכה","הגשה","מלגה","grant","call","proposal","fund","deadline","fellowship"]
        return any(k in t for k in keywords)
