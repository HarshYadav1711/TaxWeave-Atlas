"""
Narrative text and MeF-shaped XML derived only from ``SyntheticTaxCase`` (canonical tax case).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from taxweave_atlas.reconciliation.config import load_reconciliation_bundle
from taxweave_atlas.schema.case import SyntheticTaxCase

_FS_TO_IRS1040: dict[str, str] = {
    "single": "1",
    "married_filing_jointly": "2",
    "married_filing_separately": "3",
    "head_of_household": "4",
    "qualifying_surviving_spouse": "5",
}


def _digits_only_ssn(ssn: str) -> str:
    return re.sub(r"\D", "", ssn)


def _name_control(last_name: str) -> str:
    s = re.sub(r"[^A-Za-z]", "", last_name).upper()
    return (s + "XXXX")[:4]


def _text_el(parent: ET.Element, tag: str, text: str | int | None) -> ET.Element:
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def build_mef_subset_prompt_xml(case: SyntheticTaxCase) -> bytes:
    """
    MeF-**styled** Prompt XML: same outer grammar as the reference pack sample, populated only
    from the reconciled case (including ``structural_mef`` schedule stubs). See
    ``specs/reference_pack_contract.yaml`` for remaining omissions.
    """
    p = case.profile
    fl = case.federal.lines
    inc = case.income
    w2 = inc.w2
    mef_cfg = load_reconciliation_bundle()["structural_mef"]
    unmodeled = mef_cfg.get("fully_unmodeled_schedules") or []
    unmodeled_txt = ",".join(str(x) for x in unmodeled)

    root = ET.Element("Return")
    root.set("returnVersion", f"{case.tax_year}v5.0")

    hdr = ET.SubElement(root, "ReturnHeader")
    _text_el(hdr, "TaxYr", str(case.tax_year))
    _text_el(hdr, "TaxPeriodBeginDt", f"{case.tax_year}-01-01")
    _text_el(hdr, "TaxPeriodEndDt", f"{case.tax_year}-12-31")
    _text_el(hdr, "ReturnTypeCd", "1040")

    filer = ET.SubElement(hdr, "Filer")
    _text_el(filer, "PrimarySSN", _digits_only_ssn(p.synthetic_ssn_primary))
    _text_el(
        filer,
        "NameLine1Txt",
        f"{p.primary_first_name} {p.primary_last_name}",
    )
    _text_el(filer, "PrimaryNameControlTxt", _name_control(p.primary_last_name))
    if p.spouse_first_name and p.spouse_last_name and p.synthetic_ssn_spouse:
        _text_el(filer, "SpouseSSN", _digits_only_ssn(p.synthetic_ssn_spouse))
        _text_el(
            filer,
            "SpouseNameLine1Txt",
            f"{p.spouse_first_name} {p.spouse_last_name}",
        )
        _text_el(filer, "SpouseNameControlTxt", _name_control(p.spouse_last_name))

    addr = ET.SubElement(filer, "USAddress")
    _text_el(addr, "AddressLine1Txt", p.address.line1)
    if p.address.line2:
        _text_el(addr, "AddressLine2Txt", p.address.line2)
    _text_el(addr, "CityNm", p.address.city)
    _text_el(addr, "StateAbbreviationCd", p.address.state)
    _text_el(addr, "ZIPCd", p.address.zip.replace("-", "")[:10])

    cov = ET.SubElement(root, "TaxWeaveAtlasCoverage")
    _text_el(cov, "SyntheticSubsetInd", "true")
    _text_el(cov, "UnmodeledSchedulesTxt", unmodeled_txt)
    _text_el(
        cov,
        "PartialFieldSchedulesTxt",
        "IRS1040ScheduleC,IRS1040ScheduleSE: net self-employment only (no expense detail or SE tax lines).",
    )
    synth_names = [d.element_name for d in case.structural_mef.documents]
    if synth_names:
        _text_el(cov, "ReconciliationSynthesizedSchedulesTxt", ",".join(synth_names))

    rd = ET.SubElement(root, "ReturnData")

    irs1040 = ET.SubElement(rd, "IRS1040")
    irs1040.set("documentId", "1")
    code = _FS_TO_IRS1040.get(p.filing_status)
    if code:
        _text_el(irs1040, "IndividualReturnFilingStatusCd", code)
    _text_el(irs1040, "WagesAmt", fl.wages)
    _text_el(irs1040, "TaxableInterestAmt", fl.taxable_interest)
    _text_el(irs1040, "OrdinaryDividendsAmt", fl.ordinary_dividends)
    _text_el(irs1040, "AdjustedGrossIncomeAmt", fl.agi)
    _text_el(irs1040, "TaxableIncomeAmt", fl.taxable_income)
    _text_el(irs1040, "TotalTaxAmt", fl.total_tax)
    _text_el(irs1040, "WithholdingTaxAmt", fl.federal_withholding)

    w2_el = ET.SubElement(rd, "IRSW2")
    w2_el.set("documentId", "IRSW2-0")
    _text_el(w2_el, "EmployeeSSN", _digits_only_ssn(w2.employee_ssn))
    ein = re.sub(r"\D", "", w2.employer_ein)
    _text_el(w2_el, "EmployerEIN", ein.zfill(9) if ein else "000000000")
    en = ET.SubElement(w2_el, "EmployerName")
    _text_el(en, "BusinessNameLine1Txt", w2.employer_name[:100])
    _text_el(w2_el, "EmployeeNm", w2.employee_name[:100])
    _text_el(w2_el, "WagesAmt", inc.wages)
    _text_el(w2_el, "WithholdingAmt", inc.federal_withholding)
    _text_el(w2_el, "SocialSecurityWagesAmt", w2.social_security_wages)
    _text_el(w2_el, "MedicareWagesAndTipsAmt", w2.medicare_wages)

    if fl.taxable_interest > 0 or fl.ordinary_dividends > 0:
        schb = ET.SubElement(rd, "IRS1040ScheduleB")
        schb.set("documentId", "IRS1040ScheduleB")
        _text_el(schb, "InterestAmt", fl.taxable_interest)
        _text_el(schb, "TotalInterestAmt", fl.taxable_interest)
        _text_el(schb, "OrdinaryDividendsAmt", fl.ordinary_dividends)
        _text_el(schb, "TotalOrdinaryDividendsAmt", fl.ordinary_dividends)

    for sm in case.structural_mef.documents:
        sub = ET.SubElement(rd, sm.element_name)
        sub.set("documentId", sm.document_id)
        for tag, val in sm.fields.items():
            _text_el(sub, tag, val)

    rd.set("documentCnt", str(len(list(rd))))

    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode")
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    return (header + xml_str).encode("utf-8")


def questionnaire_highlights(case: SyntheticTaxCase) -> dict[str, Any]:
    """Key questionnaire fields for narrative consistency with reconciliation."""
    q = case.questionnaire.answers
    return {
        "q_wages_reported": q.q_wages_reported,
        "itemized_deduction_elected": q.itemized_deduction_elected,
        "has_self_employment_income": q.has_self_employment_income,
        "has_retirement_distributions": q.has_retirement_distributions,
        "complexity_tier": q.extensions.get("complexity_tier", ""),
    }


def client_summary_paragraphs(case: SyntheticTaxCase) -> list[str]:
    p = case.profile
    ex = case.executive_summary
    qh = questionnaire_highlights(case)
    lines = [
        f"Tax year {case.tax_year} — client summary (synthetic).",
        f"Taxpayer: {p.taxpayer_label}",
        f"Filing status: {p.filing_status.replace('_', ' ')}",
        f"Residence: {p.address.city}, {p.address.state} {p.address.zip}",
        f"Questionnaire alignment: wages reported {qh['q_wages_reported']}; "
        f"itemized elected {qh['itemized_deduction_elected']}; "
        f"SE income flag {qh['has_self_employment_income']}; "
        f"retirement distributions flag {qh['has_retirement_distributions']}; "
        f"complexity {qh['complexity_tier']!r}.",
        f"AGI (reconciled): {ex.agi}; taxable income: {ex.taxable_income}; "
        f"total federal tax: {ex.total_tax}; withholding: {ex.federal_withholding}.",
        "This document is generated for training and testing only. Not for filing.",
    ]
    return lines


def attachments_index_paragraphs(case: SyntheticTaxCase) -> list[str]:
    parts = [
        f"Synthetic input package for tax year {case.tax_year}.",
        "Supporting document categories (structure mirrors reference pack):",
        "— Form W-2 (wages and withholding)",
        "— Form 1099-INT (interest)",
        "— Form 1099-DIV (ordinary dividends)",
        "— Bank statement (placeholder workbook)",
        "— Invoice (placeholder)",
        "— Schedule C (placeholder workbook when self-employment not modeled as full Schedule C XML)",
    ]
    if case.income.dividends_ordinary <= 0:
        parts.append("Note: 1099-DIV PDF still present with zero or reconciled dividend disclosure for package parity.")
    parts.append("All amounts tie to the same reconciled SyntheticTaxCase as case.json.")
    return parts


def completed_forms_summary_paragraphs(case: SyntheticTaxCase) -> list[str]:
    return [
        f"Completed return package summary — TY {case.tax_year} (synthetic).",
        "Primary PDF: combined federal and state line summaries in one file (reference workflow: single return PDF).",
        "Figures reconcile to case.json / executive summary; not filing advice.",
    ]


def executive_brief_docx_paragraphs(case: SyntheticTaxCase) -> list[str]:
    ex = case.executive_summary
    return [
        f"Executive summary — TY {case.tax_year}",
        f"AGI: {ex.agi}; taxable income: {ex.taxable_income}",
        f"Federal tax: {ex.total_tax}; withholding: {ex.federal_withholding}; state tax: {ex.state_tax}",
        f"Effective federal rate (synthetic): {ex.effective_rate_federal:.4f}",
        "See companion PDF for full field table. Synthetic data only.",
    ]


def prompt_companion_docx_paragraphs(case: SyntheticTaxCase) -> list[str]:
    return [
        "Tax Return Data — Prompt companion (synthetic).",
        f"Tax year {case.tax_year}.",
        "Machine-readable intake: see Tax Return Data - Prompt.xml in this folder.",
        "XML uses a MeF-shaped subset populated from the same SyntheticTaxCase as all other artifacts.",
        "Omissions vs a full IRS e-file package are listed under TaxWeaveAtlasCoverage (sibling of ReturnData) in the XML.",
        "Not a submission to any tax authority.",
    ]
