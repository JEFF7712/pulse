#!/usr/bin/env python3
"""Emit PNG-in-ICO favicon(s) matching pulse-mark.svg (stdlib only)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _png_rgba(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows: list[bytes] = []
    stride = width * 4
    for y in range(height):
        rows.append(b"\x00" + pixels[y * stride : (y + 1) * stride])
    raw = b"".join(rows)
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _pulse_rgba(size: int, bg: tuple[int, int, int] = (0x1A, 0x1A, 0x1A)) -> bytes:
    cx = (size - 1) / 2.0
    cy = (size - 1) / 2.0
    scale = size / 32.0
    rx_inner_out = 5.35 * scale
    ry_inner_out = 4.45 * scale
    k = ry_inner_out / rx_inner_out  # same aspect as inner / outer ovals
    rx_inner_in = 4.35 * scale
    ry_inner_in = rx_inner_in * k
    rx_ring_in = 10.0 * scale
    ry_ring_in = rx_ring_in * k
    rx_ring_out = 11.5 * scale
    ry_ring_out = rx_ring_out * k
    br, bg_, bb = bg
    out = bytearray(size * size * 4)
    i = 0
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            u_inner_in = (dx / rx_inner_in) ** 2 + (dy / ry_inner_in) ** 2
            u_inner_out = (dx / rx_inner_out) ** 2 + (dy / ry_inner_out) ** 2
            in_inner_ring = u_inner_in > 1.0 and u_inner_out <= 1.0
            u_in = (dx / rx_ring_in) ** 2 + (dy / ry_ring_in) ** 2
            u_out = (dx / rx_ring_out) ** 2 + (dy / ry_ring_out) ** 2
            in_outer_ring = u_in > 1.0 and u_out <= 1.0
            if in_inner_ring:
                out[i : i + 4] = bytes([0x4A, 0xDE, 0x80, 0xFF])
            elif in_outer_ring:
                rr, gg, b_ = 0x4A, 0xDE, 0x80
                a = 0.45
                out[i] = int(rr * a + br * (1 - a))
                out[i + 1] = int(gg * a + bg_ * (1 - a))
                out[i + 2] = int(b_ * a + bb * (1 - a))
                out[i + 3] = 255
            else:
                out[i : i + 4] = bytes([br, bg_, bb, 0xFF])
            i += 4
    return bytes(out)


def _ico_from_pngs(pairs: list[tuple[int, int, bytes]]) -> bytes:
    # pairs: (width, height, png_bytes)
    offset = 6 + len(pairs) * 16
    parts: list[bytes] = [
        struct.pack("<HHH", 0, 1, len(pairs)),
    ]
    blob = bytearray()
    for w, h, png in pairs:
        w_b = 0 if w >= 256 else w
        h_b = 0 if h >= 256 else h
        parts.append(
            struct.pack(
                "<BBBBHHII",
                w_b,
                h_b,
                0,
                0,
                1,
                32,
                len(png),
                offset + len(blob),
            )
        )
        blob.extend(png)
    return b"".join(parts) + bytes(blob)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    public = root / "docs-app" / "docs" / "public"
    public.mkdir(parents=True, exist_ok=True)
    sizes = (16, 32, 48)
    pngs: list[tuple[int, int, bytes]] = []
    for s in sizes:
        px = _pulse_rgba(s)
        pngs.append((s, s, _png_rgba(s, s, px)))
    ico = _ico_from_pngs(pngs)
    out = public / "favicon.ico"
    out.write_bytes(ico)
    print(f"Wrote {out} ({len(ico)} bytes)")


if __name__ == "__main__":
    main()
