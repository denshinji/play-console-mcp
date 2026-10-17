from __future__ import annotations

from pathlib import Path

from conftest import png_bytes

from play_console_mcp import images, listing_md
from play_console_mcp.config import Settings


def info_for(tmp_path: Path, width: int, height: int, color_type: int = 2) -> images.ImageInfo:
    path = tmp_path / "image.png"
    path.write_bytes(png_bytes(width, height, color_type))
    return images.read_image_info(path)


def test_reads_png_size_and_alpha(tmp_path):
    info = info_for(tmp_path, 1080, 1920, color_type=6)
    assert (info.format, info.width, info.height, info.has_alpha) == ("png", 1080, 1920, True)


def test_reads_jpeg_size(tmp_path):
    # SOI, an APP0 segment, then SOF0 with height 500 and width 1024.
    app0 = b"\xff\xe0\x00\x10" + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0\x00\x11\x08\x01\xf4\x04\x00\x03" + b"\x00" * 9
    path = tmp_path / "feature.jpg"
    path.write_bytes(b"\xff\xd8" + app0 + sof0 + b"\xff\xd9")
    info = images.read_image_info(path)
    assert (info.format, info.width, info.height) == ("jpeg", 1024, 500)


def test_icon_must_be_512_png(tmp_path):
    errors, _ = images.check_image("icon", info_for(tmp_path, 500, 500))
    assert errors == ["icon must be 512x512, got 500x500"]


def test_screenshot_ratio_and_alpha(tmp_path):
    errors, warnings = images.check_image("phoneScreenshots", info_for(tmp_path, 400, 900, 6))
    assert "at most twice" in errors[0]
    assert "alpha" in warnings[0]


def test_store_graphics_pass_checks(store_root):
    store = store_root / "docs/store/play"
    for image_type, path in [
        ("icon", store / "icon-512.png"),
        ("featureGraphic", store / "feature-graphic-1024x500.png"),
        *[("phoneScreenshots", p) for p in sorted((store / "screenshots").glob("*.png"))],
    ]:
        errors, _ = images.check_image(image_type, images.read_image_info(path))
        assert errors == [], (path.name, errors)


def test_parses_listing_file(store_root):
    path = store_root / "docs/store/play/listing-id.md"
    fields = listing_md.parse_listing(path.read_text(encoding="utf-8"))
    assert listing_md.language_of(path) == "id"
    assert fields["title"] == "Contoh"
    assert fields["shortDescription"].startswith("Catat skincare")
    assert fields["fullDescription"].startswith("Contoh membantu")
    assert fields["fullDescription"].endswith("bukan saran medis.")
    assert "• Atur rutinitas" in fields["fullDescription"]
    assert listing_md.length_errors(fields) == []


def test_parse_ignores_unknown_sections_and_counts():
    text = "# Title\n\n## App name (3/30)\nAbc\n\n## Notes\nignored\n\n## Short description\nShort\n"
    assert listing_md.parse_listing(text) == {"title": "Abc", "shortDescription": "Short"}


def test_length_errors():
    assert listing_md.length_errors({"title": "x" * 31}) == [
        "title is 31 characters; the limit is 30"
    ]


def test_settings_from_env(tmp_path):
    settings = Settings.from_env(
        {
            "PLAY_SERVICE_ACCOUNT_JSON": "~/key.json",
            "PLAY_PACKAGE_NAMES": "com.example.app, com.example.app.dev",
            "PLAY_ASSET_ROOT": str(tmp_path),
            "PLAY_ALLOW_PRODUCTION": "true",
        }
    )
    assert settings.credentials_path == Path("~/key.json").expanduser()
    assert settings.package_names == ("com.example.app", "com.example.app.dev")
    assert settings.asset_root == tmp_path.resolve()
    assert settings.allow_production is True
    assert Settings.from_env({}).allow_production is False
