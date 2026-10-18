# Input products and their phase rules

All lanes count pixels on (or geolocated onto) the regular 0.05 degree grid. The phase rule of each lane is stored
in the `phase_rule` attribute of every output file (`PHASE_RULE` in `itf/itf_day.py`).

| Lane | Product | Years used | Input directory |
|---|---|---|---|
| `cci` | ESA Cloud_cci v3.0 L3U AVHRR-PM daily, 0.05 degree (Stengel et al., 2020) | 1982-2016 | `CCI_S1_ARCHIVE/{extensive,intensive}/YYYY/MM/` |
| `clara` | EUMETSAT CM SAF CLARA-A3 instantaneous level-2b, NOAA-18 (Karlsson et al., 2023) | 2008 | `CLARA_MIRROR/{CMA,CPH,CTO,CWP}/YYYY/MM/` |
| `modis` | NASA Aqua MODIS MYD06_L2 collection 6.1, 1 km infrared phase and CTT (Platnick et al., 2017) | 2008 | `MODIS_ARCHIVE/YYYY/DDD/MYD06_L2/YYYY/DDD/` |
| `modis5` | the same granules at 5 km (Cloud_Phase_Infrared, Cloud_Top_Temperature) | 2008 | as `modis` |

## cci

- Download: `scripts/cci_download.sh` mirrors the public daily files (about 0.9 GB each) from
  `https://public.satproj.klima.dwd.de/data/ESA_Cloud_CCI/CLD_PRODUCTS/v3.0/L3U/AVHRR-PM/<satellite>/YYYY/MM/`. The
  satellite directory (`AVHRR_NOAA-7` ... `AVHRR_NOAA-19`) is discovered from the server index.
- Subsets: `scripts/cci_select.sh` keeps the ascending (afternoon) node only. `intensive/`: `ctt = ctt_corrected_asc`,
  `cot = cot_asc`; `extensive/`: `cvf_liq = (cph_asc == 1)`, `cvf_ice = (cph_asc == 2)`,
  `cwp_ext = cwp_asc * (cvf_ice + cvf_liq)`. Both keep the raw file names.
- Phase rule: `cvf_liq == 1` liquid, `cvf_ice == 1` ice, both 0 clear, fill not observed. No illumination or quality
  flags are applied.
- Archive gaps: 1994 (61 days), 1995 (31 days) and a few single days.

## clara

- Access: CLARA-A3 level-2b files are delivered by CM SAF (https://wui.cmsaf.eu) as one order per product; the
  instantaneous 0.05 degree level-2b files are needed, not the daily-mean level-3 products at 0.25 degree. One year of
  the four products is about 190 GB.
- Staging: `scripts/clara_stage.sh` downloads the order tars with the credentials of a netrc file (`CLARA_NETRC`) and
  unpacks them into `CLARA_MIRROR/<product>/YYYY/MM/`. Order numbers go into `CLARA_ORDERS` in `config.env`.
- Phase rule: `cph_asc` 1 liquid, 2 ice (both only where `cma_asc == 1`), 0 clear, fill not observed; CTT from
  `ctt_asc`; ascending node only.

## modis and modis5

- Access: `scripts/modis_download.sh` lists a day with the public JSON index of the LAADS archive
  (`https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MYD06_L2/YYYY/DDD.json`) and downloads the granules
  with an Earthdata or LAADS bearer token from the environment variable `LAADS_TOKEN`. One day is about 288 granules
  and 16.5 GB.
- Index: `itf/index_modis.py` writes the bounding box and minimum solar zenith angle of each granule to
  `OUT_ROOT/modis/index/YYYY/DDD.json`; `scripts/run_itf.sh` does this before the first use of a day.
- Phase rule (1 km): `Cloud_Phase_Infrared_1km` 1 liquid, 3 mixed (`n_mix`), 2 ice, 6 undetermined (`n_und`),
  0 clear; daytime pixels only (`Cloud_Mask_1km` byte 0 bit 3 and solar zenith < 81.36 degrees) with a determined cloud
  mask (bit 0); `ctt = cloud_top_temperature_1km`. The optical-properties phase gives the diagnostic `itf_op`.
  The 1 km pixels are geolocated by upsampling the 5 km latitude and longitude fields.
- Phase rule (5 km): the same with `Cloud_Phase_Infrared`, `Cloud_Mask_5km`, `Solar_Zenith` and
  `Cloud_Top_Temperature`; no optical phase.

## References

- Stengel, M. et al. (2020): Cloud_cci Advanced Very High Resolution Radiometer post meridiem (AVHRR-PM) dataset
  version 3, Earth Syst. Sci. Data, 12, 41-60, https://doi.org/10.5194/essd-12-41-2020
- Karlsson, K.-G. et al. (2023): CLARA-A3: The third edition of the AVHRR-based CM SAF climate data record on clouds,
  radiation and surface albedo, Earth Syst. Sci. Data, 15, 4901-4926, https://doi.org/10.5194/essd-15-4901-2023
- Platnick, S. et al. (2017): MODIS Atmosphere L2 Cloud Product (06_L2), Aqua, collection 6.1,
  https://doi.org/10.5067/MODIS/MYD06_L2.061
