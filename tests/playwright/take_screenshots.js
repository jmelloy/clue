const { chromium } = require("playwright");

const BASE_URL = process.env.BASE_URL || "http://localhost:5173";
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR || "./screenshots";

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath:
      "/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome",
  });

  // ===== Screenshot 1 & 2: Lobby =====
  console.log("Taking lobby screenshots...");
  const lobbyCtx = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const lobbyPage = await lobbyCtx.newPage();
  await lobbyPage.goto(BASE_URL);
  await sleep(3000);
  await lobbyPage.screenshot({ path: `${SCREENSHOT_DIR}/01-lobby-clue.png` });
  console.log("  Saved Clue lobby");

  const holdemBtn = await lobbyPage.$(".game-type-btn:not(.active)");
  if (holdemBtn) {
    await holdemBtn.click();
    await sleep(1000);
  }
  await lobbyPage.screenshot({ path: `${SCREENSHOT_DIR}/02-lobby-holdem.png` });
  console.log("  Saved Hold'em lobby");
  await lobbyCtx.close();

  // ===== Create holdem game and players via API =====
  console.log("Setting up holdem game...");
  const { game_id: gameId } = await (
    await fetch(`${BACKEND_URL}/api/holdem/games`, { method: "POST" })
  ).json();
  console.log("  Game:", gameId);

  const p1 = await (
    await fetch(`${BACKEND_URL}/api/holdem/games/${gameId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: "Alice", buy_in: 1000 }),
    })
  ).json();
  const p2 = await (
    await fetch(`${BACKEND_URL}/api/holdem/games/${gameId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: "Bob", buy_in: 1000 }),
    })
  ).json();
  const p3 = await (
    await fetch(`${BACKEND_URL}/api/holdem/games/${gameId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: "Charlie", buy_in: 1500 }),
    })
  ).json();
  console.log("  Players:", p1.player_id, p2.player_id, p3.player_id);

  // ===== Screenshot 3: Waiting Room =====
  console.log("Taking waiting room screenshot...");
  const ctx1 = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const page1 = await ctx1.newPage();
  page1.on("console", (msg) => {
    if (msg.type() === "error") console.log("  CONSOLE ERROR:", msg.text());
  });

  // Set identity before navigating
  await page1.goto(BASE_URL);
  await page1.evaluate(
    ({ pid, pname }) => {
      localStorage.setItem("playerId", pid);
      localStorage.setItem("playerName", pname);
    },
    { pid: p1.player_id, pname: "Alice" }
  );

  // Navigate to holdem game URL
  await page1.goto(`${BASE_URL}/holdem/${gameId}`);
  await sleep(3000);

  // The Lobby should show the game with rejoin option - click Alice's name
  const aliceBtn = await page1.$("text=Alice");
  if (aliceBtn) {
    console.log("  Clicking Alice to rejoin...");
    await aliceBtn.click();
    await sleep(3000);
  }

  await page1.screenshot({
    path: `${SCREENSHOT_DIR}/03-holdem-waiting-room.png`,
  });
  console.log("  Saved waiting room");

  // ===== Screenshot 4: Poker Table =====
  console.log("Starting game and taking table screenshot...");

  // Click start button if visible
  const startBtn = await page1.$('button:has-text("Start")');
  if (startBtn) {
    console.log("  Clicking Start...");
    await startBtn.click();
  } else {
    console.log("  Starting via API...");
    const startResp = await fetch(
      `${BACKEND_URL}/api/holdem/games/${gameId}/start`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: p1.player_id }),
      }
    );
    console.log("  Start response:", startResp.status);
  }

  await sleep(5000);
  await page1.screenshot({
    path: `${SCREENSHOT_DIR}/04-holdem-poker-table.png`,
  });
  console.log("  Saved poker table");

  // ===== Screenshot 5: Player 2 view =====
  console.log("Taking player 2 view...");
  const ctx2 = await browser.newContext({
    viewport: { width: 1400, height: 900 },
  });
  const page2 = await ctx2.newPage();

  await page2.goto(BASE_URL);
  await page2.evaluate(
    ({ pid, pname }) => {
      localStorage.setItem("playerId", pid);
      localStorage.setItem("playerName", pname);
    },
    { pid: p2.player_id, pname: "Bob" }
  );

  await page2.goto(`${BASE_URL}/holdem/${gameId}`);
  await sleep(3000);

  // Click Bob to rejoin
  const bobBtn = await page2.$("text=Bob");
  if (bobBtn) {
    await bobBtn.click();
    await sleep(4000);
  }

  await page2.screenshot({
    path: `${SCREENSHOT_DIR}/05-holdem-player2-view.png`,
  });
  console.log("  Saved player 2 view");

  await browser.close();
  console.log("\nAll screenshots saved to", SCREENSHOT_DIR);
}

main().catch((err) => {
  console.error("Error:", err);
  process.exit(1);
});
