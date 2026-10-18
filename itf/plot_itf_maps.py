#!/usr/bin/env python3
"""ITF maps at fixed CTT ranges around a point source, one figure per month (or the year with seasonal rows).

Usage: python -m itf.plot_itf_maps --root <root> --box moscow --year 1982-2016 --months year --lanes cci --out-dir <dir>
Input: <root>/<lane>/<box>/<year>.nc and <root>/<lane>/<box>/<year>/MM.nc (itf_agg.py or itf_pool.py).

Per cell (0.05 degree cells merged --coarsen x --coarsen): ITF = sum(n_ice) / sum(n_ice + n_liq + n_mix) over the
period in each 12 K CTT range (0..-12, -12..-24, -24..-36 degC); cells with fewer than MIN_N phase samples are blank;
titles give the pooled box ITF. The 10 km centre disk and the 70-100 km background ring of plot_itf_change.py are drawn.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np

from .plot_itf_change import LABEL, LANES, TARGETS
from .sites import SITES

MIN_N = 1   # every cell with at least one phase sample is shown
SEASONS = {"DJF": ("12", "01", "02"), "MAM": ("03", "04", "05"), "JJA": ("06", "07", "08"), "SON": ("09", "10", "11")}


def itf_map(path: Path | list[Path], target: tuple[float, float], co: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, int, float]:
    """ITF (cells coarsened co x co) and sample count of the bins inside target."""
    cnt: dict[str, np.ndarray] = {}
    for f in path if isinstance(path, list) else [path]:   # seasons: counts summed over their months
        with nc.Dataset(f) as d:
            c = np.asarray(d["cosp_ht"][:], float)
            k = np.where((c - 1.5 >= target[0]) & (c + 1.5 <= target[1]))[0]
            for n in ("n_ice", "n_liq", "n_mix"):
                if n in d.variables:
                    v = np.ma.filled(d[n][:, :, :, k], 0).sum((0, 3)).astype(float)
                    cnt[n] = cnt.get(n, 0) + v
            lat, lon = np.asarray(d["lat"][:]), np.asarray(d["lon"][:])
    ny, nx = len(lat) // co, len(lon) // co
    cnt = {k2: v[: ny * co, : nx * co].reshape(ny, co, nx, co).sum((1, 3)) for k2, v in cnt.items()}
    lat, lon = lat[: ny * co].reshape(ny, co).mean(1), lon[: nx * co].reshape(nx, co).mean(1)
    n = sum(cnt.values())
    pooled = cnt["n_ice"].sum() / n.sum() if n.sum() else np.nan
    with np.errstate(invalid="ignore", divide="ignore"):
        itf = np.where(n >= MIN_N, cnt["n_ice"] / n, np.nan)
    return lat, lon, itf, f"{target[1]:.0f}…{target[0]:.0f} °C", int(n.sum()), pooled


def month_file(root: Path, lane: str, box: str, year: str, m: str) -> Path | list[Path]:
    """Monthly file, the yearly sum for m == "year", or the month files of a season."""
    base = root / lane / box
    if m in SEASONS:
        return [f for mm in SEASONS[m] if (f := base / str(year) / f"{mm}.nc").exists()]
    return base / f"{year}.nc" if m == "year" else base / str(year) / f"{m}.nc"


def exists(f: Path | list[Path]) -> bool:
    return bool(f) if isinstance(f, list) else f.exists()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, required=True, help="directory holding <lane>/<box>/<year>.nc and <year>/MM.nc")
    p.add_argument("--box", default="moscow")
    p.add_argument("--year", default="2008", help="year or pooled tag, e.g. 1982-2016 (itf_pool.py)")
    p.add_argument("--months", nargs="+", default=["year"], help="months (01..12) or 'year'")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--lanes", nargs="+", default=list(LANES), help="subset of lanes; a subset adds _<lanes> to the file names")
    p.add_argument("--seasons", nargs="*", default=["DJF", "MAM"], help="single lane + month 'year': extra rows with these seasons")
    p.add_argument("--coarsen", type=int, default=1, help="merge co x co 0.05 degree cells (1 = native, 4 = 0.2 degree)")
    a = p.parse_args()
    if a.box not in SITES:
        raise SystemExit(f"unknown site {a.box}; known: {', '.join(SITES)}")
    site = SITES[a.box]
    a.out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 7, "axes.titlesize": 7})
    proj = ccrs.PlateCarree()
    for m in a.months:
        lanes = [ln for ln in a.lanes if exists(month_file(a.root, ln, a.box, a.year, m))]
        if not lanes:
            print(f"warning: no data for {a.box} {a.year} {m}")
            continue
        rows = [(ln, m) for ln in lanes]
        if len(lanes) == 1 and m == "year":   # one lane: year plus seasonal rows
            rows += [(lanes[0], sn) for sn in a.seasons if exists(month_file(a.root, lanes[0], a.box, a.year, sn))]
        fig, axs = plt.subplots(len(rows), len(TARGETS), figsize=(6.6, 2.35 * len(rows)), subplot_kw={"projection": proj}, squeeze=False)
        maps = [[itf_map(month_file(a.root, ln, a.box, a.year, mm), t, a.coarsen) for t in TARGETS] for ln, mm in rows]
        per_col = len(rows) > 1 and len(lanes) == 1   # own colour range per map when only one lane is shown
        for j in range(len(TARGETS)):
            for i, (ln, mm) in enumerate(rows):
                ax = axs[i, j]
                lat, lon, itf, rng, ntot, pooled = maps[i][j]
                vals = itf[np.isfinite(itf)]
                vmin, vmax = np.percentile(vals, (2, 98)) if per_col and vals.size else (0.0, 1.0)
                h = 0.025 * a.coarsen
                lone = np.append(lon - h, lon[-1] + h)   # cell edges
                late = np.append(lat - h, lat[-1] + h)
                pm = ax.pcolormesh(lone, late, itf, vmin=vmin, vmax=vmax, cmap="RdYlBu", shading="flat", transform=proj)
                ax.add_feature(cfeature.BORDERS, lw=0.4)
                ax.add_feature(cfeature.RIVERS, lw=0.3, alpha=0.6)
                for r_km, ls in ((10, "-"), (70, "--"), (100, "--")):   # centre disk and background ring
                    ang = np.linspace(0, 2 * np.pi, 200)
                    ax.plot(site.lon + r_km / (111.2 * np.cos(np.radians(site.lat))) * np.cos(ang), site.lat + r_km / 111.2 * np.sin(ang),
                            color="k", lw=0.5, ls=ls, transform=proj)
                ax.set_extent([lon.min() - h, lon.max() + h, lat.min() - h, lat.max() + h], crs=proj)
                tag_r = "" if mm in ("year", m) and not per_col else f"{'year' if mm == 'year' else mm} · "
                ax.set_title(f"{LABEL[ln]} · {tag_r}CTT {rng}\nbox ITF {pooled:.2f} · n={ntot}")
                if per_col:
                    cb = fig.colorbar(pm, ax=ax, orientation="horizontal", fraction=0.05, pad=0.04, extend="both")
                    cb.ax.tick_params(labelsize=5.5)
        h_in = fig.get_figheight()   # fixed margins in inches so one-row and multi-row figures both fit
        fig.subplots_adjust(hspace=0.6 if per_col else 0.45, bottom=0.75 / h_in, top=1 - 0.75 / h_in)
        if not per_col:
            cax = fig.add_axes([0.2, 0.3 / h_in, 0.6, 0.06 / h_in])
            cb = fig.colorbar(pm, cax=cax, orientation="horizontal")
            cb.set_label("ITF = n_ice / (n_ice + n_liq + n_mix)")
        when = f"{a.year} (year, occurrence-weighted)" if m == "year" else f"{a.year}-{m}"
        fig.suptitle(f"Ice-topped fraction, {when}, 2°×2° box around {site.label} (centre of the 10 km ring), {0.05 * a.coarsen:.2f}° cells", fontsize=8, y=1 - 0.15 / fig.get_figheight())
        tag = "" if list(a.lanes) == list(LANES) else "_" + "-".join(a.lanes)
        out = a.out_dir / f"itf_maps_{a.box}_{a.year}{'' if m == 'year' else m}{tag}.png"
        fig.savefig(out, dpi=200, bbox_inches="tight")
        out.with_suffix(".md").write_text(
            f"Ice-topped fraction ITF = n_ice/(n_ice+n_liq+n_mix) per {0.05 * a.coarsen:.2f}° cell, {when}, summed over all days (year: counts pooled over all months = monthly ITF weighted by cloud occurrence), "
            f"in the 12 K CTT ranges 0…−12, −12…−24 and −24…−36 °C; every cell with ≥ 1 phase sample is shown; titles give the pooled box ITF and sample count. "
            + (f"Rows: year and seasons {', '.join(r[1] for r in rows[1:])} (counts pooled over the season's months); each map has its own colour range = 2–98th percentile of its cells (colour bar below it). " if per_col else "")
            + "Solid circle: 10 km centre disk; dashed circles: 70–100 km background ring of the ITF change. "
            "MODIS: daytime infrared phase (collection 6.1), undetermined pixels excluded.\n")
        plt.close(fig)
        print(out)
        print(out.with_suffix(".md"))


if __name__ == "__main__":
    main()
