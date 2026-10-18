#!/usr/bin/env bash
# Figures for a set of sites: per-site ITF change (plot_itf_change.py), ITF maps (plot_itf_maps.py) and the combined
# all-sites figures (plot_itf_change_sites.py).
# Usage: bash scripts/run_sites.sh --root data --lane cci --year 1982-2016 --out-dir figs [--sites "moscow moscow_ctl"] [--no-maps]
# --root holds <lane>/<site>/<year>/MM.nc (and <year>.nc for the maps); --year is a year or a pooled tag of itf_pool.py.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
root=""; lane="cci"; year=""; out_dir=""; sites=""; maps=TRUE
while [[ $# -gt 0 ]]; do
    case "$1" in
        --root)    root="$2"; shift 2 ;;
        --lane)    lane="$2"; shift 2 ;;
        --year)    year="$2"; shift 2 ;;
        --out-dir) out_dir="$2"; shift 2 ;;
        --sites)   sites="$2"; shift 2 ;;
        --no-maps) maps=FALSE; shift ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
[[ -n "${root}" && -n "${year}" && -n "${out_dir}" ]] || { echo "--root, --year and --out-dir are required" >&2; exit 2; }
root="$(cd "${root}" && pwd)"
mkdir -p "${out_dir}"; out_dir="$(cd "${out_dir}" && pwd)"
cd "${REPO}"
[[ -n "${sites}" ]] || sites="$("${PYTHON}" -m itf.sites --list | tr '\n' ' ')"
for s in ${sites}; do
    [[ -d "${root}/${lane}/${s}/${year}" ]] || { echo "skip ${s}: no ${root}/${lane}/${s}/${year}" >&2; continue; }
    run_capped 30m "${PYTHON}" -m itf.plot_itf_change --root "${root}" --box "${s}" --year "${year}" --lanes "${lane}" --out-dir "${out_dir}"
    if [[ "${maps}" == TRUE && -s "${root}/${lane}/${s}/${year}.nc" ]]; then
        run_capped 30m "${PYTHON}" -m itf.plot_itf_maps --root "${root}" --box "${s}" --year "${year}" --months year --lanes "${lane}" --out-dir "${out_dir}"
    fi
done
run_capped 30m "${PYTHON}" -m itf.plot_itf_change_sites --fig-dir "${out_dir}" --year "${year}" --lane "${lane}"
run_capped 30m "${PYTHON}" -m itf.plot_itf_change_sites --fig-dir "${out_dir}" --year "${year}" --lane "${lane}" --seasons --profiles itf
