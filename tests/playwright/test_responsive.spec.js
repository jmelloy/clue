// @ts-check
const { test, expect } = require("@playwright/test");

const SCREENSHOT_DIR = "./screenshots/responsive";

const VIEWPORTS = {
  "iphone-se": { width: 375, height: 667 },
  "iphone-14": { width: 390, height: 844 },
  "iphone-14-pro-max": { width: 430, height: 932 },
  "pixel-7": { width: 412, height: 915 },
  "ipad-mini": { width: 768, height: 1024 },
  "ipad-pro": { width: 1024, height: 1366 },
  desktop: { width: 1280, height: 900 },
};

test.describe("Responsive Layout - Clue Game", () => {
  for (const [device, viewport] of Object.entries(VIEWPORTS)) {
    test(`no horizontal overflow at ${device} (${viewport.width}x${viewport.height})`, async ({
      browser,
    }) => {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();

      // --- Lobby ---
      await page.goto("/");
      await expect(page.locator("h1")).toContainText("Game Night", {
        timeout: 10000,
      });
      await page.waitForTimeout(1000);

      const lobbyOverflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth
      );
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/lobby-${device}.png`,
        fullPage: true,
      });
      expect(lobbyOverflow, `Lobby overflows at ${device}`).toBe(false);

      // --- Select Clue, create game ---
      await page.locator(".game-card").first().click();
      await page
        .locator('input[placeholder="Your name"]')
        .first()
        .fill("TestPlayer");
      await page
        .locator('button:has-text("Start Game")')
        .first()
        .click();

      // --- Waiting Room ---
      await expect(
        page.getByText("The Suspects Are Gathering")
      ).toBeVisible({ timeout: 10000 });
      await page.waitForTimeout(500);

      const waitingOverflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth
      );
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/waiting-${device}.png`,
        fullPage: true,
      });
      expect(waitingOverflow, `Waiting room overflows at ${device}`).toBe(
        false
      );

      // --- Add agents & start game ---
      const addAgentBtn = page
        .getByRole("button", { name: "Add Agent" })
        .first();
      await addAgentBtn.click();
      await expect(page.locator(".count-badge")).toContainText("2 / 6", {
        timeout: 5000,
      });
      await addAgentBtn.click();
      await expect(page.locator(".count-badge")).toContainText("3 / 6", {
        timeout: 5000,
      });

      await page
        .getByRole("button", { name: "Begin the Investigation" })
        .click();
      await expect(page.locator(".game-board").first()).toBeVisible({
        timeout: 10000,
      });
      await expect(page.locator(".board-map")).toBeVisible();
      await page.waitForTimeout(2000);

      // --- Game Board ---
      await page.screenshot({
        path: `${SCREENSHOT_DIR}/gameboard-${device}.png`,
        fullPage: true,
      });

      const gameOverflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth
      );
      expect(gameOverflow, `Game board overflows at ${device}`).toBe(false);

      // Verify board fits within viewport
      const boardWidth = await page.evaluate(() => {
        const board = document.querySelector(".board-container");
        return board ? board.getBoundingClientRect().width : 0;
      });
      expect(boardWidth).toBeLessThanOrEqual(viewport.width);

      await context.close();
    });
  }
});
