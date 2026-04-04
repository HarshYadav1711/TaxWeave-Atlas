"""
Run a generation batch: each row is a reconciled ``SyntheticTaxCase`` written under
``_staging/datasets/`` (full blueprint) and, unless disabled, PDF-only ``datasets/`` plus
``manifests/batch_plan.json`` / ``batch_summary.json``.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from taxweave_atlas.config_loader import load_application_config
from taxweave_atlas.exceptions import ConfigurationError, TaxWeaveError, ValidationError
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.generation.uniqueness import case_fingerprint
from taxweave_atlas.orchestration.manifest import BatchPlan, DatasetPlan
from taxweave_atlas.paths import staging_datasets_root
from taxweave_atlas.schema.ids import DatasetIdentity, stream_seed

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GenerationBatchResult:
    output_dir: Path
    batch_plan_path: Path
    count: int


def run_case_generation_batch(
    output: Path,
    *,
    master_seed: int,
    count: int,
    complexity_override: str | None = None,
    state_override: str | None = None,
    tax_year_override: int | None = None,
    max_uniqueness_attempts: int = 750,
    write_pdfs: bool = True,
) -> GenerationBatchResult:
    """Build ``count`` unique cases; optional PDF export; never overwrite existing folders."""
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

    complexity_label = complexity_override or str(app.get("default_complexity", "mixed"))

    log.info(
        "starting batch: count=%d master_seed=%s write_pdfs=%s",
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

        salt = 0
        case = None
        fp = None
        while salt < max_uniqueness_attempts:
            candidate = build_synthetic_case(
                master_seed=master_seed,
                identity=ident,
                salt=salt,
                state_override=state_override,
                tax_year_override=tax_year_override,
                complexity_override=complexity_override,
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
            case.questionnaire.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

        if write_pdfs:
            export_dir.mkdir(parents=True, exist_ok=False)
            from taxweave_atlas.pdf.pipeline import render_dataset_deliverable_trees

            try:
                render_dataset_deliverable_trees(
                    case,
                    staging_dir,
                    export_dir,
                    reconcile_first=False,
                    dataset_index=ident.index,
                    uniqueness_salt=salt,
                )
            except TaxWeaveError:
                shutil.rmtree(export_dir, ignore_errors=True)
                raise
            except Exception:
                shutil.rmtree(export_dir, ignore_errors=True)
                raise

        interval = 50 if count >= 200 else (20 if count >= 50 else 5)
        if (i + 1) == 1 or (i + 1) == count or (i + 1) % interval == 0:
            log.info("progress: %d/%d (%s)", i + 1, count, ident.slug)

        cx = case.questionnaire.answers.extensions.get("complexity_tier", complexity_label)
        dataset_plans.append(
            DatasetPlan(
                index=i,
                slug=ident.slug,
                stream_seed=stream_seed(master_seed, ident, salt=salt),
                tax_year=case.tax_year,
                state_code=case.state.code,
                complexity_tier=str(cx),
                uniqueness_salt=salt,
                case_fingerprint=fp,
            )
        )

    plan = BatchPlan(
        stage="synthetic_generation_v1",
        master_seed=master_seed,
        count=count,
        complexity_level=complexity_label,
        default_tax_year=default_year,
        note=(
            "Synthetic taxpayer generation; internal tree under _staging/datasets/ (full blueprint); "
            "deliverable PDFs + manifest.json under datasets/ (see specs/dataset_structure_blueprint.yaml)."
        ),
        datasets=dataset_plans,
    )
    plan_path = manifests / "batch_plan.json"
    plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    summary = {
        "count": count,
        "master_seed": master_seed,
        "unique_fingerprints": len(seen_fp),
        "complexity_override": complexity_override,
        "state_override": state_override,
        "tax_year_override": tax_year_override,
    }
    (manifests / "batch_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    log.info("finished batch: %d datasets (staging %s, export %s)", count, staging_root, datasets_root)
    return GenerationBatchResult(output_dir=output, batch_plan_path=plan_path, count=count)
