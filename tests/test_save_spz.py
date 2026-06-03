"""Tests for MarbleSaveSPZ."""

from __future__ import annotations

import os

import pytest

from src.marble.common import SpzData
from src.marble.save_spz import MarbleSaveSPZ


def test_input_types():
    schema = MarbleSaveSPZ.INPUT_TYPES()
    assert schema["required"]["spz"][0] == "SPZ"
    assert schema["optional"]["filename"][0] == "STRING"
    assert schema["optional"]["subfolder"][0] == "STRING"


def test_node_attributes():
    assert MarbleSaveSPZ.CATEGORY == "Marble"
    assert MarbleSaveSPZ.RETURN_TYPES == ("STRING", "STRING")
    assert MarbleSaveSPZ.RETURN_NAMES == ("spz_path", "folder")
    assert MarbleSaveSPZ.OUTPUT_NODE is True


def test_save_writes_to_world_splats_folder(tmp_output):
    spz = SpzData(data=b"SPZBYTES", key="500k", world_id="w1")
    path, folder = MarbleSaveSPZ().save(spz=spz, subfolder="marble")
    expected_folder = os.path.join(str(tmp_output), "marble", "w1", "splats")
    assert folder == expected_folder
    assert path == os.path.join(expected_folder, "500k.spz")
    with open(path, "rb") as f:
        assert f.read() == b"SPZBYTES"


def test_save_filename_defaults_to_key(tmp_output):
    spz = SpzData(data=b"X", key="full_res", world_id="w1")
    path, _ = MarbleSaveSPZ().save(spz=spz)
    assert path.endswith(os.path.join("splats", "full_res.spz"))


def test_save_custom_filename(tmp_output):
    spz = SpzData(data=b"X", key="full_res", world_id="w1")
    path, _ = MarbleSaveSPZ().save(spz=spz, filename="my_splat")
    assert path.endswith("my_splat.spz")


def test_save_uses_unknown_when_world_id_blank(tmp_output):
    spz = SpzData(data=b"X", key="100k", world_id="")
    path, _ = MarbleSaveSPZ().save(spz=spz)
    assert "unknown" in path


def test_save_raises_on_empty_spz(tmp_output):
    with pytest.raises(RuntimeError, match="empty SPZ"):
        MarbleSaveSPZ().save(spz=SpzData(data=b"", key="full_res", world_id="w1"))
