"""
gov.il class_action_law_database — Playwright scraper (dry-run only).

Usage:
    python class_action_playwright.py

Returns a dry-run report to stdout + JSON file in outputs/.
NEVER writes to DB.

API: POST https://www.gov.il/he/api/DynamicCollector
     Body: {"DynamicTemplateID": "class_action_law_database", "skip": 0, "limit": 20}
     Returns: {"Results": [...], "TotalResults": N}

Each result:
    {"Data": {"number", "list", "sub_list", "date", "file", "publication"}, "UrlName": "..."}
"""
import io
import json
import logging
import re
import sys
from datetime import date, datetime
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PAGE_URL = (
    "https://www.gov.il/he/Departments/DynamicCollectors/"
    "class_action_law_database?skip=0"
)
DETAIL_BASE = "https://www.gov.il/he/Departments/DynamicCollectors/class_action_law_database/"

# publication codes → human-readable (from gov.il taxonomy)
PUBLICATION_TYPES = {
    "1": "קול קורא",
    "2": "קול קורא — חינוך",
    "3": "קול קורא — בריאות",
    "4": "קול קורא — רווחה",
    "5": "קול קורא — ספורט",
    "6": "קול קורא — תרבות",
    "7": "קול קורא — פיתוח עסקים",
    "8": "קול קורא — סביבה",
    "9": "קול קורא — משפטי",
}

SETTLEMENT_KEYWORDS = [
    "הסדר פשרה", "פשרה", "settlement", "קרן פיצוי",
    "פיצוי", "compensation", "fund", "תשלום לניזוקים",
    "הסכם פשרה", "כספים שנפסקו", "תובענה ייצוגית",
]


def normalize_date(raw: str) -> Optional[str]:
    """Convert ISO datetime string or date string to YYYY-MM-DD, only if future."""
    if not raw:
        return None
    today = date.today()
    # ISO datetime: 2026-06-14T21:00:00Z
    m = re.match(r"(20\d{2})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.isoformat()  # return even if past — useful for reporting
        except ValueError:
            pass
    return None


def classify(sub_list: str, number: str) -> str:
    combined = sub_list + " " + number
    if any(kw in combined for kw in SETTLEMENT_KEYWORDS):
        return "settlement_fund"
    return "class_action_only"


def scrape_class_action_playwright(pages: int = 1) -> dict:
    """
    Scrape gov.il class_action_law_database using Playwright.
    pages: how many pages to fetch (20 items/page). Default 1 = first 20.
    Returns dry-run report dict — never touches DB.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"error": "playwright not installed — run: pip install playwright && playwright install chromium"}

    all_items = []
    total_available = 0
    cf_blocked = False
    api_intercepted = False
    error = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            ignore_https_errors=True,
            locale="he-IL",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        body_store = {}

        def on_response(r):
            if (
                r.url == "https://www.gov.il/he/api/DynamicCollector"
                and r.status == 200
            ):
                try:
                    body_store["bytes"] = r.body()
                    body_store["url"] = r.url
                except Exception:
                    pass

        page.on("response", on_response)

        logger.info("Loading: %s", PAGE_URL)
        try:
            page.goto(PAGE_URL, timeout=30000, wait_until="networkidle")
        except Exception as e:
            logger.warning("Page load error: %s", e)

        title = page.title()
        content = page.content()

        if "just a moment" in title.lower() or "checking your browser" in content.lower():
            cf_blocked = True
            logger.warning("Cloudflare challenge blocked — even Chromium")
            try:
                import os; os.makedirs("outputs", exist_ok=True)
                page.screenshot(path="outputs/class_action_cf.png")
            except Exception:
                pass
        else:
            logger.info("Page loaded: %s", title)

            if "bytes" in body_store:
                api_intercepted = True
                try:
                    data = json.loads(body_store["bytes"].decode("utf-8"))
                    total_available = data.get("TotalResults", 0)
                    results = data.get("Results", [])
                    logger.info("API: %d/%d items in first page", len(results), total_available)

                    for entry in results:
                        d = entry.get("Data", {})
                        url_name = entry.get("UrlName", "")
                        sub_list = d.get("sub_list", "").strip()
                        number = d.get("number", "").strip()
                        raw_date = d.get("date", "")
                        deadline = normalize_date(raw_date)
                        pub_codes = d.get("publication", [])
                        pub_types = [PUBLICATION_TYPES.get(str(c), c) for c in pub_codes]

                        # Title: "מספר NN/YYYY — תיאור"
                        title_val = f"{number} — {sub_list}" if number else sub_list
                        detail_url = DETAIL_BASE + url_name if url_name else PAGE_URL

                        all_items.append({
                            "title": title_val,
                            "number": number,
                            "sub_list": sub_list,
                            "url": detail_url,
                            "deadline": deadline,
                            "raw_date": raw_date[:10] if raw_date else None,
                            "publication_types": pub_types,
                            "has_file": bool(d.get("file")),
                        })
                except Exception as e:
                    error = f"API parse error: {e}"
                    logger.error(error)
            else:
                error = "API response not intercepted — page may not have loaded correctly"
                logger.warning(error)

        browser.close()

    # Classify
    accepted = []
    rejected = []
    for item in all_items:
        cl = classify(item["sub_list"], item["number"])
        item["classification"] = cl
        if cl == "settlement_fund":
            accepted.append(item)
        else:
            rejected.append(item)

    today = date.today().isoformat()
    future_items = [i for i in all_items if i.get("deadline") and i["deadline"] >= today]

    report = {
        "dry_run": True,
        "source": "gov.il — הוועדה לחלוקת כספים שנפסקו בתובענות ייצוגיות",
        "url": PAGE_URL,
        "scanned_at": today,
        "total_available": total_available,
        "raw_count": len(all_items),
        "future_deadline_count": len(future_items),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "samples": all_items[:20],
        "accepted": accepted,
        "rejected_sample": rejected[:5],
        "recommended_classification": "settlement_fund",
        "note": "לא הוכנס ל-DB. יש לאשר ידנית לפני שמירה.",
        "api_intercepted": api_intercepted,
        "cf_blocked": cf_blocked,
        "error": error,
    }
    return report


def main():
    import os
    os.makedirs("outputs", exist_ok=True)

    print("=" * 58)
    print("  gov.il תובענות ייצוגיות — Playwright DRY-RUN")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 58)

    report = scrape_class_action_playwright()

    if report.get("error") and not report.get("raw_count"):
        print(f"\nERROR: {report['error']}")
        return

    if report.get("cf_blocked"):
        print("\n⚠  Cloudflare חסם — גם Chromium.")
        print("   Screenshot: outputs/class_action_cf.png")
        return

    print(f"\ntotal_available:  {report['total_available']}")
    print(f"raw_count:        {report['raw_count']}  (עמוד ראשון בלבד)")
    print(f"future_deadline:  {report['future_deadline_count']}")
    print(f"accepted:         {report['accepted_count']}  (settlement_fund)")
    print(f"rejected:         {report['rejected_count']}  (class_action_only)")
    print(f"api_intercepted:  {report['api_intercepted']}")

    print(f"\n--- {min(20, report['raw_count'])} דוגמאות ---")
    for item in report["samples"]:
        dl = item.get("raw_date") or "no date"
        cl = item.get("classification", "?")
        print(f"  [{dl}] [{cl[:12]}] {item['title'][:65]}")
        print(f"         {item['url']}")

    if report["accepted"]:
        print(f"\n--- Accepted settlement funds ({report['accepted_count']}) ---")
        for item in report["accepted"]:
            print(f"  [{item.get('raw_date','?')}] {item['title'][:70]}")

    print(f"\nNOTE: {report['note']}")

    out_path = f"outputs/class_action_dryrun_{date.today().isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Full report: {out_path}")


if __name__ == "__main__":
    main()
