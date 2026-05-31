"""MarbleListWorlds node.

Loads an already-generated world by id and emits the same outputs as
MarbleGenerateWorld, so it can drive the Save/Fetch nodes without paying for a
fresh generation.

The world dropdown is populated client-side: the node's "Update" button (see
web/marble_list_worlds.js) posts the api_key to the /marble/list_worlds route
below, which returns the caller's worlds by name. The combo holds the (unique)
world name; load() resolves that name back to an id via the same worlds_to_items
mapping the dropdown was built from. Because the options are filled in the
frontend rather than in INPUT_TYPES, VALIDATE_INPUTS accepts whatever the
frontend submits.
"""

from __future__ import annotations

import asyncio
from inspect import cleandoc
from typing import Any

from ..marble_api import MarbleClient, world_assets_to_strings
from .common import _get_api_key

_WORLD_PLACEHOLDER = "<press Update>"


def _world_name(world: dict[str, Any]) -> str:
    """Display name for a world list entry (best-effort, schema-tolerant).

    Prefers the user-set display_name, then other name-ish fields, then the
    generation prompt, and finally the id so the entry is never blank.
    """
    world_id = world.get("world_id", "") or ""
    return (
        world.get("display_name") or world.get("name") or world.get("title") or world.get("prompt") or world.get("text_prompt") or world_id
    )


def worlds_to_items(resp: dict[str, Any]) -> list[dict[str, str]]:
    """Map a list_worlds response to [{id, name}] entries with unique names.

    `name` is what the dropdown shows AND what load() resolves back to an id, so
    names must be unique. Duplicates get a short id suffix. The frontend and the
    backend both call this, so the two can never disagree on the labelling.
    """
    worlds = (resp or {}).get("worlds") or []
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for w in worlds:
        world_id = w.get("world_id", "") or ""
        if not world_id:
            continue
        name = _world_name(w)
        if name in seen:
            name = f"{name} ({world_id[:6]})"
        # Extremely unlikely, but guarantee uniqueness rather than risk a clash.
        while name in seen:
            name = f"{name}·"
        seen.add(name)
        items.append({"id": world_id, "name": name})
    return items


class MarbleListWorlds:
    """Load an existing Marble world and output its assets.

    Press "Update" on the node to fetch your worlds (uses the api_key field,
    falling back to WORLDLABS_API_KEY / marble_config.json), then pick one from
    the dropdown. Outputs match Marble: Generate World, so wiring is identical.
    """

    CATEGORY = "Marble"
    DESCRIPTION = cleandoc(__doc__)
    RETURN_TYPES = (
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "INT",
    )
    RETURN_NAMES = (
        "world_id",
        "splat_urls_json",
        "mesh_url",
        "pano_url",
        "thumbnail_url",
        "world_marble_url",
        "semantics_metadata_json",
        "cost_credits",
    )
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "api_key": (
                    "STRING",
                    {
                        "default": "",
                        "password": True,
                        "tooltip": "Optional. If empty, falls back to WORLDLABS_API_KEY env var or marble_config.json.",
                    },
                ),
                "world": (
                    [_WORLD_PLACEHOLDER],
                    {
                        "tooltip": "Press 'Update' to fetch your worlds, then pick one by name.",
                    },
                ),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, world: str | None = None, **kwargs: Any) -> bool | str:
        # The dropdown is populated in the frontend, so the submitted name won't
        # be in the static INPUT_TYPES list. Accept anything; load() surfaces a
        # clear error if no world was selected or the name no longer resolves.
        return True

    def load(self, api_key: str, world: str) -> tuple[str, str, str, str, str, str, str, int]:
        if not world or world == _WORLD_PLACEHOLDER:
            raise RuntimeError("No world selected. Enter an API key (or set WORLDLABS_API_KEY), press 'Update', then pick a world.")

        client = MarbleClient(api_key=api_key or _get_api_key())

        # Resolve the selected name back to an id using the SAME mapping the
        # dropdown was built from, so the labels are guaranteed to match.
        items = worlds_to_items(client.list_worlds(page_size=100))
        match = next((i for i in items if i["name"] == world), None)
        if match is None:
            raise RuntimeError(f"World '{world}' was not found. Press 'Update' to refresh the list and pick again.")

        data = client.get_world(match["id"])
        # get_world returns the world object directly; tolerate a {"world": {...}} wrapper.
        world_obj = data.get("world") if isinstance(data.get("world"), dict) else data

        outputs = world_assets_to_strings(world_obj)
        cost_credits = int((world_obj.get("cost") or {}).get("total_credits", 0) or 0)

        print(f"[Marble] loaded world_id={outputs[0]}, credits={cost_credits}")
        return (*outputs, cost_credits)


def list_worlds_items(api_key: str) -> list[dict[str, str]]:
    """Fetch the caller's worlds as [{id, name}] for the /marble/list_worlds route."""
    client = MarbleClient(api_key=api_key or _get_api_key())
    return worlds_to_items(client.list_worlds(page_size=100))


# --- ComfyUI server route (only registers inside a running ComfyUI) -----------
# The handler is a thin wrapper around list_worlds_items() (tested above); this
# registration block only runs under ComfyUI, so it is excluded from coverage.
try:  # pragma: no cover
    from server import PromptServer  # type: ignore
    from aiohttp import web  # type: ignore

    @PromptServer.instance.routes.post("/marble/list_worlds")
    async def _marble_list_worlds(request: "web.Request") -> "web.Response":
        try:
            body = await request.json()
        except Exception:
            body = {}
        api_key = (body or {}).get("api_key") or ""
        try:
            # list_worlds() is blocking requests I/O; keep it off the event loop.
            items = await asyncio.get_event_loop().run_in_executor(None, list_worlds_items, api_key)
            return web.json_response({"worlds": items})
        except Exception as e:  # surface the message to the button's toast
            return web.json_response({"error": str(e)}, status=400)

except ImportError:
    # Imported outside ComfyUI (tests, tooling) — no server to register against.
    pass
