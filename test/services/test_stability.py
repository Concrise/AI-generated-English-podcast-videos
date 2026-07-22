import sys
import shutil
import threading
import time
import wave

import pytest
from PIL import Image
from pydantic import ValidationError

from app.controllers.manager.memory_manager import InMemoryTaskManager
from app.models import const
from app.models.schema import VideoAspect, VideoParams
from app.services.concurrency import (
    GenerationTask,
    GenerationTaskError,
    run_generation_tasks,
)
from app.services.media_utils import (
    MediaProcessingError,
    run_media_command,
    validate_image_file,
)
from app.services.state import MemoryState
from app.services.video import combine_videos


def test_video_params_use_consistent_safe_defaults():
    parameters = VideoParams()

    assert parameters.video_aspect is VideoAspect.portrait
    assert parameters.video_aspect.to_resolution() == (1080, 1920)
    assert parameters.speaker_1_voice == "gemini:Kore"
    assert parameters.speaker_2_voice == "gemini:Puck"
    assert parameters.subtitle_enabled is False


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("video_count", 0),
        ("video_count", 11),
        ("n_threads", 0),
        ("bgm_volume", 1.1),
        ("voice_rate", 0.1),
        ("font_size", 500),
    ],
)
def test_video_params_reject_expensive_or_invalid_values(field_name, field_value):
    with pytest.raises(ValidationError):
        VideoParams(**{field_name: field_value})


def test_memory_state_preserves_fields_and_clamps_progress():
    state = MemoryState()
    state.update_task(
        "task-1",
        state=const.TASK_STATE_PROCESSING,
        progress=-10,
        stage="audio",
    )
    state.update_task(
        "task-1",
        state=const.TASK_STATE_COMPLETE,
        progress=150,
        videos=["final.mp4"],
    )

    task = state.get_task("task-1")
    assert task["progress"] == 100
    assert task["stage"] == "audio"
    assert task["videos"] == ["final.mp4"]
    assert task["created_at"] <= task["updated_at"]


def test_memory_state_returns_defensive_copies():
    state = MemoryState()
    state.update_task("task-1", progress=10, payload="original")

    returned_task = state.get_task("task-1")
    returned_task["payload"] = "changed"

    assert state.get_task("task-1")["payload"] == "original"


def test_task_manager_never_exceeds_configured_concurrency():
    manager = InMemoryTaskManager(max_concurrent_tasks=2)
    release_tasks = threading.Event()
    all_tasks_completed = threading.Event()
    active_lock = threading.Lock()
    active_tasks = 0
    peak_active_tasks = 0
    completed_tasks = 0
    task_count = 8

    def blocking_task():
        nonlocal active_tasks, peak_active_tasks, completed_tasks
        with active_lock:
            active_tasks += 1
            peak_active_tasks = max(peak_active_tasks, active_tasks)
        release_tasks.wait(timeout=5)
        with active_lock:
            active_tasks -= 1
            completed_tasks += 1
            if completed_tasks == task_count:
                all_tasks_completed.set()

    for _ in range(task_count):
        manager.add_task(blocking_task)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with active_lock:
            if active_tasks == 2:
                break
        time.sleep(0.01)

    with active_lock:
        assert active_tasks == 2
        assert peak_active_tasks == 2

    release_tasks.set()
    assert all_tasks_completed.wait(timeout=5)
    assert peak_active_tasks == 2


def test_task_manager_rejects_non_positive_concurrency():
    with pytest.raises(ValueError):
        InMemoryTaskManager(max_concurrent_tasks=0)


def test_generation_tasks_use_serial_execution_when_concurrency_is_disabled():
    execution_order = []

    def create_task(task_index):
        def execute_task():
            execution_order.append(task_index)
            return task_index

        return GenerationTask(name=f"task-{task_index}", execute=execute_task)

    results = run_generation_tasks(
        [create_task(task_index) for task_index in range(4)],
        concurrent=False,
        max_workers=4,
    )

    assert results == [0, 1, 2, 3]
    assert execution_order == [0, 1, 2, 3]


def test_generation_tasks_preserve_input_order_when_completion_order_differs():
    second_task_completed = threading.Event()

    def execute_first_task():
        assert second_task_completed.wait(timeout=2)
        return "first"

    def execute_second_task():
        second_task_completed.set()
        return "second"

    results = run_generation_tasks(
        [
            GenerationTask(name="first", execute=execute_first_task),
            GenerationTask(name="second", execute=execute_second_task),
        ],
        concurrent=True,
        max_workers=2,
    )

    assert results == ["first", "second"]


def test_generation_tasks_respect_maximum_worker_count():
    active_lock = threading.Lock()
    active_tasks = 0
    peak_active_tasks = 0

    def execute_task():
        nonlocal active_tasks, peak_active_tasks
        with active_lock:
            active_tasks += 1
            peak_active_tasks = max(peak_active_tasks, active_tasks)
        time.sleep(0.05)
        with active_lock:
            active_tasks -= 1
        return True

    tasks = [
        GenerationTask(name=f"task-{task_index}", execute=execute_task)
        for task_index in range(9)
    ]
    results = run_generation_tasks(tasks, concurrent=True, max_workers=3)

    assert results == [True] * 9
    assert peak_active_tasks == 3


def test_generation_tasks_allow_none_as_a_valid_ordered_result():
    results = run_generation_tasks(
        [
            GenerationTask(name="none-result", execute=lambda: None),
            GenerationTask(name="value-result", execute=lambda: "value"),
        ],
        concurrent=True,
        max_workers=2,
    )

    assert results == [None, "value"]


def test_generation_tasks_report_the_failed_task_name():
    def raise_provider_error():
        raise RuntimeError("provider rejected concurrent request")

    with pytest.raises(GenerationTaskError, match="image-request-2"):
        run_generation_tasks(
            [
                GenerationTask(name="image-request-1", execute=lambda: "ok"),
                GenerationTask(name="image-request-2", execute=raise_provider_error),
            ],
            concurrent=True,
            max_workers=2,
        )


def test_generation_tasks_reject_non_positive_worker_count():
    with pytest.raises(ValueError, match="positive integer"):
        run_generation_tasks([], concurrent=True, max_workers=0)


def test_image_validation_rejects_non_image_content(tmp_path):
    invalid_image = tmp_path / "provider-error.png"
    invalid_image.write_text("<html>gateway error</html>", encoding="utf-8")

    with pytest.raises(MediaProcessingError):
        validate_image_file(str(invalid_image))


def test_image_validation_accepts_decodable_image(tmp_path):
    image_path = tmp_path / "valid.png"
    Image.new("RGB", (128, 128), "white").save(image_path)

    assert validate_image_file(str(image_path)) == str(image_path)


def test_media_command_reports_failed_stage():
    with pytest.raises(MediaProcessingError, match="offline command test"):
        run_media_command(
            [sys.executable, "-c", "raise SystemExit(7)"],
            stage="offline command test",
            timeout_seconds=10,
        )


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="local FFmpeg tools are not installed",
)
def test_image_and_audio_can_be_composed_into_valid_video(tmp_path):
    image_path = tmp_path / "frame.png"
    audio_path = tmp_path / "narration.wav"
    video_path = tmp_path / "result.mp4"

    Image.new("RGB", (360, 640), "navy").save(image_path)
    sample_rate = 16_000
    with wave.open(str(audio_path), "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(b"\x00\x00" * sample_rate)

    output_path = combine_videos(
        combined_video_path=str(video_path),
        video_paths=[str(image_path)],
        audio_file=str(audio_path),
        threads=1,
    )

    assert output_path == str(video_path)
    assert video_path.is_file()
