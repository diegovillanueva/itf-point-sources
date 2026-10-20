#!/usr/bin/env python3
"""Mean ITF, cloud occurrence and COT versus distance from the site centre, for all sites, in 12 K and native 3 K CTT bins.

Usage: python -m itf.plot_itf_distance --root data --year 1982-2016 --out-dir <dir> [--lane cci] [--sites moscow moscow_ctl] [--ring-km 5] [--variables itf occ cot]
Per distance ring (default 5 km wide, 0-100 km) and CTT bin: ITF = sum n_ice / sum (n_ice + n_liq + n_mix) over all cells of the ring
(occurrence-weighted mean of the pooled counts in <root>/<lane>/<site>/<year>.nc); occ = cloud samples per cell; COT = sum cot_sum / sum n_cot.
The 2° x 2° box reaches only about 60-75 km east/west of the site, so rings beyond that are north and south arcs only.
Writes itf_distance_<year>_<lane>.csv (long format) and per variable <var>_distance_12K_<year>_<lane>.png and <var>_distance_3K_<year>_<lane>.png with .md captions.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np

from .plot_itf_change import LABEL, TARGETS, distance_km
from .sites import SITES, Site

BINS_3K = [(c - 1.5, c + 1.5) for c in np.arange(-1.5, -36, -3.0)]   # native 3 K bins 0..-36 °C
BG_KM = (70.0, 100.0)


VARS = {   # variable: (axis label, change label, change in pp of ITF (True) or relative [%] (False))
    "itf": ("ITF", "ITF - ITF(70-100 km) [pp]", True),
    "occ": ("cloud samples per 0.05° cell", "relative to 70-100 km [%]", False),
    "cot": ("mean COT", "relative to 70-100 km [%]", False),
}


def ring_stats(path: Path, site: Site, ctt: tuple[float, float], edges: np.ndarray) -> dict[str, np.ndarray]:
    """ITF, cloud samples per cell, mean COT, cloud samples and cell count per distance ring for one CTT range (lo, hi) in °C."""
    with nc.Dataset(path) as d:
        c = np.asarray(d["cosp_ht"][:], float)
        k = np.where((c - 1.5 >= ctt[0] - 1e-6) & (c + 1.5 <= ctt[1] + 1e-6))[0]
        cnt = {n: np.ma.filled(d[n][:, :, :, k], 0).sum((0, 3)).astype(float)
               for n in ("n_ice", "n_liq", "n_mix", "n_cot", "cot_sum") if n in d.variables}
        lat, lon = np.asarray(d["lat"][:]), np.asarray(d["lon"][:])
    dist = distance_km(lat, lon, site)
    n = sum(cnt[v] for v in ("n_ice", "n_liq", "n_mix") if v in cnt)
    r = np.digitize(dist, edges) - 1
    ring = lambda a: np.array([a[r == i].sum() for i in range(len(edges) - 1)])  # noqa: E731
    ice, tot, cells = ring(cnt["n_ice"]), ring(n), ring(np.ones_like(n))
    cs, cn = (ring(cnt[v]) if v in cnt else np.zeros(len(edges) - 1) for v in ("cot_sum", "n_cot"))
    with np.errstate(invalid="ignore", divide="ignore"):
        return {"itf": np.where(tot > 0, ice / tot, np.nan), "occ": np.where(cells > 0, tot / cells, np.nan),
                "cot": np.where(cn > 0, cs / cn, np.nan), "tot": tot, "cells": cells}


def main() -> None:
    """CSV plus, per variable, the 12 K figure (value and change vs distance, all sites) and the 3 K figure (one panel per site)."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True, help="root with <lane>/<site>/<year>.nc")
    p.add_argument("--year", default="1982-2016", help="year or pooled tag of itf_pool.py")
    p.add_argument("--lane", default="cci")
    p.add_argument("--sites", nargs="+", default=list(SITES))
    p.add_argument("--ring-km", type=float, default=5.0)
    p.add_argument("--max-km", type=float, default=100.0)
    p.add_argument("--variables", nargs="+", default=list(VARS), choices=list(VARS))
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    edges = np.arange(0.0, a.max_km + a.ring_km / 2, a.ring_km)
    mid = 0.5 * (edges[:-1] + edges[1:])
    files = {s: a.root / a.lane / s / f"{a.year}.nc" for s in a.sites}
    sites = [s for s in a.sites if files[s].exists()]
    for s in set(a.sites) - set(sites):
        print(f"warning: missing {files[s]}")
    res = {(s, b): ring_stats(files[s], SITES[s], b, edges) for s in sites for b in (*TARGETS, *BINS_3K)}
    bg = {(s, b): ring_stats(files[s], SITES[s], b, np.array(BG_KM)) for s in sites for b in (*TARGETS, *BINS_3K)}

    csv_path = a.out_dir / f"itf_distance_{a.year}_{a.lane}.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["site", "bin", "ctt_hi_C", "ctt_lo_C", "dist_lo_km", "dist_hi_km", "itf", "occ_per_cell", "cot", "cloud_samples", "n_cells"])
        for (s, b), r in res.items():
            kind = "12K" if b in TARGETS else "3K"
            for i in range(len(mid)):
                w.writerow([s, kind, b[1], b[0], edges[i], edges[i + 1], f"{r['itf'][i]:.4f}", f"{r['occ'][i]:.2f}", f"{r['cot'][i]:.3f}",
                            int(r["tot"][i]), int(r["cells"][i])])
    outs = [csv_path]
    for v in a.variables:
        outs += plot_var(v, a, sites, res, bg, mid)
    for f in outs:
        print(f.resolve())


def plot_var(v: str, a: argparse.Namespace, sites: list[str], res: dict, bg: dict, mid: np.ndarray) -> list[Path]:
    """12 K and 3 K figures of one variable; returns the written paths."""
    ylab, dlab, pp = VARS[v]
    name = {"itf": "ITF", "occ": f"cloud occurrence", "cot": "COT"}[v]
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 7})
    pairs = sorted({s.removesuffix("_ctl") for s in sites}, key=list(SITES).index)
    col = dict(zip(pairs, plt.get_cmap("tab10").colors))
    fig, axs = plt.subplots(2, len(TARGETS), figsize=(7.2, 4.6), sharex=True, constrained_layout=True)
    for j, b in enumerate(TARGETS):
        for s in sites:
            y, y0 = res[(s, b)][v], float(bg[(s, b)][v][0])
            ls = "--" if s.endswith("_ctl") else "-"
            lab = SITES[s].label.split(" (")[0] + (" control" if s.endswith("_ctl") and "control" not in SITES[s].label else "")
            axs[0, j].plot(mid, y, ls, color=col[s.removesuffix("_ctl")], lw=1.0, label=lab if j == 0 else None)
            with np.errstate(invalid="ignore", divide="ignore"):
                axs[1, j].plot(mid, 100 * (y - y0) if pp else 100 * (y / y0 - 1), ls, color=col[s.removesuffix("_ctl")], lw=1.0)
        axs[0, j].set_title(f"CTT {b[1]:.0f}..{b[0]:.0f} °C", fontsize=8)
        axs[1, j].axhline(0, color="0.5", lw=0.5)
        axs[1, j].set_xlabel("distance from centre [km]")
        for ax in axs[:, j]:
            ax.axvspan(*BG_KM, color="0.92", zorder=0)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
    axs[0, 0].set_ylabel(ylab)
    axs[1, 0].set_ylabel(dlab)
    fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=6, frameon=False, fontsize=6)
    fig.suptitle(f"Mean {name} vs distance from the site, {LABEL.get(a.lane, a.lane)} {a.year}, {a.ring_km:.0f} km rings (solid: source, dashed: control)", fontsize=8)
    out12 = a.out_dir / f"{v}_distance_12K_{a.year}_{a.lane}.png"
    fig.savefig(out12, dpi=200, bbox_inches="tight")
    plt.close(fig)

    nr = (len(sites) + 2) // 3
    fig, axs = plt.subplots(nr, 3, figsize=(7.2, 2.0 * nr), sharex=True, sharey=True, constrained_layout=True, squeeze=False)
    cm = plt.get_cmap("viridis")
    for n, s in enumerate(sites):
        ax = axs[n // 3, n % 3]
        for i, b in enumerate(BINS_3K):  # warm bins yellow, cold bins dark, as in the colour bar
            y, y0 = res[(s, b)][v], float(bg[(s, b)][v][0])
            with np.errstate(invalid="ignore", divide="ignore"):
                ax.plot(mid, 100 * (y - y0) if pp else 100 * (y / y0 - 1), color=cm(1 - i / (len(BINS_3K) - 1)), lw=0.9)
        ax.axvspan(*BG_KM, color="0.92", zorder=0)
        ax.axhline(0, color="0.5", lw=0.5)
        ax.set_title(SITES[s].label, fontsize=7, loc="left")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    for ax in axs[:, 0]:
        ax.set_ylabel(dlab)
    for ax in axs[-1, :]:
        ax.set_xlabel("distance from centre [km]")
    for ax in axs.flat[len(sites):]:
        ax.set_visible(False)
    sm = plt.cm.ScalarMappable(cmap=cm, norm=plt.Normalize(BINS_3K[-1][0] + 1.5, BINS_3K[0][0] + 1.5))
    fig.colorbar(sm, ax=axs, shrink=0.5, label="CTT bin centre [°C]")
    fig.suptitle(f"{name} vs distance relative to the 70-100 km ring, per 3 K CTT bin, {LABEL.get(a.lane, a.lane)} {a.year}, {a.ring_km:.0f} km rings", fontsize=8)
    out3 = a.out_dir / f"{v}_distance_3K_{a.year}_{a.lane}.png"
    fig.savefig(out3, dpi=200, bbox_inches="tight")
    plt.close(fig)

    what = {"itf": "ITF = sum n_ice / sum (n_ice + n_liq + n_mix) over all 0.05° cells of the ring (occurrence-weighted)",
            "occ": f"cloud occurrence = phase-determined cloud samples summed over {a.year}, per 0.05° cell of the ring",
            "cot": "mean cloud optical thickness = sum cot_sum / sum n_cot over all 0.05° cells of the ring (daytime retrievals)"}[v]
    base = (f"Mean {name} versus distance from the site centre ({LABEL.get(a.lane, a.lane)}, {a.year}), {a.ring_km:.0f} km rings: {what}. "
            "Grey band: 70-100 km background ring; the 2° x 2° box reaches only about 60-75 km east/west, so rings beyond that are north and south arcs only. ")
    out12.with_suffix(".md").write_text(base + f"Top: {name} in the 12 K CTT ranges, solid = source, dashed = its random control (150-200 km away). "
                                        f"Bottom: {dlab.replace('[pp]', 'in percentage points').replace('[%]', 'in %')} (the site's own 70-100 km value).\n")
    out3.with_suffix(".md").write_text(base + f"One panel per site: {dlab.replace('[pp]', 'in percentage points').replace('[%]', 'in %')}, one line per native 3 K CTT bin from -1.5 °C (yellow) to -34.5 °C (dark).\n")
    return [out12, out12.with_suffix(".md"), out3, out3.with_suffix(".md")]


if __name__ == "__main__":
    main()
