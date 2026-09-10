"""Tiny on-disk JSON cache so a dev run doesn't re-page the API every request."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import time
from typing import Any

logger = logging.getLogger(__name__)


def _path(cache_dir: str, key: str) -> pathlib.Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return pathlib.Path(cache_dir) / f"{digest}.json"


def read(cache_dir: str, key: str, ttl_seconds: int) -> Any | None:
    path = _path(cache_dir, key)
    try:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > ttl_seconds:
            return None
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("ignoring unreadable cache entry %s: %s", path.name, exc)
        return None


def write(cache_dir: str, key: str, value: Any) -> None:
    """Best-effort write. The cache is an optimization, so a failure here is
    logged and swallowed rather than propagated to the caller."""
    path = _path(cache_dir, key)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(value), "utf-8")
        tmp.replace(path)  # atomic on the same filesystem
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("could not write cache entry %s: %s", path.name, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
