from __future__ import annotations

from typing import Any

import yaml

from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import config_dir, generator_config_dir


def load_application_config() -> dict[str, Any]:
    path = config_dir() / "application.yaml"
    if not path.is_file():
        raise ConfigurationError(f"Missing application config: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError("application.yaml must parse to a mapping")
    return data


def load_tax_rule_placeholder(name: str) -> dict[str, Any]:
    path = config_dir() / "tax_rules" / f"{name}.yaml"
    if not path.is_file():
        raise ConfigurationError(f"Missing tax rule placeholder: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path.name} must parse to a mapping")
    return data


def load_generator_settings() -> dict[str, Any]:
    """
    Merge generator/*.yaml into one settings dict (keys must not collide, or later wins).
    """
    d = generator_config_dir()
    if not d.is_dir():
        raise ConfigurationError(f"Missing generator config directory: {d}")
    merged: dict[str, Any] = {}
    for path in sorted(d.glob("*.yaml")):
        part = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(part, dict):
            raise ConfigurationError(f"{path.name} must parse to a mapping")
        overlap = set(merged) & set(part)
        if overlap:
            raise ConfigurationError(f"Duplicate generator config keys in {path.name}: {sorted(overlap)}")
        merged.update(part)
    if not merged:
        raise ConfigurationError(f"No generator YAML files in {d}")
    return merged
