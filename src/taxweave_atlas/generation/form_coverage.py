"""
Ensure each synthetic case triggers at least six applicable supporting forms (before the 7-form cap).

Fillers are deterministic from the case RNG stream: only amounts are jittered, not inclusion rules.
"""

from __future__ import annotations

import random

from taxweave_atlas.schema.credits import CreditEntry


def _ctc_actc_totals(credits: list[CreditEntry]) -> tuple[int, int]:
    ctc = sum(c.amount for c in credits if c.code == "CTC_SYNTH")
    actc = sum(c.amount for c in credits if c.code == "ACTC_SYNTH")
    return ctc, actc


def _raw_supporting_count(
    *,
    se_net: int,
    interest: int,
    dividends: int,
    sch1_adj: int,
    retirement: int,
    schedule_2: int,
    qc: int,
    ctc: int,
    actc: int,
    qbi: int,
    dep: int,
    credit_total: int,
) -> int:
    n = 0
    if interest > 0 or dividends > 0:
        n += 1
    if se_net > 0:
        n += 2
    if sch1_adj > 0 or retirement > 0:
        n += 1
    if schedule_2 > 0:
        n += 1
    if qc >= 1 and (ctc > 0 or actc > 0):
        n += 1
    if qbi > 0:
        n += 1
    if dep > 0:
        n += 1
    if credit_total > 0:
        n += 1
    return n


def enrich_supporting_form_coverage(
    rng: random.Random,
    *,
    complexity_tier: str,
    qualifying_children: int,
    interest_div: list[int],
    other_ordinary: dict[str, int],
    passive_income: dict[str, int],
    adjustments_to_agi: dict[str, int],
    credits: list[CreditEntry],
    stub_amounts: dict[str, int],
) -> None:
    """
    Mutate buckets in place until at least six supporting forms are justified.

    ``interest_div`` is ``[interest, dividends]``. ``stub_amounts`` keys: ``schedule_2``,
    ``qbi``, ``dep`` (mapped to case top-level fields in the engine).
    """
    interest = interest_div[0]
    dividends = interest_div[1]
    retirement = int(passive_income.get("retirement_distributions", 0) or 0)
    sch1_adj = sum(adjustments_to_agi.values())
    sch2 = int(stub_amounts.get("schedule_2", 0) or 0)
    qbi = int(stub_amounts.get("qbi", 0) or 0)
    dep = int(stub_amounts.get("dep", 0) or 0)
    credit_total = sum(c.amount for c in credits)
    ctc, actc = _ctc_actc_totals(credits)

    def refresh() -> int:
        nonlocal interest, dividends, sch1_adj, retirement, sch2, qbi, dep, credit_total, ctc, actc
        interest = interest_div[0]
        dividends = interest_div[1]
        sch1_adj = sum(adjustments_to_agi.values())
        retirement = int(passive_income.get("retirement_distributions", 0) or 0)
        sch2 = int(stub_amounts.get("schedule_2", 0) or 0)
        qbi = int(stub_amounts.get("qbi", 0) or 0)
        dep = int(stub_amounts.get("dep", 0) or 0)
        credit_total = sum(c.amount for c in credits)
        ctc, actc = _ctc_actc_totals(credits)
        se_net = int(other_ordinary.get("self_employment_net", 0) or 0)
        return _raw_supporting_count(
            se_net=se_net,
            interest=interest,
            dividends=dividends,
            sch1_adj=sch1_adj,
            retirement=retirement,
            schedule_2=sch2,
            qc=qualifying_children,
            ctc=ctc,
            actc=actc,
            qbi=qbi,
            dep=dep,
            credit_total=credit_total,
        )

    guard = 0
    while refresh() < 6 and guard < 24:
        guard += 1
        if interest_div[0] <= 0 and interest_div[1] <= 0:
            interest_div[0] = 120 + rng.randint(0, 180)
            continue
        if sum(adjustments_to_agi.values()) <= 0 and retirement <= 0:
            if complexity_tier == "easy":
                adjustments_to_agi["educator_expenses_synthetic"] = 250 + rng.randint(0, 50)
            else:
                adjustments_to_agi["ira_deduction_synthetic"] = 2000 + rng.randint(0, 1500)
            continue
        if int(stub_amounts.get("schedule_2", 0) or 0) <= 0:
            stub_amounts["schedule_2"] = 650 + rng.randint(0, 250)
            continue
        if int(stub_amounts.get("qbi", 0) or 0) <= 0:
            stub_amounts["qbi"] = 8000 + rng.randint(0, 4000)
            continue
        if int(stub_amounts.get("dep", 0) or 0) <= 0:
            stub_amounts["dep"] = 3200 + rng.randint(0, 2000)
            continue
        if sum(c.amount for c in credits) <= 0:
            credits.append(
                CreditEntry(
                    code="FORM_COVERAGE_SYNTH",
                    amount=400 + rng.randint(0, 200),
                    refundable=False,
                )
            )
            continue
        if retirement <= 0 and complexity_tier != "easy":
            passive_income["retirement_distributions"] = 3500 + rng.randint(0, 2000)
            continue
        # Last resort: bump dividends to keep Schedule B non-zero path distinct from interest-only
        if interest_div[1] <= 0:
            interest_div[1] = 150 + rng.randint(0, 120)
            continue
        break
