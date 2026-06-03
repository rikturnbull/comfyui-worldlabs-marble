"""Shared pytest fixtures for the marble package.

Adds the repo root to sys.path so `from src.marble.X` imports work, and
provides fixtures that isolate filesystem and environment state between tests.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _disable_debug_logging(monkeypatch):
    """Default debug off so tests don't spam stdout. Tests that exercise
    logging explicitly can override with monkeypatch.setenv('WLT_DEBUG', '1')."""
    monkeypatch.setenv("WLT_DEBUG", "0")


@pytest.fixture
def mock_api_key(monkeypatch):
    monkeypatch.setenv("WORLDLABS_API_KEY", "test-key")
    return "test-key"


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.delenv("WORLDLABS_API_KEY", raising=False)


@pytest.fixture
def tmp_output(tmp_path, monkeypatch):
    """Patch _output_directory across the marble package to use tmp_path."""
    from src.marble import common, convert_spz, fetch_mesh, save_spz

    fake = lambda: str(tmp_path)  # noqa: E731 - tiny lambda is fine here
    monkeypatch.setattr(common, "_output_directory", fake)
    monkeypatch.setattr(fetch_mesh, "_output_directory", fake)
    monkeypatch.setattr(save_spz, "_output_directory", fake)
    monkeypatch.setattr(convert_spz, "_output_directory", fake)
    return tmp_path
