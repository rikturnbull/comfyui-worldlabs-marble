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
    make_multi_image_prompt,
    make_text_prompt,
    world_assets_to_strings,
)
from .common import _get_api_key, _tensor_batch_to_png_b64, _tensor_to_png_b64


def _parse_azimuths(raw: str, count: int) -> list[float | None] | None:
    """Parse the comma-separated azimuths widget into a per-image list.

    Blank → None (let Marble place the images). An empty slot (e.g. "0,,90")
    leaves that image unplaced. Raises on non-numeric values or more azimuths
    than images.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    result: list[float | None] = []
    for part in (p.strip() for p in raw.split(",")):
        if part == "":
            result.append(None)
            continue
        try:
            result.append(float(part))
        except ValueError as e:
            raise RuntimeError(f"Invalid azimuth value {part!r} in azimuths={raw!r}. Use comma-separated degrees, e.g. '0,180'.") from e
    if len(result) > count:
        raise RuntimeError(f"Got {len(result)} azimuths for {count} image(s); provide at most one per image.")
    return result


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
                        "default": "marble-1.1",
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
                        "min": 600,
                        "max": 7200,
                        "tooltip": "Hard safety-net timeout for the polling loop. Generation typically takes 5-10 minutes; the ComfyUI cancel button interrupts within ~1s regardless of this value.",
                    },
                ),
                "poll_interval_seconds": (
                    "INT",
                    {
                        "default": 30,
                        "min": 15,
                        "max": 60,
                        "tooltip": "How often to check operation status while generation is in progress.",
                    },
                ),
            },
            "optional": {
                "image": (
                    "IMAGE",
                    {
                        "tooltip": "Optional reference image(s). One image → image-conditioned generation; a batch of 2+ (e.g. via Batch Images) → multi-image generation (up to 4, or 8 with reconstruct_images).",
                    },
                ),
                "is_pano": (
                    ["auto", "true", "false"],
                    {
                        "default": "auto",
                        "tooltip": "How to treat the input image as a panorama: 'auto' detects valid equirectangular panoramas, 'true' always uses the image as a panorama, 'false' treats it as a standard image. Single-image only; ignored with no image or a multi-image batch.",
                    },
                ),
                "azimuths": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Multi-image only: comma-separated sphere positions in degrees, aligned to the batched image order (e.g. '0,180'). Blank lets Marble place them. Ignored for a single image.",
                    },
                ),
                "reconstruct_images": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Multi-image only: reconstruction mode — reconstructs the scene from the photos and allows up to 8 images instead of 4. Ignored for a single image.",
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
        is_pano: str = "auto",
        azimuths: str = "",
        reconstruct_images: bool = False,
        api_key: str = "",
    ) -> tuple[str, str, str, str, str, str, str, int]:
        client = MarbleClient(api_key=api_key or _get_api_key())

        if image is None:
            world_prompt = make_text_prompt(prompt)
        elif image.shape[0] == 1:
            # Convert the combo string to the PanoDetectionMode the API expects:
            # "auto" stays as "auto"; "true"/"false" become Python booleans.
            if is_pano == "true":
                pano_mode: bool | str = True
            elif is_pano == "false":
                pano_mode = False
            else:
                pano_mode = "auto"
            world_prompt = make_image_prompt(
                _tensor_to_png_b64(image),
                extension="png",
                text=prompt or None,
                is_pano=pano_mode,
            )
        else:
            count = image.shape[0]
            max_images = 8 if reconstruct_images else 4
            if count > max_images:
                hint = "" if reconstruct_images else " (enable reconstruct_images for up to 8)"
                raise RuntimeError(f"Marble multi-image supports up to {max_images} images{hint}; got {count}.")
            world_prompt = make_multi_image_prompt(
                [(b64, "png") for b64 in _tensor_batch_to_png_b64(image)],
                azimuths=_parse_azimuths(azimuths, count),
                text=prompt or None,
                reconstruct_images=reconstruct_images,
            )

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

        op_world = op.get("response") or {}
        world_id = op_world.get("world_id", "") or ""

        # The operation can report done before all imagery (e.g. pano_url) is
        # populated in its response. get_world() returns the fully-materialised
        # world — the same source Marble: List Worlds reads — so re-fetch it to
        # avoid emitting empty asset URLs. Fall back to the operation response if
        # the fetch fails for any reason.
        world = op_world
        if world_id:
            try:
                full = client.get_world(world_id)
                world = full.get("world") if isinstance(full.get("world"), dict) else full
            except Exception as e:  # noqa: BLE001 - best-effort enrichment, never fatal
                print(f"[Marble] get_world re-fetch failed, using operation response: {e}")
                world = op_world

        outputs = world_assets_to_strings(world)
        cost_credits = int((op.get("cost") or {}).get("total_credits", 0) or 0)

        splat_urls_json = outputs[1]
        print(f"[Marble] done world_id={outputs[0]}, spz keys={list(json.loads(splat_urls_json).keys())}, credits={cost_credits}")
        return (*outputs, cost_credits)
