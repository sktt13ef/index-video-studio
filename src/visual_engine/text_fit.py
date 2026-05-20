from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageDraw, ImageFont


FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/simhei.ttf"),
    Path("C:/Windows/Fonts/simsun.ttc"),
]

BAD_LINE_START = set("，。！？；：、,.!?;:)）】》")


@dataclass
class FittedText:
    lines: list[str]
    font_size: int
    overflow: bool
    line_height: int


def resolve_font_path(bold: bool = False) -> Path:
    if bold and FONT_CANDIDATES[0].exists():
        return FONT_CANDIDATES[0]
    for path in FONT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("No supported Chinese font found in C:/Windows/Fonts")


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(resolve_font_path(bold=bold)), size=size)


def visual_len(text: str) -> int:
    total = 0
    for char in text:
        if unicodedata.east_asian_width(char) in {"F", "W", "A"}:
            total += 2
        else:
            total += 1
    return total


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return int(box[2] - box[0])


def _split_units(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    units: list[str] = []
    buffer = ""
    for char in text:
        if char == " ":
            if buffer:
                units.append(buffer)
                buffer = ""
            units.append(char)
        elif char.isascii() and (char.isalnum() or char in {"%", ".", "/", "-", "_"}):
            buffer += char
        else:
            if buffer:
                units.append(buffer)
                buffer = ""
            units.append(char)
    if buffer:
        units.append(buffer)
    return units


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    *,
    max_visual_chars: int = 36,
) -> list[str]:
    units = _split_units(text)
    lines: list[str] = []
    current = ""
    for unit in units:
        candidate = (current + unit).strip()
        if not candidate:
            continue
        too_wide = text_width(draw, candidate, font) > max_width
        too_long = visual_len(candidate) > max_visual_chars
        if current and (too_wide or too_long):
            lines.append(current.strip())
            current = unit.strip()
        else:
            current = candidate
    if current:
        lines.append(current.strip())

    repaired: list[str] = []
    for line in lines:
        if repaired and line and line[0] in BAD_LINE_START:
            repaired[-1] += line[0]
            line = line[1:].strip()
        if line:
            repaired.append(line)
    return repaired


def fit_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_lines: int,
    *,
    start_size: int,
    min_size: int,
    bold: bool = False,
    max_visual_chars: int = 36,
) -> FittedText:
    for size in range(start_size, min_size - 1, -2):
        font = load_font(size, bold=bold)
        lines = wrap_text(draw, text, font, max_width, max_visual_chars=max_visual_chars)
        if len(lines) <= max_lines and all(text_width(draw, line, font) <= max_width for line in lines):
            return FittedText(lines=lines, font_size=size, overflow=False, line_height=int(size * 1.32))

    font = load_font(min_size, bold=bold)
    lines = wrap_text(draw, text, font, max_width, max_visual_chars=max_visual_chars)
    return FittedText(lines=lines[:max_lines], font_size=min_size, overflow=len(lines) > max_lines, line_height=int(min_size * 1.32))

