#!/usr/bin/env bash
# Mirror ESA Cloud_cci v3 L3U AVHRR-PM daily CLD_PRODUCTS files (about 0.9 GB each) into ${CCI_RAW}/YYYY/MM/.
# Usage: bash scripts/cci_download.sh --year YYYY [--month MM] [--day DD]; REWRITE=TRUE re-fetches.
# The NOAA satellite is discovered from the server index; if several cover a month the highest NOAA number wins
# (override with SENSOR=AVHRR_NOAA-18). Transfers resume into .part files and are verified with ncdump.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
year=""; month=""; day=""; SENSOR="${SENSOR:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --year) year="$2"; shift 2 ;;
        --month) month="$2"; shift 2 ;;
        --day) day="$2"; shift 2 ;;
        *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ -n "${year}" ]] || { echo "--year is required" >&2; exit 2; }
[[ -n "${CCI_RAW}" ]] || { echo "set CCI_RAW in config.env" >&2; exit 2; }
PRODUCT="CLD_PRODUCTS"

index() {
    # Print the href entries of a server directory listing (empty on failure).
    wget -q -T 60 -t 3 -O - "$1/" 2>/dev/null | grep -o 'href="[^"?/][^"]*"' | sed 's/^href="//; s/"$//' || true
}

sensor_for() {
    # Usage: sensor_for YYYY MM; prints the NOAA directory that holds this month.
    local y="$1" m="$2" s best="" bestn=-1 n
    if [[ -n "${SENSOR}" ]]; then echo "${SENSOR}"; return; fi
    for s in ${SENSORS}; do
        if index "${CCI_URL}/${s}/${y}" | grep -qx "${m}/"; then
            n="${s##*-}"; (( n > bestn )) && { best="${s}"; bestn="${n}"; }
        fi
    done
    echo "${best}"
}

wget_rc() {
    # Usage: wget_rc url out; resumes into out.part, renames when complete and readable.
    local url="$1" out="$2"
    if [[ "${REWRITE}" != TRUE && -s "${out}" ]]; then echo "  skip $(basename "${out}")"; return 0; fi
    [[ "${REWRITE}" == TRUE ]] && rm -f "${out}" "${out}.part"
    if (cd "$(dirname "${out}")" && timeout 3h wget -q --continue -T 120 -t 5 -O "$(basename "${out}").part" "${url}") \
        && ncdump -k "${out}.part" >/dev/null 2>&1; then
        mv "${out}.part" "${out}"; echo "  ok $(basename "${out}")"
    else
        echo "  failed ${url}, partial kept for resume" >&2; return 1
    fi
}

SENSORS="$(index "${CCI_URL}" | grep '^AVHRR_NOAA-' | tr -d '/' | tr '\n' ' ')"
[[ -n "${SENSORS}" ]] || { echo "${CCI_URL} not reachable" >&2; exit 4; }
echo "sensors on server: ${SENSORS}"
months="${month:-01 02 03 04 05 06 07 08 09 10 11 12}"
nfail=0
for m in ${months}; do
    m="$(printf '%02d' "$((10#${m}))")"
    s="$(sensor_for "${year}" "${m}")"
    [[ -n "${s}" ]] || { echo "no sensor covers ${year}-${m}"; continue; }
    src="${CCI_URL}/${s}/${year}/${m}"
    out_dir="${CCI_RAW}/${year}/${m}"; mkdir -p "${out_dir}"
    pattern="^${year}${m}${day:+$(printf '%02d' "$((10#${day}))")}[0-9]*-ESACCI-L3U_CLOUD-${PRODUCT}-${s}-fv3.0.nc$"
    files="$(index "${src}" | grep -E "${pattern}" || true)"
    echo "${year}-${m} ${s}: $(wc -w <<<"${files}") files"
    for f in ${files}; do
        wget_rc "${src}/${f}" "${out_dir}/${f}" &
        while (( $(jobs -rp | wc -l) >= PARALLEL )); do wait -n || nfail=$((nfail + 1)); done
    done
    while (( $(jobs -rp | wc -l) > 0 )); do wait -n || nfail=$((nfail + 1)); done
done
echo "done, ${nfail} failures"
echo "${CCI_RAW}/${year}"
[[ "${nfail}" -eq 0 ]]
