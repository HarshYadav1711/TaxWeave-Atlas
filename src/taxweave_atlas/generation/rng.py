from __future__ import annotations

import random
from typing import Any


def weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    if not weights:
        raise ValueError("empty weights")
    items = [(k, float(v)) for k, v in weights.items() if float(v) > 0]
    if not items:
        raise ValueError("no positive weights")
    total = sum(w for _, w in items)
    r = rng.random() * total
    acc = 0.0
    for k, w in items:
        acc += w
        if r <= acc:
            return k
    return items[-1][0]


def randint_range(rng: random.Random, spec: dict[str, Any]) -> int:
    return rng.randint(int(spec["min"]), int(spec["max"]))
