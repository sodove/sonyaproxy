import os
import tempfile
import pytest
import yaml
from flavor import FlavorConfig, ReleaseDayBoost, load_flavor, compute_quotas


def test_load_flavor_defaults(tmp_path):
    flavor = load_flavor(str(tmp_path / "nonexistent.yml"))
    assert isinstance(flavor, FlavorConfig)
    assert "electronic" in flavor.genres
    assert flavor.max_tracks_per_cycle == 20
    assert flavor.refresh_interval_hours == 12
    assert "RU" in flavor.chart_regions


def test_load_flavor_from_yaml(tmp_path):
    cfg = {
        "genres": {"pop": 0.5, "jazz": 0.5},
        "languages": {"en": 1.0},
        "chart_regions": ["GB"],
        "refresh_interval_hours": 6,
        "max_tracks_per_cycle": 10,
    }
    p = tmp_path / "flavor.yml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    flavor = load_flavor(str(p))
    assert flavor.genres == {"pop": 0.5, "jazz": 0.5}
    assert flavor.chart_regions == ["GB"]
    assert flavor.refresh_interval_hours == 6
    assert flavor.max_tracks_per_cycle == 10


def test_compute_quotas_basic():
    flavor = FlavorConfig(
        genres={"electronic": 0.6, "rock": 0.4},
        chart_regions=["US"],
        max_tracks_per_cycle=10,
    )
    quotas = compute_quotas(flavor)
    assert len(quotas) == 2
    total = sum(q["count"] for q in quotas)
    assert total == 10
    assert all(q["region"] == "US" for q in quotas)


def test_compute_quotas_multi_region():
    flavor = FlavorConfig(
        genres={"electronic": 0.5, "rock": 0.5},
        chart_regions=["RU", "US"],
        max_tracks_per_cycle=10,
    )
    quotas = compute_quotas(flavor)
    assert len(quotas) == 4  # 2 genres x 2 regions
    total = sum(q["count"] for q in quotas)
    assert total == 10
    regions = {q["region"] for q in quotas}
    assert regions == {"RU", "US"}


def test_compute_quotas_rounding():
    flavor = FlavorConfig(
        genres={"a": 0.33, "b": 0.33, "c": 0.34},
        chart_regions=["US"],
        max_tracks_per_cycle=10,
    )
    quotas = compute_quotas(flavor)
    total = sum(q["count"] for q in quotas)
    assert total <= flavor.max_tracks_per_cycle
    assert total == 10  # last genre gets remainder


def test_release_day_boost_defaults():
    flavor = FlavorConfig()
    assert flavor.release_day_boost.days == ["friday"]
    assert flavor.release_day_boost.interval_hours == 4
    assert flavor.release_day_boost.track_multiplier == 2.0


def test_release_day_boost_from_yaml(tmp_path):
    cfg = {
        "genres": {"electronic": 1.0},
        "languages": {"en": 1.0},
        "chart_regions": ["US"],
        "refresh_interval_hours": 12,
        "max_tracks_per_cycle": 20,
        "release_day_boost": {
            "days": ["friday", "saturday"],
            "interval_hours": 3,
            "track_multiplier": 1.5,
        },
    }
    p = tmp_path / "flavor.yml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    flavor = load_flavor(str(p))
    assert flavor.release_day_boost.days == ["friday", "saturday"]
    assert flavor.release_day_boost.interval_hours == 3
    assert flavor.release_day_boost.track_multiplier == 1.5


def test_release_day_boost_missing_in_yaml(tmp_path):
    cfg = {
        "genres": {"electronic": 1.0},
        "chart_regions": ["US"],
        "max_tracks_per_cycle": 10,
    }
    p = tmp_path / "flavor.yml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    flavor = load_flavor(str(p))
    # Should use defaults when not in YAML
    assert flavor.release_day_boost.days == ["friday"]
    assert flavor.release_day_boost.track_multiplier == 2.0


def test_boost_multiplier_applied():
    flavor = FlavorConfig(
        max_tracks_per_cycle=10,
        release_day_boost=ReleaseDayBoost(track_multiplier=3.0),
    )
    boosted = int(flavor.max_tracks_per_cycle * flavor.release_day_boost.track_multiplier)
    assert boosted == 30
