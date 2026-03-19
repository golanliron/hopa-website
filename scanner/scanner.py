#!/usr/bin/env python3
"""
Hopa Grant Scanner
------------------
Usage:
    python scanner.py              # scan all, save to Supabase
    python scanner.py --dry-run   # scan only, no save
    python scanner.py --israel    # Israel sources only
    python scanner.py --intl      # International only
"""
import argparse
import io
import json
import logging
import os
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

# Fix Windows terminal encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

from config import (
    ISRAELI_SOURCES, INTERNATIONAL_SOURCES, RSS_SOURCES,
    REQUEST_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY,
    OUTPUT_DIR, SUPABASE_URL, SUPABASE_KEY,
)
from base_scanner import BaseScanner, Call, calc_match_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Supabase save ─────────────────────────────────────────
def save_to_supabase(calls: list[Call]) -> bool:
    if not SUPABASE_KEY:
        logger.warning("SUPABASE_KEY חסר — לא שומר ל-Supabase")
        return False

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Clear old records
    try:
        r = requests.delete(
            f"{SUPABASE_URL}/rest/v1/scanner_calls",
            headers={**headers, "Prefer": ""},
            params={"id": "neq.00000000-0000-0000-0000-000000000000"},
            timeout=15,
        )
        r.raise_for_status()
        logger.info("✓ נמחקו רשומות ישנות")
    except Exception as e:
        logger.error("שגיאה במחיקת ישנים: %s", e)
        return False

    # Insert in batches of 100
    rows = [c.to_dict() for c in calls]
    batch_size = 100
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/scanner_calls",
                headers=headers,
                json=batch,
                timeout=20,
            )
            r.raise_for_status()
            inserted += len(batch)
            logger.info("✓ שמרתי %d/%d", inserted, len(rows))
        except Exception as e:
            logger.error("שגיאה בשמירת batch %d: %s", i, e)

    logger.info("✅ סה\"כ נשמרו %d קולות קוראים ל-Supabase", inserted)
    return True


# ── Save JSON locally ─────────────────────────────────────
def save_json(calls: list[Call]):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"calls_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in calls], f, ensure_ascii=False, indent=2)
    logger.info("💾 נשמר JSON: %s", path)
    return path


# ── RSS scanner ───────────────────────────────────────────
def scan_rss(source: dict) -> list[Call]:
    try:
        import feedparser
    except ImportError:
        logger.warning("feedparser לא מותקן — מדלג על RSS")
        return []

    scanner = BaseScanner()
    raw = scanner.fetch_raw(source["url"])
    if not raw:
        return []
    feed = feedparser.parse(raw)
    calls = []
    for entry in feed.entries:
        title = getattr(entry, "title", "")
        link  = getattr(entry, "link", "")
        summary = getattr(entry, "summary", "")
        if summary:
            summary = BeautifulSoup(summary, "lxml").get_text(strip=True)[:300]
        if title:
            calls.append(Call(
                title=title, source=source["name"], url=link,
                category=source["category"], region="international",
                description=summary,
            ))
    return calls


# ── Main scan ─────────────────────────────────────────────
def scan_all(region: str = "all") -> list[Call]:
    scanner = BaseScanner()
    all_calls = []

    if region in ("all", "israel"):
        print("\n--- Israel sources ---")
        for src in ISRAELI_SOURCES:
            logger.info("  -> %s", src["name"])
            soup = scanner.fetch(src["url"])
            if soup:
                calls = scanner.extract_calls(soup, src, "israel")
                all_calls.extend(calls)
                logger.info("     found %d calls", len(calls))
            time.sleep(0.5)

    if region in ("all", "intl"):
        print("\n--- International sources ---")
        for src in INTERNATIONAL_SOURCES:
            logger.info("  -> %s", src["name"])
            soup = scanner.fetch(src["url"])
            if soup:
                calls = scanner.extract_calls(soup, src, "international")
                all_calls.extend(calls)
                logger.info("     found %d calls", len(calls))
            time.sleep(0.5)

        print("\n--- RSS feeds ---")
        for src in RSS_SOURCES:
            logger.info("  -> %s", src["name"])
            calls = scan_rss(src)
            all_calls.extend(calls)
            logger.info("     found %d calls", len(calls))

    # Deduplicate globally by URL
    seen, unique = set(), []
    for c in all_calls:
        if c.url not in seen:
            seen.add(c.url)
            unique.append(c)

    # Calculate match scores
    for c in unique:
        c.match_score = calc_match_score(c)

    # Sort: highest match first
    unique.sort(key=lambda c: c.match_score, reverse=True)
    return unique


# ── Entry point ───────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Hopa Grant Scanner")
    parser.add_argument("--dry-run", action="store_true", help="הדפס בלי לשמור")
    parser.add_argument("--israel",  action="store_true", help="ישראל בלבד")
    parser.add_argument("--intl",    action="store_true", help="בינלאומי בלבד")
    parser.add_argument("--json",    action="store_true", help="שמור גם ל-JSON")
    args = parser.parse_args()

    region = "all"
    if args.israel: region = "israel"
    if args.intl:   region = "intl"

    print("=" * 50)
    print("  Hopa Grant Scanner")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 50)

    calls = scan_all(region=region)

    print(f"\nTotal found: {len(calls)} calls")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        for c in calls[:10]:
            print(f"  * {c.title[:60]} [{c.source[:30]}]")
        return

    if args.json:
        save_json(calls)

    if calls:
        save_to_supabase(calls)
    else:
        print("\nNo calls found - nothing saved")

    print("\nDone!")


if __name__ == "__main__":
    main()
