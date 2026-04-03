from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatasetIdentity:
    """Stable identity for one synthetic bundle within a batch."""

    index: int
    """0-based index in the batch run."""

    @property
    def dataset_id(self) -> int:
        """Monotonic id (equals index)."""
        return self.index

    @property
    def slug(self) -> str:
        """Filesystem-safe folder name (1-based, zero-padded)."""
        return f"dataset_{self.index + 1:05d}"


def stream_seed(master_seed: int, identity: DatasetIdentity, *, salt: int = 0) -> int:
    """
    Deterministic 64-bit seed for an isolated RNG stream per dataset.
    `salt` supports de-duplication passes without changing `master_seed`.
    """
    payload = f"{master_seed}:{identity.index}:{salt}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)
