#!/usr/bin/env python3
"""Combined ITF change for all point sources from the per-site CSVs of plot_itf_change.py.

Usage: python -m itf.plot_itf_change_sites --fig-dir <dir> --year 1982-2016 --lane cci [--seasons] [--profiles itf occ cot]

Default top panel: heat map with rows = sites and column groups = yearly relative change [%], delta ITF [pp] and
normalized change [%] per 12 K CTT range, plus the background supercooled fraction 1 - ITF_bg [%] as text.
With --seasons: delta ITF [pp] for the year and the seasons DJF, MAM, JJA, SON at CTT 0..-12 and -12..-24 degC.
Bottom: ITF (or cloud occurrence, or mean COT) of centre and background versus CTT (3 K bins) per site.
All values are occurrence-weighted yearly means as written by plot_itf_change.py (run it per site first).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .plot_itf_change import TARGETS
from .sites import SITES

PROFILES = {"itf": ("itf", "ITF", (0, 1.02)), "occ": ("occ", "cloud samples per 0.05° cell, year", (0, None)),
            "cot": ("cot", "mean COT", (0, None))}   # bottom-panel variants from itf_profile_<site>_<year>_<lane>.csv
METRICS = (("itf_change_pct", "relative change [%]"), ("itf_diff_pp", "ΔITF [pp]"), ("itf_change_norm_pct", "normalized [%]"))
SEASONS = ("DJF", "MAM", "JJA", "SON")


def season_rows(path: Path, rng: str) -> dict[str, dict]:
    """Season rows (occurrence-weighted delta ITF, 1 - ITF_bg) of one 12 K range keyed by season."""
    with path.open() as fh:
        return {r["month"].split()[1]: r for r in csv.DictReader(fh) if "(season" in r["month"] and r["ctt_range_C"] == rng}


def year_rows(path: Path) -> tuple[dict[str, dict], dict[float, tuple[float, float]]]:
    """Yearly 12 K rows keyed by range and 3 K profile rows keyed by bin centre (ITF_c, ITF_bg)."""
    ranges, prof = {}, {}
    with path.open() as fh:
        for r in csv.DictReader(fh):
            if "occurrence-weighted" not in r["month"]:
                continue
            lo_hi = r["ctt_range_C"]
            if ".0.." in lo_hi or lo_hi.startswith("0.0"):   # 3 K bin, e.g. "-3.0..-6.0"
                hi, lo = (float(x) for x in lo_hi.split(".."))
                prof[(hi + lo) / 2] = (float(r["itf_centre_median"] or "nan"), float(r["itf_background_median"] or "nan"))
            else:
                ranges[lo_hi] = r
    return ranges, prof


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fig-dir", type=Path, required=True)
    p.add_argument("--year", default="2008", help="year or pooled tag, e.g. 1982-2016")
    p.add_argument("--lane", default="cci")
    p.add_argument("--seasons", action="store_true", help="top panel: delta ITF for year, DJF, MAM, JJA, SON")
    p.add_argument("--profiles", nargs="+", default=list(PROFILES), choices=list(PROFILES), help="one figure per bottom-panel variant")
    a = p.parse_args()
    for pv in a.profiles:
        plot(a, pv)


def plot(a: argparse.Namespace, pv: str) -> None:
    """Heat map plus per-site profiles of ITF, cloud occurrence or COT versus CTT."""
    sites = [s for s in SITES if (a.fig_dir / f"itf_change_{s}_{a.year}_{a.lane}.csv").exists()]
    if not sites:
        raise SystemExit(f"no itf_change_<site>_{a.year}_{a.lane}.csv under {a.fig_dir}")
    col, ylab, ylim = PROFILES[pv]
    profs = {}
    for s in sites:
        f = a.fig_dir / f"itf_profile_{s}_{a.year}_{a.lane}.csv"
        if f.exists():
            with f.open() as fh:
                profs[s] = {float(r["ctt_C"]): (float(r[f"{col}_centre"]), float(r[f"{col}_background"])) for r in csv.DictReader(fh)}
    data = {s: year_rows(a.fig_dir / f"itf_change_{s}_{a.year}_{a.lane}.csv") for s in sites}
    keys = [f"{t[1]:.0f}..{t[0]:.0f}" for t in TARGETS]
    grid = np.array([[float(data[s][0][k][m] or "nan") for m, _ in METRICS for k in keys] for s in sites])
    sup = np.array([[float(data[s][0][k]["bg_supercooled_pct"] or "nan") for k in keys] for s in sites])
    metrics, bglab, bgfmt = METRICS, "1 − ITF$_{bg}$", "{:.0f}%"
    if pv != "itf":   # top panel = change of the profiled quantity itself, per 12 K range
        grid, sup = np.full((len(sites), 2 * len(keys)), np.nan), np.full((len(sites), len(keys)), np.nan)
        for i, s in enumerate(sites):
            rows = {}
            if (f := a.fig_dir / f"itf_profile_{s}_{a.year}_{a.lane}.csv").exists():
                with f.open() as fh:
                    rows = {float(r["ctt_C"]): r for r in csv.DictReader(fh)}
            for j, t in enumerate(TARGETS):
                b = [r for c, r in rows.items() if t[0] < c < t[1]]
                oc, ob = (np.array([float(r[f"occ_{w}"]) for r in b]) for w in ("centre", "background"))
                if pv == "occ":   # cloud samples per cell summed over the 4 bins
                    vc, vb = oc.sum(), ob.sum()
                else:   # COT averaged over the bins, weighted by occurrence
                    cc, cb = (np.array([float(r[f"cot_{w}"]) for r in b]) for w in ("centre", "background"))
                    vc = np.nansum(cc * oc) / oc[np.isfinite(cc)].sum() if np.isfinite(cc).any() else np.nan
                    vb = np.nansum(cb * ob) / ob[np.isfinite(cb)].sum() if np.isfinite(cb).any() else np.nan
                grid[i, j], grid[i, len(keys) + j], sup[i, j] = (100 * (vc / vb - 1) if vb > 0 else np.nan), vc - vb, vb
        unit = "samples/cell" if pv == "occ" else "COT"
        metrics = (("", "relative change [%]"), ("", f"Δ{pv.upper()} [{unit}]"))
        bglab, bgfmt = f"background [{unit}]", "{:.0f}" if pv == "occ" else "{:.1f}"
    labels, lim, unit_lab, tag = [f"{k.replace('..', '…')} °C" for k in keys], 50, "[%] or [pp]", ""
    nb = len(keys)   # width of the right-hand 1 - ITF_bg block
    if a.seasons:   # delta ITF [pp] for the year and each season, one block per CTT range 0..-12 and -12..-24 degC
        rng = keys[:2]
        grid = np.full((len(sites), 5 * len(rng)), np.nan)
        for g, k in enumerate(rng):
            for i, s in enumerate(sites):
                sea = season_rows(a.fig_dir / f"itf_change_{s}_{a.year}_{a.lane}.csv", k)
                grid[i, 5 * g:5 * g + 5] = [float(data[s][0][k]["itf_diff_pp"])] + [float(sea[n]["itf_diff_pp"] or "nan") if n in sea else np.nan for n in SEASONS]
        keys, labels, lim, unit_lab, tag, nb = ["year", *SEASONS], ["year", *SEASONS], 6, "ΔITF [pp]", "_season", 0
        metrics = tuple(("", f"ΔITF [pp], CTT {k.replace('..', '…')} °C") for k in rng)
    nk = len(keys)
    sizes = [nk] * len(metrics)
    if pv == "itf" and not a.seasons:   # drop normalized -24..-36 degC: 1 - ITF_bg < 20 % there at every site
        grid, sizes[-1] = np.delete(grid, len(metrics) * nk - 1, axis=1), nk - 1
    starts = np.concatenate([[0], np.cumsum(sizes)])
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 7})
    fig = plt.figure(figsize=(7.2, 0.32 * len(sites) + 1.6 + 2.0 * ((len(sites) + 2) // 3)))
    gs = fig.add_gridspec(1 + (len(sites) + 2) // 3, 3, height_ratios=[0.32 * len(sites) + 0.9] + [1.6] * ((len(sites) + 2) // 3), hspace=0.75, wspace=0.3)
    ax = fig.add_subplot(gs[0, :])
    im = ax.imshow(np.clip(grid, -lim, lim), cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid[i, j]
            unreliable = pv == "itf" and j >= 2 * nk and sup[i, j - 2 * nk] < 20   # normalized change on < 20 % supercooled background
            ax.text(j, i, "n/a" if np.isnan(v) else f"{v:+.0f}" + ("*" if unreliable else ""), ha="center", va="center", fontsize=6,
                    color="0.3" if np.isnan(v) else ("w" if abs(v) > 0.6 * lim else "k"))
        for k in range(nb):
            ax.text(grid.shape[1] + k, i, bgfmt.format(sup[i, k]), ha="center", va="center", fontsize=6)
    for g in range(1, len(metrics) + (nb > 0)):
        ax.axvline(starts[g] - 0.5, color="k", lw=1.0)
    for g, (_, lab) in enumerate((*metrics, (None, bglab))[:len(metrics) + (nb > 0)]):
        ax.text(starts[g] + ((sizes + [nb])[g] - 1) / 2, -0.85, lab, ha="center", fontsize=7, fontweight="bold")
    ax.set_xlim(-0.5, grid.shape[1] + nb - 0.5)
    ax.set_ylim(len(sites) - 0.5, -1.2)
    ax.set_xticks(range(grid.shape[1] + nb), [lab for n in sizes + [nb] for lab in labels[:n]], rotation=45, ha="right")
    ax.set_yticks(range(len(sites)), [SITES[s].label for s in sites])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01, extend="both")
    cb.set_label(unit_lab if pv == "itf" else f"[%] or [{unit}]")
    ax.set_title(f"{pv.upper()} change at point sources, {a.lane} {a.year}, occurrence-weighted {'year and seasons' if a.seasons else 'year'}: centre 0–10 km vs background 70–100 km", fontsize=8, pad=18)
    for n, s in enumerate(sites):
        axp = fig.add_subplot(gs[1 + n // 3, n % 3])
        prof = profs.get(s, data[s][1] if pv == "itf" else {})
        c = np.array(sorted(prof, reverse=True))
        axp.plot(c, [prof[x][0] for x in c], "o-", color="#b2182b", ms=2, lw=0.9, label="centre 0–10 km")
        axp.plot(c, [prof[x][1] for x in c], "s-", color="#2166ac", ms=2, lw=0.9, label="background 70–100 km")
        axp.set_xlim(0, -42)
        axp.set_ylim(*ylim)
        axp.set_title(SITES[s].label, fontsize=7, loc="left")
        axp.set_xlabel("CTT [°C], 3 K bins")
        if n % 3 == 0:
            axp.set_ylabel(ylab)
        if n == 0:
            axp.legend(frameon=False, fontsize=6, loc="upper left")
        for sp in ("top", "right"):
            axp.spines[sp].set_visible(False)
    out = a.fig_dir / f"itf_change_sites_{a.year}_{a.lane}{'' if pv == 'itf' else '_' + pv}{tag}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    out.with_suffix(".md").write_text(
        f"Combined ITF change at {len(sites)} point sources ({a.lane}, {a.year}), from the per-site itf_change_<site>_{a.year}_{a.lane}.csv files of plot_itf_change.py. "
        + ("Top (season version): ΔITF = 100 × (ITF_c − ITF_bg) [pp] for the occurrence-weighted year and the seasons DJF, MAM, JJA, SON (monthly values weighted by cloud occurrence within the season), left block CTT 0…−12 °C, right block −12…−24 °C, colour scale clipped at ±6 pp. The default version's top panel instead shows: " if a.seasons else "")
        + ("" if pv == "itf" else f"Top ({pv} version): relative change 100 × (centre/background − 1) [%] and difference centre − background of " + ("yearly cloud samples per cell summed over the four 3 K bins" if pv == "occ" else "yearly mean COT averaged over the four 3 K bins weighted by occurrence") + " per 12 K CTT range; right: background value. The ITF version's top panel instead shows: ") + "Top: occurrence-weighted yearly relative change 100 × (centre/background − 1) [%], ΔITF = 100 × (ITF_c − ITF_bg) [pp] and normalized change "
        "100 × ΔITF / (1 − ITF_bg) [%] per 12 K CTT range (normalized only for 0…−12 and −12…−24 °C: at −24…−36 °C 1 − ITF_bg is < 20 %), colour scale clipped at ±50; * = normalized change on < 20 % supercooled background (unreliable); "
        "right: background supercooled fraction 1 − ITF_bg [%]. Bottom: " + {"itf": "yearly ITF", "occ": "yearly cloud samples per 0.05° cell (phase-determined pixels summed over the year)", "cot": "yearly pixel-weighted mean cloud optical thickness (daytime retrievals)"}[pv] + " of centre (0–10 km, red) and background (70–100 km, blue) per 3 K CTT bin. "
        "Centre = median over 0.05° cells 0–10 km from the source, background = median over 70–100 km (north and south arcs of the 2°×2° box only).\n")
    print(out)
    print(out.with_suffix(".md"))
    plt.close(fig)


if __name__ == "__main__":
    main()
