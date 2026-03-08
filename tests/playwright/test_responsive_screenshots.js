const { chromium } = require("playwright-core");

const BASE_URL = process.env.BASE_URL || "http://localhost:5173";
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR || "./screenshots/responsive";
const CHROME_PATH =
  process.env.CHROME_PATH ||
  "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const VIEWPORTS = {
  "iphone-se": { width: 375, height: 667 },
  "iphone-14": { width: 390, height: 844 },
  "iphone-14-pro-max": { width: 430, height: 932 },
  "pixel-7": { width: 412, height: 915 },
  "ipad-mini": { width: 768, height: 1024 },
  "ipad-pro": { width: 1024, height: 1366 },
  desktop: { width: 1280, height: 900 },
};

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
  });

  const results = [];

  for (const [device, viewport] of Object.entries(VIEWPORTS)) {
    console.log(`\n=== ${device} (${viewport.width}x${viewport.height}) ===`);

    const context = await browser.newContext({ viewport });
    const page = await context.newPage();

    try {
      await page.goto(BASE_URL);
      await sleep(2000);

      // Click Clue game card
      await page.locator(".game-card").first().click();
      await sleep(1000);

      // Create game
      await page.locator('input[placeholder="Your name"]').first().fill("TestPlayer");
      await page.locator('button:has-text("Start Game")').first().click();
      await sleep(3000);

      // Add agents & start
      const addBtn = page.locator('button:has-text("Add Agent")').first();
      await addBtn.click();
      await sleep(1500);
      await addBtn.click();
      await sleep(1500);
      await page.locator('button:has-text("Begin the Investigation")').click();
      await sleep(5000);

      // Measure with overflow-x removed temporarily
      const m = await page.evaluate(() => {
        // Temporarily remove overflow-x: hidden to see true content width
        const html = document.documentElement;
        const body = document.body;
        const app = document.getElementById("clue-app");

        const origHtml = html.style.overflowX;
        const origBody = body.style.overflowX;
        const origApp = app ? app.style.overflowX : "";

        html.style.overflowX = "visible";
        body.style.overflowX = "visible";
        if (app) app.style.overflowX = "visible";

        const trueScrollWidth = Math.max(
          html.scrollWidth,
          body.scrollWidth,
          app ? app.scrollWidth : 0
        );

        // Find elements wider than viewport
        const wideElements = [];
        document.querySelectorAll("*").forEach((el) => {
          const rect = el.getBoundingClientRect();
          if (rect.width > window.innerWidth + 2) {
            wideElements.push({
              tag: el.tagName,
              class: el.className.toString().substring(0, 60),
              width: Math.round(rect.width),
              left: Math.round(rect.left),
              right: Math.round(rect.right),
            });
          }
        });

        // Restore
        html.style.overflowX = origHtml;
        body.style.overflowX = origBody;
        if (app) app.style.overflowX = origApp;

        // Specific element measurements
        const mainLayout = document.querySelector(".main-layout");
        const sidebar = document.querySelector(".sidebar-column");
        const boardContainer = document.querySelector(".board-container");
        const cardHand = document.querySelector(".card-hand");
        const gameHeader = document.querySelector(".game-header");
        const actionSection = document.querySelector(".action-section");
        const suggestionForm = document.querySelector(".suggestion-form");
        const detectiveNotes = document.querySelector(".detective-notes");

        function measure(el) {
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return { width: Math.round(r.width), scrollWidth: el.scrollWidth, left: Math.round(r.left), right: Math.round(r.right) };
        }

        return {
          viewportWidth: window.innerWidth,
          trueScrollWidth,
          overflow: trueScrollWidth > window.innerWidth,
          overflowAmount: trueScrollWidth - window.innerWidth,
          mainLayout: measure(mainLayout),
          sidebar: measure(sidebar),
          boardContainer: measure(boardContainer),
          cardHand: measure(cardHand),
          gameHeader: measure(gameHeader),
          actionSection: measure(actionSection),
          suggestionForm: measure(suggestionForm),
          detectiveNotes: measure(detectiveNotes),
          wideElements: wideElements.slice(0, 10),
        };
      });

      await page.screenshot({ path: `${SCREENSHOT_DIR}/gameboard-${device}.png`, fullPage: true });

      console.log(`  Viewport: ${m.viewportWidth}px`);
      console.log(`  True scroll width: ${m.trueScrollWidth}px (overflow: ${m.overflow}, +${m.overflowAmount}px)`);
      if (m.mainLayout) console.log(`  Main layout: ${JSON.stringify(m.mainLayout)}`);
      if (m.boardContainer) console.log(`  Board container: ${JSON.stringify(m.boardContainer)}`);
      if (m.cardHand) console.log(`  Card hand: ${JSON.stringify(m.cardHand)}`);
      if (m.gameHeader) console.log(`  Game header: ${JSON.stringify(m.gameHeader)}`);
      if (m.sidebar) console.log(`  Sidebar: ${JSON.stringify(m.sidebar)}`);
      if (m.actionSection) console.log(`  Action section: ${JSON.stringify(m.actionSection)}`);
      if (m.suggestionForm) console.log(`  Suggestion form: ${JSON.stringify(m.suggestionForm)}`);
      if (m.detectiveNotes) console.log(`  Detective notes: ${JSON.stringify(m.detectiveNotes)}`);
      if (m.wideElements.length > 0) {
        console.log(`  Wide elements (>${m.viewportWidth}px):`);
        for (const el of m.wideElements) {
          console.log(`    ${el.tag}.${el.class}: ${el.width}px [${el.left} - ${el.right}]`);
        }
      }

      if (m.overflow) {
        results.push({ device, overflowAmount: m.overflowAmount, wideElements: m.wideElements });
      }
    } catch (err) {
      console.log(`  ERROR: ${err.message}`);
    }

    await context.close();
  }

  await browser.close();

  console.log("\n\n========== SUMMARY ==========");
  if (results.length === 0) {
    console.log("No overflow issues detected (even with overflow-x: hidden removed)!");
  } else {
    console.log(`Found ${results.length} viewport(s) with overflow:`);
    for (const r of results) {
      console.log(`\n  ${r.device}: overflow by ${r.overflowAmount}px`);
      for (const el of r.wideElements) {
        console.log(`    ${el.tag}.${el.class}: ${el.width}px`);
      }
    }
  }
}

main().catch((err) => {
  console.error("Error:", err);
  process.exit(1);
});
