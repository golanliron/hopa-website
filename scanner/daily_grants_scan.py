"""
Hopa Daily Grants Scanner — v3.0
Scans ONLY actual open grant applications (קולות קוראים) with direct submission links.
NO foundation profiles, NO guidestar search links, NO generic pages.

Uploads to Goldfish DB (touqczopfjxcpmbxzdjr) opportunities table.

Runs daily via Task Scheduler at 07:00.
"""
import json
import re
import os
import sys
import uuid
import urllib3
import requests
import logging
from datetime import datetime, date
from pathlib import Path
from html import unescape
from urllib.parse import urlparse

# Fix encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

# File logging
LOG_DIR = Path(__file__).parent / "outputs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "scanner.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
logging.info("Scanner v3.0 started")

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Goldfish DB — THE target database
GOLDFISH_SUPABASE_URL = "https://touqczopfjxcpmbxzdjr.supabase.co"
GOLDFISH_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRvdXFjem9wZmp4Y3BtYnh6ZGpyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4OTAzNTcsImV4cCI6MjA5MzQ2NjM1N30.K16QAHB3IwRnHJl_XxtcWjnxzggF-Z3gtTrestlq-ek"

HEADERS_GOLDFISH = {
    "apikey": GOLDFISH_SUPABASE_KEY,
    "Authorization": f"Bearer {GOLDFISH_SUPABASE_KEY}",
    "Content-Type": "application/json",
}

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ============================================================
# UTILITIES
# ============================================================

def clean_html(text):
    """Remove HTML tags, scripts, styles and decode entities."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_date(text):
    """Try to extract a date from Hebrew text."""
    if not text:
        return None
    m = re.search(r'(\d{1,2})[./](\d{1,2})[./](20\d{2})', text)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    m = re.search(r'(20\d{2})-(\d{2})-(\d{2})', text)
    if m:
        return m.group(0)
    return None


def fetch(url, timeout=30):
    """Fetch URL with browser headers, SSL bypass."""
    try:
        resp = requests.get(url, headers=HEADERS_BROWSER, timeout=timeout, verify=False)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


# ============================================================
# AUTO-TAGGING — same patterns as org-dna.ts for consistent matching
# ============================================================

POPULATION_PATTERNS = [
    ('youth_at_risk', re.compile(r'נוער.{0,5}סיכון|צעירים.{0,5}סיכון|נשירה|נושרים|מנותקים')),
    ('youth', re.compile(r'נוער|בני נוער|נערים|נערות|תיכון')),
    ('young_adults', re.compile(r'צעירים|בוגרים צעירים|גיל 18|גיל 26|צעירי|דור צעיר')),
    ('children', re.compile(r'ילדים|ילדות|גן|יסודי|גיל הרך')),
    ('disabilities', re.compile(r'מוגבלות|מוגבלויות|נכות|נכים|שיקום|אוטיזם|אוטיסט|התפתחותי|מיוחד')),
    ('elderly', re.compile(r'קשישים|זקנים|גיל הזהב|גיל שלישי|סיעודי')),
    ('immigrants', re.compile(r'עולים|עלייה|קליטה|יוצאי אתיופיה|אתיופים')),
    ('arab', re.compile(r'ערבי|ערבים|בדואי|בדואים|דרוזי|מגזר ערבי|חברה ערבית')),
    ('haredi', re.compile(r'חרדי|חרדים|חרדית|אולטרא.?אורתודוקס')),
    ('women', re.compile(r'נשים|בנות|מגדר|פמיניז|אלמנות|חד הורי')),
    ('soldiers', re.compile(r'חיילים|משוחררים|צבא|צה"ל|שירות.{0,5}(לאומי|צבאי)|גיוס')),
    ('homeless', re.compile(r'חסרי בית|דרי רחוב|מחוסרי דיור')),
    ('addiction', re.compile(r'התמכרות|סמים|אלכוהול|גמילה')),
    ('lgbtq', re.compile(r'להט"?ב|גאווה|טרנס|הומו|לסבי')),
    ('refugees', re.compile(r'פליטים|מבקשי מקלט|מהגרים')),
    ('prisoners', re.compile(r'אסירים|כלואים|משוחררי כלא|שב"ס')),
]

DOMAIN_PATTERNS = [
    ('education', re.compile(r'חינוך|לימוד|הוראה|בית ספר|אקדמי|השכלה|מלגות|בגרות')),
    ('dropout_prevention', re.compile(r'נשירה|מניעת נשירה|נושרים|מנותקים|שימור')),
    ('welfare', re.compile(r'רווחה|סיוע|ליווי|העצמה|חוסן|שיקום חברתי')),
    ('employment', re.compile(r'תעסוקה|עבודה|הכשרה מקצועית|קריירה|יזמות|הכנסה')),
    ('health', re.compile(r'בריאות|רפואה|נפשי|טיפול|פסיכולוג|רפואי|קליני')),
    ('mental_health', re.compile(r'בריאות הנפש|נפשי|פסיכולוג|חרדה|דיכאון|טראומה')),
    ('culture', re.compile(r'תרבות|אמנות|מוזיקה|תיאטרון|קולנוע|ספרות|יצירה')),
    ('environment', re.compile(r'סביבה|אקולוגי|ירוק|קיימות|מיחזור|אקלים')),
    ('technology', re.compile(r'טכנולוגי|דיגיטל|הייטק|תוכנה|מחשב|סייבר|AI')),
    ('coexistence', re.compile(r'דו.?קיום|שותפות|ערבים.{0,5}יהודים|חברה משותפת')),
    ('sport', re.compile(r'ספורט|כדורגל|כדורסל|פעילות גופנית|אתלטיקה')),
    ('community', re.compile(r'קהילה|קהילתי|שכונה|מתנ"ס|מרכז קהילתי|חברתי')),
    ('social_innovation', re.compile(r'חדשנות חברתית|שינוי חברתי|מוביליות חברתית|אימפקט')),
    ('legal', re.compile(r'משפטי|זכויות|ייצוג|פרקליט|סיוע משפטי')),
]

GEO_PATTERNS = [
    ('negev', re.compile(r'נגב|באר שבע|ערד|דימונה|רהט|ירוחם|מצפה רמון')),
    ('galilee', re.compile(r'גליל|צפת|כרמיאל|עכו|נהריה|מעלות|קריית שמונה')),
    ('periphery', re.compile(r'פריפריה|שולי|מרוחק|עוטף|קו עימות|גבול')),
    ('center', re.compile(r'מרכז הארץ|תל אביב|גוש דן|רמת גן|פתח תקווה')),
    ('jerusalem', re.compile(r'ירושלים')),
    ('haifa', re.compile(r'חיפה|קריות')),
    ('national', re.compile(r'ארצי|ברחבי הארץ|כלל ארצי|פריסה ארצית')),
]


def auto_tag_grant(title, description="", page_text=""):
    """
    Auto-classify a grant using regex patterns matching org-dna.ts.
    Returns categories, target_populations, regions arrays.
    """
    full_text = f"{title} {description} {page_text}".lower()

    categories = [key for key, pat in DOMAIN_PATTERNS if pat.search(full_text)]
    target_populations = [key for key, pat in POPULATION_PATTERNS if pat.search(full_text)]
    regions = [key for key, pat in GEO_PATTERNS if pat.search(full_text)]

    return categories, target_populations, regions


def is_valid_grant_url(url):
    """
    Reject garbage URLs that are NOT direct links to specific grants.
    Returns True only if the URL looks like a direct link to a specific RFP.
    """
    if not url:
        return False

    # REJECT: guidestar search links
    if 'guidestar.org.il/search' in url:
        return False

    # REJECT: generic gov.il listing pages (not specific grant)
    if re.match(r'https?://www\.gov\.il/he/departments/dynamiccollectors/', url, re.IGNORECASE):
        return False

    # REJECT: generic foundation homepages (no path beyond domain)
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    if not path or path in ('he', 'en', 'home', 'index.html'):
        return False

    # REJECT: social media links that aren't specific posts
    if 'facebook.com' in url and '/posts/' not in url and '/permalink/' not in url:
        return False

    # REJECT: activetrail / newsletter tracking links
    if 'activetrail' in url.lower() or 'trailer.web-view' in url:
        return False

    # REJECT: PDF files that are not grant documents (privacy, regulations, reports)
    if url.lower().endswith('.pdf'):
        pdf_skip = ['privacy', 'פרטיות', 'regulations', 'תקנון', 'impact', 'אימפקט', 'report', 'דוח']
        if any(s in url.lower() for s in pdf_skip):
            return False

    # REJECT: generic about/impact/team/work pages (not specific grants)
    path_lower = parsed.path.lower()
    generic_paths = ['/impact', '/about', '/team', '/work/', '/עודעלינו', '/גישה/',
                     '/wp-content/uploads/website-privacy', '/impact_report/']
    if any(g in path_lower for g in generic_paths):
        return False

    return True


def is_actual_grant_title(title):
    """Reject titles that are clearly not grant applications."""
    if not title or len(title) < 8:
        return False
    # Reject navigation/UI text and generic page titles
    skip_exact = {
        'עמוד ראשי', 'דף הבית', 'צור קשר', 'אודות', 'חיפוש', 'הרשמה', 'התחברות',
        'מדיניות פרטיות', 'תנאי שימוש', 'דוח אימפקט', 'לכל הפרטים', 'לכתבה המלאה',
        'השקעות אימפקט', 'פילנתרופיה אסטרטגית', 'שיתופי פעולה בין-מגזריים',
        'שאלות ותשובות', 'أسئلة وأجوبة', 'دعوة لتقديم',
        'menu', 'search', 'home', 'about', 'privacy policy', 'contact',
    }
    title_stripped = title.strip(' >-–—')
    if title_stripped in skip_exact:
        return False

    skip_words = ['קישור', 'תאריך אחרון', 'מפרסם', 'למדריך', 'אין מכרזים',
                  'בשורות טובות', 'דף הבית', 'צור קשר', 'אודות', 'חיפוש',
                  'הרשמה', 'התחברות', 'מדיניות פרטיות', 'תנאי שימוש',
                  'menu', 'search', 'home', 'about', 'privacy']
    title_lower = title.lower()
    if any(sw in title_lower or sw in title for sw in skip_words):
        return False

    # Reject generic short labels (CTA buttons, nav links)
    if len(title) < 15 and not re.search(r'(?:קול|מענק|תמיכ|מכרז|פרס|מלג|הגש|תוכנית)', title):
        return False

    # Reject if title is too long (likely a description dumped as title)
    if len(title) > 200:
        return False
    return True


# ============================================================
# SCANNERS — Only sources that provide actual open RFPs
# ============================================================

def scan_shatil():
    """Shatil — direct links to specific grant pages."""
    results = []
    html = fetch("https://shatil.org.il/%D7%A7%D7%A8%D7%A0%D7%95%D7%AA-%D7%95%D7%A7%D7%95%D7%9C%D7%95%D7%AA-%D7%A7%D7%95%D7%A8%D7%90%D7%99%D7%9D/")
    if not html:
        return results

    pattern = r'href="(https?://shatil\.org\.il/kol/[^"]+)"[^>]*>.*?<h[2-4][^>]*>([^<]+)</h'
    matches = re.findall(pattern, html, re.DOTALL)

    date_pattern = r'href="(https?://shatil\.org\.il/kol/[^"]+)"[^>]*>.*?<p class="date__title[^"]*">([^<]*)</p>'
    date_matches = dict(re.findall(date_pattern, html, re.DOTALL))

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            deadline = extract_date(date_matches.get(link, ""))
            results.append({
                "title": title,
                "url": link,
                "deadline": deadline,
                "source": "shatil",
                "funder": "",
            })

    print(f"  [shatil] {len(results)} items")
    return results


def scan_gov_il_kolkore():
    """gov.il — extract SPECIFIC grant page URLs, not listing pages."""
    results = []
    # Try paginated URLs (skip=0,20,40...) — up to 200 items
    urls_to_try = [
        f"https://www.gov.il/he/Departments/DynamicCollectors/kolkore-list?skip={skip}"
        for skip in range(0, 200, 20)
    ] + ["https://www.gov.il/he/Departments/DynamicCollectors/kolkore-list"]
    html = None
    for url in urls_to_try:
        html = fetch(url)
        if html:
            break
    if not html:
        return results

    # gov.il embeds data in JSON script tags
    json_pattern = r'<script[^>]*type="application/json"[^>]*>(.*?)</script>'
    json_blocks = re.findall(json_pattern, html, re.DOTALL)

    for block in json_blocks:
        try:
            data = json.loads(block)
            items = []
            if isinstance(data, dict):
                for key in ["results", "items", "data", "content"]:
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        break
            elif isinstance(data, list):
                items = data

            for item in items:
                if not isinstance(item, dict):
                    continue
                title = item.get("Title", item.get("title", item.get("name", "")))
                url = item.get("Url", item.get("url", item.get("link", "")))

                # Make URL absolute if needed
                if url and not url.startswith("http"):
                    url = f"https://www.gov.il{url}"

                if title and len(title) > 5 and is_valid_grant_url(url) and is_actual_grant_title(title):
                    results.append({
                        "title": clean_html(title),
                        "url": url,
                        "deadline": extract_date(item.get("EndDate", item.get("deadline", ""))),
                        "description": clean_html(item.get("Description", item.get("description", "")))[:500],
                        "source": "gov_il",
                        "funder": item.get("Ministry", item.get("ministry", "")),
                    })
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: parse HTML for specific grant links (not listing pages)
    if not results:
        # Only match links to specific kolkore pages, not the listing itself
        pattern = r'<a[^>]*href="(/he/[^"]*kolkor[^"]*)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)
        for link, title in matches:
            full_url = f"https://www.gov.il{link}"
            title = clean_html(title)
            if title and len(title) > 10 and is_valid_grant_url(full_url) and is_actual_grant_title(title):
                results.append({
                    "title": title,
                    "url": full_url,
                    "source": "gov_il",
                    "funder": "",
                })

    print(f"  [gov.il] {len(results)} items")
    return results


def scan_innovation_authority():
    """Innovation Authority — specific grant pages."""
    results = []
    html = fetch("https://innovationisrael.org.il/kol-kore/")
    if not html:
        return results

    patterns = [
        r'<a[^>]*href="(https://innovationisrael\.org\.il/kol-kore/[^"]+)"[^>]*>.*?<h[2-4][^>]*>([^<]+)</h',
        r'href="(https://innovationisrael\.org\.il/kol-kore/[^"]+)"[^>]*title="([^"]+)"',
    ]

    matches = []
    for pat in patterns:
        matches = re.findall(pat, html, re.DOTALL)
        if matches:
            break

    if not matches:
        pattern = r'<a[^>]*href="(https://innovationisrael\.org\.il/kol-kore/[^"/]+/?)"[^>]*>(.*?)</a>'
        matches = [(l, clean_html(t)) for l, t in re.findall(pattern, html, re.DOTALL) if clean_html(t)]

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title,
                "url": link,
                "source": "innovation_authority",
                "funder": "רשות החדשנות",
            })

    print(f"  [innovation] {len(results)} items")
    return results


def scan_btl():
    """Bituach Leumi — specific grant links."""
    results = []
    html = fetch("https://www.btl.gov.il/Funds/kolotkorim/Pages/default.aspx")
    if not html:
        return results

    pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*(?:קול|מענק|תמיכ|קרן)[^<]*)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if not link.startswith("http"):
            link = f"https://www.btl.gov.il{link}"
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title,
                "url": link,
                "source": "btl",
                "funder": "ביטוח לאומי",
            })

    print(f"  [btl] {len(results)} items")
    return results


def scan_kkl():
    """KKL — specific call for proposals."""
    results = []
    html = fetch("https://www.kkl.org.il/about-us/tenders/call-for-proposals/")
    if not html:
        return results

    pattern = r'<a[^>]*href="(https://www\.kkl\.org\.il/about-us/tenders/call-for-proposals/[^"]+)"[^>]*>(.*?)</a>'
    matches = re.findall(pattern, html, re.DOTALL)

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title,
                "url": link,
                "source": "kkl",
                "funder": "קק\"ל",
            })

    print(f"  [kkl] {len(results)} items")
    return results


def scan_gov_ministry(url, source_name, funder_name):
    """Scan a gov.il ministry page for specific grant links (not listing pages)."""
    results = []
    html = fetch(url)
    if not html:
        return results

    keywords = r'(?:קול|תמיכ|מענק|תכנית|הזמנה|הגש|סיוע)'
    pattern = rf'<a[^>]*href="([^"]*)"[^>]*>([^<]*{keywords}[^<]*)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if not link.startswith("http"):
            link = f"https://www.gov.il{link}"
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title,
                "url": link,
                "source": source_name,
                "funder": funder_name,
            })

    return results


def scan_gov_ministries():
    """Scan government ministry pages for specific grants."""
    all_results = []

    sources = [
        ("https://mop.education/open-call/", "mop_education", "משרד החינוך — מו\"פ"),
        ("https://www.gov.il/he/pages/support-tests-associations", "gov_welfare", "משרד הרווחה"),
        ("https://www.gov.il/he/pages/ministry_support", "gov_culture", "משרד התרבות"),
        ("https://www.gov.il/he/departments/units/sport_support_unit", "gov_sport", "משרד התרבות — ספורט"),
        ("https://pob.education.gov.il/kolotkorim/kolkore/", "pob_education", "משרד החינוך — פו\"ב"),
        ("https://tmichot.mof.gov.il/call-for-proposals/", "mof_tmichot", "משרד האוצר — תמיכות"),
        ("https://edu-tech.education.gov.il/taknot/kol-kore/", "edu_tech", "משרד החינוך — טכנולוגיות"),
        ("https://www.hityashvut.org.il/קולות-קוראים/", "hityashvut", "החטיבה להתיישבות"),
        ("https://govextra.gov.il/tnufa/tenufa-letzfon/home/kolot-koraim/", "tnufa_letzfon", "תנופה לצפון"),
        ("https://www.pmi.com/markets/israel/he/sustainability/contributions", "pmi_israel", "Philip Morris Israel — CSR"),
        ("https://www.ezvonot.com/ועדת-העזבונות/", "ezvonot", "ועדת העיזבונות — משרד המשפטים"),
        ("https://elitzur.org.il/קולות-קוראים/", "elitzur", "אליצור — ספורט ועמותות"),
        ("https://www.kshalem.org.il/קול-קורא/", "kshalem", "קרן שלם — מוגבלויות"),
        ("https://www.gov.il/he/pages/tmichot_mosdot_tzibur", "gov_aliya", "משרד העלייה והקליטה"),
        ("https://govextra.gov.il/minisite-new/tkuma-zmani/home/tenders-new/", "tkuma", "תקומה — שיקום העוטף"),
        ("https://www.gov.il/he/departments/ministry_of_energy/govil-landing-page", "gov_energy", "משרד האנרגיה והתשתיות"),
        ("https://www.gov.il/he/departments/ministry_of_negev_galilee_and_national_resilience/govil-landing-page", "gov_negev_galil", "משרד הנגב, הגליל והחוסן הלאומי"),
        ("https://www.gov.il/he/departments/foreign_affairs_ministry/govil-landing-page", "gov_foreign", "משרד החוץ"),
        ("https://app.vendors.co.il/jewishagency/michrazim", "jewish_agency_vendors", "הסוכנות היהודית"),
    ]

    for url, source_name, funder in sources:
        items = scan_gov_ministry(url, source_name, funder)
        all_results.extend(items)
        if items:
            print(f"  [{source_name}] {len(items)} items")

    return all_results


def scan_pais():
    """Mifal HaPais — specific grant/culture program links."""
    results = []
    html = fetch("https://culture.pais.co.il/")
    if not html:
        return results

    keywords = r'(?:קול|תמיכ|מענק|הגש|תכנית)'
    pattern = rf'<a[^>]*href="([^"]+)"[^>]*>([^<]*{keywords}[^<]*)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if not link.startswith("http"):
            link = f"https://culture.pais.co.il{link}"
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title,
                "url": link,
                "source": "pais",
                "funder": "מפעל הפיס",
            })

    print(f"  [pais] {len(results)} items")
    return results


def scan_estates_committee():
    """Vadat Azbonot — specific grant links."""
    results = []
    html = fetch("https://www.gov.il/he/departments/topics/allowance_from_the_estates_committee/govil-landing-page")
    if not html:
        return results

    keywords = r'(?:קול|תמיכ|מענק|הגש|הקצ|עזבונות)'
    pattern = rf'<a[^>]*href="([^"]*)"[^>]*>([^<]*{keywords}[^<]*)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)

    seen = set()
    for link, title in matches:
        title = clean_html(title)
        if not link.startswith("http"):
            link = f"https://www.gov.il{link}"
        if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title,
                "url": link,
                "source": "estates_committee",
                "funder": "ועדת העזבונות",
            })

    print(f"  [estates] {len(results)} items")
    return results


def scan_grants_gov():
    """
    Grants.gov API — US federal grants open to Israeli NGOs.
    Filters: USAID, State Dept, education/welfare programs eligible for international orgs.
    API docs: https://www.grants.gov/web/grants/s2s/grantor/showApplicantTypes.html
    """
    results = []
    try:
        # Search for grants relevant to Israel / international nonprofits
        search_terms = ["israel", "middle east youth", "education nonprofit international"]
        seen = set()

        for term in search_terms:
            api_url = f"https://api.grants.gov/v2/api/opportunities/search?keyword={requests.utils.quote(term)}&oppStatuses=posted&rows=20&sortBy=openDate%7Cdesc"
            resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=20)
            if resp.status_code != 200:
                continue
            data = resp.json()
            opportunities = data.get("data", {}).get("oppHits", []) or []
            for opp in opportunities:
                title = opp.get("title", "")
                opp_id = opp.get("id", "")
                if not title or opp_id in seen:
                    continue
                seen.add(opp_id)
                url = f"https://www.grants.gov/search-results-detail/{opp_id}"
                close_date = opp.get("closeDate", "")
                deadline = None
                if close_date:
                    try:
                        dt = datetime.strptime(close_date[:10], "%m/%d/%Y")
                        deadline = dt.strftime("%Y-%m-%d")
                    except Exception:
                        deadline = extract_date(close_date)

                agency = opp.get("agencyName", "") or opp.get("owningAgencyName", "")
                results.append({
                    "title": title[:300],
                    "url": url,
                    "deadline": deadline,
                    "source": "grants_gov",
                    "funder": f"Grants.gov — {agency}" if agency else "Grants.gov",
                    "description": (opp.get("synopsis", "") or "")[:500],
                })
    except Exception as e:
        print(f"  [grants.gov] Error: {e}")

    print(f"  [grants.gov] {len(results)} items")
    return results


def scan_jfn():
    """
    Jewish Funders Network — grants and RFPs from Jewish philanthropic foundations.
    Many fund Israel-based nonprofits. https://www.jfunders.org
    """
    results = []
    urls_to_try = [
        "https://www.jfunders.org/grants",
        "https://www.jfunders.org/rfps",
        "https://www.jfunders.org/funding-opportunities",
    ]

    for url in urls_to_try:
        html = fetch(url)
        if not html:
            continue

        # Look for grant links and titles
        patterns = [
            r'<a[^>]*href="(https?://(?:www\.)?jfunders\.org/[^"]*(?:grant|rfp|fund)[^"]*)"[^>]*>(.*?)</a>',
            r'<h[2-4][^>]*><a[^>]*href="([^"]+)"[^>]*>([^<]+)</a></h[2-4]>',
            r'<a[^>]*href="([^"]+)"[^>]*class="[^"]*(?:title|heading|link)[^"]*"[^>]*>([^<]+)</a>',
        ]

        seen = set()
        for pat in patterns:
            matches = re.findall(pat, html, re.DOTALL | re.IGNORECASE)
            for link, title in matches:
                title = clean_html(title).strip()
                if not link.startswith("http"):
                    link = f"https://www.jfunders.org{link}"
                if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
                    seen.add(link)
                    results.append({
                        "title": title[:300],
                        "url": link,
                        "source": "jfn",
                        "funder": "Jewish Funders Network",
                    })
        if results:
            break

    # If no structured links, try extracting from listing text
    if not results:
        html = fetch("https://www.jfunders.org/grants") or ""
        # Extract any external grant links on the page
        ext_pattern = r'<a[^>]*href="(https?://(?!jfunders)[^"]+)"[^>]*>([^<]{15,150})</a>'
        for link, title in re.findall(ext_pattern, html, re.IGNORECASE):
            title = clean_html(title).strip()
            if is_actual_grant_title(title) and is_valid_grant_url(link):
                results.append({
                    "title": title[:300],
                    "url": link,
                    "source": "jfn",
                    "funder": "Jewish Funders Network",
                })

    print(f"  [jfn] {len(results)} items")
    return results


def scan_municipal():
    """
    Israeli municipal councils — Tel Aviv, Jerusalem, Haifa, Beer Sheva.
    Each city publishes its own grant calls for local NGOs.
    """
    results = []

    cities = [
        {
            "name": "עיריית תל אביב",
            "urls": [
                "https://www.tel-aviv.gov.il/Residents/SocialServices/Pages/Callsforproposal.aspx",
                "https://www.tel-aviv.gov.il/Residents/SocialServices/Pages/Grants.aspx",
            ],
            "source": "municipal_tlv",
            "base": "https://www.tel-aviv.gov.il",
        },
        {
            "name": "עיריית ירושלים",
            "urls": [
                "https://www.jerusalem.muni.il/he/city/tenders/kolkore/",
                "https://www.jerusalem.muni.il/he/residents/socialwelfare/",
                "https://www.jerusalem.muni.il/he/business/tenders/",
            ],
            "source": "municipal_jlm",
            "base": "https://www.jerusalem.muni.il",
        },
        {
            "name": "עיריית חיפה",
            "urls": [
                "https://www.haifa.muni.il/residents/welfare/",
                "https://www.haifa.muni.il/business/tenders/",
            ],
            "source": "municipal_haifa",
            "base": "https://www.haifa.muni.il",
        },
        {
            "name": "עיריית באר שבע",
            "urls": [
                "https://www.beersheva.muni.il/Residents/SocialServices/",
                "https://www.beersheva.muni.il/BusinessCenter/Tenders/",
            ],
            "source": "municipal_bs",
            "base": "https://www.beersheva.muni.il",
        },
    ]

    keywords = r'(?:קול|תמיכ|מענק|הגש|תכנית|סיוע|מכרז)'
    seen = set()

    for city in cities:
        city_results = []
        for url in city["urls"]:
            html = fetch(url)
            if not html:
                continue

            pattern = rf'<a[^>]*href="([^"]*)"[^>]*>([^<]*{keywords}[^<]*)</a>'
            matches = re.findall(pattern, html, re.IGNORECASE)
            for link, title in matches:
                title = clean_html(title).strip()
                if not link.startswith("http"):
                    link = city["base"] + ("" if link.startswith("/") else "/") + link.lstrip("/")
                if title and link not in seen and is_actual_grant_title(title) and is_valid_grant_url(link):
                    seen.add(link)
                    city_results.append({
                        "title": title[:300],
                        "url": link,
                        "source": city["source"],
                        "funder": city["name"],
                    })

        if city_results:
            print(f"  [{city['source']}] {len(city_results)} items from {city['name']}")
        results.extend(city_results)

    print(f"  [municipal] {len(results)} total items")
    return results


def scan_candid():
    """
    Candid.org (Foundation Directory) — search for grants available to Israel-based orgs.
    Uses public search API / HTML scraping with Israel-specific filters.
    https://candid.org
    """
    results = []

    search_urls = [
        "https://candid.org/explore-issues/grants?subject=Education&recipient-country=Israel",
        "https://candid.org/find-funding/search?q=israel+youth&type=grants",
    ]

    for url in search_urls:
        html = fetch(url)
        if not html:
            continue

        # Try structured data first (JSON-LD or embedded JSON)
        json_pattern = r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>'
        for block in re.findall(json_pattern, html, re.DOTALL):
            try:
                data = json.loads(block)
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    for k in ["itemListElement", "results", "grants", "data"]:
                        if k in data:
                            items = data[k] if isinstance(data[k], list) else []
                            break

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("name", item.get("title", ""))
                    link = item.get("url", item.get("@id", ""))
                    if title and link and is_actual_grant_title(title) and is_valid_grant_url(link):
                        results.append({
                            "title": clean_html(title)[:300],
                            "url": link,
                            "source": "candid",
                            "funder": item.get("funder", {}).get("name", "Candid") if isinstance(item.get("funder"), dict) else "Candid",
                            "description": clean_html(item.get("description", ""))[:500],
                        })
            except Exception:
                continue

        # Fallback: scrape links
        if not results:
            pat = r'<a[^>]*href="(https?://candid\.org/[^"]*(?:grant|fund|opport)[^"]*)"[^>]*>([^<]{10,150})</a>'
            for link, title in re.findall(pat, html, re.IGNORECASE):
                title = clean_html(title).strip()
                if is_actual_grant_title(title) and is_valid_grant_url(link):
                    results.append({
                        "title": title[:300],
                        "url": link,
                        "source": "candid",
                        "funder": "Candid",
                    })

    print(f"  [candid] {len(results)} items")
    return results


def scan_gov_il_mevhanim():
    """
    gov.il DynamicCollector — קולות קוראים ותמיכות (test-servies).
    Uses Playwright + API intercept to bypass Cloudflare.
    TemplateID: fcd8e430-95c9-4e06-b66f-ad2d4e143a50
    """
    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [gov_mevhanim] playwright not installed — skipping")
        logging.warning("gov_mevhanim: playwright not installed")
        return results

    import time as _time

    captured = []

    def on_response(response):
        if 'api/DynamicCollector' in response.url:
            try:
                d = response.json()
                items = d.get('Results', [])
                captured.extend(items)
            except Exception:
                pass

    # kolkore-list = all open RFPs across all ministries
    BASE_URL = 'https://www.gov.il/he/Departments/DynamicCollectors/kolkore-list?skip={skip}'
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for skip in range(0, 600, 20):
                page = browser.new_page(locale='he-IL', user_agent=UA)
                page.on('response', on_response)
                try:
                    page.goto(BASE_URL.format(skip=skip), wait_until='networkidle', timeout=40000)
                    _time.sleep(0.5)
                except Exception:
                    pass
                page.close()
                if skip > 0 and len(captured) % 20 != 0:
                    # reached last page
                    break
            browser.close()
    except Exception as e:
        print(f"  [gov_mevhanim] Playwright error: {e}")
        logging.error(f"gov_mevhanim playwright error: {e}")
        return results

    # Process captured items
    today = date.today()
    seen_ids = set()
    for item in captured:
        item_id = item.get('ItemId') or item.get('Id') or ''
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        title = clean_html(item.get('Title') or item.get('DisplayName') or '')
        if not title or not is_actual_grant_title(title):
            continue

        # Build URL
        url_path = item.get('UrlPath') or item.get('Url') or ''
        if url_path and not url_path.startswith('http'):
            url = f"https://www.gov.il{url_path}" if url_path.startswith('/') else f"https://www.gov.il/he/{url_path}"
        elif url_path:
            url = url_path
        else:
            # Fallback: direct gov.il page link
            slug = item.get('Slug') or item.get('ItemSlug') or item_id
            if not slug:
                continue
            url = f"https://www.gov.il/he/Departments/DynamicCollectors/test-servies/{slug}"

        if not is_valid_grant_url(url):
            # Allow gov.il specific pages (override the listing-page rejection for direct items)
            if not url.startswith('https://www.gov.il'):
                continue

        # Deadline
        deadline_str = (
            item.get('ToDateHeb') or item.get('ToDate') or
            item.get('SubmissionDeadline') or item.get('EndDate') or ''
        )
        deadline = extract_date(str(deadline_str)) if deadline_str else None

        # Filter out very old items (before 2024)
        if deadline and deadline < '2024-01-01':
            continue

        # Description
        description = clean_html(
            item.get('ShortDescription') or item.get('Description') or
            item.get('Abstract') or ''
        )[:500]

        # Funder = ministry
        funder = clean_html(
            item.get('ProgramOwner') or item.get('Ministry') or
            item.get('DepartmentTitle') or ''
        )

        # PDF links
        pdf_links = []
        for att in item.get('Attachments') or []:
            att_url = att.get('Url') or att.get('AttachmentUrl') or ''
            if att_url and '.pdf' in att_url.lower():
                if not att_url.startswith('http'):
                    att_url = 'https://www.gov.il' + att_url
                pdf_links.append(att_url)

        # Add PDF to description
        if pdf_links:
            description = (description + ' | PDF: ' + ' , '.join(pdf_links[:3]))[:1000]

        results.append({
            'title': title,
            'url': url,
            'deadline': deadline,
            'source': 'gov_mevhanim',
            'funder': funder or None,
            'description': description or None,
        })

    print(f"  [gov_mevhanim] {len(captured)} raw items → {len(results)} valid")
    logging.info(f"gov_mevhanim: {len(captured)} raw → {len(results)} valid")
    return results


def scan_data_gov_il():
    """
    data.gov.il open API — scan known resource IDs for active grant calls.
    Requires User-Agent: datagov-external-client
    Supports filters: {"field": ["val1","val2"]} and fields selection.
    Also auto-discovers new datasets via package_search.
    """
    results = []

    DATAGOV_HEADERS = {
        "User-Agent": "datagov-external-client",
        "Accept": "application/json",
    }

    def datagov_search(q, rows=20):
        """Search for datasets by keyword, return list of (title, resource_id, funder)."""
        found = []
        try:
            resp = requests.get(
                "https://data.gov.il/api/3/action/package_search",
                params={"q": q, "rows": rows},
                headers=DATAGOV_HEADERS,
                timeout=20,
                verify=False,
            )
            if resp.status_code != 200:
                return found
            data = resp.json()
            for pkg in data.get("result", {}).get("results", []):
                org = pkg.get("organization", {}).get("title", "") if isinstance(pkg.get("organization"), dict) else ""
                for res in pkg.get("resources", []):
                    if res.get("datastore_active"):
                        found.append((pkg.get("title",""), res["id"], org))
        except Exception:
            pass
        return found

    # Known resource IDs for grant-related datasets
    RESOURCES = [
        {
            "resource_id": "347114f1-1bd7-49b3-848a-582efc46f888",
            "name": "קולות קוראים — משרד המדע והטכנולוגיה",
            "funder": "משרד החדשנות, המדע והטכנולוגיה",
            "title_field": "נושא המחקר",
            "url_field": None,
            "deadline_field": "תאריך סיום הסכם",
            "filters": {"סטטוס": ["פעיל", "active"]},
        },
    ]

    for res in RESOURCES:
        try:
            params = {
                "resource_id": res["resource_id"],
                "limit": 100,
                "offset": 0,
            }
            if res.get("filters"):
                import json as _json
                params["filters"] = _json.dumps(res["filters"], ensure_ascii=False)

            resp = requests.get(
                "https://data.gov.il/api/3/action/datastore_search",
                params=params,
                headers=DATAGOV_HEADERS,
                timeout=30,
                verify=False,
            )
            if resp.status_code != 200:
                print(f"  [datagov] {res['name']} → HTTP {resp.status_code}")
                continue

            data = resp.json()
            records = data.get("result", {}).get("records", [])

            for rec in records:
                title_field = res.get("title_field", "title")
                title = str(rec.get(title_field, "")).strip()
                if not title or not is_actual_grant_title(title):
                    continue

                deadline = None
                if res.get("deadline_field"):
                    deadline = extract_date(str(rec.get(res["deadline_field"], "")))

                url = None
                if res.get("url_field"):
                    url = str(rec.get(res["url_field"], "")).strip() or None

                results.append({
                    "title": title[:300],
                    "url": url or f"https://data.gov.il/dataset/{res['resource_id']}",
                    "deadline": deadline,
                    "source": "datagov_il",
                    "funder": res["funder"],
                    "description": str(rec.get("תכנית מימון", rec.get("תחום קול קורא", "")))[:500] or None,
                })

            print(f"  [datagov] {res['name']} → {len(records)} records")

        except Exception as e:
            print(f"  [datagov] {res.get('name','?')} error: {e}")
            logging.error(f"datagov error {res.get('resource_id')}: {e}")

    print(f"  [datagov] total {len(results)} items")
    return results


def scan_menomadin():
    """Menomadin Foundation — prizes and grants for social resilience."""
    results = []
    urls = [
        "https://menomadinfoundation.com/he/",
        "https://menomadinfoundation.com/he/פרס-טייב-לחוסן-לאומי/",
    ]
    for url in urls:
        html = fetch(url)
        if not html:
            continue
        pattern = r'<a[^>]*href="(https://menomadinfoundation\.com/[^"]+)"[^>]*>(.*?)</a>'
        for link, title in re.findall(pattern, html, re.DOTALL):
            title = clean_html(title).strip()
            if title and len(title) > 8 and is_actual_grant_title(title) and is_valid_grant_url(link):
                results.append({
                    "title": title[:300],
                    "url": link,
                    "source": "menomadin",
                    "funder": "Menomadin Foundation",
                })
    print(f"  [menomadin] {len(results)} items")
    return results


def scan_missfixtheuniverse():
    """Miss Fix the Universe — grants for women's employment & financial independence."""
    results = []
    html = fetch("https://missfixtheuniverse.com")
    if not html:
        return results
    keywords = r'(?:קול|מענק|הגש|מועמד|תמיכ)'
    pattern = rf'<a[^>]*href="([^"]+)"[^>]*>([^<]*{keywords}[^<]*)</a>'
    for link, title in re.findall(pattern, html, re.IGNORECASE):
        title = clean_html(title).strip()
        if not link.startswith("http"):
            link = f"https://missfixtheuniverse.com{link}"
        if title and is_actual_grant_title(title) and is_valid_grant_url(link):
            results.append({
                "title": title[:300],
                "url": link,
                "source": "missfixtheuniverse",
                "funder": "שדולת הנשים / בנק הפועלים — Miss Fix the Universe",
            })
    print(f"  [missfixtheuniverse] {len(results)} items")
    return results


def scan_mr_gov_il():
    """mr.gov.il — Israeli government procurement / RFP portal.
    ONLY scrape the KOLOT-KORIM category (actual calls for proposals, not procurement/tenders).
    Filter out equipment, construction, consulting, and other non-grant items.
    """
    results = []
    html = fetch("https://mr.gov.il/ilgstorefront/he/c/KOLOT-KORIM")
    if not html:
        print("  [mr_gov_il] fetch failed")
        return results

    pattern = r'<a[^>]*href="(/ilgstorefront/he/p/[^"]+)"[^>]*>(.*?)</a>'
    seen = set()
    # Reject procurement/equipment/construction items
    reject_kw = ['אספקת', 'התקנת', 'שאיבה', 'קידוח', 'מיזוג', 'חשמל', 'ביטוח',
                 'תחבורה', 'הסעה', 'ניקיון', 'שמירה', 'כביסה', 'ריהוט', 'מזון',
                 'דלק', 'רכב', 'תקשורת', 'מחשוב', 'דפוס', 'פרסום', 'הסברה',
                 'כנסייה', 'פטנט', 'דוזימטריה', 'CUBESAT', 'ARTEMIS']
    for link, title in re.findall(pattern, html, re.DOTALL):
        title = clean_html(title).strip()
        full_url = f"https://mr.gov.il{link}"
        if not title or full_url in seen or len(title) < 8:
            continue
        if any(kw in title for kw in reject_kw):
            continue
        if not is_actual_grant_title(title):
            continue
        seen.add(full_url)
        results.append({
            "title": title[:300],
            "url": full_url,
            "source": "mr_gov_il",
            "funder": "מרכז רכש ממשלתי",
        })
    print(f"  [mr_gov_il] {len(results)} items")
    return results


def scan_keren_yozmot():
    """Keren Yozmot — annual call for educational innovation projects."""
    results = []
    html = fetch("https://www.keren-yozmot.org.il/kolkore/")
    if not html:
        return results
    pattern = r'<a[^>]*href="(https?://(?:www\.)?keren-yozmot\.org\.il/[^"]+)"[^>]*>(.*?)</a>'
    seen = set()
    for link, title in re.findall(pattern, html, re.DOTALL):
        title = clean_html(title).strip()
        if title and link not in seen and len(title) > 8 and is_actual_grant_title(title) and is_valid_grant_url(link):
            seen.add(link)
            results.append({
                "title": title[:300],
                "url": link,
                "source": "keren_yozmot",
                "funder": "הקרן לעידוד יוזמות חינוכיות / משרד החינוך",
            })
    # If no links found, add the main page as a grant
    if not results:
        results.append({
            "title": "קול קורא — המקום ליזמות חינוכית",
            "url": "https://www.keren-yozmot.org.il/kolkore/",
            "source": "keren_yozmot",
            "funder": "הקרן לעידוד יוזמות חינוכיות / משרד החינוך",
        })
    print(f"  [keren_yozmot] {len(results)} items")
    return results


def scan_negev_galil():
    """Reshut HaNegev + Reshut HaGalil — regional calls for proposals."""
    results = []
    sources = [
        ("https://www.negev.co.il/kolot-korim/", "negev_authority", "הרשות לפיתוח הנגב", "https://www.negev.co.il"),
        ("https://www.galil.co.il/kolot-korim/", "galil_authority", "הרשות לפיתוח הגליל", "https://www.galil.co.il"),
        ("https://www.gov.il/he/departments/ministry_of_negev_galilee_and_national_resilience", "negev_galil_ministry", "משרד הנגב, הגליל והחוסן הלאומי", "https://www.gov.il"),
    ]
    seen = set()
    for url, source_name, funder, base in sources:
        html = fetch(url)
        if not html:
            continue
        pattern = r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        for link, title in re.findall(pattern, html, re.DOTALL):
            title = clean_html(title).strip()
            if not link.startswith("http"):
                link = base + ("" if link.startswith("/") else "/") + link.lstrip("/")
            if title and link not in seen and len(title) > 8 and is_actual_grant_title(title) and is_valid_grant_url(link):
                seen.add(link)
                results.append({
                    "title": title[:300],
                    "url": link,
                    "source": source_name,
                    "funder": funder,
                })
    print(f"  [negev_galil] {len(results)} items")
    return results


def scan_israeli_foundations():
    """Scan Israeli private foundations for open calls / grant applications."""
    results = []
    foundations = [
        {
            "url": "https://www.agfund.co.il/",
            "source": "agfund",
            "funder": "קרן אהרון גוטווירט",
            "base": "https://www.agfund.co.il",
        },
        {
            "url": "https://www.kassirer.org.il/",
            "source": "kassirer",
            "funder": "קרן קסירר",
            "base": "https://www.kassirer.org.il",
        },
        {
            "url": "https://rfrn.org.il/",
            "source": "rothschild_edrf",
            "funder": "קרן אדמונד דה רוטשילד",
            "base": "https://rfrn.org.il",
        },
        {
            "url": "https://www.sacta-rashi.org.il/",
            "source": "sacta_rashi",
            "funder": "קרן סאקטא-רשי",
            "base": "https://www.sacta-rashi.org.il",
        },
        {
            "url": "https://yadhanadiv.org.il/grants/",
            "source": "yad_hanadiv",
            "funder": "קרן יד הנדיב (רוטשילד)",
            "base": "https://yadhanadiv.org.il",
        },
        {
            "url": "https://www.alonfoundation.org.il/",
            "source": "alon_foundation",
            "funder": "קרן אלון",
            "base": "https://www.alonfoundation.org.il",
        },
        {
            "url": "https://www.lautmanfund.org.il/",
            "source": "lautman",
            "funder": "קרן דב לאוטמן",
            "base": "https://www.lautmanfund.org.il",
        },
        {
            "url": "https://www.pfrp.co.il/",
            "source": "mifal_hapais_keren",
            "funder": "קרן מפעל הפיס",
            "base": "https://www.pfrp.co.il",
        },
        {
            "url": "https://clore-foundation.org.il/",
            "source": "clore",
            "funder": "Clore Israel Foundation",
            "base": "https://clore-foundation.org.il",
        },
        {
            "url": "https://www.boxenbaum.org.il/",
            "source": "boxenbaum",
            "funder": "קרן בוקסנבאום נטע",
            "base": "https://www.boxenbaum.org.il",
        },
    ]

    grant_keywords = re.compile(r'קול.?קורא|מענק|הגש|מכרז|תמיכ|מלג|הזמנ|פרויקט|שותפות|RFP|grant|proposal|apply', re.IGNORECASE)

    for f in foundations:
        html = fetch(f["url"])
        if not html:
            continue
        pattern = r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        seen = set()
        for link, title in re.findall(pattern, html, re.DOTALL):
            title = clean_html(title).strip()
            if not link.startswith("http"):
                link = f["base"] + ("" if link.startswith("/") else "/") + link.lstrip("/")
            if not title or len(title) < 8 or link in seen:
                continue
            # Only grab links that look like grants
            if not grant_keywords.search(title) and not grant_keywords.search(link):
                continue
            if not is_actual_grant_title(title) or not is_valid_grant_url(link):
                continue
            seen.add(link)
            results.append({
                "title": title[:300],
                "url": link,
                "source": f["source"],
                "funder": f["funder"],
            })
    print(f"  [israeli_foundations] {len(results)} items from {len(foundations)} foundations")
    return results


def scan_intl_foundations():
    """Scan international foundations relevant to Israel education/youth."""
    results = []
    sources = [
        {
            "url": "https://seedthedream.org/",
            "source": "seed_the_dream",
            "funder": "Seed the Dream Foundation",
            "base": "https://seedthedream.org",
        },
        {
            "url": "https://avichai.org/",
            "source": "avi_chai",
            "funder": "AVI CHAI Foundation",
            "base": "https://avichai.org",
        },
        {
            "url": "https://vanleerfoundation.org/",
            "source": "van_leer",
            "funder": "Bernard van Leer Foundation",
            "base": "https://vanleerfoundation.org",
        },
        {
            "url": "https://fundforwomen.loreal.com/",
            "source": "loreal_women",
            "funder": "L'Oréal Fund for Women",
            "base": "https://fundforwomen.loreal.com",
        },
        {
            "url": "https://www.schusterman.org/grants",
            "source": "schusterman",
            "funder": "Schusterman Family Philanthropies",
            "base": "https://www.schusterman.org",
        },
    ]

    grant_keywords = re.compile(r'grant|RFP|proposal|apply|call|fund|opportunity|קול|מענק|הגש', re.IGNORECASE)

    for f in sources:
        html = fetch(f["url"])
        if not html:
            continue
        pattern = r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        seen = set()
        for link, title in re.findall(pattern, html, re.DOTALL):
            title = clean_html(title).strip()
            if not link.startswith("http"):
                link = f["base"] + ("" if link.startswith("/") else "/") + link.lstrip("/")
            if not title or len(title) < 8 or link in seen:
                continue
            if not grant_keywords.search(title) and not grant_keywords.search(link):
                continue
            if not is_actual_grant_title(title) or not is_valid_grant_url(link):
                continue
            seen.add(link)
            results.append({
                "title": title[:300],
                "url": link,
                "source": f["source"],
                "funder": f["funder"],
            })
    print(f"  [intl_foundations] {len(results)} items from {len(sources)} foundations")
    return results


def scan_tamir_newsletter():
    """Parse Tamir Sharabi's weekly newsletter cached locally."""
    results = []
    cache_file = OUTPUT_DIR / "tamir_latest.txt"

    if not cache_file.exists():
        print("  [tamir] No cache file found.")
        return results

    text = cache_file.read_text(encoding="utf-8")
    if not text.strip():
        return results

    lines = text.split('\n')
    current_funder = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if any(kw in line for kw in ['משרד', 'קרן', 'רשות', 'הסוכנות', 'ועדת']):
            if len(line) < 60 and not any(kw in line for kw in ['קישור', 'תאריך', 'להגשה']):
                current_funder = line
                i += 1
                continue

        if line and len(line) > 10 and 'קישור' not in line and 'תאריך' not in line:
            deadline = None
            url = None
            title_candidate = line

            for j in range(1, min(5, len(lines) - i)):
                next_line = lines[i + j].strip() if i + j < len(lines) else ""
                if not deadline:
                    d = extract_date(next_line)
                    if d:
                        deadline = d
                if not url and 'http' in next_line:
                    url_match = re.search(r'https?://[^\s<"]+', next_line)
                    if url_match:
                        url = url_match.group(0)

            # Only add if URL is valid and title is real
            if url and is_valid_grant_url(url) and is_actual_grant_title(title_candidate):
                results.append({
                    "title": title_candidate[:300],
                    "url": url,
                    "deadline": deadline,
                    "source": "tamir_newsletter",
                    "funder": current_funder or None,
                })

        i += 1

    # Deduplicate by title
    seen = set()
    unique = []
    for r in results:
        if r["title"] not in seen:
            seen.add(r["title"])
            unique.append(r)

    print(f"  [tamir] {len(unique)} items")
    return unique


# ============================================================
# ENRICHMENT — Get details from actual grant page
# ============================================================

PHONE_RE = re.compile(r'(?:טלפון|טל|phone|tel)[\s:]*([0-9\-\s\(\)]{7,15})|(?<!\d)(0[2-9]\d?[\-\s]?\d{3}[\-\s]?\d{4})(?!\d)')
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
SKIP_EMAILS = {'example@example.com', 'info@info.com', 'test@test.com'}


def extract_contact_info(text):
    """Extract phone numbers and emails from page text."""
    phones = []
    for m in PHONE_RE.finditer(text):
        phone = (m.group(1) or m.group(2) or '').strip()
        phone = re.sub(r'[\s\(\)]', '', phone)
        if phone and len(phone) >= 7 and phone not in phones:
            phones.append(phone)

    emails = []
    for m in EMAIL_RE.finditer(text):
        email = m.group(0).lower()
        if email not in SKIP_EMAILS and email not in emails:
            emails.append(email)

    if not phones and not emails:
        return None

    parts = []
    if phones:
        parts.append("tel: " + ", ".join(phones[:3]))
    if emails:
        parts.append("email: " + ", ".join(emails[:3]))
    return " | ".join(parts)


def extract_grant_details(url):
    """Visit the actual grant URL and extract details including contact info."""
    if not url:
        return {}

    html = fetch(url, timeout=15)
    if not html:
        return {}

    details = {}
    text = clean_html(html[:15000])

    deadline = extract_date(text)
    if deadline:
        details["deadline"] = deadline

    amount_match = re.search(r'(?:עד|סכום|מימון|תקציב)[^₪\d]*?(\d[\d,]+)\s*(?:₪|ש"ח|שקל)', text)
    if amount_match:
        amount_str = amount_match.group(1).replace(",", "")
        try:
            details["amount_max"] = int(amount_str)
        except ValueError:
            pass

    # Extract contact info (phone, email)
    contact = extract_contact_info(text)
    if contact:
        details["contact_info"] = contact

    desc_patterns = [
        r'<meta[^>]*name="description"[^>]*content="([^"]+)"',
        r'<p[^>]*>(.{100,500}?)</p>',
    ]
    for pat in desc_patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            desc = clean_html(m.group(1))
            if len(desc) > 50:
                details["description"] = desc[:500]
                break

    return details


# ============================================================
# DEDUP & UPLOAD — to Goldfish opportunities table
# ============================================================

def get_existing_urls():
    """Get all existing grant URLs from Goldfish opportunities."""
    try:
        resp = requests.get(
            f"{GOLDFISH_SUPABASE_URL}/rest/v1/opportunities?select=url,title&limit=2000",
            headers=HEADERS_GOLDFISH,
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            urls = {item["url"] for item in data if item.get("url")}
            titles = {item["title"] for item in data if item.get("title")}
            return urls, titles
    except Exception:
        pass
    return set(), set()


def deduplicate(new_items, existing_urls, existing_titles):
    """Remove items already in database."""
    unique = []
    for item in new_items:
        url = item.get("url", "")
        title = item.get("title", "")

        if not title or not url:
            continue

        # Exact URL match
        if url in existing_urls:
            continue

        # Fuzzy title match
        is_dup = any(
            title[:40] in existing or existing[:40] in title
            for existing in existing_titles
            if len(existing) > 10
        )
        if not is_dup:
            unique.append(item)

    return unique


def upload_to_goldfish(items):
    """Upload new items to Goldfish opportunities table. Skips duplicates by URL."""
    if not items:
        return 0

    # Fetch existing URLs to avoid duplicates
    existing_urls = set()
    try:
        resp = requests.get(
            f"{GOLDFISH_SUPABASE_URL}/rest/v1/opportunities?select=url&limit=5000",
            headers=HEADERS_GOLDFISH,
            timeout=20,
        )
        if resp.status_code == 200:
            existing_urls = {r["url"] for r in resp.json() if r.get("url")}
    except Exception:
        pass
    print(f"  Existing URLs in DB: {len(existing_urls)}")

    rows = []
    skipped = 0
    for item in items:
        url = item.get("url")
        if url and url in existing_urls:
            skipped += 1
            continue
        if url:
            existing_urls.add(url)  # prevent intra-batch duplicates
        rows.append({
            "title": item.get("title", "")[:300],
            "description": item.get("description", "")[:1000] or None,
            "url": url,
            "deadline": item.get("deadline") or None,
            "amount_max": item.get("amount_max") or None,
            "source": item.get("source", "scanner"),
            "funder": item.get("funder") or None,
            "active": True,
            "type": "grant",
            "categories": item.get("categories", []),
            "target_populations": item.get("target_populations", []),
            "tags": [],
            "contact_info": item.get("contact_info") or None,
        })

    if skipped:
        print(f"  Skipped {skipped} duplicates (URL already in DB)")

    uploaded = 0
    for i in range(0, len(rows), 50):
        batch = rows[i:i+50]
        resp = requests.post(
            f"{GOLDFISH_SUPABASE_URL}/rest/v1/opportunities",
            headers={**HEADERS_GOLDFISH, "Prefer": "return=minimal"},
            json=batch
        )
        if resp.status_code < 300:
            uploaded += len(batch)
        else:
            print(f"  Upload batch failed ({resp.status_code}): {resp.text[:200]}")
            logging.warning(f"Upload failed: {resp.status_code} {resp.text[:200]}")

    return uploaded


# ============================================================
# CLEANUP — deactivate expired opportunities
# ============================================================

def cleanup_expired():
    """Mark opportunities with passed deadlines as active=false."""
    print("\n--- Cleaning up expired opportunities ---")
    try:
        resp = requests.patch(
            f"{GOLDFISH_SUPABASE_URL}/rest/v1/opportunities?active=eq.true&deadline=lt.{date.today().isoformat()}&deadline=not.is.null",
            headers={**HEADERS_GOLDFISH, "Prefer": "return=representation"},
            json={"active": False},
        )
        if resp.status_code in (200, 204):
            try:
                count = len(resp.json()) if resp.text.strip() else 0
            except Exception:
                count = 0
            print(f"  Deactivated {count} expired opportunities")
            logging.info(f"Cleanup: deactivated {count} expired opportunities")
        else:
            print(f"  Cleanup failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"  Cleanup error: {e}")
        logging.error(f"Cleanup error: {e}")


# ============================================================
# MAIN
# ============================================================

def main():
    print(f"{'='*60}")
    print(f"  HOPA GRANTS SCANNER v3.0 — {date.today()}")
    print(f"  Target: Goldfish DB (touqczopfjxcpmbxzdjr)")
    print(f"  Rule: ONLY actual open RFPs with direct URLs")
    print(f"{'='*60}\n")

    all_results = []

    # === LAYER 1: ישראל — ממשלה ומוסדות ===
    print("--- [ישראל — ממשלה] Scanning Israeli government sources ---")
    il_gov_scanners = [
        ("gov.il קולות קוראים", scan_gov_il_kolkore),
        ("gov.il מבחנים ותמיכות (Playwright)", scan_gov_il_mevhanim),
        ("ביטוח לאומי", scan_btl),
        ("קק\"ל", scan_kkl),
        ("מפעל הפיס", scan_pais),
        ("ועדת העזבונות", scan_estates_committee),
        ("רשות החדשנות", scan_innovation_authority),
        ("מרכז רכש ממשלתי (mr.gov.il)", scan_mr_gov_il),
        ("data.gov.il — מאגרי נתונים פתוחים", scan_data_gov_il),
    ]
    for name, scanner in il_gov_scanners:
        print(f"  Scanning {name}...")
        all_results.extend(scanner())

    # === LAYER 2: ישראל — מגזר שלישי ורשויות מקומיות ===
    print("\n--- [ישראל — מגזר שלישי] NGOs, foundations, local councils ---")
    print("  Scanning שתיל...")
    all_results.extend(scan_shatil())
    print("  Scanning רשויות מקומיות (ת\"א, ירושלים, חיפה, ב\"ש)...")
    all_results.extend(scan_municipal())
    print("  Scanning Menomadin Foundation...")
    all_results.extend(scan_menomadin())
    print("  Scanning Miss Fix the Universe...")
    all_results.extend(scan_missfixtheuniverse())
    print("  Scanning הקרן לעידוד יוזמות חינוכיות...")
    all_results.extend(scan_keren_yozmot())
    print("  Scanning הרשות לפיתוח הנגב + הגליל...")
    all_results.extend(scan_negev_galil())
    print("  Scanning קרנות ישראליות (גוטווירט, קסירר, רוטשילד, רשי, יד הנדיב...)...")
    all_results.extend(scan_israeli_foundations())

    # === LAYER 3: ישראל — משרדי ממשלה ספציפיים ===
    print("\n--- [ישראל — משרדי ממשלה] Government ministries ---")
    ministry_results = scan_gov_ministries()
    all_results.extend(ministry_results)

    # === LAYER 4: בינלאומי — קרנות יהודיות ופדרליות ===
    print("\n--- [בינלאומי] International Jewish & US federal sources ---")
    print("  Scanning Grants.gov (USAID/State Dept)...")
    all_results.extend(scan_grants_gov())
    print("  Scanning Jewish Funders Network (JFN)...")
    all_results.extend(scan_jfn())
    print("  Scanning Candid.org (Israel filter)...")
    all_results.extend(scan_candid())
    print("  Scanning קרנות בינלאומיות (Seed the Dream, Schusterman, L'Oréal, Van Leer...)...")
    all_results.extend(scan_intl_foundations())

    # === Tamir newsletter ===
    print("\n--- Tamir Newsletter ---")
    try:
        from fetch_tamir_email import fetch_latest_tamir_email, parse_tamir_grants
        body = fetch_latest_tamir_email()
        if not body:
            cache = OUTPUT_DIR / "tamir_latest.txt"
            if cache.exists():
                body = cache.read_text(encoding="utf-8")
        if body:
            tamir_grants = parse_tamir_grants(body)
            # Filter through quality checks
            for g in tamir_grants:
                if is_valid_grant_url(g.get("url")) and is_actual_grant_title(g.get("title")):
                    all_results.append(g)
            print(f"  [tamir] {len(tamir_grants)} raw, {len([g for g in tamir_grants if is_valid_grant_url(g.get('url'))])} passed quality check")
    except Exception as e:
        print(f"  [tamir] Import error: {e}")
        tamir_results = scan_tamir_newsletter()
        all_results.extend(tamir_results)

    # === Final quality gate — one more pass ===
    quality_results = []
    for item in all_results:
        if is_valid_grant_url(item.get("url")) and is_actual_grant_title(item.get("title")):
            quality_results.append(item)
        else:
            logging.info(f"Rejected: {item.get('title', '?')[:60]} | URL: {item.get('url', 'none')[:80]}")

    print(f"\n  Total found: {len(all_results)} | Passed quality: {len(quality_results)}")

    if not quality_results:
        print("No quality items found. Done.")
        return

    # === Enrich — get details + auto-tag from actual pages ===
    print("\nEnriching items with grant details + auto-tagging...")
    enriched = 0
    for item in quality_results[:30]:
        page_text = ""
        if item.get("url") and not item.get("description"):
            html = fetch(item["url"], timeout=15)
            if html:
                page_text = clean_html(html[:15000])
                details = extract_grant_details(item["url"])
                if details:
                    item.update({k: v for k, v in details.items() if v and not item.get(k)})
                enriched += 1

        # Auto-tag using regex patterns (same as org-dna.ts)
        categories, target_populations, regions = auto_tag_grant(
            item.get("title", ""),
            item.get("description", ""),
            page_text
        )
        item["categories"] = categories
        item["target_populations"] = target_populations
        item["regions"] = regions

    tagged = sum(1 for i in quality_results if i.get("categories") or i.get("target_populations"))
    print(f"  Enriched {enriched} items, tagged {tagged} with categories/populations\n")

    # === Dedup against Goldfish DB ===
    existing_urls, existing_titles = get_existing_urls()
    print(f"Existing in Goldfish DB: {len(existing_urls)} URLs, {len(existing_titles)} titles")

    new_items = deduplicate(quality_results, existing_urls, existing_titles)
    print(f"New unique items: {len(new_items)}")

    if not new_items:
        print("All items already in database. Done.")
        return

    # === Save locally ===
    output_file = OUTPUT_DIR / f"scan_{date.today().isoformat()}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(new_items, f, ensure_ascii=False, indent=2)
    print(f"Saved to: {output_file}")

    # === Upload to Goldfish ===
    uploaded = upload_to_goldfish(new_items)
    print(f"\nUploaded {uploaded} new grants to Goldfish!")

    # === Summary ===
    # === Layer breakdown summary ===
    layer_counts = {
        "ישראל — ממשלה": sum(1 for i in new_items if i.get("source") in ("gov_il", "gov_mevhanim", "btl", "kkl", "pais", "estates_committee", "innovation_authority", "gov_welfare", "gov_culture", "gov_sport", "gov_aliya", "tkuma", "mop_education")),
        "ישראל — מגזר שלישי": sum(1 for i in new_items if i.get("source") in ("shatil", "municipal_tlv", "municipal_jlm", "municipal_haifa", "municipal_bs")),
        "בינלאומי": sum(1 for i in new_items if i.get("source") in ("grants_gov", "jfn", "candid")),
        "ניוזלטר / אחר": sum(1 for i in new_items if i.get("source") in ("tamir_newsletter",)),
    }
    print(f"\n{'='*60}")
    print(f"  SUMMARY — HOPA GRANTS SCANNER v3.1")
    print(f"  Scanned: {len(all_results)} total")
    print(f"  Passed quality: {len(quality_results)}")
    print(f"  New unique: {len(new_items)}")
    print(f"  Uploaded: {uploaded}")
    print(f"  --- By layer ---")
    for layer, count in layer_counts.items():
        print(f"    {layer}: {count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    try:
        cleanup_expired()
        main()
        logging.info("Scanner v3.0 completed successfully")
    except Exception as e:
        logging.error(f"Scanner crashed: {e}", exc_info=True)
        raise
