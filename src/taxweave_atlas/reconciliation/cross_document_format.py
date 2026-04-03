"""Human-readable cross-document consistency violation messages."""

from __future__ import annotations


def format_cross_document_mismatch(
    *,
    check_id: str,
    left_document: str,
    right_document: str,
    left_field: str,
    right_field: str,
    left_value: object,
    right_value: object,
    tolerance_note: str = "",
) -> str:
    """Multi-line message: which documents/fields differ and expected equality rule."""
    tail = f"\n  Tolerance: {tolerance_note}" if tolerance_note else ""
    return (
        f"Cross-document consistency failed [{check_id}]\n"
        f"  Left document:  {left_document}\n"
        f"    Field: {left_field}\n"
        f"    Value: {left_value!r}\n"
        f"  Right document: {right_document}\n"
        f"    Field: {right_field}\n"
        f"    Value: {right_value!r}\n"
        f"  Expected: reconciled values must align within the stated tolerance.{tail}"
    )
