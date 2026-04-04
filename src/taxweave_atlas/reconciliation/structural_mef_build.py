"""
Build ``StructuralMefPacket`` from ``config/reconciliation/structural_mef.yaml`` and
``supporting_forms`` selection (6–7 supporting forms + mandatory IRS1040 outside this list).
"""

from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ConfigurationError, ReconciliationError
from taxweave_atlas.reconciliation.paths_util import resolve_dotted_path
from taxweave_atlas.reconciliation.supporting_forms import (
    applicable_supporting_forms,
    finalize_supporting_forms,
    ordered_supporting_forms,
)
from taxweave_atlas.schema.case import SyntheticTaxCase
from taxweave_atlas.schema.structural_mef import StructuralMefDocument, StructuralMefPacket


def _as_positive_int(case_data: dict[str, Any], path: str) -> int:
    try:
        v = resolve_dotted_path(case_data, path)
    except KeyError:
        return 0
    if v is None:
        return 0
    n = int(v)
    return n if n > 0 else 0


def _resolve_int(case_data: dict[str, Any], path: str) -> int:
    try:
        v = resolve_dotted_path(case_data, path)
    except KeyError:
        return 0
    if v is None:
        return 0
    return int(v)


def _build_8812(case: SyntheticTaxCase, s8812: dict[str, Any]) -> StructuralMefDocument:
    qc = case.profile.dependents_qualifying_children_under_17
    nr_codes = set(s8812.get("nonrefundable_credit_codes") or [])
    ref_codes = set(s8812.get("refundable_credit_codes") or [])
    ctc_total = sum(c.amount for c in case.credits.credits if c.code in nr_codes)
    actc_total = sum(c.amount for c in case.credits.credits if c.code in ref_codes)
    if ctc_total <= 0 and actc_total <= 0:
        raise ReconciliationError(
            "structural_mef: IRS1040Schedule8812 selected but no CTC_SYNTH/ACTC_SYNTH credit amounts"
        )
    el = s8812.get("element_name") or "IRS1040Schedule8812"
    did = s8812.get("document_id") or "IRS1040Schedule8812-0"
    xfn = s8812.get("xml_field_names") or {}
    f_child = xfn.get("child_count")
    f_ctc = xfn.get("ctc_total")
    f_actc = xfn.get("actc_total")
    if not all(isinstance(x, str) for x in (f_child, f_ctc, f_actc)):
        raise ConfigurationError("structural_mef: schedule_8812.xml_field_names incomplete")
    return StructuralMefDocument(
        element_name=str(el),
        document_id=str(did),
        fields={f_child: qc, f_ctc: ctc_total, f_actc: actc_total},
    )


def _build_from_yaml_def(
    case: SyntheticTaxCase,
    element_name: str,
    block: dict[str, Any],
    data: dict[str, Any],
) -> StructuralMefDocument:
    did = block.get("document_id")
    fields_map = block.get("fields") or {}
    if not isinstance(did, str) or not isinstance(fields_map, dict):
        raise ConfigurationError(f"structural_mef: incomplete form_definitions for {element_name}")
    fields: dict[str, int] = {}
    for xml_tag, src_path in fields_map.items():
        if not isinstance(xml_tag, str) or not isinstance(src_path, str):
            raise ConfigurationError(f"structural_mef: {element_name} fields must be tag: path strings")
        fields[xml_tag] = _resolve_int(data, src_path)
    return StructuralMefDocument(element_name=element_name, document_id=did, fields=fields)


def build_structural_mef_packet(case: SyntheticTaxCase, spec: dict[str, Any]) -> StructuralMefPacket:
    if spec.get("version") != 1:
        raise ConfigurationError("structural_mef.yaml: unsupported version")

    applicable = applicable_supporting_forms(case)
    final_names = finalize_supporting_forms(case, applicable)
    ordered = ordered_supporting_forms(final_names)

    form_defs = spec.get("form_definitions") or {}
    if not isinstance(form_defs, dict):
        raise ConfigurationError("structural_mef: form_definitions must be a mapping")

    data = case.model_dump(mode="json")
    documents: list[StructuralMefDocument] = []
    s8812_full = spec.get("schedule_8812") or {}

    for name in ordered:
        if name == "IRS1040Schedule8812":
            blk = {**s8812_full, **(form_defs.get("IRS1040Schedule8812") or {})}
            documents.append(_build_8812(case, blk))
            continue
        if name == "IRS8867":
            total = sum(c.amount for c in case.credits.credits)
            if total <= 0:
                raise ReconciliationError("structural_mef: IRS8867 requires positive total credits")
            b = form_defs.get("IRS8867") or {}
            did = b.get("document_id") if isinstance(b.get("document_id"), str) else "IRS8867-0"
            documents.append(
                StructuralMefDocument(
                    element_name="IRS8867",
                    document_id=did,
                    fields={"TotalCreditsClmAmt": total},
                )
            )
            continue

        block = form_defs.get(name)
        if not isinstance(block, dict):
            raise ConfigurationError(f"structural_mef: missing form_definitions for {name}")

        when_path = block.get("when_positive_path")
        if isinstance(when_path, str):
            if _as_positive_int(data, when_path) <= 0:
                raise ReconciliationError(
                    f"structural_mef: form {name} in selection but when_positive_path not positive"
                )

        documents.append(_build_from_yaml_def(case, name, block, data))

    return StructuralMefPacket(documents=documents)
