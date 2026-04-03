from __future__ import annotations

from taxweave_atlas.exceptions import NotImplementedStageError


def assert_reconciliation_not_implemented() -> None:
    raise NotImplementedStageError(
        "Tax reconciliation is not implemented — populate config/tax_rules/ and wire engines first."
    )
