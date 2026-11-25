"""Settings. Everything comes from environment variables, read once at startup."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_STORE_DIR = "~/squirrel"


@dataclass(frozen=True)
class Config:
    store_dir: Path
    cache_dir: Path
    model: str = DEFAULT_MODEL
    api_url: str = DEFAULT_API_URL
    api_key: str = field(default="", repr=False)
    effort: str = ""
    fallback: bool = True
    use_fzf: bool = True
    git_autocommit: bool = False

    @property
    def store_file(self) -> Path:
        return self.store_dir / "commands.jsonl"

    @property
    def state_file(self) -> Path:
        return self.cache_dir / "state.json"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> Config:
        env = os.environ if env is None else env
        cache_root = env.get("XDG_CACHE_HOME") or "~/.cache"
        return cls(
            store_dir=Path(os.path.expanduser(env.get("SQUIRREL_DIR") or DEFAULT_STORE_DIR)),
            cache_dir=Path(os.path.expanduser(cache_root)) / "squirrel",
            model=env.get("SQUIRREL_MODEL") or DEFAULT_MODEL,
            api_url=env.get("SQUIRREL_API_URL") or DEFAULT_API_URL,
            api_key=env.get("ANTHROPIC_API_KEY", ""),
            effort=env.get("SQUIRREL_EFFORT", ""),
            fallback=env.get("SQUIRREL_NO_FALLBACK") != "1",
            use_fzf=env.get("SQUIRREL_NO_FZF") != "1",
            git_autocommit=env.get("SQUIRREL_GIT_AUTOCOMMIT") == "1",
        )
