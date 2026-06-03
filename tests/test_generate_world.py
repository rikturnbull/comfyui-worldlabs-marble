"""Tests for MarbleGenerateWorld."""

from __future__ import annotations

import json

import pytest
import responses
import torch

from src.marble.generate_world import MarbleGenerateWorld, _parse_azimuths
from src.marble_api import MARBLE_BASE_URL


def _full_world_response(world_id: str = "w1") -> dict:
    """A representative successful operation response from Marble."""
    return {
        "operation_id": "op1",
        "done": True,
        "metadata": {"progress": {"status": "SUCCEEDED"}},
        "response": {
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
                    "semantics_metadata": {
                        "metric_scale_factor": 2.5,
                        "ground_plane_offset": 1.0,
                    },
                },
            },
        },
        "cost": {"total_credits": 1580},
    }


def test_input_types_declares_required_fields():
    schema = MarbleGenerateWorld.INPUT_TYPES()
    assert "prompt" in schema["required"]
    assert "model" in schema["required"]
    assert "seed" in schema["required"]
    assert "image" in schema["optional"]
    assert "is_pano" in schema["optional"]
    # api_key is in 'required' so it renders first in the node UI; an empty
    # default + the env-var/config-file fallback make it functionally optional.
    assert "api_key" in schema["required"]
    assert schema["required"]["api_key"][1].get("password") is True
    assert next(iter(schema["required"])) == "api_key"  # rendered first


@responses.activate
def test_text_only_generation_sends_text_prompt(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json=_full_world_response(),
    )
    # generate() re-fetches the completed world for fully-materialised assets.
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/worlds/w1",
        json=_full_world_response()["response"],
    )

    node = MarbleGenerateWorld()
    result = node.generate(
        prompt="a mountain",
        model="marble-1.0",
        seed=42,
        max_wait_seconds=10,
        poll_interval_seconds=0,
    )

    sent = json.loads(responses.calls[0].request.body)
    assert sent["world_prompt"] == {"type": "text", "text_prompt": "a mountain"}
    assert sent["model"] == "marble-1.0"
    assert sent["seed"] == 42

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
    assert json.loads(semantics) == {"metric_scale_factor": 2.5, "ground_plane_offset": 1.0}
    assert credits == 1580


@responses.activate
def test_image_prompt_generation_sends_image_prompt(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json=_full_world_response(),
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world_response()["response"])

    image = torch.zeros((1, 4, 4, 3), dtype=torch.float32)
    image[0, :, :, 0] = 1.0  # red

    MarbleGenerateWorld().generate(
        prompt="extra context",
        model="marble-1.1",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
        image=image,
        is_pano=True,
    )

    sent = json.loads(responses.calls[0].request.body)
    wp = sent["world_prompt"]
    assert wp["type"] == "image"
    assert wp["is_pano"] is True
    assert wp["text_prompt"] == "extra context"
    assert wp["image_prompt"]["source"] == "data_base64"
    assert wp["image_prompt"]["extension"] == "png"
    assert isinstance(wp["image_prompt"]["data_base64"], str) and wp["image_prompt"]["data_base64"]


@responses.activate
def test_image_prompt_omits_empty_text(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json=_full_world_response(),
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world_response()["response"])

    image = torch.zeros((1, 4, 4, 3), dtype=torch.float32)
    MarbleGenerateWorld().generate(
        prompt="",
        model="marble-1.0",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
        image=image,
    )
    wp = json.loads(responses.calls[0].request.body)["world_prompt"]
    assert "text_prompt" not in wp


def _mock_full_generation():
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/operations/op1", json=_full_world_response())
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world_response()["response"])


@responses.activate
def test_multi_image_batch_sends_multi_prompt(mock_api_key):
    _mock_full_generation()
    images = torch.zeros((3, 4, 4, 3), dtype=torch.float32)

    MarbleGenerateWorld().generate(
        prompt="three views",
        model="marble-1.1",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
        image=images,
        azimuths="0,120,240",
    )

    wp = json.loads(responses.calls[0].request.body)["world_prompt"]
    assert wp["type"] == "multi-image"
    assert len(wp["multi_image_prompt"]) == 3
    assert [e["azimuth"] for e in wp["multi_image_prompt"]] == [0, 120, 240]
    assert wp["text_prompt"] == "three views"
    assert "reconstruct_images" not in wp


@responses.activate
def test_multi_image_reconstruct_allows_more_than_four(mock_api_key):
    _mock_full_generation()
    images = torch.zeros((6, 4, 4, 3), dtype=torch.float32)

    MarbleGenerateWorld().generate(
        prompt="",
        model="marble-1.1",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
        image=images,
        reconstruct_images=True,
    )
    wp = json.loads(responses.calls[0].request.body)["world_prompt"]
    assert wp["type"] == "multi-image"
    assert len(wp["multi_image_prompt"]) == 6
    assert wp["reconstruct_images"] is True


def test_multi_image_over_limit_without_reconstruct_raises(mock_api_key):
    images = torch.zeros((5, 4, 4, 3), dtype=torch.float32)
    with pytest.raises(RuntimeError, match="up to 4 images"):
        MarbleGenerateWorld().generate(
            prompt="x",
            model="marble-1.1",
            seed=0,
            max_wait_seconds=10,
            poll_interval_seconds=0,
            image=images,
        )


def test_multi_image_over_eight_raises(mock_api_key):
    images = torch.zeros((9, 4, 4, 3), dtype=torch.float32)
    with pytest.raises(RuntimeError, match="up to 8 images"):
        MarbleGenerateWorld().generate(
            prompt="x",
            model="marble-1.1",
            seed=0,
            max_wait_seconds=10,
            poll_interval_seconds=0,
            image=images,
            reconstruct_images=True,
        )


def test_parse_azimuths():
    assert _parse_azimuths("", 3) is None
    assert _parse_azimuths("0, 180", 2) == [0.0, 180.0]
    assert _parse_azimuths("0,,90", 3) == [0.0, None, 90.0]  # empty slot -> unplaced
    with pytest.raises(RuntimeError, match="Invalid azimuth"):
        _parse_azimuths("0,west", 2)
    with pytest.raises(RuntimeError, match="at most one per image"):
        _parse_azimuths("0,90,180", 2)


@responses.activate
def test_raises_when_operation_returns_error(mock_api_key):
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json={"operation_id": "op1", "done": True, "error": {"message": "bad"}, "response": {}},
    )

    with pytest.raises(RuntimeError, match="generation failed"):
        MarbleGenerateWorld().generate(
            prompt="x",
            model="marble-1.0",
            seed=0,
            max_wait_seconds=10,
            poll_interval_seconds=0,
        )


@responses.activate
def test_refetches_world_when_operation_response_lacks_imagery(mock_api_key):
    """The op can report done before pano_url is populated; get_world fills it in."""
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    # Operation completes but its response has no imagery yet.
    op_without_pano = _full_world_response()
    op_without_pano["response"]["assets"].pop("imagery")
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/operations/op1", json=op_without_pano)
    # The materialised world (get_world) does carry the pano.
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/worlds/w1",
        json=_full_world_response()["response"],
    )

    _, _, _, pano_url, *_ = MarbleGenerateWorld().generate(
        prompt="x",
        model="marble-1.0",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
    )
    assert pano_url == "https://cdn.example/pano.png"


@responses.activate
def test_refetch_failure_falls_back_to_operation_response(mock_api_key):
    """If get_world fails, generate() still returns the operation-response assets."""
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/operations/op1", json=_full_world_response())
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", status=500, json={"error": "boom"})

    _, _, _, pano_url, *_ = MarbleGenerateWorld().generate(
        prompt="x",
        model="marble-1.0",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
    )
    assert pano_url == "https://cdn.example/pano.png"  # from the op response fallback


@responses.activate
def test_handles_missing_assets_gracefully(mock_api_key):
    """Sparse response with no assets shouldn't crash; outputs default to empty."""
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json={"operation_id": "op1", "done": True, "response": {"world_id": "w1"}},
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json={"world_id": "w1"})

    result = MarbleGenerateWorld().generate(
        prompt="x",
        model="marble-1.0",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
    )
    world_id, splat_urls_json, mesh_url, pano_url, thumbnail_url, world_marble_url, semantics, credits = result
    assert world_id == "w1"
    assert json.loads(splat_urls_json) == {}
    assert mesh_url == ""
    assert pano_url == ""
    assert thumbnail_url == ""
    assert world_marble_url == ""
    assert json.loads(semantics) == {}
    assert credits == 0


def test_node_attributes():
    assert MarbleGenerateWorld.CATEGORY == "Marble"
    assert MarbleGenerateWorld.FUNCTION == "generate"
    assert len(MarbleGenerateWorld.RETURN_TYPES) == len(MarbleGenerateWorld.RETURN_NAMES)
    assert MarbleGenerateWorld.RETURN_NAMES[0] == "world_id"
    assert MarbleGenerateWorld.RETURN_TYPES[-1] == "INT"  # cost_credits


@responses.activate
def test_explicit_api_key_input_overrides_env(mock_api_key):
    """If api_key input is non-empty, it takes priority over WORLDLABS_API_KEY."""
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json=_full_world_response(),
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world_response()["response"])

    MarbleGenerateWorld().generate(
        prompt="x",
        model="marble-1.0",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
        api_key="explicit-key",
    )
    assert responses.calls[0].request.headers["WLT-Api-Key"] == "explicit-key"


@responses.activate
def test_empty_api_key_input_falls_back_to_env(mock_api_key):
    """Empty api_key input means fall back to WORLDLABS_API_KEY env var."""
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json=_full_world_response(),
    )
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/worlds/w1", json=_full_world_response()["response"])

    MarbleGenerateWorld().generate(
        prompt="x",
        model="marble-1.0",
        seed=0,
        max_wait_seconds=10,
        poll_interval_seconds=0,
        api_key="",
    )
    assert responses.calls[0].request.headers["WLT-Api-Key"] == "test-key"
