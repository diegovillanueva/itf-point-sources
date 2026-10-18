# Method

## Question

Does aerosol from an anthropogenic point source (a city, a smelter, a refinery, cement plants) shift the temperature
at which supercooled liquid clouds glaciate? The observable is the ice-topped fraction ITF of cloudy pixels as a
function of cloud-top temperature (CTT), compared between the box centre and a background ring in the same box.

## Definitions

- ITF = n_ice / (n_ice + n_liq + n_mix): fraction of phase-determined cloudy pixels whose retrieved cloud-top phase is
  ice, per 0.05 degree cell and CTT bin. n_mix (MODIS infrared phase 3) joins the liquid side by default
  (`--mixed liquid` in itf_day.py); undetermined pixels (n_und) are excluded.
- CTT bins: 40 bins of 3 K with centres from -91.5 to 25.5 degC (`itf/ctt_bins.py`). Edges are built in K with
  two-decimal rounding and compared in float32; a CTT exactly on an edge belongs to no bin.
- Box: lat +- 1 degree, lon +- 1 degree around the site (40 x 40 cells of 0.05 degree). Cell centres are the
  regular 0.05 degree grid of the Cloud_cci and CLARA level-3/2b products; MODIS pixels are geolocated onto it.
- Centre: cells within 0-10 km of the site; background: cells 70-100 km away (equirectangular distance). At 50-60
  degrees N the box reaches only 62-70 km east and west, so the background ring consists of its north and south arcs.
- Target CTT ranges: 0..-12, -12..-24 and -24..-36 degC (four native bins each). Cells with fewer than 3 phase samples
  in a range are dropped (`MIN_N` in `itf/plot_itf_change.py`).

## Pipeline

1. `itf_day.py` reads one day of one product for the box and counts, per cell and CTT bin, the liquid, ice, mixed,
   undetermined and CTT-valid pixels plus the observed pixels per cell (`n_obs`) and the sum of cloud optical thickness
   (`cot_sum`, `n_cot`). The products and their phase rules are listed in `products.md`.
2. `itf_agg.py` concatenates the days of a month (`YYYY/MM.nc`, one time step per day) and sums the counts of the year
   (`YYYY.nc`). `itf_pool.py` sums several years into `<a>-<b>.nc` and per calendar month into `<a>-<b>/MM.nc`.
   Counts are summed, never averaged, so every cloudy pixel has the same weight (occurrence weighting).
3. `plot_itf_change.py` computes, per month and target range, the median cell ITF of the centre and of the background,
   the relative change 100 x (centre / background - 1) [%], the absolute difference in percentage points and the
   change normalised by the supercooled background fraction 100 x (ITF_c - ITF_bg) / (1 - ITF_bg) [%]. Yearly values
   weight the months by cloud occurrence (phase samples in centre + ring). ITF(CTT) profiles per 3 K bin are written
   for the year and the seasons.
4. `plot_itf_change_sites.py` collects the per-site CSV tables into one figure of all sites and their controls.
   `plot_itf_maps.py` maps ITF per target range for a site.

## Controls

Each source has a control box whose centre is displaced by a random 150-200 km in a random direction (drawn once with
numpy `default_rng(2008)` and stored in `sites.csv`). The controls give the noise range of the centre-vs-background
change at a site without a point source; a source signal must exceed the spread of the controls.

## Caveats

- The products differ in sensor, phase algorithm, overpass time and daytime restriction (`products.md`); compare lanes
  qualitatively, not value by value.
- Cloud_cci AVHRR-PM covers 1982-2016 with afternoon satellites that drift in local time; the bundled data pool all
  years, so a decadal trend in overpass time contributes to the climatology but cancels in the centre-minus-background
  difference.
- A relative change is undefined when the background median is 0 (`n/a`), and the normalised change is unreliable
  where the supercooled background fraction is below about 20 %.
