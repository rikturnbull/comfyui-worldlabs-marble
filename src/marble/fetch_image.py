"""MarbleFetchImage node."""

from __future__ import annotations

from inspect import cleandoc
from typing import Any

import torch

from .common import _url_to_tensor


class MarbleFetchImage:
    """Fetch a Marble image URL (pano or thumbnail) and return a ComfyUI IMAGE."""

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "fetch"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "url": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Image URL from MarbleGenerateWorld (pano_url or thumbnail_url). Decoded into an IMAGE tensor in memory.",
                    },
                ),
            },
        }

    def fetch(self, url: str) -> tuple[torch.Tensor]:
        if not url:
            raise RuntimeError("MarbleFetchImage received an empty URL")
        print(f"[Marble] fetching image: {url}")
        return (_url_to_tensor(url),)
