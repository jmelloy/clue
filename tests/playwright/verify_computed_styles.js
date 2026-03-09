const { chromium } = require("playwright-core");

const BASE_URL = process.env.BASE_URL || "http://localhost:5173";
const CHROME_PATH = "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome";

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: CHROME_PATH });

  const viewport = { width: 375, height: 667 }; // iPhone SE
  console.log(`Testing at ${viewport.width}x${viewport.height} (iPhone SE)\n`);

  const context = await browser.newContext({ viewport });
  const page = await context.newPage();

  // Create a game and get to the board
  await page.goto(BASE_URL);
  await sleep(2000);
  await page.locator(".game-card").first().click();
  await sleep(1000);
  await page.locator('input[placeholder="Your name"]').first().fill("TestPlayer");
  await page.locator('button:has-text("Start Game")').first().click();
  await sleep(3000);
  const addBtn = page.locator('button:has-text("Add Agent")').first();
  await addBtn.click(); await sleep(1500);
  await addBtn.click(); await sleep(1500);
  await page.locator('button:has-text("Begin the Investigation")').click();
  await sleep(5000);

  // Check computed styles for key elements
  const results = await page.evaluate(() => {
    function getComputed(selector, props) {
      const el = document.querySelector(selector);
      if (!el) return { selector, found: false };
      const cs = getComputedStyle(el);
      const result = { selector, found: true };
      for (const p of props) {
        result[p] = cs.getPropertyValue(p);
      }
      result._width = el.offsetWidth;
      result._scrollWidth = el.scrollWidth;
      result._overflow = el.scrollWidth > el.offsetWidth;
      return result;
    }

    return [
      getComputed('#clue-app', ['box-sizing', 'max-width', 'padding', 'overflow-x']),
      getComputed('.board-container', ['box-sizing', 'width', 'max-width']),
      getComputed('.board-map', ['padding']),
      getComputed('.main-layout', ['grid-template-columns', 'width']),
      getComputed('.game-header', ['padding', 'gap', 'flex-wrap']),
      getComputed('.header-left h1', ['font-size']),
      getComputed('.hand-card', ['width', 'font-size', 'box-sizing']),
      getComputed('.sidebar-column', ['max-width', 'width']),
      getComputed('.sidebar-panel', ['padding']),
      getComputed('.status-banner', ['font-size', 'padding']),
      getComputed('.dice', ['width', 'height', 'font-size']),
      getComputed('.game-id-label', ['display']),
    ];
  });

  let issues = 0;
  for (const r of results) {
    if (!r.found) {
      console.log(`  [SKIP] ${r.selector} — not found`);
      continue;
    }
    const overflowFlag = r._overflow ? ' ⚠️ OVERFLOW' : '';
    console.log(`  ${r.selector} (${r._width}px, scroll: ${r._scrollWidth}px)${overflowFlag}`);
    delete r.selector; delete r.found; delete r._width; delete r._scrollWidth; delete r._overflow;
    for (const [k, v] of Object.entries(r)) {
      console.log(`    ${k}: ${v}`);
    }
    if (r._overflow) issues++;
  }

  // Check specific expectations
  console.log("\n--- Validation ---");

  const checks = await page.evaluate(() => {
    const cs = (sel) => { const el = document.querySelector(sel); return el ? getComputedStyle(el) : null; };
    const checks = [];

    // #clue-app must be border-box
    const app = cs('#clue-app');
    checks.push({ name: '#clue-app box-sizing', expected: 'border-box', actual: app?.boxSizing, pass: app?.boxSizing === 'border-box' });

    // .board-container must be border-box
    const bc = cs('.board-container');
    checks.push({ name: '.board-container box-sizing', expected: 'border-box', actual: bc?.boxSizing, pass: bc?.boxSizing === 'border-box' });

    // .main-layout must be single column at 375px
    const ml = cs('.main-layout');
    const isSingleCol = ml && !ml.gridTemplateColumns.includes(' ');
    checks.push({ name: '.main-layout single column', expected: 'single column', actual: ml?.gridTemplateColumns, pass: isSingleCol });

    // .game-header must wrap on mobile
    const gh = cs('.game-header');
    checks.push({ name: '.game-header flex-wrap', expected: 'wrap', actual: gh?.flexWrap, pass: gh?.flexWrap === 'wrap' });

    // .hand-card should be 60px at 375px (390px breakpoint)
    const hc = cs('.hand-card');
    const hcWidth = parseFloat(hc?.width);
    checks.push({ name: '.hand-card width ≤68px', expected: '≤68px', actual: hc?.width, pass: hcWidth <= 68 });

    // .game-id-label should be hidden at 375px (390px breakpoint)
    const gid = cs('.game-id-label');
    checks.push({ name: '.game-id-label hidden', expected: 'none', actual: gid?.display, pass: gid?.display === 'none' });

    // .dice should be 24x24 at 375px (500px breakpoint)
    const dice = cs('.dice');
    checks.push({ name: '.dice width 24px', expected: '24px', actual: dice?.width, pass: dice ? parseFloat(dice.width) <= 24 : false });

    // No element wider than viewport
    let widestEl = null;
    let widestWidth = 0;
    document.querySelectorAll('.game-board *').forEach(el => {
      const w = el.getBoundingClientRect().width;
      if (w > widestWidth) { widestWidth = w; widestEl = el.className?.toString()?.substring(0, 40) || el.tagName; }
    });
    checks.push({ name: 'widest element ≤ viewport', expected: '≤375px', actual: `${Math.round(widestWidth)}px (${widestEl})`, pass: widestWidth <= 375 });

    return checks;
  });

  let failures = 0;
  for (const c of checks) {
    const status = c.pass ? '✅' : '❌';
    if (!c.pass) failures++;
    console.log(`  ${status} ${c.name}: expected ${c.expected}, got ${c.actual}`);
  }

  console.log(`\n${failures === 0 ? 'All checks passed!' : `${failures} check(s) FAILED`}`);

  await browser.close();
  process.exit(failures > 0 ? 1 : 0);
}

main().catch(err => { console.error(err); process.exit(1); });
