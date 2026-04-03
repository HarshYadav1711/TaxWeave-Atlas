from __future__ import annotations

from typing import Any

import yaml

from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import sample_pack_dir


def load_pdf_mappings() -> dict[str, Any]:
    path = sample_pack_dir() / "mappings.yaml"
    if not path.is_file():
        raise ConfigurationError(f"Missing mappings.yaml: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "documents" not in data:
        raise ConfigurationError("mappings.yaml must contain documents:")
    return data["documents"]


def resolve_case_path(case_dict: dict[str, Any], dotted: str) -> Any:
    cur: Any = case_dict
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise ConfigurationError(f"Mapping path not found on case: {dotted!r} (at {part!r})")
        cur = cur[part]
    return cur


def materialize_mapping_document(
    document_key: str,
    case_dict: dict[str, Any],
    documents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    documents = documents or load_pdf_mappings()
    if document_key not in documents:
        raise ConfigurationError(f"No mapping document {document_key!r} in mappings.yaml")
    spec = documents[document_key]
    if not isinstance(spec, dict):
        raise ConfigurationError(f"Invalid mapping spec for {document_key!r}")
    out: dict[str, Any] = {}
    for label, path in spec.items():
        if not isinstance(path, str):
            raise ConfigurationError(f"mappings.{document_key}.{label} must be a string path")
        out[label] = resolve_case_path(case_dict, path)
    return out
