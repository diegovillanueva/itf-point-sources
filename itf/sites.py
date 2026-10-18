"""Site table: sites.csv in the repository root is the single source of truth.

Columns: name, label, lat, lon, type, control_of. Control sites are random offsets of 150-200 km from
their source (seed 2008) and share the source's analysis settings.

Command line: python -m itf.sites <name>  prints the lat_min,lat_max,lon_min,lon_max box of a site;
              python -m itf.sites --list  prints all names.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import NamedTuple

SITES_CSV = Path(__file__).resolve().parent.parent / "sites.csv"
HALF_DEG = 1.0   # the analysis box is lat +- 1 deg, lon +- 1 deg around the site (40 x 40 cells of 0.05 deg)


class Site(NamedTuple):
    name: str
    label: str
    lat: float
    lon: float
    type: str
    control_of: str


def load_sites(path: Path = SITES_CSV) -> dict[str, Site]:
    """Sites keyed by name, in file order."""
    with path.open(newline="") as fh:
        return {r["name"]: Site(r["name"], r["label"], float(r["lat"]), float(r["lon"]), r["type"], r["control_of"])
                for r in csv.DictReader(fh)}


SITES = load_sites()


def site_box(name: str) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) of the analysis box around a site."""
    s = SITES[name]
    return (s.lat - HALF_DEG, s.lat + HALF_DEG, s.lon - HALF_DEG, s.lon + HALF_DEG)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("name", nargs="?")
    p.add_argument("--list", action="store_true")
    a = p.parse_args()
    if a.list or not a.name:
        print("\n".join(SITES))
        return
    if a.name not in SITES:
        raise SystemExit(f"unknown site {a.name}; known: {', '.join(SITES)}")
    print(",".join(f"{v:.4f}" for v in site_box(a.name)))


if __name__ == "__main__":
    main()
