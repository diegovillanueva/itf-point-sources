"""Unit tests of the CTT binning (run: pytest tests)."""
import numpy as np

from itf.ctt_bins import CENTERS, bin_index, edges_kelvin


def test_centers_and_edges() -> None:
    assert len(CENTERS) == 40
    assert CENTERS[0] == -91.5 and CENTERS[-1] == 25.5
    e = edges_kelvin()
    assert len(e) == 41
    assert np.allclose(np.diff(e), 3.0)
    assert e[0] == 180.15 and e[-1] == 300.15


def test_bin_index_values() -> None:
    ctt = np.array([256.15, 273.15 - 0.5, 180.15 + 0.1, 300.15 - 0.1], "f4")
    assert bin_index(ctt).tolist() == [25, 30, 0, 39]
    assert CENTERS[25] == -16.5


def test_bin_index_edges_and_missing() -> None:
    e = edges_kelvin().astype("f4")
    assert (bin_index(e) == -1).all()                           # exactly on an edge: no bin
    assert bin_index(np.array([np.nan, 100.0, 400.0], "f4")).tolist() == [-1, -1, -1]
