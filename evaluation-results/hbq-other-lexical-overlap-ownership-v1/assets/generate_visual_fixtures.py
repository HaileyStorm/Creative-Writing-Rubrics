"""Deterministically generate small public PNG fixtures; no model is used."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 64, 48
NAMES = ("fixture-a", "fixture-b", "fixture-c", "fixture-d", "fixture-e", "fixture-f")


def png_bytes(name: str) -> bytes:
    seed = hashlib.sha256(("hbq-l2-public-" + name).encode("utf-8")).digest()
    rows = []
    for y in range(HEIGHT):
        row = bytearray()
        for x in range(WIDTH):
            horizon = 22 + seed[0] % 4
            if y < horizon:
                pixel = (70 + (x // 4), 130 + (y // 3), 190)
            else:
                distance = max(0, y - horizon)
                pixel = (150 - min(90, distance * 3), 100 - min(60, distance * 2), 65)
            if name in {"fixture-a", "fixture-f"} and y >= horizon and abs(x - 32) <= max(1, (y - horizon) // 3):
                pixel = (230, 210, 125)
            if name == "fixture-b" and (x + y + seed[1]) % 11 == 0:
                pixel = (210, 80, 90)
            if name == "fixture-c" and y >= horizon:
                pixel = (120, 120, 120)
            if name == "fixture-d" and x > 31:
                pixel = (90, 90, 90)
            if name == "fixture-e":
                pixel = (105, 105, 105)
            row.extend(pixel)
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    # Stored DEFLATE avoids compressor-version drift across supported Python runtimes.
    adler_a, adler_b = 1, 0
    for byte in raw:
        adler_a = (adler_a + byte) % 65521
        adler_b = (adler_b + adler_a) % 65521
    if len(raw) > 65535:
        raise ValueError("Fixture raw stream exceeds the deterministic stored-block limit")
    stored_deflate = b"\x78\x01\x01" + struct.pack("<HH", len(raw), 0xffff - len(raw)) + raw + struct.pack(">I", (adler_b << 16) | adler_a)
    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = 0xffffffff
        for byte in kind + data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ (0xedb88320 if crc & 1 else 0)
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc ^ 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) + chunk(b"IDAT", stored_deflate) + chunk(b"IEND", b"")


def main() -> None:
    entries = []
    for name in NAMES:
        path = ROOT / f"{name}.png"
        data = png_bytes(name)
        path.write_bytes(data)
        entries.append({"fixture_id": name, "path": f"assets/{path.name}", "mime_type": "image/png", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "width": WIDTH, "height": HEIGHT})
    manifest = {"format_version": 1, "generator": "assets/generate_visual_fixtures.py", "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "fixtures": entries}
    (ROOT / "fixture-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
