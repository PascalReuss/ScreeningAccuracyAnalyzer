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


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    request_timeout: float = 30.0
    max_retries: int = 4
    cache_dir: str = ".cache"
    cache_ttl_seconds: int = 900

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.environ.get("PAULSJOB_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "PAULSJOB_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        return cls(
            api_key=api_key,
            base_url=os.environ.get("PAULSJOB_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            cache_ttl_seconds=int(os.environ.get("SCREENING_CACHE_TTL", "900")),
        )
