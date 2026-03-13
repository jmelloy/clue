# Playing Card Pip Grid Reference

Measured from physical card photographs (10 of spades, 3 of spades).
Reference PNGs: `scripts/ref_10_spades.png`, `scripts/ref_3_spades.png`.

## Card Dimensions

| Property | 10♠ (px) | 3♠ (px) | Notes |
|---|---|---|---|
| Card width | 1874 | 1840 | Photo resolution varies |
| Card height | 2383 | 2231 | |
| Aspect ratio | 0.786 | 0.825 | Standard poker = 0.714 (2.5×3.5") |

> The photos aren't perfectly corrected for perspective, so aspect ratio is slightly off from the standard 5:7.

## Pip Size

| Measurement | Value | Notes |
|---|---|---|
| Pip width | ~21% of card width | Consistent across both cards |
| Pip height | ~21% of card height | Slightly shorter on bottom row of 3♠ |
| Pip width (px at 500w) | ~105 px | At the 500×700 generated card size |
| Pip height (px at 700h) | ~147 px | |
| Pip aspect ratio | ~0.79 (w/h) | Spade is slightly taller than wide |

## Pip Grid Positions (% of card area)

### 10 of Spades — Measured Pip Centers

| Pip | X% | Y% |
|---|---|---|
| 1 (top-left) | 26.7 | 21.5 |
| 2 (top-right) | 74.3 | 21.6 |
| 3 (upper-center) | 50.5 | 32.7 |
| 4 (mid-left) | 26.7 | 44.0 |
| 5 (mid-right) | 74.4 | 44.0 |
| 6 (lower-mid-left) | 26.6 | 64.9 |
| 7 (lower-mid-right) | 74.4 | 64.8 |
| 8 (lower-center) | 50.4 | 76.7 |
| 9 (bottom-left) | 26.6 | 87.9 |
| 10 (bottom-right) | 74.7 | 88.0 |

### 3 of Spades — Measured Pip Centers

| Pip | X% | Y% |
|---|---|---|
| 1 (top) | 50.5 | 22.9 |
| 2 (middle) | 50.2 | 58.9 |
| 3 (bottom) | 49.9 | 91.9 |

## Grid Structure

### Columns (X positions)
- **Left column**: ~27% from left edge
- **Center column**: ~50% (centered)
- **Right column**: ~74% from left edge
- **Column gap**: ~24% between left↔center and center↔right

### Rows (Y positions for 10♠)
- **Row 1** (top pair): ~21.5%
- **Row 2** (upper center): ~32.7%
- **Row 3** (middle pair): ~44.0%
- **Row 4** (lower-mid pair): ~64.9%
- **Row 5** (lower center): ~76.7%
- **Row 6** (bottom pair): ~88.0%
- **Gap between adjacent rows**: ~11-12%
- **Gap between row 3→4 (middle break)**: ~21%

### Rows (Y positions for 3♠)
- **Top**: ~23%
- **Middle**: ~59%
- **Bottom**: ~92%
- **Gap between rows**: ~33-36%

## Corner Labels

| Element | Position (X%, Y%) | Size (W×H px) | Size (% of card) |
|---|---|---|---|
| Top-left rank text | 5.7%, 10.4% | 26×259 | 1.4% × 10.9% |
| Top-left rank glyph | 10.8%, 10.4% | 100×261 | 5.3% × 11.0% |
| Top-left suit symbol | 9.4%, 22.6% | 140×214 | 7.5% × 9.0% |
| Bottom-right suit symbol | 92.2%, 86.6% | 144×220 | 7.7% × 9.2% |
| Bottom-right rank | 90.9%, 96.6% | 105×151 | 5.6% × 6.3% |

- Corner rank/suit centered at ~9% from edge (X) and ~10-23% from edge (Y)
- Corner suit symbol is ~7.5% wide × 9% tall
- Corner rank text is ~5.5% wide × 11% tall

## Comparison with Current `generate_cards.py` PIP_LAYOUTS

Current code uses `(row%, col%)` within a **pip area** that has 8% horizontal and 12% vertical margins.

To convert from card-% to pip-area-%:
- `pip_x% = (card_x% - 8) / 84 * 100`
- `pip_y% = (card_y% - 12) / 76 * 100`

### Current vs Measured (10 of spades)

| Pip | Current (row%, col%) | Measured card (Y%, X%) | Measured pip-area (row%, col%) |
|---|---|---|---|
| Top pair | (18, 28), (18, 72) | (21.5, 26.7), (21.6, 74.3) | (12.5, 22.3), (12.6, 78.9) |
| Upper center | (30, 50) | (32.7, 50.5) | (27.2, 50.6) |
| Mid pair | (38, 28), (38, 72) | (44.0, 26.7), (44.0, 74.4) | (42.1, 22.3), (42.1, 79.0) |
| Lower-mid pair | (62, 28), (62, 72) | (64.9, 26.6), (64.8, 74.4) | (69.6, 22.1), (69.5, 79.0) |
| Lower center | (70, 50) | (76.7, 50.4) | (85.1, 50.5) |
| Bottom pair | (82, 28), (82, 72) | (88.0, 26.6), (88.0, 74.7) | (100.0, 22.1), (100.0, 79.4) |

### Key Differences
1. **Vertical spread**: Real card pips span from ~21% to ~88% of card height (67% range). Current code spans 18→82 within pip area (76% margins) = ~25.7% to 74.3% of card = 49% range. **Real cards use more vertical space.**
2. **Horizontal spread**: Real pips at ~27% and ~74% (47% spread). Current code puts them at 28/72 within pip area = ~31.5% and 68.5% of card (37% spread). **Real cards are wider spread.**
3. **Bottom row extends further**: Real bottom row is at ~88%, much lower than current 82% of pip area.

### Suggested Updated PIP_LAYOUTS (card % directly)

If switching to card-% coordinates (removing the margin abstraction):

```python
PIP_LAYOUTS = {
    1: [(50, 50)],
    2: [(23, 50), (88, 50)],
    3: [(23, 50), (56, 50), (88, 50)],
    4: [(23, 27), (23, 74), (88, 27), (88, 74)],
    5: [(23, 27), (23, 74), (56, 50), (88, 27), (88, 74)],
    6: [(23, 27), (23, 74), (56, 27), (56, 74), (88, 27), (88, 74)],
    7: [(23, 27), (23, 74), (39, 50), (56, 27), (56, 74), (88, 27), (88, 74)],
    8: [(23, 27), (23, 74), (39, 50), (56, 27), (56, 74), (72, 50), (88, 27), (88, 74)],
    9: [(23, 27), (23, 74), (44, 27), (44, 74), (56, 50), (67, 27), (67, 74), (88, 27), (88, 74)],
    10: [(22, 27), (22, 74), (33, 50), (44, 27), (44, 74), (65, 27), (65, 74), (77, 50), (88, 27), (88, 74)],
}
```
