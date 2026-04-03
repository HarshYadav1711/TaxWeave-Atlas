from __future__ import annotations

from typing import Any


def resolve_dotted_path(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur


def get_optional_income_bucket(case_dict: dict[str, Any], path: str, default: int = 0) -> int:
    """Navigate income.* paths; return default if intermediate dicts or key missing."""
    parts = path.split(".")
    cur: Any = case_dict
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    if cur is None:
        return default
    if isinstance(cur, bool):
        return int(cur)
    return int(cur)
