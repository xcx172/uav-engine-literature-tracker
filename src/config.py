"""Configuration loading.

Real credentials live only in the user's local ``.env``. Tests inject fake
values through environment variables and never read that file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "deepseek-flash"


@dataclass(frozen=True)
class Settings:
    openalex_key: str | None
    deepseek_key: str | None
    model: str
    db_path: Path
    timeout: float = 30.0

    @classmethod
    def load(cls, root: str | Path = ".", *, load_env_file: bool = True) -> "Settings":
        root_path = Path(root).resolve()
        if load_env_file:
            load_dotenv(root_path / ".env", interpolate=False, override=False)
        return cls(
            openalex_key=(os.getenv("OPENALEX_API_KEY") or "").strip() or None,
            deepseek_key=(os.getenv("DEEPSEEK_API_KEY") or "").strip() or None,
            model=(os.getenv("DEEPSEEK_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            db_path=root_path / "data" / "tracker.sqlite3",
        )

    def validate(self, online: bool) -> list[str]:
        if not online:
            return []
        missing: list[str] = []
        if not self.openalex_key:
            missing.append("OPENALEX_API_KEY")
        if not self.deepseek_key:
            missing.append("DEEPSEEK_API_KEY")
        return missing
