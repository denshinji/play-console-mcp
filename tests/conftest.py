from __future__ import annotations

import struct
import zlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from play_console_mcp.config import Settings
from play_console_mcp.play import PlayConsole

LISTING_ID = """\
# Listingan Google Play — Indonesia (id, default)

## Nama aplikasi (6/30)

Contoh

## Deskripsi singkat (31/80)

Catat skincare dan rutinitasmu.

## Deskripsi lengkap

Contoh membantu kamu merawat diri.

• Simpan produk
• Atur rutinitas

Catatan: bukan saran medis.
"""


def png_bytes(width: int, height: int, color_type: int = 2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", b"") + chunk(b"IEND", b"")


def make_service() -> MagicMock:
    service = MagicMock(name="androidpublisher")
    edits = service.edits.return_value
    edits.insert.return_value.execute.return_value = {"id": "edit-1"}
    edits.tracks.return_value.list.return_value.execute.return_value = {"tracks": []}
    return service


@pytest.fixture
def service() -> MagicMock:
    return make_service()


def write_store(root: Path) -> Path:
    """Builds root/docs/store/play the way a real app repo lays it out."""
    store = root / "docs/store/play"
    (store / "screenshots").mkdir(parents=True)
    (store / "listing-id.md").write_text(LISTING_ID, encoding="utf-8")
    (store / "icon-512.png").write_bytes(png_bytes(512, 512, color_type=6))
    (store / "feature-graphic-1024x500.png").write_bytes(png_bytes(1024, 500))
    for name in ("02-shelf.png", "01-home.png", "03-insight.png"):
        (store / "screenshots" / name).write_bytes(png_bytes(1080, 1920))
    return store


@pytest.fixture
def store_root(tmp_path) -> Path:
    root = tmp_path / "app-repo"
    write_store(root)
    return root


@pytest.fixture
def make_play(service, tmp_path):
    def factory(root: Path = tmp_path, allow_production: bool = False) -> PlayConsole:
        settings = Settings(
            credentials_path=tmp_path / "missing.json",
            package_names=("com.example.app",),
            asset_root=root.resolve(),
            allow_production=allow_production,
        )
        return PlayConsole(settings, service_factory=lambda: service)

    return factory
