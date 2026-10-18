#!/usr/bin/env bash
# End-to-end smoke test on synthetic data: three synthetic Cloud_cci days -> run_itf.sh (itf_day.py) -> itf_agg.py ->
# plot_itf_change.py, checking the daily counts and the expected +200 % ITF change at the site centre.
# Usage: bash tests/test_smoke.sh [work dir]   (default: a temporary directory, removed on success)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="${1:-$(mktemp -d)}"
mkdir -p "${work}"
site=moscow
cd "${REPO}"
export OUT_ROOT="${work}/out" CCI_S1_ARCHIVE="${work}/cci" PARALLEL=2
PYTHON="${PYTHON:-python3}"
for i in 0 1 2; do
    "${PYTHON}" -m tests.make_synthetic_day --archive "${CCI_S1_ARCHIVE}" --site "${site}" --date "2008-01-0$((i + 1))" --day-index "${i}" | head -1
done
for d in 01 02 03; do
    bash scripts/run_itf.sh --product cci --site "${site}" --year 2008 --month 01 --day "${d}" >/dev/null
done
"${PYTHON}" - "${OUT_ROOT}/cci/daily/${site}/2008/01" <<'EOF'
import sys
from pathlib import Path
import netCDF4 as nc
d = Path(sys.argv[1])
files = sorted(d.glob("[0-9][0-9].nc"))
assert len(files) == 3, files
for k, f in enumerate(files):
    with nc.Dataset(f) as ds:
        liq, ice = int(ds["n_liq"][:].sum()), int(ds["n_ice"][:].sum())
        nobs = int(ds["n_obs"][:].sum())
        assert ds["cosp_ht"].shape == (40,)
        assert ds["n_ice"][0, :, :, 25].sum() == ice, "all ice pixels must fall in the -18..-15 degC bin"
    assert nobs == 1600 and liq + ice == 1600, (f, nobs, liq, ice)
    if k == 0:
        assert liq == 0 and ice == 1600, (liq, ice)
    else:
        assert 0 < ice < 20 and liq == 1600 - ice, (liq, ice)
    print(f"{f.name}: n_obs {nobs}, liq {liq}, ice {ice}")
EOF
bash scripts/run_year.sh --product cci --site "${site}" --year 2008 --months "01" >/dev/null
test -s "${OUT_ROOT}/cci/${site}/2008/01.nc" && test -s "${OUT_ROOT}/cci/${site}/2008.nc"
"${PYTHON}" -m itf.plot_itf_change --root "${OUT_ROOT}" --box "${site}" --year 2008 --lanes cci --out-dir "${work}/figs" >/dev/null
csv="${work}/figs/itf_change_${site}_2008_cci.csv"
row="$(grep '^cci,2008-01,-12..-24,' "${csv}" | tr -d '\r')"   # csv rows end in CRLF
echo "${row}"
IFS=, read -r _ _ _ cen bg chg ncen nbg norm _ diff <<<"${row}"
[[ "${cen}" == 1.000 && "${bg}" == 0.333 && "${chg}" == 200.0 && "${norm}" == 100.0 && "${diff}" == 66.7 ]] || { echo "unexpected ITF change row: ${row}" >&2; exit 1; }
[[ "${ncen}" -gt 0 && "${nbg}" -gt 0 ]]
test -s "${work}/figs/itf_change_${site}_2008_cci.png"
echo "smoke test passed (centre ${ncen} cells, background ${nbg} cells)"
[[ $# -gt 0 ]] || rm -rf "${work}"
