from __future__ import annotations

from pathlib import Path

from taxweave_atlas.config_loader import load_application_config
from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.orchestration.manifest import BatchPlan, DatasetPlan
from taxweave_atlas.schema.ids import DatasetIdentity, stream_seed


def build_batch_plan(*, master_seed: int, count: int, complexity_level: str | None) -> BatchPlan:
    app = load_application_config()
    default_year = app.get("tax_years", {}).get("default")
    if not isinstance(default_year, int):
        raise ConfigurationError("application.yaml must define tax_years.default as an int")

    if complexity_level is None:
        raw = app.get("default_complexity")
        if raw is None:
            raise ConfigurationError("application.yaml must define default_complexity")
        complexity_level = str(raw)

    datasets: list[DatasetPlan] = []
    for i in range(count):
        ident = DatasetIdentity(index=i)
        datasets.append(
            DatasetPlan(
                index=i,
                slug=ident.slug,
                stream_seed=stream_seed(master_seed, ident),
            )
        )

    return BatchPlan(
        master_seed=master_seed,
        count=count,
        complexity_level=complexity_level,
        default_tax_year=default_year,
        datasets=datasets,
    )


def write_foundation_batch_plan(
    output: Path,
    *,
    master_seed: int,
    count: int,
    complexity_level: str | None = None,
) -> Path:
    """
    Create output/manifests/ and write batch_plan.json with deterministic dataset ids
    and per-dataset stream seeds. Does not synthesize cases or PDFs.
    """
    plan = build_batch_plan(master_seed=master_seed, count=count, complexity_level=complexity_level)
    output.mkdir(parents=True, exist_ok=True)
    manifests = output / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    path = manifests / "batch_plan.json"
    path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path
