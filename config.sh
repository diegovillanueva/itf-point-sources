#!/usr/bin/env bash
# Shared configuration: loads config.env (if present), applies defaults and defines two helpers.
# Source it from every script: source "$(dirname "${BASH_SOURCE[0]}")/../config.sh"
# shellcheck disable=SC2034
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${REPO}/config.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${REPO}/config.env"
    set +a
fi
OUT_ROOT="${OUT_ROOT:-${REPO}/out}"
CCI_RAW="${CCI_RAW:-}"
CCI_S1_ARCHIVE="${CCI_S1_ARCHIVE:-}"
CCI_URL="${CCI_URL:-https://public.satproj.klima.dwd.de/data/ESA_Cloud_CCI/CLD_PRODUCTS/v3.0/L3U/AVHRR-PM}"
CLARA_MIRROR="${CLARA_MIRROR:-}"
CLARA_NETRC="${CLARA_NETRC:-}"
CLARA_ORDERS="${CLARA_ORDERS:-}"
CLARA_URL="${CLARA_URL:-https://cmsaf.dwd.de/data}"
MODIS_ARCHIVE="${MODIS_ARCHIVE:-}"
LAADS_URL="${LAADS_URL:-https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MYD06_L2}"
PARALLEL="${PARALLEL:-4}"
MEM_GB_PER_TASK="${MEM_GB_PER_TASK:-4}"
REWRITE="${REWRITE:-FALSE}"
PYTHON="${PYTHON:-python3}"

run_capped() {
    # Usage: run_capped <timeout> cmd...; runs cmd with a virtual-memory cap of MEM_GB_PER_TASK GB and one BLAS thread.
    local t="$1"; shift
    ( ulimit -v $(( MEM_GB_PER_TASK * 1024 * 1024 )); export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
      timeout "${t}" "$@" )
}

site_box() {
    # Usage: site_box <name>; prints lat_min,lat_max,lon_min,lon_max of the site's analysis box (sites.csv).
    ( cd "${REPO}" && "${PYTHON}" -m itf.sites "$1" )
}
