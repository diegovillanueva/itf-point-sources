#!/usr/bin/env python3
"""ITF change around a point source per lane, month and CTT range: 100 * (centre / background - 1) [%].

Usage: python -m itf.plot_itf_change --root <root> --box moscow --year 1982-2016 --lanes cci --out-dir <dir>
Input: <root>/<lane>/<box>/<year>/MM.nc as written by itf_agg.py or itf_pool.py.

Per 0.05 degree cell: ITF = sum(n_ice) / sum(n_ice + n_liq + n_mix) over the month in each 12 K CTT range
(0..-12, -12..-24, -24..-36 degC); cells with fewer than MIN_N samples are dropped.
centre = median cell ITF at 0-10 km from the site; background = median over 70-100 km. The 2 x 2 degree box reaches
only about 60-75 km east and west of the site, so the background ring consists of its northern and southern arcs.

With a single lane the script also writes occurrence-weighted yearly and seasonal rows (DJF, MAM, JJA, SON) and the
3 K profile file itf_profile_<box>_<year>_<lane>.csv used by plot_itf_change_sites.py.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np

from .sites import SITES, Site

LANES = ("cci", "clara", "modis", "modis5")
LABEL = {"cci": "Cloud_cci", "clara": "CLARA-A3", "modis": "MODIS 1 km", "modis5": "MODIS 5 km"}
TARGETS = ((-12.0, 0.0), (-24.0, -12.0), (-36.0, -24.0))   # 12 K CTT ranges [degC], 4 native 3 K bins each
MIN_N = 3
PROFILE_C = np.arange(-1.5, -42, -3.0)   # native 3 K bin centres 0..-42 degC for the ITF(CTT) profiles
CENTRE_KM, BG_KM = (0.0, 10.0), (70.0, 100.0)
SEASONS = (("DJF", ("12", "01", "02")), ("MAM", ("03", "04", "05")), ("JJA", ("06", "07", "08")), ("SON", ("09", "10", "11")))


def distance_km(lat: np.ndarray, lon: np.ndarray, site: Site) -> np.ndarray:
    """Equirectangular distance [km] of every cell centre from the site."""
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    return 111.2 * np.hypot(la - site.lat, (lo - site.lon) * np.cos(np.radians(site.lat)))


def change(path: Path, target: tuple[float, float], site: Site) -> tuple[float, float, float, int, int, float, float, float]:
    """Centre median, background median, change [%], cells in centre and background, cloud samples in centre + background,
    mean cloud samples per cell in the centre and in the background."""
    with nc.Dataset(path) as d:
        c = np.asarray(d["cosp_ht"][:], float)
        k = np.where((c - 1.5 >= target[0]) & (c + 1.5 <= target[1]))[0]   # all 3 K bins inside the range
        cnt = {n: np.ma.filled(d[n][:, :, :, k], 0).sum((0, 3)).astype(float) for n in ("n_ice", "n_liq", "n_mix") if n in d.variables}
        lat, lon = np.asarray(d["lat"][:]), np.asarray(d["lon"][:])
    n = sum(cnt.values())
    with np.errstate(invalid="ignore", divide="ignore"):
        itf = np.where(n >= MIN_N, cnt["n_ice"] / n, np.nan)
    dist = distance_km(lat, lon, site)
    occ = float(n[((dist >= CENTRE_KM[0]) & (dist <= CENTRE_KM[1])) | ((dist >= BG_KM[0]) & (dist <= BG_KM[1]))].sum())
    out = []
    for lo_km, hi_km in (CENTRE_KM, BG_KM):
        v = itf[(dist >= lo_km) & (dist <= hi_km) & ~np.isnan(itf)]
        out.append((float(np.median(v)) if v.size else np.nan, v.size))
    (cen, nc_), (bg, nb) = out
    chg = 100 * (cen / bg - 1) if bg > 0 and nc_ and nb else np.nan
    mc, mb = (float(n[(dist >= lo_km) & (dist <= hi_km)].mean()) for lo_km, hi_km in (CENTRE_KM, BG_KM))
    return cen, bg, chg, nc_, nb, occ, mc, mb


def cot_sums(path: Path, target: tuple[float, float], site: Site) -> np.ndarray:
    """COT sum and n_cot over the centre and background cells, shape (2, 2) = (centre, bg) x (sum, n); zeros without COT."""
    with nc.Dataset(path) as d:
        if "cot_sum" not in d.variables:
            return np.zeros((2, 2))
        c = np.asarray(d["cosp_ht"][:], float)
        k = np.where((c - 1.5 >= target[0]) & (c + 1.5 <= target[1]))[0]
        sm = np.ma.filled(d["cot_sum"][:, :, :, k], 0).sum((0, 3)).astype(float)
        n = np.ma.filled(d["n_cot"][:, :, :, k], 0).sum((0, 3)).astype(float)
        lat, lon = np.asarray(d["lat"][:]), np.asarray(d["lon"][:])
    dist = distance_km(lat, lon, site)
    return np.array([[sm[m].sum(), n[m].sum()] for m in ((dist >= CENTRE_KM[0]) & (dist <= CENTRE_KM[1]), (dist >= BG_KM[0]) & (dist <= BG_KM[1]))])


def month_dir(root: Path, lane: str, box: str, year: str) -> Path:
    return root / lane / box / str(year)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, required=True, help="directory holding <lane>/<box>/<year>/MM.nc")
    p.add_argument("--box", default="moscow")
    p.add_argument("--year", default="2008", help="year or pooled tag, e.g. 1982-2016 (itf_pool.py)")
    p.add_argument("--months", nargs="*", default=None, help="default: every month with a monthly file")
    p.add_argument("--lanes", nargs="+", default=list(LANES), help="subset of lanes; a subset adds _<lanes> to the file names")
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    if a.box not in SITES:
        raise SystemExit(f"unknown site {a.box}; known: {', '.join(SITES)}")
    site = SITES[a.box]
    a.out_dir.mkdir(parents=True, exist_ok=True)
    months = a.months or sorted({f.stem for ln in a.lanes for f in month_dir(a.root, ln, a.box, a.year).glob("[0-9][0-9].nc")})
    if not months:
        raise SystemExit(f"no monthly files under {a.root}/<lane>/{a.box}/{a.year}")
    cols = [(m, t) for m in months for t in TARGETS]
    lanes = list(a.lanes)
    tag = "" if lanes == list(LANES) else "_" + "-".join(lanes)
    val = np.full((len(lanes), len(cols)), np.nan)
    occ = np.zeros((len(lanes), len(cols)))
    bgv = np.full((len(lanes), len(cols)), np.nan)
    nrm = np.full((len(lanes), len(cols)), np.nan)
    dif = np.full((len(lanes), len(cols)), np.nan)
    rows = []
    for i, ln in enumerate(lanes):
        for j, (m, t) in enumerate(cols):
            f = month_dir(a.root, ln, a.box, a.year) / f"{m}.nc"
            if not f.exists():
                continue
            cen, bg, chg, nc_, nb, occ[i, j], _, _ = change(f, t, site)
            val[i, j], bgv[i, j] = chg, bg
            nrm[i, j] = 100 * (cen - bg) / (1 - bg) if bg < 1 and not np.isnan(chg) else np.nan   # relative to the supercooled background
            dif[i, j] = 100 * (cen - bg) if not np.isnan(chg) else np.nan   # absolute difference [percentage points]
            rows.append([ln, f"{a.year}-{m}", f"{t[1]:.0f}..{t[0]:.0f}", f"{cen:.3f}", f"{bg:.3f}", f"{chg:.1f}", nc_, nb, f"{nrm[i, j]:.1f}", f"{100 * (1 - bg):.1f}", f"{dif[i, j]:.1f}"])
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 7})
    lim = 100
    if len(lanes) == 1:   # one lane: rows = CTT ranges, columns = months, plus yearly and seasonal summaries
        def shape(x: np.ndarray) -> np.ndarray:
            return x[0].reshape(len(months), len(TARGETS)).T

        grid = shape(val)
        w = shape(occ) * ~np.isnan(grid)   # year = monthly values weighted by cloud occurrence
        with np.errstate(invalid="ignore"):
            yr, yd, ys = (np.nansum(x * w, 1) / w.sum(1) for x in (grid, shape(dif), 100 * (1 - shape(bgv))))
            yn = np.where(ys > 0, 100 * yd / ys, np.nan)   # ratio of yearly means (monthly ratios are undefined where ITF_bg = 1)
        for t, v, vn, vs, vd in zip(TARGETS, yr, yn, ys, yd):
            rows.append([lanes[0], f"{a.year} (occurrence-weighted)", f"{t[1]:.0f}..{t[0]:.0f}", "", "", f"{v:.1f}", "", "", f"{vn:.1f}", f"{vs:.1f}", f"{vd:.1f}"])
        for sn, mm in SEASONS:
            sel = np.isin(months, mm)
            with np.errstate(invalid="ignore"):
                sd, ss = (np.nansum(x[:, sel] * w[:, sel], 1) / w[:, sel].sum(1) for x in (shape(dif), 100 * (1 - shape(bgv))))
            for t, vd, vs in zip(TARGETS, sd, ss):
                rows.append([lanes[0], f"{a.year} {sn} (season, occ. weighted)", f"{t[1]:.0f}..{t[0]:.0f}", "", "", "", "", "", "", f"{vs:.1f}", f"{vd:.1f}"])
        grid = np.column_stack([grid, yr, yd, yn])
        prof = np.full((3, len(PROFILE_C), len(months)), np.nan)   # delta ITF [pp], ITF_c, ITF_bg per 3 K bin and month
        pw = np.zeros(prof.shape[1:])
        cntm, cotm = np.zeros((2, len(PROFILE_C), len(months))), np.zeros((2, 2, len(PROFILE_C), len(months)))
        for j, m in enumerate(months):
            f = month_dir(a.root, lanes[0], a.box, a.year) / f"{m}.nc"
            if not f.exists():
                continue
            for k, c in enumerate(PROFILE_C):
                cen, bg, chg, _, _, o, mc, mb = change(f, (c - 1.5, c + 1.5), site)
                cntm[:, k, j] = mc, mb
                cotm[:, :, k, j] = cot_sums(f, (c - 1.5, c + 1.5), site)
                if not np.isnan(chg):
                    prof[:, k, j], pw[k, j] = (100 * (cen - bg), cen, bg), o
        cnt, cot = cntm.sum(-1), cotm.sum(-1)
        with np.errstate(invalid="ignore"):
            ydif, ycen, ybg = np.nansum(prof * pw, 2) / pw.sum(1)
        seas = {}   # DJF and MAM profiles: ITF (c, bg), occurrence (c, bg), COT (c, bg)
        for sn, mm in SEASONS[:2]:
            jj = [j for j, m in enumerate(months) if m in mm]
            with np.errstate(invalid="ignore", divide="ignore"):
                si = np.nansum(prof[1:, :, jj] * pw[:, jj], 2) / pw[:, jj].sum(1)
                sc = cotm[:, :, :, jj].sum(-1)
                seas[sn] = (si, cntm[:, :, jj].sum(-1), np.where(sc[:, 1] > 0, sc[:, 0] / np.where(sc[:, 1] > 0, sc[:, 1], 1), np.nan))
        for c, v, vc, vb in zip(PROFILE_C, ydif, ycen, ybg):
            rows.append([lanes[0], f"{a.year} (occurrence-weighted)", f"{c + 1.5:.1f}..{c - 1.5:.1f}", f"{vc:.3f}", f"{vb:.3f}", "", "", "", "", "", f"{v:.1f}"])
        with np.errstate(invalid="ignore", divide="ignore"):
            ycot = np.where(cot[:, 1] > 0, cot[:, 0] / cot[:, 1], np.nan)   # pixel-weighted mean COT per bin, whole year
        pf = a.out_dir / f"itf_profile_{a.box}_{a.year}_{lanes[0]}.csv"
        with pf.open("w", newline="") as fh:
            wr = csv.writer(fh, lineterminator="\n")
            wr.writerow(["ctt_C", "itf_centre", "itf_background", "occ_centre", "occ_background", "cot_centre", "cot_background"])
            for k, c in enumerate(PROFILE_C):
                wr.writerow([c, f"{ycen[k]:.4f}", f"{ybg[k]:.4f}", f"{cnt[0, k]:.2f}", f"{cnt[1, k]:.2f}", f"{ycot[0, k]:.3f}", f"{ycot[1, k]:.3f}"])
        print(pf)
        nm0 = len(months) + 4
        fig = plt.figure(figsize=(max(7.0, 0.5 * nm0 + 1.8), 0.45 * len(TARGETS) + 1.4 + 6.0))
        gs = fig.add_gridspec(3, 3, height_ratios=[0.45 * len(TARGETS) + 1.0, 2.6, 2.6], hspace=0.6, wspace=0.3)
        for n, (lab, ylab) in enumerate((("(d) ITF(CTT)", "ITF"), ("(e) cloud occurrence per CTT bin", "cloud samples per 0.05° cell"), ("(f) mean COT per CTT bin", "mean cloud optical thickness"))):
            axs = fig.add_subplot(gs[2, n])
            for sn, ls, mk in (("DJF", "-", "o"), ("MAM", "--", "^")):
                for w_, col, where in ((0, "#b2182b", "centre"), (1, "#2166ac", "background")):
                    axs.plot(PROFILE_C, seas[sn][n][w_], ls=ls, marker=mk, color=col, ms=2.5, lw=1, label=f"{sn} {where}")
            axs.set_xlim(0, -42)
            axs.set_ylim(0, 1 if n == 0 else None)
            axs.set_xlabel("CTT [°C], 3 K bins")
            axs.set_ylabel(ylab)
            axs.set_title(f"{lab}, DJF and MAM", fontsize=7, loc="left")
            if n == 0:
                axs.legend(frameon=False, fontsize=5.5, loc="upper left")
            for sp in ("top", "right"):
                axs.spines[sp].set_visible(False)
        ax = fig.add_subplot(gs[0, :])
        axi, axo, axc = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1]), fig.add_subplot(gs[1, 2])
        axc.plot(PROFILE_C, ycot[0], "o-", color="#b2182b", ms=3, lw=1, label="centre 0–10 km")
        axc.plot(PROFILE_C, ycot[1], "s-", color="#2166ac", ms=3, lw=1, label="background 70–100 km")
        axc.set_ylim(0, None)
        axc.set_ylabel("mean cloud optical thickness")
        axo.plot(PROFILE_C, cnt[0], "o-", color="#b2182b", ms=3, lw=1, label="centre 0–10 km")
        axo.plot(PROFILE_C, cnt[1], "s-", color="#2166ac", ms=3, lw=1, label="background 70–100 km")
        axo.set_ylim(0, None)
        axo.set_ylabel(f"cloud samples per 0.05° cell, {a.year}")
        axi.plot(PROFILE_C, ycen, "o-", color="#b2182b", ms=3, lw=1, label="centre 0–10 km")
        axi.plot(PROFILE_C, ybg, "s-", color="#2166ac", ms=3, lw=1, label="background 70–100 km")
        axi.set_ylim(0, 1)
        axi.set_ylabel("ITF")
        axi.legend(frameon=False, fontsize=6, loc="upper left")
        for axx, title in ((axi, "(a) ITF(CTT), occurrence-weighted year"), (axo, "(b) cloud occurrence per CTT bin, year total"), (axc, "(c) mean COT per CTT bin, year")):
            axx.set_xlim(0, -42)
            axx.set_xlabel("CTT [°C], 3 K bins")
            axx.set_title(title, fontsize=7, loc="left")
            for sp in ("top", "right"):
                axx.spines[sp].set_visible(False)
        im = ax.imshow(np.clip(grid, -lim, lim), cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
        ax.set_yticks(range(len(TARGETS)), [f"{t[1]:.0f}…{t[0]:.0f} °C" for t in TARGETS])
        nm = len(months)
        ax.set_xticks(range(nm + 4), [*months, "year", "year\nΔITF", "year\nnorm.", "year\n1−ITF$_{bg}$"])
        ax.axvline(nm - 0.5, color="k", lw=1.2)
        ax.axvline(nm + 2.5, color="k", lw=1.2)
        for i, v in enumerate(ys):   # background supercooled fraction [%] as text
            ax.text(nm + 3, i, f"{v:.0f}%", ha="center", va="center", fontsize=6, color="k")
        ax.set_xlim(-0.5, nm + 3.5)
        ax.set_xlabel(f"{LABEL[lanes[0]]}, month of {a.year}")
    else:   # rows = lanes, columns = month x CTT range
        grid = val
        fig, ax = plt.subplots(figsize=(max(4.0, 0.55 * len(cols) + 1.5), 0.45 * len(lanes) + 1.4))
        im = ax.imshow(np.clip(grid, -lim, lim), cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
        ax.set_yticks(range(len(lanes)), [LABEL[ln] for ln in lanes])
        ax.set_xticks(range(len(cols)), [f"{t[1]:.0f}…{t[0]:.0f} °C" for _, t in cols])
        for j in range(len(months)):
            ax.text(3 * j + 1, -0.9, f"{a.year}-{months[j]}", ha="center", fontsize=7, fontweight="bold")
            if j:
                ax.axvline(3 * j - 0.5, color="k", lw=0.8)
        ax.set_ylim(len(lanes) - 0.5, -1.3)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid[i, j]
            ax.text(j, i, "n/a" if np.isnan(v) else f"{v:+.0f}", ha="center", va="center", fontsize=6,
                    color="0.3" if np.isnan(v) else ("w" if abs(v) > 60 else "k"))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, extend="both")
    cb.set_label("ITF change = 100 × (centre / background − 1) [%]")
    ax.set_title(f"ITF change at {site.label}: centre 0–10 km vs background 70–100 km (0.05° cells)", fontsize=8, pad=14)
    csv_path = a.out_dir / f"itf_change_{a.box}_{a.year}{tag}.csv"
    with csv_path.open("w", newline="") as fh:
        wr = csv.writer(fh, lineterminator="\n")
        wr.writerow(["lane", "month", "ctt_range_C", "itf_centre_median", "itf_background_median", "itf_change_pct", "n_cells_centre", "n_cells_background", "itf_change_norm_pct", "bg_supercooled_pct", "itf_diff_pp"])
        wr.writerows(rows)
    out = a.out_dir / f"itf_change_{a.box}_{a.year}{tag}.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    out.with_suffix(".md").write_text(
        f"ITF change = 100 × (median ITF of 0.05° cells 0–10 km from {site.label} / median over 70–100 km − 1) [%], per lane, month ({a.year}) and 12 K CTT range "
        f"0…−12, −12…−24, −24…−36 °C; cell ITF = Σn_ice/Σ(n_ice+n_liq+n_mix) over the month, cells with < {MIN_N} samples dropped. "
        "The 2°×2° box reaches only ≈ 62 km east/west, so the background ring is its north and south arcs. "
        "n/a: no valid centre/background cell or background median 0. "
        "year: monthly values weighted by cloud occurrence (phase samples in centre + ring); year ΔITF = 100 × (ITF_centre − ITF_bg) [percentage points]; "
        "bottom rows: (a) year ITF_centre and ITF_bg, (b) mean cloud samples (n_ice+n_liq+n_mix) per 0.05° cell in centre and background, summed over the year, "
        "(c) mean COT, per native 3 K CTT bin 0…−42 °C (same weighting; csv rows with 3 K ranges), (d)-(f) the same for DJF and MAM; "
        "year norm. = 100 × year ΔITF / year (1 − ITF_bg) [%] (ratio of the yearly means, not the mean of monthly ratios, which are undefined when ITF_bg = 1): "
        "the change relative to the supercooled (liquid) background, unreliable where 1−ITF_bg is small (< 20 %); year 1−ITF_bg = background supercooled fraction [%]. "
        f"Values with medians and cell counts: {csv_path.name}.\n")
    print(out)
    print(out.with_suffix(".md"))
    print(csv_path)


if __name__ == "__main__":
    main()
