#!/usr/bin/env python3
"""Aggregate daily itf_day.py files of one year: monthly time series (MM.nc) and the yearly sum (YYYY.nc).

Usage: python -m itf.itf_agg --in-dir <daily/<box>/YYYY> --out-dir <lane/<box>> --year YYYY
Counts (and cot_sum) are summed, never averaged; itf = n_ice / (n_ice + n_liq) of the summed counts (same for itf_op).
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import netCDF4 as nc
import numpy as np


def copy_coords(src: nc.Dataset, out: nc.Dataset) -> None:
    """Copy dimensions, coordinate variables and global attributes; time stays unlimited."""
    for name, dim in src.dimensions.items():
        out.createDimension(name, None if name == "time" else len(dim))
    for name in ("lat", "lon", "cosp_ht", "ctt_bnds"):
        v = src[name]
        o = out.createVariable(name, v.dtype, v.dimensions)
        o[:] = v[:]
        for a in v.ncattrs():
            setattr(o, a, getattr(v, a))
    t = out.createVariable("time", "f8", ("time",))
    for a in src["time"].ncattrs():
        setattr(t, a, getattr(src["time"], a))
    for a in src.ncattrs():
        if a not in ("date", "sources", "candidate_granules", "history"):
            setattr(out, a, getattr(src, a))


def write(path: Path, src: nc.Dataset, times: np.ndarray, counts: dict[str, np.ndarray], n_days: int, dates: str) -> None:
    """Write summed or concatenated counts and the derived itf fields."""
    part = path.with_suffix(".part.nc")
    with nc.Dataset(part, "w", format="NETCDF4") as out:
        copy_coords(src, out)
        out["time"][:] = times
        for name, arr in counts.items():
            dims = src[name].dimensions
            kind = "f4" if arr.dtype.kind == "f" else "i4"   # cot_sum is a float sum
            v = out.createVariable(name, kind, dims, zlib=True, complevel=4, fill_value=np.float32(-999.0) if kind == "f4" else -1)
            v[:] = arr
            v.units = "1"
            v.long_name = getattr(src[name], "long_name", name)
        for itf, ice, liq in (("itf", "n_ice", "n_liq"), ("itf_op", "n_ice_op", "n_liq_op")):
            if ice not in counts:
                continue
            n_ice, n_liq = counts[ice], counts[liq]
            if itf == "itf" and "n_mix" in counts:   # the mixed phase joins the side named by the mixed_as attribute
                if getattr(src, "mixed_as", "liquid") == "liquid":
                    n_liq = n_liq + counts["n_mix"]
                else:
                    n_ice = n_ice + counts["n_mix"]
            den = n_ice + n_liq
            with np.errstate(invalid="ignore", divide="ignore"):
                val = np.where(den > 0, n_ice / np.where(den > 0, den, 1), -999.0).astype("f4")
            v = out.createVariable(itf, "f4", src[itf].dimensions, zlib=True, complevel=4, fill_value=np.float32(-999.0))
            v[:] = val
            v.units = "1"
            v.long_name = getattr(src[itf], "long_name", itf)
        out.n_days = n_days
        out.dates = dates
        out.history = f"{time.strftime('%Y-%m-%d %H:%M:%S')}: itf_agg.py"
    part.rename(path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--year", type=int, required=True)
    a = p.parse_args()
    files = sorted(a.in_dir.glob("[0-9][0-9]/[0-9][0-9].nc"))
    if not files:
        raise SystemExit(f"no daily files under {a.in_dir}")
    out_year = a.out_dir / f"{a.year}"
    out_year.mkdir(parents=True, exist_ok=True)
    with nc.Dataset(files[0]) as d:
        names = [n for n, v in d.variables.items() if (v.dtype.kind == "i" or n == "cot_sum") and v.ndim >= 3]
    year_sum: dict[str, np.ndarray] = {}
    n_year = 0
    for month in sorted({f.parent.name for f in files}):
        mfiles = [f for f in files if f.parent.name == month]
        stack = {n: [] for n in names}
        times = []
        for f in mfiles:
            with nc.Dataset(f) as d:
                times.append(float(d["time"][0]))
                for n in names:
                    stack[n].append(np.ma.filled(d[n][:], 0))
        counts = {n: np.concatenate(stack[n], axis=0) for n in names}
        with nc.Dataset(mfiles[0]) as src:
            write(out_year / f"{month}.nc", src, np.array(times), counts, len(mfiles), f"{mfiles[0].stem}..{mfiles[-1].stem}")
        print(out_year / f"{month}.nc")
        for n in names:
            s = counts[n].sum(axis=0, keepdims=True)
            year_sum[n] = s if n not in year_sum else year_sum[n] + s
        n_year += len(mfiles)
    with nc.Dataset(files[0]) as src:
        mid = (dt.date(a.year, 7, 1) - dt.date(1970, 1, 1)).days
        write(a.out_dir / f"{a.year}.nc", src, np.array([mid], "f8"), year_sum, n_year,
              f"{files[0].parent.name}/{files[0].stem}..{files[-1].parent.name}/{files[-1].stem}")
    print(a.out_dir / f"{a.year}.nc")


if __name__ == "__main__":
    main()
