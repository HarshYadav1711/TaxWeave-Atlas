"""Synthetic case construction and batch runs."""

from taxweave_atlas.generation.batch_runner import GenerationBatchResult, run_case_generation_batch
from taxweave_atlas.generation.engine import build_synthetic_case

__all__ = [
    "GenerationBatchResult",
    "build_synthetic_case",
    "run_case_generation_batch",
]
