// @ts-check
const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173';

test.describe('Game Creation Flow', () => {
  test('create a game, add agents, and start', async ({ page }) => {
    // 1. Navigate to the lobby
    await page.goto(BASE_URL);

    // Verify we're on the lobby page
    await expect(page.locator('h1')).toContainText('CLUE');
    await expect(page.getByText('Host a Game')).toBeVisible();

    // 2. Enter a player name in the "Host a Game" section
    const hostSection = page.locator('.card-create');
    const nameInput = hostSection.locator('input[placeholder="Your alias"]');
    await nameInput.fill('TestPlayer');

    // 3. Click "Open the Case" to create a game
    await hostSection.getByRole('button', { name: 'Open the Case' }).click();

    // 4. Should be in the Waiting Room now
    await expect(page.getByText('The Suspects Are Gathering')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Suspects Present')).toBeVisible();

    // Verify our player is listed
    await expect(page.getByText('TestPlayer')).toBeVisible();
    await expect(page.locator('.count-badge')).toContainText('1 / 6');

    // 5. Add agents — click "Add Agent" a couple times
    const addAgentBtn = page.getByRole('button', { name: 'Add Agent' }).first();
    await addAgentBtn.click();
    await expect(page.locator('.count-badge')).toContainText('2 / 6', { timeout: 5000 });

    await addAgentBtn.click();
    await expect(page.locator('.count-badge')).toContainText('3 / 6', { timeout: 5000 });

    // 6. Start the game — "Begin the Investigation"
    const startBtn = page.getByRole('button', { name: 'Begin the Investigation' });
    await expect(startBtn).toBeEnabled();
    await startBtn.click();

    // 7. Verify we're on the game board
    await expect(page.locator('.game-board').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.board-map')).toBeVisible();
  });

  test('create a game with maximum agents (5 AI + 1 human)', async ({ page }) => {
    await page.goto(BASE_URL);

    // Host a game
    const hostSection = page.locator('.card-create');
    await hostSection.locator('input[placeholder="Your alias"]').fill('Host');
    await hostSection.getByRole('button', { name: 'Open the Case' }).click();

    // Wait for waiting room
    await expect(page.getByText('The Suspects Are Gathering')).toBeVisible({ timeout: 10000 });

    // Add 5 agents to fill the game
    const addAgentBtn = page.getByRole('button', { name: 'Add Agent' }).first();
    for (let i = 0; i < 5; i++) {
      await addAgentBtn.click();
      await expect(page.locator('.count-badge')).toContainText(`${i + 2} / 6`, { timeout: 5000 });
    }

    // Agent controls should be hidden when full
    await expect(page.locator('.agent-controls')).toBeHidden();

    // Start the game
    await page.getByRole('button', { name: 'Begin the Investigation' }).click();
    await expect(page.locator('.game-board').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.board-map')).toBeVisible();
  });
});
