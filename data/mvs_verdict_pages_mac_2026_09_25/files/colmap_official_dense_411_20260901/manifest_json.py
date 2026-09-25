from __future__ import annotations

import json
from pathlib import Path


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dump_json(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=_json_default)
