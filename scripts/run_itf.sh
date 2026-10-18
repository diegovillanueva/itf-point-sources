#!/usr/bin/env bash
# One product, one site, one month (or day) of daily ITF counts with itf_day.py.
# Usage: bash scripts/run_itf.sh --product cci|clara|modis|modis5 --site moscow --year 2008 --month 01 [--day 01]
#        [--box lat_min,lat_max,lon_min,lon_max] [--parallel N] [--rewrite] [--mixed liquid|ice]
# Output: ${OUT_ROOT}/<product>/daily/<site>/YYYY/MM/DD.nc; MODIS days are indexed first into ${OUT_ROOT}/modis/index/.
# Existing outputs are skipped unless --rewrite (or REWRITE=TRUE); days run PARALLEL at a time under run_capped.
# Days without input (archive gaps) are reported and do not count as failures; the exit status is non-zero only on errors.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
product=""; site=""; year=""; month=""; day=""; box=""; parallel="${PARALLEL}"; mixed="liquid"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --product)  product="$2"; shift 2 ;;
        --site)     site="$2"; shift 2 ;;
        --year)     year="$2"; shift 2 ;;
        --month)    month="$2"; shift 2 ;;
        --day)      day="$2"; shift 2 ;;
        --box)      box="$2"; shift 2 ;;
        --parallel) parallel="$2"; shift 2 ;;
        --rewrite)  REWRITE=TRUE; shift ;;
        --mixed)    mixed="$2"; shift 2 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
[[ -n "${product}" && -n "${site}" && -n "${year}" && -n "${month}" ]] || { echo "--product, --site, --year and --month are required" >&2; exit 2; }
case "${product}" in cci|clara|modis|modis5) ;; *) echo "--product cci|clara|modis|modis5" >&2; exit 2 ;; esac
[[ -n "${box}" ]] || box="$(site_box "${site}")"
month="$(printf '%02d' "$((10#${month}))")"
out_dir="${OUT_ROOT}/${product}/daily/${site}/${year}/${month}"
index_dir="${OUT_ROOT}/modis/index"
log_dir="${OUT_ROOT}/${product}/logs"
mkdir -p "${out_dir}" "${log_dir}"
case "${product}" in
    cci)    [[ -d "${CCI_S1_ARCHIVE}" ]] || { echo "CCI_S1_ARCHIVE=${CCI_S1_ARCHIVE} not found" >&2; exit 3; }
            src_args=(--cci-archive "${CCI_S1_ARCHIVE}") ;;
    clara)  [[ -d "${CLARA_MIRROR}" ]] || { echo "CLARA_MIRROR=${CLARA_MIRROR} not found" >&2; exit 3; }
            src_args=(--clara-mirror "${CLARA_MIRROR}") ;;
    modis*) [[ -d "${MODIS_ARCHIVE}" ]] || { echo "MODIS_ARCHIVE=${MODIS_ARCHIVE} not found" >&2; exit 3; }
            src_args=(--modis-archive "${MODIS_ARCHIVE}" --modis-index "${index_dir}" --mixed "${mixed}") ;;
esac
if [[ -n "${day}" ]]; then
    days=("$(printf '%02d' "$((10#${day}))")")
else
    ndays="$("${PYTHON}" -c "import calendar; print(calendar.monthrange(${year}, $((10#${month})))[1])")"
    days=(); for ((d = 1; d <= ndays; d++)); do days+=("$(printf '%02d' "${d}")"); done
fi
todo=()
for d in "${days[@]}"; do
    [[ "${REWRITE}" == FALSE && -s "${out_dir}/${d}.nc" ]] && continue
    todo+=("${d}")
done
if [[ ${#todo[@]} -eq 0 ]]; then echo "${product} ${site} ${year}-${month}: all ${#days[@]} days present"; exit 0; fi

one_day() {
    local d="$1" log="${log_dir}/${site}_${year}${month}_$1.log"
    cd "${REPO}"
    if [[ "${product}" == modis* ]]; then
        run_capped 30m "${PYTHON}" -m itf.index_modis --year "${year}" --month "$((10#${month}))" --day "$((10#${d}))" \
            --archive "${MODIS_ARCHIVE}" --index-dir "${index_dir}" --nproc 1 >"${log}" 2>&1 \
            || { echo "index ${year}-${month}-${d} failed (see ${log})" >&2; return 1; }
    fi
    run_capped 30m "${PYTHON}" -m itf.itf_day --product "${product}" --date "${year}-${month}-${d}" \
        --box "${box}" --box-name "${site}" --out "${out_dir}/${d}.nc" "${src_args[@]}" >>"${log}" 2>&1 \
        || { echo "${product} ${site} ${year}-${month}-${d} failed (see ${log})" >&2; return 1; }
    grep '^done' "${log}" || true
}
t0="$(date +%s)"
for d in "${todo[@]}"; do
    while (( $(jobs -rp | wc -l) >= parallel )); do wait -n || true; done
    one_day "${d}" &
done
wait || true
n_ok="$(for d in "${days[@]}"; do [[ -s "${out_dir}/${d}.nc" ]] && echo x || true; done | wc -l)"
n_skip=0; n_fail=0
for d in "${todo[@]}"; do
    [[ -s "${out_dir}/${d}.nc" ]] && continue
    if grep -q 'no input' "${log_dir}/${site}_${year}${month}_${d}.log" 2>/dev/null; then n_skip=$((n_skip + 1)); else n_fail=$((n_fail + 1)); fi
done
echo "${product} ${site} ${year}-${month}: ${n_ok}/${#days[@]} days present, ${n_skip} without input, ${n_fail} failed, $(( $(date +%s) - t0 )) s"
echo "${out_dir}"
[[ "${n_fail}" -eq 0 ]]
