#!/usr/bin/env python3
"""Write one synthetic day in the Cloud_cci subset layout read by itf_day.py (used by tests/test_smoke.sh).

Usage: python -m tests.make_synthetic_day --archive <dir> --site moscow --date 2008-01-01 --day-index 0
Creates <archive>/extensive/YYYY/MM/<file> (cvf_liq, cvf_ice) and <archive>/intensive/YYYY/MM/<file> (ctt, cot) on the
full 3600 x 7200 grid, writing only the cells of the site's box (compressed, so the files stay small). Every box cell is
cloudy with ctt = 256.15 K (-17 degC) and cot = 5: cells within 10 km of the site are ice on every day, all other
cells are ice on day index 0 and liquid otherwise. Over three days the centre ITF is 1 and every background cell has
ITF 1/3, so plot_itf_change.py must report an ITF change of +200 % (+66.7 percentage points) in the -12..-24 degC range.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import netCDF4 as nc
import numpy as np

from itf.itf_day import box_slices
from itf.modis_geo import NLAT, NLON, RES
from itf.plot_itf_change import distance_km
from itf.sites import SITES, site_box

CTT_K = 256.15
COT = 5.0


def write(path: Path, fields: dict[str, np.ndarray], sl: tuple[int, int, int, int]) -> None:
    i0, i1, j0, j1 = sl
    path.parent.mkdir(parents=True, exist_ok=True)
    with nc.Dataset(path, "w", format="NETCDF4") as out:
        out.createDimension("time", 1)
        out.createDimension("lat", NLAT)
        out.createDimension("lon", NLON)
        v = out.createVariable("lat", "f8", ("lat",))
        v[:] = -90.0 + RES * (np.arange(NLAT) + 0.5)
        v.units = "degrees_north"
        v = out.createVariable("lon", "f8", ("lon",))
        v[:] = -180.0 + RES * (np.arange(NLON) + 0.5)
        v.units = "degrees_east"
        for name, arr in fields.items():
            v = out.createVariable(name, "f4", ("time", "lat", "lon"), zlib=True, complevel=1, chunksizes=(1, 40, 40),
                                   fill_value=np.float32(np.nan))
            v[0, i0:i1, j0:j1] = arr
        out.title = "synthetic test day"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--site", default="moscow")
    p.add_argument("--date", type=dt.date.fromisoformat, required=True)
    p.add_argument("--day-index", type=int, required=True, help="0: background cells are ice; otherwise liquid")
    a = p.parse_args()
    site = SITES[a.site]
    sl = box_slices(site_box(a.site))
    i0, i1, j0, j1 = sl
    lat = -90.0 + RES * (np.arange(i0, i1) + 0.5)
    lon = -180.0 + RES * (np.arange(j0, j1) + 0.5)
    centre = distance_km(lat, lon, site) <= 10.0
    ice = centre | (a.day_index == 0)
    shape = (i1 - i0, j1 - j0)
    name = f"{a.date:%Y%m%d}-ESACCI-L3U_CLOUD-CLD_PRODUCTS-AVHRR_NOAA-18-fv3.0.nc"
    write(a.archive / "extensive" / f"{a.date:%Y/%m}" / name,
          {"cvf_liq": (~ice).astype("f4"), "cvf_ice": ice.astype("f4")}, sl)
    write(a.archive / "intensive" / f"{a.date:%Y/%m}" / name,
          {"ctt": np.full(shape, CTT_K, "f4"), "cot": np.full(shape, COT, "f4")}, sl)
    print(f"{a.date}: {int(ice.sum())} ice and {int((~ice).sum())} liquid cells, {int(centre.sum())} centre cells")
    print(a.archive / "extensive" / f"{a.date:%Y/%m}" / name)
    print(a.archive / "intensive" / f"{a.date:%Y/%m}" / name)


if __name__ == "__main__":
    main()
