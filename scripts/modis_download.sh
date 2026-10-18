#!/usr/bin/env bash
# Download MODIS-Aqua MYD06_L2 collection 6.1 granules of whole UTC days from LAADS into
# ${MODIS_ARCHIVE}/YYYY/DDD/MYD06_L2/YYYY/DDD/ (about 288 granules and 16.5 GB per day).
# Usage: LAADS_TOKEN=<token> bash scripts/modis_download.sh --year 2008 --doy 1 [--doy-end 31]
# The token (LAADS or Earthdata Login bearer token) is read from the environment only. Listings use the public
# JSON index of the archive directory; transfers resume with curl -C - and are size-checked against the listing.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
year=""; doy=""; doy_end=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --year) year="$2"; shift 2 ;;
        --doy) doy="$2"; shift 2 ;;
        --doy-end) doy_end="$2"; shift 2 ;;
        *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ -n "${year}" && -n "${doy}" ]] || { echo "--year and --doy are required" >&2; exit 2; }
[[ -n "${MODIS_ARCHIVE}" ]] || { echo "set MODIS_ARCHIVE in config.env" >&2; exit 2; }
[[ -n "${LAADS_TOKEN:-}" ]] || { echo "LAADS_TOKEN is not set in the environment" >&2; exit 4; }
doy_end="${doy_end:-${doy}}"

fetch() {
    # Usage: fetch <url> <out> <size>; resumes into .part and renames after a size check.
    local url="$1" out="$2" size="$3"
    if [[ -s "${out}" && "$(stat -c %s "${out}")" == "${size}" ]]; then return 0; fi
    timeout 1h curl -sS --fail -L --retry 5 --retry-delay 30 -H "Authorization: Bearer ${LAADS_TOKEN}" -C - -o "${out}.part" "${url}" \
        || { echo "  $(basename "${out}"): transfer failed, .part kept" >&2; return 1; }
    [[ "$(stat -c %s "${out}.part")" == "${size}" ]] || { echo "  $(basename "${out}"): size mismatch" >&2; return 1; }
    mv "${out}.part" "${out}"
}

nfail=0
for ((d = 10#${doy}; d <= 10#${doy_end}; d++)); do
    ddd="$(printf '%03d' "${d}")"
    dir="${MODIS_ARCHIVE}/${year}/${ddd}/MYD06_L2/${year}/${ddd}"; mkdir -p "${dir}"
    # Listing: one "name size" pair per granule, from the JSON index of the archive directory.
    mapfile -t items < <(curl -sS --fail -L "${LAADS_URL}/${year}/${ddd}.json" \
        | "${PYTHON}" -c 'import json, sys
d = json.load(sys.stdin)
for r in (d["content"] if isinstance(d, dict) and "content" in d else d):
    if r["name"].endswith(".hdf"):
        print(r["name"], r["size"])')
    (( ${#items[@]} )) || { echo "${year}-${ddd}: empty listing" >&2; nfail=$((nfail + 1)); continue; }
    echo "${year}-${ddd}: ${#items[@]} granules"
    for it in "${items[@]}"; do
        fetch "${LAADS_URL}/${year}/${ddd}/${it% *}" "${dir}/${it% *}" "${it#* }" &
        while (( $(jobs -rp | wc -l) >= PARALLEL )); do wait -n || nfail=$((nfail + 1)); done
    done
    while (( $(jobs -rp | wc -l) > 0 )); do wait -n || nfail=$((nfail + 1)); done
    echo "  $(find "${dir}" -name 'MYD06_L2.*.hdf' | wc -l) files in ${dir}"
done
echo "done, ${nfail} failures"
echo "${MODIS_ARCHIVE}/${year}"
[[ "${nfail}" -eq 0 ]]
