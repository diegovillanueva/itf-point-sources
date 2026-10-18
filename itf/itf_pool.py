#!/usr/bin/env python3
"""Pool itf_agg.py output over several years: <a>-<b>.nc (sum of the yearly files) and <a>-<b>/MM.nc
(each calendar month summed over the years).

Usage: python -m itf.itf_pool --agg-dir <lane/<box>> --years 1982 2016
Counts are summed over all days of all years (occurrence weighting); itf is recomputed from the pooled counts.
cot_sum and n_cot are kept only if every pooled file has them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import netCDF4 as nc
import numpy as np

from .itf_agg import write


def pool(files: list[Path], out: Path) -> None:
    """Sum the count variables of files over time and years into one time step."""
    with nc.Dataset(files[0]) as d:
        names = [n for n, v in d.variables.items() if (v.dtype.kind == "i" or n == "cot_sum") and v.ndim >= 3]
    tot: dict[str, np.ndarray] = {}
    for f in files:
        with nc.Dataset(f) as d:
            names = [n for n in names if n in d.variables]
            for n in names:
                s = np.ma.filled(d[n][:], 0).sum(axis=0, keepdims=True)
                tot[n] = s if n not in tot else tot[n] + s
    tot = {n: v for n, v in tot.items() if n in names}
    with nc.Dataset(files[0]) as src:
        write(out, src, np.array([float(src["time"][0])]), tot, len(files), f"{files[0].parent.name}/{files[0].stem}..{files[-1].parent.name}/{files[-1].stem}")
    print(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agg-dir", type=Path, required=True)
    p.add_argument("--years", type=int, nargs=2, required=True)
    a = p.parse_args()
    tag = f"{a.years[0]}-{a.years[1]}"
    years = [y for y in range(a.years[0], a.years[1] + 1) if (a.agg_dir / f"{y}.nc").exists()]
    if not years:
        raise SystemExit(f"no yearly files {a.years[0]}..{a.years[1]} under {a.agg_dir}")
    print(f"{len(years)} years: {years[0]}..{years[-1]}")
    (a.agg_dir / tag).mkdir(exist_ok=True)
    pool([a.agg_dir / f"{y}.nc" for y in years], a.agg_dir / f"{tag}.nc")
    for m in range(1, 13):
        files = [f for y in years if (f := a.agg_dir / str(y) / f"{m:02d}.nc").exists()]
        if files:
            pool(files, a.agg_dir / tag / f"{m:02d}.nc")


if __name__ == "__main__":
    main()
