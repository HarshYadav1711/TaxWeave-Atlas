from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from taxweave_atlas.config import (
    load_federal_computation,
    load_generator_config,
    load_state_computation,
    load_template_manifest,
)
from taxweave_atlas.exceptions import ValidationError
from taxweave_atlas.generator import build_tax_case, bundle_fingerprint
from taxweave_atlas.models.case import TaxCase
from taxweave_atlas.render.registry import render_deliverable
from taxweave_atlas.validate import validate_case_mappings, validate_case_rules, validate_manifest_against_mappings


@dataclass(frozen=True)
class BatchResult:
    output_dir: Path
    count: int
    seed: int
    fingerprints_path: Path


def _write_case_json(case_dir: Path, case: TaxCase) -> None:
    p = case_dir / "case.json"
    p.write_text(case.model_dump_json(indent=2), encoding="utf-8")


def generate_batch(
    *,
    count: int,
    seed: int,
    output: Path,
    write_case_json: bool = True,
    max_uniqueness_attempts: int = 500,
) -> BatchResult:
    if count < 1:
        raise ValidationError("count must be >= 1")
    output.mkdir(parents=True, exist_ok=True)

    validate_manifest_against_mappings()
    gen = load_generator_config()
    fed = load_federal_computation()
    st = load_state_computation()
    manifest = load_template_manifest()

    fingerprints: dict[str, int] = {}
    meta_lines: list[dict[str, Any]] = []

    for i in range(count):
        salt = 0
        case: TaxCase | None = None
        fp: str | None = None
        while salt < max_uniqueness_attempts:
            candidate = build_tax_case(
                index=i, seed=seed, gen=gen, fed=fed, st=st, salt=salt
            )
            d = candidate.model_dump(mode="json")
            fp = bundle_fingerprint(d)
            if fp not in fingerprints:
                fingerprints[fp] = i
                case = candidate
                break
            salt += 1
        if case is None or fp is None:
            raise ValidationError(
                f"Could not produce unique bundle for index {i} after {max_uniqueness_attempts} attempts"
            )

        case_dict = case.model_dump(mode="json")
        validate_case_mappings(case_dict)
        validate_case_rules(case_dict)

        case_dir = output / f"dataset_{i+1:05d}"
        case_dir.mkdir(parents=True, exist_ok=False)

        if write_case_json:
            _write_case_json(case_dir, case)

        for d in manifest["deliverables"]:
            rid = d["renderer"]
            md = d["mapping_document"]
            fname = d["filename"]
            pdf_bytes = render_deliverable(rid, md, case_dict)
            (case_dir / fname).write_bytes(pdf_bytes)

        meta_lines.append(
            {
                "index": i,
                "dataset_dir": case_dir.name,
                "fingerprint": fp,
                "uniqueness_salt": salt,
            }
        )

    manifest_path = output / "batch_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for row in meta_lines:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "count": count,
        "seed": seed,
        "fingerprints": len(fingerprints),
    }
    (output / "batch_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    return BatchResult(
        output_dir=output,
        count=count,
        seed=seed,
        fingerprints_path=manifest_path,
    )


def validate_reference_pack() -> None:
    """Load canonical sample + configs; fail loudly on drift."""
    validate_manifest_against_mappings()
    from taxweave_atlas.generator import load_sample_case

    case = load_sample_case()
    d = case.model_dump(mode="json")
    validate_case_mappings(d)
    validate_case_rules(d)
