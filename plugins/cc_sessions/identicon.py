"""Generate 3x3 symmetric geometric identicons for project names."""

from __future__ import annotations

import base64
from functools import lru_cache

COLORS = [
    "#E05252", "#E07B39", "#D4A843", "#5AAE5A", "#43A5A5", "#4A90D9",
    "#6B7FD9", "#8B6FC0", "#C06BAA", "#7C8A6E", "#9E7B5B", "#5B8A9E",
]


def _popcount(n: int) -> int:
    c = 0
    while n:
        c += n & 1
        n >>= 1
    return c


def _row_has_content(bits: int, row: int) -> bool:
    return bool(((bits >> (row * 2)) & 1) | ((bits >> (row * 2 + 1)) & 1))


def _build_good_patterns() -> list[int]:
    good = []
    for b in range(64):
        if _popcount(b) < 3:
            continue
        if not _row_has_content(b, 2):
            continue
        if b == 63:
            continue
        r0 = _row_has_content(b, 0)
        r1 = _row_has_content(b, 1)
        r2 = _row_has_content(b, 2)
        if r0 and r2 and not r1:
            continue
        good.append(b)
    return good


GOOD_PATTERNS = _build_good_patterns()


def _djb2(s: str) -> int:
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return h


def _bits_to_grid(bits: int) -> list[list[int]]:
    grid = []
    for row in range(3):
        left = (bits >> (row * 2)) & 1
        center = (bits >> (row * 2 + 1)) & 1
        grid.append([left, center, left])
    return grid


@lru_cache(maxsize=128)
def generate(name: str, size: int = 32) -> str:
    """Generate a data URI for a 3x3 identicon SVG from a project name."""
    h = _djb2(name)
    color = COLORS[h % len(COLORS)]
    bits = GOOD_PATTERNS[(h >> 8) % len(GOOD_PATTERNS)]
    grid = _bits_to_grid(bits)

    cs = size / 3
    rx = size * 0.1875
    inset = cs * 0.12
    cell_size = cs - inset * 2
    cell_rx = cell_size * 0.2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {size} {size}" width="{size}" height="{size}">',
        f'<rect width="{size}" height="{size}" rx="{rx}" '
        f'fill="{color}" opacity="0.18"/>',
    ]

    for row in range(3):
        for col in range(3):
            if grid[row][col]:
                x = col * cs + inset
                y = row * cs + inset
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{cell_size}" '
                    f'height="{cell_size}" rx="{cell_rx}" fill="{color}"/>'
                )

    parts.append("</svg>")
    svg = "".join(parts)
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"
