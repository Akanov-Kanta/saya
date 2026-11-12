"""The Bayes "sensor": the feels-like temperature from Open-Meteo (free, no API key).

Recent and future dates (about 2 months back to 2 weeks ahead) use the forecast
API; older dates use the historical archive. Every answer is cached in
data/weather_cache.json, so the demo also works offline once it has run.
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

CACHE_FILE = Path(__file__).parent / "data" / "weather_cache.json"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


_memory = {}  # readings fetched by this process, for when the cache file cannot be written


def _load_cache() -> dict:
    try:
        return {**json.loads(CACHE_FILE.read_text()), **_memory}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_memory)


def feels_like_at(when: datetime, lat: float, lon: float) -> tuple[float, str]:
    """Return (feels-like degC, source description) for the hour containing `when`."""
    utc_hour = when.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    key = f"{utc_hour:%Y-%m-%dT%H:00Z}@{lat:.4f},{lon:.4f}"
    cache = _load_cache()
    if key in cache:
        return cache[key]["feels_like"], cache[key]["source"] + " (cached)"

    day = utc_hour.date()
    recent = date.today() - timedelta(days=60) <= day <= date.today() + timedelta(days=15)
    url = FORECAST_URL if recent else ARCHIVE_URL
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "apparent_temperature,temperature_2m",
        "start_date": day.isoformat(), "end_date": day.isoformat(),
        "timezone": "GMT",
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    hourly = response.json()["hourly"]
    index = hourly["time"].index(f"{utc_hour:%Y-%m-%dT%H:00}")
    feels_like = hourly["apparent_temperature"][index]
    if feels_like is None:
        raise ValueError(f"Open-Meteo has no value for {key} yet")
    source = (f"Open-Meteo {'forecast' if recent else 'archive'}: "
              f"air {hourly['temperature_2m'][index]:.1f} degC, feels like {feels_like:.1f} degC")

    cache[key] = {"feels_like": feels_like, "source": source}
    _memory[key] = cache[key]
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except OSError:  # read-only disk, as on Vercel: keep the reading in memory only
        pass
    return feels_like, source
