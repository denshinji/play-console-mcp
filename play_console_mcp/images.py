"""Local checks for store graphics, so a bad file fails before it is uploaded.

The limits follow the Play Console graphic asset requirements. Play still has
the final say; these checks only catch the common mistakes early.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

MB = 1024 * 1024

SCREENSHOT_TYPES = (
    "phoneScreenshots",
    "sevenInchScreenshots",
    "tenInchScreenshots",
    "tvScreenshots",
    "wearScreenshots",
)
SINGLE_TYPES = ("icon", "featureGraphic", "tvBanner")
IMAGE_TYPES = (*SINGLE_TYPES, *SCREENSHOT_TYPES)
MAX_SCREENSHOTS = 8


@dataclass(frozen=True)
class ImageInfo:
    format: str  # "png" or "jpeg"
    width: int
    height: int
    has_alpha: bool
    size_bytes: int

    @property
    def mime_type(self) -> str:
        return "image/png" if self.format == "png" else "image/jpeg"


def read_image_info(path: Path) -> ImageInfo:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        color_type = data[25]
        # Color types 4 and 6 carry an alpha channel; a tRNS chunk adds one too.
        has_alpha = color_type in (4, 6) or b"tRNS" in data[: data.find(b"IDAT")]
        return ImageInfo("png", width, height, has_alpha, len(data))
    if data.startswith(b"\xff\xd8"):
        width, height = _jpeg_size(data)
        return ImageInfo("jpeg", width, height, False, len(data))
    raise ValueError(f"{path.name}: not a PNG or JPEG file")


def _jpeg_size(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        # SOF0..SOF15 hold the frame size; C4, C8 and CC are other segments.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        i += 2 + length
    raise ValueError("JPEG has no frame header")


def check_image(image_type: str, info: ImageInfo) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings) for one file of the given Play image type."""
    errors: list[str] = []
    warnings: list[str] = []
    size = f"{info.width}x{info.height}"

    if image_type == "icon":
        if info.format != "png":
            errors.append("icon must be a PNG")
        if (info.width, info.height) != (512, 512):
            errors.append(f"icon must be 512x512, got {size}")
        if info.size_bytes > 1 * MB:
            errors.append("icon must be 1 MB or smaller")
        return errors, warnings

    exact = {"featureGraphic": (1024, 500), "tvBanner": (1280, 720)}.get(image_type)
    if exact:
        if (info.width, info.height) != exact:
            errors.append(f"{image_type} must be {exact[0]}x{exact[1]}, got {size}")
        if info.size_bytes > 15 * MB:
            errors.append(f"{image_type} must be 15 MB or smaller")
    elif image_type in SCREENSHOT_TYPES:
        short, long = sorted((info.width, info.height))
        if short < 320 or long > 3840:
            errors.append(f"screenshot sides must be 320-3840 px, got {size}")
        if long > 2 * short:
            errors.append(f"screenshot long side may be at most twice the short side, got {size}")
        if info.size_bytes > 8 * MB:
            errors.append("screenshot must be 8 MB or smaller")
    else:
        errors.append(f"unknown image type {image_type!r}; use one of {', '.join(IMAGE_TYPES)}")

    if info.has_alpha:
        warnings.append("has an alpha channel; Play asks for 24-bit PNG or JPEG without alpha")
    return errors, warnings
