"""
Hopa Grant Scanner — Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://vhmwijzcrqjjquxomccq.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

FOCUS_TOPICS = [
    "נוער בסיכון", "צעירים בסיכון", "מוביליות חברתית", "קהילות מודרות",
    "חדשנות טכנולוגית", "חינוך", "מניעת נשירה", "קהילות מיוחדות",
    "youth at risk", "at-risk youth", "social mobility", "marginalized communities",
    "dropout prevention", "education innovation", "underserved communities",
]

ISRAELI_SOURCES = [
    {"name": "אתר התמיכות הממשלתי - משרד האוצר", "url": "https://tmichot.mof.gov.il/call-for-proposals/", "category": "government"},
    {"name": "משרד הפנים - קולות קוראים", "url": "https://www.gov.il/he/Departments/DynamicCollectors/kolkore-list", "category": "government"},
    {"name": "רשות החדשנות - קולות קוראים", "url": "https://innovationisrael.org.il/kol_kore/", "category": "innovation"},
    {"name": "משרד החינוך - קולות קוראים", "url": "https://pob.education.gov.il/kolotkorim/kolkore/", "category": "education"},
    {"name": "שפ\"י - שירות פסיכולוגי ייעוצי", "url": "https://shefi.education.gov.il/publication/voices-calling/", "category": "youth_at_risk"},
    {"name": "ביטוח לאומי - קרן לילדים ונוער", "url": "https://www.btl.gov.il/About/news/Pages/ArchiveFolder/kolKoreYeladim.aspx", "category": "youth_at_risk"},
    {"name": "הג'וינט - מוביליות חברתית", "url": "https://www.thejoint.org.il/challenges/social_mobility/", "category": "social_mobility"},
    {"name": "שתיל - קרנות וקולות קוראים", "url": "https://shatil.org.il/%D7%A7%D7%A8%D7%A0%D7%95%D7%AA-%D7%95%D7%A7%D7%95%D7%9C%D7%95%D7%AA-%D7%A7%D7%95%D7%A8%D7%90%D7%99%D7%9D/", "category": "social"},
    {"name": "SocialMap - הקול קורה", "url": "https://socialmap.org.il/hakol-kore", "category": "social"},
    {"name": "גיידסטאר - קולות קוראים", "url": "https://www.guidestar.org.il/search-announcements", "category": "ngo"},
    {"name": "משאבים - מענקים לעמותות", "url": "https://mashabim.org/main-page/", "category": "ngo"},
]

INTERNATIONAL_SOURCES = [
    {"name": "OJJDP - Office of Juvenile Justice", "url": "https://ojjdp.ojp.gov/funding/current", "category": "youth_at_risk"},
    {"name": "fundsforNGOs - Youth & Adolescents", "url": "https://www2.fundsforngos.org/category/youth-adolescents/", "category": "youth_at_risk"},
    {"name": "fundsforNGOs - Education", "url": "https://www2.fundsforngos.org/category/education/", "category": "education"},
    {"name": "fundsforNGOs - Latest Grants", "url": "https://www2.fundsforngos.org/category/latest-funds-for-ngos/", "category": "ngo"},
    {"name": "Instrumentl - Youth Programs", "url": "https://www.instrumentl.com/browse-grants/grants-for-youth-programs", "category": "youth_at_risk"},
    {"name": "EU Funding Portal - Education", "url": "https://eufundingportal.eu/tag/education/", "category": "education"},
]

RSS_SOURCES = [
    {"name": "Grants.gov - Youth & Education RSS", "url": "https://www.grants.gov/rss/GG_OppModByCategory.xml", "category": "government"},
]

# ── Hopa match scoring ────────────────────────────────────
# Base score by category (0-60)
CATEGORY_BASE_SCORE = {
    "youth_at_risk":   60,
    "social_mobility": 55,
    "education":       50,
    "social":          40,
    "ngo":             35,
    "government":      30,
    "innovation":      25,
}

# Keywords that boost score (+5 each, up to +40)
HOPA_KEYWORDS_HE = [
    "נוער בסיכון", "נשירה", "מניעת נשירה", "צעירים בסיכון",
    "ליווי", "שייכות", "מוביליות", "העצמה", "בני נוער",
    "14", "18", "26", "מעבר", "בוגרים", "תעסוקה", "מלגה",
    "חינוך", "קהילה", "מודרת", "הכלה", "סיכון",
]
HOPA_KEYWORDS_EN = [
    "youth at risk", "dropout", "at-risk", "prevention",
    "young adults", "mentoring", "social mobility", "underserved",
    "transition", "employment", "scholarship", "inclusion",
    "belonging", "marginalized", "vulnerable youth",
]

REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Hopa Grant Scanner; +https://hopa.org.il)",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8",
}
MAX_RETRIES = 2
RETRY_DELAY = 2

OUTPUT_DIR = "outputs"
