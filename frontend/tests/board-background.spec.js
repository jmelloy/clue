// @ts-check
import { test, expect } from '@playwright/test'

/**
 * Board background alignment tests.
 *
 * These tests verify that the 25x24 CSS grid cells are correctly
 * positioned within the board container, ensuring any background
 * image (or CSS-drawn board) aligns with the grid squares.
 *
 * Uses a standalone test page that renders BoardMap with mock data
 * (no backend needed).
 */

test.describe('Board grid alignment', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/src/board-test.html')
    // Wait for the board to render
    await page.waitForSelector('.board-container', { timeout: 10000 })
  })

  test('board container has correct aspect ratio (24:25)', async ({ page }) => {
    const board = page.locator('.board-container')
    const box = await board.boundingBox()
    expect(box).toBeTruthy()

    const expectedRatio = 24 / 25
    const actualRatio = box.width / box.height
    // Allow 2% tolerance for rounding
    expect(actualRatio).toBeCloseTo(expectedRatio, 1)
  })

  test('grid has 600 cells (25 rows x 24 cols)', async ({ page }) => {
    const cellCount = await page.locator('.board-grid .cell').count()
    expect(cellCount).toBe(600) // 25 * 24
  })

  test('cells are uniformly sized within the grid', async ({ page }) => {
    const cells = page.locator('.board-grid .cell')
    // Sample cells from different positions: corners and center
    const sampleIndices = [0, 23, 288, 300, 576, 599]
    const sizes = []

    for (const idx of sampleIndices) {
      const box = await cells.nth(idx).boundingBox()
      if (box) {
        sizes.push({ w: Math.round(box.width * 10) / 10, h: Math.round(box.height * 10) / 10 })
      }
    }

    expect(sizes.length).toBeGreaterThan(1)

    // All cells should be the same size (within 1px tolerance)
    for (const size of sizes) {
      expect(size.w).toBeCloseTo(sizes[0].w, 0)
      expect(size.h).toBeCloseTo(sizes[0].h, 0)
    }
  })

  test('grid cells fill the container without gaps', async ({ page }) => {
    const containerBox = await page.locator('.board-container').boundingBox()
    const gridBox = await page.locator('.board-grid').boundingBox()

    expect(containerBox).toBeTruthy()
    expect(gridBox).toBeTruthy()

    // Grid should fill the container's content area (inside the border)
    const borderWidth = await page.locator('.board-container').evaluate(
      el => parseFloat(getComputedStyle(el).borderWidth) || 0
    )
    const expectedWidth = containerBox.width - borderWidth * 2
    const expectedHeight = containerBox.height - borderWidth * 2
    expect(gridBox.width).toBeCloseTo(expectedWidth, 0)
    expect(gridBox.height).toBeCloseTo(expectedHeight, 0)
  })

  test('cell positions map correctly to row/col coordinates', async ({ page }) => {
    const gridBox = await page.locator('.board-grid').boundingBox()
    const cells = page.locator('.board-grid .cell')

    // Cell at index 0 should be at top-left of the grid
    const firstCell = await cells.nth(0).boundingBox()
    expect(firstCell.x).toBeCloseTo(gridBox.x, 0)
    expect(firstCell.y).toBeCloseTo(gridBox.y, 0)

    // Cell at index 23 should be at top-right edge of the grid
    const topRight = await cells.nth(23).boundingBox()
    expect(topRight.x + topRight.width).toBeCloseTo(gridBox.x + gridBox.width, 1)

    // Cell at index 576 (row 24, col 0) should be at bottom-left of the grid
    const bottomLeft = await cells.nth(576).boundingBox()
    expect(bottomLeft.x).toBeCloseTo(gridBox.x, 0)
    expect(bottomLeft.y + bottomLeft.height).toBeCloseTo(gridBox.y + gridBox.height, 1)
  })

  test('room cells exist for all 9 rooms', async ({ page }) => {
    // Each room type should have cells
    const roomCells = await page.locator('.cell-room').count()
    expect(roomCells).toBeGreaterThan(100) // 9 rooms with many cells each

    const hallwayCells = await page.locator('.cell-hallway').count()
    expect(hallwayCells).toBeGreaterThan(30)

    const wallCells = await page.locator('.cell-wall').count()
    expect(wallCells).toBeGreaterThan(10)

    const doorCells = await page.locator('.cell-door').count()
    expect(doorCells).toBeGreaterThan(10)
  })

  test('board image background is applied', async ({ page }) => {
    // Grid should have a background image set
    const bgImage = await page.locator('.board-grid').evaluate(
      el => getComputedStyle(el).backgroundImage
    )
    expect(bgImage).toContain('board.jpg')

    // Non-highlighted cells should be transparent to let the image show through
    const hallwayBg = await page.locator('.cell-hallway:not(.reachable):not(.my-room)').first().evaluate(
      el => getComputedStyle(el).backgroundColor
    )
    expect(hallwayBg).toContain('rgba(0, 0, 0, 0)')

    const wallBg = await page.locator('.cell-wall').first().evaluate(
      el => getComputedStyle(el).backgroundColor
    )
    expect(wallBg).toContain('rgba(0, 0, 0, 0)')
  })

  test('player tokens are positioned correctly', async ({ page }) => {
    const tokens = page.locator('.player-token')
    const tokenCount = await tokens.count()
    // 6 mock players
    expect(tokenCount).toBe(6)

    // Tokens should be within the board container
    const containerBox = await page.locator('.board-container').boundingBox()
    for (let i = 0; i < tokenCount; i++) {
      const tokenBox = await tokens.nth(i).boundingBox()
      expect(tokenBox).toBeTruthy()
      // Token center should be within the container (with margin for token size)
      const tokenCenterX = tokenBox.x + tokenBox.width / 2
      const tokenCenterY = tokenBox.y + tokenBox.height / 2
      expect(tokenCenterX).toBeGreaterThanOrEqual(containerBox.x - 5)
      expect(tokenCenterX).toBeLessThanOrEqual(containerBox.x + containerBox.width + 5)
      expect(tokenCenterY).toBeGreaterThanOrEqual(containerBox.y - 5)
      expect(tokenCenterY).toBeLessThanOrEqual(containerBox.y + containerBox.height + 5)
    }
  })

  test('room labels are hidden (image provides them)', async ({ page }) => {
    // Labels exist in DOM but are hidden via display:none
    const labels = page.locator('.room-label')
    const labelCount = await labels.count()
    expect(labelCount).toBe(9) // 9 rooms still in DOM

    const display = await labels.first().evaluate(
      el => getComputedStyle(el).display
    )
    expect(display).toBe('none')

    // Center label also hidden
    const centerDisplay = await page.locator('.center-label').evaluate(
      el => getComputedStyle(el).display
    )
    expect(centerDisplay).toBe('none')
  })

  test('take board screenshot for visual inspection', async ({ page }) => {
    const board = page.locator('.board-container')
    await board.screenshot({ path: 'tests/board-screenshot.png' })
  })
})
