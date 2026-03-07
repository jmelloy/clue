/**
 * git_history_screenshot_worker.js
 *
 * Called by git_history_screenshots.sh for each commit.
 * Creates games through the UI (Playwright), takes screenshots of gameplay.
 *
 * Usage: node git_history_screenshot_worker.js <label> <output_dir> <games>
 */

const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://localhost:5173";
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const [, , label, outputDir, gamesArg, themesArg] = process.argv;
const games = (gamesArg || "clue,holdem").split(",");
const themes = themesArg ? themesArg.split(",") : [];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tryFetch(url, options = {}) {
  try {
    const resp = await fetch(url, options);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

async function screenshotLobby(browser, label, outputDir) {
  console.log("Screenshotting lobby...");
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  try {
    await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 15000 });
    await sleep(2000);
    await page.screenshot({ path: `${outputDir}/${label}_lobby.png` });
    console.log("  Saved lobby");
  } catch (err) {
    console.log("  Lobby screenshot failed:", err.message);
  }
  await ctx.close();
}

async function screenshotClueViaUI(browser, label, outputDir) {
  console.log("Screenshotting Clue game (UI-driven)...");
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  try {
    await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 15000 });
    await sleep(1000);

    // Some versions have a game selector (Game Night hub) — click Clue first
    const clueSelector = await page.$('button:has-text("Clue")');
    if (clueSelector) {
      await clueSelector.click();
      await sleep(1000);
    }

    // Find a name input and fill it — try multiple selectors for different eras
    const nameInput = await page.$('input[placeholder="Your alias"]')
      || await page.$('input[placeholder="Your name"]')
      || await page.$('input[placeholder*="name" i]')
      || await page.$('.card-create input[type="text"]')
      || await page.$('input[type="text"]');

    if (!nameInput) {
      console.log("  SKIP: could not find name input");
      return;
    }
    await nameInput.fill("Player1");

    // Click create/host button — try multiple selectors
    const createBtn = await page.$('button:has-text("Open the Case")')
      || await page.$('button:has-text("Start Game")')
      || await page.$('button:has-text("Create Game")')
      || await page.$('button:has-text("Host")')
      || await page.$('button:has-text("Create")')
      || await page.$('.card-create button');

    if (!createBtn) {
      console.log("  SKIP: could not find create button");
      return;
    }
    await createBtn.click();
    await sleep(3000);

    // We should now be in the waiting room. Add agents if button exists.
    for (let i = 0; i < 2; i++) {
      const agentBtn = await page.$('button:has-text("Add Agent")')
        || await page.$('button:has-text("Add Bot")');
      if (agentBtn) {
        await agentBtn.click();
        await sleep(1000);
      }
    }

    // If no agent button, join extra players via API — get game ID from URL
    const currentUrl = page.url();
    const gameIdMatch = currentUrl.match(/\/game\/([A-Z0-9]+)/i);
    if (gameIdMatch) {
      const gameId = gameIdMatch[1];
      // Check player count via API
      const state = await tryFetch(`${BACKEND_URL}/clue/games/${gameId}`);
      const playerCount = state?.players?.length || 0;
      if (playerCount < 3) {
        for (let i = playerCount; i < 3; i++) {
          await tryFetch(`${BACKEND_URL}/clue/games/${gameId}/join`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ player_name: `Bot${i}` }),
          });
        }
        await sleep(1000);
      }
    }

    // Click start button — try multiple selectors
    const startBtn = await page.$('button:has-text("Begin the Investigation")')
      || await page.$('button:has-text("Start Game")')
      || await page.$('button:has-text("Start")');

    if (startBtn) {
      await startBtn.click();
      await sleep(5000);
    }

    // Wait for game board to appear
    const board = await page.$('.game-board, .board-map, .board-container, .board-grid, canvas');
    if (board) {
      await sleep(2000);
    }

    await page.screenshot({ path: `${outputDir}/${label}_clue.png` });
    console.log("  Saved Clue screenshot");

    // If themes are requested, cycle through them using the footer theme buttons
    if (themes.length > 0) {
      for (const theme of themes) {
        try {
          const themeName = theme.charAt(0).toUpperCase() + theme.slice(1);
          const themeBtn = await page.$(`button:has-text("${themeName}")`);
          if (themeBtn) {
            await themeBtn.click();
            await sleep(1500);
          }
          await page.screenshot({ path: `${outputDir}/${label}_clue_${theme}.png` });
          console.log(`  Saved Clue screenshot (${theme} theme)`);
        } catch (err) {
          console.log(`  Theme ${theme} screenshot failed:`, err.message);
        }
      }
    }
  } catch (err) {
    console.log("  Clue UI screenshot failed:", err.message);
    // Take a screenshot anyway to see what we got
    try {
      await page.screenshot({ path: `${outputDir}/${label}_clue.png` });
      console.log("  Saved Clue screenshot (error state)");
    } catch {}
  }
  await ctx.close();
}

async function screenshotHoldemViaUI(browser, label, outputDir) {
  console.log("Screenshotting Hold'em game (UI-driven)...");

  // Check if holdem endpoint exists at this commit
  const check = await tryFetch(`${BACKEND_URL}/holdem/games`, { method: "POST" });
  if (!check || !check.game_id) {
    console.log("  SKIP: Hold'em not available at this commit");
    return;
  }

  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();

  try {
    await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 15000 });
    await sleep(1000);

    // Select Texas Hold'em game type
    const holdemCard = await page.$('.game-card--holdem')
      || await page.$('button:has-text("Texas Hold")');
    if (holdemCard) {
      await holdemCard.click();
      await sleep(1000);
    }

    // Fill name — try multiple selectors for different eras
    const nameInput = await page.$('input[placeholder="Your name"]')
      || await page.$('input[placeholder="Your alias"]')
      || await page.$('input[placeholder*="name" i]')
      || await page.$('input[type="text"]');

    if (!nameInput) {
      console.log("  SKIP: could not find name input");
      return;
    }
    await nameInput.fill("Player1");

    // Click create button — try multiple selectors
    const createBtn = await page.$('button:has-text("Deal Me In")')
      || await page.$('button:has-text("Start Game")')
      || await page.$('button:has-text("Create Game")')
      || await page.$('button:has-text("Create")')
      || await page.$('.btn-primary');

    if (!createBtn) {
      console.log("  SKIP: could not find create button");
      return;
    }
    await createBtn.click();
    await sleep(3000);

    // Now in PokerWaitingRoom — add bots
    for (let i = 0; i < 2; i++) {
      const botBtn = await page.$('button:has-text("Add Bot")')
        || await page.$('button:has-text("Add Agent")');
      if (botBtn) {
        await botBtn.click();
        await sleep(1500);
      }
    }

    // Fallback: if no Add Bot button, join extra players via API
    const currentUrl = page.url();
    const gameIdMatch = currentUrl.match(/\/holdem\/([A-Z0-9]+)/i);
    if (gameIdMatch) {
      const gameId = gameIdMatch[1];
      const state = await tryFetch(`${BACKEND_URL}/holdem/games/${gameId}`);
      const playerCount = state?.players?.length || 0;
      if (playerCount < 3) {
        for (let j = playerCount; j < 3; j++) {
          await tryFetch(`${BACKEND_URL}/holdem/games/${gameId}/join`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ player_name: `Bot${j}` }),
          });
        }
        await sleep(1000);
      }
    }

    // Click deal/start button
    const dealBtn = await page.$('button:has-text("Deal Cards")')
      || await page.$('button:has-text("Start Game")')
      || await page.$('button:has-text("Start")');

    if (dealBtn) {
      await dealBtn.click();
      await sleep(5000);
    }

    // Wait for poker table to appear
    const table = await page.$('.poker-table, .table-container, .holdem-game, canvas');
    if (table) {
      await sleep(2000);
    }

    await page.screenshot({ path: `${outputDir}/${label}_holdem.png` });
    console.log("  Saved Hold'em screenshot");
  } catch (err) {
    console.log("  Hold'em UI screenshot failed:", err.message);
    try {
      await page.screenshot({ path: `${outputDir}/${label}_holdem.png` });
      console.log("  Saved Hold'em screenshot (error state)");
    } catch {}
  }
  await ctx.close();
}

async function main() {
  if (!label || !outputDir) {
    console.error("Usage: node git_history_screenshot_worker.js <label> <output_dir> <games>");
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });

  try {
    await screenshotLobby(browser, label, outputDir);

    if (games.includes("clue")) {
      await screenshotClueViaUI(browser, label, outputDir);
    }
    if (games.includes("holdem")) {
      await screenshotHoldemViaUI(browser, label, outputDir);
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error("Fatal:", err.message);
  process.exit(1);
});
