# TaxWeave Atlas

Local-only synthetic US individual tax dataset generator. Produces **PDF-only** bundles with internal consistency across questionnaire, supporting documents, federal summary lines, state summary lines, and executive summary.

## Requirements

- Python 3.11+
- Dependencies in `pyproject.toml` (ReportLab, Pydantic, PyYAML, Click)

## Quick start

```bash
cd "D:\Fun\TaxWeave Atlas"
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .

# Pilot batch (10 datasets)
taxweave-atlas generate --count 10 --seed 42 --output ./out/pilot

# Full run (2000)
taxweave-atlas generate --count 2000 --seed 42 --output ./out/full_2000

# PDF-only under each dataset folder (no case.json sidecar; regenerate via seed + index)
taxweave-atlas generate --count 2000 --seed 42 --output ./out/full_2000 --no-case-json
```

## Project layout

- `reference_pack/` — canonical sample case, field mappings, generator enumerations, validation rules
- `templates/manifest.yaml` — declares deliverable PDF types bound to renderers
- `src/taxweave_atlas/` — pipeline, models, validation, PDF renderers

## Rules of engagement

All tax logic and allowed values come from `reference_pack/`. Missing mappings or unknown generator keys **fail loudly** at load or render time.

## Reproducibility

Generation is keyed by `--seed` and dataset index. The same seed and count reproduce identical bundles (including uniqueness checks).
