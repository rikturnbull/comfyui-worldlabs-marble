"""Top-level package for marble.

ComfyUI loads this file as a package, where the relative `.src.marble.nodes`
import resolves correctly. pytest / pip-editable / standalone scripts load
it without the package context, where the relative import fails. We try the
relative import first and fall back to a sys.path-based absolute import.
"""

try:
    from .src.marble.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS  # noqa: F401
except ImportError:
    # No parent-package context. Put the repo root on sys.path so the `src`
    # namespace package is findable, then absolute-import.
    import os as _os
    import sys as _sys

    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from src.marble.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS  # noqa: E402,F401

# Frontend assets (e.g. the Marble: List Worlds "Update" button). ComfyUI serves
# every .js under this directory and auto-loads it as an extension.
WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]

__author__ = """ComfyUI-Marble"""
__email__ = "rik@controlz.co.uk"
__version__ = "0.0.1"
