# TaxWeave Atlas (foundation)

Local-only scaffold for synthetic US individual tax datasets. **No paid services, no cloud.**  
This stage defines repository boundaries, typed schemas, configuration placeholders, deterministic dataset identity, and CLI entrypoints. **Case synthesis, reconciliation, and PDF rendering are not implemented yet.**

## Layout

| Path | Purpose |
|------|---------|
| `specs/sample_pack/` | Source specs: `sample_case.json`, `mappings.yaml`, `validation_rules.yaml` |
| `specs/templates/` | PDF deliverable manifest (renderers wired later) |
| `config/application.yaml` | Tax years, enabled states, complexity tiers |
| `config/tax_rules/` | Explicit placeholders for federal/state rules (no guessed law) |
| `src/taxweave_atlas/schema/` | Pydantic models: profile, income, deductions, credits, supporting docs, federal/state, executive summary |
| `src/taxweave_atlas/generation/` | Stub — synthetic case factory (future) |
| `src/taxweave_atlas/reconciliation/` | Deterministic reconciliation: AGI, 1040-style lines, state stub tax, executive summary, supporting-doc key sync, YAML cross-checks |
| `config/reconciliation/` | Scope, credit-stacking rules, cross-check rules (plus bracket/std tables from `config/generator/computation.yaml`) |
| `src/taxweave_atlas/pdf/` | Stub — template fill / rendering (future) |
| `src/taxweave_atlas/validation/` | Spec validation against `application.yaml` |
| `src/taxweave_atlas/orchestration/` | Batch plan + manifests (deterministic ids/seeds only) |

## Install

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

## Commands

```bash
python -m taxweave_atlas validate-specs
python -m taxweave_atlas pilot --output ./outputs/pilot
python -m taxweave_atlas generate --output ./outputs/full
```

`pilot` defaults to `--count 10`; `generate` defaults to `--count 2000`. By default they run the **synthetic taxpayer engine**: each `datasets/dataset_XXXXX/` folder gets `case.json` and `questionnaire.json`, plus `manifests/batch_plan.json` (with `stream_seed`, `uniqueness_salt`, `case_fingerprint`, and sampled `tax_year` / `state_code` / `complexity_tier`).

- `--plan-only` — write `batch_plan.json` only (seeds/slots, no cases).
- `--complexity easy|medium|moderately_complex` — fix tier (otherwise mix comes from `config/generator/mix.yaml`).
- `--state CA|TX|NY|IL|FL` and `--tax-year YYYY` — fix stratum.

Tune the dataset mix via `config/generator/mix.yaml` (state/year/complexity weights) and tier bounds via `config/generator/complexity.yaml`. Internal federal/state line math for coherence uses `config/generator/computation.yaml` (labeled synthetic, not filing advice).

Reproducing a row: use `master_seed`, dataset `index`, and `uniqueness_salt` from `batch_plan.json` with `taxweave_atlas.generation.build_synthetic_case(..., salt=uniqueness_salt)`.

## Reconciliation

After the generator assembles profile, income, deductions, and credits, **`reconcile_case`** (`taxweave_atlas.reconciliation.pipeline`) recomputes federal lines, state lines, executive summary, and supporting-document `key_amounts` from explicit tables. Unsupported income keys or states/years outside `config/reconciliation/scope.yaml` raise **`ReconciliationError`**.

Before PDF production, call **`validate_reconciled_case`** (or rely on `reconcile_case`, which runs cross-checks at the end) so mismatches fail loudly.

## Extending

1. Fill `config/tax_rules/` with versioned rule data; update `src/taxweave_atlas/validation/specs.py` when `status` is no longer `not_implemented` (the foundation gate is intentional).
2. Implement `generation` → produce `SyntheticTaxCase` instances.
3. Implement `reconciliation` → consume rule packs, mutate or verify case lines.
4. Implement `pdf` → read `specs/templates/manifest.yaml` + `specs/sample_pack/mappings.yaml`.
