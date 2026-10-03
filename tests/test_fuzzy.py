import numpy as np
import pytest
import os
from app.env.fuzzy_profiles import PROFILES

pytestmark = pytest.mark.skipif(
    not os.path.exists("data/processed/lut_standard.npy"),
    reason="LUT nie zostały wygenerowane — uruchom: python pipeline/fuzzy_build.py"
)

@pytest.mark.parametrize("name", list(PROFILES))
def test_lut_complete_and_monotone(name):
    lut = np.load(f"data/processed/lut_{name}.npy")
    g = np.load("data/processed/lut_grid.npz")

    assert not np.isnan(lut).any(), f"{name}: NaN w LUT"
    assert (np.diff(lut, axis=1) >= -1e-6).all(), f"{name}: gorsze powietrze obniżyło dyskomfort"
    assert (np.diff(lut, axis=2) >= -1e-6).all(), f"{name}: wyższe UV obniżyło dyskomfort"

    hot = g["heat"] >= 22 + PROFILES[name]["heat_shift"]
    assert (np.diff(lut[hot], axis=0) >= -1e-6).all(), f"{name}: większy upał obniżył dyskomfort"


def test_profiles_order():
    s  = np.load("data/processed/lut_standard.npy")
    a  = np.load("data/processed/lut_asthma.npy")
    sen = np.load("data/processed/lut_senior.npy")
    assert (a >= s - 0.5).all(),      "asthma nigdy wyraźnie łagodniejsza niż standard"
    assert sen.mean() >= s.mean(),    "senior średnio nie łagodniejszy niż standard"
