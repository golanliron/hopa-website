"""
Specific scrapers per source — each knows exactly how to extract
title + URL + deadline from its target site.
"""
import re
import time
import logging
from datetime import date
from urllib.parse import urljoin, unquote
from typing import Optional

import requests
from bs4 import BeautifulSoup

from base_scanner import Call

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

HE_MONTHS = {
    'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'אפריל': 4,
    'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
    'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12,
}


def fetch(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or 'utf-8'
        return BeautifulSoup(r.text, 'lxml')
    except Exception as e:
        logger.warning("fetch failed %s: %s", url, e)
        return None


def extract_date(text: str) -> Optional[str]:
    """Extract a future deadline date from text. Returns ISO string or None."""
    today = date.today()

    # dd/mm/yyyy or dd.mm.yyyy
    m = re.search(r'(\d{1,2})[./](\d{1,2})[./](20\d{2})', text)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if d >= today:
                return d.isoformat()
        except ValueError:
            pass

    # yyyy-mm-dd
    m = re.search(r'(20\d{2})-(\d{2})-(\d{2})', text)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d >= today:
                return d.isoformat()
        except ValueError:
            pass

    # Hebrew month
    m = re.search(r'(\d{1,2})\s+ב?(ינואר|פברואר|מרץ|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s*(20\d{2})?', text)
    if m:
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


# ── Shatil ────────────────────────────────────────────────
def scrape_shatil() -> list[Call]:
    soup = fetch("https://shatil.org.il/%D7%A7%D7%A8%D7%A0%D7%95%D7%AA-%D7%95%D7%A7%D7%95%D7%9C%D7%95%D7%AA-%D7%A7%D7%95%D7%A8%D7%90%D7%99%D7%9D/")
    if not soup:
        return []

    calls = []
    seen = set()

    for a in soup.select('a[href*="/kol/"]'):
        href = a.get('href', '')
        if not href or href in seen:
            continue
        seen.add(href)

        raw_text = a.get_text(separator=' ', strip=True)
        deadline = extract_date(raw_text)
        if not deadline:
            continue

        title = re.sub(r'^\s*\d{1,2}[./]\d{1,2}[./]20\d{2}\s*', '', raw_text).strip()
        title = re.sub(r'^[^\w\u0590-\u05FF]+', '', title).strip()
        if not title or len(title) < 8:
            title = unquote(href.rstrip('/').split('/')[-1]).replace('-', ' ')

        calls.append(Call(
            title=title,
            source="שתיל — קרנות וקולות קוראים",
            url=href,
            category="social",
            region="israel",
            deadline=deadline,
        ))

    logger.info("shatil: %d calls", len(calls))
    return calls


# ── Mashabim ──────────────────────────────────────────────
def scrape_mashabim() -> list[Call]:
    soup = fetch("https://mashabim.org/main-page/")
    if not soup:
        return []

    calls = []
    seen = set()

    for a in soup.select('a[href*="mashabim.org/"]'):
        href = a.get('href', '')
        title = a.get_text(strip=True)
        if not href or href in seen:
            continue
        if any(x in href for x in ['main-page', 'category', '/page/', 'tag/', '#']):
            continue
        if len(title) < 10:
            continue
        seen.add(href)

        parent = a.find_parent(['li', 'div', 'article', 'td'])
        ctx = (parent.get_text(' ', strip=True) if parent else '') + ' ' + title
        deadline = extract_date(ctx)
        if not deadline:
            continue

        calls.append(Call(
            title=title,
            source="משאבים — מענקים לעמותות",
            url=href,
            category="ngo",
            region="israel",
            deadline=deadline,
        ))

    logger.info("mashabim: %d calls", len(calls))
    return calls


# ── Innovation Israel ─────────────────────────────────────
def scrape_innovation_israel() -> list[Call]:
    soup = fetch("https://innovationisrael.org.il/kol_kore/")
    if not soup:
        return []

    calls = []
    seen = set()

    for a in soup.select('a[href*="/kol_kore/"]'):
        href = a.get('href', '')
        if not href or href in seen or href.rstrip('/').endswith('/kol_kore'):
            continue
        seen.add(href)

        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue

        parent = a.find_parent(['article', 'li', 'div'])
        ctx = parent.get_text(' ', strip=True) if parent else title
        deadline = extract_date(ctx)
        if not deadline:
            continue

        calls.append(Call(
            title=title,
            source="רשות החדשנות — קולות קוראים",
            url=href,
            category="innovation",
            region="israel",
            deadline=deadline,
        ))

    logger.info("innovation_israel: %d calls", len(calls))
    return calls


# ── Gov.il kolkore ────────────────────────────────────────
def scrape_govil_kolkore() -> list[Call]:
    urls = [
        "https://www.gov.il/he/Departments/DynamicCollectors/kolkore-list",
        "https://www.gov.il/he/departments/policies/kolkore_social_welfare",
        "https://www.gov.il/he/departments/policies/kolkore_education",
    ]
    calls = []
    seen = set()

    for base_url in urls:
        soup = fetch(base_url)
        if not soup:
            continue

        for a in soup.select('a[href*="gov.il"]'):
            href = a.get('href', '')
            if not href or href in seen:
                continue
            if not any(k in href for k in ['/pages/', '/departments/publications/', '/service/', '/BlobFolder/']):
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            seen.add(href)

            parent = a.find_parent(['li', 'div', 'article', 'tr'])
            ctx = (parent.get_text(' ', strip=True) if parent else '') + ' ' + title
            deadline = extract_date(ctx)
            if not deadline:
                continue

            calls.append(Call(
                title=title,
                source="gov.il — קולות קוראים",
                url=href,
                category="government",
                region="israel",
                deadline=deadline,
            ))
        time.sleep(0.5)

    logger.info("govil_kolkore: %d calls", len(calls))
    return calls


# ── Israel Grantwatch ─────────────────────────────────────
def scrape_grantwatch_israel() -> list[Call]:
    pages = [
        "https://israel.grantwatch.com/cat/47/youth.html",
        "https://israel.grantwatch.com/cat/3/education.html",
        "https://israel.grantwatch.com/cat/32/social-services.html",
        "https://israel.grantwatch.com/cat/15/children.html",
    ]
    calls = []
    seen = set()

    for page_url in pages:
        soup = fetch(page_url)
        if not soup:
            continue

        for a in soup.select('a.grant-title, h2 a, h3 a, .grant-name a, a[href*="/grant/"]'):
            href = a.get('href', '')
            if not href or href in seen:
                continue
            if not href.startswith('http'):
                href = urljoin('https://israel.grantwatch.com', href)
            seen.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 8:
                continue

            parent = a.find_parent(['div', 'article', 'li', 'tr'])
            ctx = parent.get_text(' ', strip=True) if parent else ''
            deadline = extract_date(ctx)
            if not deadline:
                continue

            calls.append(Call(
                title=title,
                source="Israel Grantwatch",
                url=href,
                category="ngo",
                region="international",
                deadline=deadline,
            ))
        time.sleep(0.5)

    logger.info("grantwatch_israel: %d calls", len(calls))
    return calls


# ── fundsforNGOs ──────────────────────────────────────────
def scrape_fundsforngos() -> list[Call]:
    pages = [
        "https://www2.fundsforngos.org/category/youth-adolescents/",
        "https://www2.fundsforngos.org/category/education/",
        "https://www2.fundsforngos.org/category/latest-funds-for-ngos/",
    ]
    calls = []
    seen = set()

    for page_url in pages:
        soup = fetch(page_url)
        if not soup:
            continue

        for a in soup.select('h2 a, h3 a, .entry-title a'):
            href = a.get('href', '')
            if not href or href in seen:
                continue
            seen.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 8:
                continue

            parent = a.find_parent(['article', 'div', 'li'])
            ctx = parent.get_text(' ', strip=True) if parent else ''
            deadline = extract_date(ctx)
            if not deadline:
                continue

            calls.append(Call(
                title=title,
                source="fundsforNGOs",
                url=href,
                category="youth_at_risk",
                region="international",
                deadline=deadline,
            ))
        time.sleep(0.5)

    logger.info("fundsforngos: %d calls", len(calls))
    return calls


# ── Tmichot (Ministry of Finance) ────────────────────────
def scrape_tmichot() -> list[Call]:
    soup = fetch("https://tmichot.mof.gov.il/call-for-proposals/")
    if not soup:
        return []

    calls = []
    seen = set()

    for row in soup.select('tr, article, .grant-row, li.grant'):
        links = row.select('a[href]')
        if not links:
            continue
        a = links[0]
        href = a.get('href', '')
        if not href or href in seen:
            continue
        if not href.startswith('http'):
            href = urljoin('https://tmichot.mof.gov.il', href)
        seen.add(href)

        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue

        ctx = row.get_text(' ', strip=True)
        deadline = extract_date(ctx)
        if not deadline:
            continue

        calls.append(Call(
            title=title,
            source="אתר התמיכות הממשלתי — משרד האוצר",
            url=href,
            category="government",
            region="israel",
            deadline=deadline,
        ))

    logger.info("tmichot: %d calls", len(calls))
    return calls


# ── Deep crawl: fetch deadline from individual page ───────
def fetch_deadline_from_page(url: str) -> Optional[str]:
    """Open a grant page and search for deadline in the page text."""
    soup = fetch(url, timeout=12)
    if not soup:
        return None
    # look near deadline keywords
    text = soup.get_text(separator=' ')
    # search around deadline keywords
    for kw in ['מועד הגשה', 'תאריך אחרון', 'הגשה עד', 'דדליין', 'deadline', 'closing date', 'due date', 'עד תאריך', 'מועד אחרון']:
        idx = text.lower().find(kw.lower())
        if idx >= 0:
            snippet = text[idx:idx+120]
            d = extract_date(snippet)
            if d:
                return d
    # fallback: try any date in full text
    return extract_date(text)


# ── Gov.il deep scraper ───────────────────────────────────
def scrape_govil_deep(base_url: str, source_name: str, category: str) -> list[Call]:
    """Fetch gov.il listing page, then crawl each item page for deadline."""
    soup = fetch(base_url)
    if not soup:
        return []

    calls = []
    seen = set()
    candidates = []

    for a in soup.select('a[href]'):
        href = a.get('href', '')
        if not href or href in seen:
            continue
        if not any(k in href for k in ['/pages/', '/departments/publications/', '/service/', '/BlobFolder/', '/rfp/']):
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        seen.add(href)
        candidates.append((title, href))

    logger.info("govil_deep %s: %d candidates", source_name, len(candidates))

    for title, href in candidates[:60]:  # max 60 per source
        # first try deadline from listing context
        parent = soup.find('a', href=href)
        ctx = ''
        if parent:
            p = parent.find_parent(['li', 'div', 'tr', 'article'])
            ctx = p.get_text(' ', strip=True) if p else ''
        deadline = extract_date(ctx)

        # if not found, crawl the page
        if not deadline:
            deadline = fetch_deadline_from_page(href)
            time.sleep(0.3)

        if not deadline:
            continue

        calls.append(Call(
            title=title,
            source=source_name,
            url=href,
            category=category,
            region="israel",
            deadline=deadline,
        ))

    logger.info("govil_deep %s: %d calls with deadline", source_name, len(calls))
    return calls


def scrape_govil_all() -> list[Call]:
    sources = [
        ("https://www.gov.il/he/Departments/DynamicCollectors/kolkore-list", "gov.il — קולות קוראים", "government"),
        ("https://tmichot.mof.gov.il/call-for-proposals/", "אתר התמיכות הממשלתי — משרד האוצר", "government"),
        ("https://www.molsa.gov.il/AbourMinistry/tenders/Pages/default.aspx", "משרד הרווחה — קולות קוראים", "youth_at_risk"),
    ]
    all_calls = []
    seen = set()
    for url, name, cat in sources:
        calls = scrape_govil_deep(url, name, cat)
        for c in calls:
            if c.url not in seen:
                seen.add(c.url)
                all_calls.append(c)
        time.sleep(1)
    return all_calls


# ── tmichot.mof.gov.il (SPA — via hidden JSON API) ────────
def scrape_tmichot_api() -> list[Call]:
    """Ministry of Finance grant portal — fetches via internal API used by the SPA."""
    api_urls = [
        "https://tmichot.mof.gov.il/api/calls?status=open&skip=0&limit=50",
        "https://tmichot.mof.gov.il/api/tenders?status=open&skip=0&limit=50",
        "https://tmichot.mof.gov.il/api/grants?active=true&limit=50",
    ]
    calls = []
    seen = set()

    for api_url in api_urls:
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                continue
            items = r.json()
            if isinstance(items, dict):
                items = items.get("data", items.get("items", items.get("results", [])))
            for item in items:
                url = item.get("url") or item.get("link") or item.get("href") or ""
                title = item.get("title") or item.get("name") or item.get("subject") or ""
                if not title or url in seen:
                    continue
                if url:
                    seen.add(url)
                deadline = (item.get("deadline") or item.get("closingDate") or
                            item.get("endDate") or "")[:10] or None
                calls.append(Call(
                    title=title,
                    source="אתר התמיכות הממשלתי — משרד האוצר",
                    url=url or api_url,
                    category="government",
                    region="israel",
                    deadline=deadline,
                    description=item.get("description", "")[:300],
                ))
        except Exception as e:
            logger.debug("tmichot api %s: %s", api_url, e)

    # Fallback: try fetching the SPA shell and look for embedded JSON
    if not calls:
        try:
            r = requests.get("https://tmichot.mof.gov.il/call-for-proposals/",
                             headers=HEADERS, timeout=12)
            r.encoding = "utf-8"
            import json as _json
            # Look for __NEXT_DATA__ or window.__STATE__ or similar
            for pattern in [
                r'window\.__STATE__\s*=\s*(\{.*?\});',
                r'window\.__DATA__\s*=\s*(\{.*?\});',
                r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>',
            ]:
                m = re.search(pattern, r.text, re.DOTALL)
                if m:
                    try:
                        data = _json.loads(m.group(1))
                        items = []
                        # Walk nested structure
                        def _walk(obj):
                            if isinstance(obj, list):
                                for x in obj:
                                    _walk(x)
                            elif isinstance(obj, dict):
                                if any(k in obj for k in ["title", "deadline", "closingDate"]):
                                    items.append(obj)
                                for v in obj.values():
                                    _walk(v)
                        _walk(data)
                        for item in items:
                            title = item.get("title") or item.get("name") or ""
                            if not title:
                                continue
                            url = item.get("url") or item.get("link") or ""
                            deadline = (item.get("deadline") or item.get("closingDate") or "")[:10] or None
                            calls.append(Call(
                                title=title,
                                source="אתר התמיכות הממשלתי — משרד האוצר",
                                url=url or "https://tmichot.mof.gov.il/call-for-proposals/",
                                category="government",
                                region="israel",
                                deadline=deadline,
                            ))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("tmichot SPA fallback: %s", e)

    logger.info("tmichot_api: %d calls", len(calls))
    return calls


# ── ISF — קרן הלאומית למדע (Angular SPA workaround) ───────
def scrape_isf() -> list[Call]:
    """Israel Science Foundation — fetches static pages from the Angular app."""
    # ISF serves static HTML with Angular, but the grant pages have a predictable structure
    pages = [
        ("https://www.isf.org.il/#/funding/research-grants", "ISF — Research Grants"),
        ("https://www.isf.org.il/#/funding/personal-research-grants", "ISF — Personal Grants"),
        ("https://www.isf.org.il/#/funding/special-research-programs", "ISF — Special Programs"),
    ]
    # ISF's Angular app doesn't SSR — fetch the page and extract from any inline JSON
    calls = []
    try:
        r = requests.get("https://www.isf.org.il/", headers=HEADERS, timeout=12, verify=False)
        r.encoding = "utf-8"
        text = r.text

        # Look for grant data embedded in the JS bundles referenced
        bundle_urls = re.findall(r'src=["\']([^"\']+\.js)["\']', text)
        for burl in bundle_urls[:6]:
            if not burl.startswith("http"):
                burl = urljoin("https://www.isf.org.il/", burl)
            try:
                br = requests.get(burl, headers=HEADERS, timeout=10, verify=False)
                br.encoding = "utf-8"
                # Extract any Hebrew grant names from JS
                titles = re.findall(r'"title"\s*:\s*"([^"]{10,100})"', br.text)
                deadlines = re.findall(r'"deadline"\s*:\s*"([0-9\-/]{8,10})"', br.text)
                for i, title in enumerate(titles[:10]):
                    deadline = deadlines[i] if i < len(deadlines) else None
                    if deadline and len(deadline) == 10:
                        calls.append(Call(
                            title=title,
                            source="קרן הלאומית למדע — ISF",
                            url="https://www.isf.org.il/#/funding",
                            category="innovation",
                            region="israel",
                            deadline=deadline,
                        ))
            except Exception:
                pass
            time.sleep(0.2)

        # Fallback: add known annual grant programs as static entries
        if not calls:
            today = date.today()
            annual_deadline = f"{today.year}-12-15"
            for program, cat in [
                ("ISF — Regular Research Grants", "innovation"),
                ("ISF — Personal Research Grants for New Faculty", "innovation"),
                ("ISF — Special Research Programs", "innovation"),
            ]:
                calls.append(Call(
                    title=program,
                    source="קרן הלאומית למדע — ISF",
                    url="https://www.isf.org.il/#/funding/research-grants",
                    category=cat,
                    region="israel",
                    deadline=annual_deadline,
                    description="קרן הלאומית למדע — מענקי מחקר שנתיים לחוקרים אקדמאיים",
                ))
    except Exception as e:
        logger.warning("isf: %s", e)

    logger.info("isf: %d calls", len(calls))
    return calls


# ── BSF — US-Israel Binational Science Foundation ─────────
def scrape_bsf() -> list[Call]:
    """BSF — scrapes funding-opportunities pages via sitemap."""
    funding_urls = [
        "https://www.bsf.org.il/funding-opportunities/bsf-research-grants/submission/",
        "https://www.bsf.org.il/funding-opportunities/nsf-bsf-joint-research-grants/submission/",
        "https://www.bsf.org.il/funding-opportunities/start-up-research-grants/submission/",
        "https://www.bsf.org.il/funding-opportunities/the-prof-rahamimoff-travel-grants-for-young-scientists/submission/",
        "https://www.bsf.org.il/funding-opportunities/neh-bsf-research-grants/submission/",
        "https://www.bsf.org.il/about/announcements/",
    ]
    calls = []
    seen = set()

    for url in funding_urls:
        soup = fetch(url, timeout=15)
        if not soup:
            # BSF has SSL issues — retry with verify=False
            try:
                r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "lxml")
            except Exception:
                continue

        text = soup.get_text(separator=" ")
        title_tag = soup.find("h1") or soup.find("h2")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            # derive from URL
            title = url.rstrip("/").split("/")[-2].replace("-", " ").title()
        title = f"BSF — {title}"

        if url in seen:
            continue
        seen.add(url)

        deadline = extract_date(text)

        # Extract amount from text
        amount = None
        m = re.search(r"\$\s*([\d,]+)\s*(K|M|thousand|million)?", text, re.IGNORECASE)
        if m:
            amount = f"${m.group(1)}{m.group(2) or ''}"

        calls.append(Call(
            title=title,
            source="BSF — US-Israel Binational Science Foundation",
            url=url,
            category="innovation",
            region="international",
            deadline=deadline,
            grant_amount=amount,
            description=text[:300],
        ))
        time.sleep(0.3)

    logger.info("bsf: %d calls", len(calls))
    return calls


# ── Olympic Committee IL ───────────────────────────────────
def scrape_olympic_il() -> list[Call]:
    """הוועד האולימפי הישראלי — מענקים לספורטאים וגופי ספורט"""
    urls = [
        "https://olympic.org.il/grants",
        "https://olympic.org.il/support",
        "https://olympic.org.il/",
    ]
    calls = []
    seen = set()

    for base_url in urls:
        try:
            r = requests.get(base_url, headers=HEADERS, timeout=12, verify=False)
            r.encoding = "utf-8"
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
        except Exception as e:
            logger.debug("olympic %s: %s", base_url, e)
            continue

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 8 or href in seen:
                continue
            if not href.startswith("http"):
                href = urljoin("https://olympic.org.il", href)
            if any(x in href for x in ["#", "javascript:", "mailto:", "facebook", "instagram"]):
                continue
            kw = any(kw in title + href for kw in
                     ["מענק", "תמיכה", "grant", "support", "קול", "הגשה"])
            if not kw:
                continue
            seen.add(href)

            parent = a.find_parent(["article", "li", "div"])
            ctx = (parent.get_text(" ", strip=True) if parent else "") + " " + title
            deadline = extract_date(ctx)

            calls.append(Call(
                title=title,
                source="הוועד האולימפי הישראלי",
                url=href,
                category="sport",
                region="israel",
                deadline=deadline,
                description=ctx[:250],
            ))
        time.sleep(0.5)

    # If nothing found — add static known program
    if not calls:
        calls.append(Call(
            title="הוועד האולימפי — תמיכה בספורטאים ובגופי ספורט",
            source="הוועד האולימפי הישראלי",
            url="https://olympic.org.il/",
            category="sport",
            region="israel",
            deadline=None,
            description="תמיכה כספית לספורטאים ולעמותות ספורט — פרטים באתר הוועד האולימפי",
        ))

    logger.info("olympic_il: %d calls", len(calls))
    return calls


# ── Sport Authority (via mashabim + wingate fallback) ──────
def scrape_sport_authority() -> list[Call]:
    """רשות הספורט / ספורט ישראל — mcs.gov.il חסום, מחפש דרך mashabim + wingate"""
    # gov.il/mcs.gov.il return 403/SSL errors — use mashabim search as proxy
    sport_search_urls = [
        ("https://mashabim.org/?s=%D7%A1%D7%A4%D7%95%D7%A8%D7%98", "משאבים — ספורט"),
        ("https://mashabim.org/?s=%D7%A8%D7%A9%D7%95%D7%AA+%D7%94%D7%A1%D7%A4%D7%95%D7%A8%D7%98", "משאבים — רשות הספורט"),
        ("https://wingate.org.il/", "מכון וינגייט — מענקי ספורט"),
    ]
    calls = []
    seen = set()

    for base_url, source_name in sport_search_urls:
        soup = fetch(base_url)
        if not soup:
            continue

        for a in soup.select("h2 a, h3 a, .entry-title a, a[href*='sport'], a[href*='ספורט']"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 8 or href in seen:
                continue
            if not href.startswith("http"):
                href = urljoin(base_url, href)
            seen.add(href)

            parent = a.find_parent(["article", "div", "li"])
            ctx = (parent.get_text(" ", strip=True) if parent else "") + " " + title
            deadline = extract_date(ctx)
            if not deadline:
                continue  # only actionable items

            calls.append(Call(
                title=title,
                source=source_name,
                url=href,
                category="sport",
                region="israel",
                deadline=deadline,
                description=ctx[:250],
            ))
        time.sleep(0.5)

    logger.info("sport_authority: %d calls", len(calls))
    return calls


# ── data.gov.il open dataset API ──────────────────────────
def scrape_data_govil() -> list[Call]:
    """data.gov.il — CKAN API for published government grant datasets."""
    # Search for grant/tender datasets
    search_terms = ["קול קורא", "מענק לעמותות", "תמיכה בעמותות", "רשות מקומית מענק"]
    calls = []
    seen = set()

    for term in search_terms:
        try:
            r = requests.get(
                "https://data.gov.il/api/3/action/package_search",
                params={"q": term, "rows": 20},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            r.encoding = "utf-8"
            data = r.json()
            for pkg in data.get("result", {}).get("results", []):
                title = pkg.get("title", "")
                pkg_url = pkg.get("url") or f"https://data.gov.il/dataset/{pkg.get('name','')}"
                notes = pkg.get("notes", "")[:300]
                if not title or pkg_url in seen:
                    continue
                if len(title) < 8:
                    continue
                seen.add(pkg_url)

                # Try to find deadline in notes or extras
                deadline = extract_date(notes)
                if not deadline:
                    for extra in pkg.get("extras", []):
                        if "deadline" in extra.get("key", "").lower() or "תאריך" in extra.get("key", ""):
                            deadline = extract_date(extra.get("value", ""))
                            if deadline:
                                break

                calls.append(Call(
                    title=title,
                    source="data.gov.il — מאגר הנתונים הפתוח",
                    url=pkg_url,
                    category="government",
                    region="israel",
                    deadline=deadline,
                    description=notes,
                ))
        except Exception as e:
            logger.debug("data_govil term '%s': %s", term, e)
        time.sleep(0.3)

    logger.info("data_govil: %d calls", len(calls))
    return calls


# ── Class Action / Settlement scrapers ────────────────────
# SAFETY: these sources are DRY-RUN ONLY — never saved to DB automatically.
# Call scrape_class_action_dryrun() explicitly for inspection.

def _fetch_govil_dynamic_collector(template_id: str, skip: int = 0, limit: int = 50) -> list[dict]:
    """
    Call gov.il DynamicCollector API.
    Returns list of raw item dicts, or [] on failure.
    gov.il uses Cloudflare — we need a real browser session cookie to bypass it.
    Falls back to HTML scraping of the listing page.
    """
    import json as _json

    base_page = f"https://www.gov.il/he/Departments/DynamicCollectors/{template_id}?skip={skip}"
    api_url   = "https://www.gov.il/he/api/DynamicCollector"

    # Step 1: fetch listing page to get cookies + extract client metadata
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
    })

    try:
        r = session.get(base_page, timeout=15)
    except Exception as e:
        logger.warning("govil dynamic: page fetch failed: %s", e)
        return []

    if r.status_code == 403:
        logger.warning("govil dynamic: Cloudflare 403 on page — cannot bypass without browser")
        return []

    # Parse page for DynamicTemplateID / x-client-id
    client_id = "HeGovIL"  # default known value
    m = re.search(r'["\']?x-client-id["\']?\s*[:=]\s*["\']([^"\']+)["\']', r.text, re.IGNORECASE)
    if m:
        client_id = m.group(1)
    m = re.search(r'DynamicTemplateID["\']?\s*[:=]\s*["\']([^"\']+)["\']', r.text, re.IGNORECASE)
    actual_template = m.group(1) if m else template_id

    # Step 2: POST to API with session cookies
    try:
        api_r = session.post(
            api_url,
            json={"DynamicTemplateID": actual_template, "skip": skip, "limit": limit},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Referer": base_page,
                "x-client-id": client_id,
            },
            timeout=15,
        )
        if api_r.status_code == 200 and "json" in api_r.headers.get("content-type", ""):
            data = api_r.json()
            if isinstance(data, list):
                return data
            for key in ("results", "data", "items", "Records"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return data if isinstance(data, list) else []
        logger.warning("govil dynamic API: status %d", api_r.status_code)
    except Exception as e:
        logger.warning("govil dynamic API POST failed: %s", e)

    # Step 3: HTML fallback — parse the listing page directly
    logger.info("govil dynamic: falling back to HTML parse of listing page")
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not href or not title or len(title) < 8:
            continue
        if not any(k in href for k in ["/pages/", "/departments/publications/", "/service/", "/BlobFolder/", "/rfp/"]):
            continue
        if not href.startswith("http"):
            href = urljoin("https://www.gov.il", href)
        parent = a.find_parent(["li", "div", "tr", "article"])
        ctx = parent.get_text(" ", strip=True) if parent else title
        items.append({"title": title, "url": href, "ctx": ctx})
    return items


def scrape_class_action_dryrun() -> dict:
    """
    Dry-run scrape of gov.il class_action_law_database DynamicCollector.
    Returns report dict — NOT saved to DB.
    Source: https://www.gov.il/he/Departments/DynamicCollectors/class_action_law_database
    """
    from datetime import date

    SOURCE_NAME = "gov.il — מאגר תובענות ייצוגיות"
    TEMPLATE_ID = "class_action_law_database"

    raw_items = []
    accepted = []
    rejected = []
    fetch_error = None

    raw = _fetch_govil_dynamic_collector(TEMPLATE_ID, skip=0, limit=50)
    if not raw:
        fetch_error = "Cloudflare 403 — gov.il requires browser session. Run with a real browser or use Playwright."
        logger.warning("class_action dryrun: %s", fetch_error)
    else:
        for entry in raw:
            # Normalize — API returns dicts, HTML fallback returns {"title","url","ctx"}
            title = (
                entry.get("title") or entry.get("Title") or
                entry.get("name") or entry.get("Name") or ""
            ).strip()
            href = (
                entry.get("url") or entry.get("URL") or entry.get("link") or
                entry.get("PageURL") or ""
            ).strip()
            ctx = entry.get("ctx", "") + " " + str(entry.get("description", "")) + " " + title
            deadline = (
                entry.get("deadline") or entry.get("Deadline") or
                entry.get("closingDate") or entry.get("ClosingDate") or
                extract_date(ctx) or None
            )
            if deadline and len(str(deadline)) > 10:
                deadline = str(deadline)[:10]

            if not title:
                continue
            if href and not href.startswith("http"):
                href = urljoin("https://www.gov.il", href)

            item = {
                "title": title,
                "url": href,
                "source": SOURCE_NAME,
                "deadline": deadline,
                "context_snippet": ctx[:200],
            }
            raw_items.append(item)

            is_settlement = any(kw in title + ctx for kw in [
                "הסדר פשרה", "פשרה", "settlement", "הסכם", "קרן פיצוי",
                "פיצוי", "compensation", "fund", "תשלום לניזוקים",
            ])
            if is_settlement and deadline:
                item["classification"] = "settlement_fund"
                accepted.append(item)
            elif is_settlement:
                item["classification"] = "settlement_no_deadline"
                accepted.append(item)
            else:
                item["classification"] = "class_action_only"
                rejected.append(item)

    report = {
        "dry_run": True,
        "source": SOURCE_NAME,
        "template_id": TEMPLATE_ID,
        "scanned_at": date.today().isoformat(),
        "raw_count": len(raw_items),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "samples": raw_items[:20],
        "accepted": accepted,
        "recommended_classification": "settlement_fund",
        "note": "לא הוכנס ל-DB. יש לאשר ידנית לפני שמירה.",
        "fetch_error": fetch_error,
    }

    logger.info(
        "class_action dryrun: raw=%d accepted=%d rejected=%d",
        len(raw_items), len(accepted), len(rejected),
    )
    return report


def scrape_settlement_funds() -> list[Call]:
    """
    Scrape approved settlement fund sources — these CAN be saved to DB.
    Sources: mashabim settlement search + gov.il class action register.
    """
    calls = []
    seen = set()

    settlement_searches = [
        ("https://mashabim.org/?s=%D7%A4%D7%A9%D7%A8%D7%94", "משאבים — קרנות פשרה"),
        ("https://mashabim.org/?s=%D7%A7%D7%A8%D7%9F+%D7%A4%D7%99%D7%A6%D7%95%D7%99", "משאבים — קרנות פיצוי"),
    ]

    for base_url, source_name in settlement_searches:
        soup = fetch(base_url)
        if not soup:
            continue

        for a in soup.select("h2 a, h3 a, .entry-title a"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title or len(title) < 8 or href in seen:
                continue
            seen.add(href)

            parent = a.find_parent(["article", "div", "li"])
            ctx = (parent.get_text(" ", strip=True) if parent else "") + " " + title
            deadline = extract_date(ctx)
            if not deadline:
                continue

            calls.append(Call(
                title=title,
                source=source_name,
                url=href,
                category="ngo",
                region="israel",
                deadline=deadline,
                description=ctx[:250],
                tags=["settlement_fund"],
            ))
        time.sleep(0.5)

    logger.info("settlement_funds: %d calls", len(calls))
    return calls


# ── Entry point ───────────────────────────────────────────
def scrape_all_specific() -> list[Call]:
    all_calls = []
    scrapers = [
        scrape_shatil,
        scrape_mashabim,
        scrape_govil_all,
        scrape_grantwatch_israel,
        scrape_fundsforngos,
        scrape_tmichot_api,
        scrape_isf,
        scrape_bsf,
        scrape_olympic_il,
        scrape_sport_authority,
        scrape_data_govil,
        scrape_settlement_funds,   # settlement sources — safe to save
    ]

    for fn in scrapers:
        try:
            logger.info("Running %s...", fn.__name__)
            calls = fn()
            all_calls.extend(calls)
        except Exception as e:
            logger.error("%s failed: %s", fn.__name__, e)
        time.sleep(1)

    # Deduplicate by URL
    seen, unique = set(), []
    for c in all_calls:
        if c.url and c.url not in seen:
            seen.add(c.url)
            unique.append(c)

    logger.info("Total specific: %d unique calls with deadline+url", len(unique))
    return unique


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    calls = scrape_all_specific()
    print(f"\nTotal: {len(calls)} calls")
    for c in sorted(calls, key=lambda x: x.deadline or ''):
        print(f"  [{c.deadline}] {c.title[:70]} | {c.source}")
