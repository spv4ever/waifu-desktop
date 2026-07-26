from __future__ import annotations

from app.services.comfy_client import ComfyClient


class _DummyResponse:
    def __init__(self, payload: dict, *, ok: bool = True):
        self._payload = payload
        self.ok = ok
        self.status_code = 200
        self.text = str(payload)

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


def test_upload_image_sends_file_to_selected_comfyui_instance(tmp_path, monkeypatch):
    client = ComfyClient(base_url="http://comfy-video:8188")
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"png data")

    def _fake_post(url, *, files, data, timeout):
        assert url == "http://comfy-video:8188/upload/image"
        assert files["image"][0] == "reference.png"
        assert files["image"][1].read() == b"png data"
        assert data == {"type": "input", "overwrite": "true"}
        assert timeout == client.timeout
        return _DummyResponse({"name": "reference.png", "subfolder": "image2vid"})

    monkeypatch.setattr("app.services.comfy_client.requests.post", _fake_post)

    assert client.upload_image(image_path) == "image2vid/reference.png"
