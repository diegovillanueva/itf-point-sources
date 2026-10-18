"""Grid constants and MODIS MYD06_L2 helpers: SDS scaling and 5 km to 1 km geolocation."""
from __future__ import annotations

import numpy as np

NLAT, NLON, RES = 3600, 7200, 0.05   # global 0.05 degree grid (Cloud_cci L3U and CLARA level-2b layout)
SZA_MAX = 81.36                      # MODIS daytime retrieval limit, solar zenith angle [deg]


def scaled(sds, fill_to_nan: bool = True) -> np.ndarray:
    """Read an SDS and apply value = scale_factor * (stored - add_offset); fill values become NaN."""
    a = sds.attributes()
    raw = sds.get()
    out = (raw.astype("f8") - float(a.get("add_offset", 0.0))) * float(a.get("scale_factor", 1.0))
    if fill_to_nan and "_FillValue" in a:
        out[raw == a["_FillValue"]] = np.nan
    return out.astype("f4")


def upsample_5km(field5: np.ndarray, shape1: tuple[int, int], linear: bool) -> np.ndarray:
    """5 km field to 1 km: sample (i, j) sits at 1 km (5i+2, 5j+2); bilinear with edge extrapolation, or nearest."""
    n5r, n5c = field5.shape
    r5 = (np.arange(shape1[0]) - 2) / 5.0
    c5 = (np.arange(shape1[1]) - 2) / 5.0
    if not linear:
        return field5[np.ix_(np.clip(np.rint(r5), 0, n5r - 1).astype("i8"), np.clip(np.rint(c5), 0, n5c - 1).astype("i8"))]
    i0 = np.clip(np.floor(r5), 0, n5r - 2).astype("i8")
    fr = (r5 - i0)[:, None]
    j0 = np.clip(np.floor(c5), 0, n5c - 2).astype("i8")
    fc = (c5 - j0)[None, :]
    f = field5.astype("f8")
    top = f[i0][:, j0] * (1 - fc) + f[i0][:, j0 + 1] * fc
    bot = f[i0 + 1][:, j0] * (1 - fc) + f[i0 + 1][:, j0 + 1] * fc
    return top * (1 - fr) + bot * fr


def geolocate_1km(lat5: np.ndarray, lon5: np.ndarray, shape1: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate 5 km latitude/longitude to 1 km through unit vectors (dateline and pole safe)."""
    phi = np.deg2rad(lat5.astype("f8"))
    lam = np.deg2rad(lon5.astype("f8"))
    x = upsample_5km(np.cos(phi) * np.cos(lam), shape1, True)
    y = upsample_5km(np.cos(phi) * np.sin(lam), shape1, True)
    z = upsample_5km(np.sin(phi), shape1, True)
    lat = np.rad2deg(np.arctan2(z, np.hypot(x, y)))
    lon = np.rad2deg(np.arctan2(y, x))
    bad = ~np.isfinite(lat5) | ~np.isfinite(lon5)
    if bad.any():   # a fill value in the 5 km geolocation invalidates its 5 x 5 neighbourhood
        lat[upsample_5km(bad.astype("f4"), shape1, False) > 0] = np.nan
    return lat, lon
