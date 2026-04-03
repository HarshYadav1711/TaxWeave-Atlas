"""
Build ``StructuralMefPacket`` from ``config/reconciliation/structural_mef.yaml``.

Only path resolution and credit aggregation by code — no tax formulas.
"""

from __future__ import annotations

from typing import Any

from taxweave_atlas.exceptions import ConfigurationError, ReconciliationError
from taxweave_atlas.reconciliation.paths_util import resolve_dotted_path
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


def build_structural_mef_packet(case: SyntheticTaxCase, spec: dict[str, Any]) -> StructuralMefPacket:
    if spec.get("version") != 1:
        raise ConfigurationError("structural_mef.yaml: unsupported version")
    data = case.model_dump(mode="json")
    documents: list[StructuralMefDocument] = []

    sc = spec.get("schedule_c") or {}
    se_cfg = spec.get("schedule_se") or {}
    s8812 = spec.get("schedule_8812") or {}

    se_path = sc.get("when_positive_path")
    if not isinstance(se_path, str):
        raise ConfigurationError("structural_mef: schedule_c.when_positive_path required")
    se_net = _as_positive_int(data, se_path)

    if se_net > 0:
        sc_name = sc.get("element_name")
        sc_id = sc.get("document_id")
        sc_fields_map = sc.get("fields") or {}
        if not isinstance(sc_name, str) or not isinstance(sc_id, str) or not isinstance(sc_fields_map, dict):
            raise ConfigurationError("structural_mef: schedule_c element_name, document_id, fields required")
        sc_fields: dict[str, int] = {}
        for xml_tag, src_path in sc_fields_map.items():
            if not isinstance(xml_tag, str) or not isinstance(src_path, str):
                raise ConfigurationError("structural_mef: schedule_c.fields must be tag: path strings")
            sc_fields[xml_tag] = _resolve_int(data, src_path)
        documents.append(StructuralMefDocument(element_name=sc_name, document_id=sc_id, fields=sc_fields))

        se_name = se_cfg.get("element_name")
        se_id = se_cfg.get("document_id")
        se_fields_map = se_cfg.get("fields") or {}
        if not isinstance(se_name, str) or not isinstance(se_id, str) or not isinstance(se_fields_map, dict):
            raise ConfigurationError("structural_mef: schedule_se block incomplete")
        se_fields: dict[str, int] = {}
        for xml_tag, src_path in se_fields_map.items():
            if not isinstance(xml_tag, str) or not isinstance(src_path, str):
                raise ConfigurationError("structural_mef: schedule_se.fields must be tag: path strings")
            se_fields[xml_tag] = _resolve_int(data, src_path)
        documents.append(StructuralMefDocument(element_name=se_name, document_id=se_id, fields=se_fields))

    min_qc = int(s8812.get("when_min_qualifying_children", 999))
    qc_path = s8812.get("qualifying_children_path")
    if not isinstance(qc_path, str):
        raise ConfigurationError("structural_mef: schedule_8812.qualifying_children_path required")
    qc = _resolve_int(data, qc_path)

    if qc >= min_qc:
        nr_codes = set(s8812.get("nonrefundable_credit_codes") or [])
        ref_codes = set(s8812.get("refundable_credit_codes") or [])
        ctc_total = sum(c.amount for c in case.credits.credits if c.code in nr_codes)
        actc_total = sum(c.amount for c in case.credits.credits if c.code in ref_codes)
        if ctc_total <= 0 and actc_total <= 0:
            raise ReconciliationError(
                "structural_mef: qualifying children present but no CTC_SYNTH/ACTC_SYNTH credit amounts "
                "(cannot emit IRS1040Schedule8812 without mapped credit totals)"
            )
        el = s8812.get("element_name")
        did = s8812.get("document_id")
        xfn = s8812.get("xml_field_names") or {}
        if not isinstance(el, str) or not isinstance(did, str):
            raise ConfigurationError("structural_mef: schedule_8812 element_name/document_id required")
        f_child = xfn.get("child_count")
        f_ctc = xfn.get("ctc_total")
        f_actc = xfn.get("actc_total")
        if not all(isinstance(x, str) for x in (f_child, f_ctc, f_actc)):
            raise ConfigurationError("structural_mef: schedule_8812.xml_field_names incomplete")
        documents.append(
            StructuralMefDocument(
                element_name=el,
                document_id=did,
                fields={f_child: qc, f_ctc: ctc_total, f_actc: actc_total},
            )
        )

    return StructuralMefPacket(documents=documents)
