"""The weather tool.

This module contains the single tool exposed by the agent. It is deliberately
small and self-contained so it reads as a clean example of:

* an ``async`` function tool that performs real I/O (two Open-Meteo calls: first
  geocoding a city name into coordinates, then fetching the current weather), and
* a tool that requires **human approval** before it runs, expressed with
  ``@tool(approval_mode="always_require")``.

The Agent Framework turns the decorated function into a ``FunctionTool``,
deriving the JSON schema for the arguments from the type annotations and the
description from the docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import httpx
from agent_framework import tool

# Open-Meteo is free and needs no API key, which keeps this reference runnable.
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# A small subset of the WMO weather-interpretation codes returned by Open-Meteo.
# https://open-meteo.com/en/docs -> "Weather variable documentation"
WMO_WEATHER_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherError(Exception):
    """Raised when weather information cannot be retrieved for a city."""


@dataclass(frozen=True)
class GeoLocation:
    """A resolved geographic location."""

    name: str
    country: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}" if self.country else self.name


async def geocode_city(city: str, *, client: httpx.AsyncClient) -> GeoLocation:
    """Resolve a free-text city name into coordinates using Open-Meteo geocoding."""
    response = await client.get(
        GEOCODING_URL,
        params={"name": city, "count": 1, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise WeatherError(f"Could not find a location matching {city!r}.")
    top = results[0]
    return GeoLocation(
        name=top.get("name", city),
        country=top.get("country", ""),
        latitude=top["latitude"],
        longitude=top["longitude"],
    )


async def fetch_current_weather(location: GeoLocation, *, client: httpx.AsyncClient) -> str:
    """Fetch and format the current weather for a resolved location."""
    response = await client.get(
        FORECAST_URL,
        params={
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        },
    )
    response.raise_for_status()
    current = response.json().get("current")
    if not current:
        raise WeatherError(f"No current weather available for {location.label}.")

    description = WMO_WEATHER_CODES.get(int(current.get("weather_code", -1)), "unknown conditions")
    return (
        f"Current weather in {location.label}: {description}, "
        f"{current['temperature_2m']}°C, "
        f"humidity {current['relative_humidity_2m']}%, "
        f"wind {current['wind_speed_10m']} km/h."
    )


async def get_weather_report(city: str, *, client: httpx.AsyncClient | None = None) -> str:
    """Resolve a city and return a human-readable current-weather summary.

    ``client`` can be injected for testing; otherwise a short-lived client is
    created. Errors are converted into a readable message so the LLM can relay
    the problem to the user instead of the run failing.
    """
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        location = await geocode_city(city, client=client)
        return await fetch_current_weather(location, client=client)
    except WeatherError as exc:
        return str(exc)
    except httpx.HTTPError as exc:
        return f"Weather service is unavailable right now ({exc.__class__.__name__})."
    finally:
        if own_client:
            await client.aclose()


@tool(approval_mode="always_require")
async def get_current_weather(
    city: Annotated[str, "The city to get the current weather for, e.g. 'Paris' or 'Tokyo, Japan'."],
) -> str:
    """Get the current weather conditions for a city.

    This tool requires human approval before it runs (``approval_mode="always_require"``).
    The Agent Framework will pause the run and surface an approval request instead
    of invoking the function; the caller must approve it before the weather is fetched.
    """
    return await get_weather_report(city)
