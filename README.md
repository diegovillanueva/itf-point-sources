# itf-point-sources

Ice-topped cloud fraction (ITF) as a function of cloud-top temperature (CTT) on the native 0.05 degree grid in
2 x 2 degree boxes around anthropogenic point sources (a city, a copper smelter, an oil refinery, a steel plant, two
cement plants), compared with randomly displaced control boxes. The question is whether aerosol from a point source
shifts the temperature at which supercooled liquid clouds glaciate, visible as a centre-versus-background change of
ITF at the same CTT. Inputs: ESA Cloud_cci v3 (1982-2016), CM SAF CLARA-A3 level-2b and NASA MODIS MYD06_L2 (2008).
Method: [docs/method.md](docs/method.md); products and phase rules: [docs/products.md](docs/products.md).

The repository bundles the pooled 1982-2016 Cloud_cci counts of the 12 sites (67 MB under `data/cci/`), so the main
figure is reproducible without any download.

## Example figures

All summary figures (including cloud occurrence and COT versions and profiles versus distance) and the commands that create them:
[summary_cci_figures/](summary_cci_figures/README.md).

ITF change at the six point sources and their control boxes, Cloud_cci 1982-2016. Top: centre (0-10 km) minus
background (70-100 km) ITF in percentage points for the year and each season, in two CTT ranges. Bottom: yearly ITF
versus CTT at the centre (red) and in the background (blue). Produced by the quick start below.

![ITF change at all sites](summary_cci_figures/itf_change_sites_1982-2016_cci_season.png)

Created with (writes `figs/cci_1982-2016/itf_change_sites_1982-2016_cci_season.png`):

```bash
bash scripts/run_sites.sh --root data --lane cci --year 1982-2016 --out-dir figs/cci_1982-2016 --no-maps
```

ITF maps of the 2 x 2 degree box around Moscow, Cloud_cci 1982-2016, for three CTT ranges (columns) and the
year, DJF and MAM (rows). Solid ring: 10 km; dashed rings: 70 and 100 km. Each map has its own colour range.

![ITF maps around Moscow](summary_cci_figures/itf_maps_moscow_1982-2016_cci.png)

Created with (writes `figs/cci_1982-2016/itf_maps_moscow_1982-2016_cci.png`; the DJF and MAM rows come from the
default `--seasons DJF MAM`):

```bash
python -m itf.plot_itf_maps --root data --box moscow --year 1982-2016 --months year --lanes cci --out-dir figs/cci_1982-2016
```

ITF versus distance from the site centre, Cloud_cci 1982-2016, 5 km rings. One panel per box, one line per 3 K
CTT bin from -1.5 °C (yellow) to -34.5 °C (dark), each minus its own 70-100 km value (grey band), in percentage
points.

![ITF versus distance](summary_cci_figures/itf_distance_3K_1982-2016_cci.png)

Created with (writes `figs/cci_1982-2016/itf_distance_3K_1982-2016_cci.png`, plus occurrence, COT and 12 K versions
and `itf_distance_1982-2016_cci.csv`):

```bash
python -m itf.plot_itf_distance --root data --lane cci --year 1982-2016 --out-dir figs/cci_1982-2016
```

## Layout

```
sites.csv            site table (name, label, lat, lon, type, control_of); single source of truth
itf/                 python package: ctt_bins, modis_geo, sites, itf_day, itf_agg, itf_pool, index_modis,
                     plot_itf_change, plot_itf_change_sites, plot_itf_maps, plot_itf_distance
scripts/             bash drivers: cci_download, cci_select, clara_stage, modis_download, run_itf, run_year, run_sites
config.env.example   paths and resources (copy to config.env); config.sh applies the defaults
data/cci/<site>/     bundled counts: 1982-2016.nc (all years summed) and 1982-2016/MM.nc (per calendar month)
tests/               pytest unit test, synthetic-day generator and the end-to-end smoke test
docs/                method.md, products.md
```

## Installation

```bash
conda env create -f environment.yml && conda activate itf
cp config.env.example config.env     # edit the paths; only needed for the recompute from raw data
pytest tests && bash tests/test_smoke.sh
```

Requirements: Python >= 3.9 with numpy, netCDF4 and matplotlib; cartopy for the maps; pyhdf for MODIS; cdo for the
Cloud_cci subsets; wget and curl for the downloads. Run every command from the repository root, where the package
`itf` is importable (`python -m itf.<module> --help` shows the options of each tool).

## Quick start: the 1982-2016 Cloud_cci figure from the bundled data

```bash
bash scripts/run_sites.sh --root data --lane cci --year 1982-2016 --out-dir figs/cci_1982-2016 --no-maps
```

This runs `plot_itf_change.py` for the 12 sites and `plot_itf_change_sites.py` for the combined figures; the result
of interest is `figs/cci_1982-2016/itf_change_sites_1982-2016_cci_season.png` (ITF change per site and control
for the year and the four seasons, with the ITF(CTT) profiles). Each figure comes with a `.md` file describing it,
and each site with `itf_change_<site>_1982-2016_cci.csv` (medians, cell counts and changes per month and CTT range)
and `itf_profile_<site>_1982-2016_cci.csv` (per 3 K bin). The same by hand:

```bash
python -m itf.plot_itf_change --root data --box moscow --year 1982-2016 --lanes cci --out-dir figs/cci_1982-2016
python -m itf.plot_itf_change_sites --fig-dir figs/cci_1982-2016 --year 1982-2016 --lane cci --seasons
python -m itf.plot_itf_maps --root data --box moscow --year 1982-2016 --lanes cci --out-dir figs/cci_1982-2016
```

## Recomputing from raw data (example: Moscow and its control, Cloud_cci, 2008)

Set `CCI_RAW`, `CCI_S1_ARCHIVE` and `OUT_ROOT` in `config.env` (one year of raw files is about 330 GB; the subsets
are about a tenth of that), then:

```bash
bash scripts/cci_download.sh --year 2008                   # raw daily files -> CCI_RAW/2008/MM/
bash scripts/cci_select.sh --year 2008                     # cdo subsets -> CCI_S1_ARCHIVE/{intensive,extensive}/2008/MM/
for s in moscow moscow_ctl; do
    bash scripts/run_year.sh --product cci --site "$s" --year 2008      # daily counts, then monthly and yearly files
done
bash scripts/run_sites.sh --root "$OUT_ROOT" --lane cci --year 2008 --out-dir figs/cci_2008 --sites "moscow moscow_ctl"
```

`run_itf.sh` handles one month (or one day with `--day`) and skips existing outputs; `run_year.sh` loops over the
months and calls `itf_agg.py`. Several years are pooled with
`python -m itf.itf_pool --agg-dir "$OUT_ROOT/cci/moscow" --years 1982 2016`, which writes the layout of `data/cci/`.
The other lanes work the same way after staging their inputs: `scripts/clara_stage.sh --year 2008` (CM SAF order
numbers and netrc path in `config.env`) and `LAADS_TOKEN=... bash scripts/modis_download.sh --year 2008 --doy 1 --doy-end 366`,
then `run_year.sh --product clara|modis|modis5`. A new site is one line in `sites.csv`.

## Outputs

```
OUT_ROOT/<lane>/daily/<site>/YYYY/MM/DD.nc   per day: n_liq, n_ice, n_mix, n_und, n_ctt (time, lat, lon, cosp_ht),
                                             n_obs (time, lat, lon), cot_sum and n_cot, itf; attributes with the
                                             phase rule and the source files
OUT_ROOT/<lane>/<site>/YYYY/MM.nc            the days of a month (one time step each); YYYY.nc the yearly sum
OUT_ROOT/<lane>/<site>/<a>-<b>.nc, <a>-<b>/MM.nc   multi-year pools (itf_pool.py)
OUT_ROOT/modis/index/YYYY/DDD.json           granule index of the MODIS lanes
figs/<dir>/itf_change_<site>_<year>_<lanes>.{png,md,csv}, itf_profile_<site>_<year>_<lane>.csv,
           itf_change_sites_<year>_<lane>[_season].{png,md}, itf_maps_<site>_<year>_<lanes>.{png,md}
figs/<dir>/<var>_distance_{12K,3K}_<year>_<lane>.{png,md}, itf_distance_<year>_<lane>.csv   (plot_itf_distance.py)
```

The CTT axis `cosp_ht` holds the 40 bin centres (-91.5 ... 25.5 degC) with bounds `ctt_bnds` in K.

## Tests

- `pytest tests`: CTT bin edges and bin assignment.
- `bash tests/test_smoke.sh`: three synthetic Cloud_cci days for the Moscow box through `run_itf.sh`, `run_year.sh`
  and `plot_itf_change.py`; checks the pixel counts and the expected +200 % change at the centre.

## Citation and license

BSD 3-Clause (see `LICENSE`). Please cite the repository (`CITATION.cff`) and the data providers: ESA Cloud_cci v3
(Stengel et al., 2020, https://doi.org/10.5194/essd-12-41-2020), EUMETSAT CM SAF CLARA-A3 (Karlsson et al., 2023,
https://doi.org/10.5194/essd-15-4901-2023) and NASA MODIS Aqua MYD06_L2 collection 6.1 (Platnick et al., 2017,
https://doi.org/10.5067/MODIS/MYD06_L2.061).
