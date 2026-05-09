"""Tests for MarbleSaveSPZ."""

from __future__ import annotations

import json
import os

import pytest
import responses

from src.marble.save_spz import MarbleSaveSPZ


def test_input_types():
    schema = MarbleSaveSPZ.INPUT_TYPES()
    assert schema["required"]["splat_urls_json"][0] == "STRING"
    assert schema["required"]["world_id"][0] == "STRING"
    # Combo dropdown
    assert isinstance(schema["optional"]["key"][0], list)
    assert "all" in schema["optional"]["key"][0]


def test_node_attributes():
    assert MarbleSaveSPZ.CATEGORY == "Marble"
    assert MarbleSaveSPZ.RETURN_TYPES == ("STRING", "STRING")
    assert MarbleSaveSPZ.RETURN_NAMES == ("primary_spz_path", "folder")
    assert MarbleSaveSPZ.OUTPUT_NODE is True


def test_save_raises_on_invalid_json(tmp_output):
    with pytest.raises(RuntimeError, match="not valid JSON"):
        MarbleSaveSPZ().save(splat_urls_json="not json", world_id="w1")


def test_save_raises_when_no_urls(tmp_output):
    with pytest.raises(RuntimeError, match="no usable URLs"):
        MarbleSaveSPZ().save(splat_urls_json="{}", world_id="w1")


def test_save_raises_when_all_urls_blank(tmp_output):
    body = json.dumps({"a": "", "b": None})
    with pytest.raises(RuntimeError, match="no usable URLs"):
        MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1")


def test_save_raises_when_key_not_in_urls(tmp_output):
    body = json.dumps({"500k": "https://cdn.example/500k.spz"})
    with pytest.raises(RuntimeError, match="not found"):
        MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1", key="missing")


@responses.activate
def test_save_all_downloads_every_entry(tmp_output):
    responses.get("https://cdn.example/full.spz", body=b"FULL", status=200)
    responses.get("https://cdn.example/500k.spz", body=b"500K", status=200)
    body = json.dumps(
        {
            "full_res": "https://cdn.example/full.spz",
            "500k": "https://cdn.example/500k.spz",
        }
    )
    primary, folder = MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1", key="all", subfolder="marble")
    expected_folder = os.path.join(str(tmp_output), "marble", "w1", "splats")
    assert folder == expected_folder
    assert os.path.isdir(expected_folder)
    files = sorted(os.listdir(expected_folder))
    assert files == ["500k.spz", "full_res.spz"]
    # Primary is the first entry that was iterated (insertion order)
    assert primary == os.path.join(expected_folder, "full_res.spz")


@responses.activate
def test_save_specific_key_downloads_only_that_one(tmp_output):
    responses.get("https://cdn.example/100k.spz", body=b"100K", status=200)
    body = json.dumps(
        {
            "full_res": "https://cdn.example/full.spz",
            "100k": "https://cdn.example/100k.spz",
        }
    )
    primary, folder = MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1", key="100k")
    files = os.listdir(folder)
    assert files == ["100k.spz"]
    assert primary == os.path.join(folder, "100k.spz")


def test_save_treats_empty_string_key_as_all(tmp_output):
    """Backwards-compat: '' was the old default before the combo dropdown."""
    body = json.dumps({"a": "https://cdn.example/a.spz"})

    @responses.activate
    def run():
        responses.get("https://cdn.example/a.spz", body=b"A", status=200)
        primary, folder = MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1", key="")
        assert os.path.isfile(primary)

    run()


@responses.activate
def test_save_uses_unknown_world_id_when_blank(tmp_output):
    responses.get("https://cdn.example/a.spz", body=b"A", status=200)
    body = json.dumps({"a": "https://cdn.example/a.spz"})
    primary, _ = MarbleSaveSPZ().save(splat_urls_json=body, world_id="")
    assert "unknown" in primary


@responses.activate
def test_save_skips_blank_url_values(tmp_output):
    responses.get("https://cdn.example/real.spz", body=b"R", status=200)
    body = json.dumps(
        {
            "real": "https://cdn.example/real.spz",
            "blank": "",
            "nullish": None,
        }
    )
    primary, folder = MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1", key="all")
    assert os.listdir(folder) == ["real.spz"]
    assert primary.endswith("real.spz")


@responses.activate
def test_save_propagates_http_error(tmp_output):
    responses.get("https://cdn.example/a.spz", status=500)
    body = json.dumps({"a": "https://cdn.example/a.spz"})
    with pytest.raises(Exception):  # noqa: B017
        MarbleSaveSPZ().save(splat_urls_json=body, world_id="w1", key="all")
