"""MarbleSaveSPZ node."""

from __future__ import annotations

import json
import os
from inspect import cleandoc
from typing import Any

import requests

from ..marble_api import log_request, log_response_binary
from .common import MARBLE_SPZ_KEYS, _output_directory


class MarbleSaveSPZ:
    """Download Marble SPZ splat assets to disk.

    Takes the JSON map of spz_urls produced by MarbleGenerateWorld and writes
    each entry to <ComfyUI output>/<subfolder>/<world_id>/splats/<key>.spz.
    Pick a specific LOD via 'key', or use 'all' to download every entry.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("primary_spz_path", "folder")
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "splat_urls_json": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "JSON map of LOD name → SPZ URL, from MarbleGenerateWorld's splat_urls_json output.",
                    },
                ),
                "world_id": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "World identifier from MarbleGenerateWorld. Used to scope the output folder per world.",
                    },
                ),
            },
            "optional": {
                "key": (
                    MARBLE_SPZ_KEYS,
                    {
                        "default": "all",
                        "tooltip": "'all' downloads every entry; otherwise just the named LOD.",
                    },
                ),
                "subfolder": (
                    "STRING",
                    {
                        "default": "marble",
                        "tooltip": "Subdirectory under ComfyUI/output/. Final path: <output>/<subfolder>/<world_id>/splats/<key>.spz.",
                    },
                ),
            },
        }

    def save(
        self,
        splat_urls_json: str,
        world_id: str,
        key: str = "all",
        subfolder: str = "marble",
    ) -> tuple[str, str]:
        try:
            urls: dict[str, str] = json.loads(splat_urls_json) if splat_urls_json else {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"splat_urls_json is not valid JSON: {e}") from e

        urls = {k: v for k, v in urls.items() if v}
        if not urls:
            raise RuntimeError("splat_urls_json contains no usable URLs")

        if key and key != "all":
            if key not in urls:
                raise RuntimeError(f"key '{key}' not found in splat_urls_json. Available keys: {sorted(urls.keys())}")
            urls = {key: urls[key]}

        safe_world_id = world_id or "unknown"
        folder = os.path.join(_output_directory(), subfolder, safe_world_id, "splats")
        os.makedirs(folder, exist_ok=True)

        saved: list[str] = []
        for k, url in urls.items():
            dest = os.path.join(folder, f"{k}.spz")
            print(f"[Marble] downloading SPZ '{k}' -> {dest}")
            log_request("GET", url)
            r = requests.get(url, timeout=120, stream=True)
            log_response_binary(r)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
            saved.append(dest)

        primary = saved[0]
        print(f"[Marble] saved {len(saved)} SPZ file(s) to {folder}")
        return (primary, folder)
