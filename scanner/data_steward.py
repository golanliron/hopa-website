#!/usr/bin/env python3
"""
Goldfish Data Steward
---------------------
AI-driven agent for maintaining and enriching the opportunities database.

Responsibilities:
  1. Scrape new sources (BTL funds, KKL, Yael, Mirkava, Innovation Authority, Horizon)
  2. NLP extraction from pages/PDFs (deadline, matching%, target population, categories)
  3. Deduplication and sanitization of titles/funders
  4. Link validation (200 OK check)
  5. UPSERT to Supabase `opportunities` — never destructive

Usage:
    python data_steward.py              # full run
    python data_steward.py --dry-run   # scan only, print report, no save
    python data_steward.py --source btl_manof   # single source
    python data_steward.py --steward-only       # only dedup/sanitize existing DB
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Windows encoding fix ───────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HE_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "אפריל": 4,
    "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
    "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}

DEADLINE_KEYWORDS = [
    "מועד הגשה", "תאריך אחרון", "הגשה עד", "דדליין", "מועד אחרון",
    "deadline", "closing date", "due date", "submission deadline",
    "עד תאריך", "פתוח עד", "הגשת בקשות עד",
]

MATCHING_KEYWORDS = [
    "השתתפות עצמית", "מימון עצמי", "התאמה", "co-funding", "matching",
    "אחוז מימון", "חלק הרשות", "תרומה עצמית",
]

TARGET_KEYWORDS = {
    "רשויות מקומיות": ["רשות מקומית", "עירייה", "מועצה", "רשויות"],
    "עמותות": ["עמותה", "ארגון", "מלכ\"ר", "ngo", "non-profit"],
    "חברות": ["חברה", "עסק", "סטארטאפ", "startup", "company"],
    "מחקר": ["אוניברסיטה", "מכון מחקר", "research", "academic"],
    "יחידים": ["אזרח", "יחיד", "פרט", "individual"],
}

CATEGORY_KEYWORDS = {
    "חינוך": ["חינוך", "בית ספר", "תלמיד", "לימודים", "education"],
    "נוער בסיכון": ["נוער בסיכון", "נשירה", "עבריינות", "at-risk youth"],
    "תעסוקה": ["תעסוקה", "עבודה", "השמה", "employment", "workforce"],
    "רווחה חברתית": ["רווחה", "סיוע", "תמיכה חברתית", "welfare"],
    "חדשנות וטכנולוגיה": ["חדשנות", "טכנולוגיה", "innovation", "tech", "digital"],
    "סביבה": ["סביבה", "אקלים", "ירוק", "environment", "green", "climate"],
    "בריאות": ["בריאות", "רפואה", "health", "medical"],
    "תרבות": ["תרבות", "אמנות", "culture", "art"],
    "קהילה": ["קהילה", "שכונה", "community"],
    "בינלאומי": ["בינלאומי", "international", "europe", "horizon"],
}


# ── Data model ────────────────────────────────────────────
@dataclass
class Opportunity:
    title: str
    funder: str
    url: str
    source_name: str
    region: str = "israel"
    description: str = ""
    deadline: Optional[str] = None
    categories: list = field(default_factory=list)
    target_populations: list = field(default_factory=list)
    grant_amount: Optional[str] = None
    matching_percent: Optional[str] = None
    pdf_url: Optional[str] = None
    active: bool = True
    data_quality_score: int = 0  # 0-100, how complete the record is
    enrichment_notes: list = field(default_factory=list)  # what was extracted from PDF

    def to_supabase_dict(self):
        d = asdict(self)
        # Remove internal fields not in DB
        d.pop("data_quality_score", None)
        d.pop("enrichment_notes", None)
        d["scraped_at"] = datetime.now().isoformat()
        return d

    def calc_quality_score(self) -> int:
        score = 0
        if self.title and len(self.title) > 10: score += 15
        if self.funder and len(self.funder) > 3: score += 15
        if self.url: score += 10
        if self.deadline: score += 20
        if self.description and len(self.description) > 50: score += 10
        if self.categories: score += 10
        if self.target_populations: score += 10
        if self.grant_amount: score += 5
        if self.matching_percent: score += 5
        self.data_quality_score = score
        return score


# ── HTTP helpers ──────────────────────────────────────────
def fetch(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        logger.warning("fetch failed %s: %s", url, e)
        return None


def fetch_text(url: str, timeout: int = 15) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "lxml").get_text(separator=" ")
    except Exception:
        return ""


def is_broken_url(url: str) -> bool:
    """Return True if URL statically looks like a broken/error page."""
    import re
    broken_patterns = [
        r"/error(/|\?|$)",
        r"/404(/|\?|$)",
        r"/not-found(/|\?|$)",
        r"/page-not-found(/|\?|$)",
        r"gov\.il/(he|en)/error",
    ]
    for pat in broken_patterns:
        if re.search(pat, url, re.IGNORECASE):
            return True
    return False


def check_link(url: str, timeout: int = 8) -> bool:
    """Return True if URL returns 200 and is not a known error page."""
    if is_broken_url(url):
        return False
    try:
        r = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:
            r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        # Also check final URL after redirects for error patterns
        final_url = r.url if hasattr(r, 'url') else url
        if is_broken_url(final_url):
            return False
        return r.status_code == 200
    except Exception:
        return False


# ── NLP extraction ────────────────────────────────────────
def extract_date(text: str) -> Optional[str]:
    """Extract the nearest future date from text."""
    today = date.today()

    for pattern, fmt in [
        (r"(\d{1,2})[./](\d{1,2})[./](20\d{2})", "dmy"),
        (r"(20\d{2})-(\d{2})-(\d{2})", "ymd"),
    ]:
        for m in re.finditer(pattern, text):
            try:
                if fmt == "dmy":
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                else:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if d >= today:
                    return d.isoformat()
            except ValueError:
                pass

    month_pat = r"(\d{1,2})\s+ב?(" + "|".join(HE_MONTHS.keys()) + r")\s*(20\d{2})?"
    for m in re.finditer(month_pat, text):
        try:
            day = int(m.group(1))
            month = HE_MONTHS[m.group(2)]
            year = int(m.group(3)) if m.group(3) else today.year
            d = date(year, month, day)
            if d < today and not m.group(3):
                d = date(year + 1, month, day)
            if d >= today:
                return d.isoformat()
        except ValueError:
            pass

    return None


def extract_deadline_from_page(url: str) -> Optional[str]:
    """Fetch a page and search near deadline keywords."""
    text = fetch_text(url)
    if not text:
        return None
    for kw in DEADLINE_KEYWORDS:
        idx = text.lower().find(kw.lower())
        if idx >= 0:
            snippet = text[max(0, idx - 20):idx + 150]
            d = extract_date(snippet)
            if d:
                return d
    return extract_date(text)


def extract_matching_percent(text: str) -> Optional[str]:
    """Extract co-funding % or amount from text."""
    for kw in MATCHING_KEYWORDS:
        idx = text.lower().find(kw.lower())
        if idx >= 0:
            snippet = text[idx:idx + 200]
            m = re.search(r"(\d{1,3})\s*%", snippet)
            if m:
                return f"{m.group(1)}%"
            m = re.search(r"(\d[\d,]*)\s*(₪|ש\"ח|NIS)", snippet)
            if m:
                return m.group(1).replace(",", "") + " ₪"
    return None


def extract_grant_amount(text: str) -> Optional[str]:
    """Extract grant size from text."""
    for pattern in [
        r"עד\s+([\d,]+)\s*(₪|ש\"ח|אלף|מיליון)",
        r"סכום[^:]*:\s*([\d,]+)",
        r"מענק[^:]*:\s*([\d,]+)",
        r"up to\s+\$?([\d,]+)",
        r"grant[^:]*:\s*\$?([\d,]+)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            suffix = m.group(2) if m.lastindex >= 2 else ""
            if "מיליון" in suffix or "million" in suffix.lower():
                return f"{raw}M ₪"
            if "אלף" in suffix or "k" in suffix.lower():
                return f"{raw}K ₪"
            return f"{raw} ₪"
    return None


def classify_text(text: str) -> tuple[list, list]:
    """Return (categories, target_populations) inferred from text."""
    text_lower = text.lower()
    cats = [cat for cat, kws in CATEGORY_KEYWORDS.items()
            if any(kw in text_lower for kw in kws)]
    pops = [pop for pop, kws in TARGET_KEYWORDS.items()
            if any(kw in text_lower for kw in kws)]
    return cats[:5], pops[:5]


def find_pdf_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Find the first PDF link on a page."""
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if href.lower().endswith(".pdf"):
            return urljoin(base_url, href)
    return None


def enrich_opportunity(opp: Opportunity) -> list[str]:
    """Deep-fetch the opportunity page and fill in missing fields. Returns enrichment notes."""
    notes = []
    if not opp.url:
        return notes

    soup = fetch(opp.url)
    if not soup:
        return notes

    text = soup.get_text(separator=" ")

    if not opp.deadline:
        d = extract_deadline_from_page(opp.url)
        if d:
            opp.deadline = d
            notes.append(f"deadline extracted from page: {d}")

    if not opp.matching_percent:
        mp = extract_matching_percent(text)
        if mp:
            opp.matching_percent = mp
            notes.append(f"matching extracted: {mp}")

    if not opp.grant_amount:
        ga = extract_grant_amount(text)
        if ga:
            opp.grant_amount = ga
            notes.append(f"amount extracted: {ga}")

    if not opp.categories or not opp.target_populations:
        cats, pops = classify_text(text)
        if cats and not opp.categories:
            opp.categories = cats
            notes.append(f"categories classified: {cats}")
        if pops and not opp.target_populations:
            opp.target_populations = pops
            notes.append(f"populations classified: {pops}")

    # Find PDF and enrich from it
    pdf_url = find_pdf_url(soup, opp.url)
    if pdf_url:
        opp.pdf_url = pdf_url
        notes.append(f"PDF found: {pdf_url}")
        # Try to fetch PDF text (works for text-layer PDFs served as text/html)
        pdf_text = fetch_text(pdf_url)
        if pdf_text and len(pdf_text) > 100:
            if not opp.deadline:
                d = extract_date(pdf_text)
                if d:
                    opp.deadline = d
                    notes.append(f"deadline from PDF: {d}")
            if not opp.matching_percent:
                mp = extract_matching_percent(pdf_text)
                if mp:
                    opp.matching_percent = mp
                    notes.append(f"matching from PDF: {mp}")

    return notes


# ── Deduplication & Sanitization ─────────────────────────
def clean_title(title: str) -> str:
    """Remove noise patterns from scraped titles."""
    if not title:
        return title

    # Remove repeated ministry/org name (e.g. "משרד החינוך - משרד החינוך - קול קורא")
    parts = re.split(r"\s*[-–|]\s*", title)
    seen = []
    for p in parts:
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            seen.append(p_clean)
    title = " — ".join(seen)

    # Remove illegal scan artifacts
    title = re.sub(r"טקסט לא חוקי כותרת", "", title)
    title = re.sub(r"\{[^}]*\}", "", title)  # JSON-LD fragments
    title = re.sub(r"@\w+", "", title)       # email fragments
    title = re.sub(r"\s{2,}", " ", title).strip()

    return title


def clean_funder(funder: str) -> str:
    """Normalize funder name."""
    if not funder:
        return funder

    funder = re.sub(r"\{[^}]*\}", "", funder)
    funder = re.sub(r"@\w+", "", funder)

    # Deduplicate repeated words
    words = funder.split()
    seen, cleaned = set(), []
    for w in words:
        key = w.strip(",.:-")
        if key not in seen:
            seen.add(key)
            cleaned.append(w)
    funder = " ".join(cleaned).strip()

    return funder


def deduplicate_opportunities(opps: list[Opportunity]) -> list[Opportunity]:
    """Remove exact URL duplicates and near-duplicate titles."""
    seen_urls = set()
    seen_titles = {}
    unique = []

    for opp in opps:
        # URL dedup
        norm_url = opp.url.rstrip("/").lower()
        if norm_url and norm_url in seen_urls:
            continue
        if norm_url:
            seen_urls.add(norm_url)

        # Title near-dedup (same funder + title words overlap > 80%)
        title_key = re.sub(r"\W+", "", opp.title.lower())[:40]
        funder_key = re.sub(r"\W+", "", opp.funder.lower())[:20]
        compound_key = funder_key + title_key

        if compound_key in seen_titles:
            logger.debug("Dedup: '%s' matches '%s'", opp.title, seen_titles[compound_key])
            continue

        seen_titles[compound_key] = opp.title
        unique.append(opp)

    logger.info("Dedup: %d -> %d unique", len(opps), len(unique))
    return unique


# ── Source scrapers ───────────────────────────────────────

def scrape_btl_manof() -> list[Opportunity]:
    """ביטוח לאומי — קרן מנוף (עסקים קטנים ובינוניים)"""
    url = "https://www.btl.gov.il/benefits/small_business/Pages/manof.aspx"
    soup = fetch(url)
    if not soup:
        return []

    opps = []
    text = soup.get_text(separator=" ")
    title = "קרן מנוף — ביטוח לאומי — מענקים לעסקים קטנים"
    deadline = extract_deadline_from_page(url)
    cats, pops = classify_text(text)
    amount = extract_grant_amount(text)

    opp = Opportunity(
        title=title,
        funder="המוסד לביטוח לאומי — קרן מנוף",
        url=url,
        source_name="btl_manof",
        categories=cats or ["תעסוקה", "חדשנות וטכנולוגיה"],
        target_populations=pops or ["חברות", "עמותות"],
        deadline=deadline,
        grant_amount=amount,
        description="קרן מנוף של ביטוח לאומי — מענקים לעסקים קטנים ובינוניים להתאוששות וצמיחה",
    )
    opps.append(opp)
    logger.info("btl_manof: %d", len(opps))
    return opps


def scrape_btl_youth() -> list[Opportunity]:
    """ביטוח לאומי — ילדים ונוער בסיכון"""
    pages = [
        ("https://www.btl.gov.il/benefits/Children_at_Risk/Pages/default.aspx",
         "ביטוח לאומי — ילדים ונוער בסיכון"),
        ("https://www.btl.gov.il/benefits/special_factories/Pages/default.aspx",
         "ביטוח לאומי — מפעלים מיוחדים"),
    ]
    opps = []
    for url, name in pages:
        soup = fetch(url)
        if not soup:
            continue
        text = soup.get_text(separator=" ")
        deadline = extract_deadline_from_page(url)
        cats, pops = classify_text(text)
        amount = extract_grant_amount(text)
        opp = Opportunity(
            title=name,
            funder="המוסד לביטוח לאומי",
            url=url,
            source_name="btl_youth",
            categories=cats or ["נוער בסיכון", "רווחה חברתית"],
            target_populations=pops or ["עמותות"],
            deadline=deadline,
            grant_amount=amount,
            description=f"תוכנית {name} של המוסד לביטוח לאומי",
        )
        opps.append(opp)
        time.sleep(0.5)
    logger.info("btl_youth: %d", len(opps))
    return opps


def scrape_kkl() -> list[Opportunity]:
    """קק\"ל — קולות קוראים לסביבה וקהילה"""
    urls = [
        "https://www.kkl.org.il/society-environment/grants/",
        "https://www.kkl.org.il/society-environment/calls-for-proposals/",
    ]
    opps = []
    seen = set()

    for base_url in urls:
        soup = fetch(base_url)
        if not soup:
            continue

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 8:
                continue
            if not href.startswith("http"):
                href = urljoin("https://www.kkl.org.il", href)
            if href in seen:
                continue
            if any(x in href for x in ["#", "javascript:", "mailto:"]):
                continue
            seen.add(href)

            parent = a.find_parent(["article", "li", "div", "tr"])
            ctx = (parent.get_text(" ", strip=True) if parent else "") + " " + title
            deadline = extract_date(ctx)
            cats, pops = classify_text(ctx)

            opps.append(Opportunity(
                title=clean_title(title),
                funder="קרן קיימת לישראל — קק\"ל",
                url=href,
                source_name="kkl",
                categories=cats or ["סביבה", "קהילה"],
                target_populations=pops or ["עמותות", "רשויות מקומיות"],
                deadline=deadline,
                description=ctx[:300],
            ))
        time.sleep(0.5)

    logger.info("kkl: %d", len(opps))
    return opps


def scrape_yaela() -> list[Opportunity]:
    """יעל\"ה — עיזבונות ייעודיים, משרד המשפטים"""
    url = "https://www.gov.il/he/departments/legalaid/govil-landing-page?skip=0&limit=10&OfficeId=moj&subject=heritage"
    soup = fetch(url)
    if not soup:
        # fallback: search page
        soup = fetch("https://www.gov.il/he/departments/legalaid")
    if not soup:
        return []

    opps = []
    seen = set()
    text_full = soup.get_text(separator=" ")

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 10:
            continue
        if not href.startswith("http"):
            href = urljoin("https://www.gov.il", href)
        if href in seen:
            continue
        if any(x in href.lower() for x in ["#", "javascript:", "mailto:"]):
            continue

        kw_hit = any(kw in title + href for kw in ["עיזבון", "יעל", "heritage", "tzava"])
        if not kw_hit:
            continue

        seen.add(href)
        parent = a.find_parent(["article", "li", "div", "tr"])
        ctx = parent.get_text(" ", strip=True) if parent else title
        deadline = extract_date(ctx)
        cats, pops = classify_text(ctx)

        opps.append(Opportunity(
            title=clean_title(title),
            funder="ועדת העיזבונות — משרד המשפטים",
            url=href,
            source_name="yaela",
            categories=cats or ["רווחה חברתית", "חינוך"],
            target_populations=pops or ["עמותות"],
            deadline=deadline,
            description=ctx[:300],
        ))

    # Also scan the dedicated YAELA page
    yaela_direct = fetch("https://yiela.justice.gov.il")
    if yaela_direct:
        for a in yaela_direct.select("a[href]"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 8 or href in seen:
                continue
            if not href.startswith("http"):
                href = urljoin("https://yiela.justice.gov.il", href)
            seen.add(href)
            parent = a.find_parent(["article", "li", "div"])
            ctx = parent.get_text(" ", strip=True) if parent else title
            deadline = extract_date(ctx)
            opps.append(Opportunity(
                title=clean_title(title),
                funder="יעל\"ה — ועדת העיזבונות",
                url=href,
                source_name="yaela",
                categories=["רווחה חברתית"],
                target_populations=["עמותות"],
                deadline=deadline,
                description=ctx[:300],
            ))

    logger.info("yaela: %d", len(opps))
    return opps


def scrape_mirkava() -> list[Opportunity]:
    """מרכב\"ה — מערכת ניהול תקציב ממשלתי (קולות קוראים)"""
    # Mirkava publishes grant calls via the Finance Ministry
    urls = [
        "https://mof.gov.il/AG/AccountantGeneral/pages/kolkore.aspx",
        "https://www.gov.il/he/departments/topics/budget-management",
    ]
    opps = []
    seen = set()

    for base_url in urls:
        soup = fetch(base_url)
        if not soup:
            continue
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 10 or href in seen:
                continue
            if not href.startswith("http"):
                href = urljoin("https://mof.gov.il", href)
            if any(x in href for x in ["#", "javascript:", "mailto:"]):
                continue
            kw_hit = any(kw in title.lower() + href.lower() for kw in
                         ["קול קורא", "מענק", "תמיכה", "grant", "rfp", "bid"])
            if not kw_hit:
                continue
            seen.add(href)

            parent = a.find_parent(["article", "li", "div", "tr"])
            ctx = parent.get_text(" ", strip=True) if parent else title
            deadline = extract_date(ctx)
            cats, pops = classify_text(ctx)

            opps.append(Opportunity(
                title=clean_title(title),
                funder="משרד האוצר — מרכב\"ה",
                url=href,
                source_name="mirkava",
                categories=cats or ["רווחה חברתית"],
                target_populations=pops or ["עמותות", "רשויות מקומיות"],
                deadline=deadline,
                description=ctx[:300],
            ))
        time.sleep(0.5)

    logger.info("mirkava: %d", len(opps))
    return opps


def scrape_innovation_authority() -> list[Opportunity]:
    """רשות החדשנות — קולות קוראים (deep crawl)"""
    base_url = "https://innovationisrael.org.il/kol_kore/"
    soup = fetch(base_url)
    if not soup:
        return []

    opps = []
    seen = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 8:
            continue
        if not href.startswith("http"):
            href = urljoin(base_url, href)
        if href.rstrip("/") == base_url.rstrip("/"):
            continue
        if href in seen:
            continue
        if any(x in href for x in ["#", "javascript:", "mailto:", "category", "page/"]):
            continue
        seen.add(href)

        parent = a.find_parent(["article", "li", "div"])
        ctx = (parent.get_text(" ", strip=True) if parent else "") + " " + title
        deadline = extract_date(ctx)
        amount = extract_grant_amount(ctx)
        cats, pops = classify_text(ctx)

        opps.append(Opportunity(
            title=clean_title(title),
            funder="רשות החדשנות",
            url=href,
            source_name="innovation_authority",
            categories=cats or ["חדשנות וטכנולוגיה"],
            target_populations=pops or ["חברות", "עמותות"],
            deadline=deadline,
            grant_amount=amount,
            description=ctx[:300],
        ))

    logger.info("innovation_authority: %d", len(opps))
    return opps


def scrape_horizon_europe() -> list[Opportunity]:
    """Horizon Europe — Israel-relevant calls (via EC portal RSS/API)"""
    # EC provides a public search API
    api_url = (
        "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails.json"
        "?callIdentifier=&deadlineBefore=&deadlineAfter=&keywords=israel+OR+youth+OR+education"
        "&frameworkProgramme=HORIZON&status=31094501&pageNumber=1&pageSize=30"
    )
    fallback_url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-search;callCode=null;freeTextSearchKeyword=israel;matchWholeText=true"

    opps = []
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("topicData", {}).get("Topics", []):
                title = item.get("title", "")
                identifier = item.get("identifier", "")
                url = f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier.lower()}"
                deadline_raw = item.get("deadlines", [{}])[0].get("deadline", "") if item.get("deadlines") else ""
                deadline = deadline_raw[:10] if deadline_raw else None

                if not title:
                    continue

                opps.append(Opportunity(
                    title=clean_title(title),
                    funder="European Commission — Horizon Europe",
                    url=url,
                    source_name="horizon_europe",
                    region="international",
                    categories=["חדשנות וטכנולוגיה", "מחקר"],
                    target_populations=["מחקר", "חברות"],
                    deadline=deadline,
                    description=item.get("objective", "")[:300],
                ))
    except Exception as e:
        logger.warning("Horizon API failed: %s — trying fallback HTML", e)
        soup = fetch(fallback_url)
        if soup:
            for a in soup.select("a[href*='topic-details']"):
                href = a.get("href", "")
                title = a.get_text(strip=True)
                if not href or not title or len(title) < 8:
                    continue
                if not href.startswith("http"):
                    href = urljoin("https://ec.europa.eu", href)
                parent = a.find_parent(["article", "li", "div"])
                ctx = parent.get_text(" ", strip=True) if parent else title
                deadline = extract_date(ctx)
                opps.append(Opportunity(
                    title=clean_title(title),
                    funder="European Commission — Horizon Europe",
                    url=href,
                    source_name="horizon_europe",
                    region="international",
                    categories=["חדשנות וטכנולוגיה"],
                    target_populations=["מחקר", "חברות"],
                    deadline=deadline,
                    description=ctx[:300],
                ))

    logger.info("horizon_europe: %d", len(opps))
    return opps


def scrape_guidestar() -> list[Opportunity]:
    """GuideStar Israel — קרנות ומוסדות (fundbase equivalent)"""
    url = "https://www.guidestar.org.il/home"
    soup = fetch(url)
    if not soup:
        return []

    opps = []
    seen = set()

    for a in soup.select("a[href*='foundation'], a[href*='fund'], a[href*='grant'], a[href*='kol']"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 8 or href in seen:
            continue
        if not href.startswith("http"):
            href = urljoin("https://www.guidestar.org.il", href)
        seen.add(href)

        parent = a.find_parent(["article", "li", "div"])
        ctx = parent.get_text(" ", strip=True) if parent else title
        deadline = extract_date(ctx)
        cats, pops = classify_text(ctx)

        opps.append(Opportunity(
            title=clean_title(title),
            funder="GuideStar Israel",
            url=href,
            source_name="guidestar",
            categories=cats or ["רווחה חברתית"],
            target_populations=pops or ["עמותות"],
            deadline=deadline,
            description=ctx[:300],
        ))

    logger.info("guidestar: %d", len(opps))
    return opps


def scrape_open_spaces_fund() -> list[Opportunity]:
    """הקרן לשטחים פתוחים — קולות קוראים"""
    url = "https://www.openspace.org.il/grants/"
    soup = fetch(url)
    if not soup:
        soup = fetch("https://www.openspace.org.il")
    if not soup:
        return []

    opps = []
    seen = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 8 or href in seen:
            continue
        if not href.startswith("http"):
            href = urljoin("https://www.openspace.org.il", href)
        if any(x in href for x in ["#", "javascript:", "mailto:"]):
            continue
        seen.add(href)

        parent = a.find_parent(["article", "li", "div"])
        ctx = parent.get_text(" ", strip=True) if parent else title
        deadline = extract_date(ctx)
        if not deadline:
            continue  # only include items with detected deadlines

        opps.append(Opportunity(
            title=clean_title(title),
            funder="הקרן לשטחים פתוחים",
            url=href,
            source_name="open_spaces_fund",
            categories=["סביבה", "קהילה"],
            target_populations=["עמותות", "רשויות מקומיות"],
            deadline=deadline,
            description=ctx[:300],
        ))

    logger.info("open_spaces_fund: %d", len(opps))
    return opps


# ── Registry of all new sources ───────────────────────────
NEW_SCRAPERS = {
    "btl_manof": scrape_btl_manof,
    "btl_youth": scrape_btl_youth,
    "kkl": scrape_kkl,
    "yaela": scrape_yaela,
    "mirkava": scrape_mirkava,
    "innovation_authority": scrape_innovation_authority,
    "horizon_europe": scrape_horizon_europe,
    "guidestar": scrape_guidestar,
    "open_spaces_fund": scrape_open_spaces_fund,
}


# ── Supabase operations ───────────────────────────────────
def supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def upsert_opportunities(opps: list[Opportunity]) -> int:
    """UPSERT to Supabase opportunities table. Returns count inserted/updated."""
    if not SUPABASE_KEY or not SUPABASE_URL:
        logger.warning("Supabase credentials missing — skipping save")
        return 0

    headers = {**supabase_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    # Filter out opportunities with broken/error URLs before saving
    filtered_opps = []
    for o in opps:
        url_to_check = o.application_url or o.url or ""
        if is_broken_url(url_to_check):
            logger.warning("Skipping opportunity with broken URL: %s — %s", o.title, url_to_check)
            continue
        filtered_opps.append(o)
    rows = [o.to_supabase_dict() for o in filtered_opps]
    batch_size = 50
    saved = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/opportunities",
                headers=headers,
                json=batch,
                timeout=20,
            )
            if r.status_code in (200, 201):
                saved += len(batch)
                logger.info("Upserted batch %d-%d (%d rows)", i, i + len(batch), len(batch))
            else:
                logger.error("Upsert failed %d: %s", r.status_code, r.text[:300])
        except Exception as e:
            logger.error("Upsert error: %s", e)

    return saved


def fetch_existing_opportunities() -> list[dict]:
    """Fetch all active opportunities from Supabase for stewardship."""
    if not SUPABASE_KEY or not SUPABASE_URL:
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/opportunities",
            headers=supabase_headers(),
            params={"select": "id,title,funder,url,deadline,categories,target_populations,active",
                    "active": "eq.true",
                    "limit": "2000"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error("fetch_existing failed: %s", e)
        return []


def update_opportunity(opp_id: str, updates: dict) -> bool:
    """PATCH a single opportunity."""
    if not SUPABASE_KEY or not SUPABASE_URL:
        return False
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/opportunities",
            headers=supabase_headers(),
            params={"id": f"eq.{opp_id}"},
            json=updates,
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def deactivate_expired(existing: list[dict]) -> int:
    """Set active=False for opportunities past their deadline."""
    today = date.today().isoformat()
    deactivated = 0
    for row in existing:
        if row.get("deadline") and row["deadline"] < today and row.get("active"):
            if update_opportunity(row["id"], {"active": False}):
                deactivated += 1
    logger.info("Deactivated %d expired opportunities", deactivated)
    return deactivated


def steward_existing(existing: list[dict], dry_run: bool = False) -> dict:
    """
    Run sanitization + link validation on existing DB records.
    Returns report dict.
    """
    report = {
        "titles_cleaned": [],
        "funders_cleaned": [],
        "links_broken": [],
        "links_checked": 0,
    }

    for row in existing:
        opp_id = row.get("id")
        updates = {}

        # Sanitize title
        orig_title = row.get("title", "")
        new_title = clean_title(orig_title)
        if new_title != orig_title:
            updates["title"] = new_title
            report["titles_cleaned"].append({"id": opp_id, "from": orig_title, "to": new_title})

        # Sanitize funder
        orig_funder = row.get("funder", "")
        new_funder = clean_funder(orig_funder)
        if new_funder != orig_funder:
            updates["funder"] = new_funder
            report["funders_cleaned"].append({"id": opp_id, "from": orig_funder, "to": new_funder})

        # Validate link (sample every 5th to avoid rate limiting)
        url = row.get("url", "")
        if url and len(report["links_checked"]) % 5 == 0 if isinstance(report["links_checked"], int) else False:
            pass  # handled below
        if url:
            report["links_checked"] += 1
            if report["links_checked"] % 5 == 0:  # check every 5th record
                if not check_link(url):
                    report["links_broken"].append({"id": opp_id, "url": url, "title": orig_title})
                    updates["active"] = False
                time.sleep(0.2)

        if updates and not dry_run:
            update_opportunity(opp_id, updates)

    logger.info("Steward: %d titles cleaned, %d funders cleaned, %d broken links",
                len(report["titles_cleaned"]), len(report["funders_cleaned"]),
                len(report["links_broken"]))
    return report


# ── Link validation ───────────────────────────────────────
def validate_and_enrich_batch(opps: list[Opportunity],
                               max_enrich: int = 30,
                               dry_run: bool = False) -> list[Opportunity]:
    """
    For each opportunity:
    1. Check link is alive
    2. If missing deadline/categories, deep-enrich from page
    Returns only valid opportunities.
    """
    valid = []
    enriched_count = 0

    for opp in opps:
        if not opp.url:
            continue

        # Quick link check
        if not check_link(opp.url):
            logger.debug("Dead link: %s", opp.url)
            continue

        # Deep enrich if fields missing and budget allows
        needs_enrichment = (
            not opp.deadline or
            not opp.categories or
            not opp.target_populations or
            not opp.grant_amount
        )
        if needs_enrichment and enriched_count < max_enrich:
            notes = enrich_opportunity(opp)
            if notes:
                opp.enrichment_notes = notes
                enriched_count += 1
            time.sleep(0.3)

        opp.calc_quality_score()
        valid.append(opp)

    logger.info("Validated %d/%d, enriched %d", len(valid), len(opps), enriched_count)
    return valid


# ── Report generation ─────────────────────────────────────
def build_report(new_opps: list[Opportunity], steward_report: dict) -> str:
    """Build a Markdown report of the steward run."""
    lines = [
        f"# Goldfish Data Steward — דוח ריצה",
        f"**תאריך:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        "## רשומות חדשות",
        f"סה\"כ: **{len(new_opps)}** הזדמנויות חדשות",
        "",
        "| כותרת | גוף מממן | דדליין | ציון | הערות העשרה |",
        "|-------|----------|--------|------|-------------|",
    ]
    for o in sorted(new_opps, key=lambda x: x.deadline or "9999"):
        notes_str = "; ".join(o.enrichment_notes[:2]) if o.enrichment_notes else "—"
        lines.append(
            f"| {o.title[:50]} | {o.funder[:30]} | {o.deadline or '—'} "
            f"| {o.data_quality_score} | {notes_str} |"
        )

    lines += [
        "",
        "## טיוב רשומות קיימות",
        f"- כותרות תוקנו: **{len(steward_report.get('titles_cleaned', []))}**",
        f"- גופים מממנים תוקנו: **{len(steward_report.get('funders_cleaned', []))}**",
        f"- קישורים שבורים: **{len(steward_report.get('links_broken', []))}**",
        f"- קישורים שנבדקו: **{steward_report.get('links_checked', 0)}**",
    ]

    if steward_report.get("titles_cleaned"):
        lines += ["", "### כותרות שתוקנו"]
        for item in steward_report["titles_cleaned"][:10]:
            lines.append(f"- `{item['from'][:60]}` → `{item['to'][:60]}`")

    if steward_report.get("links_broken"):
        lines += ["", "### קישורים שבורים"]
        for item in steward_report["links_broken"][:10]:
            lines.append(f"- {item['title'][:50]}: `{item['url']}`")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Goldfish Data Steward")
    parser.add_argument("--dry-run", action="store_true", help="סרוק בלי לשמור")
    parser.add_argument("--source", help="הרץ מקור ספציפי בלבד")
    parser.add_argument("--steward-only", action="store_true", help="טייב DB קיים בלי סריקה")
    parser.add_argument("--no-enrich", action="store_true", help="דלג על העשרה מדפים")
    parser.add_argument("--report", action="store_true", help="שמור דוח Markdown")
    args = parser.parse_args()

    print("=" * 55)
    print("  Goldfish Data Steward")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)

    # ── Step 1: Steward existing DB ────────────────────────
    steward_report = {}
    if not args.source:
        print("\n[1/4] Fetching existing opportunities...")
        existing = fetch_existing_opportunities()
        print(f"      Found {len(existing)} active records")

        print("[2/4] Deactivating expired...")
        deactivate_expired(existing)

        print("[3/4] Sanitizing titles, funders, links...")
        steward_report = steward_existing(existing, dry_run=args.dry_run)

    if args.steward_only:
        print("\nSteward-only mode complete.")
        print(build_report([], steward_report))
        return

    # ── Step 2: Scrape new sources ─────────────────────────
    print("\n[4/4] Scraping new sources...")
    all_new: list[Opportunity] = []

    sources_to_run = (
        {args.source: NEW_SCRAPERS[args.source]}
        if args.source and args.source in NEW_SCRAPERS
        else NEW_SCRAPERS
    )

    for name, fn in sources_to_run.items():
        print(f"  -> {name}")
        try:
            opps = fn()
            all_new.extend(opps)
            print(f"     {len(opps)} found")
        except Exception as e:
            logger.error("%s failed: %s", name, e)
        time.sleep(1)

    print(f"\nTotal raw: {len(all_new)}")

    # ── Step 3: Dedup + Sanitize ───────────────────────────
    for o in all_new:
        o.title = clean_title(o.title)
        o.funder = clean_funder(o.funder)

    all_new = deduplicate_opportunities(all_new)
    print(f"After dedup: {len(all_new)}")

    # ── Step 4: Validate links + enrich ────────────────────
    if not args.no_enrich:
        print("Validating links + enriching from pages...")
        all_new = validate_and_enrich_batch(all_new, max_enrich=25, dry_run=args.dry_run)
        print(f"After validation: {len(all_new)}")

    # ── Step 5: Quality scoring ────────────────────────────
    for o in all_new:
        o.calc_quality_score()

    # Stats
    has_deadline = sum(1 for o in all_new if o.deadline)
    has_amount = sum(1 for o in all_new if o.grant_amount)
    has_matching = sum(1 for o in all_new if o.matching_percent)
    avg_quality = sum(o.data_quality_score for o in all_new) / max(len(all_new), 1)

    print(f"\nQuality stats:")
    print(f"  With deadline:  {has_deadline}/{len(all_new)}")
    print(f"  With amount:    {has_amount}/{len(all_new)}")
    print(f"  With matching%: {has_matching}/{len(all_new)}")
    print(f"  Avg quality:    {avg_quality:.0f}/100")

    # ── Step 6: Dry run preview ────────────────────────────
    if args.dry_run:
        print("\n--- DRY RUN (top 20 by quality) ---")
        for o in sorted(all_new, key=lambda x: -x.data_quality_score)[:20]:
            print(f"  [{o.data_quality_score:3d}] [{o.deadline or '       '}] "
                  f"{o.title[:55]:<55} | {o.funder[:25]}")
        print("\nSteward report:")
        print(build_report(all_new, steward_report))
        return

    # ── Step 7: Save to Supabase ───────────────────────────
    saved = upsert_opportunities(all_new)
    print(f"\nSaved {saved} opportunities to Supabase")

    # ── Step 8: Report ─────────────────────────────────────
    report_md = build_report(all_new, steward_report)
    if args.report:
        os.makedirs("outputs", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = f"outputs/steward_report_{ts}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"Report saved: {report_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
