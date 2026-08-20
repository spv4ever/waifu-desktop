from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from app.data.storage import SQLiteStore
from app.services.queue_worker import QueueWorker


def test_prompt_media_query_includes_status(monkeypatch) -> None:
    executed_query = ""

    class _Connection:
        def execute(self, query, _params):
            nonlocal executed_query
            executed_query = query
            return self

        def fetchone(self):
            return None

    class _Context:
        def __enter__(self):
            return _Connection()

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr("app.data.storage.get_connection", lambda: _Context())

    SQLiteStore().get_prompt_item_media(42)

    assert "p.status" in executed_query


def test_long_reference_extracts_actual_last_frame_as_png(tmp_path, monkeypatch) -> None:
    video = tmp_path / "segment.mp4"
    video.write_bytes(b"video")
    input_dir = tmp_path / "input"
    messages: list[str] = []

    class _Store:
        def get_prompt_item_media(self, _prompt_id):
            return {
                "status": "DONE",
                "base_image_json": '{"filename":"segment.mp4","subfolder":""}',
            }

    worker = QueueWorker.__new__(QueueWorker)
    worker.store = _Store()
    worker._log_callback = messages.append
    monkeypatch.setattr(
        "app.services.queue_worker.settings",
        SimpleNamespace(comfyui_input_dir=str(input_dir)),
    )
    monkeypatch.setattr("app.services.queue_worker.shutil.which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("app.services.queue_worker.build_output_path", lambda *_args, **_kwargs: video)

    command: list[str] = []

    def _run(cmd, **_kwargs):
        command.extend(cmd)
        Image.new("RGB", (2, 2), "red").save(Path(cmd[-1]), format="PNG")

    monkeypatch.setattr("app.services.queue_worker.subprocess.run", _run)

    result = worker._image2vid_long_reference(
        meta={
            "image2vid_long_previous_prompt_id": 41,
            "image2vid_long_project_id": 7,
            "image2vid_long_index": 1,
        }
    )

    assert result == "image2vid_long_7_1_last.png"
    assert command[command.index("-sseof") + 1] == "-1"
    assert command[command.index("-update") + 1] == "1"
    assert "-frames:v" not in command
    assert (input_dir / result).read_bytes().startswith(b"\x89PNG")
    assert any("Último frame PNG preparado" in message for message in messages)


def test_long_project_keeps_all_images_used_between_prompts(tmp_path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    project_dir = tmp_path / "output" / "project_7"
    input_dir.mkdir()
    (input_dir / "source.jpg").write_bytes(b"initial")
    (input_dir / "image2vid_long_7_1_last.png").write_bytes(b"frame-one")
    (input_dir / "image2vid_long_7_2_last.png").write_bytes(b"frame-two")
    messages: list[str] = []

    worker = QueueWorker.__new__(QueueWorker)
    worker._log_callback = messages.append
    monkeypatch.setattr(
        "app.services.queue_worker.settings",
        SimpleNamespace(comfyui_input_dir=str(input_dir)),
    )

    worker._copy_image2vid_long_references(
        meta={
            "image2vid_long_project_id": 7,
            "image2vid_long_initial_source_image": "source.jpg",
            "image2vid_source_image": "image2vid_long_7_2_last.png",
        },
        project_folder=project_dir,
        segment_count=3,
    )

    references = project_dir / "references"
    assert (references / "000_initial.jpg").read_bytes() == b"initial"
    assert (references / "001_between_prompts.png").read_bytes() == b"frame-one"
    assert (references / "002_between_prompts.png").read_bytes() == b"frame-two"
    assert any("3 imágenes de referencia" in message for message in messages)


def test_long_project_fails_if_a_used_reference_is_missing(tmp_path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "source.png").write_bytes(b"initial")
    worker = QueueWorker.__new__(QueueWorker)
    monkeypatch.setattr(
        "app.services.queue_worker.settings",
        SimpleNamespace(comfyui_input_dir=str(input_dir)),
    )

    with pytest.raises(RuntimeError, match="Faltan imágenes de referencia"):
        worker._copy_image2vid_long_references(
            meta={
                "image2vid_long_project_id": 8,
                "image2vid_source_image": "source.png",
            },
            project_folder=tmp_path / "project_8",
            segment_count=2,
        )
