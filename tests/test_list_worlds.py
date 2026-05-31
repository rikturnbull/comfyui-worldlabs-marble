"""Tests for MarbleListWorlds."""

from __future__ import annotations

import json

import pytest
import responses

from src.marble.list_worlds import MarbleListWorlds, list_worlds_items, worlds_to_items
from src.marble_api import MARBLE_BASE_URL


def _full_world(world_id: str = "w1") -> dict:
    """A GET /worlds/{id} body, same asset shape as a generate response."""
    return {
        "world_id": world_id,
        "world_marble_url": f"https://marble.worldlabs.ai/world/{world_id}",
        "assets": {
            "imagery": {"pano_url": "https://cdn.example/pano.png"},
            "mesh": {"collider_mesh_url": "https://cdn.example/mesh.glb"},
            "thumbnail_url": "https://cdn.example/thumb.webp",
            "splats": {
                "spz_urls": {
                    "full_res": "https://cdn.example/full.spz",
                    "500k": "https://cdn.example/500k.spz",
                },
                "semantics_metadata": {"metric_scale_factor": 2.5},
            },
        },
    }


def test_input_types_and_attributes():
    schema = MarbleListWorlds.INPUT_TYPES()
    assert "api_key" in schema["required"]
    assert schema["required"]["api_key"][1].get("password") is True
    assert "world" in schema["required"]  # name shown in the dropdown
    assert "world_id" not in schema["required"]  # resolved on the backend, not a widget
    assert MarbleListWorlds.FUNCTION == "load"
    # Outputs mirror Marble: Generate World exactly.
    from src.marble.generate_world import MarbleGenerateWorld

    assert MarbleListWorlds.RETURN_TYPES == MarbleGenerateWorld.RETURN_TYPES
    assert MarbleListWorlds.RETURN_NAMES == MarbleGenerateWorld.RETURN_NAMES


def test_validate_inputs_accepts_dynamic_value():
    assert MarbleListWorlds.VALIDATE_INPUTS(world="any-frontend-id") is True


def test_load_raises_without_selection(mock_api_key):
    with pytest.raises(RuntimeError, match="No world selected"):
        MarbleListWorlds().load(api_key="", world="<press Update>")


@responses.activate
def test_load_raises_when_name_no_longer_resolves(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:list",
        json={"worlds": [{"world_id": "w1", "display_name": "Other"}]},
    )
    with pytest.raises(RuntimeError, match="was not found"):
        MarbleListWorlds().load(api_key="", world="My Mountain")


@responses.activate
def test_load_resolves_name_then_fetches_world(mock_api_key):
    # load() lists worlds to resolve the selected name -> id, then GETs the world.
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:list",
        json={"worlds": [{"world_id": "w1", "display_name": "My Mountain"}]},
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world("w1"))

    result = MarbleListWorlds().load(api_key="", world="My Mountain")
    world_id, splat_urls_json, mesh_url, pano_url, thumbnail_url, world_marble_url, semantics, credits = result

    assert world_id == "w1"
    assert json.loads(splat_urls_json) == {
        "full_res": "https://cdn.example/full.spz",
        "500k": "https://cdn.example/500k.spz",
    }
    assert mesh_url == "https://cdn.example/mesh.glb"
    assert pano_url == "https://cdn.example/pano.png"
    assert thumbnail_url == "https://cdn.example/thumb.webp"
    assert world_marble_url == "https://marble.worldlabs.ai/world/w1"
    assert json.loads(semantics) == {"metric_scale_factor": 2.5}
    assert credits == 0  # listed worlds carry no per-operation cost


@responses.activate
def test_load_handles_sparse_world(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:list",
        json={"worlds": [{"world_id": "w1", "display_name": "My Mountain"}]},
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json={"world_id": "w1"})
    world_id, splat_urls_json, mesh_url, pano_url, thumbnail_url, world_marble_url, semantics, credits = MarbleListWorlds().load(
        api_key="", world="My Mountain"
    )
    assert world_id == "w1"
    assert json.loads(splat_urls_json) == {}
    assert mesh_url == pano_url == thumbnail_url == world_marble_url == ""
    assert json.loads(semantics) == {}
    assert credits == 0


@responses.activate
def test_load_explicit_key_overrides_env(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:list",
        json={"worlds": [{"world_id": "w1", "display_name": "My Mountain"}]},
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world("w1"))
    MarbleListWorlds().load(api_key="explicit-key", world="My Mountain")
    assert responses.calls[0].request.headers["WLT-Api-Key"] == "explicit-key"


def test_worlds_to_items_filters_and_names():
    resp = {
        "worlds": [
            {"world_id": "a", "display_name": "Sunset Peak"},  # display_name wins
            {"world_id": "b", "prompt": "a forest"},  # falls back to prompt
            {"world_id": "c"},  # falls back to id
            {"display_name": "no id, dropped"},
        ]
    }
    items = worlds_to_items(resp)
    assert [i["id"] for i in items] == ["a", "b", "c"]
    assert items[0]["name"] == "Sunset Peak"
    assert items[1]["name"] == "a forest"
    assert items[2]["name"] == "c"


def test_worlds_to_items_dedupes_names():
    resp = {
        "worlds": [
            {"world_id": "abcdef123", "display_name": "Mountain"},
            {"world_id": "ghijkl456", "display_name": "Mountain"},  # same name
        ]
    }
    items = worlds_to_items(resp)
    names = [i["name"] for i in items]
    assert names[0] == "Mountain"
    assert names[1] == "Mountain (ghijkl)"  # id-suffixed to stay unique
    assert len(set(names)) == 2


def test_worlds_to_items_double_collision_guard():
    # After the id-suffix a name can still clash with an existing entry; the
    # fallback appends until unique.
    resp = {
        "worlds": [
            {"world_id": "abcdef00", "display_name": "Mountain"},
            {"world_id": "zzzzzz11", "display_name": "Mountain (abcdef)"},
            {"world_id": "abcdef99", "display_name": "Mountain"},  # -> "Mountain (abcdef)" clashes
        ]
    }
    names = [i["name"] for i in worlds_to_items(resp)]
    assert names == ["Mountain", "Mountain (abcdef)", "Mountain (abcdef)·"]
    assert len(set(names)) == 3


def test_worlds_to_items_empty():
    assert worlds_to_items({}) == []
    assert worlds_to_items({"worlds": []}) == []


@responses.activate
def test_list_worlds_items_maps_response(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:list",
        json={"worlds": [{"world_id": "w1", "display_name": "Alps"}]},
    )
    assert list_worlds_items("") == [{"id": "w1", "name": "Alps"}]
