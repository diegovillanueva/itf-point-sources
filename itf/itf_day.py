#!/usr/bin/env python3
"""One day of ITF counts, (time, lat, lon, ctt), for a lat/lon box on the 0.05 degree grid.

Per 0.05 degree cell and 3 K CTT bin (itf/ctt_bins.py) the output stores integer pixel counts n_liq, n_ice,
n_und (phase undetermined), n_mix (MODIS infrared mixed phase), n_ctt (any valid CTT) and n_obs (observed pixels
per cell); itf = n_ice / (n_ice + n_liq) is derived. For products with a cloud optical thickness, cot_sum and
n_cot are added. Counts add up losslessly over days (itf_agg.py) and years (itf_pool.py).

Products: cci (Cloud_cci v3 L3U subsets, native 0.05 degree), clara (CLARA-A3 level-2b, native 0.05 degree),
modis (MYD06_L2 1 km pixels counted into the 0.05 degree cells, daytime only, infrared phase),
modis5 (MYD06_L2 5 km infrared phase on its own geolocation).

Usage: python -m itf.itf_day --product cci --date 2008-01-01 --box 54.75,56.75,36.62,38.62 --box-name moscow
           --out <file.nc> --cci-archive <CCI_S1_ARCHIVE>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import netCDF4 as nc
import numpy as np

from .ctt_bins import CENTERS, bin_index, edges_kelvin
from .modis_geo import NLAT, NLON, RES, SZA_MAX, geolocate_1km, scaled, upsample_5km

NB = len(CENTERS)
NOBS, CLEAR, LIQ, ICE, UND, MIX = -1, 0, 1, 2, 3, 4   # internal phase codes
COUNTS = ("n_liq", "n_ice", "n_und", "n_mix", "n_ctt")
PHASE_RULE = {
    "cci": "cvf_liq==1 -> liquid, cvf_ice==1 -> ice, both 0 -> clear, fill -> not observed; ascending (afternoon) node only; "
           "no illumination or quality flags are applied",
    "clara": "cph_asc 1 -> liquid, 2 -> ice (both only where cma_asc==1), 0 -> clear, fill -> not observed; ctt_asc; "
             "ascending (afternoon) node only",
    "modis": "Cloud_Phase_Infrared_1km 1 -> liquid (n_liq), 3 -> mixed (n_mix, counted as {mixed} in itf), 2 -> ice, 6 -> undetermined (n_und, excluded from "
             "itf), 0 -> clear, fill -> not observed; daytime pixels only (Cloud_Mask_1km byte 0 bit 3 set and solar zenith "
             "< 81.36 deg) with a determined cloud mask (bit 0); ctt = cloud_top_temperature_1km; itf_op (diagnostic): "
             "Cloud_Phase_Optical_Properties 2 -> liquid, 3 -> ice, 4 -> undetermined",
    "modis5": "Cloud_Phase_Infrared (5 km) 1 -> liquid (n_liq), 3 -> mixed (n_mix, counted as {mixed} in itf), 2 -> ice, "
              "6 -> undetermined (n_und, excluded from itf), 0 -> clear, fill -> not observed; daytime 5 km pixels only "
              "(Cloud_Mask_5km byte 0 bit 3 set and Solar_Zenith < 81.36 deg) with a determined cloud mask (bit 0); "
              "ctt = Cloud_Top_Temperature (5 km); 5 km Latitude/Longitude used directly; no optical phase at 5 km",
}


def box_slices(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """Index ranges (i0, i1, j0, j1) of the 0.05 degree cells whose centres lie inside (lat_min, lat_max, lon_min, lon_max)."""
    la0, la1, lo0, lo1 = box
    i0 = int(np.ceil((la0 + 90.0) / RES - 0.5))
    i1 = int(np.floor((la1 + 90.0) / RES - 0.5)) + 1
    j0 = int(np.ceil((lo0 + 180.0) / RES - 0.5))
    j1 = int(np.floor((lo1 + 180.0) / RES - 0.5)) + 1
    if not (0 <= i0 < i1 <= NLAT and 0 <= j0 < j1 <= NLON):
        raise SystemExit(f"box {box} gives no cells")
    return i0, i1, j0, j1


def count(cell: np.ndarray, phase: np.ndarray, ctt: np.ndarray, shape: tuple[int, int], cot: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Pixel counts per (lat, lon, bin) and observed pixels per (lat, lon); with cot also the COT sum and n_cot."""
    ny, nx = shape
    ncell = ny * nx
    k = bin_index(ctt.astype("f4"))
    inb = k >= 0
    out = {}
    for name, sel in (("n_liq", phase == LIQ), ("n_ice", phase == ICE), ("n_und", phase == UND), ("n_mix", phase == MIX),
                      ("n_ctt", phase >= NOBS)):
        s = sel & inb
        out[name] = np.bincount(cell[s] * NB + k[s], minlength=ncell * NB).astype("i4").reshape(ny, nx, NB)
    out["n_obs"] = np.bincount(cell[phase >= CLEAR], minlength=ncell).astype("i4").reshape(ny, nx)
    if cot is not None:   # cloud optical thickness of phase-determined pixels per CTT bin
        s = inb & np.isin(phase, (LIQ, ICE, MIX)) & np.isfinite(cot)
        out["n_cot"] = np.bincount(cell[s] * NB + k[s], minlength=ncell * NB).astype("i4").reshape(ny, nx, NB)
        out["cot_sum"] = np.bincount(cell[s] * NB + k[s], weights=cot[s], minlength=ncell * NB).astype("f4").reshape(ny, nx, NB)
    return out


def itf_of(n_ice: np.ndarray, n_liq: np.ndarray) -> np.ndarray:
    """Ice fraction of the phase-determined pixels, NaN where there are none."""
    den = n_ice + n_liq
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, n_ice / np.where(den > 0, den, 1), np.nan).astype("f4")


def read_cci(date: dt.date, sl: tuple[int, int, int, int], archive: Path) -> dict | None:
    """Hyperslab of the Cloud_cci subsets (extensive: cvf_liq, cvf_ice; intensive: ctt, cot) of one day."""
    i0, i1, j0, j1 = sl
    pat = f"{date:%Y%m%d}-ESACCI-L3U_CLOUD-CLD_PRODUCTS-AVHRR_*-fv3.0.nc"
    ext = sorted((archive / "extensive" / f"{date:%Y/%m}").glob(pat))
    inten = sorted((archive / "intensive" / f"{date:%Y/%m}").glob(pat))
    if not ext or not inten:
        return None
    with nc.Dataset(ext[0]) as e, nc.Dataset(inten[0]) as i:
        liq = np.ma.filled(e["cvf_liq"][0, i0:i1, j0:j1].astype("f4"), np.nan)
        ice = np.ma.filled(e["cvf_ice"][0, i0:i1, j0:j1].astype("f4"), np.nan)
        ctt = np.ma.filled(i["ctt"][0, i0:i1, j0:j1].astype("f4"), np.nan)
        cot = np.ma.filled(i["cot"][0, i0:i1, j0:j1].astype("f4"), np.nan)
    phase = np.full(liq.shape, NOBS, "i1")
    phase[np.isfinite(liq) | np.isfinite(ice)] = CLEAR
    phase[liq == 1] = LIQ
    phase[ice == 1] = ICE
    return {"cell": np.arange(phase.size), "phase": phase.ravel(), "ctt": ctt.ravel(), "cot": cot.ravel(),
            "sources": [ext[0].name, inten[0].name]}


def read_clara(date: dt.date, sl: tuple[int, int, int, int], mirror: Path) -> dict | None:
    """Hyperslab of the CLARA-A3 level-2b CPH (cph_asc), CTO (ctt_asc) and CMA (cma_asc) files of one day."""
    i0, i1, j0, j1 = sl
    files = {}
    for prod in ("CPH", "CTO", "CMA"):
        hits = sorted((mirror / prod / f"{date:%Y/%m}").glob(f"{prod}in{date:%Y%m%d}*.nc"))
        if not hits:
            return None
        files[prod] = hits[0]
    with nc.Dataset(files["CPH"]) as p, nc.Dataset(files["CTO"]) as t, nc.Dataset(files["CMA"]) as m:
        cph = np.ma.filled(p["cph_asc"][0, i0:i1, j0:j1].astype("i2"), -1)
        ctt = np.ma.filled(t["ctt_asc"][0, i0:i1, j0:j1].astype("f4"), np.nan)
        cma = np.ma.filled(m["cma_asc"][0, i0:i1, j0:j1].astype("i2"), -1)
    phase = np.full(cph.shape, NOBS, "i1")
    phase[cph >= 0] = CLEAR
    phase[(cph == 1) & (cma == 1)] = LIQ
    phase[(cph == 2) & (cma == 1)] = ICE
    return {"cell": np.arange(phase.size), "phase": phase.ravel(), "ctt": ctt.ravel(), "sources": [f.name for f in files.values()]}


def modis_sds(f, res: str) -> dict[str, np.ndarray]:
    """SDS of one open granule at resolution "1km" or "5km"."""
    sza = scaled(f.select("Solar_Zenith"))
    lat, lon = scaled(f.select("Latitude")), scaled(f.select("Longitude"))
    if res == "1km":
        ir = f.select("Cloud_Phase_Infrared_1km").get().astype("i2")
        shape1 = ir.shape
        g = {"ir": ir, "mask0": f.select("Cloud_Mask_1km").get()[:, :, 0].astype("u1"), "sza": upsample_5km(sza, shape1, False)}
        g["lat"], g["lon"] = geolocate_1km(lat, lon, shape1)
        g["ctt"] = scaled(f.select("cloud_top_temperature_1km"))
        g["op"] = f.select("Cloud_Phase_Optical_Properties").get().astype("i2")
        g["cot"] = scaled(f.select("Cloud_Optical_Thickness"))
        return g
    ir = f.select("Cloud_Phase_Infrared").get().astype("i2")   # native 5 km SDS on the 5 km geolocation
    return {"ir": ir, "mask0": f.select("Cloud_Mask_5km").get()[:, :, 0].astype("u1"), "sza": sza, "lat": lat, "lon": lon,
            "ctt": scaled(f.select("Cloud_Top_Temperature")), "op": np.full(ir.shape, -1, "i2")}


def modis_pixels(g: dict[str, np.ndarray], sl: tuple[int, int, int, int], name: str) -> dict | None:
    """Daytime pixels of one granule inside the box: cell, infrared phase, optical phase, ctt (and cot at 1 km)."""
    i0, i1, j0, j1 = sl
    ir, op, lat, lon = g["ir"], g["op"], g["lat"], g["lon"]
    determined = (g["mask0"] & 1) == 1
    day = (g["mask0"] & 8) == 8
    sunlit = day & (g["sza"] < SZA_MAX)
    keep = determined & sunlit & np.isfinite(lat) & np.isfinite(lon) & (ir != 127)
    if not keep.any():
        return None
    i = np.floor((lat[keep] + 90.0) / RES).astype("i8")
    j = np.floor((lon[keep] + 180.0) / RES).astype("i8") % NLON
    inside = (i >= i0) & (i < i1) & (j >= j0) & (j < j1)
    if not inside.any():
        return None
    cell = ((i - i0) * (j1 - j0) + (j - j0))[inside]
    irk, opk = ir[keep][inside], op[keep][inside]
    phase = np.full(irk.shape, NOBS, "i1")
    phase[irk == 0] = CLEAR
    phase[irk == 1] = LIQ
    phase[irk == 3] = MIX
    phase[irk == 2] = ICE
    phase[irk == 6] = UND
    phase_op = np.full(opk.shape, NOBS, "i1")
    phase_op[opk == 1] = CLEAR
    phase_op[opk == 2] = LIQ
    phase_op[opk == 3] = ICE
    phase_op[opk == 4] = UND
    out = {"cell": cell, "phase": phase, "phase_op": phase_op, "ctt": g["ctt"][keep][inside], "name": name}
    if "cot" in g:
        out["cot"] = g["cot"][keep][inside]
    return out


def modis_granule(path: Path, sl: tuple[int, int, int, int], res: str) -> dict | None:
    """Pixels of one granule inside the box; None when the file is unreadable."""
    from pyhdf.SD import SD, SDC

    try:
        f = SD(str(path), SDC.READ)
    except Exception as e:  # noqa: BLE001  corrupt granule: skipped and reported
        print(f"warning: {path.name}: {e}", file=sys.stderr)
        return None
    try:
        sds = modis_sds(f, res)
    finally:
        f.end()
    return modis_pixels(sds, sl, path.name)


def read_modis(date: dt.date, sl: tuple[int, int, int, int], box: tuple[float, float, float, float],
               archive: Path, index_dir: Path, res: str) -> dict | None:
    """Pixels of every granule whose bounding box intersects the box (from the day index of index_modis.py)."""
    idx = index_dir / f"{date:%Y}" / f"{date:%j}.json"
    if not idx.exists():
        print(f"warning: {date}: index {idx} missing (run index_modis.py first)", file=sys.stderr)
        return None
    la0, la1, lo0, lo1 = box
    gdir = archive / f"{date:%Y}" / f"{date:%j}" / "MYD06_L2" / f"{date:%Y}" / f"{date:%j}"
    parts, candidates = [], []
    for g in json.loads(idx.read_text())["granules"]:
        if g["lat_max"] < la0 or g["lat_min"] > la1:
            continue
        if not g["wrap"] and (g["lon_max"] < lo0 or g["lon_min"] > lo1):
            continue
        if g["sza_min"] is None or g["sza_min"] >= SZA_MAX:   # no daytime pixel in the granule
            continue
        candidates.append(g["name"])
        part = modis_granule(gdir / g["name"], sl, res)
        if part:
            parts.append(part)
    if not parts:
        return {"cell": np.zeros(0, "i8"), "phase": np.zeros(0, "i1"), "phase_op": np.zeros(0, "i1"),
                "ctt": np.zeros(0, "f4"), "sources": [], "candidates": candidates}
    keys = ("cell", "phase", "phase_op", "ctt") + (("cot",) if "cot" in parts[0] else ())
    out = {k: np.concatenate([p[k] for p in parts]) for k in keys}
    out["sources"] = [p["name"] for p in parts]
    out["candidates"] = candidates
    return out


def write_itf(path: Path, date: dt.date, lat: np.ndarray, lon: np.ndarray, fields: dict[str, np.ndarray],
              attrs: dict[str, str]) -> None:
    """Write (time, lat, lon, cosp_ht) int32 counts plus derived float itf fields; .part.nc then renamed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part.nc")
    edges = edges_kelvin()
    with nc.Dataset(part, "w", format="NETCDF4") as out:
        out.createDimension("time", None)
        out.createDimension("lat", len(lat))
        out.createDimension("lon", len(lon))
        out.createDimension("cosp_ht", NB)
        out.createDimension("bnds", 2)
        t = out.createVariable("time", "f8", ("time",))
        t.units = "days since 1970-01-01 00:00:00"
        t.calendar = "standard"
        t.axis = "T"
        t[:] = [(date - dt.date(1970, 1, 1)).days]
        v = out.createVariable("lat", "f8", ("lat",))
        v[:] = lat
        v.units = "degrees_north"
        v.standard_name = "latitude"
        v.axis = "Y"
        v = out.createVariable("lon", "f8", ("lon",))
        v[:] = lon
        v.units = "degrees_east"
        v.standard_name = "longitude"
        v.axis = "X"
        v = out.createVariable("cosp_ht", "f8", ("cosp_ht",))
        v[:] = CENTERS
        v.long_name = "cloud top temperature bin centre"
        v.units = "degC"
        v.bounds = "ctt_bnds"
        v = out.createVariable("ctt_bnds", "f8", ("cosp_ht", "bnds"))
        v[:] = np.column_stack([edges[:-1], edges[1:]])
        v.units = "K"
        v.comment = "bin edges in K as in itf/ctt_bins.py; a CTT exactly on an edge (float32) is in no bin"
        for name, arr in fields.items():
            if arr.dtype.kind == "i":
                dims = ("time", "lat", "lon", "cosp_ht") if arr.ndim == 3 else ("time", "lat", "lon")
                v = out.createVariable(name, "i4", dims, zlib=True, complevel=4, fill_value=-1)
                v[0] = arr
                v.units = "1"
            else:
                v = out.createVariable(name, "f4", ("time", "lat", "lon", "cosp_ht"), zlib=True, complevel=4, fill_value=np.float32(-999.0))
                v[0] = np.where(np.isfinite(arr), arr, -999.0).astype("f4")
                v.units = "1"
        out["n_liq"].long_name = "liquid-phase pixels per CTT bin"
        out["n_ice"].long_name = "ice-phase pixels per CTT bin"
        out["n_und"].long_name = "cloudy pixels with undetermined phase per CTT bin"
        out["n_mix"].long_name = "mixed-phase pixels per CTT bin (MODIS IR phase 3; zero for cci/clara); counted in itf as attribute mixed_as"
        out["n_ctt"].long_name = "pixels with a valid CTT per CTT bin (any phase)"
        if "cot_sum" in out.variables:
            out["n_cot"].long_name = "phase-determined pixels with a valid cloud optical thickness per CTT bin"
            out["cot_sum"].long_name = "sum of cloud optical thickness over n_cot pixels per CTT bin (mean COT = cot_sum / n_cot)"
        out["n_obs"].long_name = "observed pixels per cell (any phase, any CTT)"
        out["itf"].long_name = "ice fraction n_ice / (n_ice + n_liq) per CTT bin"
        if "itf_op" in out.variables:
            out["itf_op"].long_name = "diagnostic ice fraction from the MODIS optical-properties phase (daytime)"
            out["n_liq_op"].long_name = "liquid-phase pixels per CTT bin, MODIS optical-properties phase (diagnostic)"
            out["n_ice_op"].long_name = "ice-phase pixels per CTT bin, MODIS optical-properties phase (diagnostic)"
        for k, val in attrs.items():
            setattr(out, k, val)
        out.history = f"{time.strftime('%Y-%m-%d %H:%M:%S')}: itf_day.py"
        out.Conventions = "CF-1.8"
    part.rename(path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--product", choices=("cci", "clara", "modis", "modis5"), required=True)
    p.add_argument("--date", type=dt.date.fromisoformat, required=True)
    p.add_argument("--box", required=True, help="lat_min,lat_max,lon_min,lon_max")
    p.add_argument("--box-name", default="box")
    p.add_argument("--out", type=Path, required=True, help="output file")
    p.add_argument("--cci-archive", type=Path, help="CCI_S1_ARCHIVE (extensive/, intensive/)")
    p.add_argument("--clara-mirror", type=Path, help="CLARA_MIRROR (CPH/, CTO/, CMA/)")
    p.add_argument("--modis-archive", type=Path, help="MODIS_ARCHIVE")
    p.add_argument("--modis-index", type=Path, help="index directory written by index_modis.py")
    p.add_argument("--mixed", choices=("liquid", "ice"), default="liquid", help="MODIS IR mixed phase counts as (default liquid)")
    a = p.parse_args()
    t0 = time.time()
    box = tuple(float(x) for x in a.box.split(","))
    sl = box_slices(box)
    i0, i1, j0, j1 = sl
    lat = -90.0 + RES * (np.arange(i0, i1) + 0.5)
    lon = -180.0 + RES * (np.arange(j0, j1) + 0.5)
    shape = (i1 - i0, j1 - j0)
    if a.product == "cci":
        d = read_cci(a.date, sl, a.cci_archive)
    elif a.product == "clara":
        d = read_clara(a.date, sl, a.clara_mirror)
    else:
        d = read_modis(a.date, sl, box, a.modis_archive, a.modis_index, "1km" if a.product == "modis" else "5km")
    if d is None:
        print(f"warning: {a.product} {a.date}: no input, nothing written", file=sys.stderr)
        return
    fields = count(d["cell"], d["phase"], d["ctt"], shape, d.get("cot"))
    if a.mixed == "liquid":   # n_mix is only non-zero for MODIS; it joins the liquid or the ice side of itf
        fields["itf"] = itf_of(fields["n_ice"], fields["n_liq"] + fields["n_mix"])
    else:
        fields["itf"] = itf_of(fields["n_ice"] + fields["n_mix"], fields["n_liq"])
    attrs = {"product": a.product, "date": a.date.isoformat(), "box": a.box, "box_name": a.box_name,
             "phase_rule": PHASE_RULE[a.product].format(mixed=a.mixed), "sources": " ".join(d["sources"]),
             "mixed_as": a.mixed, "title": f"ITF(ctt) counts, {a.product}, {a.box_name}, {a.date}"}
    if a.product == "modis":
        op = count(d["cell"], d["phase_op"], d["ctt"], shape)
        fields["n_liq_op"], fields["n_ice_op"] = op["n_liq"], op["n_ice"]
        fields["itf_op"] = itf_of(op["n_ice"], op["n_liq"])
    if a.product in ("modis", "modis5"):
        attrs["candidate_granules"] = " ".join(d["candidates"])
    write_itf(a.out, a.date, lat, lon, fields, attrs)
    print(a.out)
    print(f"done {a.product} {a.date}: n_obs {int(fields['n_obs'].sum())}, liq {int(fields['n_liq'].sum())}, "
          f"ice {int(fields['n_ice'].sum())}, mix {int(fields['n_mix'].sum())}, und {int(fields['n_und'].sum())} "
          f"in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
