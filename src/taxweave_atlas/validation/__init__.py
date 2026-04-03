"""Validation entrypoints (foundation: specs and config wiring only)."""

from taxweave_atlas.validation.specs import validate_specs_against_application_config

__all__ = ["validate_specs_against_application_config"]
