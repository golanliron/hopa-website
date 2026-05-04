"""
Atlas Grants Full Scraper
סריקה חד-פעמית מאסיבית של כל מקורות המימון מאטלס
גישה: פותח דפדפן נקי, את מתחברת פעם אחת, והוא סורק הכל
"""

import json
import time
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://app.atlas-grants.com/admin/funds/funds-search"
BROWSER_DATA = os.path.join(os.path.dirname(__file__), "atlas_browser")


def scrape_atlas():
    print("\n=== Atlas Grants Full Scraper ===")
    print("=== הדפדפן ישאר פתוח עד שתסגרי אותו ===\n")

    with sync_playwright() as p:
        # פרופיל נפרד שנשמר — בפעם השנייה כבר תהיי מחוברת
        browser = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA,
            headless=False,
            viewport={"width": 1400, "height": 900},
            locale="he-IL",
            slow_mo=500  # קצת איטי כדי שהאתר לא יחסום
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        print("[*] פותח את אטלס...")
        page.goto(BASE_URL, timeout=60000)
        time.sleep(5)

        # בדיקה אם מחוברים
        current_url = page.url.lower()
        if "login" in current_url or "sign" in current_url or "auth" in current_url:
            print("\n" + "="*50)
            print(" התחברי לאטלס בדפדפן שנפתח!")
            print(" הסקריפט ימתין עד שתסיימי...")
            print("="*50 + "\n")

            # ממתינים עד 3 דקות
            for i in range(180):
                time.sleep(2)
                current_url = page.url.lower()
                if "login" not in current_url and "sign" not in current_url and "auth" not in current_url:
                    print("[+] זוהתה כניסה מוצלחת!")
                    break
                if i % 15 == 0 and i > 0:
                    print(f"    עדיין ממתין... ({i*2} שניות)")
            else:
                print("[X] לא הצלחנו להתחבר תוך 3 דקות. סוגר.")
                browser.close()
                return []

            # מנווטים לדף החיפוש
            time.sleep(2)
            page.goto(BASE_URL, timeout=60000)
            time.sleep(5)

        print("[+] מחובר! מתחיל סריקה...\n")

        all_items = []
        page_num = 0
        consecutive_empty = 0

        while True:
            page_num += 1
            print(f"[*] סורק עמוד {page_num}...")
            time.sleep(3)

            # שומר screenshot לדיבוג
            screenshot_path = os.path.join(OUTPUT_DIR, f"page_{page_num}.png")
            page.screenshot(path=screenshot_path)

            # שולף כרטיסים
            items = page.evaluate("""
                () => {
                    const results = [];
                    const seen = new Set();

                    // אסטרטגיה 1: חיפוש לפי מבנה טקסט ידוע
                    const allElements = document.querySelectorAll('*');
                    const candidates = [];

                    for (const el of allElements) {
                        const text = el.innerText || '';
                        // כרטיס אטלס מכיל בד"כ: שם + תיאור + Deadline + תגיות
                        if (text.length > 80 && text.length < 4000 &&
                            el.children.length > 1 &&
                            (text.includes('Deadline') || text.includes('קו׳׳ק') ||
                             text.includes('קרן') || text.includes('עסק') ||
                             text.includes('הקדש') || text.includes('הוסף למועדפים'))) {

                            // בדיקה שזה לא הcontainer הגדול
                            const parent = el.parentElement;
                            if (parent && parent.innerText && parent.innerText.length > text.length * 2) {
                                candidates.push(el);
                            }
                        }
                    }

                    // אם לא מצאנו עם הגישה הזו, ננסה גישה אחרת
                    let cards = candidates;
                    if (cards.length === 0) {
                        // מחפשים div-ים שמכילים "הוסף למועדפים" — כי כל כרטיס מכיל את זה
                        const allDivs = document.querySelectorAll('div');
                        cards = Array.from(allDivs).filter(d => {
                            const t = d.innerText || '';
                            return t.includes('הוסף למועדפים') && t.includes('שיתוף') &&
                                   t.length > 100 && t.length < 5000 &&
                                   d.querySelectorAll('div').length < 50;
                        });
                    }

                    // מחלצים נתונים מכל כרטיס
                    for (const card of cards) {
                        const text = card.innerText.trim();
                        const key = text.substring(0, 100);
                        if (seen.has(key)) continue;
                        seen.add(key);

                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

                        // מסננים שורות של UI
                        const contentLines = lines.filter(l =>
                            !l.includes('הוסף למועדפים') && !l.includes('הסתרה') &&
                            !l.includes('הוסף לתוכנית') && !l.includes('שיתוף') &&
                            l !== 'New' && l !== 'קו׳׳ק' && l !== 'קרן' && l !== 'עסק' && l !== 'הקדש'
                        );

                        // שם
                        let title = contentLines[0] || '';

                        // סוג
                        let type = 'unknown';
                        if (text.includes('קו׳׳ק')) type = 'kok';
                        else if (lines.includes('קרן')) type = 'fund';
                        else if (lines.includes('עסק')) type = 'business';
                        else if (lines.includes('הקדש')) type = 'endowment';

                        // Deadline
                        let deadline = '';
                        const dlMatch = text.match(/Deadline:\\s*([\\d\\-]+)/);
                        if (dlMatch) deadline = dlMatch[1];

                        // תיאור
                        let description = contentLines.slice(1).filter(l => l.length > 30).join(' ').substring(0, 800);

                        // תגיות — שורות קצרות בסוף
                        let tags = contentLines.filter(l => l.length > 3 && l.length < 50 && !l.includes('Deadline'));
                        // מנסים לזהות תגיות (בד"כ בסוף הכרטיס)
                        const tagCandidates = tags.slice(-8).filter(l =>
                            !l.includes('.') && l.length < 40
                        );

                        // New
                        const isNew = lines.includes('New');

                        // סכום
                        let amount = '';
                        const amtMatch = text.match(/([\\.\\d,]+)\\s*(?:₪|ש"ח|שקל|דולר|\\$|אירו)/);
                        if (amtMatch) amount = amtMatch[0];

                        if (title.length > 5) {
                            results.push({
                                title: title,
                                type: type,
                                is_new: isNew,
                                description: description,
                                deadline: deadline,
                                amount: amount,
                                tags: tagCandidates.slice(0, 6),
                                full_text: text.substring(0, 2500)
                            });
                        }
                    }

                    return results;
                }
            """)

            if items and len(items) > 0:
                new_count = 0
                for item in items:
                    if item['title'] not in [x['title'] for x in all_items]:
                        all_items.append(item)
                        new_count += 1
                print(f"    -> {len(items)} פריטים ({new_count} חדשים)")
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                print(f"    -> ריק ({consecutive_empty}/3)")
                if consecutive_empty >= 3:
                    print("\n[+] 3 עמודים ריקים ברצף - סיום")
                    break

            # גלילה / עמוד הבא
            scrolled = page.evaluate("""
                () => {
                    // חיפוש כפתור הבא
                    const btns = document.querySelectorAll('button, a');
                    for (const btn of btns) {
                        const t = (btn.innerText || '').trim();
                        const label = btn.getAttribute('aria-label') || '';
                        if ((t === '>' || t === 'הבא' || t === 'Next' || label.includes('next') || label.includes('הבא')) &&
                            !btn.disabled && btn.offsetParent !== null) {
                            btn.click();
                            return 'next_page';
                        }
                    }

                    // infinite scroll
                    const oldHeight = document.documentElement.scrollHeight;
                    window.scrollTo(0, document.documentElement.scrollHeight);
                    return 'scrolled';
                }
            """)

            print(f"    [{scrolled}]")
            time.sleep(3)

            if page_num > 200:
                print("\n[!] עצירת בטיחות")
                break

        # שמירה
        print(f"\n{'='*50}")
        print(f" סה\"כ: {len(all_items)} פריטים ייחודיים")
        print(f"{'='*50}\n")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(OUTPUT_DIR, f"atlas_full_{timestamp}.json")

        export_data = {
            "metadata": {
                "source": "app.atlas-grants.com",
                "url": BASE_URL,
                "scraped_date": datetime.now().isoformat(),
                "total_items": len(all_items),
                "pages_scanned": page_num
            },
            "items": all_items
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"[+] נשמר: {output_file}")

        main_file = os.path.join(os.path.dirname(__file__), "..", "data", "atlas_full_export.json")
        with open(main_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"[+] נשמר: data/atlas_full_export.json")

        browser.close()

    print("\n=== סריקה הושלמה! ===")
    return all_items


if __name__ == "__main__":
    scrape_atlas()
