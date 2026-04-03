"""Dataset folder layout from ``specs/dataset_structure_blueprint.yaml`` (sample-aligned)."""

from taxweave_atlas.structure.layout import write_dataset_structure_bundle
from taxweave_atlas.structure.validate import validate_dataset_structure

__all__ = ["write_dataset_structure_bundle", "validate_dataset_structure"]
