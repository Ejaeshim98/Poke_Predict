from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    """
    Load environment variables from the local .env file.

    This keeps secrets out of code and out of git, while still making them
    available to the local app.
    """
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        # python-dotenv uses `dotenv_path` as the argument name.
        load_dotenv(dotenv_path=env_path, override=False)


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)

