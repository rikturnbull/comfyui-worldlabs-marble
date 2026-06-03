"""MarbleFetchSPZ node: download one SPZ splat into memory."""

from __future__ import annotations

import json
from inspect import cleandoc
from typing import Any

import requests

from ..marble_api import log_request, log_response_binary
from .common import MARBLE_SPZ_LOD_KEYS, SpzData


class MarbleFetchSPZ:
    """Download a single Marble SPZ splat (by LOD) into an in-memory SPZ value.

    Takes the JSON map of spz_urls from MarbleGenerateWorld and fetches the one
    LOD you pick. The resulting SPZ output can be wired into Marble: Save SPZ
    (to write it to disk) and/or Marble: Convert SPZ to PLY — nothing touches
    disk until one of those nodes runs.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = ("SPZ",)
    RETURN_NAMES = ("spz",)
    FUNCTION = "fetch"

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
                        "tooltip": "World identifier from MarbleGenerateWorld. Carried into the SPZ value to scope output paths.",
                    },
                ),
            },
            "optional": {
                "key": (
                    MARBLE_SPZ_LOD_KEYS,
                    {
                        "default": "full_res",
                        "tooltip": "Which level of detail to download.",
                    },
                ),
            },
        }

    def fetch(
        self,
        splat_urls_json: str,
        world_id: str,
        key: str = "full_res",
    ) -> tuple[SpzData]:
        try:
            urls: dict[str, str] = json.loads(splat_urls_json) if splat_urls_json else {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"splat_urls_json is not valid JSON: {e}") from e

        urls = {k: v for k, v in urls.items() if v}
        if not urls:
            raise RuntimeError("splat_urls_json contains no usable URLs")
        if key not in urls:
            raise RuntimeError(f"key '{key}' not found in splat_urls_json. Available keys: {sorted(urls.keys())}")

        url = urls[key]
        print(f"[Marble] downloading SPZ '{key}'")
        log_request("GET", url)
        r = requests.get(url, timeout=120)
        log_response_binary(r)
        r.raise_for_status()

        return (SpzData(data=r.content, key=key, world_id=world_id or "unknown"),)
