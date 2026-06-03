"""ComfyUI-specific helpers for Marble nodes.

API/HTTP/logging logic lives in the sibling `marble_api` package. This
module only contains things that depend on ComfyUI runtime (folder_paths,
torch tensors) or on local filesystem state (config file, package layout).
"""

from __future__ import annotations

import base64
import io
import json
import os
from dataclasses import dataclass

import numpy as np
import requests
import torch
from PIL import Image as PILImage

from ..marble_api import log_request, log_response_binary

try:
    import folder_paths  # provided by ComfyUI at runtime
except ImportError:
    folder_paths = None

MARBLE_SPZ_KEYS = ["all", "full_res", "500k", "150k", "100k"]
# Single-LOD choices for Fetch SPZ (no "all" — it emits exactly one splat).
MARBLE_SPZ_LOD_KEYS = ["full_res", "500k", "150k", "100k"]


@dataclass
class SpzData:
    """One downloaded SPZ splat, passed between Marble nodes on the SPZ socket.

    Carries the raw .spz bytes plus the LOD `key` and `world_id` so downstream
    Save / Convert nodes can build sensible per-world output paths without
    needing those wired in again.
    """

    data: bytes
    key: str = "full_res"
    world_id: str = "unknown"


def _package_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _get_api_key() -> str:
    key = os.environ.get("WORLDLABS_API_KEY")
    if key:
        return key
    config_path = os.path.join(_package_root(), "marble_config.json")
    if not os.path.exists(config_path):
        raise RuntimeError(
            "WORLDLABS_API_KEY not found. Either set the WORLDLABS_API_KEY environment variable, "
            f"or create {config_path} with content like:\n"
            '  {"api_key": "your-key-here"}'
        )
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
    except OSError as e:
        raise RuntimeError(f"could not read {config_path}: {e}") from e
    if not content:
        raise RuntimeError(f"{config_path} exists but is empty.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{config_path} contains invalid JSON: {e}. First 80 chars: {content[:80]!r}") from e
    key = data.get("api_key") or data.get("WORLDLABS_API_KEY")
    if not key:
        raise RuntimeError(f"{config_path} loaded but has no 'api_key' field. Found keys: {list(data.keys())}")
    return key


def _tensor_to_png_b64(image: torch.Tensor) -> str:
    arr = image[0].detach().cpu().numpy()
    arr = (arr * 255.0).clip(0, 255).astype(np.uint8)
    pil = PILImage.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _tensor_batch_to_png_b64(image: torch.Tensor) -> list[str]:
    """Encode every image in a ComfyUI IMAGE batch (B, H, W, C) to PNG base64."""
    return [_tensor_to_png_b64(image[i : i + 1]) for i in range(image.shape[0])]


def _url_to_tensor(url: str) -> torch.Tensor:
    log_request("GET", url)
    r = requests.get(url, timeout=60)
    log_response_binary(r)
    r.raise_for_status()
    pil = PILImage.open(io.BytesIO(r.content)).convert("RGB")
    arr = np.array(pil).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _output_directory() -> str:
    if folder_paths is not None:
        return folder_paths.get_output_directory()
    return os.path.abspath("output")
