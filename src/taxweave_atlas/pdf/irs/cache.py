from __future__ import annotations

import os
import urllib.error
import urllib.request
from functools import lru_cache

from taxweave_atlas.exceptions import RendererError
from taxweave_atlas.paths import irs_template_cache_dir


def _template_year(case_year: int) -> int:
    """IRS prior-year URLs are maintained for recent years; snap to supported window."""
    if case_year >= 2024:
        return min(case_year, 2025)
    if case_year <= 2022:
        return 2023
    return case_year


@lru_cache(maxsize=32)
def get_irs_prior_pdf_bytes(*, slug: str, year: int) -> bytes:
    """
    Load an IRS ``irs-prior`` fillable PDF (cached on disk).

    ``slug`` is the basename without year suffix (e.g. ``f1040``, ``f1040sb``).
    """
    y = _template_year(year)
    url = f"https://www.irs.gov/pub/irs-prior/{slug}--{y}.pdf"
    cache_root = irs_template_cache_dir()
    cache_path = cache_root / str(y) / f"{slug}--{y}.pdf"
    if cache_path.is_file():
        return cache_path.read_bytes()

    if os.environ.get("TAXWEAVE_IRS_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        raise RendererError(
            f"IRS template missing at {cache_path} and TAXWEAVE_IRS_OFFLINE is set (slug={slug!r} year={y})"
        )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TaxWeaveAtlas/0.1 (template fetch)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except (OSError, urllib.error.URLError) as e:
        raise RendererError(f"IRS template download failed {url!r}: {e}") from e

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
    except OSError:
        pass
    return data
