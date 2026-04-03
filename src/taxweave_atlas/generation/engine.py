"""
Synthetic case factory: sample profile, income, deductions, and credits from YAML config,
then run reconciliation so every emitted ``SyntheticTaxCase`` is internally consistent.
"""

from __future__ import annotations

import random

from taxweave_atlas.config_loader import load_application_config, load_generator_settings
from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.generation.rng import randint_range, weighted_choice
from taxweave_atlas.generation.validation import validate_synthetic_source
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.schema.credits import CreditEntry, CreditsPacket
from taxweave_atlas.schema.deductions import DeductionPacket
from taxweave_atlas.schema.executive import ExecutiveSummary
from taxweave_atlas.schema.federal import FederalFormLines, FederalReturn
from taxweave_atlas.schema.income import Form1099Int, FormW2, IncomeSources
from taxweave_atlas.schema.ids import DatasetIdentity, stream_seed
from taxweave_atlas.schema.profile import FilingStatus, MailingAddress, TaxpayerProfile
from taxweave_atlas.schema.questionnaire import QuestionnaireAnswers, QuestionnairePacket
from taxweave_atlas.schema.state import StateAdjustments, StateReturn, StateReturnLines
from taxweave_atlas.schema.supporting import SupportingDocumentsIndex


def _format_ein(n: int) -> str:
    n = abs(n) % 100_000_000
    hi = min(99, n // 10_000_000)
    lo = n % 10_000_000
    return f"{hi:02d}-{lo:07d}"


def _synthetic_ssn(rng: random.Random, salt: int, idx: int, role: str) -> str:
    base = (idx * 7919 + salt * 503 + hash(role) % 10_007) % 100_000_000
    a = base % 100
    b = (base // 100) % 10_000
    return f"900-{a:02d}-{b:04d}"


def build_synthetic_case(
    *,
    master_seed: int,
    identity: DatasetIdentity,
    salt: int = 0,
    state_override: str | None = None,
    tax_year_override: int | None = None,
    complexity_override: str | None = None,
) -> SyntheticTaxCase:
    """One reconciled synthetic taxpayer-year. RNG stream: ``stream_seed(master_seed, identity, salt=salt)``."""
    app = load_application_config()
    settings = load_generator_settings()
    strat = settings.get("stratification") or {}
    pools = settings.get("pools") or {}
    comp = settings.get("computation") or {}
    tiers = settings.get("complexity_tiers") or {}
    fs_weights = settings.get("filing_status_weights") or {}

    if not isinstance(strat, dict) or not isinstance(pools, dict):
        raise ConfigurationError("generator settings missing stratification or pools")

    enabled_states = list(app["states"]["enabled"])
    active_years = [int(y) for y in app["tax_years"]["active"]]

    if tax_year_override is not None and tax_year_override not in active_years:
        raise ConfigurationError(
            f"tax_year_override {tax_year_override} not in application tax_years.active"
        )
    if state_override is not None and state_override not in enabled_states:
        raise ConfigurationError(f"state_override {state_override!r} not in states.enabled")
    if complexity_override is not None and complexity_override not in tiers:
        raise ConfigurationError(f"complexity_override {complexity_override!r} unknown in generator tiers")

    sw = strat["state_weights"]
    for s in enabled_states:
        if s not in sw:
            raise ConfigurationError(f"stratification.state_weights missing {s!r}")
    state_weights = {s: float(sw[s]) for s in enabled_states}

    yw_raw = strat["tax_year_weights"]
    year_weights = {str(int(k)): float(v) for k, v in yw_raw.items()}
    for y in active_years:
        if str(y) not in year_weights:
            raise ConfigurationError(f"stratification.tax_year_weights missing {y}")

    cx_weights = {
        k: float(v) for k, v in strat["complexity_weights"].items() if k in tiers
    }
    if not cx_weights:
        raise ConfigurationError("stratification.complexity_weights empty or mismatched with tiers")

    rng = random.Random(stream_seed(master_seed, identity, salt=salt))

    state = state_override or weighted_choice(rng, state_weights)
    tax_year = tax_year_override or int(weighted_choice(rng, year_weights))
    cx = complexity_override or weighted_choice(rng, cx_weights)
    tier = tiers.get(cx)
    if not isinstance(tier, dict):
        raise ConfigurationError(f"Unknown complexity tier {cx!r}")

    filing_status = weighted_choice(rng, {k: float(v) for k, v in fs_weights.items()})
    fs: FilingStatus = filing_status  # type: ignore[assignment]

    qc_max = int(tier["qualifying_children_max"])
    od_max = int(tier["other_dependents_max"])
    qc = rng.randint(0, qc_max)
    od = rng.randint(0, od_max)

    if fs == "head_of_household" and qc + od < 1:
        qc = 1
    if fs == "qualifying_surviving_spouse" and qc < 1:
        qc = 1

    first_names: list[str] = pools["first_names"]
    last_names: list[str] = pools["last_names"]
    first = rng.choice(first_names)
    last = rng.choice(last_names)

    spouse_first = None
    spouse_last = None
    spouse_ssn = None
    if fs in ("married_filing_jointly", "married_filing_separately"):
        spouse_first = rng.choice(first_names)
        spouse_last = rng.choice(last_names)
        tries = 0
        while spouse_first == first and spouse_last == last and tries < 20:
            spouse_first = rng.choice(first_names)
            spouse_last = rng.choice(last_names)
            tries += 1
        spouse_ssn = _synthetic_ssn(rng, salt, identity.index, "spouse")

    addr_pool = pools["addresses_by_state"][state]
    city_entry = rng.choice(addr_pool["cities"])
    street = rng.choice(addr_pool["streets"])
    primary_ssn = _synthetic_ssn(rng, salt, identity.index, "primary")

    profile = TaxpayerProfile(
        primary_first_name=first,
        primary_last_name=last,
        spouse_first_name=spouse_first,
        spouse_last_name=spouse_last,
        filing_status=fs,
        taxpayer_label=f"{first} {last} (synthetic)",
        synthetic_ssn_primary=primary_ssn,
        synthetic_ssn_spouse=spouse_ssn,
        address=MailingAddress(
            line1=street,
            city=str(city_entry["city"]),
            state=state,
            zip=str(city_entry["zip"]),
        ),
        dependents_qualifying_children_under_17=qc,
        dependents_other=od,
    )

    wages = randint_range(rng, tier["wages"])
    interest = 0
    if rng.random() < float(tier["interest_probability"]):
        interest = randint_range(rng, tier["interest"])
    dividends = 0
    if rng.random() < float(tier["dividend_probability"]):
        dividends = randint_range(rng, tier["dividends"])

    other: dict[str, int] = {}
    passive: dict[str, int] = {}
    has_se = False
    has_ret = False
    if rng.random() < float(tier["self_employment_probability"]):
        other["self_employment_net"] = rng.randint(3_000, 48_000)
        has_se = True
    if rng.random() < float(tier["retirement_probability"]):
        passive["retirement_distributions"] = rng.randint(2_000, 62_000)
        has_ret = True

    employer = rng.choice(pools["employers"])
    payer = rng.choice(pools["payers_1099"])
    ein = _format_ein(identity.index * 1_000_003 + master_seed + salt + rng.randrange(50_000))
    payer_tin = _format_ein(identity.index * 999_983 + master_seed + 17_001 + rng.randrange(50_000))

    primary_name = profile.primary_full_name
    w2 = FormW2(
        employer_name=employer,
        employer_ein=ein,
        employee_name=primary_name,
        employee_ssn=primary_ssn,
        social_security_wages=wages,
        medicare_wages=wages,
    )
    int_form = Form1099Int(
        payer_name=payer,
        payer_tin=payer_tin,
        recipient_name=primary_name,
        recipient_tin=primary_ssn,
        interest_reported=interest,
    )

    wh_lo = float(comp["withholding"]["rate_min"])
    wh_hi = float(comp["withholding"]["rate_max"])
    federal_withholding = int(round(wages * rng.uniform(wh_lo, wh_hi)))

    income = IncomeSources(
        wages=wages,
        interest=interest,
        dividends_ordinary=dividends,
        federal_withholding=federal_withholding,
        w2=w2,
        forms_1099_int=int_form,
        other_ordinary_income=other,
        passive_income=passive,
    )

    itemized_elected = rng.random() < float(tier["itemized_probability"])
    itemized_components: dict[str, int] = {}
    if itemized_elected:
        elected_method = "itemized"
        salt_cap = rng.randint(4_000, 10_000)
        charity = rng.randint(500, 12_000)
        mortgage = rng.randint(0, 18_000)
        itemized_components["state_and_local_income_tax"] = salt_cap
        itemized_components["charitable_cash"] = charity
        if mortgage > 0:
            itemized_components["mortgage_interest"] = mortgage
    else:
        elected_method = "standard"

    ded = DeductionPacket(
        elected_method=elected_method,  # type: ignore[arg-type]
        itemized_components=itemized_components,
        adjustments_to_agi={},
    )

    caps = comp["credit_caps_synthetic"]
    credits: list[CreditEntry] = []
    if qc > 0:
        ctc = int(caps["ctc_per_child"]) * qc
        credits.append(CreditEntry(code="CTC_SYNTH", amount=ctc, refundable=False))
        if cx != "easy" and rng.random() < 0.55:
            actc = rng.randint(0, min(int(caps["actc_max_refundable"]), ctc))
            if actc > 0:
                credits.append(CreditEntry(code="ACTC_SYNTH", amount=actc, refundable=True))
    if cx == "moderately_complex" and rng.random() < 0.25:
        credits.append(
            CreditEntry(
                code="AOTC_SYNTH",
                amount=rng.randint(500, int(caps["education_credit_max"])),
                refundable=False,
            )
        )
    if cx != "easy" and rng.random() < 0.12:
        credits.append(
            CreditEntry(
                code="SAVER_SYNTH",
                amount=rng.randint(100, int(caps["saver_credit_max"])),
                refundable=False,
            )
        )

    credits_packet = CreditsPacket(credits=credits)

    addn = 0
    subn = 0
    if cx == "moderately_complex" and rng.random() < 0.35:
        addn = rng.randint(0, 4_000)
    if rng.random() < 0.2:
        subn = rng.randint(0, 2_500)

    q_answers = QuestionnaireAnswers(
        q_wages_reported=wages,
        q_foreign_account=cx != "easy" and rng.random() < 0.06,
        q_crypto=cx != "easy" and rng.random() < 0.1,
        q_energy_credits=cx == "moderately_complex" and rng.random() < 0.08,
        num_qualifying_children_under_17=qc,
        num_other_dependents=od,
        itemized_deduction_elected=itemized_elected,
        has_self_employment_income=has_se,
        has_retirement_distributions=has_ret,
        extensions={
            "complexity_tier": cx,
            "stratum_state": state,
            "stratum_tax_year": str(tax_year),
            "dataset_slug": identity.slug,
        },
    )
    questionnaire = QuestionnairePacket(answers=q_answers)

    federal_ph = FederalReturn(
        lines=FederalFormLines(
            wages=wages,
            taxable_interest=interest,
            ordinary_dividends=dividends,
            agi=0,
            standard_deduction=0,
            taxable_income=0,
            total_tax=0,
            federal_withholding=federal_withholding,
        )
    )
    st_ph = StateReturn(
        code=state,
        adjustments=StateAdjustments(additions=addn, subtractions=subn),
        lines=StateReturnLines(
            state_wages=wages,
            additions=addn,
            subtractions=subn,
            state_taxable_income=0,
            state_tax=0,
        ),
        tax_computed=0,
    )
    executive_ph = ExecutiveSummary(
        agi=0,
        taxable_income=0,
        total_tax=0,
        federal_withholding=federal_withholding,
        state_tax=0,
        effective_rate_federal=0.0,
    )

    case = SyntheticTaxCase(
        tax_year=tax_year,
        profile=profile,
        questionnaire=questionnaire,
        income=income,
        deductions=ded,
        credits=credits_packet,
        supporting_documents=SupportingDocumentsIndex(documents=[]),
        federal=federal_ph,
        state=st_ph,
        executive_summary=executive_ph,
    )
    validate_synthetic_source(case)
    from taxweave_atlas.reconciliation.pipeline import reconcile_case as _reconcile

    return _reconcile(case)
