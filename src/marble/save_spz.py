"""MarbleSaveSPZ node."""

from __future__ import annotations

import os
from inspect import cleandoc
from typing import Any

from .common import SpzData, _output_directory


class MarbleSaveSPZ:
    """Write an in-memory SPZ splat (from Marble: Fetch SPZ) to disk.

    Saves to <ComfyUI output>/<subfolder>/<world_id>/splats/<name>.spz, where
    <name> defaults to the splat's LOD key.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("spz_path", "folder")
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "spz": (
                    "SPZ",
                    {
                        "forceInput": True,
                        "tooltip": "SPZ splat from Marble: Fetch SPZ.",
                    },
                ),
            },
            "optional": {
                "filename": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Base filename (no extension). Empty uses the splat's LOD key.",
                    },
                ),
                "subfolder": (
                    "STRING",
                    {
                        "default": "marble",
                        "tooltip": "Subdirectory under ComfyUI/output/. Final path: <output>/<subfolder>/<world_id>/splats/<name>.spz.",
                    },
                ),
            },
        }

    def save(
        self,
        spz: SpzData,
        filename: str = "",
        subfolder: str = "marble",
    ) -> tuple[str, str]:
        if not spz or not spz.data:
            raise RuntimeError("MarbleSaveSPZ received an empty SPZ")

        name = filename.strip() or spz.key
        folder = os.path.join(_output_directory(), subfolder, spz.world_id or "unknown", "splats")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, f"{name}.spz")

        print(f"[Marble] saving SPZ -> {dest}")
        with open(dest, "wb") as f:
            f.write(spz.data)
        print(f"[Marble] saved SPZ ({len(spz.data)} bytes) to {dest}")
        return (dest, folder)
