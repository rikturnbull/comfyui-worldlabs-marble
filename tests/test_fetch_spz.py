"""Tests for MarbleFetchSPZ."""

from __future__ import annotations

import json

import pytest
import responses

from src.marble.common import SpzData
from src.marble.fetch_spz import MarbleFetchSPZ


def test_input_types():
    schema = MarbleFetchSPZ.INPUT_TYPES()
    assert schema["required"]["splat_urls_json"][0] == "STRING"
    assert schema["required"]["world_id"][0] == "STRING"
    assert isinstance(schema["optional"]["key"][0], list)
    assert "all" not in schema["optional"]["key"][0]
    assert "full_res" in schema["optional"]["key"][0]


def test_node_attributes():
    assert MarbleFetchSPZ.CATEGORY == "Marble"
    assert MarbleFetchSPZ.RETURN_TYPES == ("SPZ",)
    assert MarbleFetchSPZ.RETURN_NAMES == ("spz",)
    # A producer, not a terminal output node.
    assert getattr(MarbleFetchSPZ, "OUTPUT_NODE", False) is False


@responses.activate
def test_fetch_downloads_selected_key():
    responses.get("https://cdn.example/500k.spz", body=b"FIVEHUNDRED", status=200)
    body = json.dumps(
        {
            "full_res": "https://cdn.example/full.spz",
            "500k": "https://cdn.example/500k.spz",
        }
    )
    (spz,) = MarbleFetchSPZ().fetch(splat_urls_json=body, world_id="w1", key="500k")
    assert isinstance(spz, SpzData)
    assert spz.data == b"FIVEHUNDRED"
    assert spz.key == "500k"
    assert spz.world_id == "w1"


@responses.activate
def test_fetch_defaults_world_id_to_unknown():
    responses.get("https://cdn.example/full.spz", body=b"F", status=200)
    body = json.dumps({"full_res": "https://cdn.example/full.spz"})
    (spz,) = MarbleFetchSPZ().fetch(splat_urls_json=body, world_id="", key="full_res")
    assert spz.world_id == "unknown"


def test_fetch_raises_on_invalid_json():
    with pytest.raises(RuntimeError, match="not valid JSON"):
        MarbleFetchSPZ().fetch(splat_urls_json="nope", world_id="w1")


def test_fetch_raises_when_no_urls():
    with pytest.raises(RuntimeError, match="no usable URLs"):
        MarbleFetchSPZ().fetch(splat_urls_json="{}", world_id="w1")


def test_fetch_raises_when_key_missing():
    body = json.dumps({"500k": "https://cdn.example/500k.spz"})
    with pytest.raises(RuntimeError, match="not found"):
        MarbleFetchSPZ().fetch(splat_urls_json=body, world_id="w1", key="full_res")


@responses.activate
def test_fetch_propagates_http_error():
    responses.get("https://cdn.example/full.spz", status=500)
    body = json.dumps({"full_res": "https://cdn.example/full.spz"})
    with pytest.raises(Exception):  # noqa: B017
        MarbleFetchSPZ().fetch(splat_urls_json=body, world_id="w1", key="full_res")
