"""Tests for the weather tool and its Open-Meteo integration."""

from __future__ import annotations

import httpx
import pytest

from weather_agent import weather
from weather_agent.weather import get_current_weather, get_weather_report


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


@pytest.mark.parametrize(
    "code,expected",
    [(0, "clear sky"), (2, "partly cloudy"), (95, "thunderstorm"), (999, "unknown conditions")],
)
def test_weather_code_descriptions(code, expected):
    assert weather.WMO_WEATHER_CODES.get(code, "unknown conditions") == expected
