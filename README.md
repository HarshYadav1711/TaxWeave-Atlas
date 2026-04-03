# TaxWeave Atlas

Offline generator for **synthetic U.S. individual tax datasets**: JSON cases, reconciled line summaries, optional PDFs, and **delivery validation**.

**Runtime dependencies** (declared in `pyproject.toml`): `pydantic`, `PyYAML`, `click`, `reportlab`. Everything else is stdlib.

---

## Architecture (overview)

| Layer | Role |
|-------|------|
| **config** | `application.yaml` + `config/generator/*.yaml` + `config/reconciliation/` — explicit weights, bounds, and rule packs (no hidden defaults beyond these files). |
| **schema** | Pydantic models for `SyntheticTaxCase` and nested slices (profile, income, federal, state, etc.). |
| **generation** | `build_synthetic_case`: deterministic RNG per `(master_seed, dataset_index, uniqueness_salt)` → source fields → **reconciliation**. |
| **reconciliation** | `reconcile_case`: AGI, federal/state lines, executive summary, supporting-doc key amounts; YAML **cross-checks** at end. |
| **pdf** | ReportLab tables from `specs/sample_pack/mappings.yaml` + `specs/templates/manifest.yaml`. |
| **delivery** | `validate_batch_output`: dedup, completeness, numeric checks, optional PDF checksums, mix vs `mix.yaml`. |

**Generation flow (text)**

```text
  master_seed + DatasetIdentity(index) + salt
              │
              ▼
      stream_seed → RNG
              │
              ▼
   sample state / year / tier / profile / income / deductions / credits
              │
              ▼
           reconcile_case  ──► cross_checks (YAML)
              │
              ├─► case.json + questionnaire.json
              └─► [optional] PDF bundle + 00_dataset_files_manifest.json
```

Re-running with the same `master_seed`, row `index`, and `uniqueness_salt` from `manifests/batch_plan.json` reproduces the same case (see **Reproducibility** below).

---

## Repository layout

| Path | Purpose |
|------|---------|
| `config/` | Application profile, generator tables, reconciliation scope and checks |
| `specs/` | Sample case, PDF mappings, template manifest |
| `src/taxweave_atlas/` | Library code |
| `tests/` | Pytest |

---

## Setup

```bash
python -m venv .venv && .\.venv\Scripts\activate   # Windows
pip install -e . && pip install -e ".[dev]"
```

---

## CLI (summary)

| Command | Purpose |
|---------|---------|
| `validate-specs` | Gate: sample pack vs `application.yaml` |
| `pilot` / `generate` | Write `datasets/*` + `manifests/batch_plan.json` |
| `produce pilot\|weekly` | Generate then `validate-batch` (defaults: 35 / 350 rows) |
| `validate-batch PATH` | Post-hoc delivery checks + audit JSON |
| `render-pdfs TARGET` | Rerender PDFs from existing `case.json` |

Global **`-v`**: DEBUG logging. Common flags: **`--no-pdfs`**, **`--plan-only`**, **`--complexity`**, **`--state`**, **`--tax-year`**.

```bash
python -m taxweave_atlas validate-specs
python -m taxweave_atlas produce pilot --output ./out/pilot
python -m taxweave_atlas validate-batch ./out/pilot --strict-distribution
pytest && ruff check src tests
```

---

## Output tree

```text
<output>/datasets/dataset_00001/
  case.json
  questionnaire.json
  00_dataset_files_manifest.json    # if PDFs enabled
  01_delivery_audit.json          # after validate-batch / produce
  01–06*.pdf
<output>/manifests/
  batch_plan.json
  batch_summary.json
  delivery_validation_report.json   # after validation
```

---

## Validation (transparency)

- **Spec gate**: `validate-specs` before trusting generator config changes.
- **Per case**: reconciliation cross-checks are defined in `config/reconciliation/` (not buried in code).
- **Per batch**: `validate-batch` reports duplicates, required fields, questionnaire match, PDF set + SHA-256, and optional stratification drift vs `config/generator/mix.yaml`.

---

## Reproducibility

```python
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.schema.ids import DatasetIdentity

case = build_synthetic_case(
    master_seed=42,
    identity=DatasetIdentity(index=0),
    salt=<uniqueness_salt from batch_plan.json>,
)
```

Synthetic data only — **not** filing advice.
