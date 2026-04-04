from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from taxweave_atlas.pdf.irs.acroform import fill_acroform_pdf, match_field_key
from taxweave_atlas.pdf.irs.cache import get_irs_prior_pdf_bytes
from taxweave_atlas.schema.case import SyntheticTaxCase


def _fmt_money(n: int) -> str:
    return str(int(n))


def _fmt_ssn(raw: str) -> str:
    d = "".join(c for c in raw if c.isdigit())
    if len(d) == 9:
        return f"{d[:3]}-{d[3:5]}-{d[5:]}"
    return raw.strip()[:11]


def _add(reader: PdfReader, updates: dict[str, str], tail: str, value: str) -> None:
    k = match_field_key(reader, tail)
    if k:
        updates[k] = value


def _filing_status_field(reader: PdfReader, status: str) -> str | None:
    mapping = {
        "single": ".Page1[0].c1_1[0]",
        "married_filing_jointly": ".Page1[0].c1_2[0]",
        "married_filing_separately": ".Page1[0].c1_3[0]",
        "head_of_household": ".Page1[0].c1_4[0]",
        "qualifying_surviving_spouse": ".Page1[0].c1_5[0]",
    }
    tail = mapping.get(status)
    return match_field_key(reader, tail) if tail else None


def _qbi_amount(case: SyntheticTaxCase) -> int:
    for d in case.structural_mef.documents:
        if d.element_name == "IRS8995" and "QlfyBusIncmAmt" in d.fields:
            return int(d.fields["QlfyBusIncmAmt"])
    return 0


def build_f1040_field_values(reader: PdfReader, case: SyntheticTaxCase) -> dict[str, str]:
    """Map reconciled case data onto 2024-style Form 1040 AcroForm keys (IRS prior PDF)."""
    p = case.profile
    L = case.federal.lines
    addl = L.additional_lines

    updates: dict[str, str] = {}

    _add(reader, updates, ".Page1[0].f1_01[0]", p.primary_first_name.strip())
    _add(reader, updates, ".Page1[0].f1_02[0]", p.primary_last_name.strip())
    _add(reader, updates, ".Page1[0].f1_03[0]", _fmt_ssn(p.synthetic_ssn_primary))

    if p.filing_status == "married_filing_jointly" and p.spouse_first_name and p.spouse_last_name:
        _add(reader, updates, ".Page1[0].f1_04[0]", p.spouse_first_name.strip())
        _add(reader, updates, ".Page1[0].f1_05[0]", p.spouse_last_name.strip())
        if p.synthetic_ssn_spouse:
            _add(reader, updates, ".Page1[0].f1_06[0]", _fmt_ssn(p.synthetic_ssn_spouse))

    _add(reader, updates, "Address_ReadOrder[0].f1_20[0]", p.address.line1.strip())
    if p.address.line2:
        _add(reader, updates, "Address_ReadOrder[0].f1_21[0]", p.address.line2.strip())
    _add(reader, updates, "Address_ReadOrder[0].f1_23[0]", p.address.city.strip())
    _add(reader, updates, "Address_ReadOrder[0].f1_24[0]", p.address.state.strip().upper()[:2])
    _add(reader, updates, "Address_ReadOrder[0].f1_25[0]", p.address.zip.strip()[:10])

    fs = _filing_status_field(reader, p.filing_status)
    if fs:
        updates[fs] = "/1"

    sched1_inc = int(addl.get("schedule_1_additional_income_retirement", 0) or 0)
    sched1_adj = int(addl.get("schedule_1_adjustments_total", 0) or 0)
    pre_credit = int(addl.get("pre_credit_income_tax", 0) or 0)
    sched2_line3 = int(addl.get("schedule_2_additional_taxes", 0) or 0)

    wages = int(L.wages)
    interest = int(L.taxable_interest)
    divs = int(L.ordinary_dividends)
    agi = int(L.agi)
    std = int(L.standard_deduction)
    sched_a = int(addl.get("schedule_a_total", 0) or 0)
    itemized = bool(addl.get("itemized_elected_flag", 0))
    line12 = sched_a if itemized else std
    qbi = _qbi_amount(case)
    line14 = line12 + qbi
    taxable = int(L.taxable_income)
    total_tax = int(L.total_tax)
    wh = int(L.federal_withholding)

    line9 = wages + interest + divs + sched1_inc
    if line9 != agi + sched1_adj:
        line9 = agi + sched1_adj

    _add(reader, updates, ".Page1[0].f1_32[0]", _fmt_money(wages))
    _add(reader, updates, ".Page1[0].f1_41[0]", _fmt_money(wages))
    _add(reader, updates, ".Page1[0].f1_42[0]", "0")
    _add(reader, updates, ".Page1[0].f1_43[0]", _fmt_money(interest))
    _add(reader, updates, ".Page1[0].f1_44[0]", "0")
    _add(reader, updates, ".Page1[0].f1_45[0]", _fmt_money(divs))
    _add(reader, updates, ".Page1[0].f1_52[0]", "0")
    _add(reader, updates, ".Page1[0].f1_53[0]", _fmt_money(sched1_inc))
    _add(reader, updates, ".Page1[0].f1_54[0]", _fmt_money(line9))
    _add(reader, updates, ".Page1[0].f1_55[0]", _fmt_money(sched1_adj))
    _add(reader, updates, ".Page1[0].f1_56[0]", _fmt_money(agi))
    _add(reader, updates, ".Page1[0].f1_57[0]", _fmt_money(line12))
    _add(reader, updates, ".Page1[0].f1_58[0]", _fmt_money(qbi))
    _add(reader, updates, ".Page1[0].f1_59[0]", _fmt_money(line14))
    _add(reader, updates, ".Page1[0].f1_60[0]", _fmt_money(taxable))

    if pre_credit > 0:
        _add(reader, updates, ".Page2[0].f2_03[0]", _fmt_money(pre_credit))
    if sched2_line3 > 0:
        _add(reader, updates, ".Page2[0].f2_04[0]", _fmt_money(sched2_line3))
    _add(reader, updates, ".Page2[0].f2_11[0]", _fmt_money(total_tax))
    _add(reader, updates, ".Page2[0].f2_12[0]", _fmt_money(wh))
    _add(reader, updates, ".Page2[0].f2_15[0]", _fmt_money(wh))

    over = max(0, wh - total_tax)
    if over > 0:
        _add(reader, updates, ".Page2[0].f2_35[0]", _fmt_money(over))

    return updates


def render_filled_f1040_pdf_bytes(case: SyntheticTaxCase) -> bytes:
    """Official IRS Form 1040 fillable PDF with reconciled fields (2+ pages)."""
    raw = get_irs_prior_pdf_bytes(slug="f1040", year=case.tax_year)
    reader = PdfReader(BytesIO(raw))
    values = build_f1040_field_values(reader, case)
    return fill_acroform_pdf(raw, values)
