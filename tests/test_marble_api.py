"""Tests for the marble_api package: client, helpers, errors, logging."""

from __future__ import annotations

import json

import pytest
import responses

from src.marble_api import (
    MARBLE_BASE_URL,
    MARBLE_MODELS,
    MarbleAPIError,
    MarbleClient,
    is_debug,
    log_request,
    log_response_binary,
    log_response_json,
    make_image_prompt,
    make_multi_image_prompt,
    make_text_prompt,
)
from src.marble_api.client import _sanitize_body


# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------


def test_marble_models_includes_known_versions():
    assert "marble-1.0" in MARBLE_MODELS
    assert "marble-1.1" in MARBLE_MODELS


def test_make_text_prompt_shape():
    assert make_text_prompt("hello") == {"type": "text", "text_prompt": "hello"}


def test_make_image_prompt_minimal():
    body = make_image_prompt("BASE64", extension="png")
    assert body["type"] == "image"
    assert body["image_prompt"] == {
        "source": "data_base64",
        "data_base64": "BASE64",
        "extension": "png",
    }
    assert body["is_pano"] == "auto"
    assert "text_prompt" not in body


def test_make_image_prompt_with_text_and_pano():
    body = make_image_prompt("DATA", extension="jpg", text="caption", is_pano=True)
    assert body["text_prompt"] == "caption"
    assert body["is_pano"] is True
    assert body["image_prompt"]["extension"] == "jpg"


def test_make_image_prompt_with_auto_pano_mode():
    body = make_image_prompt("DATA", extension="jpg", is_pano="auto")
    assert body["is_pano"] == "auto"


def test_make_image_prompt_omits_empty_text():
    body = make_image_prompt("DATA", text="")
    assert "text_prompt" not in body
    body = make_image_prompt("DATA", text=None)
    assert "text_prompt" not in body


def test_make_multi_image_prompt_basic():
    body = make_multi_image_prompt([("aaa", "png"), ("bbb", "jpg")], text="two views")
    assert body["type"] == "multi-image"
    assert len(body["multi_image_prompt"]) == 2
    assert body["multi_image_prompt"][0]["content"] == {
        "source": "data_base64",
        "data_base64": "aaa",
        "extension": "png",
    }
    assert "azimuth" not in body["multi_image_prompt"][0]
    assert body["text_prompt"] == "two views"
    assert "reconstruct_images" not in body  # omitted when False


def test_make_multi_image_prompt_azimuths_and_reconstruct():
    body = make_multi_image_prompt(
        [("a", "png"), ("b", "png")],
        azimuths=[0.0, None],  # second image left unplaced
        reconstruct_images=True,
    )
    assert body["multi_image_prompt"][0]["azimuth"] == 0.0
    assert "azimuth" not in body["multi_image_prompt"][1]
    assert body["reconstruct_images"] is True
    assert "text_prompt" not in body


# ---------------------------------------------------------------------------
# MarbleAPIError
# ---------------------------------------------------------------------------


def test_marble_api_error_carries_metadata():
    err = MarbleAPIError(404, "https://x.example/y", {"detail": "nope"})
    assert err.status_code == 404
    assert err.url == "https://x.example/y"
    assert err.body == {"detail": "nope"}
    assert "404" in str(err)
    assert "nope" in str(err)


# ---------------------------------------------------------------------------
# is_debug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_is_debug_truthy(monkeypatch, val):
    monkeypatch.setenv("WLT_DEBUG", val)
    assert is_debug() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "garbage", ""])
def test_is_debug_falsy(monkeypatch, val):
    monkeypatch.setenv("WLT_DEBUG", val)
    assert is_debug() is False


def test_is_debug_default_when_unset(monkeypatch):
    monkeypatch.delenv("WLT_DEBUG", raising=False)
    assert is_debug() is False


# ---------------------------------------------------------------------------
# Body sanitization
# ---------------------------------------------------------------------------


def test_sanitize_body_redacts_data_base64():
    body = {"world_prompt": {"image_prompt": {"data_base64": "x" * 100}}}
    out = _sanitize_body(body)
    assert "x" * 100 not in json.dumps(out)
    assert "100 chars base64 redacted" in out["world_prompt"]["image_prompt"]["data_base64"]


def test_sanitize_body_recurses_lists():
    body = [{"data_base64": "abc"}, {"keep": "yes"}]
    out = _sanitize_body(body)
    assert "redacted" in out[0]["data_base64"]
    assert out[1] == {"keep": "yes"}


def test_sanitize_body_passes_scalars():
    assert _sanitize_body("hello") == "hello"
    assert _sanitize_body(42) == 42
    assert _sanitize_body(None) is None


def test_sanitize_body_keeps_non_string_data_base64():
    # If for some reason data_base64 is not a string, leave it alone.
    body = {"data_base64": 123}
    assert _sanitize_body(body) == {"data_base64": 123}


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def test_log_request_silent_when_debug_off(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "0")
    log_request("GET", "https://x.example/a", body={"k": "v"})
    assert capsys.readouterr().out == ""


def test_log_request_prints_when_debug_on(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "1")
    log_request("POST", "https://x.example/a", body={"k": "v"})
    out = capsys.readouterr().out
    assert "POST https://x.example/a" in out
    assert '"k": "v"' in out


def test_log_request_redacts_base64(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "1")
    log_request("POST", "https://x.example/a", body={"data_base64": "x" * 50})
    out = capsys.readouterr().out
    assert "x" * 50 not in out
    assert "redacted" in out


def test_log_request_explicit_debug_flag_overrides_env(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "0")
    log_request("GET", "https://x.example/a", debug=True)
    assert "GET https://x.example/a" in capsys.readouterr().out


def test_log_response_json_silent_when_debug_off(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "0")
    fake = type("R", (), {"text": "{}", "status_code": 200, "url": "https://x"})()
    log_response_json(fake)
    assert capsys.readouterr().out == ""


def test_log_response_json_truncates_long_bodies(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "1")
    long_text = "a" * 5000
    fake = type("R", (), {"text": long_text, "status_code": 200, "url": "https://x"})()
    log_response_json(fake)
    out = capsys.readouterr().out
    assert "(+1000 chars truncated)" in out


def test_log_response_binary_prints_headers(capsys, monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "1")
    fake = type(
        "R",
        (),
        {
            "status_code": 200,
            "url": "https://x.example/file",
            "headers": {"Content-Length": "12345", "Content-Type": "application/octet-stream"},
        },
    )()
    log_response_binary(fake)
    out = capsys.readouterr().out
    assert "200 https://x.example/file" in out
    assert "12345 bytes" in out
    assert "application/octet-stream" in out


# ---------------------------------------------------------------------------
# MarbleClient construction and headers
# ---------------------------------------------------------------------------


def test_client_requires_api_key():
    with pytest.raises(ValueError):
        MarbleClient(api_key="")


def test_client_default_base_url():
    c = MarbleClient(api_key="k")
    assert c.base_url == MARBLE_BASE_URL
    assert c.api_key == "k"
    assert c.timeout == 60


def test_client_strips_trailing_slash():
    c = MarbleClient(api_key="k", base_url="https://x.example/")
    assert c.base_url == "https://x.example"


def test_client_headers_include_api_key():
    c = MarbleClient(api_key="abc")
    assert c._headers == {"WLT-Api-Key": "abc", "Content-Type": "application/json"}


def test_client_debug_defaults_from_env(monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "0")
    assert MarbleClient(api_key="k").debug is False
    monkeypatch.setenv("WLT_DEBUG", "1")
    assert MarbleClient(api_key="k").debug is True


def test_client_debug_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("WLT_DEBUG", "0")
    assert MarbleClient(api_key="k", debug=True).debug is True


# ---------------------------------------------------------------------------
# MarbleClient endpoints
# ---------------------------------------------------------------------------


@responses.activate
def test_get_credits():
    responses.get(f"{MARBLE_BASE_URL}/marble/v1/credits", json={"remaining_credits": 12.5})
    assert MarbleClient(api_key="k").get_credits() == {"remaining_credits": 12.5}


@responses.activate
def test_generate_world_minimal_body():
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1", "done": False},
    )
    c = MarbleClient(api_key="k")
    op = c.generate_world(world_prompt={"type": "text", "text_prompt": "hi"})
    assert op["operation_id"] == "op1"
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {
        "world_prompt": {"type": "text", "text_prompt": "hi"},
        "model": "marble-1.1",
    }
    assert responses.calls[0].request.headers["WLT-Api-Key"] == "k"


@responses.activate
def test_generate_world_includes_optional_fields():
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"operation_id": "op1"},
    )
    MarbleClient(api_key="k").generate_world(
        world_prompt={"type": "text", "text_prompt": "hi"},
        model="marble-1.1",
        seed=42,
        display_name="my-world",
        tags=["test", "demo"],
        permission={"public": True},
    )
    sent = json.loads(responses.calls[0].request.body)
    assert sent["model"] == "marble-1.1"
    assert sent["seed"] == 42
    assert sent["display_name"] == "my-world"
    assert sent["tags"] == ["test", "demo"]
    assert sent["permission"] == {"public": True}


@responses.activate
def test_get_operation():
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json={"operation_id": "op1", "done": True},
    )
    op = MarbleClient(api_key="k").get_operation("op1")
    assert op["done"] is True


@responses.activate
def test_get_world():
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/worlds/world1",
        json={"world_id": "world1"},
    )
    assert MarbleClient(api_key="k").get_world("world1")["world_id"] == "world1"


@responses.activate
def test_delete_world_returns_empty_dict_for_no_content():
    responses.delete(f"{MARBLE_BASE_URL}/marble/v1/worlds/w", body="", status=204)
    assert MarbleClient(api_key="k").delete_world("w") == {}


@responses.activate
def test_list_worlds_minimal():
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:list",
        json={"worlds": [], "next_page_token": None},
    )
    MarbleClient(api_key="k").list_worlds()
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"page_size": 20, "sort_by": "created_at"}


@responses.activate
def test_list_worlds_passes_filters():
    responses.post(f"{MARBLE_BASE_URL}/marble/v1/worlds:list", json={"worlds": []})
    MarbleClient(api_key="k").list_worlds(
        page_size=50,
        page_token="next",
        status="SUCCEEDED",
        model="marble-1.1",
        tags=["a"],
        is_public=True,
        created_after="2026-01-01",
        created_before="2026-02-01",
        sort_by="updated_at",
    )
    sent = json.loads(responses.calls[0].request.body)
    assert sent["page_size"] == 50
    assert sent["page_token"] == "next"
    assert sent["status"] == "SUCCEEDED"
    assert sent["model"] == "marble-1.1"
    assert sent["tags"] == ["a"]
    assert sent["is_public"] is True
    assert sent["created_after"] == "2026-01-01"
    assert sent["created_before"] == "2026-02-01"
    assert sent["sort_by"] == "updated_at"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@responses.activate
def test_request_raises_on_4xx_with_json_detail():
    responses.post(
        f"{MARBLE_BASE_URL}/marble/v1/worlds:generate",
        json={"detail": "bad"},
        status=422,
    )
    c = MarbleClient(api_key="k")
    with pytest.raises(MarbleAPIError) as exc_info:
        c.generate_world(world_prompt={"type": "text", "text_prompt": "x"})
    err = exc_info.value
    assert err.status_code == 422
    assert err.body == {"detail": "bad"}


@responses.activate
def test_request_raises_on_5xx_with_text_body():
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/credits",
        body="server fell over",
        status=500,
    )
    with pytest.raises(MarbleAPIError) as exc_info:
        MarbleClient(api_key="k").get_credits()
    assert exc_info.value.status_code == 500
    assert exc_info.value.body == "server fell over"


# ---------------------------------------------------------------------------
# wait_for_operation
# ---------------------------------------------------------------------------


@responses.activate
def test_wait_for_operation_returns_when_done_immediately():
    responses.get(
        f"{MARBLE_BASE_URL}/marble/v1/operations/op1",
        json={"done": True, "operation_id": "op1"},
    )
    c = MarbleClient(api_key="k")
    op = c.wait_for_operation("op1", timeout=10, poll_interval=0)
    assert op["done"] is True
    assert len(responses.calls) == 1  # initial poll only


@responses.activate
def test_wait_for_operation_polls_until_done(monkeypatch):
    # First two responses say not done, third says done
    op_url = f"{MARBLE_BASE_URL}/marble/v1/operations/op1"
    responses.get(op_url, json={"done": False, "metadata": {"progress": 10}})
    responses.get(op_url, json={"done": False, "metadata": {"progress": 50}})
    responses.get(op_url, json={"done": True, "metadata": {"progress": 100}, "response": {"x": 1}})

    progress_events: list = []
    monkeypatch.setattr("time.sleep", lambda _s: None)  # don't actually sleep
    c = MarbleClient(api_key="k")
    op = c.wait_for_operation(
        "op1",
        timeout=10,
        poll_interval=0,
        on_progress=progress_events.append,
    )
    assert op["done"] is True
    assert progress_events == [10, 50, 100]


@responses.activate
def test_wait_for_operation_raises_on_timeout(monkeypatch):
    op_url = f"{MARBLE_BASE_URL}/marble/v1/operations/op1"
    responses.get(op_url, json={"done": False}, status=200)
    responses.get(op_url, json={"done": False}, status=200)

    # Fake time progression so deadline hits on second iteration
    monkeypatch.setattr("time.sleep", lambda _s: None)
    times = iter([0.0, 100.0, 200.0, 300.0])
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    c = MarbleClient(api_key="k")
    with pytest.raises(TimeoutError):
        c.wait_for_operation("op1", timeout=1, poll_interval=0)


@responses.activate
def test_wait_for_operation_honors_check_interrupt(monkeypatch):
    op_url = f"{MARBLE_BASE_URL}/marble/v1/operations/op1"
    responses.get(op_url, json={"done": False})

    monkeypatch.setattr("time.sleep", lambda _s: None)

    class Cancelled(Exception):
        pass

    calls = {"n": 0}

    def check_interrupt() -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise Cancelled("user cancelled")

    c = MarbleClient(api_key="k")
    with pytest.raises(Cancelled):
        c.wait_for_operation(
            "op1",
            timeout=600,
            poll_interval=5,
            check_interrupt=check_interrupt,
        )
    # Should have cancelled before exhausting the timeout — only one poll.
    assert len(responses.calls) == 1


@responses.activate
def test_wait_for_operation_check_interrupt_after_sleep(monkeypatch):
    """The time.sleep() branch inside interruptible_sleep must be reachable.

    check_interrupt is allowed to pass on the first inner call (letting
    time.sleep execute), then raises on the second inner call.
    """
    op_url = f"{MARBLE_BASE_URL}/marble/v1/operations/op1"
    responses.get(op_url, json={"done": False})

    monkeypatch.setattr("time.sleep", lambda _s: None)

    class Cancelled(Exception):
        pass

    # Call sequence:
    #   1 – initial check_interrupt() before first poll  → pass
    #   2 – first call inside interruptible_sleep loop   → pass (hits time.sleep)
    #   3 – second call inside interruptible_sleep loop  → raise
    calls = {"n": 0}

    def check_interrupt() -> None:
        calls["n"] += 1
        if calls["n"] >= 3:
            raise Cancelled("user cancelled")

    c = MarbleClient(api_key="k")
    with pytest.raises(Cancelled):
        c.wait_for_operation(
            "op1",
            timeout=600,
            poll_interval=5,
            check_interrupt=check_interrupt,
        )
