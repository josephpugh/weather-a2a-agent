"""Tests for the weather tool and its Open-Meteo integration."""

from __future__ import annotations

import httpx
import pytest

from weather_agent import weather
from weather_agent.weather import get_current_weather, get_geocode_location, get_weather_report


async def test_get_weather_report_success():
    report = await get_weather_report("Paris")
    assert "Paris, France" in report
    assert "partly cloudy" in report
    assert "18.0°C" in report
    assert "humidity 55%" in report
    assert "wind 12.0 km/h" in report


async def test_geocoding_and_forecast_are_both_called(open_meteo):
    await get_weather_report("Paris")
    geocode_route, forecast_route = open_meteo.routes
    assert geocode_route.called
    assert forecast_route.called


async def test_city_not_found(open_meteo):
    open_meteo.get(weather.GEOCODING_URL).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    report = await get_weather_report("Nowheresville")
    assert "Could not find" in report


async def test_weather_service_http_error(open_meteo):
    open_meteo.get(weather.FORECAST_URL).mock(return_value=httpx.Response(500))
    report = await get_weather_report("Paris")
    assert "unavailable" in report.lower()


def test_tool_requires_approval():
    # The tool is declared with approval_mode="always_require" so the framework
    # will pause for a human decision before invoking it.
    assert get_current_weather.name == "get_current_weather"
    assert get_current_weather.approval_mode == "always_require"


async def test_get_geocode_location_success():
    location = await get_geocode_location(city="Paris")
    assert location == {"name": "Paris", "country": "France", "latitude": 48.85, "longitude": 2.35}


async def test_get_geocode_location_city_not_found(open_meteo):
    open_meteo.get(weather.GEOCODING_URL).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    result = await get_geocode_location(city="Nowheresville")
    assert "Could not find" in result


async def test_get_geocode_location_does_not_call_forecast(open_meteo):
    await get_geocode_location(city="Paris")
    geocode_route, forecast_route = open_meteo.routes
    assert geocode_route.called
    assert not forecast_route.called


def test_geocode_tool_never_requires_approval():
    # Unlike get_current_weather, this is a read-only lookup with no side effects.
    assert get_geocode_location.name == "get_geocode_location"
    assert get_geocode_location.approval_mode == "never_require"


@pytest.mark.parametrize(
    "code,expected",
    [(0, "clear sky"), (2, "partly cloudy"), (95, "thunderstorm"), (999, "unknown conditions")],
)
def test_weather_code_descriptions(code, expected):
    assert weather.WMO_WEATHER_CODES.get(code, "unknown conditions") == expected
