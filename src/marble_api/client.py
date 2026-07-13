"""Client for the WorldLabs Marble World API v1.

Reference: https://docs.worldlabs.ai/api/reference/openapi
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Literal

import requests

MARBLE_BASE_URL = "https://api.worldlabs.ai"
MARBLE_MODELS = ["marble-1.0", "marble-1.0-draft", "marble-1.1", "marble-1.1-plus"]


class MarbleAPIError(Exception):
    """Raised when the Marble API returns a non-2xx response."""

    def __init__(self, status_code: int, url: str, body: Any):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"Marble API {status_code} from {url}: {body}")


def is_debug() -> bool:
    val = os.environ.get("WLT_DEBUG", "0").lower()
    return val in ("1", "true", "yes", "on")


def _sanitize_body(body: Any) -> Any:
    if isinstance(body, dict):
        out: dict[str, Any] = {}
        for k, v in body.items():
            if k == "data_base64" and isinstance(v, str):
                out[k] = f"<{len(v)} chars base64 redacted>"
            else:
                out[k] = _sanitize_body(v)
        return out
    if isinstance(body, list):
        return [_sanitize_body(v) for v in body]
    return body


def log_request(method: str, url: str, body: Any = None, *, debug: bool | None = None) -> None:
    if debug is None:
        debug = is_debug()
    if not debug:
        return
    print(f"[Marble:debug] -> {method} {url}")
    if body is not None:
        print(f"[Marble:debug]    body: {json.dumps(_sanitize_body(body))}")


def log_response_json(r: requests.Response, *, debug: bool | None = None) -> None:
    if debug is None:
        debug = is_debug()
    if not debug:
        return
    text = r.text
    if len(text) > 4000:
        text = text[:4000] + f"... (+{len(text) - 4000} chars truncated)"
    print(f"[Marble:debug] <- {r.status_code} {r.url}")
    print(f"[Marble:debug]    body: {text}")


def log_response_binary(r: requests.Response, *, debug: bool | None = None) -> None:
    if debug is None:
        debug = is_debug()
    if not debug:
        return
    size = r.headers.get("Content-Length", "?")
    ctype = r.headers.get("Content-Type", "?")
    print(f"[Marble:debug] <- {r.status_code} {r.url}  ({ctype}, {size} bytes)")


def make_text_prompt(text: str) -> dict[str, Any]:
    """Build a text WorldPrompt body."""
    return {"type": "text", "text_prompt": text}


def make_image_prompt(
    data_base64: str,
    extension: str = "png",
    text: str | None = None,
    is_pano: Literal["auto"] | bool = "auto",
) -> dict[str, Any]:
    """Build an image WorldPrompt body using base64-encoded image content."""
    prompt: dict[str, Any] = {
        "type": "image",
        "image_prompt": {
            "source": "data_base64",
            "data_base64": data_base64,
            "extension": extension,
        },
        "is_pano": is_pano,
    }
    if text:
        prompt["text_prompt"] = text
    return prompt


def make_multi_image_prompt(
    images: list[tuple[str, str]],
    azimuths: list[float | None] | None = None,
    text: str | None = None,
    reconstruct_images: bool = False,
) -> dict[str, Any]:
    """Build a multi-image WorldPrompt body from base64-encoded images.

    `images` is a list of ``(data_base64, extension)`` pairs. `azimuths`, if
    given, is a parallel list of sphere positions in degrees (use ``None`` to
    leave an image unplaced). Set `reconstruct_images` for reconstruction mode,
    which allows up to 8 images instead of 4.
    """
    items: list[dict[str, Any]] = []
    for i, (data_base64, extension) in enumerate(images):
        entry: dict[str, Any] = {
            "content": {
                "source": "data_base64",
                "data_base64": data_base64,
                "extension": extension,
            }
        }
        if azimuths is not None and i < len(azimuths) and azimuths[i] is not None:
            entry["azimuth"] = azimuths[i]
        items.append(entry)
    prompt: dict[str, Any] = {"type": "multi-image", "multi_image_prompt": items}
    if text:
        prompt["text_prompt"] = text
    if reconstruct_images:
        prompt["reconstruct_images"] = True
    return prompt


def world_assets_to_strings(world: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    """Extract the standard asset outputs from a Marble world object.

    Accepts the `response` object of a generate operation or the body of a
    GET /worlds/{id} response (both share the same shape). Returns the same
    seven string fields, in the same order, that MarbleGenerateWorld emits
    before its trailing cost_credits INT:

        (world_id, splat_urls_json, mesh_url, pano_url, thumbnail_url,
         world_marble_url, semantics_metadata_json)

    Missing fields default to "" / "{}" so sparse responses don't crash.
    """
    world = world or {}
    assets = world.get("assets") or {}
    splats = assets.get("splats") or {}
    return (
        world.get("world_id", "") or "",
        json.dumps(splats.get("spz_urls") or {}),
        (assets.get("mesh") or {}).get("collider_mesh_url", "") or "",
        (assets.get("imagery") or {}).get("pano_url", "") or "",
        assets.get("thumbnail_url", "") or "",
        world.get("world_marble_url", "") or "",
        json.dumps(splats.get("semantics_metadata") or {}),
    )


class MarbleClient:
    """Thin wrapper over the Marble REST API.

    Methods return raw JSON dicts mirroring the OpenAPI response schemas,
    keeping the surface close to the spec.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = MARBLE_BASE_URL,
        debug: bool | None = None,
        timeout: int = 60,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.debug = debug if debug is not None else is_debug()
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"WLT-Api-Key": self.api_key, "Content-Type": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        log_request(method, url, json_body, debug=self.debug)
        r = requests.request(
            method,
            url,
            json=json_body,
            headers=self._headers,
            timeout=timeout if timeout is not None else self.timeout,
        )
        log_response_json(r, debug=self.debug)
        if not r.ok:
            try:
                detail: Any = r.json()
            except ValueError:
                detail = r.text
            raise MarbleAPIError(r.status_code, url, detail)
        if not r.content:
            return {}
        return r.json()

    # --- Endpoints -------------------------------------------------------

    def get_credits(self) -> dict[str, Any]:
        """GET /marble/v1/credits"""
        return self._request("GET", "/marble/v1/credits")

    def generate_world(
        self,
        world_prompt: dict[str, Any],
        model: str = "marble-1.1",
        seed: int | None = None,
        display_name: str | None = None,
        tags: list[str] | None = None,
        permission: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /marble/v1/worlds:generate. Returns the initial operation."""
        body: dict[str, Any] = {"world_prompt": world_prompt, "model": model}
        if seed is not None:
            body["seed"] = seed
        if display_name is not None:
            body["display_name"] = display_name
        if tags is not None:
            body["tags"] = tags
        if permission is not None:
            body["permission"] = permission
        return self._request("POST", "/marble/v1/worlds:generate", body)

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        """GET /marble/v1/operations/{operation_id}"""
        return self._request("GET", f"/marble/v1/operations/{operation_id}")

    def wait_for_operation(
        self,
        operation_id: str,
        timeout: int = 600,
        poll_interval: int = 5,
        on_progress: Callable[[Any], None] | None = None,
        check_interrupt: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Poll get_operation until done=true, the deadline is hit, or error is set.

        Returns the final operation. Does NOT raise on operation-level errors —
        callers should inspect op['error']. Raises TimeoutError on deadline.

        If check_interrupt is provided, it is called at least once per second
        during the poll loop. Raise from it (e.g. ComfyUI's
        InterruptProcessingException) to cancel the wait promptly without
        waiting out the deadline.
        """
        deadline = time.monotonic() + timeout
        last_progress: Any = None

        def emit_progress(o: dict[str, Any]) -> None:
            nonlocal last_progress
            progress = (o.get("metadata") or {}).get("progress")
            if on_progress is not None and progress is not None and progress != last_progress:
                on_progress(progress)
                last_progress = progress

        def interruptible_sleep(seconds: float) -> None:
            end = time.monotonic() + seconds
            while True:
                if check_interrupt is not None:
                    check_interrupt()
                remaining = end - time.monotonic()
                if remaining <= 0:
                    return
                time.sleep(min(1.0, remaining))

        if check_interrupt is not None:
            check_interrupt()
        op = self.get_operation(operation_id)
        emit_progress(op)
        while not op.get("done"):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"operation {operation_id} did not complete within {timeout}s")
            interruptible_sleep(poll_interval)
            op = self.get_operation(operation_id)
            emit_progress(op)
        return op

    def get_world(self, world_id: str) -> dict[str, Any]:
        """GET /marble/v1/worlds/{world_id}"""
        return self._request("GET", f"/marble/v1/worlds/{world_id}")

    def delete_world(self, world_id: str) -> dict[str, Any]:
        """DELETE /marble/v1/worlds/{world_id}"""
        return self._request("DELETE", f"/marble/v1/worlds/{world_id}")

    def export_world(
        self,
        world_id: str,
        asset_type: Literal["splats", "mesh"],
        format: Literal["ply", "glb"],
        mesh_variant: Literal["textured", "vertex_colored"] | None = None,
        resolution: Literal["full_res", "500k", "150k", "100k"] | None = None,
    ) -> dict[str, Any]:
        """POST /marble/v1/worlds/{world_id}:export. Returns an ExportWorldResponse operation.

        PLY splat exports are completed synchronously (done=True immediately).
        HQ mesh exports return an in-progress operation; poll with get_operation.
        """
        body: dict[str, Any] = {"asset_type": asset_type, "format": format}
        if mesh_variant is not None:
            body["mesh_variant"] = mesh_variant
        if resolution is not None:
            body["resolution"] = resolution
        return self._request("POST", f"/marble/v1/worlds/{world_id}:export", body)

    def list_worlds(
        self,
        page_size: int = 20,
        page_token: str | None = None,
        status: str | None = None,
        model: str | None = None,
        tags: list[str] | None = None,
        is_public: bool | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_by: str = "created_at",
    ) -> dict[str, Any]:
        """POST /marble/v1/worlds:list"""
        body: dict[str, Any] = {"page_size": page_size, "sort_by": sort_by}
        if page_token is not None:
            body["page_token"] = page_token
        if status is not None:
            body["status"] = status
        if model is not None:
            body["model"] = model
        if tags is not None:
            body["tags"] = tags
        if is_public is not None:
            body["is_public"] = is_public
        if created_after is not None:
            body["created_after"] = created_after
        if created_before is not None:
            body["created_before"] = created_before
        return self._request("POST", "/marble/v1/worlds:list", body)
