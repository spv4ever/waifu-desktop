from __future__ import annotations

from app.services.comfy_client import ComfyClient


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_is_prompt_in_queue_detects_running_and_pending(monkeypatch):
    client = ComfyClient(base_url="http://example")

    payload = {
        "queue_running": [[1, "abc-123", {}]],
        "queue_pending": [[2, "zzz-999", {}]],
    }

    def _fake_get(url, timeout):
        assert url.endswith("/queue")
        return _DummyResponse(payload)

    monkeypatch.setattr("app.services.comfy_client.requests.get", _fake_get)

    assert client.is_prompt_in_queue("abc-123") is True
    assert client.is_prompt_in_queue("zzz-999") is True
    assert client.is_prompt_in_queue("missing") is False


def test_is_prompt_in_queue_handles_nested_shapes(monkeypatch):
    client = ComfyClient(base_url="http://example")

    payload = {
        "queue_running": [{"prompt": {"id": "id-1"}}],
        "queue_pending": [],
    }

    def _fake_get(url, timeout):
        return _DummyResponse(payload)

    monkeypatch.setattr("app.services.comfy_client.requests.get", _fake_get)

    assert client.is_prompt_in_queue("id-1") is True
