# TaxWeave Atlas

Offline generator for **synthetic U.S. individual tax datasets**: a single canonical **`SyntheticTaxCase`** (alias **`TaxCase`**) per row, reconciled numbers, staged artifacts, **PDF-only handoff trees**, and **batch validation**.

**Runtime dependencies** (`pyproject.toml`): `pydantic`, `PyYAML`, `click`, `reportlab`. All other usage is the Python standard library.

---

## End-to-end pipeline

The system is intentionally linear: **one in-memory case model** drives every file; validation runs **before** export PDFs are finalized.

1. **TaxCase** — `build_synthetic_case` fills profile, questionnaire, income, deductions, credits, and initial federal/state shells using deterministic RNG from `(master_seed, dataset_index, uniqueness_salt)`.
2. **Reconciliation** — `reconcile_case` computes federal/state/executive (and structural MeF-shaped fields), then runs YAML-defined **cross-document checks** (e.g. W-2 vs Form 1040 wages, 1099 totals vs Schedule B, Schedule C vs SE, summary vs return). Failures abort with document- and field-labeled messages.
3. **Documents** — From the **reconciled** case only: `_staging/datasets/dataset_XXXXX/` gets the full blueprint (JSON, DOCX/XLSX placeholders, XML subset, staging manifest). `datasets/dataset_XXXXX/` gets **PDFs + `manifest.json` only** (per `specs/dataset_structure_blueprint.yaml`).
4. **Validation (batch)** — `validate-batch` (or `produce`, which generates then validates) checks fingerprints, questionnaire/case agreement, blueprint compliance, PDF-only export rules, and optional mix drift vs `config/generator/mix.yaml`.

```text
  TaxCase (synthetic source fields)
       │
       ▼
  reconcile_case  ──► cross_checks + structural validators
       │
       ├──► _staging/datasets/…  (full internal tree + checksum manifest)
       └──► datasets/…          (PDF deliverables + export manifest)
       │
       ▼
  validate-batch (optional but recommended after generation)
```

---

## Sample alignment (what “aligned” means)

The generator does **not** scrape or copy a real taxpayer dataset. Alignment is **structural and contractual**:

| Mechanism | Role |
|-----------|------|
| **`specs/sample_pack/`** | Reference **shapes** (`sample_case.json`, `mappings.yaml`, validation hints). The live generator builds new cases from config + RNG, not by editing the sample row. |
| **`specs/dataset_structure_blueprint.yaml`** | Authoritative **folder names, nesting, file names, and which paths are staging vs PDF export**. Manifest checksum key order follows blueprint iteration order. |
| **`specs/reference_pack_contract.yaml`** | Declares **prompt / MeF subset scope** and what is intentionally omitted (no invented full schedules beyond the modeled case). |
| **`specs/sample_pack/mappings.yaml`** | PDF field wiring from case paths into ReportLab-backed forms. |
| **`dataset/`** (optional) | External **layout reference** only; this codebase does not read those files during generation. |

So: **same workflow shape and packaging rules as the reference pack; all numeric and narrative content is synthetic and reconciliation-checked.**

---

## What this system guarantees

- **Single source of truth** — After reconciliation, packaged artifacts are derived only from the reconciled `SyntheticTaxCase`.
- **Deterministic generation** — Same `master_seed`, `DatasetIdentity.index`, and `uniqueness_salt` (recorded in `manifests/batch_plan.json`) yields the same case.
- **Cross-document numeric consistency** — Enforced by `config/reconciliation/cross_checks.yaml` (default exact match; optional absolute tolerance).
- **Export integrity** — Deliverable `datasets/` trees are **PDF-only** plus export `manifest.json`; validation can enforce blueprint compliance and duplicate detection.
- **Reproducible validation** — `validate-specs` gates config/sample/blueprint coherence before you rely on generator changes.

---

## What this system intentionally does not do

- **No legal or filing advice** — Synthetic training-style data only.
- **No full IRS form engine** — Not every schedule or line is modeled; see `reference_pack_contract.yaml` for scope.
- **No e-file or MeF submission** — Structural XML is a **subset** for prompt/workflow fidelity, not a filing package.
- **No cloud services** — Local files, local PDF rendering.
- **No overwrite of existing dataset folders** — A batch run fails if `dataset_XXXXX` already exists under `_staging` or `datasets` (use a fresh output directory or remove old trees).

---

## Setup (clean environment)

From a **new** clone, use an empty output directory for each batch you want to reproduce exactly.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
pip install -e ".[dev]"
python -m taxweave_atlas validate-specs
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[dev]"
python -m taxweave_atlas validate-specs
```

Pinned dependency versions are not required for determinism of **case content**; that comes from the seeded RNG and fixed configs. Use the same repository commit, config files, and `(master_seed, index, uniqueness_salt)` for bitwise-identical cases.

---

## Pilot run (small batch)

Default pilot size is **10** datasets; handoff-style workflow with validation defaults to **`produce pilot`** (35 rows — override with `--count`).

**Minimal pilot (generate only, 10 rows)**

```bash
python -m taxweave_atlas pilot --output ./out/pilot --seed 42
```

**Pilot with validation (recommended)**

```bash
python -m taxweave_atlas produce pilot --output ./out/pilot --seed 42
```

**Staging JSON only (no PDFs)**

```bash
python -m taxweave_atlas pilot --output ./out/pilot --no-pdfs
```

**Optional filters** (same for `pilot` / `generate`): `--complexity easy|medium|moderately_complex`, `--state CA|TX|NY|IL|FL`, `--tax-year <int in application.yaml>`.

Use **`-v`** on any command for DEBUG-level logging (verbose).

---

## Batch generation

| Command | Typical use |
|---------|-------------|
| `pilot` | Small run (default **10** rows). |
| `generate` | Large run (default **2000** rows). |
| `produce pilot\|weekly` | Generate then **`validate-batch`**; weekly default **350** rows unless `--count` is set. |
| `validate-batch PATH` | Post-hoc checks on an existing output root. |
| `render-pdfs TARGET` | Rebuild PDFs from `_staging/.../case.json` or a batch root. |
| `validate-specs` | Gate before trusting config or spec edits. |

**Large batch example**

```bash
python -m taxweave_atlas generate --output ./out/full --seed 42 --count 2000
python -m taxweave_atlas validate-batch ./out/full
```

**Batch plan only (no cases)**

```bash
python -m taxweave_atlas pilot --output ./out/plan --plan-only
```

---

## Architecture (modules)

| Layer | Role |
|-------|------|
| **config** | `application.yaml`, `config/generator/*.yaml`, `config/reconciliation/*` — weights, bounds, reconciliation and cross-check rules. |
| **schema** | `SyntheticTaxCase` / `TaxCase` — canonical model. |
| **generation** | `build_synthetic_case`, `run_case_generation_batch`, uniqueness salt retry for fingerprint deduplication. |
| **reconciliation** | `reconcile_case`, federal/state/executive computation, cross-checks, structural MeF packet build/validate. |
| **pdf** | ReportLab rendering from `mappings.yaml`. |
| **structure** | Blueprint-driven staging + PDF export writers, compliance scoring. |
| **delivery** | `validate_batch_output` — audits, reports under `manifests/`. |

---

## Output layout (summary)

**Deliverable** — `datasets/dataset_XXXXX/`: segment folders per blueprint, **only `.pdf` files** and root **`manifest.json`**.

**Internal** — `_staging/datasets/dataset_XXXXX/`: `case.json`, `questionnaire.json`, full blueprint (including DOCX/XLSX/XML where defined), **`00_dataset_files_manifest.json`**.

**Manifests** — `manifests/batch_plan.json`, `batch_summary.json`; after validation, `delivery_validation_report.json` and `delivery_audits/dataset_XXXXX.json`.

---

## Validation (transparency)

- **Spec gate**: `validate-specs` — sample case year/state vs `application.yaml`, blueprint load, reference contract, structural MeF config, full reconciliation of sample case.
- **Per batch**: `validate-batch` — duplicates, required artifacts, reconciled-case validation, strict blueprint compliance (including manifest key order), PDF-only export rules, optional mix drift (`--strict-distribution`).

---

## Reproducibility (library)

```python
from taxweave_atlas.generation.engine import build_synthetic_case
from taxweave_atlas.schema.ids import DatasetIdentity

case = build_synthetic_case(
    master_seed=42,
    identity=DatasetIdentity(index=0),
    salt=<uniqueness_salt from manifests/batch_plan.json>,
)
```

---

## Quality checks before submission

```bash
python -m taxweave_atlas validate-specs
pytest
ruff check src tests
```

Synthetic data only — **not** filing advice.
