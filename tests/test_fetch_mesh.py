"""Tests for MarbleFetchMesh and the _wrap_file3d helper."""

from __future__ import annotations

import os

import pytest
import responses

from src.marble import fetch_mesh
from src.marble.fetch_mesh import MarbleFetchMesh, _wrap_file3d


def test_input_types():
    schema = MarbleFetchMesh.INPUT_TYPES()
    assert schema["required"]["url"][0] == "STRING"
    assert schema["required"]["world_id"][0] == "STRING"
    assert schema["optional"]["filename"][0] == "STRING"
    assert schema["optional"]["subfolder"][0] == "STRING"


def test_node_attributes():
    assert MarbleFetchMesh.CATEGORY == "Marble"
    assert MarbleFetchMesh.RETURN_TYPES == ("STRING", "FILE_3D_GLB")
    assert MarbleFetchMesh.RETURN_NAMES == ("mesh_path", "glb")
    assert MarbleFetchMesh.OUTPUT_NODE is True


def test_fetch_raises_on_empty_url(tmp_output):
    with pytest.raises(RuntimeError, match="empty URL"):
        MarbleFetchMesh().fetch(url="", world_id="w1")


@responses.activate
def test_fetch_saves_with_extension_from_url(tmp_output):
    body = b"fake glb bytes"
    responses.get("https://cdn.example/abc/mesh.glb", body=body, status=200)

    mesh_path, glb = MarbleFetchMesh().fetch(
        url="https://cdn.example/abc/mesh.glb",
        world_id="w1",
        filename="collider_mesh",
        subfolder="marble",
    )
    expected = os.path.join(str(tmp_output), "marble", "w1", "collider_mesh.glb")
    assert mesh_path == expected
    assert os.path.isfile(expected)
    with open(expected, "rb") as f:
        assert f.read() == body
    # When comfy_api isn't available (test env), _wrap_file3d returns the path
    assert glb == expected


@responses.activate
def test_fetch_defaults_to_glb_when_url_has_no_extension(tmp_output):
    responses.get("https://cdn.example/mesh-no-ext", body=b"x", status=200)
    mesh_path, _ = MarbleFetchMesh().fetch(
        url="https://cdn.example/mesh-no-ext",
        world_id="w1",
    )
    assert mesh_path.endswith(".glb")


@responses.activate
def test_fetch_uses_unknown_world_id_when_blank(tmp_output):
    responses.get("https://cdn.example/m.glb", body=b"x", status=200)
    mesh_path, _ = MarbleFetchMesh().fetch(url="https://cdn.example/m.glb", world_id="")
    assert "unknown" in mesh_path


@responses.activate
def test_fetch_propagates_http_error(tmp_output):
    responses.get("https://cdn.example/missing.glb", status=404)
    with pytest.raises(Exception):  # noqa: B017
        MarbleFetchMesh().fetch(url="https://cdn.example/missing.glb", world_id="w1")


# ---------------------------------------------------------------------------
# _wrap_file3d
# ---------------------------------------------------------------------------


def test_wrap_file3d_falls_back_to_path_when_comfy_api_missing(monkeypatch):
    monkeypatch.setattr(fetch_mesh, "_ComfyTypes", None)
    assert _wrap_file3d("/some/path.glb") == "/some/path.glb"


def test_wrap_file3d_uses_types_file3d_when_available(monkeypatch):
    constructed: list = []

    class FakeFile3D:
        def __init__(self, path):
            constructed.append(path)
            self.path = path

    fake_types = type("Types", (), {"File3D": FakeFile3D})
    monkeypatch.setattr(fetch_mesh, "_ComfyTypes", fake_types)
    result = _wrap_file3d("/p.glb")
    assert isinstance(result, FakeFile3D)
    assert constructed == ["/p.glb"]


def test_wrap_file3d_falls_back_when_constructor_raises(monkeypatch, capsys):
    class ExplodingFile3D:
        def __init__(self, path):
            raise RuntimeError("nope")

    fake_types = type("Types", (), {"File3D": ExplodingFile3D})
    monkeypatch.setattr(fetch_mesh, "_ComfyTypes", fake_types)
    result = _wrap_file3d("/p.glb")
    assert result == "/p.glb"
    assert "could not construct" in capsys.readouterr().out
