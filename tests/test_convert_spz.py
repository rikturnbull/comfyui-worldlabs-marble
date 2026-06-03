"""Tests for the MarbleConvertSPZ node."""

from __future__ import annotations

import gzip
import os
import struct

import numpy as np
import pytest

from src.marble import spz_codec
from src.marble.common import SpzData
from src.marble.convert_spz import MarbleConvertSPZ


def _tiny_spz_bytes(num: int = 2) -> bytes:
    header = struct.pack("<IIIBBBB", spz_codec.SPZ_MAGIC, 2, num, 0, 12, 0, 0)
    payload = (
        header
        + np.zeros(num * 9, dtype=np.uint8).tobytes()  # positions
        + np.full(num, 128, dtype=np.uint8).tobytes()  # alphas
        + np.full(num * 3, 128, dtype=np.uint8).tobytes()  # colors
        + np.zeros(num * 3, dtype=np.uint8).tobytes()  # scales
        + np.full(num * 3, 128, dtype=np.uint8).tobytes()  # rotations
    )
    return gzip.compress(payload)


@pytest.fixture
def spz(tmp_path):
    return SpzData(data=_tiny_spz_bytes(), key="full_res", world_id="w1")


def test_node_attributes():
    assert MarbleConvertSPZ.CATEGORY == "Marble"
    assert MarbleConvertSPZ.RETURN_TYPES == ("STRING",)
    assert MarbleConvertSPZ.RETURN_NAMES == ("ply_path",)
    assert MarbleConvertSPZ.OUTPUT_NODE is True


def test_input_types():
    schema = MarbleConvertSPZ.INPUT_TYPES()
    assert schema["required"]["spz"][0] == "SPZ"
    assert schema["optional"]["ply_path"][0] == "STRING"
    assert schema["optional"]["subfolder"][0] == "STRING"


def test_convert_default_path_uses_world_and_key(spz, tmp_output):
    (ply_path,) = MarbleConvertSPZ().convert(spz=spz)
    assert ply_path == os.path.join(str(tmp_output), "marble", "w1", "splats", "full_res.ply")
    assert os.path.isfile(ply_path)
    with open(ply_path, "rb") as f:
        assert f.read(4) == b"ply\n"


def test_convert_explicit_absolute_output(spz, tmp_path):
    out = str(tmp_path / "sub" / "out.ply")
    (ply_path,) = MarbleConvertSPZ().convert(spz=spz, ply_path=out)
    assert ply_path == out
    assert os.path.isfile(out)


def test_convert_appends_ply_extension(spz, tmp_path):
    out = str(tmp_path / "noext")
    (ply_path,) = MarbleConvertSPZ().convert(spz=spz, ply_path=out)
    assert ply_path == out + ".ply"


def test_convert_relative_output_uses_output_dir(spz, tmp_output):
    rel = os.path.join("rel", "out.ply")
    (ply_path,) = MarbleConvertSPZ().convert(spz=spz, ply_path=rel)
    assert ply_path == os.path.join(str(tmp_output), "rel", "out.ply")
    assert os.path.isfile(ply_path)


def test_convert_raises_on_empty_spz(tmp_output):
    with pytest.raises(RuntimeError, match="empty SPZ"):
        MarbleConvertSPZ().convert(spz=SpzData(data=b"", key="full_res", world_id="w1"))
