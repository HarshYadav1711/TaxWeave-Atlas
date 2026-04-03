from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ConfigurationError, ValidationError
from taxweave_atlas.mapping import load_mappings, materialize_document, resolve_case_path
from taxweave_atlas.config import load_template_manifest, load_validation_rules


def _get_op(op: str):
    if op == "eq":
        return lambda a, b: a == b
    raise ValidationError(f"Unknown validation op: {op!r}")


def validate_case_rules(case_dict: dict[str, Any]) -> None:
    cfg = load_validation_rules()
    rules = cfg.get("rules")
    if not isinstance(rules, list):
        raise ValidationError("validation_rules.yaml: rules must be a list")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValidationError("invalid rule entry")
        rid = rule.get("id", "?")
        left_path = rule.get("left")
        right_path = rule.get("right")
        op = rule.get("op")
        if not isinstance(left_path, str) or not isinstance(right_path, str) or not isinstance(op, str):
            raise ValidationError(f"Rule {rid}: left/right/op must be strings")
        try:
            lv = resolve_case_path(case_dict, left_path)
            rv = resolve_case_path(case_dict, right_path)
        except Exception as e:
            raise ValidationError(f"Rule {rid}: path resolution failed: {e}") from e
        fn = _get_op(op)
        if not fn(lv, rv):
            raise ValidationError(f"Rule {rid} failed: {left_path}={lv!r} {op} {right_path}={rv!r}")


def validate_manifest_against_mappings() -> None:
    manifest = load_template_manifest()
    mappings = load_mappings()
    dels = manifest.get("deliverables")
    if not isinstance(dels, list):
        raise ConfigurationError("manifest deliverables must be a list")
    for d in dels:
        mk = d.get("mapping_document")
        if mk not in mappings:
            raise ConfigurationError(
                f"Deliverable {d.get('id')!r} mapping_document {mk!r} missing from mappings.yaml"
            )


def validate_case_mappings(case_dict: dict[str, Any]) -> None:
    manifest = load_template_manifest()
    for d in manifest["deliverables"]:
        mk = d["mapping_document"]
        materialize_document(mk, case_dict)
