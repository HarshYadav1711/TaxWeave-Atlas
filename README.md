# TaxWeave Atlas

Offline generator for **synthetic U.S. individual tax datasets**: JSON cases, reconciled line summaries, optional PDFs, and **delivery validation**.

**Runtime dependencies** (declared in `pyproject.toml`): `pydantic`, `PyYAML`, `click`, `reportlab`. Everything else is stdlib.

---

## Architecture (overview)

| Layer | Role |
|-------|------|
| **config** | `application.yaml` + `config/generator/*.yaml` + `config/reconciliation/` — explicit weights, bounds, and rule packs (no hidden defaults beyond these files). |
| **schema** | **`SyntheticTaxCase`** (alias **`TaxCase`**) — single canonical object; every packaged artifact derives from it after reconciliation. |
| **generation** | `build_synthetic_case`: deterministic RNG per `(master_seed, dataset_index, uniqueness_salt)` → source fields → **reconciliation**. |
| **reconciliation** | `reconcile_case`: AGI, federal/state lines, executive summary, supporting-doc key amounts; YAML **cross-checks** at end. |
| **pdf** | ReportLab-backed bytes; field materialization from `specs/sample_pack/mappings.yaml`. |
| **structure** | `specs/dataset_structure_blueprint.yaml` + `specs/reference_pack_contract.yaml` — on-disk tree and workflow vs reference `dataset/` (structure only; all content synthetic). |
| **delivery** | `validate_batch_output`: dedup, completeness, numeric checks, **structure contract**, mix vs `mix.yaml`. |

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
              └─► [optional] blueprint tree + 00_dataset_files_manifest.json (v2, all file checksums)
```

Re-running with the same `master_seed`, row `index`, and `uniqueness_salt` from `manifests/batch_plan.json` reproduces the same case (see **Reproducibility** below).

---

## Repository layout

| Path | Purpose |
|------|---------|
| `config/` | Application profile, generator tables, reconciliation scope and checks |
| `specs/` | Sample case, mappings, manifests, **`dataset_structure_blueprint.yaml`**, **`reference_pack_contract.yaml`** (workflow / Prompt XML scope) |
| `dataset/` | Reference pack (optional checkout) — layout template only; generator does not read file contents |
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

## Output tree (reference-aligned)

Each `dataset_XXXXX/` mirrors the reference workflow: **Client Summary** → **Input Documents** (categories + summary docx) → **Complete form** (combined federal+state PDF + summary docx) → **Executive Summary** (docx + PDF) → **Prompt** (companion docx + MeF-shaped subset XML from the same case). Exact folder names and ordering come from `dataset_structure_blueprint.yaml`.

```text
<output>/datasets/dataset_00001/
  case.json
  questionnaire.json
  00_dataset_files_manifest.json   # v2: export_token, files_sha256 (all paths)
  01_delivery_audit.json           # after validate-batch / produce
  1. Client Summary-<token>/ ...
  2. Input Documents-<token>/ ...
  3. Complete form-<token>/ ...
  4. Executive Summary-<token>/ ...
  Prompt-<token>/ ...
<output>/manifests/
  batch_plan.json
  batch_summary.json
  delivery_validation_report.json
```

Prompt XML is a **synthetic subset** in the sample’s outer MeF style; schedules not modeled in `SyntheticTaxCase` are **not** fabricated — see `specs/reference_pack_contract.yaml`.

---

## Validation (transparency)

- **Spec gate**: `validate-specs` before trusting generator config changes.
- **Per case**: reconciliation cross-checks are defined in `config/reconciliation/` (not buried in code).
- **Per batch**: `validate-batch` reports duplicates, required fields, questionnaire match, **blueprint structure** (folders, files, manifest v2 checksums), and optional stratification drift vs `config/generator/mix.yaml`.

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
