#!/usr/bin/env python3
"""
Generate images of a standard 52-card deck in 3 different visual styles.

Output structure (default):
  frontend/public/images/cards/
    classic/   - Traditional serif style, cream background, ornamental border
    modern/    - Minimalist geometric style, white background, colour accent bar
    vintage/   - Aged-paper retro style, Liberation Serif, double-line border

Usage:
    python scripts/generate_cards.py
    python scripts/generate_cards.py --output /path/to/output
    python scripts/generate_cards.py --style classic
    python scripts/generate_cards.py --width 250 --height 350
"""

import argparse
import io
import random
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Card constants
# ---------------------------------------------------------------------------

SUITS = ["spades", "hearts", "diamonds", "clubs"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

SUIT_SYMBOLS = {
    "spades": "\u2660",
    "hearts": "\u2665",
    "diamonds": "\u2666",
    "clubs": "\u2663",
}

# Pip positions as (row %, col %) of the full card area.
# Measured from real playing card photographs — pips span ~22% to ~88% vertically,
# ~27% to ~74% horizontally. Each pip is ~21% of card width/height.
PIP_LAYOUTS: dict[int, list[tuple[int, int]]] = {
    1: [(50, 50)],
    2: [(22, 50), (78, 50)],
    3: [(22, 50), (50, 50), (78, 50)],
    4: [(22, 27), (22, 73), (78, 27), (78, 73)],
    5: [(22, 27), (22, 73), (50, 50), (78, 27), (78, 73)],
    6: [(22, 27), (22, 73), (50, 27), (50, 73), (78, 27), (78, 73)],
    7: [(22, 27), (22, 73), (36, 50), (50, 27), (50, 73), (78, 27), (78, 73)],
    8: [
        (22, 27),
        (22, 73),
        (36, 50),
        (50, 27),
        (50, 73),
        (64, 50),
        (78, 27),
        (78, 73),
    ],
    9: [
        (22, 27),
        (22, 73),
        (41, 27),
        (41, 73),
        (50, 50),
        (59, 27),
        (59, 73),
        (78, 27),
        (78, 73),
    ],
    10: [
        (22, 27),
        (22, 73),
        (33, 50),
        (44, 27),
        (44, 73),
        (65, 27),
        (65, 73),
        (76, 50),
        (87, 27),
        (87, 73),
    ],
}


def pip_count(rank: str) -> int:
    if rank == "A":
        return 1
    try:
        n = int(rank)
        if 2 <= n <= 10:
            return n
    except ValueError:
        pass
    return 0  # face card — handled separately


# ---------------------------------------------------------------------------
# Font helpers — cross-platform via bundled DejaVu fonts
# ---------------------------------------------------------------------------

_FONT_CACHE_DIR = Path(__file__).parent / "fonts"

# DejaVu 2.37 from GitHub — freely licensed, excellent Unicode coverage
_DEJAVU_ZIP_URL = (
    "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/"
    "version_2_37/dejavu-fonts-ttf-2.37.zip"
)

# Font files we need (paths inside the zip)
_DEJAVU_FONTS = {
    "DejaVuSerif-Bold.ttf": "dejavu-fonts-ttf-2.37/ttf/DejaVuSerif-Bold.ttf",
    "DejaVuSerif.ttf": "dejavu-fonts-ttf-2.37/ttf/DejaVuSerif.ttf",
    "DejaVuSans-Bold.ttf": "dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf": "dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf",
}


def _ensure_fonts() -> None:
    """Download and cache DejaVu fonts if not already present."""
    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    missing = [name for name in _DEJAVU_FONTS if not (_FONT_CACHE_DIR / name).exists()]
    if not missing:
        return

    print(f"  Downloading DejaVu fonts to {_FONT_CACHE_DIR} …")
    resp = urllib.request.urlopen(_DEJAVU_ZIP_URL)
    data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for local_name, zip_path in _DEJAVU_FONTS.items():
            dest = _FONT_CACHE_DIR / local_name
            if not dest.exists():
                dest.write_bytes(zf.read(zip_path))
                print(f"    ✓ {local_name}")
    print()


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a bundled DejaVu font by filename at the requested pixel *size*."""
    path = _FONT_CACHE_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    # Fallback: try system paths (Linux package installs)
    for base in [
        "/usr/share/fonts/truetype/dejavu/",
        "/usr/share/fonts/truetype/liberation/",
    ]:
        p = Path(base) / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    raise FileNotFoundError(
        f"Font {name!r} not found. Run the script again to auto-download fonts."
    )


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple | None = None,
    outline: tuple | None = None,
    width: int = 1,
) -> None:
    """Draw a rounded rectangle (Pillow ≥ 8.2 has this built-in)."""
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def centered_text(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple,
) -> None:
    """Draw *text* centred at (cx, cy)."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((cx - w // 2, cy - h // 2), text, font=font, fill=fill)


# ---------------------------------------------------------------------------
# Shared corner helper — draw the bottom-right corner (rotated 180°)
# ---------------------------------------------------------------------------


def _draw_rotated_corner(
    draw: ImageDraw.ImageDraw,
    rank: str,
    suit: str,
    rank_font: ImageFont.FreeTypeFont,
    suit_font: ImageFont.FreeTypeFont,
    color: tuple,
    W: int,
    H: int,
    cx_offset: int,
    top_y: int,
) -> None:
    """Render rank + suit in the bottom-right corner (unrotated, reading from corner).

    In a digital card game cards are never held upside-down, so we keep text
    readable rather than rotating 180° (which garbles multi-char ranks like "10"
    and makes ♥ look like ♠).
    """
    symbol = SUIT_SYMBOLS[suit]
    bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
    rh = bbox_r[3] - bbox_r[1]
    bbox_s = draw.textbbox((0, 0), symbol, font=suit_font)
    sh = bbox_s[3] - bbox_s[1]

    # Mirror the top-left layout: suit closest to corner, rank above
    cx = W - cx_offset
    suit_bottom = H - top_y
    suit_cy = suit_bottom - sh // 2
    rank_cy = suit_cy - sh // 2 - 12 - rh // 2

    centered_text(draw, cx, rank_cy, rank, rank_font, color)
    centered_text(draw, cx, suit_cy, symbol, suit_font, color)


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------


class Theme:
    name: str

    # card dimensions are injected at runtime
    W: int = 500
    H: int = 700

    def suit_color(self, suit: str) -> tuple:
        raise NotImplementedError

    def draw_background(self, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
        raise NotImplementedError

    def draw_border(self, draw: ImageDraw.ImageDraw) -> None:
        raise NotImplementedError

    def draw_corner(
        self,
        draw: ImageDraw.ImageDraw,
        rank: str,
        suit: str,
        top_left: bool,
        rank_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        suit_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        raise NotImplementedError

    def draw_center(
        self,
        draw: ImageDraw.ImageDraw,
        rank: str,
        suit: str,
        fonts: dict,
    ) -> None:
        raise NotImplementedError

    def draw_card_back(self, img: Image.Image) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared pip renderer (all themes re-use the same geometry)
    # ------------------------------------------------------------------

    def _draw_pips(
        self,
        draw: ImageDraw.ImageDraw,
        suit: str,
        count: int,
        pip_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        color: tuple,
    ) -> None:
        """Draw suit pips using PIP_LAYOUTS (card-% coordinates)."""
        symbol = SUIT_SYMBOLS[suit]
        for row_pct, col_pct in PIP_LAYOUTS.get(count, []):
            px = int(self.W * col_pct / 100)
            py = int(self.H * row_pct / 100)
            bbox = draw.textbbox((0, 0), symbol, font=pip_font)
            pw = bbox[2] - bbox[0]
            ph = bbox[3] - bbox[1]
            x = px - pw // 2
            y = py - ph // 2
            draw.text((x, y), symbol, font=pip_font, fill=color)

    def _draw_face_center(
        self,
        draw: ImageDraw.ImageDraw,
        rank: str,
        suit: str,
        face_rank_font: ImageFont.FreeTypeFont,
        face_suit_font: ImageFont.FreeTypeFont,
        color: tuple,
    ) -> None:
        """Draw a large rank letter with suit symbol below it, centered on the card."""
        symbol = SUIT_SYMBOLS[suit]
        cx, cy = self.W // 2, self.H // 2

        # Measure both glyphs
        bbox_r = draw.textbbox((0, 0), rank, font=face_rank_font)
        rh = bbox_r[3] - bbox_r[1]
        bbox_s = draw.textbbox((0, 0), symbol, font=face_suit_font)
        sh = bbox_s[3] - bbox_s[1]

        # Stack rank above suit with a small gap
        gap = 8
        total_h = rh + gap + sh
        rank_cy = cy - total_h // 2 + rh // 2
        suit_cy = cy + total_h // 2 - sh // 2

        centered_text(draw, cx, rank_cy, rank, face_rank_font, color)
        centered_text(draw, cx, suit_cy, symbol, face_suit_font, color)


# ---------------------------------------------------------------------------
# Theme 1 — Classic
# ---------------------------------------------------------------------------


class ClassicTheme(Theme):
    """Traditional playing card: cream background, DejaVu Serif, ornamental border."""

    name = "classic"

    BG = (245, 241, 232)  # cream
    BORDER = (28, 28, 46)  # near-black
    RED = (185, 28, 28)
    BLACK = (28, 28, 46)
    BACK_BG = (26, 77, 46)  # dark green
    BACK_ACCENT = (201, 168, 76)  # gold

    def suit_color(self, suit: str) -> tuple:
        return self.RED if suit in ("hearts", "diamonds") else self.BLACK

    # ------------------------------------------------------------------
    def draw_background(self, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 20, fill=self.BG)

    def draw_border(self, draw: ImageDraw.ImageDraw) -> None:
        m = 10
        draw_rounded_rect(
            draw,
            (m, m, self.W - m - 1, self.H - m - 1),
            14,
            fill=None,
            outline=self.BORDER,
            width=2,
        )
        m2 = 14
        draw_rounded_rect(
            draw,
            (m2, m2, self.W - m2 - 1, self.H - m2 - 1),
            10,
            fill=None,
            outline=(*self.BORDER[:3], 60),
            width=1,
        )

    def draw_corner(self, draw, rank, suit, top_left, rank_font, suit_font):
        color = self.suit_color(suit)
        symbol = SUIT_SYMBOLS[suit]
        cx_offset = 48  # horizontal center of corner column
        top_y = 34  # top of rank text
        if top_left:
            bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
            rh = bbox_r[3] - bbox_r[1]
            centered_text(draw, cx_offset, top_y + rh // 2, rank, rank_font, color)
            centered_text(draw, cx_offset, top_y + rh + 20, symbol, suit_font, color)
        else:
            _draw_rotated_corner(
                draw,
                rank,
                suit,
                rank_font,
                suit_font,
                color,
                self.W,
                self.H,
                cx_offset,
                top_y,
            )

    def draw_center(self, draw, rank, suit, fonts):
        color = self.suit_color(suit)
        if rank in ("J", "Q", "K"):
            self._draw_face_center(
                draw, rank, suit, fonts["face_rank"], fonts["face_suit"], color
            )
        else:
            count = pip_count(rank)
            if count:
                self._draw_pips(draw, suit, count, fonts["pip"], color)

    def draw_card_back(self, img: Image.Image) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 20, fill=self.BACK_BG)
        # gold ornamental border
        m = 12
        draw_rounded_rect(
            draw,
            (m, m, self.W - m - 1, self.H - m - 1),
            14,
            fill=None,
            outline=self.BACK_ACCENT,
            width=2,
        )
        # diagonal hatch pattern
        spacing = 16
        for offset in range(-self.H, self.W + self.H, spacing):
            draw.line(
                [(offset, 0), (offset + self.H, self.H)],
                fill=(*self.BACK_ACCENT[:3], 30),
                width=1,
            )
        # inner frame
        m2 = 20
        draw_rounded_rect(
            draw,
            (m2, m2, self.W - m2 - 1, self.H - m2 - 1),
            10,
            fill=None,
            outline=(*self.BACK_ACCENT[:3], 80),
            width=1,
        )


# ---------------------------------------------------------------------------
# Theme 2 — Modern
# ---------------------------------------------------------------------------


class ModernTheme(Theme):
    """Minimalist flat design: white background, Lato Bold, colour accent bar."""

    name = "modern"

    BG = (255, 255, 255)
    RED = (220, 38, 38)
    BLUE = (37, 99, 235)
    BORDER = (229, 231, 235)  # light grey border
    BACK_BG = (17, 24, 39)  # very dark navy

    def suit_color(self, suit: str) -> tuple:
        return self.RED if suit in ("hearts", "diamonds") else self.BLUE

    def _accent_color(self, suit: str) -> tuple:
        return self.suit_color(suit)

    def draw_background(self, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 16, fill=self.BG)

    def draw_border(self, draw: ImageDraw.ImageDraw) -> None:
        draw_rounded_rect(
            draw,
            (0, 0, self.W - 1, self.H - 1),
            16,
            fill=None,
            outline=self.BORDER,
            width=3,
        )

    def _draw_accent_bar(self, draw: ImageDraw.ImageDraw, suit: str) -> None:
        """Draw a coloured bar along the top and bottom edges."""
        color = self._accent_color(suit)
        bar_h = 8
        draw.rectangle((16, 0, self.W - 16, bar_h - 1), fill=color)
        draw.rectangle((16, self.H - bar_h, self.W - 16, self.H - 1), fill=color)

    def draw_corner(self, draw, rank, suit, top_left, rank_font, suit_font):
        color = self.suit_color(suit)
        symbol = SUIT_SYMBOLS[suit]
        cx_offset = 46
        top_y = 30
        if top_left:
            bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
            rh = bbox_r[3] - bbox_r[1]
            centered_text(draw, cx_offset, top_y + rh // 2, rank, rank_font, color)
            centered_text(draw, cx_offset, top_y + rh + 20, symbol, suit_font, color)
        else:
            _draw_rotated_corner(
                draw,
                rank,
                suit,
                rank_font,
                suit_font,
                color,
                self.W,
                self.H,
                cx_offset,
                top_y,
            )

    def draw_center(self, draw, rank, suit, fonts):
        # accent bars drawn here because we need suit colour
        self._draw_accent_bar(draw, suit)
        color = self.suit_color(suit)
        if rank in ("J", "Q", "K"):
            self._draw_face_center(
                draw, rank, suit, fonts["face_rank"], fonts["face_suit"], color
            )
        else:
            count = pip_count(rank)
            if count:
                self._draw_pips(draw, suit, count, fonts["pip"], color)

    def draw_card_back(self, img: Image.Image) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 16, fill=self.BACK_BG)
        # grid pattern
        grid_color = (255, 255, 255, 18)
        spacing = 24
        for x in range(0, self.W, spacing):
            draw.line([(x, 0), (x, self.H)], fill=grid_color, width=1)
        for y in range(0, self.H, spacing):
            draw.line([(0, y), (self.W, y)], fill=grid_color, width=1)
        # coloured accent bar top + bottom
        bar_h = 10
        accent = (37, 99, 235, 220)
        draw.rectangle((16, 0, self.W - 16, bar_h - 1), fill=accent)
        draw.rectangle((16, self.H - bar_h, self.W - 16, self.H - 1), fill=accent)
        # centre diamond
        cx, cy = self.W // 2, self.H // 2
        d = 40
        draw.polygon(
            [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)],
            fill=(37, 99, 235, 180),
        )


# ---------------------------------------------------------------------------
# Theme 3 — Vintage
# ---------------------------------------------------------------------------


class VintageTheme(Theme):
    """Aged-paper retro style: warm beige, Liberation Serif, double-line border."""

    name = "vintage"

    BG = (240, 230, 200)  # aged paper
    DARK_RED = (120, 30, 30)  # burgundy
    DARK_NAVY = (20, 20, 60)  # dark navy
    BORDER_OUTER = (101, 67, 33)  # brown
    BORDER_INNER = (160, 110, 60)  # lighter brown
    BACK_BG = (55, 27, 12)  # dark walnut

    def suit_color(self, suit: str) -> tuple:
        return self.DARK_RED if suit in ("hearts", "diamonds") else self.DARK_NAVY

    def draw_background(self, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
        # fill with parchment colour
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 18, fill=self.BG)
        # subtle noise texture via small dots
        rng = random.Random(42)
        draw_obj = draw
        for _ in range(800):
            x = rng.randint(0, self.W - 1)
            y = rng.randint(0, self.H - 1)
            shade = rng.randint(0, 30)
            alpha = rng.randint(10, 40)
            draw_obj.point((x, y), fill=(160 - shade, 140 - shade, 110 - shade, alpha))

    def draw_border(self, draw: ImageDraw.ImageDraw) -> None:
        m = 10
        draw_rounded_rect(
            draw,
            (m, m, self.W - m - 1, self.H - m - 1),
            12,
            fill=None,
            outline=self.BORDER_OUTER,
            width=3,
        )
        m2 = 17
        draw_rounded_rect(
            draw,
            (m2, m2, self.W - m2 - 1, self.H - m2 - 1),
            8,
            fill=None,
            outline=self.BORDER_INNER,
            width=1,
        )
        # corner flourishes — small diamond accents
        for cx, cy in [
            (m + 6, m + 6),
            (self.W - m - 7, m + 6),
            (m + 6, self.H - m - 7),
            (self.W - m - 7, self.H - m - 7),
        ]:
            d = 5
            draw.polygon(
                [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)],
                fill=self.BORDER_INNER,
            )

    def draw_corner(self, draw, rank, suit, top_left, rank_font, suit_font):
        color = self.suit_color(suit)
        symbol = SUIT_SYMBOLS[suit]
        cx_offset = 48
        top_y = 36
        if top_left:
            bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
            rh = bbox_r[3] - bbox_r[1]
            centered_text(draw, cx_offset, top_y + rh // 2, rank, rank_font, color)
            centered_text(draw, cx_offset, top_y + rh + 20, symbol, suit_font, color)
        else:
            _draw_rotated_corner(
                draw,
                rank,
                suit,
                rank_font,
                suit_font,
                color,
                self.W,
                self.H,
                cx_offset,
                top_y,
            )

    def draw_center(self, draw, rank, suit, fonts):
        color = self.suit_color(suit)
        if rank in ("J", "Q", "K"):
            self._draw_face_center(
                draw, rank, suit, fonts["face_rank"], fonts["face_suit"], color
            )
        else:
            count = pip_count(rank)
            if count:
                self._draw_pips(draw, suit, count, fonts["pip"], color)

    def draw_card_back(self, img: Image.Image) -> None:
        draw = ImageDraw.Draw(img, "RGBA")
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 18, fill=self.BACK_BG)
        # diamond hatch
        rng = random.Random(7)
        spacing = 20
        for offset in range(-self.H, self.W + self.H, spacing):
            draw.line(
                [(offset, 0), (offset + self.H, self.H)],
                fill=(160, 110, 60, 40),
                width=1,
            )
        for offset in range(-self.H, self.W + self.H, spacing):
            draw.line(
                [(offset + self.H, 0), (offset, self.H)],
                fill=(160, 110, 60, 40),
                width=1,
            )
        # concentric borders
        m = 12
        draw_rounded_rect(
            draw,
            (m, m, self.W - m - 1, self.H - m - 1),
            12,
            fill=None,
            outline=(160, 110, 60, 200),
            width=2,
        )
        m2 = 20
        draw_rounded_rect(
            draw,
            (m2, m2, self.W - m2 - 1, self.H - m2 - 1),
            8,
            fill=None,
            outline=(160, 110, 60, 120),
            width=1,
        )
        # centre medallion
        cx, cy = self.W // 2, self.H // 2
        r = 45
        for ri, alpha in [(r, 160), (r - 10, 100), (r - 20, 60)]:
            draw.ellipse(
                [(cx - ri, cy - ri), (cx + ri, cy + ri)],
                fill=None,
                outline=(160, 110, 60, alpha),
                width=2,
            )


# ---------------------------------------------------------------------------
# Font sets per theme
# ---------------------------------------------------------------------------

THEME_FONTS = {
    "classic": {
        "rank_name": "DejaVuSerif-Bold.ttf",
        "suit_name": "DejaVuSerif-Bold.ttf",
        "pip_name": "DejaVuSerif.ttf",
        "face_name": "DejaVuSerif-Bold.ttf",
    },
    "modern": {
        "rank_name": "DejaVuSans-Bold.ttf",
        "suit_name": "DejaVuSans-Bold.ttf",
        "pip_name": "DejaVuSans.ttf",
        "face_name": "DejaVuSans-Bold.ttf",
    },
    "vintage": {
        "rank_name": "DejaVuSerif-Bold.ttf",
        "suit_name": "DejaVuSerif.ttf",
        "pip_name": "DejaVuSerif.ttf",
        "face_name": "DejaVuSerif-Bold.ttf",
    },
}


def build_fonts(theme_name: str, W: int, H: int) -> dict:
    cfg = THEME_FONTS[theme_name]
    scale = W / 500  # relative to 500 px wide reference
    return {
        "rank": load_font(cfg["rank_name"], int(52 * scale)),
        "suit": load_font(cfg["suit_name"], int(48 * scale)),
        "pip": load_font(cfg["pip_name"], int(130 * scale)),
        "face_rank": load_font(cfg["face_name"], int(160 * scale)),
        "face_suit": load_font(cfg["suit_name"], int(120 * scale)),
    }


# ---------------------------------------------------------------------------
# Card renderer
# ---------------------------------------------------------------------------


def render_card(
    theme: Theme,
    rank: str,
    suit: str,
    fonts: dict,
) -> Image.Image:
    img = Image.new("RGBA", (theme.W, theme.H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")

    theme.draw_background(draw, img)

    # draw_center may set _pending_paste (e.g. MageTheme with AI artwork)
    theme._pending_paste = None  # type: ignore[attr-defined]
    theme.draw_center(draw, rank, suit, fonts)

    # Composite AI artwork before drawing corners (corners draw on top)
    pending = getattr(theme, "_pending_paste", None)
    if pending is not None:
        art_img, px, py = pending
        # Convert AI art to RGBA for proper compositing
        if art_img.mode != "RGBA":
            art_img = art_img.convert("RGBA")
        img.paste(art_img, (px, py), art_img)
        theme._pending_paste = None  # type: ignore[attr-defined]
        # Redraw after paste so the draw context reflects the composited image
        draw = ImageDraw.Draw(img, "RGBA")

    theme.draw_corner(draw, rank, suit, True, fonts["rank"], fonts["suit"])
    theme.draw_corner(draw, rank, suit, False, fonts["rank"], fonts["suit"])

    return img


def render_back(theme: Theme) -> Image.Image:
    img = Image.new("RGBA", (theme.W, theme.H), (0, 0, 0, 0))
    theme.draw_card_back(img)
    return img


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Theme 4 — Mage (AI-generated center art on classic card template)
# ---------------------------------------------------------------------------

# AI-generated images directory
_MAGE_IMAGE_DIR = Path(__file__).parent.parent / "mage-output" / "1 - Z-Image Turbo"
_MAGE_RANK_MAP = {"A": "Ace", "J": "Jack", "Q": "Queen", "K": "King"}
_MAGE_SUIT_MAP = {
    "clubs": "Clubs",
    "diamonds": "Diamonds",
    "hearts": "Hearts",
    "spades": "Spades",
}

# Best variant index per card (0-indexed, selected by visual review)
_MAGE_BEST_VARIANT: dict[str, int] = {
    "Ace of Clubs": 2,  # variant 3: no inner border frame, fills card naturally
}

# Corner regions to blank out (as fraction of card size).
# The AI cards have rank/suit text in the top-left and bottom-right corners only.
# Sized to cover rank text + suit symbol + any decorative pips near corners.
_MAGE_CORNER_W = 0.20  # width of each corner region
_MAGE_CORNER_H = 0.22  # height of each corner region

# Minimal edge trim — just past the card border / rounded-corner area
_MAGE_EDGE_TRIM = 0.03


def _find_mage_image(rank: str, suit: str) -> Path | None:
    """Find the best AI-generated image for a given rank/suit."""
    rank_name = _MAGE_RANK_MAP.get(rank)
    suit_name = _MAGE_SUIT_MAP.get(suit)
    if not rank_name or not suit_name:
        return None

    card_name = f"{rank_name} of {suit_name}"
    import re

    pattern = re.compile(rf"^{re.escape(card_name)}_\d+\.jpg$")
    matches = sorted(f for f in _MAGE_IMAGE_DIR.iterdir() if pattern.match(f.name))
    if not matches:
        return None

    idx = _MAGE_BEST_VARIANT.get(card_name, 0)
    return matches[min(idx, len(matches) - 1)]


def _find_card_bounds(
    img: Image.Image, threshold: int = 240
) -> tuple[int, int, int, int]:
    """Find the bounding box of card content (non-white area)."""
    import numpy as np

    arr = np.array(img.convert("L"))
    h, w = arr.shape

    def first_content(iter_range, is_row):
        dim = w if is_row else h
        for i in iter_range:
            line = arr[i, :] if is_row else arr[:, i]
            if np.sum(line < threshold) / dim > 0.08:
                return i
        return iter_range[0] if hasattr(iter_range, "__getitem__") else 0

    top = first_content(range(h), True)
    bot = first_content(range(h - 1, -1, -1), True)
    left = first_content(range(w), False)
    right = first_content(range(w - 1, -1, -1), False)
    return left, top, right + 1, bot + 1


def _extract_mage_center(img_path: Path) -> Image.Image:
    """Extract center artwork from an AI card image.

    Instead of aggressively cropping all edges, this:
    1. Crops to the card boundary (removes white margin)
    2. Trims a thin edge strip (border/rounded corners)
    3. Masks out the top-left and bottom-right corner regions (AI rank/suit text)
    4. Makes white/near-white pixels transparent for clean compositing
    """
    import numpy as np

    img = Image.open(img_path)

    # Crop to card boundary (remove white margins)
    bounds = _find_card_bounds(img)
    card = img.crop(bounds)
    cw, ch = card.size

    # Trim thin edge strip (card border / rounded corners)
    trim_x = int(cw * _MAGE_EDGE_TRIM)
    trim_y = int(ch * _MAGE_EDGE_TRIM)
    trimmed = card.crop((trim_x, trim_y, cw - trim_x, ch - trim_y))
    tw, th = trimmed.size

    # Convert to RGBA
    rgba = trimmed.convert("RGBA")
    arr = np.array(rgba)

    # Mask out the top-left corner (AI rank/suit text)
    corner_w = int(tw * _MAGE_CORNER_W)
    corner_h = int(th * _MAGE_CORNER_H)
    arr[:corner_h, :corner_w, 3] = 0

    # Mask out the bottom-right corner (AI rank/suit text)
    arr[th - corner_h :, tw - corner_w :, 3] = 0

    # Replace remaining white/near-white background with transparency
    white_mask = (arr[:, :, 0] > 235) & (arr[:, :, 1] > 235) & (arr[:, :, 2] > 235)
    arr[white_mask, 3] = 0

    return Image.fromarray(arr)


class MageTheme(ClassicTheme):
    """Classic card template with AI-generated center art for face cards and aces."""

    name = "mage"

    # Cache extracted center images to avoid re-processing
    _center_cache: dict[str, Image.Image] = {}

    def _get_center_art(self, rank: str, suit: str) -> Image.Image | None:
        """Load and cache AI-generated center artwork for a card."""
        key = f"{rank}_{suit}"
        if key in self._center_cache:
            return self._center_cache[key]

        img_path = _find_mage_image(rank, suit)
        if img_path is None or not img_path.exists():
            return None

        center = _extract_mage_center(img_path)
        self._center_cache[key] = center
        return center

    def draw_center(self, draw, rank, suit, fonts):
        color = self.suit_color(suit)

        # For A/J/Q/K: composite AI artwork into the center area
        if rank in _MAGE_RANK_MAP:
            center_art = self._get_center_art(rank, suit)
            if center_art is not None:
                # Target area: full card interior (artwork fills edge-to-edge,
                # corners are already masked out in the extracted image)
                margin_x = int(self.W * 0.02)
                margin_y = int(self.H * 0.02)
                area_w = self.W - 2 * margin_x
                area_h = self.H - 2 * margin_y

                # Resize artwork to fit, maintaining aspect ratio
                art_w, art_h = center_art.size
                scale = min(area_w / art_w, area_h / art_h)
                new_w = int(art_w * scale)
                new_h = int(art_h * scale)
                resized = center_art.resize((new_w, new_h), Image.LANCZOS)

                # Center it in the target area
                paste_x = margin_x + (area_w - new_w) // 2
                paste_y = margin_y + (area_h - new_h) // 2

                self._pending_paste = (resized, paste_x, paste_y)
                return

        # Number cards: use standard pip rendering
        count = pip_count(rank)
        if count:
            self._draw_pips(draw, suit, count, fonts["pip"], color)


THEMES: dict[str, Theme] = {
    "classic": ClassicTheme(),
    "modern": ModernTheme(),
    "vintage": VintageTheme(),
    "mage": MageTheme(),
}


def generate_all(output_dir: Path, styles: list[str], W: int, H: int) -> None:
    _ensure_fonts()
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(styles) * (52 + 1)  # 52 cards + back per theme
    done = 0

    for style_name in styles:
        theme = THEMES[style_name]
        theme.W = W
        theme.H = H

        style_dir = output_dir / style_name
        style_dir.mkdir(parents=True, exist_ok=True)

        fonts = build_fonts(
            theme.name if theme.name in THEME_FONTS else "classic", W, H
        )

        for suit in SUITS:
            for rank in RANKS:
                filename = f"{rank}_{suit}.png"
                img = render_card(theme, rank, suit, fonts)
                img.convert("RGB").save(style_dir / filename, "PNG", optimize=True)
                done += 1
                pct = done * 100 // total
                print(
                    f"\r  [{pct:3d}%] {style_name}: {rank} of {suit}    ",
                    end="",
                    flush=True,
                )

        # card back
        back = render_back(theme)
        back.convert("RGB").save(style_dir / "back.png", "PNG", optimize=True)
        done += 1
        print(
            f"\r  [{done * 100 // total:3d}%] {style_name}: back              ",
            end="",
            flush=True,
        )

        print(f"\n  ✓  {style_name}: {52 + 1} images → {style_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate playing card images in 3 visual styles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).parent.parent / "frontend" / "public" / "images" / "cards"
        ),
        help="Output directory (default: frontend/public/images/cards/)",
    )
    parser.add_argument(
        "--style",
        choices=list(THEMES.keys()),
        action="append",
        dest="styles",
        help="Which style(s) to generate (default: all three)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=500,
        help="Card width in pixels (default: 500)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=700,
        help="Card height in pixels (default: 700)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    styles = args.styles or list(THEMES.keys())
    output_dir = Path(args.output)

    print(f"Generating {len(styles)} card set(s) → {output_dir}")
    print(f"Card size: {args.width}×{args.height} px\n")

    generate_all(output_dir, styles, args.width, args.height)

    print(f"\nDone. {len(styles) * 53} images written to {output_dir}")


if __name__ == "__main__":
    main()
