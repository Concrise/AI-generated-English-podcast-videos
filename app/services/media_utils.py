"""Shared, strict helpers for local media processing.

These helpers never call external AI services. They centralize subprocess error
handling and output validation so callers cannot mistake a partially written file
for a successful media result.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from PIL import Image


DEFAULT_MEDIA_TIMEOUT_SECONDS = 300


class MediaProcessingError(RuntimeError):
    """Raised when a local media command or validation step fails."""


def run_media_command(
    command: Sequence[str],
    *,
    stage: str,
    timeout_seconds: int = DEFAULT_MEDIA_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run a local media command and raise a concise, stage-aware error."""
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        executable = command[0] if command else "media command"
        raise MediaProcessingError(
            f"{stage} failed because {executable!r} is not installed or not in PATH"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise MediaProcessingError(
            f"{stage} timed out after {timeout_seconds} seconds"
        ) from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or error.stdout or "").strip()
        if len(stderr) > 2000:
            stderr = stderr[-2000:]
        raise MediaProcessingError(
            f"{stage} failed with exit code {error.returncode}: {stderr or 'no diagnostic output'}"
        ) from error


def create_temporary_output_path(final_path: str) -> str:
    """Return a unique temporary path in the final output directory."""
    final = Path(final_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    suffix = final.suffix or ".tmp"
    return str(final.with_name(f".{final.stem}.{uuid4().hex}.part{suffix}"))


def publish_output(temporary_path: str, final_path: str) -> str:
    """Atomically publish a previously validated output file."""
    os.replace(temporary_path, final_path)
    return final_path


def remove_file_safely(file_path: str) -> None:
    """Remove a caller-owned temporary file without masking the primary error."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass


def probe_media(file_path: str) -> dict:
    """Return ffprobe metadata for a local media file."""
    if not file_path or not os.path.isfile(file_path):
        raise MediaProcessingError(f"media file does not exist: {file_path}")

    completed = run_media_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            file_path,
        ],
        stage=f"probe media {os.path.basename(file_path)}",
        timeout_seconds=30,
    )
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise MediaProcessingError(
            f"ffprobe returned invalid JSON for {file_path}"
        ) from error
    if not isinstance(metadata, dict):
        raise MediaProcessingError(f"ffprobe returned invalid metadata for {file_path}")
    return metadata


def probe_duration(file_path: str) -> float:
    """Read a finite, positive media duration from ffprobe metadata."""
    metadata = probe_media(file_path)
    format_duration = metadata.get("format", {}).get("duration")
    duration_candidates = [format_duration]
    duration_candidates.extend(
        stream.get("duration") for stream in metadata.get("streams", [])
    )
    for candidate in duration_candidates:
        try:
            duration = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(duration) and duration > 0:
            return duration
    raise MediaProcessingError(f"media duration is missing or invalid: {file_path}")


def validate_image_file(
    file_path: str,
    *,
    minimum_width: int = 64,
    minimum_height: int = 64,
) -> str:
    """Fully decode an image and reject HTML/JSON/partial image responses."""
    if not file_path or not os.path.isfile(file_path):
        raise MediaProcessingError(f"image file does not exist: {file_path}")
    if os.path.getsize(file_path) <= 0:
        raise MediaProcessingError(f"image file is empty: {file_path}")

    try:
        with Image.open(file_path) as image:
            image.verify()
        with Image.open(file_path) as image:
            image.load()
            width, height = image.size
    except Exception as error:
        raise MediaProcessingError(f"image file is invalid: {file_path}") from error

    if width < minimum_width or height < minimum_height:
        raise MediaProcessingError(
            f"image dimensions are too small ({width}x{height}): {file_path}"
        )
    return file_path


def validate_audio_file(file_path: str) -> float:
    """Validate that a file contains a decodable audio stream and return duration."""
    metadata = probe_media(file_path)
    has_audio = any(
        stream.get("codec_type") == "audio" for stream in metadata.get("streams", [])
    )
    if not has_audio:
        raise MediaProcessingError(f"audio stream is missing: {file_path}")
    return probe_duration(file_path)


def validate_video_file(
    file_path: str,
    *,
    expected_duration: float | None = None,
    duration_tolerance_seconds: float = 1.5,
    require_audio: bool = True,
) -> float:
    """Validate video/audio streams and optionally compare expected duration."""
    metadata = probe_media(file_path)
    streams = metadata.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if not has_video:
        raise MediaProcessingError(f"video stream is missing: {file_path}")
    if require_audio and not has_audio:
        raise MediaProcessingError(f"audio stream is missing from video: {file_path}")

    actual_duration = probe_duration(file_path)
    if expected_duration is not None:
        allowed_difference = max(
            duration_tolerance_seconds,
            expected_duration * 0.03,
        )
        if abs(actual_duration - expected_duration) > allowed_difference:
            raise MediaProcessingError(
                "video duration does not match narration: "
                f"expected {expected_duration:.2f}s, got {actual_duration:.2f}s"
            )
    return actual_duration
