import json

from app.services.comfy_history_parser import extract_saved_video_output


def test_extract_saved_video_output_prefers_persisted_video():
    video = {"filename": "result.mp4", "subfolder": "image2vid/waifu", "type": "output"}

    assert extract_saved_video_output(
        base_media_json=json.dumps(video),
        history_json=None,
    ) == video


def test_extract_saved_video_output_recovers_legacy_video_from_queue_history():
    video = {"filename": "legacy.mp4", "subfolder": "image2vid/waifu", "type": "output"}
    history = {"outputs": {"99": {"videos": [video]}}}

    assert extract_saved_video_output(
        base_media_json=None,
        history_json=json.dumps(history),
    ) == video
