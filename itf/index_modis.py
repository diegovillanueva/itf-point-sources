#!/usr/bin/env python3
"""Per-day index of MODIS MYD06_L2 granules: bounding box and minimum solar zenith angle of every granule.

Writes <index_dir>/YYYY/DDD.json with one record per granule: name, lat_min/max, lon_min/max, wrap (crosses the
dateline), sza_min. Existing index files are kept unless --rewrite is given; the index does not depend on the box.

Usage: python -m itf.index_modis --year 2008 --month 1 [--day 1] --archive <MODIS_ARCHIVE> --index-dir <dir>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np


def granule_record(path: Path) -> dict | None:
    """Read the 5 km geolocation and solar zenith of one granule; None when the file is unreadable."""
    from pyhdf.SD import SD, SDC

    try:
        f = SD(str(path), SDC.READ)
    except Exception as e:  # noqa: BLE001
        print(f"warning: {path.name}: {e}", file=sys.stderr)
        return None
    try:
        lat = f.select("Latitude").get().astype("f8")
        lon = f.select("Longitude").get().astype("f8")
        sza_sds = f.select("Solar_Zenith")
        a = sza_sds.attributes()
        raw = sza_sds.get()
        sza = (raw.astype("f8") - float(a.get("add_offset", 0.0))) * float(a.get("scale_factor", 1.0))
        sza[raw == a.get("_FillValue", -32768)] = np.nan
    finally:
        f.end()
    ok = (lat >= -90) & (lat <= 90) & (lon >= -180) & (lon <= 180)
    if not ok.any():
        return None
    lat, lon = lat[ok], lon[ok]
    wrap = bool(lon.max() - lon.min() > 180.0)   # granule straddles the dateline: treated as covering all longitudes
    return {"name": path.name, "lat_min": float(lat.min()), "lat_max": float(lat.max()),
            "lon_min": float(lon.min()), "lon_max": float(lon.max()), "wrap": wrap,
            "sza_min": float(np.nanmin(sza)) if np.isfinite(sza).any() else None}


def index_day(date: dt.date, archive: Path, index_dir: Path, nproc: int, rewrite: bool) -> Path | None:
    """Build (or reuse) the index of one UTC day; returns the JSON path or None when no granules exist."""
    doy = f"{date:%j}"
    out = index_dir / f"{date:%Y}" / f"{doy}.json"
    if out.exists() and not rewrite:
        return out
    gdir = archive / f"{date:%Y}" / doy / "MYD06_L2" / f"{date:%Y}" / doy
    files = sorted(gdir.glob("MYD06_L2.*.hdf"))
    if not files:
        print(f"warning: {date}: no granules under {gdir}", file=sys.stderr)
        return None
    if nproc <= 1:
        recs = [r for r in map(granule_record, files) if r]
    else:
        with mp.Pool(nproc) as pool:
            recs = [r for r in pool.map(granule_record, files, chunksize=4) if r]
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(".part.json")
    part.write_text(json.dumps({"date": date.isoformat(), "n_files": len(files), "granules": recs}, indent=0))
    part.rename(out)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--month", type=int, required=True)
    p.add_argument("--day", type=int)
    p.add_argument("--archive", type=Path, required=True, help="MODIS_ARCHIVE root (YYYY/DDD/MYD06_L2/YYYY/DDD/*.hdf)")
    p.add_argument("--index-dir", type=Path, required=True)
    p.add_argument("--nproc", type=int, default=2)
    p.add_argument("--rewrite", action="store_true")
    a = p.parse_args()
    first = dt.date(a.year, a.month, a.day or 1)
    last = first if a.day else (dt.date(a.year + (a.month == 12), a.month % 12 + 1, 1) - dt.timedelta(days=1))
    d = first
    while d <= last:
        out = index_day(d, a.archive, a.index_dir, a.nproc, a.rewrite)
        if out:
            print(out)
        d += dt.timedelta(days=1)


if __name__ == "__main__":
    main()
