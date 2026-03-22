"""Tests for cc-sessions identicon generation."""

import base64
import xml.etree.ElementTree as ET

from cc_sessions.identicon import (
    COLORS,
    GOOD_PATTERNS,
    generate,
    _djb2,
    _bits_to_grid,
)


class TestDjb2:
    def test_deterministic(self):
        assert _djb2("VoiceText") == _djb2("VoiceText")

    def test_different_inputs_different_hashes(self):
        assert _djb2("VoiceText") != _djb2("claude-code")

    def test_empty_string(self):
        assert _djb2("") == 5381

    def test_unicode(self):
        h = _djb2("项目名")
        assert isinstance(h, int)
        assert h > 0


class TestGoodPatterns:
    def test_min_popcount(self):
        for bits in GOOD_PATTERNS:
            assert bin(bits).count("1") >= 3

    def test_bottom_row_has_content(self):
        for bits in GOOD_PATTERNS:
            bottom_left = (bits >> 4) & 1
            bottom_center = (bits >> 5) & 1
            assert bottom_left or bottom_center

    def test_not_all_filled(self):
        assert 63 not in GOOD_PATTERNS

    def test_vertical_connectivity(self):
        for bits in GOOD_PATTERNS:
            r0 = (bits & 0x03) != 0
            r1 = (bits & 0x0C) != 0
            r2 = (bits & 0x30) != 0
            if r0 and r2:
                assert r1, f"pattern {bits:06b} has gap in middle row"


class TestBitsToGrid:
    def test_symmetry(self):
        for bits in GOOD_PATTERNS:
            grid = _bits_to_grid(bits)
            for row in grid:
                assert row[0] == row[2], "left must mirror right"

    def test_dimensions(self):
        grid = _bits_to_grid(GOOD_PATTERNS[0])
        assert len(grid) == 3
        assert all(len(row) == 3 for row in grid)


class TestGenerate:
    def test_deterministic(self):
        assert generate("VoiceText") == generate("VoiceText")

    def test_different_projects_different_icons(self):
        names = ["VoiceText", "claude-code", "WenZi", "dotfiles",
                 "react-app", "api-server", "blog", "infra"]
        results = [generate(n) for n in names]
        assert len(set(results)) >= 6

    def test_data_uri_format(self):
        uri = generate("test-project")
        assert uri.startswith("data:image/svg+xml;base64,")

    def test_valid_svg(self):
        uri = generate("test-project")
        b64 = uri.split(",", 1)[1]
        svg_bytes = base64.b64decode(b64)
        root = ET.fromstring(svg_bytes)
        assert root.tag == "{http://www.w3.org/2000/svg}svg"

    def test_empty_name(self):
        uri = generate("")
        assert uri.startswith("data:image/svg+xml;base64,")

    def test_long_name(self):
        uri = generate("a" * 1000)
        assert uri.startswith("data:image/svg+xml;base64,")

    def test_color_in_palette(self):
        for name in ["VoiceText", "claude-code", "WenZi"]:
            h = _djb2(name)
            color = COLORS[h % len(COLORS)]
            uri = generate(name)
            b64 = uri.split(",", 1)[1]
            svg_str = base64.b64decode(b64).decode()
            assert color in svg_str
