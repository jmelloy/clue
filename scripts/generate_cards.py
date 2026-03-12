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
import math
import random
import sys
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

# Pip positions as (row %, col %) — matches PlayingCard.vue
PIP_LAYOUTS: dict[int, list[tuple[int, int]]] = {
    1: [(50, 50)],
    2: [(18, 50), (82, 50)],
    3: [(18, 50), (50, 50), (82, 50)],
    4: [(18, 28), (18, 72), (82, 28), (82, 72)],
    5: [(18, 28), (18, 72), (50, 50), (82, 28), (82, 72)],
    6: [(18, 28), (18, 72), (50, 28), (50, 72), (82, 28), (82, 72)],
    7: [(18, 28), (18, 72), (34, 50), (50, 28), (50, 72), (82, 28), (82, 72)],
    8: [
        (18, 28), (18, 72), (34, 50),
        (50, 28), (50, 72),
        (66, 50), (82, 28), (82, 72),
    ],
    9: [
        (18, 28), (18, 72),
        (38, 28), (38, 72),
        (50, 50),
        (62, 28), (62, 72),
        (82, 28), (82, 72),
    ],
    10: [
        (18, 28), (18, 72),
        (30, 50),
        (38, 28), (38, 72),
        (62, 28), (62, 72),
        (70, 50),
        (82, 28), (82, 72),
    ],
}

FACE_UNICODE = {"J": "\u265E", "Q": "\u2655", "K": "\u2654"}


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
# Font helpers
# ---------------------------------------------------------------------------

_FONT_SEARCH_PATHS = [
    "/usr/share/fonts/truetype/dejavu/",
    "/usr/share/fonts/truetype/liberation/",
    "/usr/share/fonts/truetype/lato/",
    "/usr/share/fonts/truetype/freefont/",
    "/usr/share/fonts/truetype/ubuntu/",
    "/usr/local/share/fonts/",
]


def find_font(name: str) -> str | None:
    """Return the first filesystem path that matches *name* (case-insensitive).

    Args:
        name: Font filename fragment to search for (e.g. 'DejaVuSerif-Bold').

    Returns:
        Absolute path to the font file, or ``None`` if not found.
    """
    for base in _FONT_SEARCH_PATHS:
        p = Path(base)
        if not p.exists():
            continue
        for f in p.glob("*.ttf"):
            if name.lower() in f.name.lower():
                return str(f)
    return None


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font by name fragment at the requested pixel *size*.

    Searches :data:`_FONT_SEARCH_PATHS` via :func:`find_font`.  Falls back to
    Pillow's built-in bitmap font if the named font cannot be located or loaded.

    Args:
        name: Font filename fragment (case-insensitive, e.g. 'Lato-Bold').
        size: Desired font size in pixels.

    Returns:
        A :class:`~PIL.ImageFont.FreeTypeFont` on success, or the Pillow default
        :class:`~PIL.ImageFont.ImageFont` on failure.
    """
    path = find_font(name)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


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
        pip_area: tuple[int, int, int, int],  # left, top, right, bottom
        color: tuple,
    ) -> None:
        symbol = SUIT_SYMBOLS[suit]
        left, top, right, bottom = pip_area
        area_w = right - left
        area_h = bottom - top
        for row_pct, col_pct in PIP_LAYOUTS.get(count, []):
            px = left + int(area_w * col_pct / 100)
            py = top + int(area_h * row_pct / 100)
            # rotate bottom pips 180°
            bbox = draw.textbbox((0, 0), symbol, font=pip_font)
            pw = bbox[2] - bbox[0]
            ph = bbox[3] - bbox[1]
            x = px - pw // 2
            y = py - ph // 2
            if row_pct > 50:
                # render on a small sub-image and rotate
                tmp = Image.new("RGBA", (pw + 4, ph + 4), (0, 0, 0, 0))
                td = ImageDraw.Draw(tmp)
                td.text((2, 2), symbol, font=pip_font, fill=color)
                tmp = tmp.rotate(180)
                draw._image.paste(tmp, (x - 2, y - 2), tmp)
            else:
                draw.text((x, y), symbol, font=pip_font, fill=color)


# ---------------------------------------------------------------------------
# Theme 1 — Classic
# ---------------------------------------------------------------------------

class ClassicTheme(Theme):
    """Traditional playing card: cream background, DejaVu Serif, ornamental border."""

    name = "classic"

    BG = (245, 241, 232)        # cream
    BORDER = (28, 28, 46)       # near-black
    RED = (185, 28, 28)
    BLACK = (28, 28, 46)
    BACK_BG = (26, 77, 46)      # dark green
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
        pad_x, pad_y = 22, 20
        if top_left:
            centered_text(draw, pad_x + 14, pad_y + 14, rank, rank_font, color)
            centered_text(draw, pad_x + 14, pad_y + 38, symbol, suit_font, color)
        else:
            cx = self.W - pad_x - 14
            cy = self.H - pad_y - 14
            # render upside-down
            bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
            rw = bbox_r[2] - bbox_r[0]
            rh = bbox_r[3] - bbox_r[1]
            tmp_r = Image.new("RGBA", (rw + 4, rh + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tmp_r).text((2, 2), rank, font=rank_font, fill=color)
            tmp_r = tmp_r.rotate(180)
            draw._image.paste(tmp_r, (cx - rw // 2 - 2, cy - rh // 2 - 2), tmp_r)

            bbox_s = draw.textbbox((0, 0), symbol, font=suit_font)
            sw = bbox_s[2] - bbox_s[0]
            sh = bbox_s[3] - bbox_s[1]
            sy = cy + rh // 2 + 6
            tmp_s = Image.new("RGBA", (sw + 4, sh + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tmp_s).text((2, 2), symbol, font=suit_font, fill=color)
            tmp_s = tmp_s.rotate(180)
            draw._image.paste(tmp_s, (cx - sw // 2 - 2, sy - 2), tmp_s)

    def draw_center(self, draw, rank, suit, fonts):
        color = self.suit_color(suit)
        if rank in FACE_UNICODE:
            sym = FACE_UNICODE[rank]
            centered_text(draw, self.W // 2, self.H // 2, sym, fonts["face"], color)
        else:
            count = pip_count(rank)
            if count:
                margin_x = int(self.W * 0.12)
                margin_y = int(self.H * 0.16)
                self._draw_pips(
                    draw, suit, count, fonts["pip"],
                    (margin_x, margin_y, self.W - margin_x, self.H - margin_y),
                    color,
                )

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
            draw.line([(offset, 0), (offset + self.H, self.H)], fill=(*self.BACK_ACCENT[:3], 30), width=1)
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
    BORDER = (229, 231, 235)    # light grey border
    BACK_BG = (17, 24, 39)      # very dark navy

    def suit_color(self, suit: str) -> tuple:
        return self.RED if suit in ("hearts", "diamonds") else self.BLUE

    def _accent_color(self, suit: str) -> tuple:
        return self.suit_color(suit)

    def draw_background(self, draw: ImageDraw.ImageDraw, img: Image.Image) -> None:
        draw_rounded_rect(draw, (0, 0, self.W - 1, self.H - 1), 16, fill=self.BG)

    def draw_border(self, draw: ImageDraw.ImageDraw) -> None:
        draw_rounded_rect(
            draw, (0, 0, self.W - 1, self.H - 1), 16,
            fill=None, outline=self.BORDER, width=3,
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
        pad_x, pad_y = 18, 16
        if top_left:
            centered_text(draw, pad_x + 16, pad_y + 16, rank, rank_font, color)
            centered_text(draw, pad_x + 16, pad_y + 42, symbol, suit_font, color)
        else:
            cx = self.W - pad_x - 16
            cy = self.H - pad_y - 16
            bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
            rw = bbox_r[2] - bbox_r[0]
            rh = bbox_r[3] - bbox_r[1]
            tmp_r = Image.new("RGBA", (rw + 4, rh + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tmp_r).text((2, 2), rank, font=rank_font, fill=color)
            tmp_r = tmp_r.rotate(180)
            draw._image.paste(tmp_r, (cx - rw // 2 - 2, cy - rh // 2 - 2), tmp_r)

            bbox_s = draw.textbbox((0, 0), symbol, font=suit_font)
            sw = bbox_s[2] - bbox_s[0]
            sh = bbox_s[3] - bbox_s[1]
            sy = cy + rh // 2 + 8
            tmp_s = Image.new("RGBA", (sw + 4, sh + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tmp_s).text((2, 2), symbol, font=suit_font, fill=color)
            tmp_s = tmp_s.rotate(180)
            draw._image.paste(tmp_s, (cx - sw // 2 - 2, sy - 2), tmp_s)

    def draw_center(self, draw, rank, suit, fonts):
        # accent bars drawn here because we need suit colour
        self._draw_accent_bar(draw, suit)
        color = self.suit_color(suit)
        if rank in FACE_UNICODE:
            sym = FACE_UNICODE[rank]
            centered_text(draw, self.W // 2, self.H // 2, sym, fonts["face"], color)
        else:
            count = pip_count(rank)
            if count:
                margin_x = int(self.W * 0.13)
                margin_y = int(self.H * 0.15)
                self._draw_pips(
                    draw, suit, count, fonts["pip"],
                    (margin_x, margin_y, self.W - margin_x, self.H - margin_y),
                    color,
                )

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

    BG = (240, 230, 200)        # aged paper
    DARK_RED = (120, 30, 30)    # burgundy
    DARK_NAVY = (20, 20, 60)    # dark navy
    BORDER_OUTER = (101, 67, 33)   # brown
    BORDER_INNER = (160, 110, 60)  # lighter brown
    BACK_BG = (55, 27, 12)        # dark walnut

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
        pad_x, pad_y = 24, 22
        if top_left:
            centered_text(draw, pad_x + 12, pad_y + 12, rank, rank_font, color)
            centered_text(draw, pad_x + 12, pad_y + 36, symbol, suit_font, color)
        else:
            cx = self.W - pad_x - 12
            cy = self.H - pad_y - 12
            bbox_r = draw.textbbox((0, 0), rank, font=rank_font)
            rw = bbox_r[2] - bbox_r[0]
            rh = bbox_r[3] - bbox_r[1]
            tmp_r = Image.new("RGBA", (rw + 4, rh + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tmp_r).text((2, 2), rank, font=rank_font, fill=color)
            tmp_r = tmp_r.rotate(180)
            draw._image.paste(tmp_r, (cx - rw // 2 - 2, cy - rh // 2 - 2), tmp_r)

            bbox_s = draw.textbbox((0, 0), symbol, font=suit_font)
            sw = bbox_s[2] - bbox_s[0]
            sh = bbox_s[3] - bbox_s[1]
            sy = cy + rh // 2 + 8
            tmp_s = Image.new("RGBA", (sw + 4, sh + 4), (0, 0, 0, 0))
            ImageDraw.Draw(tmp_s).text((2, 2), symbol, font=suit_font, fill=color)
            tmp_s = tmp_s.rotate(180)
            draw._image.paste(tmp_s, (cx - sw // 2 - 2, sy - 2), tmp_s)

    def draw_center(self, draw, rank, suit, fonts):
        color = self.suit_color(suit)
        if rank in FACE_UNICODE:
            sym = FACE_UNICODE[rank]
            centered_text(draw, self.W // 2, self.H // 2, sym, fonts["face"], color)
        else:
            count = pip_count(rank)
            if count:
                margin_x = int(self.W * 0.12)
                margin_y = int(self.H * 0.15)
                self._draw_pips(
                    draw, suit, count, fonts["pip"],
                    (margin_x, margin_y, self.W - margin_x, self.H - margin_y),
                    color,
                )

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
            draw, (m, m, self.W - m - 1, self.H - m - 1),
            12, fill=None, outline=(160, 110, 60, 200), width=2,
        )
        m2 = 20
        draw_rounded_rect(
            draw, (m2, m2, self.W - m2 - 1, self.H - m2 - 1),
            8, fill=None, outline=(160, 110, 60, 120), width=1,
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
        "rank_name": "DejaVuSerif-Bold",
        "suit_name": "DejaVuSerif-Bold",
        "pip_name": "DejaVuSerif",
        "face_name": "DejaVuSerif-Bold",
    },
    "modern": {
        "rank_name": "Lato-Bold",
        "suit_name": "Lato-Bold",
        "pip_name": "Lato-Regular",
        "face_name": "Lato-Bold",
    },
    "vintage": {
        "rank_name": "LiberationSerif-Bold",
        "suit_name": "LiberationSerif-Regular",
        "pip_name": "LiberationSerif-Regular",
        "face_name": "LiberationSerif-Bold",
    },
}


def build_fonts(theme_name: str, W: int, H: int) -> dict:
    cfg = THEME_FONTS[theme_name]
    scale = W / 500  # relative to 500 px wide reference
    return {
        "rank": load_font(cfg["rank_name"], int(44 * scale)),
        "suit": load_font(cfg["suit_name"], int(30 * scale)),
        "pip": load_font(cfg["pip_name"], int(54 * scale)),
        "face": load_font(cfg["face_name"], int(180 * scale)),
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
    theme.draw_border(draw)

    theme.draw_corner(draw, rank, suit, True, fonts["rank"], fonts["suit"])
    theme.draw_corner(draw, rank, suit, False, fonts["rank"], fonts["suit"])
    theme.draw_center(draw, rank, suit, fonts)

    return img


def render_back(theme: Theme) -> Image.Image:
    img = Image.new("RGBA", (theme.W, theme.H), (0, 0, 0, 0))
    theme.draw_card_back(img)
    return img


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

THEMES: dict[str, Theme] = {
    "classic": ClassicTheme(),
    "modern": ModernTheme(),
    "vintage": VintageTheme(),
}


def generate_all(output_dir: Path, styles: list[str], W: int, H: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(styles) * (52 + 1)  # 52 cards + back per theme
    done = 0

    for style_name in styles:
        theme = THEMES[style_name]
        theme.W = W
        theme.H = H

        style_dir = output_dir / style_name
        style_dir.mkdir(parents=True, exist_ok=True)

        fonts = build_fonts(style_name, W, H)

        for suit in SUITS:
            for rank in RANKS:
                img = render_card(theme, rank, suit, fonts)
                filename = f"{rank}_{suit}.png"
                img.convert("RGB").save(style_dir / filename, "PNG", optimize=True)
                done += 1
                pct = done * 100 // total
                print(f"\r  [{pct:3d}%] {style_name}: {rank} of {suit}    ", end="", flush=True)

        # card back
        back = render_back(theme)
        back.convert("RGB").save(style_dir / "back.png", "PNG", optimize=True)
        done += 1
        print(f"\r  [{done * 100 // total:3d}%] {style_name}: back              ", end="", flush=True)

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
        default=str(Path(__file__).parent.parent / "frontend" / "public" / "images" / "cards"),
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
