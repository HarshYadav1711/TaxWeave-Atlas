from __future__ import annotations

from typing import Any

import yaml

from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import templates_spec_dir


def load_template_manifest() -> dict[str, Any]:
    path = templates_spec_dir() / "manifest.yaml"
    if not path.is_file():
        raise ConfigurationError(f"Missing template manifest: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError("manifest.yaml must be a mapping")
    dels = data.get("deliverables")
    if not isinstance(dels, list):
        raise ConfigurationError("manifest.yaml missing deliverables list")
    return data


def filter_deliverables(deliverables: list[dict[str, Any]], case_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply `when` clauses from manifest (deterministic, no heuristics)."""
    out: list[dict[str, Any]] = []
    for d in deliverables:
        when = d.get("when")
        if when == "dividends_positive":
            try:
                divs = case_dict["income"]["dividends_ordinary"]
            except KeyError:
                raise ConfigurationError("case_dict missing income.dividends_ordinary for when filter")
            if int(divs) <= 0:
                continue
        elif when is not None:
            raise ConfigurationError(f"Unknown manifest when clause: {when!r}")
        out.append(d)
    return out
