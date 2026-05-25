/**
 * crawl-fixtures.mjs
 *
 * עבור כל fixture ב-examples.json:
 *   1. פותח את ה-source URL
 *   2. מחלץ לינקים רלוונטיים (PDF / Google Form / דפי הגשה)
 *   3. נכנס לכל לינק רלוונטי — עד שמגיע ל"עלה" (אין יותר לינקים/קבצים)
 *   4. מדפיס את הנתיב המלא + מה מצא בסוף
 *   5. אם ה-fixture כבר מוגדר עם expected_attachment_url / expected_application_url — משווה
 *
 * הרצה: node test-fixtures/opportunities/crawl-fixtures.mjs
 * אפשר לסנן: node test-fixtures/opportunities/crawl-fixtures.mjs btl-funds
 */

import { readFileSync, writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import puppeteer from "puppeteer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const EXAMPLES_PATH = join(__dirname, "examples.json");

// --- הגדרות ---
const MAX_DEPTH = 4;          // עומק crawl מקסימלי
const FETCH_TIMEOUT = 10000;  // 10 שניות לכל בקשה

// דומיינים שדורשים Puppeteer (SPA / JS-rendered)
const PUPPETEER_DOMAINS = [
  "gov.il",
  "mof.gov.il",
  "tmichot.mof.gov.il",
];

function needsPuppeteer(url) {
  return PUPPETEER_DOMAINS.some((d) => url.includes(d));
}

// דפוסים שמצביעים על "לינק הגשה" או "קובץ מקור"
const APPLICATION_PATTERNS = [
  /google\.com\/forms/i,
  /forms\.gle/i,
  /typeform\.com/i,
  /jotform\.com/i,
  /docs\.google\.com/i,
  /drive\.google\.com/i,
];

const ATTACHMENT_PATTERNS = [
  /\.pdf(\?|$)/i,
  /\.docx?(\?|$)/i,
  /\.xlsx?(\?|$)/i,
];

const SKIP_PATTERNS = [
  /facebook\.com/i,
  /instagram\.com/i,
  /twitter\.com/i,
  /linkedin\.com/i,
  /youtube\.com/i,
  /whatsapp/i,
  /mailto:/i,
  /tel:/i,
  /javascript:/i,
];

// --- פונקציות עזר ---

function isApplicationUrl(url) {
  return APPLICATION_PATTERNS.some((p) => p.test(url));
}

function isAttachmentUrl(url) {
  return ATTACHMENT_PATTERNS.some((p) => p.test(url));
}

function isLeafUrl(url) {
  return isApplicationUrl(url) || isAttachmentUrl(url);
}

function shouldSkip(url) {
  return SKIP_PATTERNS.some((p) => p.test(url));
}

function resolveUrl(href, base) {
  try {
    return new URL(href, base).href;
  } catch {
    return null;
  }
}

let _browser = null;
async function getBrowser() {
  if (!_browser) {
    _browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
  }
  return _browser;
}

async function fetchHtmlPuppeteer(url) {
  try {
    const browser = await getBrowser();
    const page = await browser.newPage();
    await page.setUserAgent(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
    );
    await page.goto(url, { waitUntil: "networkidle2", timeout: FETCH_TIMEOUT });
    const html = await page.content();
    const finalUrl = page.url();
    await page.close();
    return { html, finalUrl };
  } catch (e) {
    return { error: e.message };
  }
}

async function fetchHtml(url) {
  if (needsPuppeteer(url)) {
    process.stdout.write(" [puppeteer]");
    return fetchHtmlPuppeteer(url);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "he,en;q=0.9",
      },
      redirect: "follow",
    });
    clearTimeout(timer);
    const contentType = res.headers.get("content-type") || "";
    if (!res.ok) return { error: `HTTP ${res.status}`, finalUrl: res.url };
    if (!contentType.includes("text/html")) {
      return { html: null, finalUrl: res.url, contentType };
    }
    const html = await res.text();
    return { html, finalUrl: res.url };
  } catch (e) {
    clearTimeout(timer);
    return { error: e.message };
  }
}

function extractLinks(html, baseUrl) {
  const links = new Set();
  // href מ-<a>
  const hrefRe = /href=["']([^"']+)["']/gi;
  let m;
  while ((m = hrefRe.exec(html)) !== null) {
    const resolved = resolveUrl(m[1], baseUrl);
    if (resolved && !shouldSkip(resolved)) links.add(resolved);
  }
  // src מ-<iframe> (Google Forms מוטמע)
  const srcRe = /src=["']([^"']+)["']/gi;
  while ((m = srcRe.exec(html)) !== null) {
    const resolved = resolveUrl(m[1], baseUrl);
    if (resolved && isApplicationUrl(resolved)) links.add(resolved);
  }
  return [...links];
}

function classifyLink(url, baseUrl) {
  if (isApplicationUrl(url)) return "application_form";
  if (isAttachmentUrl(url)) return "attachment";
  // לינק פנימי — אותו דומיין
  try {
    const base = new URL(baseUrl);
    const target = new URL(url);
    if (target.hostname === base.hostname) return "internal";
  } catch {}
  return "external";
}

// --- crawl רקורסיבי ---

async function crawl(url, depth = 0, visited = new Set(), path = []) {
  if (depth > MAX_DEPTH) return { url, depth, result: "max_depth_reached", path };
  if (visited.has(url)) return { url, depth, result: "already_visited", path };
  visited.add(url);

  const currentPath = [...path, url];
  process.stdout.write(`${"  ".repeat(depth)}→ ${url}\n`);

  // אם זה כבר עלה — מחזירים
  if (isLeafUrl(url)) {
    return {
      url,
      depth,
      result: isApplicationUrl(url) ? "application_form" : "attachment",
      path: currentPath,
    };
  }

  const { html, finalUrl, contentType, error } = await fetchHtml(url);

  if (error) return { url, depth, result: "fetch_error", error, path: currentPath };
  if (!html) return { url, depth, result: "non_html", contentType, path: currentPath };

  const links = extractLinks(html, finalUrl || url);
  const leaves = [];

  for (const link of links) {
    const type = classifyLink(link, finalUrl || url);
    if (type === "application_form" || type === "attachment") {
      leaves.push({ url: link, type, path: [...currentPath, link] });
    }
  }

  // אם מצאנו עלים ישירים — מחזירים אותם
  if (leaves.length > 0) {
    return { url, depth, result: "found_leaves", leaves, path: currentPath };
  }

  // אם לא — נכנסים ללינקים פנימיים
  const internalLinks = links
    .filter((l) => classifyLink(l, finalUrl || url) === "internal")
    .slice(0, 5); // מגבילים ל-5 לינקים פנימיים לכל דף

  const results = [];
  for (const link of internalLinks) {
    const sub = await crawl(link, depth + 1, visited, currentPath);
    if (sub.result === "found_leaves" || sub.result === "application_form" || sub.result === "attachment") {
      results.push(sub);
    }
  }

  if (results.length > 0) return { url, depth, result: "found_via_internal", results, path: currentPath };
  return { url, depth, result: "nothing_found", path: currentPath };
}

// --- השוואה ל-expected ---

function collectLeaves(crawlResult) {
  const found = [];
  if (!crawlResult) return found;
  if (crawlResult.result === "application_form" || crawlResult.result === "attachment") {
    found.push({ url: crawlResult.url, type: crawlResult.result });
  }
  if (crawlResult.leaves) {
    for (const l of crawlResult.leaves) found.push({ url: l.url, type: l.type });
  }
  if (crawlResult.results) {
    for (const r of crawlResult.results) found.push(...collectLeaves(r));
  }
  return found;
}

function compare(fixture, crawlResult) {
  const found = collectLeaves(crawlResult);
  const issues = [];

  if (fixture.expected_attachment_url) {
    const match = found.find((f) => f.url === fixture.expected_attachment_url);
    if (match) {
      issues.push({ type: "PASS", field: "expected_attachment_url", url: fixture.expected_attachment_url });
    } else {
      issues.push({ type: "FAIL", field: "expected_attachment_url", expected: fixture.expected_attachment_url, actual: found });
    }
  }

  if (fixture.expected_application_url) {
    const match = found.find((f) => f.url === fixture.expected_application_url);
    if (match) {
      issues.push({ type: "PASS", field: "expected_application_url", url: fixture.expected_application_url });
    } else {
      issues.push({ type: "FAIL", field: "expected_application_url", expected: fixture.expected_application_url, actual: found });
    }
  }

  return { found, issues };
}

// --- ריצה ראשית ---

async function main() {
  const filterId = process.argv[2] || null;
  const examples = JSON.parse(readFileSync(EXAMPLES_PATH, "utf-8"));
  const results = {};

  for (const fixture of examples) {
    if (filterId && fixture.id !== filterId) continue;
    if (fixture.expected_status === "expired") {
      console.log(`\n⏭  SKIP [${fixture.id}] — expired`);
      continue;
    }

    console.log(`\n${"=".repeat(60)}`);
    console.log(`🔍 [${fixture.id}] ${fixture.name}`);
    console.log(`   source: ${fixture.source}`);

    const crawlResult = await crawl(fixture.source);
    const { found, issues } = compare(fixture, crawlResult);

    console.log(`\n   נמצא:`);
    if (found.length === 0) {
      console.log(`   (כלום)`);
    } else {
      for (const f of found) {
        console.log(`   [${f.type}] ${f.url}`);
      }
    }

    if (issues.length > 0) {
      console.log(`\n   השוואה:`);
      for (const issue of issues) {
        if (issue.type === "PASS") {
          console.log(`   ✅ PASS — ${issue.field}`);
        } else {
          console.log(`   ❌ FAIL — ${issue.field}`);
          console.log(`      expected: ${issue.expected}`);
          console.log(`      actual:   ${issue.actual.map((a) => a.url).join(", ") || "(כלום)"}`);
        }
      }
    }

    results[fixture.id] = { found, issues };
  }

  // שמירת תוצאות
  const outPath = join(__dirname, "crawl-results.json");
  writeFileSync(outPath, JSON.stringify(results, null, 2), "utf-8");
  console.log(`\n\nתוצאות נשמרו ב: ${outPath}`);

  if (_browser) await _browser.close();
}

main().catch(console.error);
