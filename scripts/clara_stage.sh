#!/usr/bin/env bash
# Mirror CM SAF order tars of CLARA-A3 level-2b (instantaneous, 0.05 degree) and unpack the daily files.
# Usage: bash scripts/clara_stage.sh --year YYYY [--month MM] [--day DD] [--verify] [--delete-tars]
# Tars -> ${CLARA_MIRROR}/tars/ORD<id>_NN.tar (+ .list index); members -> ${CLARA_MIRROR}/<CMA|CPH|CTO|CWP>/YYYY/MM/<name>.nc.
# Orders come from CLARA_ORDERS ("CMA:<id> CPH:<id> CTO:<id> CWP:<id>"); credentials only via --netrc-file "${CLARA_NETRC}".
# Resumable: curl -C - into .part, size checked against the server listing; REWRITE=TRUE re-extracts existing members.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
year=""; month=""; day=""; VERIFY=FALSE; DELETE_TARS=FALSE
while [[ $# -gt 0 ]]; do
    case "$1" in
        --year) year="$2"; shift 2 ;;
        --month) month="$2"; shift 2 ;;
        --day) day="$2"; shift 2 ;;
        --verify) VERIFY=TRUE; shift ;;
        --delete-tars) DELETE_TARS=TRUE; VERIFY=TRUE; shift ;;
        *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ -n "${year}" ]] || { echo "--year is required" >&2; exit 2; }
[[ -n "${CLARA_MIRROR}" && -n "${CLARA_ORDERS}" ]] || { echo "set CLARA_MIRROR and CLARA_ORDERS in config.env" >&2; exit 2; }
[[ -r "${CLARA_NETRC}" ]] || { echo "netrc ${CLARA_NETRC} not readable" >&2; exit 4; }
[[ -n "${month}" ]] && month="$(printf '%02d' "$((10#${month}))")"
[[ -n "${day}" ]] && day="$(printf '%02d' "$((10#${day}))")"
TARS="${CLARA_MIRROR}/tars"; mkdir -p "${TARS}"
CURL=(curl -sS --fail --netrc-file "${CLARA_NETRC}" --retry 5 --retry-delay 30 --connect-timeout 60)

listing() {
    # Usage: listing <order id>; prints "name size" for every tar of the order.
    "${CURL[@]}" "${CLARA_URL}/ORD$1/" | sed 's/<[^>]*>/ /g' | tr -d '\r' | awk '$1 ~ /\.tar$/ {print $1, $NF}'
}

dest_of() {
    # Usage: dest_of <root> <member name>; e.g. CTOin20080101000000323AVN1801GL.nc -> <root>/CTO/2008/01/<name>.
    echo "$1/${2:0:3}/${2:5:4}/${2:9:2}/$2"
}

fetch_tar() {
    # Usage: fetch_tar <order> <name> <size>; resumes into .part, writes <name>.list after a size-checked download.
    local ord="$1" name="$2" size="$3" out="${TARS}/$2"
    if [[ -s "${out}" && "$(stat -c %s "${out}")" == "${size}" && -s "${out}.list" ]]; then return 0; fi
    if [[ ! -s "${out}" ]]; then
        [[ -s "${out}.part" && "$(stat -c %s "${out}.part")" == "${size}" ]] \
            || timeout 6h "${CURL[@]}" -C - -o "${out}.part" "${CLARA_URL}/ORD${ord}/${name}" || { echo "  ${name}: transfer failed, .part kept" >&2; return 1; }
        [[ "$(stat -c %s "${out}.part")" == "${size}" ]] || { echo "  ${name}: size $(stat -c %s "${out}.part") != ${size}" >&2; return 1; }
        mv "${out}.part" "${out}"
    fi
    tar tvf "${out}" | awk '{print $6, $3}' > "${out}.list.tmp" && mv "${out}.list.tmp" "${out}.list"
    echo "  ok ${name} ($(wc -l < "${out}.list") files, $(awk -v s="${size}" 'BEGIN{printf "%.2f", s/1e9}') GB)"
}

tar_done() {
    # Usage: tar_done <list> <pattern>; true when every listed member matching the pattern is already in the mirror.
    local n s d
    while read -r n s; do
        d="$(dest_of "${CLARA_MIRROR}" "${n}")"
        [[ -s "${d}" && "$(stat -c %s "${d}")" == "${s}" ]] || return 1
    done < <(grep "^$2" "$1")
}

unpack_tar() {
    # Usage: unpack_tar <tar>; extracts the members still missing (or all with REWRITE) into the mirror tree.
    local t="$1" tmp need=() n s d
    while read -r n s; do
        d="$(dest_of "${CLARA_MIRROR}" "${n}")"
        [[ "${REWRITE}" == TRUE || ! -s "${d}" || "$(stat -c %s "${d}")" != "${s}" ]] && need+=("${n}")
    done < "${t}.list"
    (( ${#need[@]} )) || return 0
    tmp="$(mktemp -d "${TARS}/.x.XXXX")"
    timeout 2h tar xf "${t}" -C "${tmp}" "${need[@]}" || { echo "  $(basename "${t}"): extract failed" >&2; rm -rf "${tmp}"; return 1; }
    for n in "${need[@]}"; do d="$(dest_of "${CLARA_MIRROR}" "${n}")"; mkdir -p "$(dirname "${d}")"; mv -f "${tmp}/${n}" "${d}"; done
    rmdir "${tmp}"; echo "  $(basename "${t}"): ${#need[@]} files unpacked"
}

pat="${year}${month:-..}${day:-..}"
nfail=0
for po in ${CLARA_ORDERS}; do
    prod="${po%%:*}" ord="${po##*:}"
    echo "${prod} ORD${ord}"
    mapfile -t tars < <(listing "${ord}")
    (( ${#tars[@]} )) || { echo "ORD${ord} listing empty or unreachable" >&2; nfail=$((nfail + 1)); continue; }
    for ts in "${tars[@]}"; do
        name="${ts% *}" size="${ts#* }"
        if [[ -s "${TARS}/${name}.list" ]]; then
            grep -q "^${prod}in${pat}" "${TARS}/${name}.list" || continue
            [[ "${REWRITE}" != TRUE ]] && tar_done "${TARS}/${name}.list" "${prod}in${pat}" && continue
        fi
        fetch_tar "${ord}" "${name}" "${size}" &
        while (( $(jobs -rp | wc -l) >= PARALLEL )); do wait -n || nfail=$((nfail + 1)); done
    done
    while (( $(jobs -rp | wc -l) > 0 )); do wait -n || nfail=$((nfail + 1)); done
    for ts in "${tars[@]}"; do
        t="${TARS}/${ts% *}"
        [[ -s "${t}" && -s "${t}.list" ]] && grep -q "^${prod}in${pat}" "${t}.list" || continue
        [[ "${REWRITE}" != TRUE ]] && tar_done "${t}.list" "${prod}in${pat}" && continue
        unpack_tar "${t}" &
        while (( $(jobs -rp | wc -l) >= PARALLEL )); do wait -n || nfail=$((nfail + 1)); done
    done
    while (( $(jobs -rp | wc -l) > 0 )); do wait -n || nfail=$((nfail + 1)); done
    got="$(find "${CLARA_MIRROR}/${prod}/${year}" -name "${prod}in${pat//./?}*.nc" 2>/dev/null | wc -l || true)"
    want="$(cat "${TARS}"/ORD"${ord}"_*.list 2>/dev/null | grep -c "^${prod}in${pat}" || true)"
    echo "${prod} ${pat}: ${got}/${want} files in ${CLARA_MIRROR}/${prod}/${year}"
    [[ "${got}" -ge "${want}" && "${want}" -gt 0 ]] || nfail=$((nfail + 1))
done

if [[ "${VERIFY}" == TRUE ]]; then
    bad=0
    for l in "${TARS}"/*.list; do
        while read -r n s; do
            d="$(dest_of "${CLARA_MIRROR}" "${n}")"
            [[ -s "${d}" && "$(stat -c %s "${d}")" == "${s}" ]] || { echo "  ${n} missing or wrong size" >&2; bad=$((bad + 1)); }
        done < "${l}"
    done
    echo "verify: $(cat "${TARS}"/*.list | wc -l) members, ${bad} bad"
    if [[ "${DELETE_TARS}" == TRUE && "${bad}" -eq 0 && "${nfail}" -eq 0 ]]; then
        find "${TARS}" -name '*.tar' -delete; echo "tars deleted (indexes kept)"
    fi
    nfail=$((nfail + bad))
fi
echo "done, ${nfail} failures"
echo "${CLARA_MIRROR}"
[[ "${nfail}" -eq 0 ]]
