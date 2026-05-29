"""MarbleGenerateWorld node."""

from __future__ import annotations

import json
from inspect import cleandoc
from typing import Any

import torch

from ..marble_api import (
    MARBLE_MODELS,
    MarbleClient,
    make_image_prompt,
    make_text_prompt,
)
from .common import _get_api_key, _tensor_to_png_b64

try:
    from comfy.model_management import throw_exception_if_processing_interrupted as _check_interrupt
except ImportError:
    _check_interrupt = None


class MarbleGenerateWorld:
    """Generate a 3D world via the WorldLabs Marble API.

    API key resolution order:
      1. The optional `api_key` node input (if non-empty).
      2. The WORLDLABS_API_KEY environment variable.
      3. marble_config.json in the package root.

    Submits a generation request, polls the operation until completion,
    and returns the world identifiers plus URLs for each asset.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = (
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "INT",
    )
    RETURN_NAMES = (
        "world_id",
        "splat_urls_json",
        "mesh_url",
        "pano_url",
        "thumbnail_url",
        "world_marble_url",
        "semantics_metadata_json",
        "cost_credits",
    )
    FUNCTION = "generate"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "password": True,
                        "tooltip": "Optional. If empty, falls back to WORLDLABS_API_KEY env var or marble_config.json.",
                    },
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "A serene mountain landscape at sunset",
                        "tooltip": "Text description of the world to generate. Combine with an image input for image-conditioned generation.",
                    },
                ),
                "model": (
                    MARBLE_MODELS,
                    {
                        "default": "marble-1.0",
                        "tooltip": "Marble model variant. '-draft' is fastest and cheapest; '-plus' adds dynamic world sizing.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFF,
                        "tooltip": "Random seed for reproducibility. Same prompt + same seed produces the same world.",
                    },
                ),
                "max_wait_seconds": (
                    "INT",
                    {
                        "default": 600,
                        "min": 30,
                        "max": 7200,
                        "tooltip": "Hard safety-net timeout for the polling loop. Generation typically takes 5-10 minutes; the ComfyUI cancel button interrupts within ~1s regardless of this value.",
                    },
                ),
                "poll_interval_seconds": (
                    "INT",
                    {
                        "default": 5,
                        "min": 1,
                        "max": 60,
                        "tooltip": "How often to check operation status while generation is in progress.",
                    },
                ),
            },
            "optional": {
                "image": (
                    "IMAGE",
                    {
                        "tooltip": "Optional reference image. Switches the request from text-only to image-conditioned generation.",
                    },
                ),
                "is_pano": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Set if the input image is a 360° equirectangular panorama. Ignored when no image is provided.",
                    },
                ),
            },
        }

    def generate(
        self,
        prompt: str,
        model: str,
        seed: int,
        max_wait_seconds: int,
        poll_interval_seconds: int,
        image: torch.Tensor | None = None,
        is_pano: bool = False,
        api_key: str = "",
    ) -> tuple[str, str, str, str, str, str, str, int]:
        client = MarbleClient(api_key=api_key or _get_api_key())

        if image is not None:
            world_prompt = make_image_prompt(
                _tensor_to_png_b64(image),
                extension="png",
                text=prompt or None,
                is_pano=is_pano,
            )
        else:
            world_prompt = make_text_prompt(prompt)

        print(f"[Marble] starting generation (model={model}, seed={seed})")
        op = client.generate_world(world_prompt=world_prompt, model=model, seed=seed)
        operation_id = op["operation_id"]
        print(f"[Marble] operation_id={operation_id}, polling...")

        op = client.wait_for_operation(
            operation_id,
            timeout=max_wait_seconds,
            poll_interval=poll_interval_seconds,
            on_progress=lambda p: print(f"[Marble] progress: {p.get('status', p) if isinstance(p, dict) else p}"),
            check_interrupt=_check_interrupt,
        )

        if op.get("error"):
            raise RuntimeError(f"Marble generation failed: {op['error']}")

        world = op.get("response") or {}
        world_id = world.get("world_id", "")
        assets = world.get("assets") or {}
        pano_url = (assets.get("imagery") or {}).get("pano_url", "") or ""
        mesh_url = (assets.get("mesh") or {}).get("collider_mesh_url", "") or ""
        splats = assets.get("splats") or {}
        spz_urls = splats.get("spz_urls") or {}
        splat_urls_json = json.dumps(spz_urls)
        semantics_metadata_json = json.dumps(splats.get("semantics_metadata") or {})
        thumbnail_url = assets.get("thumbnail_url", "") or ""
        world_marble_url = world.get("world_marble_url", "") or ""
        cost_credits = int((op.get("cost") or {}).get("total_credits", 0) or 0)

        print(f"[Marble] done world_id={world_id}, spz keys={list(spz_urls.keys())}, credits={cost_credits}")
        return (
            world_id,
            splat_urls_json,
            mesh_url,
            pano_url,
            thumbnail_url,
            world_marble_url,
            semantics_metadata_json,
            cost_credits,
        )
