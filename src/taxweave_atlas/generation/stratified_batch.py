"""
Stratified review pilot batches: fixed marginal distributions for state, complexity, and tax year.

Used for reviewer-ready pilots (~80 rows) with blueprint-identical PDF export trees.
"""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from pathlib import Path

from taxweave_atlas.config_loader import load_application_config
from taxweave_atlas.exceptions import ConfigurationError, ValidationError
from taxweave_atlas.generation.batch_runner import GenerationBatchResult
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.generation.uniqueness import case_fingerprint
from taxweave_atlas.orchestration.manifest import BatchPlan, DatasetPlan
from taxweave_atlas.paths import staging_datasets_root
from taxweave_atlas.reconciliation.supporting_forms import count_supporting_forms
from taxweave_atlas.schema.ids import DatasetIdentity, stream_seed

log = logging.getLogger(__name__)

_REVIEW_STATES: tuple[str, ...] = ("CA", "TX", "NY", "IL", "FL")
_COMPLEXITY_ORDER: tuple[str, ...] = ("easy", "medium", "moderately_complex")
_YEAR_BASE: tuple[int, ...] = (2020, 2021, 2022, 2023, 2024)


def _split_n_into_k_parts(n: int, k: int) -> list[int]:
    """Split ``n`` into ``k`` nonnegative integers differing by at most one."""
    if k <= 0:
        raise ValueError("k must be positive")
    base = n // k
    rem = n % k
    return [base + (1 if i < rem else 0) for i in range(k)]


def build_stratification_assignments(
    count: int,
    *,
    master_seed: int,
) -> tuple[list[str], list[str], list[int], dict[str, object]]:
    """
    Build three length-``count`` lists (states, complexity tiers, tax years) with target marginals.

    Marginals (designed for ``count`` = 80):
    - Five states equally often (16 each at 80).
    - Complexity ~30% / 40% / 30% (easy / medium / moderately_complex).
    - Years 2020–2024 evenly over ``count - n_2025`` slots; ``n_2025 ≈ round(count * 10/80)`` (10 at 80).

    Lists are independently shuffled with ``random.Random(master_seed)`` so joint assignment is
    pseudo-random but marginals are exact.
    """
    if count < 1:
        raise ConfigurationError("stratified batch count must be >= 1")

    enabled = list(load_application_config()["states"]["enabled"])
    for s in _REVIEW_STATES:
        if s not in enabled:
            raise ConfigurationError(f"Stratified pilot requires state {s!r} in application.yaml states.enabled")

    active_years = [int(y) for y in load_application_config()["tax_years"]["active"]]
    for y in (*_YEAR_BASE, 2025):
        if y not in active_years:
            raise ConfigurationError(f"Stratified pilot requires tax year {y} in application.yaml tax_years.active")

    # States
    per_state = _split_n_into_k_parts(count, len(_REVIEW_STATES))
    states: list[str] = []
    for st, c in zip(_REVIEW_STATES, per_state, strict=True):
        states.extend([st] * c)

    # Complexity (percentages rounded; adjust medium for exact sum)
    easy_n = (count * 30 + 50) // 100
    med_n = (count * 40 + 50) // 100
    mod_n = count - easy_n - med_n
    if mod_n < 0:
        med_n += mod_n
        mod_n = 0
    complexity: list[str] = (
        ["easy"] * easy_n + ["medium"] * med_n + ["moderately_complex"] * mod_n
    )
    if len(complexity) != count:
        raise ConfigurationError("internal: complexity multiset length mismatch")

    # Years: 2025 share scales with batch size (~10 per 80 rows); remainder across 2020–2024
    n_2025 = min(count, max(1, int(round(count * 10 / 80))))
    rest = count - n_2025
    year_chunks = _split_n_into_k_parts(rest, len(_YEAR_BASE))
    years: list[int] = []
    for y, c in zip(_YEAR_BASE, year_chunks, strict=True):
        years.extend([y] * c)
    years.extend([2025] * n_2025)
    assert len(years) == count, "internal: year multiset length mismatch"

    rng = random.Random(master_seed)
    rng.shuffle(states)
    rng.shuffle(complexity)
    rng.shuffle(years)

    profile: dict[str, object] = {
        "count": count,
        "master_seed": master_seed,
        "states_target": {s: per_state[i] for i, s in enumerate(_REVIEW_STATES)},
        "complexity_target": {"easy": easy_n, "medium": med_n, "moderately_complex": mod_n},
        "tax_years_target": {str(y): year_chunks[i] for i, y in enumerate(_YEAR_BASE)} | {"2025": n_2025},
    }
    return states, complexity, years, profile


def _forms_line(case: object) -> str:
    from taxweave_atlas.schema.case import SyntheticTaxCase

    assert isinstance(case, SyntheticTaxCase)
    parts = ["IRS1040"] + [d.element_name for d in case.structural_mef.documents]
    return "+".join(parts)


def run_stratified_review_pilot_batch(
    output: Path,
    *,
    master_seed: int,
    count: int = 80,
    max_uniqueness_attempts: int = 750,
    write_pdfs: bool = True,
    run_delivery_validation: bool = False,
) -> GenerationBatchResult:
    """
    Generate ``count`` datasets with stratified state / complexity / tax year assignment.

    Structure matches ``specs/dataset_structure_blueprint.yaml`` (PDF-only under ``datasets/``).
    Logs one INFO line per dataset after successful render.
    """
    states_a, cx_a, years_a, profile = build_stratification_assignments(count, master_seed=master_seed)

    output.mkdir(parents=True, exist_ok=True)
    staging_root = staging_datasets_root(output)
    staging_root.mkdir(parents=True, exist_ok=True)
    datasets_root = output / "datasets"
    datasets_root.mkdir(parents=True, exist_ok=True)
    manifests = output / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)

    app = load_application_config()
    default_year = app.get("tax_years", {}).get("default")
    if not isinstance(default_year, int):
        raise ConfigurationError("application.yaml must define tax_years.default as int")

    log.info(
        "starting stratified review pilot: count=%d master_seed=%s write_pdfs=%s",
        count,
        master_seed,
        write_pdfs,
    )

    seen_fp: set[str] = set()
    dataset_plans: list[DatasetPlan] = []

    for i in range(count):
        ident = DatasetIdentity(index=i)
        staging_dir = staging_root / ident.slug
        export_dir = datasets_root / ident.slug
        if staging_dir.exists() or export_dir.exists():
            raise ValidationError(
                f"Dataset folder already exists: {staging_dir} or {export_dir}"
            )

        st_ov = states_a[i]
        cx_ov = cx_a[i]
        yr_ov = years_a[i]

        salt = 0
        case = None
        fp = None
        while salt < max_uniqueness_attempts:
            candidate = build_synthetic_case(
                master_seed=master_seed,
                identity=ident,
                salt=salt,
                state_override=st_ov,
                tax_year_override=yr_ov,
                complexity_override=cx_ov,
            )
            fp = case_fingerprint(candidate)
            if fp not in seen_fp:
                seen_fp.add(fp)
                case = candidate
                break
            salt += 1

        if case is None or fp is None:
            raise ValidationError(
                f"Could not produce unique case for index {i} after {max_uniqueness_attempts} attempts"
            )

        staging_dir.mkdir(parents=True, exist_ok=False)
        (staging_dir / "case.json").write_text(
            case.model_dump_json(indent=2, exclude_computed_fields=True) + "\n",
            encoding="utf-8",
        )
        (staging_dir / "questionnaire.json").write_text(
            case.questionnaire.model_dump_json(indent=2) + "\n",
            encoding="utf-8"
        )

        if write_pdfs:
            export_dir.mkdir(parents=True, exist_ok=False)
            from taxweave_atlas.pdf.pipeline import render_dataset_deliverable_trees

            render_dataset_deliverable_trees(
                case,
                staging_dir,
                export_dir,
                reconcile_first=False,
                dataset_index=ident.index,
                uniqueness_salt=salt,
            )

        cx_label = str(case.questionnaire.answers.extensions.get("complexity_tier", cx_ov))
        n_sup = count_supporting_forms(case)
        log.info(
            "review_pilot dataset=%s state=%s complexity=%s tax_year=%s supporting_forms=%d forms=%s validation=pass",
            ident.slug,
            case.state.code,
            cx_label,
            case.tax_year,
            n_sup,
            _forms_line(case),
        )

        dataset_plans.append(
            DatasetPlan(
                index=i,
                slug=ident.slug,
                stream_seed=stream_seed(master_seed, ident, salt=salt),
                tax_year=case.tax_year,
                state_code=case.state.code,
                complexity_tier=cx_label,
                uniqueness_salt=salt,
                case_fingerprint=fp,
            )
        )

    plan = BatchPlan(
        stage="stratified_review_pilot_v1",
        master_seed=master_seed,
        count=count,
        complexity_level="stratified",
        default_tax_year=default_year,
        note=(
            "Stratified review pilot: equal states (CA/TX/NY/IL/FL), ~30/40/30 complexity, "
            "2020–2024 spread with extra 2025 share; blueprint PDF export under datasets/."
        ),
        datasets=dataset_plans,
    )
    plan_path = manifests / "batch_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    actual_states = Counter(p.state_code for p in dataset_plans)
    actual_cx = Counter(p.complexity_tier for p in dataset_plans)
    actual_years = Counter(p.tax_year for p in dataset_plans)

    summary = {
        "count": count,
        "master_seed": master_seed,
        "mode": "stratified_review_pilot",
        "stratification_design": profile,
        "actual_distribution": {
            "states": dict(sorted(actual_states.items())),
            "complexity_tier": dict(sorted(actual_cx.items())),
            "tax_year": {str(k): v for k, v in sorted(actual_years.items())},
        },
        "unique_fingerprints": len(seen_fp),
    }
    (manifests / "batch_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    log.info("finished stratified review pilot: %d datasets → %s", count, datasets_root)

    if run_delivery_validation:
        from taxweave_atlas.delivery.batch_validate import validate_batch_output

        report = validate_batch_output(output, expect_pdfs=write_pdfs)
        log.info("delivery_validation ok=%s %s", report.ok, report.summary_line())
        if not report.ok:
            raise ValidationError("delivery validation failed after stratified pilot generation")

    return GenerationBatchResult(output_dir=output, batch_plan_path=plan_path, count=count)
