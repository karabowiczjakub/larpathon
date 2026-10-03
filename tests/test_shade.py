import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.contracts import SunPosition
from app.shade.mock import MockShade
from app.shade.model import ShadeModel
from app.shade.sun import sun_position

TZ = ZoneInfo("Europe/Warsaw")
NOON = datetime(2025, 7, 3, 14, tzinfo=TZ)
AZ = np.arange(0, 360, 22.5)
EL = np.array([5, 10, 15, 20, 30, 40, 50, 65])


@pytest.fixture
def model():
    table = np.zeros((3, 16, 8), dtype=np.uint8)
    table[1] = 255
    table[2, 0, :] = np.arange(8) * 30
    return ShadeModel(table, np.array([0, 1, 0.5]), AZ, EL)


def test_solar_position_and_timezone():
    sun = sun_position(NOON)
    assert 200 < sun.azimuth_deg < 230
    assert 55 < sun.elevation_deg < 63
    assert sun == sun_position(NOON.astimezone(timezone.utc))
    evening = sun_position(NOON.replace(hour=18, minute=30))
    assert 275 < evening.azimuth_deg < 290
    assert 15 < evening.elevation_deg < 25


def test_naive_datetime_rejected(model):
    with pytest.raises(ValueError, match="timezone-aware"):
        model.edge_shade(datetime(2025, 7, 3, 14))  # noqa: DTZ001 — intentional invalid input


def test_dst_fold_uses_different_instants(model):
    a = datetime(2025, 10, 26, 2, 30, tzinfo=TZ, fold=0)
    b = a.replace(fold=1)
    assert model.sun(a) != model.sun(b)


@pytest.mark.parametrize("elevation", [-90, -1, 0])
def test_night(model, monkeypatch, elevation):
    monkeypatch.setattr(model, "sun", lambda at: SunPosition(0, elevation))
    assert np.array_equal(model.edge_shade(NOON), np.ones(3))


@pytest.mark.parametrize("elevation, expected", [(1e-12, 0), (7.5, 15), (90, 210)])
def test_elevation_interpolation_and_clamping(model, monkeypatch, elevation, expected):
    monkeypatch.setattr(model, "sun", lambda at: SunPosition(359, elevation))
    values = model.edge_shade(NOON)
    assert values[2] == pytest.approx(expected / 255)
    assert values.dtype == np.float32
    assert np.isfinite(values).all()
    assert ((0 <= values) & (values <= 1)).all()


def test_cache_is_deterministic_and_cannot_be_overwritten(model):
    a = model.edge_shade(NOON)
    b = model.edge_shade(NOON.astimezone(timezone.utc))
    assert a is b
    with pytest.raises(ValueError):
        a[0] = 0.5
    with pytest.raises(ValueError):
        model.table[0, 0, 0] = 255


def test_separate_model_caches(model):
    other = ShadeModel(np.full((3, 16, 8), 255, np.uint8), np.zeros(3), AZ, EL)
    assert other.edge_shade(NOON)[0] == 1
    assert model.edge_shade(NOON)[0] == 0


def test_load_and_wrong_graph(tmp_path, model):
    np.save(tmp_path / "shade.npy", model.table)
    np.save(tmp_path / "edge_tree_frac.npy", model.edge_tree_frac)
    (tmp_path / "shade_bins.json").write_text(
        json.dumps({"az": AZ.tolist(), "el": EL.tolist()})
    )
    loaded = ShadeModel.load(tmp_path, 3)
    np.testing.assert_array_equal(loaded.edge_shade(NOON), model.edge_shade(NOON))
    with pytest.raises(ValueError, match="another graph"):
        ShadeModel.load(tmp_path, 4)


def test_missing_artifact_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError):
        ShadeModel.load(tmp_path, 3)


@pytest.mark.parametrize("tree", [[float("nan")], [float("inf")], [-0.1], [1.1], []])
def test_invalid_tree_fraction(tree):
    with pytest.raises(ValueError):
        ShadeModel(np.zeros((1, 16, 8), np.uint8), tree, AZ, EL)


def test_mock_and_empty_graph():
    a, b = MockShade(3), MockShade(3)
    np.testing.assert_array_equal(a.edge_shade(NOON), b.edge_shade(NOON))
    assert np.all(a.edge_shade(NOON.replace(hour=23)) == 1)
    assert MockShade(0).edge_shade(NOON).shape == (0,)


def test_runtime_without_network(model, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Runtime must not use the network")

    monkeypatch.setattr("socket.socket.connect", no_network)
    assert model.edge_shade(NOON).shape == (3,)
    assert np.all(model.edge_shade(NOON.replace(hour=23)) == 1)


def test_time_changes_interpolation_cache(model, monkeypatch):
    monkeypatch.setattr(model, "sun", lambda at: SunPosition(0, at.hour))
    early = model.edge_shade(NOON.replace(hour=5))
    later = model.edge_shade(NOON.replace(hour=10))
    assert later[2] > early[2]


@pytest.mark.parametrize(
    "az, el", [([0, 0], [5]), ([360], [5]), ([0], [0]), ([0], [float("nan")])]
)
def test_invalid_bins(az, el):
    with pytest.raises(ValueError):
        ShadeModel(np.zeros((1, len(az), len(el)), np.uint8), [0], az, el)
