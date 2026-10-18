#!/usr/bin/env bash
# Select the intensive (ctt, cot) and extensive (cvf_liq, cvf_ice, cwp_ext) variables of the raw Cloud_cci L3U days
# with cdo: ${CCI_RAW}/YYYY/MM/<file> -> ${CCI_S1_ARCHIVE}/{intensive,extensive}/YYYY/MM/<file>.
# Usage: bash scripts/cci_select.sh --year YYYY [--month MM] [--day DD]; REWRITE=TRUE overwrites.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
year=""; month=""; day=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --year) year="$2"; shift 2 ;;
        --month) month="$2"; shift 2 ;;
        --day) day="$2"; shift 2 ;;
        *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ -n "${year}" ]] || { echo "--year is required" >&2; exit 2; }
[[ -n "${CCI_RAW}" && -n "${CCI_S1_ARCHIVE}" ]] || { echo "set CCI_RAW and CCI_S1_ARCHIVE in config.env" >&2; exit 2; }
mm="??"; [[ -n "${month}" ]] && mm="$(printf '%02d' "$((10#${month}))")"
dd="??"; [[ -n "${day}" ]] && dd="$(printf '%02d' "$((10#${day}))")"

cdo_sel_int="-selname,ctt_corrected_asc,cot_asc"
cdo_form_int="-expr,ctt=ctt_corrected_asc;cot=cot_asc"
cdo_sel_ext="-selname,cwp_asc,cph_asc"
cdo_form_ext="-expr,cvf_liq=(cph_asc==1);cvf_ice=(cph_asc==2);cwp_ext=cwp_asc*(cvf_ice+cvf_liq)"

process_file() {
    # Usage: process_file <raw file>; writes both subsets, skipping existing outputs unless REWRITE=TRUE.
    local f_in="$1" f y m kind form sel out t0 rc=0
    f="$(basename "${f_in}")"; m="$(basename "$(dirname "${f_in}")")"; y="$(basename "$(dirname "$(dirname "${f_in}")")")"
    t0="$(date +%s)"
    for kind in intensive extensive; do
        if [[ "${kind}" == intensive ]]; then form="${cdo_form_int}"; sel="${cdo_sel_int}"; else form="${cdo_form_ext}"; sel="${cdo_sel_ext}"; fi
        out="${CCI_S1_ARCHIVE}/${kind}/${y}/${m}/${f}"
        [[ "${REWRITE}" != TRUE && -s "${out}" ]] && continue
        mkdir -p "$(dirname "${out}")"
        if ! run_capped 30m cdo -O -s "${form}" "${sel}" "${f_in}" "${out}.tmp" || ! mv "${out}.tmp" "${out}"; then
            echo "[FAIL-${kind}] ${f}" >&2; rm -f "${out}.tmp"; rc=1
        fi
    done
    echo "[$([[ ${rc} -eq 0 ]] && echo OK || echo FAIL)] $(( $(date +%s) - t0 ))s ${f}"
    return "${rc}"
}
export -f process_file run_capped
export CCI_S1_ARCHIVE REWRITE MEM_GB_PER_TASK cdo_sel_int cdo_form_int cdo_sel_ext cdo_form_ext

shopt -s nullglob
files=( "${CCI_RAW}/${year}"/${mm}/${year}${mm}${dd}-ESACCI-L3U_CLOUD-CLD_PRODUCTS-AVHRR_NOAA-*-fv3.0.nc )
echo "${#files[@]} raw files for ${year}-${mm}-${dd}, parallel ${PARALLEL}"
[[ ${#files[@]} -gt 0 ]] || exit 0
printf '%s\n' "${files[@]}" | xargs -P "${PARALLEL}" -I{} bash -c 'process_file "$1"' _ {}
echo "${CCI_S1_ARCHIVE}/intensive/${year}"
echo "${CCI_S1_ARCHIVE}/extensive/${year}"
