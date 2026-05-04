// Atlas Grants Full Scraper — Console Script
// הדביקי את זה ב-F12 > Console ולחצי Enter

(async () => {
  const ALL_ITEMS = [];
  let pageNum = 0;
  let scrollAttempts = 0;
  const MAX_SCROLL_ATTEMPTS = 50;

  console.log("=== Atlas Scraper Started ===");

  // פונקציה לחילוץ כרטיסים מהדף
  function extractCards() {
    const cards = [];
    const seen = new Set();

    // מחפשים כרטיסים לפי הטקסט "הוסף למועדפים" — כל כרטיס מכיל את זה
    const allDivs = document.querySelectorAll("div");

    for (const div of allDivs) {
      const text = div.innerText || "";

      // כרטיס אטלס: מכיל "הוסף למועדפים" + "שיתוף" + תוכן
      if (
        text.includes("הוסף למועדפים") &&
        text.includes("שיתוף") &&
        text.length > 100 &&
        text.length < 5000
      ) {
        // בדיקה שזה לא container ענק
        const childDivs = div.querySelectorAll("div");
        if (childDivs.length > 80) continue;

        // בדיקת כפילות
        const key = text.substring(0, 120);
        if (seen.has(key)) continue;
        seen.add(key);

        const lines = text
          .split("\n")
          .map((l) => l.trim())
          .filter((l) => l.length > 0);

        // סינון שורות UI
        const contentLines = lines.filter(
          (l) =>
            !l.includes("הוסף למועדפים") &&
            !l.includes("הסתרה") &&
            !l.includes("הוסף לתוכנית") &&
            !l.includes("שיתוף") &&
            l !== "New" &&
            l !== "Endowment icon"
        );

        // סוג
        let type = "unknown";
        if (lines.some((l) => l === "קו׳׳ק")) type = "kok";
        else if (lines.some((l) => l === "קרן")) type = "fund";
        else if (lines.some((l) => l === "עסק")) type = "business";
        else if (lines.some((l) => l === "הקדש")) type = "endowment";

        // שם — השורה הראשונה שהיא לא סוג
        let title = contentLines.find(
          (l) =>
            l.length > 10 && l !== "קו׳׳ק" && l !== "קרן" && l !== "עסק" && l !== "הקדש"
        ) || contentLines[0] || "";

        // Deadline
        let deadline = "";
        const dlMatch = text.match(/Deadline:\s*([\d\-]+)/);
        if (dlMatch) deadline = dlMatch[1];

        // תיאור
        const descLines = contentLines.filter(
          (l) =>
            l.length > 40 &&
            l !== title &&
            !l.includes("Deadline") &&
            l !== "קו׳׳ק" &&
            l !== "קרן"
        );
        const description = descLines.join(" ").substring(0, 1000);

        // תגיות — שורות קצרות
        const tags = contentLines.filter(
          (l) =>
            l.length > 3 &&
            l.length < 50 &&
            !l.includes("Deadline") &&
            l !== title &&
            !descLines.includes(l) &&
            l !== "קו׳׳ק" &&
            l !== "קרן" &&
            l !== "עסק" &&
            l !== "הקדש"
        );

        // New
        const isNew = lines.includes("New");

        // סכום
        let amount = "";
        const amtMatch = text.match(/([\d,.]+)\s*(?:₪|ש"ח|שקל|דולר|\$|אירו)/);
        if (amtMatch) amount = amtMatch[0];

        if (title.length > 5) {
          cards.push({
            title: title,
            type: type,
            is_new: isNew,
            description: description,
            deadline: deadline,
            amount: amount,
            tags: tags.slice(0, 8),
            full_text: text.substring(0, 2500),
          });
        }
      }
    }

    return cards;
  }

  // פונקציה לגלילה
  function scrollDown() {
    return new Promise((resolve) => {
      window.scrollTo(0, document.documentElement.scrollHeight);
      setTimeout(resolve, 2000);
    });
  }

  // סריקה ראשונית
  let prevCount = 0;

  while (scrollAttempts < MAX_SCROLL_ATTEMPTS) {
    pageNum++;
    const cards = extractCards();

    if (cards.length > prevCount) {
      console.log(
        `[Page ${pageNum}] Found ${cards.length} items (+${cards.length - prevCount} new)`
      );
      // מוסיפים רק חדשים
      for (const card of cards) {
        if (!ALL_ITEMS.find((x) => x.title === card.title)) {
          ALL_ITEMS.push(card);
        }
      }
      prevCount = cards.length;
      scrollAttempts = 0;
    } else {
      scrollAttempts++;
      console.log(
        `[Page ${pageNum}] No new items (attempt ${scrollAttempts}/${MAX_SCROLL_ATTEMPTS})`
      );

      // מנסים ללחוץ "הבא" / "Load More"
      const btns = document.querySelectorAll("button, a");
      let clicked = false;
      for (const btn of btns) {
        const t = (btn.innerText || "").trim();
        const label = btn.getAttribute("aria-label") || "";
        if (
          (t === ">" ||
            t === "הבא" ||
            t === "Next" ||
            t.includes("הצג עוד") ||
            t.includes("Load") ||
            label.includes("next") ||
            label.includes("הבא")) &&
          !btn.disabled &&
          btn.offsetParent !== null
        ) {
          btn.click();
          clicked = true;
          console.log(`  -> Clicked: "${t || label}"`);
          scrollAttempts = 0;
          await new Promise((r) => setTimeout(r, 3000));
          break;
        }
      }

      if (!clicked && scrollAttempts >= 5) {
        console.log("No more content found. Stopping.");
        break;
      }
    }

    await scrollDown();
  }

  // סיכום
  console.log(`\n=== DONE! Total: ${ALL_ITEMS.length} unique items ===\n`);

  // הורדה כקובץ JSON
  const exportData = {
    metadata: {
      source: "app.atlas-grants.com",
      url: window.location.href,
      scraped_date: new Date().toISOString(),
      total_items: ALL_ITEMS.length,
    },
    items: ALL_ITEMS,
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `atlas_full_export_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  console.log("File downloaded! Check your Downloads folder.");

  // גם מציג בconsole
  console.log(JSON.stringify(exportData, null, 2));
})();
