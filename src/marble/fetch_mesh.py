"""MarbleFetchMesh node."""

from __future__ import annotations

import os
from inspect import cleandoc
from typing import Any
from urllib.parse import urlparse

import requests

from ..marble_api import log_request, log_response_binary
from .common import _output_directory

try:
    from comfy_api.latest import Types as _ComfyTypes  # File3D wrapper used by Preview3D / SaveGLB
except ImportError:
    _ComfyTypes = None


def _wrap_file3d(path: str) -> Any:
    """Wrap a path in a Types.File3D instance for FILE3DGLB-typed consumers.

    Falls back to the plain path string if the new ComfyUI API isn't available,
    which works for nodes that accept STRING as a fallback (e.g. Preview3D).
    """
    if _ComfyTypes is not None:
        try:
            return _ComfyTypes.File3D(path)
        except Exception as e:  # noqa: BLE001 - broad catch is intentional for safe fallback
            print(f"[Marble] could not construct comfy_api Types.File3D: {e}; returning path string")
    return path


class MarbleFetchMesh:
    """Download a Marble mesh URL to disk and return its file path plus a typed GLB.

    Saves to <ComfyUI output>/<subfolder>/<world_id>/<filename><ext>, where
    <ext> is inferred from the URL (default .glb).

    Outputs:
      - mesh_path (STRING): the file path on disk.
      - glb (FILE_3D_GLB): a typed handle compatible with Preview 3D, Save 3D
        Model (SaveGLB), and other 3D-model-consuming nodes.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = ("STRING", "FILE_3D_GLB")
    RETURN_NAMES = ("mesh_path", "glb")
    FUNCTION = "fetch"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "url": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Mesh URL from MarbleGenerateWorld (mesh_url). The file is streamed to disk.",
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
                "filename": (
                    "STRING",
                    {
                        "default": "collider_mesh",
                        "tooltip": "Base filename. The extension is inferred from the URL (default .glb).",
                    },
                ),
                "subfolder": (
                    "STRING",
                    {
                        "default": "marble",
                        "tooltip": "Subdirectory under ComfyUI/output/. Final path: <output>/<subfolder>/<world_id>/<filename><ext>.",
                    },
                ),
            },
        }

    def fetch(
        self,
        url: str,
        world_id: str,
        filename: str = "collider_mesh",
        subfolder: str = "marble",
    ) -> tuple[str, Any]:
        if not url:
            raise RuntimeError("MarbleFetchMesh received an empty URL")

        parsed_path = urlparse(url).path
        ext = os.path.splitext(parsed_path)[1].lower() or ".glb"

        safe_world_id = world_id or "unknown"
        folder = os.path.join(_output_directory(), subfolder, safe_world_id)
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, f"{filename}{ext}")

        print(f"[Marble] downloading mesh -> {dest}")
        log_request("GET", url)
        r = requests.get(url, timeout=120, stream=True)
        log_response_binary(r)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if chunk:
                    f.write(chunk)
        print(f"[Marble] saved mesh to {dest}")
        return (dest, _wrap_file3d(dest))
