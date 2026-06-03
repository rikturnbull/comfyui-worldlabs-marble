"""Marble node registration. Each class lives in its own module."""

from __future__ import annotations

from .convert_spz import MarbleConvertSPZ
from .fetch_image import MarbleFetchImage
from .fetch_mesh import MarbleFetchMesh
from .fetch_spz import MarbleFetchSPZ
from .generate_world import MarbleGenerateWorld
from .list_worlds import MarbleListWorlds
from .save_spz import MarbleSaveSPZ

NODE_CLASS_MAPPINGS = {
    "MarbleGenerateWorld": MarbleGenerateWorld,
    "MarbleListWorlds": MarbleListWorlds,
    "MarbleFetchImage": MarbleFetchImage,
    "MarbleFetchMesh": MarbleFetchMesh,
    "MarbleFetchSPZ": MarbleFetchSPZ,
    "MarbleSaveSPZ": MarbleSaveSPZ,
    "MarbleConvertSPZ": MarbleConvertSPZ,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MarbleGenerateWorld": "Marble: Generate World",
    "MarbleListWorlds": "Marble: List Worlds",
    "MarbleFetchImage": "Marble: Fetch Image",
    "MarbleFetchMesh": "Marble: Fetch Mesh",
    "MarbleFetchSPZ": "Marble: Fetch SPZ",
    "MarbleSaveSPZ": "Marble: Save SPZ",
    "MarbleConvertSPZ": "Marble: Convert SPZ to PLY",
}
