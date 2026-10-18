#!/usr/bin/env bash
# One product, one site, one year: all months through run_itf.sh, then itf_agg.py (monthly and yearly files).
# Usage: bash scripts/run_year.sh --product cci --site moscow --year 2008 [--months "01 02"] [--parallel N] [--rewrite]
# Output: ${OUT_ROOT}/<product>/daily/<site>/YYYY/MM/DD.nc and ${OUT_ROOT}/<product>/<site>/{YYYY/MM.nc,YYYY.nc}.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
product=""; site=""; year=""; months="$(seq -w 1 12 | tr '\n' ' ')"; extra=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --product)  product="$2"; shift 2 ;;
        --site)     site="$2"; shift 2 ;;
        --year)     year="$2"; shift 2 ;;
        --months)   months="$2"; shift 2 ;;
        --parallel) extra+=(--parallel "$2"); shift 2 ;;
        --rewrite)  extra+=(--rewrite); shift ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
[[ -n "${product}" && -n "${site}" && -n "${year}" ]] || { echo "--product, --site and --year are required" >&2; exit 2; }
t0="$(date +%s)"
fail=0
for m in ${months}; do
    bash "${REPO}/scripts/run_itf.sh" --product "${product}" --site "${site}" --year "${year}" --month "${m}" "${extra[@]}" || fail=1
done
cd "${REPO}"
run_capped 2h "${PYTHON}" -m itf.itf_agg --in-dir "${OUT_ROOT}/${product}/daily/${site}/${year}" \
    --out-dir "${OUT_ROOT}/${product}/${site}" --year "${year}"
n="$(find "${OUT_ROOT}/${product}/daily/${site}/${year}" -name '[0-9][0-9].nc' | wc -l)"
echo "${product} ${site} ${year}: ${n} daily files, $(( ($(date +%s) - t0) / 60 )) min"
[[ "${fail}" -eq 0 ]] || { echo "some months incomplete, rerun to resume" >&2; exit 1; }
