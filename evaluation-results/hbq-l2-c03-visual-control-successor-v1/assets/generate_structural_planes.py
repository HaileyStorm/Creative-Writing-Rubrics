"""Render deterministic, text-free structural-plane fixtures for L2 c03."""
from __future__ import annotations

import struct
import zlib
from functools import lru_cache


WIDTH, HEIGHT = 320, 220
BACKGROUND = (244, 242, 236)
WALL = (221, 224, 222)
PLANE = (176, 196, 204)
GRID = (42, 57, 66)
EDGE = (31, 43, 50)
FLOOR_CORNERS = ((44, 196), (276, 196), (206, 100), (114, 100))
COHERENT_VANISHING_POINT = (160, 36)
INCOMPATIBLE_LEFT_VANISHING_POINT = (128, 52)
INCOMPATIBLE_RIGHT_VANISHING_POINT = (188, 52)
LONGITUDINAL_BOTTOMS = ((95, 196), (110, 196), (125, 196), (200, 196), (215, 196), (230, 196))


def _blank() -> list[list[tuple[int, int, int]]]:
    return [[BACKGROUND for _ in range(WIDTH)] for _ in range(HEIGHT)]


def _set(canvas: list[list[tuple[int, int, int]]], x: int, y: int, color: tuple[int, int, int]) -> None:
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        canvas[y][x] = color


def _line(canvas: list[list[tuple[int, int, int]]], start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int], width: int = 1) -> None:
    x0, y0 = start
    x1, y1 = end
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        for oy in range(-(width // 2), width // 2 + 1):
            for ox in range(-(width // 2), width // 2 + 1):
                _set(canvas, x0 + ox, y0 + oy, color)
        if (x0, y0) == (x1, y1):
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def _fill_polygon(canvas: list[list[tuple[int, int, int]]], points: tuple[tuple[int, int], ...], color: tuple[int, int, int]) -> None:
    for y in range(max(y for _x, y in points), min(y for _x, y in points) - 1, -1):
        crossings: list[float] = []
        for index, (x0, y0) in enumerate(points):
            x1, y1 = points[(index + 1) % len(points)]
            if y0 == y1 or not (min(y0, y1) <= y < max(y0, y1)):
                continue
            crossings.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        crossings.sort()
        for index in range(0, len(crossings) - 1, 2):
            for x in range(int(crossings[index] + 0.999999), int(crossings[index + 1]) + 1):
                _set(canvas, x, y, color)


def _lerp(start: tuple[int, int], end: tuple[int, int], amount: float) -> tuple[int, int]:
    return (round(start[0] + (end[0] - start[0]) * amount), round(start[1] + (end[1] - start[1]) * amount))


def _room(canvas: list[list[tuple[int, int, int]]]) -> None:
    _fill_polygon(canvas, ((18, 18), (302, 18), (276, 196), (44, 196)), WALL)
    _line(canvas, (18, 18), (44, 196), EDGE, 2)
    _line(canvas, (302, 18), (276, 196), EDGE, 2)
    _line(canvas, (18, 18), (302, 18), EDGE, 2)
    _fill_polygon(canvas, FLOOR_CORNERS, PLANE)
    for index in range(4):
        _line(canvas, FLOOR_CORNERS[index], FLOOR_CORNERS[(index + 1) % 4], EDGE, 2)


def _horizontal_rows(canvas: list[list[tuple[int, int, int]]]) -> None:
    left_top, right_top, right_bottom, left_bottom = FLOOR_CORNERS[3], FLOOR_CORNERS[2], FLOOR_CORNERS[1], FLOOR_CORNERS[0]
    for amount in (0.14, 0.29, 0.47, 0.67, 0.86):
        left = _lerp(left_top, left_bottom, amount)
        right = _lerp(right_top, right_bottom, amount)
        _line(canvas, left, right, GRID, 1)


def _coherent_segments() -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    return tuple((bottom, (160 + (bottom[0] - 160) * 2 // 5, 100)) for bottom in LONGITUDINAL_BOTTOMS)


def _incompatible_segments() -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    segments: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for bottom in LONGITUDINAL_BOTTOMS[:3]:
        segments.append((bottom, (128 + (bottom[0] - 128) // 3, 100)))
    for bottom in LONGITUDINAL_BOTTOMS[3:]:
        segments.append((bottom, (188 + (bottom[0] - 188) // 3, 100)))
    return tuple(segments)


def _line_intersection(first: tuple[tuple[int, int], tuple[int, int]], second: tuple[tuple[int, int], tuple[int, int]]) -> tuple[int, int]:
    (x1, y1), (x2, y2) = first
    (x3, y3), (x4, y4) = second
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denominator == 0:
        raise ValueError("Longitudinal rays must not be parallel")
    numerator_x = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4))
    numerator_y = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4))
    if numerator_x % denominator or numerator_y % denominator:
        raise ValueError("Rendered ray intersection must remain on whole pixels")
    return (numerator_x // denominator, numerator_y // denominator)


def _coherent_canvas() -> list[list[tuple[int, int, int]]]:
    canvas = _blank()
    _room(canvas)
    for bottom, top in _coherent_segments():
        _line(canvas, bottom, top, GRID, 1)
    _horizontal_rows(canvas)
    return canvas


def _incompatible_canvas() -> list[list[tuple[int, int, int]]]:
    canvas = _blank()
    _room(canvas)
    for bottom, top in _incompatible_segments():
        _line(canvas, bottom, top, GRID, 1)
    _horizontal_rows(canvas)
    return canvas


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _stored_zlib(raw: bytes) -> bytes:
    """Use stored DEFLATE blocks so fixture bytes do not vary with zlib versions."""
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


def _png(canvas: list[list[tuple[int, int, int]]]) -> bytes:
    raw = b"".join(bytes((0,)) + bytes(component for pixel in row for component in pixel) for row in canvas)
    signature = bytes((137, 80, 78, 71, 13, 10, 26, 10))
    return signature + _chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", _stored_zlib(raw)) + _chunk(b"IEND", b"")


@lru_cache(maxsize=1)
def fixture_png_bytes() -> dict[str, bytes]:
    return {"structural_plane_incompatible_v1": _png(_incompatible_canvas()), "structural_plane_coherent_v1": _png(_coherent_canvas())}


def pixel_invariants() -> dict[str, object]:
    fixtures = fixture_png_bytes()
    coherent = _coherent_segments()
    incompatible = _incompatible_segments()
    coherent_intersection = _line_intersection(coherent[0], coherent[-1])
    incompatible_left_intersection = _line_intersection(incompatible[0], incompatible[2])
    incompatible_right_intersection = _line_intersection(incompatible[3], incompatible[-1])
    return {
        "dimensions": (WIDTH, HEIGHT),
        "text_or_directional_marks": "absent_by_generator_surface",
        "shared_structural_plane_corners": FLOOR_CORNERS,
        "coherent": {"derived_support_intersection": coherent_intersection, "declared_vanishing_point": COHERENT_VANISHING_POINT, "longitudinal_rays": len(coherent), "transverse_rows": 5},
        "incompatible": {"derived_left_support_intersection": incompatible_left_intersection, "derived_right_support_intersection": incompatible_right_intersection, "longitudinal_rays": len(incompatible), "transverse_rows": 5, "vanishing_points_distinct": incompatible_left_intersection != incompatible_right_intersection},
        "fixtures_distinct": fixtures["structural_plane_incompatible_v1"] != fixtures["structural_plane_coherent_v1"],
    }
