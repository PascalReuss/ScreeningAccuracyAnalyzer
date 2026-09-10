"""Runtime configuration, sourced from environment variables only."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional convenience for local dev
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:  # pragma: no cover
    pass

DEFAULT_BASE_URL = "https://api.paulsjob.ai/dev/v1"


_TRUTHY = {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from None


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    request_timeout: float = 30.0
    max_retries: int = 4
    cache_dir: str = ".cache"
    cache_ttl_seconds: int = 900
    demo_mode: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        demo_mode = os.environ.get("SCREENING_DEMO", "").strip().lower() in _TRUTHY
        api_key = os.environ.get("PAULSJOB_API_KEY", "").strip()
        if not api_key and not demo_mode:
            raise RuntimeError(
                "PAULSJOB_API_KEY is not set. Copy .env.example to .env and fill it "
                "in, or set SCREENING_DEMO=1 to run against the bundled demo data."
            )
        return cls(
            api_key=api_key or "demo",
            base_url=os.environ.get("PAULSJOB_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            cache_ttl_seconds=_int_env("SCREENING_CACHE_TTL", 900),
            demo_mode=demo_mode,
        )
