from __future__ import annotations

from typing import Any

import yaml

from taxweave_atlas.config_loader import load_generator_settings
from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import project_root


def load_reconciliation_bundle() -> dict[str, Any]:
    """Load scope, credits, cross_checks, and attach generator computation tables."""
    base = project_root() / "config" / "reconciliation"
    if not base.is_dir():
        raise ConfigurationError(f"Missing reconciliation config directory: {base}")

    def _load(name: str) -> dict[str, Any]:
        path = base / name
        if not path.is_file():
            raise ConfigurationError(f"Missing reconciliation file: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfigurationError(f"{name} must parse to a mapping")
        return data

    scope = _load("scope.yaml")
    credits = _load("credits.yaml")
    checks = _load("cross_checks.yaml")
    structural_mef = _load("structural_mef.yaml")
    gen = load_generator_settings()
    computation = gen.get("computation")
    if not isinstance(computation, dict):
        raise ConfigurationError("generator settings missing computation block")

    return {
        "scope": scope.get("scope") or {},
        "credit_application": credits.get("credit_application") or {},
        "cross_checks": checks.get("rules") or [],
        "cross_check_tolerance": checks.get("tolerance") or {"default_abs": 0},
        "structural_mef": structural_mef,
        "computation": computation,
    }
