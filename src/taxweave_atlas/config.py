from __future__ import annotations

from typing import Any

import yaml

from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import reference_pack_dir


def _load_yaml(name: str) -> dict[str, Any]:
    path = reference_pack_dir() / name
    if not path.is_file():
        raise ConfigurationError(f"Missing required config: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError(f"{name} must parse to a mapping")
    return data


def load_generator_config() -> dict[str, Any]:
    return _load_yaml("generator_config.yaml")


def load_federal_computation() -> dict[str, Any]:
    return _load_yaml("federal_computation.yaml")


def load_state_computation() -> dict[str, Any]:
    return _load_yaml("state_computation.yaml")


def load_validation_rules() -> dict[str, Any]:
    return _load_yaml("validation_rules.yaml")


def load_template_manifest() -> dict[str, Any]:
    from taxweave_atlas.paths import templates_dir

    path = templates_dir() / "manifest.yaml"
    if not path.is_file():
        raise ConfigurationError(f"Missing template manifest: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError("manifest.yaml must be a mapping")
    return data
