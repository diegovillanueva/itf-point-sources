"""Cloud-top temperature (CTT) bins: 40 bins of 3 K from -93 to 27 degC.

The edges are built in K with two-decimal rounding and compared in float32, so a CTT exactly on an
edge belongs to no bin. This reproduces the binning of the original cdo-based pipeline exactly.
"""
from __future__ import annotations

import numpy as np

CENTERS = np.arange(-91.5, 26.0, 3.0)   # 40 bin centres in degC


def edges_kelvin() -> np.ndarray:
    """Bin edges in K (41 values), rounded to two decimals."""
    lows = [float(f"{float(f'{c - 1.5:.1f}') + 273.15:.2f}") for c in CENTERS]
    ups = [float(f"{float(f'{c + 1.5:.1f}') + 273.15:.2f}") for c in CENTERS]
    assert all(abs(u - lo) < 1e-9 for u, lo in zip(ups[:-1], lows[1:]))
    return np.array(lows + [ups[-1]], dtype="f8")


def bin_index(ctt: np.ndarray) -> np.ndarray:
    """Bin index 0..39 per element of ctt [K]; -1 where missing, outside the range or exactly on an edge."""
    edges = edges_kelvin().astype("f4")
    c = ctt.astype("f4")
    idx = np.searchsorted(edges, c, side="right") - 1
    bad = ~np.isfinite(c) | (idx < 0) | (idx >= len(CENTERS)) | np.isin(c, edges)
    idx[bad] = -1
    return idx
