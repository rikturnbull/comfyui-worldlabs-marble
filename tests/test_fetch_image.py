"""Tests for MarbleFetchImage."""

from __future__ import annotations

import io

import pytest
import responses
import torch
from PIL import Image as PILImage

from src.marble.fetch_image import MarbleFetchImage


def _png_bytes(w: int = 4, h: int = 4) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_input_types():
    schema = MarbleFetchImage.INPUT_TYPES()
    assert schema["required"]["url"][0] == "STRING"
    assert schema["required"]["url"][1]["forceInput"] is True


def test_node_attributes():
    assert MarbleFetchImage.CATEGORY == "Marble"
    assert MarbleFetchImage.RETURN_TYPES == ("IMAGE",)
    assert MarbleFetchImage.RETURN_NAMES == ("image",)
    assert MarbleFetchImage.FUNCTION == "fetch"


def test_fetch_raises_on_empty_url():
    with pytest.raises(RuntimeError, match="empty URL"):
        MarbleFetchImage().fetch(url="")


@responses.activate
def test_fetch_returns_image_tensor():
    responses.get(
        "https://cdn.example/img.png",
        body=_png_bytes(8, 4),
        status=200,
        content_type="image/png",
    )
    (image,) = MarbleFetchImage().fetch(url="https://cdn.example/img.png")
    assert isinstance(image, torch.Tensor)
    assert image.shape == (1, 4, 8, 3)
    assert image.dtype == torch.float32


@responses.activate
def test_fetch_propagates_http_error():
    responses.get("https://cdn.example/oops.png", status=500)
    with pytest.raises(Exception):  # noqa: B017 - requests.HTTPError; broad to avoid coupling to internals
        MarbleFetchImage().fetch(url="https://cdn.example/oops.png")
