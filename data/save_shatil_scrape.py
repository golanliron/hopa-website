"""
שומר את הסריקה משתיל + ביטוח לאומי — 2026-05-04
"""
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

shatil_items = [
    {"title": "קול קורא להגשת בקשות לוועדת העיזבונות", "deadline": "2026-05-06", "open_date": "", "funder": "וועדת העיזבונות", "url": "https://shatil.org.il/kol/קול-קורא-להגשת-בקשות-לוועדת-העיזבונות/", "source": "shatil"},
    {"title": "קול קורא של תוכנית הרזידנסי המשותפת AIR Givat Haviva", "deadline": "2026-07-07", "open_date": "", "funder": "AIR Givat Haviva", "url": "https://shatil.org.il/kol/תוכנית-הרזידנסי-air-givat-haviva/", "source": "shatil"},
    {"title": "קידום צעירים וצעירות יוצאי אתיופיה", "deadline": "2025-12-01", "open_date": "", "funder": "Levi Lassen Foundation", "url": "https://shatil.org.il/kol/קידום-צעירים-וצעירות-יוצאי-אתיופיה/", "source": "shatil"},
    {"title": "העצמת חברה אזרחית ותקשורת לחוסן קהילתי ולכידות חברתית", "deadline": "2025-11-02", "open_date": "", "funder": "Expertise France", "url": "https://shatil.org.il/kol/העצמת-חברה-אזרחית-ותקשורת-לחו/", "source": "shatil"},
    {"title": "מענק Monday לעמותות", "deadline": "", "open_date": "", "funder": "Monday", "url": "https://shatil.org.il/kol/ההרשמה-למענק-monday-לעמותות-נפתחה-מחדש/", "source": "shatil"},
    {"title": "הג'וינט — מענים בעקבות המלחמה עם איראן", "deadline": "2025-08-19", "open_date": "", "funder": "הג'וינט", "url": "https://shatil.org.il/kol/קול-קורא-הגוינט-למענים-בעקבות-המלחמ/", "source": "shatil"},
    {"title": "תכנית חברה וקהילה ברשויות הבדואיות בנגב", "deadline": "2025-08-18", "open_date": "", "funder": "משרד החינוך", "url": "https://shatil.org.il/kol/קול-קורא-לתכנית-חברה-וקהילה-ברשויות-ה/", "source": "shatil"},
    {"title": "מלגות מפעל הפיס ועיריית חיפה", "deadline": "2025-08-11", "open_date": "", "funder": "מפעל הפיס", "url": "https://shatil.org.il/kol/מלגות-מפעל-הפיס-ועיריית-חיפה/", "source": "shatil"},
    {"title": "הנציבות האירופית Horizon Europe", "deadline": "2025-09-16", "open_date": "", "funder": "הנציבות האירופית", "url": "https://shatil.org.il/kol/הנציבות-האירופית-horizon-europe/", "source": "shatil"},
    {"title": "Social Shifters", "deadline": "2025-08-29", "open_date": "", "funder": "Social Shifters", "url": "https://shatil.org.il/kol/social-shifters/", "source": "shatil"},
    {"title": "Lisle International", "deadline": "2025-07-31", "open_date": "", "funder": "Lisle International", "url": "https://shatil.org.il/kol/lisle-international/", "source": "shatil"},
    {"title": "קולות קוראים של מפעל הפיס", "deadline": "", "open_date": "", "funder": "מפעל הפיס", "url": "https://shatil.org.il/kol/קולות-קוראים-של-מפעל-הפיס/", "source": "shatil"},
    {"title": "Open Technology Fund", "deadline": "", "open_date": "", "funder": "Open Technology Fund", "url": "https://shatil.org.il/kol/open-technology-fund/", "source": "shatil"},
    {"title": "קרן Disrupt", "deadline": "", "open_date": "", "funder": "Disrupt", "url": "https://shatil.org.il/kol/קרן-distrupt/", "source": "shatil"},
    {"title": "Purpose Earth", "deadline": "", "open_date": "", "funder": "Purpose Earth", "url": "https://shatil.org.il/kol/purpose-earth/", "source": "shatil"},
    {"title": "The Lantos Foundation", "deadline": "", "open_date": "", "funder": "The Lantos Foundation", "url": "https://shatil.org.il/kol/the-lantos-foundation/", "source": "shatil"},
    {"title": "מענקי מחקר סילקה טמפל", "deadline": "", "open_date": "", "funder": "סילקה טמפל", "url": "https://shatil.org.il/kol/מענקי-מחקר-סילקה-טמפל/", "source": "shatil"},
    {"title": "קול קורא של עיריית באר שבע", "deadline": "", "open_date": "", "funder": "עיריית באר שבע", "url": "https://shatil.org.il/kol/קול-קורא-של-עיריית-באר-שבע/", "source": "shatil"},
]

btl_items = [
    {"title": "מחקר הערכה ליוזמת תעסוקת אנשים עם מוגבלויות בשוק הפתוח", "deadline": "2026-05-07", "open_date": "", "funder": "ביטוח לאומי — קרן לפיתוח שירותים לאנשים עם מוגבלויות", "url": "https://www.btl.gov.il/Funds/kolotkorim/Pages/default.aspx", "source": "btl"},
]

all_items = shatil_items + btl_items

output = {
    "scraped_date": "2026-05-04",
    "sources": ["shatil.org.il", "btl.gov.il"],
    "total_items": len(all_items),
    "items": all_items
}

with open("shatil_btl_scrape_20260504.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Saved {len(all_items)} items from Shatil + BTL")
print(f"  With deadline: {sum(1 for i in all_items if i['deadline'])}")
print(f"  Ongoing (no deadline): {sum(1 for i in all_items if not i['deadline'])}")
print(f"  ALL have URLs!")
