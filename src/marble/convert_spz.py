"""MarbleConvertSPZ node: decode an in-memory SPZ splat to a standard .ply."""

from __future__ import annotations

import os
from inspect import cleandoc
from typing import Any

from .common import SpzData, _output_directory
from .spz_codec import spz_bytes_to_ply_bytes


class MarbleConvertSPZ:
    """Convert an SPZ gaussian splat (from Marble: Fetch SPZ) to a standard .ply.

    Decodes the splat in pure Python and writes the uncompressed INRIA-layout
    PLY that most splat viewers and tools expect. PLY is roughly 10x larger
    than the SPZ.

    By default writes to <output>/<subfolder>/<world_id>/splats/<key>.ply;
    set ply_path to override.

    Outputs:
      - ply_path (STRING): the written .ply file path on disk.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("ply_path",)
    FUNCTION = "convert"
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
                "ply_path": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Output .ply path. Empty writes to <output>/<subfolder>/<world_id>/splats/<key>.ply. Relative paths are under ComfyUI/output/.",
                    },
                ),
                "subfolder": (
                    "STRING",
                    {
                        "default": "marble",
                        "tooltip": "Subdirectory under ComfyUI/output/ for the default output path. Ignored when ply_path is set.",
                    },
                ),
            },
        }

    def convert(self, spz: SpzData, ply_path: str = "", subfolder: str = "marble") -> tuple[str]:
        if not spz or not spz.data:
            raise RuntimeError("MarbleConvertSPZ received an empty SPZ")

        dest = ply_path.strip()
        if not dest:
            dest = os.path.join(subfolder, spz.world_id or "unknown", "splats", f"{spz.key}.ply")
        if not dest.lower().endswith(".ply"):
            dest += ".ply"
        if not os.path.isabs(dest):
            dest = os.path.join(_output_directory(), dest)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

        print(f"[Marble] converting SPZ '{spz.key}' -> PLY: {dest}")
        ply = spz_bytes_to_ply_bytes(spz.data)
        with open(dest, "wb") as f:
            f.write(ply)
        print(f"[Marble] wrote PLY ({len(ply)} bytes) to {dest}")
        return (dest,)
