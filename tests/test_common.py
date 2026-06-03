"""Tests for src.marble.common."""

from __future__ import annotations

import base64
import io
import json
import os

import numpy as np
import pytest
import responses
import torch
from PIL import Image as PILImage

from src.marble import common
from src.marble.common import (
    _get_api_key,
    _output_directory,
    _package_root,
    _tensor_to_png_b64,
    _url_to_tensor,
)


# ---------------------------------------------------------------------------
# _package_root
# ---------------------------------------------------------------------------


def test_package_root_resolves_to_repo_root():
    root = _package_root()
    # Resolves to the marble custom-node repo root, where pyproject.toml lives
    assert os.path.isfile(os.path.join(root, "pyproject.toml"))


# ---------------------------------------------------------------------------
# _get_api_key
# ---------------------------------------------------------------------------


def test_get_api_key_prefers_env_var(mock_api_key):
    assert _get_api_key() == "test-key"


def test_get_api_key_reads_config_file(no_api_key, tmp_path, monkeypatch):
    cfg = tmp_path / "marble_config.json"
    cfg.write_text(json.dumps({"api_key": "from-file"}), encoding="utf-8")
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    assert _get_api_key() == "from-file"


def test_get_api_key_accepts_uppercase_field(no_api_key, tmp_path, monkeypatch):
    cfg = tmp_path / "marble_config.json"
    cfg.write_text(json.dumps({"WORLDLABS_API_KEY": "uppercase"}), encoding="utf-8")
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    assert _get_api_key() == "uppercase"


def test_get_api_key_handles_utf8_bom(no_api_key, tmp_path, monkeypatch):
    cfg = tmp_path / "marble_config.json"
    # Write with BOM, like Windows PowerShell Out-File -Encoding utf8 does
    cfg.write_bytes(b"\xef\xbb\xbf" + json.dumps({"api_key": "bom-key"}).encode("utf-8"))
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    assert _get_api_key() == "bom-key"


def test_get_api_key_raises_when_no_config(no_api_key, tmp_path, monkeypatch):
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    with pytest.raises(RuntimeError, match="WORLDLABS_API_KEY not found"):
        _get_api_key()


def test_get_api_key_raises_on_empty_file(no_api_key, tmp_path, monkeypatch):
    (tmp_path / "marble_config.json").write_text("", encoding="utf-8")
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    with pytest.raises(RuntimeError, match="empty"):
        _get_api_key()


def test_get_api_key_raises_on_invalid_json(no_api_key, tmp_path, monkeypatch):
    (tmp_path / "marble_config.json").write_text("not json", encoding="utf-8")
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    with pytest.raises(RuntimeError, match="invalid JSON"):
        _get_api_key()


def test_get_api_key_raises_on_missing_key_field(no_api_key, tmp_path, monkeypatch):
    cfg = tmp_path / "marble_config.json"
    cfg.write_text(json.dumps({"other": "value"}), encoding="utf-8")
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))
    with pytest.raises(RuntimeError, match="no 'api_key' field"):
        _get_api_key()


def test_get_api_key_propagates_oserror(no_api_key, tmp_path, monkeypatch):
    cfg = tmp_path / "marble_config.json"
    cfg.write_text(json.dumps({"api_key": "x"}), encoding="utf-8")
    monkeypatch.setattr(common, "_package_root", lambda: str(tmp_path))

    def boom(*_a, **_kw):
        raise OSError("permission denied")

    monkeypatch.setattr("builtins.open", boom)
    with pytest.raises(RuntimeError, match="could not read"):
        _get_api_key()


# ---------------------------------------------------------------------------
# _tensor_to_png_b64
# ---------------------------------------------------------------------------


def test_tensor_to_png_b64_round_trips():
    tensor = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
    tensor[0, :, :, 0] = 1.0  # solid red
    encoded = _tensor_to_png_b64(tensor)

    decoded = base64.b64decode(encoded)
    img = PILImage.open(io.BytesIO(decoded))
    assert img.size == (8, 8)
    arr = np.array(img)
    assert (arr[..., 0] == 255).all()  # red channel saturated


def test_tensor_to_png_b64_clips_out_of_range_values():
    tensor = torch.full((1, 4, 4, 3), 5.0, dtype=torch.float32)
    encoded = _tensor_to_png_b64(tensor)
    decoded = base64.b64decode(encoded)
    arr = np.array(PILImage.open(io.BytesIO(decoded)))
    assert arr.max() == 255  # clipped


# ---------------------------------------------------------------------------
# _url_to_tensor
# ---------------------------------------------------------------------------


def _make_png_bytes(width: int = 8, height: int = 8, color=(0, 128, 255)) -> bytes:
    img = PILImage.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@responses.activate
def test_url_to_tensor_returns_correct_shape():
    responses.get(
        "https://cdn.example/img.png",
        body=_make_png_bytes(16, 12),
        status=200,
        content_type="image/png",
    )
    tensor = _url_to_tensor("https://cdn.example/img.png")
    assert tensor.shape == (1, 12, 16, 3)
    assert tensor.dtype == torch.float32
    assert 0.0 <= tensor.min() <= tensor.max() <= 1.0


@responses.activate
def test_url_to_tensor_raises_on_http_error():
    responses.get("https://cdn.example/missing.png", status=404)
    with pytest.raises(Exception):  # noqa: B017 - requests.HTTPError; broad to avoid depending on internals
        _url_to_tensor("https://cdn.example/missing.png")


# ---------------------------------------------------------------------------
# _output_directory
# ---------------------------------------------------------------------------


def test_output_directory_uses_folder_paths_when_available(monkeypatch, tmp_path):
    fake = type("F", (), {"get_output_directory": staticmethod(lambda: str(tmp_path))})
    monkeypatch.setattr(common, "folder_paths", fake)
    assert _output_directory() == str(tmp_path)


def test_output_directory_falls_back_when_no_folder_paths(monkeypatch):
    monkeypatch.setattr(common, "folder_paths", None)
    assert _output_directory() == os.path.abspath("output")


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_marble_spz_keys_includes_known_lods():
    assert "all" in common.MARBLE_SPZ_KEYS
    assert "full_res" in common.MARBLE_SPZ_KEYS
    assert "500k" in common.MARBLE_SPZ_KEYS


def test_marble_spz_lod_keys_excludes_all():
    assert "all" not in common.MARBLE_SPZ_LOD_KEYS
    assert common.MARBLE_SPZ_LOD_KEYS == ["full_res", "500k", "150k", "100k"]


def test_spz_data_defaults():
    spz = common.SpzData(data=b"abc")
    assert spz.data == b"abc"
    assert spz.key == "full_res"
    assert spz.world_id == "unknown"
