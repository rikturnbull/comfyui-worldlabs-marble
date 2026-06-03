# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Seven ComfyUI nodes for the WorldLabs Marble API:
  - **Marble: Generate World** — text or image-conditioned 3D world generation with progress polling. Accepts a batched `IMAGE` input: a single image uses image-conditioned generation (unchanged), while a batch of 2+ switches to multi-image generation (up to 4 images, or 8 with `reconstruct_images`), with optional per-image `azimuths`.
  - **Marble: List Worlds** — loads an existing world; outputs match Generate World, so it's a drop-in source for the Fetch/Save nodes with no generation cost. The world dropdown is populated client-side via an **Update** button (JS frontend) that calls a `/marble/list_worlds` server route; selection is by world name, resolved back to an id on run.
  - **Marble: Fetch Image** — pano/thumbnail URL → ComfyUI `IMAGE` tensor.
  - **Marble: Fetch Mesh** — collider mesh URL → file path and `FILE_3D_GLB` typed output (compatible with Save 3D Model / Preview 3D / SaveGLB).
  - **Marble: Fetch SPZ** — downloads one Niantic SPZ Gaussian splat LOD (`full_res` / `500k` / `150k` / `100k`) into an in-memory `SPZ` value that fans out to Save SPZ and/or Convert SPZ to PLY.
  - **Marble: Save SPZ** — writes an `SPZ` value to disk as a `.spz` file.
  - **Marble: Convert SPZ to PLY** — converts an `SPZ` value to a standard INRIA-layout `.ply` (binary_little_endian). Pure-Python decoder (numpy + stdlib only, no compiled bindings); supports SPZ v1/v2/v3 including the v3 "smallest three" quaternion packing and spherical harmonics up to degree 3.
- `WEB_DIRECTORY` JS frontend (`web/marble_list_worlds.js`) for the List Worlds Update button, with a busy state (label/cursor) and non-blocking toast notifications.
- Standalone `marble_api` Python package — independent client for the WorldLabs Marble API. Endpoints: `health_check`, `generate_world`, `get_operation`, `wait_for_operation`, `get_world`, `delete_world`, `list_worlds`. Helpers for building text / image / multi-image `WorldPrompt` bodies.
- API key resolution order: `api_key` node input → `WORLDLABS_API_KEY` env var → `marble_config.json` in the package root.
- Debug HTTP logging gated by `WLT_DEBUG` (default on). Base64 image data and the API key are redacted before logging.
- Tooltips on every node input.
- Test suite using `responses` for HTTP stubs and `monkeypatch` for ComfyUI runtime shims; runs without ComfyUI installed.
- CI workflows:
  - `test.yml` — pytest matrix on Python 3.10 / 3.11 / 3.12 with a 100% coverage gate, plus pre-commit (ruff lint + format).
  - `validate.yml` — Comfy Org `node-diff` backwards-compatibility check.
  - `publish_node.yml` — publishes to the Comfy Registry on tag push.
  - `check-marble-api.yml` — daily diff of the WorldLabs OpenAPI spec; on a change it opens a PR that already updates the stored snapshot and asks Copilot to make any matching `client.py` changes on the same branch.

### Fixed

- **Marble: Generate World** now re-fetches the completed world via `get_world` before returning, so asset URLs (e.g. `pano_url`) that the generation operation hadn't populated yet are no longer emitted empty. Falls back to the operation response if the re-fetch fails.
