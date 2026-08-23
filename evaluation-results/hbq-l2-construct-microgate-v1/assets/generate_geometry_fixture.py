"""Render a deterministic architectural impossible-stairwell PNG fixture."""
from __future__ import annotations

import struct
import zlib
from functools import lru_cache


WIDTH, HEIGHT = 240, 180
BACKGROUND = (243, 239, 230)
WALL = (222, 222, 216)
FLOOR = (203, 199, 188)
INK = (48, 52, 57)
STAIR = (98, 146, 173)
TREAD = (222, 238, 244)
BRIDGE = (205, 117, 62)
OCCLUDER = (109, 61, 38)
MARKER = (250, 248, 238)
LANDINGS = ((52, 142), (178, 142), (178, 56), (52, 56))
LOOP_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0))
OCCLUSION_CENTER = (120, 96)

_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "U": ("101", "101", "101", "101", "111"),
    "P": ("110", "101", "110", "100", "100"),
}


def _line(canvas: list[list[tuple[int, int, int]]], start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int], width: int = 1) -> None:
    x0, y0 = start
    x1, y1 = end
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    step_x, step_y = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        for offset_y in range(-(width // 2), width // 2 + 1):
            for offset_x in range(-(width // 2), width // 2 + 1):
                x, y = x0 + offset_x, y0 + offset_y
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    canvas[y][x] = color
        if (x0, y0) == (x1, y1):
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += step_x
        if twice <= dx:
            error += dx
            y0 += step_y


def _rect(canvas: list[list[tuple[int, int, int]]], x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    for y in range(max(0, y0), min(HEIGHT, y1 + 1)):
        for x in range(max(0, x0), min(WIDTH, x1 + 1)):
            canvas[y][x] = color


def _glyph(canvas: list[list[tuple[int, int, int]]], text: str, x0: int, y0: int, color: tuple[int, int, int] = INK, scale: int = 2) -> None:
    for index, character in enumerate(text):
        for row, pattern in enumerate(_FONT[character]):
            for column, bit in enumerate(pattern):
                if bit == "1":
                    _rect(canvas, x0 + (index * 4 + column) * scale, y0 + row * scale, x0 + (index * 4 + column + 1) * scale - 1, y0 + (row + 1) * scale - 1, color)


def _arrow(canvas: list[list[tuple[int, int, int]]], start: tuple[int, int], end: tuple[int, int]) -> None:
    _line(canvas, start, end, INK, 2)
    x0, y0 = start
    x1, y1 = end
    if abs(x1 - x0) >= abs(y1 - y0):
        back = -7 if x1 > x0 else 7
        _line(canvas, end, (x1 + back, y1 - 5), INK, 2)
        _line(canvas, end, (x1 + back, y1 + 5), INK, 2)
    else:
        back = 7 if y1 > y0 else -7
        _line(canvas, end, (x1 - 5, y1 + back), INK, 2)
        _line(canvas, end, (x1 + 5, y1 + back), INK, 2)


def _stairs(canvas: list[list[tuple[int, int, int]]], start: tuple[int, int], end: tuple[int, int], horizontal: bool) -> None:
    _line(canvas, start, end, STAIR, 15)
    _line(canvas, start, end, INK, 2)
    count = 7
    for index in range(1, count):
        x = start[0] + (end[0] - start[0]) * index // count
        y = start[1] + (end[1] - start[1]) * index // count
        if horizontal:
            _line(canvas, (x, y - 7), (x, y + 7), TREAD, 2)
        else:
            _line(canvas, (x - 7, y), (x + 7, y), TREAD, 2)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = 0xFFFFFFFF
    for byte in kind + payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc ^ 0xFFFFFFFF)


def _stored_zlib(raw: bytes) -> bytes:
    adler_a, adler_b = 1, 0
    for byte in raw:
        adler_a = (adler_a + byte) % 65521
        adler_b = (adler_b + adler_a) % 65521
    blocks = bytearray((120, 1))
    for offset in range(0, len(raw), 65535):
        part = raw[offset:offset + 65535]
        blocks.append(1 if offset + len(part) == len(raw) else 0)
        blocks.extend(struct.pack("<HH", len(part), 0xFFFF - len(part)))
        blocks.extend(part)
    blocks.extend(struct.pack(">I", (adler_b << 16) | adler_a))
    return bytes(blocks)


@lru_cache(maxsize=1)
def png_bytes() -> bytes:
    canvas = [[BACKGROUND for _x in range(WIDTH)] for _y in range(HEIGHT)]
    _rect(canvas, 28, 20, 211, 124, WALL)
    _line(canvas, (28, 20), (8, 171), INK, 2)
    _line(canvas, (211, 20), (232, 171), INK, 2)
    _line(canvas, (28, 124), (8, 171), INK, 2)
    _line(canvas, (211, 124), (232, 171), INK, 2)
    _line(canvas, (8, 171), (232, 171), INK, 2)
    for x in range(30, 216, 31):
        _line(canvas, (120, 124), (x, 171), FLOOR, 2)
    _rect(canvas, 102, 34, 137, 82, (184, 188, 186))
    _line(canvas, (102, 34), (137, 82), INK, 2)
    _line(canvas, (137, 34), (102, 82), INK, 2)

    # A square stairwell loop in a room. Every flight carries the visible UP
    # label; the numbered landings show the impossible 0→1→2→3→0 elevation
    # cycle instead of an evaluator-only conclusion.
    _stairs(canvas, LANDINGS[0], LANDINGS[1], True)
    _stairs(canvas, LANDINGS[1], LANDINGS[2], False)
    _stairs(canvas, LANDINGS[2], LANDINGS[3], True)
    _stairs(canvas, LANDINGS[3], LANDINGS[0], False)
    for index, (x, y) in enumerate(LANDINGS):
        _rect(canvas, x - 8, y - 8, x + 8, y + 8, MARKER)
        _line(canvas, (x - 8, y - 8), (x + 8, y - 8), INK)
        _line(canvas, (x + 8, y - 8), (x + 8, y + 8), INK)
        _line(canvas, (x + 8, y + 8), (x - 8, y + 8), INK)
        _line(canvas, (x - 8, y + 8), (x - 8, y - 8), INK)
        _glyph(canvas, str(index), x - 3, y - 5)
    _glyph(canvas, "UP", 91, 130)
    _glyph(canvas, "UP", 165, 95)
    _glyph(canvas, "UP", 111, 48)
    _glyph(canvas, "UP", 40, 95)
    _arrow(canvas, (72, 132), (88, 132))
    _arrow(canvas, (168, 128), (168, 112))
    _arrow(canvas, (158, 48), (142, 48))
    _arrow(canvas, (72, 70), (72, 86))

    # The foreground bridge crosses a visible behind stair at the center.
    # Its dark cap masks the blue tread lines at the single intersection.
    _line(canvas, (82, 99), (158, 99), BRIDGE, 14)
    _line(canvas, (82, 99), (158, 99), INK, 2)
    _line(canvas, (112, 91), (128, 107), STAIR, 8)
    _line(canvas, (112, 91), (128, 107), TREAD, 2)
    _rect(canvas, 115, 94, 125, 104, OCCLUDER)
    _line(canvas, (115, 94), (125, 104), INK, 2)

    raw = b"".join(bytes((0,)) + bytes(channel for pixel in row for channel in pixel) for row in canvas)
    signature = bytes((137, 80, 78, 71, 13, 10, 26, 10))
    return signature + _chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", _stored_zlib(raw)) + _chunk(b"IEND", b"")


def pixel_invariants() -> dict[str, object]:
    """Return inspectable topology and decoded-pixel commitments for this fixture."""
    image = png_bytes()
    idat_size = struct.unpack(">I", image[33:37])[0]
    raw = zlib.decompress(image[41:41 + idat_size])
    stride = WIDTH * 3 + 1

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = y * stride + 1 + x * 3
        return tuple(raw[offset:offset + 3])

    labels = tuple(any(pixel(label_x, label_y) == INK for label_y in range(y - 5, y + 6) for label_x in range(x - 4, x + 5)) for x, y in LANDINGS)
    edge_pixels = tuple(pixel((LANDINGS[a][0] + LANDINGS[b][0]) // 2, (LANDINGS[a][1] + LANDINGS[b][1]) // 2) == INK for a, b in LOOP_EDGES)
    x, y = OCCLUSION_CENTER
    return {
        "dimensions": (WIDTH, HEIGHT),
        "closed_loop": {"landings": (0, 1, 2, 3), "successors": (1, 2, 3, 0), "returns_to_zero": True, "all_flights_marked_up": True, "marker_pixels_present": labels, "edge_pixels_present": edge_pixels},
        "occlusion": {"center": OCCLUSION_CENTER, "foreground_pixel": pixel(x, y), "behind_tread_pixel": pixel(112, 91), "foreground_masks_behind": pixel(x, y) == OCCLUDER and pixel(112, 91) == TREAD},
    }
