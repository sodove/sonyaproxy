import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ReleaseDayBoost:
    days: list[str] = field(default_factory=lambda: ["friday"])
    interval_hours: int = 4
    track_multiplier: float = 2.0


@dataclass
class FlavorConfig:
    genres: dict[str, float] = field(default_factory=lambda: {
        "electronic": 0.3, "hip-hop": 0.3, "bass": 0.2, "rock": 0.1, "other": 0.1,
    })
    languages: dict[str, float] = field(default_factory=lambda: {
        "ru": 0.4, "en": 0.5, "other": 0.1,
    })
    chart_regions: list[str] = field(default_factory=lambda: ["RU", "US"])
    refresh_interval_hours: int = 12
    max_tracks_per_cycle: int = 20
    release_day_boost: ReleaseDayBoost = field(default_factory=ReleaseDayBoost)


def load_flavor(path: str = "flavor.yml") -> FlavorConfig:
    p = Path(path)
    if not p.exists():
        return FlavorConfig()
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    defaults = FlavorConfig()
    boost_data = data.get("release_day_boost", {})
    boost_defaults = ReleaseDayBoost()
    boost = ReleaseDayBoost(
        days=boost_data.get("days", boost_defaults.days),
        interval_hours=boost_data.get("interval_hours", boost_defaults.interval_hours),
        track_multiplier=boost_data.get("track_multiplier", boost_defaults.track_multiplier),
    )
    return FlavorConfig(
        genres=data.get("genres", defaults.genres),
        languages=data.get("languages", defaults.languages),
        chart_regions=data.get("chart_regions", defaults.chart_regions),
        refresh_interval_hours=data.get("refresh_interval_hours", defaults.refresh_interval_hours),
        max_tracks_per_cycle=data.get("max_tracks_per_cycle", defaults.max_tracks_per_cycle),
        release_day_boost=boost,
    )


def compute_quotas(flavor: FlavorConfig) -> list[dict]:
    regions = flavor.chart_regions or ["US"]
    n_regions = len(regions)
    total = flavor.max_tracks_per_cycle

    genre_weights = {g: w for g, w in flavor.genres.items() if g != "other"}
    if not genre_weights:
        return []

    weight_sum = sum(genre_weights.values())
    quotas = []
    allocated = 0

    genre_items = list(genre_weights.items())
    for i, (genre, weight) in enumerate(genre_items):
        genre_total = math.floor(total * weight / weight_sum) if i < len(genre_items) - 1 else total - allocated
        if genre_total <= 0:
            continue
        allocated += genre_total

        per_region = genre_total // n_regions
        remainder = genre_total % n_regions
        for j, region in enumerate(regions):
            count = per_region + (1 if j < remainder else 0)
            if count > 0:
                quotas.append({"genre": genre, "region": region, "count": count})

    return quotas
