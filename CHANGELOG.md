# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Four ComfyUI nodes for the WorldLabs Marble API:
  - **Marble: Generate World** — text or image-conditioned 3D world generation with progress polling.
  - **Marble: Fetch Image** — pano/thumbnail URL → ComfyUI `IMAGE` tensor.
  - **Marble: Fetch Mesh** — collider mesh URL → file path and `FILE_3D_GLB` typed output (compatible with Save 3D Model / Preview 3D / SaveGLB).
  - **Marble: Save SPZ** — Niantic SPZ Gaussian splat downloads with LOD selection (`all`, `full_res`, `500k`, `150k`, `100k`).
- Standalone `marble_api` Python package — independent client for the WorldLabs Marble API. Endpoints: `health_check`, `generate_world`, `get_operation`, `wait_for_operation`, `get_world`, `delete_world`, `list_worlds`. Helpers for building text/image `WorldPrompt` bodies.
- API key resolution order: `api_key` node input → `WORLDLABS_API_KEY` env var → `marble_config.json` in the package root.
- Debug HTTP logging gated by `WLT_DEBUG` (default on). Base64 image data and the API key are redacted before logging.
- Tooltips on every node input.
- Test suite using `responses` for HTTP stubs and `monkeypatch` for ComfyUI runtime shims; runs without ComfyUI installed.
- CI workflows:
  - `test.yml` — pytest matrix on Python 3.10 / 3.11 / 3.12 with a 100% coverage gate, plus pre-commit (ruff lint + format).
  - `validate.yml` — Comfy Org `node-diff` backwards-compatibility check.
  - `publish_node.yml` — publishes to the Comfy Registry on tag push.
  - `check-marble-api.yml` — daily diff of the WorldLabs OpenAPI spec; opens an issue assigned to Copilot if the spec changes, with a prepared branch carrying the snapshot update.
