"""Tiny on-disk JSON cache so a dev run doesn't re-page the API every request."""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
from typing import Any


def _path(cache_dir: str, key: str) -> pathlib.Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return pathlib.Path(cache_dir) / f"{digest}.json"


def read(cache_dir: str, key: str, ttl_seconds: int) -> Any | None:
    path = _path(cache_dir, key)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > ttl_seconds:
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write(cache_dir: str, key: str, value: Any) -> None:
    path = _path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), "utf-8")
