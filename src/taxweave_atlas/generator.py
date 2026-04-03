from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from taxweave_atlas.compute import (
    compute_federal_lines,
    compute_state_bundle,
    effective_federal_rate,
)
from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.models.case import (
    Address,
    ExecutiveSummary,
    FederalLines,
    FederalReturn,
    Form1099Int,
    Income,
    Profile,
    Questionnaire,
    QuestionnaireAnswers,
    StateAdjustments,
    StateLines,
    StateReturn,
    TaxCase,
    W2,
)
from taxweave_atlas.paths import reference_pack_dir


def _rng_for_index(seed: int, index: int, salt: int = 0) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{index}:{salt}".encode()).digest()
    s = int.from_bytes(digest[:8], "big", signed=False)
    return random.Random(s)


def _pick(rng: random.Random, items: list[Any]) -> Any:
    if not items:
        raise ConfigurationError("empty choice list in generator_config")
    return items[rng.randrange(len(items))]


def _rand_int(rng: random.Random, lo: int, hi: int) -> int:
    return rng.randint(lo, hi)


def synthetic_ssn(rng: random.Random, index: int) -> str:
    """Use 900-xx-xxxx style synthetic identifiers (not real assigned SSNs)."""
    a = (index * 11003 + rng.randrange(100)) % 100
    b = (index * 7919 + rng.randrange(10000)) % 10000
    return f"900-{a:02d}-{b:04d}"


def _format_ein(n: int) -> str:
    n = abs(n) % 100_000_000
    hi = min(99, n // 10_000_000)
    lo = n % 10_000_000
    return f"{hi:02d}-{lo:07d}"


def bundle_fingerprint(case_dict: dict[str, Any]) -> str:
    """Stable identity hash for duplicate bundle detection."""
    p = case_dict["profile"]
    inc = case_dict["income"]
    st = case_dict["state"]
    key = {
        "ssn_p": p["synthetic_ssn_primary"],
        "ssn_s": p.get("synthetic_ssn_spouse"),
        "wages": inc["wages"],
        "interest": inc["interest"],
        "dividends": inc["dividends_ordinary"],
        "ein": inc["w2"]["employer_ein"],
        "state": st["code"],
        "filing": p["filing_status"],
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def build_tax_case(
    *,
    index: int,
    seed: int,
    gen: dict[str, Any],
    fed: dict[str, Any],
    st: dict[str, Any],
    salt: int = 0,
) -> TaxCase:
    rng = _rng_for_index(seed, index, salt)
    tax_year = int(gen["tax_year"])
    filing_status = _pick(rng, list(gen["filing_status"]))
    state_code = _pick(rng, list(gen["state_codes"]))
    loc = gen["cities_by_state"][state_code]
    if not isinstance(loc, dict) or "city" not in loc or "zip" not in loc:
        raise ConfigurationError(f"cities_by_state.{state_code} invalid")

    first = _pick(rng, list(gen["first_names"]))
    last = _pick(rng, list(gen["last_names"]))
    street = _pick(rng, list(gen["streets"]))

    spouse_first = None
    spouse_last = None
    spouse_ssn = None
    if filing_status == "married_filing_jointly":
        spouse_first = _pick(rng, list(gen["first_names"]))
        spouse_last = _pick(rng, list(gen["last_names"]))
        while spouse_first == first and spouse_last == last:
            spouse_first = _pick(rng, list(gen["first_names"]))
            spouse_last = _pick(rng, list(gen["last_names"]))
        spouse_ssn = synthetic_ssn(rng, index + 17_000)

    ssn_primary = synthetic_ssn(rng, index)

    wages = _rand_int(rng, int(gen["wages"]["min"]), int(gen["wages"]["max"]))
    interest = 0
    if rng.random() < float(gen["has_interest_probability"]):
        interest = _rand_int(rng, int(gen["interest"]["min"]), int(gen["interest"]["max"]))
    dividends = 0
    if rng.random() < float(gen["has_dividends_probability"]):
        dividends = _rand_int(rng, int(gen["dividends"]["min"]), int(gen["dividends"]["max"]))

    wh_lo, wh_hi = gen["withholding_rate"]["min"], gen["withholding_rate"]["max"]
    federal_withholding = int(round(wages * rng.uniform(float(wh_lo), float(wh_hi))))

    employer = _pick(rng, list(gen["employer_names"]))
    employer_ein = _format_ein(index * 1_000_003 + seed * 97 + rng.randrange(10_000))

    primary_name = f"{first} {last}"
    w2 = W2(
        employer_name=employer,
        employer_ein=employer_ein,
        employee_name=primary_name,
        employee_ssn=ssn_primary,
        social_security_wages=wages,
        medicare_wages=wages,
    )

    payer_tin = _format_ein(index * 1_000_003 + seed * 97 + 19_001 + rng.randrange(10_000))
    int_form = Form1099Int(
        payer_name="Synthetic Interest Payer NA",
        payer_tin=payer_tin,
        recipient_name=primary_name,
        recipient_tin=ssn_primary,
        interest_reported=interest,
    )

    income = Income(
        wages=wages,
        interest=interest,
        dividends_ordinary=dividends,
        federal_withholding=federal_withholding,
        w2=w2,
        forms_1099_int=int_form,
    )

    fl = compute_federal_lines(
        gen,
        fed,
        wages=wages,
        interest=interest,
        dividends_ordinary=dividends,
        federal_withholding=federal_withholding,
        filing_status=filing_status,
    )

    addn = _rand_int(rng, 0, 500) if rng.random() < 0.15 else 0
    subn = _rand_int(rng, 0, 300) if rng.random() < 0.12 else 0
    st_pack = compute_state_bundle(
        gen,
        st,
        state_code=state_code,
        agi=int(fl["agi"]),
        wages=wages,
        additions=addn,
        subtractions=subn,
    )

    q_items = gen.get("questionnaire_items")
    if not isinstance(q_items, list):
        raise ConfigurationError("generator_config questionnaire_items invalid")
    allowed_ids = {it["id"] for it in q_items if isinstance(it, dict) and "id" in it}
    if allowed_ids != {"q_wages_reported", "q_foreign_account", "q_crypto", "q_energy_credits"}:
        raise ConfigurationError(
            "questionnaire_items changed — update generator.build_tax_case to populate new ids"
        )

    questionnaire = Questionnaire(
        answers=QuestionnaireAnswers(
            q_wages_reported=wages,
            q_foreign_account=rng.random() < 0.08,
            q_crypto=rng.random() < 0.12,
            q_energy_credits=rng.random() < 0.05,
        )
    )

    profile = Profile(
        primary_first_name=first,
        primary_last_name=last,
        spouse_first_name=spouse_first,
        spouse_last_name=spouse_last,
        filing_status=filing_status,
        taxpayer_label=f"{primary_name} (synthetic)",
        synthetic_ssn_primary=ssn_primary,
        synthetic_ssn_spouse=spouse_ssn,
        address=Address(
            line1=street,
            city=str(loc["city"]),
            state=state_code,
            zip=str(loc["zip"]),
        ),
    )

    federal = FederalReturn(
        lines=FederalLines(
            wages=fl["wages"],
            taxable_interest=fl["taxable_interest"],
            ordinary_dividends=fl["ordinary_dividends"],
            agi=fl["agi"],
            standard_deduction=fl["standard_deduction"],
            taxable_income=fl["taxable_income"],
            total_tax=fl["total_tax"],
            federal_withholding=fl["federal_withholding"],
        )
    )

    state_ret = StateReturn(
        code=str(st_pack["code"]),
        adjustments=StateAdjustments(**st_pack["adjustments"]),
        lines=StateLines(**st_pack["lines"]),
        tax_computed=int(st_pack["tax_computed"]),
    )

    eff = effective_federal_rate(fl["total_tax"], fl["agi"])
    executive = ExecutiveSummary(
        agi=fl["agi"],
        taxable_income=fl["taxable_income"],
        total_tax=fl["total_tax"],
        federal_withholding=fl["federal_withholding"],
        state_tax=state_ret.tax_computed,
        effective_rate_federal=eff,
    )

    return TaxCase(
        tax_year=tax_year,
        profile=profile,
        questionnaire=questionnaire,
        income=income,
        federal=federal,
        state=state_ret,
        executive_summary=executive,
    )


def load_sample_case() -> TaxCase:
    path = reference_pack_dir() / "sample_case.json"
    if not path.is_file():
        raise ConfigurationError(f"Missing sample_case.json at {path}")
    return TaxCase.model_validate_json(path.read_text(encoding="utf-8"))
