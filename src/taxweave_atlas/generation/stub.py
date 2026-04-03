from __future__ import annotations

from taxweave_atlas.exceptions import NotImplementedStageError


def assert_generation_not_implemented() -> None:
    raise NotImplementedStageError(
        "Synthetic case generation is not implemented in the foundation stage."
    )
