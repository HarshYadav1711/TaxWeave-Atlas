# TaxWeave Atlas

Offline toolkit for **synthetic US individual tax datasets**: typed cases, deterministic reconciliation, PDF bundles, and **delivery validation** suitable for review handoff. No paid document services and no network requirement at runtime.

## What you get

- **Generation**: `SyntheticTaxCase` JSON plus `questionnaire.json`, reconciled federal/state lines, supporting-document figures, and optional PDFs per dataset folder.
- **Validation**: Spec gate, per-batch **delivery checks** (duplicates, completeness, cross-form math, file/checksum integrity, PDF counts, stratification vs `config/generator/mix.yaml`), and machine-readable reports.
- **Orchestration**: One-shot **pilot** (default 35 datasets) and **weekly** (default 350) flows that generate then validate.

## Layout

| Path | Purpose |
|------|---------|
| `config/application.yaml` | Tax years, enabled states, complexity tier ids |
| `config/generator/*.yaml` | Mix weights, tier bounds, computation tables (synthetic) |
| `config/reconciliation/` | Scope, cross-checks, reconciliation rules |
| `specs/sample_pack/` | Sample case, PDF field mappings |
| `specs/templates/manifest.yaml` | PDF deliverable list and conditional `when` clauses |
| `src/taxweave_atlas/` | Schemas, engine, reconciliation, PDF render, **delivery** validation |
| `tests/` | Pytest: tier smoke tests and batch delivery tests |

## Setup

Python 3.11+ recommended.

```bash
python -m venv .venv
.\.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e .
pip install -e ".[dev]"      # ruff + pytest
```

## Commands

Global option **`-v` / `--verbose`** enables DEBUG logging on stderr.

### Spec validation

```bash
python -m taxweave_atlas validate-specs
```

### Generation

```bash
# Small ad-hoc batch (default count 10)
python -m taxweave_atlas pilot --output ./outputs/pilot --count 25 --seed 42

# Large batch (default count 2000)
python -m taxweave_atlas generate --output ./outputs/full --count 500 --seed 42
```

Useful flags:

- **`--no-pdfs`** — only `case.json` and `questionnaire.json`.
- **`--plan-only`** — write `manifests/batch_plan.json` only.
- **`--complexity easy|medium|moderately_complex`** — fix tier (otherwise mix from `mix.yaml`).
- **`--state CA|...`** / **`--tax-year YYYY`** — fix stratum.

### Orchestrated pilot / weekly

Runs generation, then **`validate-batch`** on the same tree. Exits with code **1** if delivery validation fails.

```bash
python -m taxweave_atlas produce pilot --output ./outputs/review_pilot
python -m taxweave_atlas produce weekly --output ./outputs/review_weekly
python -m taxweave_atlas produce weekly --output ./outputs/custom --count 320
```

Defaults: **pilot = 35** datasets (within 20–50), **weekly = 350** (within 300–400). Override with **`--count`**.

### Post-hoc delivery validation

```bash
python -m taxweave_atlas validate-batch ./outputs/pilot
```

- **`--no-pdfs`** — skip PDF presence and `00_dataset_files_manifest.json` checks (JSON-only trees).
- **`--strict-distribution`** — stratification drift vs `mix.yaml` becomes an **error** (default is warning for large |z|).
- **`--no-per-dataset-audit`** — do not write `01_delivery_audit.json` per folder.
- **`--no-batch-report`** — do not write `manifests/delivery_validation_report.json`.

### PDF-only rerender

```bash
python -m taxweave_atlas render-pdfs ./outputs/pilot
python -m taxweave_atlas render-pdfs ./outputs/pilot/datasets/dataset_00001
```

## Output structure

After **`pilot`**, **`generate`**, or **`produce`**:

```text
<output>/
  datasets/
    dataset_00001/
      case.json
      questionnaire.json
      00_dataset_files_manifest.json   # PDF SHA-256 + case hash (if PDFs enabled)
      01_delivery_audit.json           # after validate-batch / produce
      01_intake_questionnaire.pdf
      02_supporting_form_w2.pdf
      03_supporting_form_1099_int.pdf
      03b_supporting_form_1099_div.pdf   # only if dividends > 0
      04_federal_return_summary.pdf
      05_state_return_summary.pdf
      06_executive_summary.pdf
    dataset_00002/
      ...
  manifests/
    batch_plan.json                    # seeds, fingerprints, stratum metadata
    batch_summary.json
    delivery_validation_report.json    # aggregate delivery result (after validation)
```

**Fingerprints** in `batch_plan.json` identify synthetic identities for duplicate detection across and within batches.

## Delivery validation (what is checked)

| Check | Description |
|-------|-------------|
| Duplicates | No repeated `case_fingerprint` within the batch |
| Field completeness | Required dotted paths present and non-null on each case |
| Cross-form numeric | YAML cross-checks + supporting-doc alignment (`validate_reconciled_case`) |
| Per-folder integrity | `case.json` parses; `questionnaire.json` matches the case |
| PDF integrity | Expected filenames vs `specs/templates/manifest.yaml`; checksums vs bytes on disk |
| Document count | Manifest PDF count matches conditional set (e.g. 1099-DIV only with dividends) |
| Distribution | State, tax year, and complexity histograms vs `mix.yaml` (warning by default; **`--strict-distribution`** to fail) |

## Tests

```bash
ruff check src tests
pytest
```

## Dependencies

Runtime: **pydantic**, **PyYAML**, **click**, **reportlab** (PDF only). Dev: **ruff**, **pytest**.

## Reproducing one row

Use `master_seed`, dataset `index`, and `uniqueness_salt` from `manifests/batch_plan.json`:

```python
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.schema.ids import DatasetIdentity

case = build_synthetic_case(
    master_seed=42,
    identity=DatasetIdentity(index=0),
    salt=<uniqueness_salt>,
)
```
