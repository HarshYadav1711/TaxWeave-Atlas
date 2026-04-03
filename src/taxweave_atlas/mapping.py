from __future__ import annotations

from typing import Any

import yaml

from taxweave_atlas.exceptions import ConfigurationError, MappingResolutionError
from taxweave_atlas.paths import reference_pack_dir


def load_mappings() -> dict[str, Any]:
    path = reference_pack_dir() / "mappings.yaml"
    if not path.is_file():
        raise ConfigurationError(f"Missing mappings file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") is None:
        raise ConfigurationError("mappings.yaml must be a mapping with version")
    docs = data.get("documents")
    if not isinstance(docs, dict):
        raise ConfigurationError("mappings.yaml missing documents:")
    return docs


def resolve_case_path(case_dict: dict[str, Any], dotted: str) -> Any:
    cur: Any = case_dict
    parts = dotted.split(".")
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            raise MappingResolutionError(f"Path not found on case: {dotted} (failed at {p!r})")
        cur = cur[p]
    return cur


def materialize_document(
    document_key: str,
    case_dict: dict[str, Any],
    mappings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mappings = mappings or load_mappings()
    if document_key not in mappings:
        raise ConfigurationError(f"No mapping document {document_key!r} in mappings.yaml")
    spec = mappings[document_key]
    if not isinstance(spec, dict):
        raise ConfigurationError(f"Invalid mapping spec for {document_key!r}")
    out: dict[str, Any] = {}
    for label, path in spec.items():
        if not isinstance(path, str):
            raise ConfigurationError(f"Mapping {document_key}.{label} must be a string path")
        out[label] = resolve_case_path(case_dict, path)
    return out
