"""Runtime settings, read from the environment once at startup."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS = Path("~/.config/play-console-mcp/service-account.json")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    credentials_path: Path
    # Packages the server may touch; the first one is the default. While it is
    # empty (PLAY_PACKAGE_NAMES unset) every API tool refuses to run.
    package_names: tuple[str, ...]
    # Uploads (graphics, bundles) must resolve to a file under this directory.
    asset_root: Path
    allow_production: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        credentials = env.get("PLAY_SERVICE_ACCOUNT_JSON") or str(DEFAULT_CREDENTIALS)
        packages = tuple(
            name.strip()
            for name in env.get("PLAY_PACKAGE_NAMES", "").split(",")
            if name.strip()
        )
        root = env.get("PLAY_ASSET_ROOT") or os.getcwd()
        return cls(
            credentials_path=Path(credentials).expanduser(),
            package_names=packages,
            asset_root=Path(root).expanduser().resolve(),
            allow_production=_truthy(env.get("PLAY_ALLOW_PRODUCTION")),
        )
