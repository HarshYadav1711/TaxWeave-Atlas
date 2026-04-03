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
| **reconciliation** | `reconcile_case`: AGI, federal/state lines, executive summary, supporting-doc key amounts; YAML **cross-checks** (tolerance in `config/reconciliation/cross_checks.yaml`) with **document-labeled** mismatch messages; Schedule C vs SE net; supporting PDFs vs 1040 / Schedule B mirrors. |
| **pdf** | ReportLab-backed bytes; field materialization from `specs/sample_pack/mappings.yaml`. |
| **structure** | `specs/dataset_structure_blueprint.yaml` + `specs/reference_pack_contract.yaml` — on-disk tree and workflow vs reference `dataset/` (structure only; all content synthetic). |
| **delivery** | `validate_batch_output`: dedup, completeness, **staging + PDF-only export** contracts, mix vs `mix.yaml`. |

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
              ├─► _staging/datasets/…: case.json, questionnaire, full tree + 00_dataset_files_manifest.json (v2)
              └─► datasets/…: PDFs only + manifest.json (deliverable)
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
| `pilot` / `generate` | Write `_staging/datasets/*` (internal) + PDF-only `datasets/*` + `manifests/batch_plan.json` |
| `produce pilot\|weekly` | Generate then `validate-batch` (defaults: 35 / 350 rows) |
| `validate-batch PATH` | Post-hoc delivery checks + audit JSON |
| `render-pdfs TARGET` | Rerender from `_staging/datasets/.../case.json` or batch root |

Global **`-v`**: DEBUG logging. Common flags: **`--no-pdfs`**, **`--plan-only`**, **`--complexity`**, **`--state`**, **`--tax-year`**.

```bash
python -m taxweave_atlas validate-specs
python -m taxweave_atlas produce pilot --output ./out/pilot
python -m taxweave_atlas validate-batch ./out/pilot --strict-distribution
pytest && ruff check src tests
```

---

## Output tree (reference-aligned)

**Deliverable** (`datasets/dataset_XXXXX/`): same segment **folder names** as the reference workflow, but **only `.pdf` files** plus root **`manifest.json`** (checksums for those PDFs). No JSON, DOCX, XLSX, or XML in the handoff tree.

**Internal build** (`_staging/datasets/dataset_XXXXX/`): `case.json`, `questionnaire.json`, full blueprint including DOCX/XLSX, **Prompt** segment (companion docx + MeF-shaped subset XML), and `00_dataset_files_manifest.json` (v2, all paths). Used for regeneration, debugging, and validation against the reconciled case.

```text
<output>/_staging/datasets/dataset_00001/
  case.json
  questionnaire.json
  00_dataset_files_manifest.json
  1. Client Summary-<token>/   # .docx + .pdf (internal)
  2. Input Documents-<token>/  # .docx, .xlsx, supporting .pdf, …
  3. Complete form-<token>/ ...
  4. Executive Summary-<token>/ ...
  Prompt-<token>/              # .docx + .xml (not exported)

<output>/datasets/dataset_00001/
  manifest.json
  1. Client Summary-<token>/…/*.pdf
  2. Input Documents-<token>/…/*.pdf
  3. Complete form-<token>/…/*.pdf
  4. Executive Summary-<token>/…/*.pdf

<output>/manifests/
  batch_plan.json
  batch_summary.json
  delivery_validation_report.json
  delivery_audits/dataset_00001.json   # after validate-batch / produce
```

Prompt XML is a **synthetic subset** in the sample’s outer MeF style; schedules not modeled in `SyntheticTaxCase` are **not** fabricated — see `specs/reference_pack_contract.yaml`.

---

## Validation (transparency)

- **Spec gate**: `validate-specs` before trusting generator config changes.
- **Per case**: reconciliation cross-checks are defined in `config/reconciliation/` (not buried in code).
- **Per batch**: `validate-batch` reports duplicates, required fields, questionnaire match, **strict blueprint contract** (`specs/dataset_structure_blueprint.yaml`: folder hierarchy, inner folder names, required documents, naming rules, **manifest `files_sha256` key order** vs blueprint iteration order), **100% blueprint compliance score** per staging/export tree in `manifests/delivery_audits/*.json`, PDF-only export checks, and optional mix drift vs `config/generator/mix.yaml`.

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
