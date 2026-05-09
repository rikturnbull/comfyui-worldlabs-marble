"""Marble node registration. Each class lives in its own module."""

from __future__ import annotations

from .fetch_image import MarbleFetchImage
from .fetch_mesh import MarbleFetchMesh
from .generate_world import MarbleGenerateWorld
from .save_spz import MarbleSaveSPZ

NODE_CLASS_MAPPINGS = {
    "MarbleGenerateWorld": MarbleGenerateWorld,
    "MarbleFetchImage": MarbleFetchImage,
    "MarbleFetchMesh": MarbleFetchMesh,
    "MarbleSaveSPZ": MarbleSaveSPZ,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MarbleGenerateWorld": "Marble: Generate World",
    "MarbleFetchImage": "Marble: Fetch Image",
    "MarbleFetchMesh": "Marble: Fetch Mesh",
    "MarbleSaveSPZ": "Marble: Save SPZ",
}
