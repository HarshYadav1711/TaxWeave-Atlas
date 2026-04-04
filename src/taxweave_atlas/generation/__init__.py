"""Synthetic case construction and batch runs."""

from taxweave_atlas.generation.batch_runner import GenerationBatchResult, run_case_generation_batch
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.generation.stratified_batch import (
    build_stratification_assignments,
    run_stratified_review_pilot_batch,
)

__all__ = [
    "GenerationBatchResult",
    "build_synthetic_case",
    "build_stratification_assignments",
    "run_case_generation_batch",
    "run_stratified_review_pilot_batch",
]
