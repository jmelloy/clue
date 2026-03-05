#!/usr/bin/env node
/**
 * Screenshot capture script for the Clue and Texas Hold'em game server.
 *
 * Captures screenshots of various game states for documentation purposes.
 * Requires a running frontend (default: http://localhost:5173) and backend.
 *
 * Usage:
 *   node scripts/take_screenshots.js [--base-url http://localhost:5173] [--out screenshots/]
 *
 * Prerequisites:
 *   npm install  (from repo root — installs @playwright/test)
 *   npx playwright install chromium
 */

const { chromium } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const args = process.argv.slice(2);
const getArg = (flag, def) => {
  const idx = args.indexOf(flag);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : def;
};

const BASE_URL = getArg("--base-url", "http://localhost:5173");
const OUT_DIR = getArg(
  "--out",
  path.join(__dirname, "..", "screenshots")
);

fs.mkdirSync(OUT_DIR, { recursive: true });

function outPath(name) {
  return path.join(OUT_DIR, name);
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const browser = await chromium.launch({ headless: true });

  try {
    // ─── 1. Clue Lobby ────────────────────────────────────────────────────────
    console.log("📸 01 — Clue lobby");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      await page.waitForSelector("h1", { timeout: 10000 });
      await sleep(500); // let animations settle
      await page.screenshot({ path: outPath("01-lobby-clue.png"), fullPage: false });
      await page.close();
    }

    // ─── 2. Hold'em Lobby ────────────────────────────────────────────────────
    console.log("📸 02 — Hold'em lobby");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      await page.waitForSelector("h1", { timeout: 10000 });
      // Switch to Hold'em tab
      const holdemTab = page.locator(".game-type-btn").filter({ hasText: "Hold'em" });
      if (await holdemTab.isVisible().catch(() => false)) {
        await holdemTab.click();
        await sleep(400);
      }
      await sleep(500);
      await page.screenshot({ path: outPath("02-lobby-holdem.png"), fullPage: false });
      await page.close();
    }

    // ─── 3. Clue Waiting Room ────────────────────────────────────────────────
    console.log("📸 03 — Clue waiting room");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      await page.waitForSelector('input[placeholder="Your alias"]', { timeout: 10000 });
      await page.locator(".card-create").locator('input[placeholder="Your alias"]').fill("Detective");
      await page.locator(".card-create").getByRole("button", { name: "Open the Case" }).click();
      await page.waitForSelector(".waiting-room, .suspects-gathering, h2:has-text('Gathering'), [class*=\"waiting\"]", { timeout: 15000 });
      // Add a couple of agents so the room looks populated
      const addBtn = page.getByRole("button", { name: "Add Agent" }).first();
      if (await addBtn.isVisible().catch(() => false)) {
        await addBtn.click();
        await sleep(800);
        await addBtn.click();
        await sleep(800);
      }
      await sleep(500);
      await page.screenshot({ path: outPath("03-clue-waiting-room.png"), fullPage: false });
      await page.close();
    }

    // ─── 4. Clue Game Board ──────────────────────────────────────────────────
    console.log("📸 04 — Clue game board");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      await page.waitForSelector('input[placeholder="Your alias"]', { timeout: 10000 });
      await page.locator(".card-create").locator('input[placeholder="Your alias"]').fill("Detective");
      await page.locator(".card-create").getByRole("button", { name: "Open the Case" }).click();
      await page.waitForSelector(".waiting-room, [class*=\"waiting\"]", { timeout: 15000 });

      // Add 5 agents to fill the game
      const addBtn = page.getByRole("button", { name: "Add Agent" }).first();
      for (let i = 0; i < 5; i++) {
        if (await addBtn.isVisible().catch(() => false)) {
          await addBtn.click();
          await sleep(600);
        }
      }
      // Start the game
      const startBtn = page.getByRole("button", { name: "Begin the Investigation" });
      if (await startBtn.isEnabled().catch(() => false)) {
        await startBtn.click();
      }
      await page.waitForSelector(".game-board, .board-map", { timeout: 20000 });
      await sleep(1500); // let the board render fully
      await page.screenshot({ path: outPath("04-clue-game-board.png"), fullPage: false });
      await page.close();
    }

    // ─── 5. Clue Game Board — Detective Notes open ───────────────────────────
    console.log("📸 05 — Clue game board with detective notes");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      await page.waitForSelector('input[placeholder="Your alias"]', { timeout: 10000 });
      await page.locator(".card-create").locator('input[placeholder="Your alias"]').fill("Columbo");
      await page.locator(".card-create").getByRole("button", { name: "Open the Case" }).click();
      await page.waitForSelector(".waiting-room, [class*=\"waiting\"]", { timeout: 15000 });
      const addBtn = page.getByRole("button", { name: "Add Agent" }).first();
      for (let i = 0; i < 5; i++) {
        if (await addBtn.isVisible().catch(() => false)) {
          await addBtn.click();
          await sleep(500);
        }
      }
      const startBtn = page.getByRole("button", { name: "Begin the Investigation" });
      if (await startBtn.isEnabled().catch(() => false)) {
        await startBtn.click();
      }
      await page.waitForSelector(".game-board, .board-map", { timeout: 20000 });
      await sleep(1500);
      // Open detective notes tab
      const notesTab = page.locator("button, .tab").filter({ hasText: /notes|detective/i }).first();
      if (await notesTab.isVisible().catch(() => false)) {
        await notesTab.click();
        await sleep(600);
      }
      await page.screenshot({ path: outPath("05-clue-detective-notes.png"), fullPage: false });
      await page.close();
    }

    // ─── 6. Hold'em Waiting Room ─────────────────────────────────────────────
    console.log("📸 06 — Hold'em waiting room");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      // Switch to Hold'em tab
      const holdemTab = page.locator(".game-type-btn").filter({ hasText: "Hold'em" });
      if (await holdemTab.isVisible().catch(() => false)) {
        await holdemTab.click();
        await sleep(400);
      }
      await page.waitForSelector('input[placeholder="Your alias"]', { timeout: 10000 });
      await page.locator(".card-create").locator('input[placeholder="Your alias"]').fill("PokerPro");
      await page.locator(".card-create").getByRole("button", { name: "Deal Me In" }).click();
      await page.waitForSelector(".waiting-scene", { timeout: 15000 });
      // Add a couple agents
      const addBtn = page.getByRole("button", { name: "Add Bot" }).first();
      for (let i = 0; i < 3; i++) {
        await addBtn.waitFor({ state: "visible", timeout: 5000 });
        await addBtn.click();
        await sleep(700);
      }
      await sleep(500);
      await page.screenshot({ path: outPath("06-holdem-waiting-room.png"), fullPage: false });
      await page.close();
    }

    // ─── 7. Hold'em Poker Table ──────────────────────────────────────────────
    console.log("📸 07 — Hold'em poker table");
    {
      const page = await browser.newPage();
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
      // Switch to Hold'em tab
      const holdemTab = page.locator(".game-type-btn").filter({ hasText: "Hold'em" });
      if (await holdemTab.isVisible().catch(() => false)) {
        await holdemTab.click();
        await sleep(400);
      }
      await page.waitForSelector('input[placeholder="Your alias"]', { timeout: 10000 });
      await page.locator(".card-create").locator('input[placeholder="Your alias"]').fill("Player1");
      await page.locator(".card-create").getByRole("button", { name: "Deal Me In" }).click();
      await page.waitForSelector(".waiting-scene", { timeout: 15000 });
      // Add agents — wait between each to let the request complete
      const addBtn = page.getByRole("button", { name: "Add Bot" }).first();
      for (let i = 0; i < 4; i++) {
        await addBtn.waitFor({ state: "visible", timeout: 5000 });
        await addBtn.click();
        await sleep(800);
      }
      // Start the game — wait for the deal button to be enabled
      const startBtn = page.locator("button.deal-btn");
      await startBtn.waitFor({ state: "visible", timeout: 5000 });
      await startBtn.click();
      // Wait for the poker table to appear
      await page.waitForSelector(".poker-scene", { timeout: 20000 });
      await sleep(2000);
      await page.screenshot({ path: outPath("07-holdem-poker-table.png"), fullPage: false });
      await page.close();
    }

  } finally {
    await browser.close();
  }

  console.log(`\n✅ Screenshots saved to: ${OUT_DIR}`);
  console.log(fs.readdirSync(OUT_DIR).map((f) => `   ${f}`).join("\n"));
}

main().catch((err) => {
  console.error("❌ Error:", err.message);
  process.exit(1);
});
