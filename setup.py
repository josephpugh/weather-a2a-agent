"""Legacy setuptools build script.

``pyproject.toml`` is the source of truth for this project's metadata and build
configuration (it uses the Hatchling backend, which is what ``pip install`` uses).
This ``setup.py`` is provided only for compatibility with tools that still invoke
setuptools directly (e.g. ``python setup.py ...``). If you change dependencies or
metadata, update ``pyproject.toml`` first and keep this file in sync.
"""

from pathlib import Path

from setuptools import find_packages, setup

long_description = Path("README.md").read_text(encoding="utf-8")

setup(
    name="weather-a2a-agent",
    version="0.1.0",
    description=(
        "A fully A2A-compliant weather agent built with the Microsoft Agent Framework, "
        "with in-memory session state and human-in-the-loop tool approval."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "agent-framework>=1.10.0",
        "agent-framework-a2a>=1.0.0b0",
        "httpx>=0.27",
        "uvicorn>=0.30",
    ],
    extras_require={
        "openai": ["agent-framework-openai>=1.10.0"],
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.24",
            "respx>=0.21",
        ],
    },
    entry_points={
        "console_scripts": [
            "weather-a2a-agent = weather_agent.server:main",
        ],
    },
)
