from __future__ import annotations

from taxweave_atlas.config_loader import load_application_config, load_tax_rule_placeholder
from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import sample_pack_dir
from taxweave_atlas.schema.case import SyntheticTaxCase


def load_sample_case() -> SyntheticTaxCase:
    path = sample_pack_dir() / "sample_case.json"
    if not path.is_file():
        raise ConfigurationError(f"Missing sample case: {path}")
    return SyntheticTaxCase.model_validate_json(path.read_text(encoding="utf-8"))


def validate_specs_against_application_config() -> SyntheticTaxCase:
    """
    Parse the bundled sample case and ensure its coarse attributes are declared
    in application.yaml. Does not execute validation_rules.yaml (deferred).
    """
    case = load_sample_case()
    app = load_application_config()

    years = app.get("tax_years", {}).get("active")
    if not isinstance(years, list) or not all(isinstance(y, int) for y in years):
        raise ConfigurationError("application.yaml: tax_years.active must be a list of ints")
    if case.tax_year not in years:
        raise ConfigurationError(
            f"sample_case tax_year {case.tax_year} not listed in application.yaml tax_years.active"
        )

    states = app.get("states", {}).get("enabled")
    if not isinstance(states, list) or not all(isinstance(s, str) for s in states):
        raise ConfigurationError("application.yaml: states.enabled must be a list of strings")
    if case.state.code not in states:
        raise ConfigurationError(
            f"sample_case state {case.state.code!r} not listed in application.yaml states.enabled"
        )

    # Ensure placeholder rule packs exist (explicit non-guessing posture).
    fed = load_tax_rule_placeholder("federal")
    st = load_tax_rule_placeholder("state")
    if fed.get("status") != "not_implemented":
        raise ConfigurationError("config/tax_rules/federal.yaml must remain a foundation placeholder")
    if st.get("status") != "not_implemented":
        raise ConfigurationError("config/tax_rules/state.yaml must remain a foundation placeholder")

    return case
