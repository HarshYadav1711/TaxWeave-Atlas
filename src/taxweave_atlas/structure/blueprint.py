"""
Load ``dataset_structure_blueprint.yaml`` and compute expected paths (posix) + generator ids.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import yaml

from taxweave_atlas.exceptions import ConfigurationError
from taxweave_atlas.paths import dataset_structure_blueprint_path
from taxweave_atlas.schema.case import SyntheticTaxCase

_BAD_FILENAME = '<>:"/\\|?*'


def _safe_filename_segment(value: str, max_len: int = 120) -> str:
    s = " ".join(str(value).split())
    for c in _BAD_FILENAME:
        s = s.replace(c, "_")
    return s[:max_len].rstrip(" .") or "SYNTHETIC"


@lru_cache(maxsize=1)
def load_structure_blueprint() -> dict[str, Any]:
    path = dataset_structure_blueprint_path()
    if not path.is_file():
        raise ConfigurationError(f"Missing structure blueprint: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigurationError("dataset_structure_blueprint.yaml must be a mapping")
    if data.get("version") != 1:
        raise ConfigurationError("Unsupported dataset_structure_blueprint.yaml version")
    segs = data.get("segments")
    if not isinstance(segs, list) or not segs:
        raise ConfigurationError("blueprint missing segments")
    return data


def build_layout_context(
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
) -> dict[str, Any]:
    bp = load_structure_blueprint()
    fmt = (bp.get("export_token") or {}).get("format")
    if not isinstance(fmt, str):
        raise ConfigurationError("blueprint.export_token.format missing")
    dataset_slot = dataset_index + 1
    export_token = fmt.format(
        tax_year=case.tax_year,
        dataset_slot=dataset_slot,
        salt=uniqueness_salt,
    )
    return {
        "export_token": export_token,
        "tax_year": case.tax_year,
        "dataset_slot": dataset_slot,
        "salt": uniqueness_salt,
        "primary_last_upper": case.profile.primary_last_name.upper(),
        "safe_taxpayer_label": _safe_filename_segment(case.profile.taxpayer_label),
        "executive_summary_title": _safe_filename_segment(
            f"{case.profile.primary_first_name} {case.profile.primary_last_name}",
            max_len=80,
        ),
    }


def iter_layout_file_specs(
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
) -> list[tuple[str, str]]:
    """
    Return ordered (relative_posix_path, generator_id) for every file in the contract.
    """
    bp = load_structure_blueprint()
    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    out: list[tuple[str, str]] = []

    for seg in bp["segments"]:
        if not isinstance(seg, dict):
            raise ConfigurationError("segment must be a mapping")
        outer = str(seg["outer_template"]).format(**ctx)
        inner = str(seg["inner_template"]).format(**ctx)
        base = f"{outer}/{inner}"

        for entry in seg.get("files") or []:
            if not isinstance(entry, dict):
                raise ConfigurationError("file entry must be a mapping")
            rel = str(entry["relative"]).format(**ctx)
            gen = str(entry["generator"])
            out.append((f"{base}/{rel}", gen))

        for cat in seg.get("categories") or []:
            if not isinstance(cat, dict):
                raise ConfigurationError("category must be a mapping")
            folder = str(cat["folder"])
            for entry in cat.get("files") or []:
                if not isinstance(entry, dict):
                    raise ConfigurationError("category file entry must be a mapping")
                rel = str(entry["relative"]).format(**ctx)
                gen = str(entry["generator"])
                out.append((f"{base}/{folder}/{rel}", gen))

    return out


def iter_export_layout_file_specs(
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
) -> list[tuple[str, str]]:
    """
    Deliverable paths only: PDFs under exported segments (``export: false`` segments skipped).
    Per-file ``export: false`` omits docx/xlsx kept for staging only.
    """
    bp = load_structure_blueprint()
    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    out: list[tuple[str, str]] = []

    for seg in bp["segments"]:
        if not isinstance(seg, dict):
            raise ConfigurationError("segment must be a mapping")
        if seg.get("export", True) is False:
            continue
        outer = str(seg["outer_template"]).format(**ctx)
        inner = str(seg["inner_template"]).format(**ctx)
        base = f"{outer}/{inner}"

        for entry in seg.get("files") or []:
            if not isinstance(entry, dict):
                raise ConfigurationError("file entry must be a mapping")
            if entry.get("export", True) is False:
                continue
            rel = str(entry["relative"]).format(**ctx)
            gen = str(entry["generator"])
            out.append((f"{base}/{rel}", gen))

        for cat in seg.get("categories") or []:
            if not isinstance(cat, dict):
                raise ConfigurationError("category must be a mapping")
            folder = str(cat["folder"])
            for entry in cat.get("files") or []:
                if not isinstance(entry, dict):
                    raise ConfigurationError("category file entry must be a mapping")
                if entry.get("export", True) is False:
                    continue
                rel = str(entry["relative"]).format(**ctx)
                gen = str(entry["generator"])
                out.append((f"{base}/{folder}/{rel}", gen))

    return out


def expected_structure_directories(files: list[str]) -> set[str]:
    """All parent directory paths (posix) implied by file paths, including segment roots."""
    dirs: set[str] = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return dirs


def staging_allowed_root_files() -> frozenset[str]:
    bp = load_structure_blueprint()
    raw = bp.get("staging_root_files") or bp.get("allowed_root_files") or []
    if not isinstance(raw, list):
        raise ConfigurationError("staging_root_files must be a list")
    return frozenset(str(x) for x in raw)


def export_allowed_root_files() -> frozenset[str]:
    bp = load_structure_blueprint()
    raw = bp.get("export_root_files") or []
    if not isinstance(raw, list):
        raise ConfigurationError("export_root_files must be a list")
    return frozenset(str(x) for x in raw)


def parse_dataset_slug_index(slug: str) -> int:
    """``dataset_00001`` → 0-based index."""
    m = re.match(r"^dataset_(\d+)$", slug, re.IGNORECASE)
    if not m:
        raise ConfigurationError(f"Cannot parse dataset index from slug {slug!r}")
    return int(m.group(1), 10) - 1


def expected_root_outer_names(
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
) -> list[str]:
    bp = load_structure_blueprint()
    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    return [str(seg["outer_template"]).format(**ctx) for seg in bp["segments"]]


def expected_export_root_outer_names(
    case: SyntheticTaxCase,
    *,
    dataset_index: int,
    uniqueness_salt: int,
) -> list[str]:
    bp = load_structure_blueprint()
    ctx = build_layout_context(
        case, dataset_index=dataset_index, uniqueness_salt=uniqueness_salt
    )
    names: list[str] = []
    for seg in bp["segments"]:
        if seg.get("export", True) is False:
            continue
        names.append(str(seg["outer_template"]).format(**ctx))
    return names
