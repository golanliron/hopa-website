"""
בונה בסיס נתונים מסודר של קולות קוראים ומקורות מימון
מתוך הנתונים הגולמיים שנסרקו מאטלס + מקורות נוספים
"""

import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

# === TAXONOMY - קטגוריות ותת-קטגוריות ===
TAXONOMY = {
    "חינוך והשכלה": {
        "id": "education",
        "subcategories": {
            "חינוך פורמלי": "formal_education",
            "חינוך בלתי פורמלי": "informal_education",
            "חינוך לגיל הרך": "early_childhood",
            "השכלה גבוהה": "higher_education",
            "הכשרה מקצועית": "vocational_training",
            "הוראה": "teaching",
            "חינוך משלים": "supplementary_education",
            "חינוך מיוחד": "special_education"
        }
    },
    "רווחה וחברה": {
        "id": "welfare",
        "subcategories": {
            "ילדים ונוער בסיכון": "youth_at_risk",
            "נוער וצעירים": "youth",
            "נשים ונערות": "women_girls",
            "זיקנה": "elderly",
            "צרכים מיוחדים ומוגבלויות": "disabilities",
            "עלייה וקליטה": "immigration",
            "אסירים משוחררים": "ex_prisoners",
            "משפחות במצוקה": "families_distress"
        }
    },
    "קהילה ומנהיגות": {
        "id": "community",
        "subcategories": {
            "פיתוח קהילתי": "community_dev",
            "פיתוח מנהיגות": "leadership",
            "יזמות חברתית": "social_entrepreneurship",
            "חברה משותפת": "shared_society",
            "גרעינים משימתיים": "mission_groups",
            "מעורבות אזרחית": "civic_engagement",
            "מתנדבות": "volunteering"
        }
    },
    "בריאות ורפואה": {
        "id": "health",
        "subcategories": {
            "בריאות הציבור": "public_health",
            "מחקר רפואי": "medical_research",
            "רפואה": "medicine",
            "ציוד רפואי": "medical_equipment",
            "בריאות הנפש": "mental_health"
        }
    },
    "תעסוקה וכלכלה": {
        "id": "employment",
        "subcategories": {
            "תעסוקה והכשרה": "employment_training",
            "יזמות עסקית": "entrepreneurship",
            "עצמאות כלכלית": "financial_independence",
            "הייטק וטכנולוגיה": "tech"
        }
    },
    "תרבות ואמנות": {
        "id": "culture",
        "subcategories": {
            "אומנות": "arts",
            "תרבות": "culture",
            "ספרות": "literature",
            "קולנוע": "cinema",
            "מוזיקה": "music",
            "מורשת והנצחה": "heritage",
            "זהות יהודית": "jewish_identity"
        }
    },
    "מדע ומחקר": {
        "id": "science",
        "subcategories": {
            "מחקר אקדמי": "academic_research",
            "מדע וטכנולוגיה": "science_tech",
            "בינה מלאכותית": "ai",
            "חדשנות": "innovation"
        }
    },
    "סביבה": {
        "id": "environment",
        "subcategories": {
            "איכות הסביבה": "environment",
            "חקלאות ומזון": "agriculture",
            "אנרגיה": "energy",
            "רווחת בעלי חיים": "animal_welfare"
        }
    },
    "פריפריה ואזורי עדיפות": {
        "id": "periphery",
        "subcategories": {
            "פיתוח הנגב והגליל": "negev_galilee",
            "רשויות מקומיות": "municipalities",
            "חוסן קהילתי": "community_resilience",
            "עוטף עזה וצפון": "conflict_zones"
        }
    },
    "שוויון וזכויות": {
        "id": "equality",
        "subcategories": {
            "שוויון זכויות": "equal_rights",
            "זכויות אדם": "human_rights",
            "שוויון מגדרי": "gender_equality",
            "מיעוטים": "minorities"
        }
    },
    "בינלאומי": {
        "id": "international",
        "subcategories": {
            "שת\"פ בינלאומי": "international_coop",
            "יחסים ישראל-תפוצות": "israel_diaspora",
            "עזרה הומניטארית": "humanitarian_aid",
            "קשרים בינלאומיים": "international_relations"
        }
    },
    "תשתיות ובינוי": {
        "id": "infrastructure",
        "subcategories": {
            "מבנים": "buildings",
            "הצטיידות": "equipment",
            "ספורט": "sports",
            "תחבורה": "transport"
        }
    }
}

# === TARGET POPULATIONS - אוכלוסיות יעד ===
TARGET_POPULATIONS = {
    "נשים ונערות": "women",
    "יוצאי אתיופיה": "ethiopian",
    "חרדים": "haredi",
    "ערבים": "arab",
    "בדואים": "bedouin",
    "דרוזים": "druze",
    "עולים חדשים": "new_immigrants",
    "בני מיעוטים": "minorities",
    "LGBTQ+": "lgbtq",
    "ניצולי שואה": "holocaust_survivors",
    "אנשים עם מוגבלויות": "disabilities",
    "ילדים ונוער בסיכון": "youth_at_risk",
    "נוער וצעירים": "youth",
    "קשישים": "elderly",
    "משפחות חד הוריות": "single_parents",
    "אסירים ומשוחררים": "ex_prisoners",
    "חיילים בודדים": "lone_soldiers",
    "חיילים משוחררים": "discharged_soldiers",
    "תושבי פריפריה": "periphery_residents",
    "תושבי עוטף ודרום": "south_residents",
    "תושבי צפון": "north_residents",
    "מהגרי עבודה ופליטים": "refugees",
    "אנשים בהתמכרויות": "addiction",
    "הורים צעירים": "young_parents",
    "סטודנטים": "students",
}

# מילות מפתח לזיהוי אוכלוסיות מתוך הטקסט
POPULATION_KEYWORDS = {
    "women": ["נשים", "נערות", "אימהות", "מגדרי", "פמיני"],
    "ethiopian": ["אתיופ", "יוצאי אתיופיה", "העדה האתיופית"],
    "haredi": ["חרד", "אולטרא", "חרדים", "חרדית"],
    "arab": ["ערב", "ערבי", "ערבית", "מגזר ערבי", "חברה הערבית"],
    "bedouin": ["בדואי", "בדואים", "נגב בדואי"],
    "druze": ["דרוז", "דרוזי", "דרוזית"],
    "new_immigrants": ["עולים", "עלייה", "קליטה", "מהגרים"],
    "minorities": ["מיעוט", "מיעוטים", "שוליים"],
    "lgbtq": ["lgbtq", "להט", "גאווה", "טרנס", "הומו"],
    "holocaust_survivors": ["שואה", "ניצולי", "ניצולות"],
    "disabilities": ["מוגבל", "נכות", "צרכים מיוחדים", "אוטיז", "שיקום"],
    "youth_at_risk": ["נוער בסיכון", "ילדים בסיכון", "נשירה", "מנותקים"],
    "youth": ["נוער", "צעירים", "בני נוער", "נערים"],
    "elderly": ["קשיש", "זיקנה", "גיל הזהב", "גמלאים", "הגיל השלישי"],
    "single_parents": ["חד הורי", "חד-הורי", "הורה יחיד"],
    "ex_prisoners": ["אסיר", "משוחרר", "כלא", "עבריין"],
    "lone_soldiers": ["חייל בודד", "חיילים בודדים"],
    "discharged_soldiers": ["משוחררי צבא", "משוחררי צה", "שירות צבאי"],
    "periphery_residents": ["פריפריה", "פריפריאלי", "אזור עדיפות"],
    "south_residents": ["עוטף", "דרום", "שדרות", "אשקלון", "נתיבות"],
    "north_residents": ["צפון", "גליל", "גולן", "קריות"],
    "refugees": ["פליט", "מהגר עבודה", "מבקשי מקלט", "זרים"],
    "addiction": ["התמכרות", "סמים", "אלכוהול", "הימורים"],
    "young_parents": ["הורים צעירים", "הורות צעירה"],
    "students": ["סטודנט", "אקדמ", "אוניברסיט", "מכללה"],
}

# === TAG MAPPING - מיפוי תגיות אטלס לקטגוריות ===
TAG_TO_CATEGORY = {
    # חינוך
    "חינוך": "education",
    "השכלה גבוהה": "education",
    "הוראה": "education",
    "חינוך משלים": "education",
    "חינוך לגיל הרך": "education",
    "כללי (חינוך, השכלה והכשרה מקצועית)": "education",
    "תעסוקה והכשרה מקצועית": "employment",
    # רווחה
    "רווחה": "welfare",
    "ילדים ונוער בסיכון": "welfare",
    "ילדים ונוער": "welfare",
    "כללי (ילדים ונוער)": "welfare",
    "נשים ונערות": "welfare",
    "זיקנה": "welfare",
    "צרכים מיוחדים ומוגבלויות": "welfare",
    "עלייה וקליטה": "welfare",
    "מצוקה חברתית": "welfare",
    # קהילה
    "פיתוח קהילתי": "community",
    "פיתוח מנהיגות": "community",
    "יזמות חברתית": "community",
    "כללי (חברה משותפת)": "community",
    "קהילה וחברה": "community",
    # בריאות
    "בריאות": "health",
    "מחקר רפואי": "health",
    "רפואה": "health",
    "ציוד רפואי": "health",
    "כללי (בריאות ושירותי חירום)": "health",
    "בריאות ושירותי חירום": "health",
    # תרבות
    "תרבות": "culture",
    "אומנות": "culture",
    "כללי (תרבות ואמנות)": "culture",
    "מורשת או הנצחה": "culture",
    "זהות יהודית": "culture",
    "יהדות ישראלית": "culture",
    # מדע
    "מדע": "science",
    "כללי (מחקר, מדע וטכנולוגיה)": "science",
    "מדעי החברה": "science",
    # סביבה
    "איכות הסביבה": "environment",
    "רווחת בעלי חיים": "environment",
    # פריפריה
    "פיתוח הנגב והגליל": "periphery",
    "רשויות מקומיות": "periphery",
    "מבנים": "infrastructure",
    "הצטיידות": "infrastructure",
    "כללי (ספורט)": "infrastructure",
    "ספורט": "infrastructure",
    # שוויון
    "שוויון זכויות": "equality",
    "זכויות אדם": "equality",
    # בינלאומי
    "עזרה הומניטארית": "international",
    "כללי (קשרים בינלאומיים)": "international",
    # "הסברה" — תגית גורפת באטלס (265 פריטים), לא ממפה
    # שונות
    "מידע ותקשורת": "science",
    "משפט": "equality",
}


def classify_item(item):
    """מסווג פריט לקטגוריות לפי התגיות שלו"""
    categories = set()

    for tag in item.get("tags", []):
        tag = tag.strip()
        cat_id = TAG_TO_CATEGORY.get(tag)
        if cat_id:
            categories.add(cat_id)

    # ניסיון סיווג מהתיאור אם אין תגיות
    if not categories:
        desc = (item.get("description", "") + " " + item.get("title", "")).lower()
        if any(w in desc for w in ["חינוך", "לימוד", "סטודנט", "בית ספר"]):
            categories.add("education")
        if any(w in desc for w in ["נוער", "צעיר", "ילד"]):
            categories.add("welfare")
        if any(w in desc for w in ["קהילה", "קהילתי", "חברתי"]):
            categories.add("community")
        if any(w in desc for w in ["בריאות", "רפואה", "רפואי"]):
            categories.add("health")
        if any(w in desc for w in ["תרבות", "אמנות", "אמנים"]):
            categories.add("culture")
        if any(w in desc for w in ["מדע", "מחקר", "טכנולוגי"]):
            categories.add("science")

    return list(categories)


def detect_populations(item):
    """מזהה אוכלוסיות יעד מתוך הטקסט, התגיות והתיאור"""
    populations = set()
    text = (
        item.get("title", "") + " " +
        item.get("description", "") + " " +
        " ".join(item.get("tags", []))
    ).lower()

    for pop_id, keywords in POPULATION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            populations.add(pop_id)

    return list(populations)


def parse_deadline(deadline_str):
    """ממיר deadline לפורמט אחיד YYYY-MM-DD"""
    if not deadline_str:
        return None
    # DD-MM-YYYY
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", deadline_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return deadline_str


def parse_amount(amount_str):
    """מחלץ סכום מספרי"""
    if not amount_str:
        return None
    nums = re.findall(r"[\d,]+", amount_str)
    if nums:
        clean = nums[0].replace(",", "").strip()
        if clean and clean.isdigit():
            return int(clean)
    return None


def build_database():
    # טוען נתונים גולמיים
    atlas = json.load(open("atlas_full_export.json", "r", encoding="utf-8"))
    sources = json.load(open("grant_sources.json", "r", encoding="utf-8"))

    # טוען העשרת URLs (אם קיים)
    url_enrichment = {}
    try:
        enrich = json.load(open("grants_urls_enrichment.json", "r", encoding="utf-8"))
        for item in enrich.get("items", []):
            url_enrichment[item["title_match"]] = item
        print(f"URL enrichment: {len(url_enrichment)} items loaded")
    except FileNotFoundError:
        pass

    print(f"Atlas items: {len(atlas['items'])}")

    # === בונה פריטים מסודרים ===
    db_items = []
    for i, item in enumerate(atlas["items"]):
        categories = classify_item(item)

        # Original tags cleanup
        clean_tags = [
            t.strip() for t in item.get("tags", [])
            if t.strip() and len(t.strip()) > 2
            and t.strip() not in ["work", "visibility_off", "star_border",
                                   "star_outline", "account_balance",
                                   "volunteer_activism", "bookmark_border"]
        ]

        populations = detect_populations(item)

        # העשרה מקובץ URLs
        enriched = url_enrichment.get(item["title"], {})
        item_url = enriched.get("url", item.get("url", ""))
        item_funder = enriched.get("funder", "")

        db_item = {
            "id": i + 1,
            "title": item["title"],
            "type": item["type"],  # kok / fund / business / endowment
            "is_new": item.get("is_new", False),
            "url": item_url,
            "description": item.get("description", ""),
            "deadline": parse_deadline(item.get("deadline", "")),
            "deadline_raw": item.get("deadline", ""),
            "amount": parse_amount(item.get("amount", "")),
            "amount_raw": item.get("amount", ""),
            "categories": categories,
            "target_populations": populations,
            "tags": clean_tags,
            "source": "atlas",
            "status": "open" if item.get("deadline") else "ongoing",
            "eligible": [],  # ימולא בעתיד
            "funder": item_funder,
        }

        db_items.append(db_item)

    # === בונה מאגר מקורות סריקה ===
    db_sources = []
    source_id = 0
    for sheet_name, rows in sources.items():
        if sheet_name == "סדר עדיפויות לסורק":
            continue
        for row in rows:
            source_id += 1
            db_sources.append({
                "id": source_id,
                "name": row.get("שם המקור", ""),
                "url": row.get("URL", ""),
                "frequency": row.get("תדירות סריקה", ""),
                "topics": row.get("תחומים עיקריים", ""),
                "eligibility": row.get("הערות / תנאי סף", ""),
                "main_deadline": row.get("דדליין מרכזי", ""),
                "priority": row.get("עדיפות סורק", ""),
                "layer": row.get("שכבה", ""),
                "source_type": sheet_name,
            })

    # === סטטיסטיקות ===
    cat_stats = {}
    for item in db_items:
        for cat in item["categories"]:
            cat_stats[cat] = cat_stats.get(cat, 0) + 1

    type_stats = {}
    for item in db_items:
        t = item["type"]
        type_stats[t] = type_stats.get(t, 0) + 1

    pop_stats = {}
    for item in db_items:
        for pop in item["target_populations"]:
            pop_stats[pop] = pop_stats.get(pop, 0) + 1

    # === בניית ה-DB הסופי ===
    database = {
        "version": "2.0",
        "created": "2026-05-04",
        "description": "מאגר קולות קוראים ומקורות מימון — מערכת גיוס משאבים אוניברסלית",
        "stats": {
            "total_items": len(db_items),
            "by_type": type_stats,
            "by_category": cat_stats,
            "by_population": pop_stats,
            "total_sources": len(db_sources),
            "items_with_deadline": sum(1 for i in db_items if i["deadline"]),
            "items_with_population": sum(1 for i in db_items if i["target_populations"]),
        },
        "taxonomy": TAXONOMY,
        "target_populations": TARGET_POPULATIONS,
        "items": db_items,
        "sources": db_sources,
    }

    # שמירה
    with open("grants_database.json", "w", encoding="utf-8") as f:
        json.dump(database, f, ensure_ascii=False, indent=2)

    print(f"\n=== Database Built (v2.0) ===")
    print(f"Total items: {len(db_items)}")
    print(f"  By type: {type_stats}")
    print(f"  By category: {dict(sorted(cat_stats.items(), key=lambda x: -x[1]))}")
    print(f"  By population: {dict(sorted(pop_stats.items(), key=lambda x: -x[1]))}")
    print(f"  With deadline: {sum(1 for i in db_items if i['deadline'])}")
    print(f"  With population: {sum(1 for i in db_items if i['target_populations'])}")
    print(f"Total sources: {len(db_sources)}")
    print(f"\nSaved: data/grants_database.json")

    # דוגמאות
    print("\n=== Sample items ===")
    for item in db_items[:5]:
        print(f"\n  [{item['type']}] {item['title'][:70]}")
        print(f"  Categories: {item['categories']}")
        print(f"  Populations: {item['target_populations']}")
        print(f"  Deadline: {item['deadline'] or '-'}")


if __name__ == "__main__":
    build_database()
