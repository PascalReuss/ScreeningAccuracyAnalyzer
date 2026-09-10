"""Loader for the bundled demo dataset (see ``demo/generate.py``).

Used when ``Config.demo_mode`` is on (env ``SCREENING_DEMO=1``) so the UI and the
analysis layer can be exercised without a Paulsjob API key.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

_DEMO_DIR = pathlib.Path(__file__).resolve().parent.parent / "demo"


class DemoDataMissing(RuntimeError):
    pass


def _read(name: str) -> Any:
    path = _DEMO_DIR / name
    if not path.exists():
        raise DemoDataMissing(
            f"{path} not found. Run `python demo/generate.py` to create it."
        )
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise DemoDataMissing(
            f"{path} could not be read ({exc}). "
            f"Re-create it with `python demo/generate.py`."
        ) from exc


def load_applications() -> list[dict[str, Any]]:
    """ApplicationSearchListData[] - same shape as the live search endpoint."""
    return _read("applications.json")


def load_assessments() -> dict[str, list[dict[str, Any]]]:
    """{person_slug: Assessment[]}."""
    return _read("assessments.json")
