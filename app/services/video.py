import glob
import itertools
import os
import random
import gc
import shutil
import subprocess
import json
import tempfile
from typing import List
from loguru import logger
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont

from app.models import const
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services.utils import video_effects
from app.services.media_utils import (
    MediaProcessingError,
    create_temporary_output_path,
    probe_duration,
    publish_output,
    remove_file_safely,
    run_media_command,
    validate_audio_file,
    validate_image_file,
    validate_video_file,
)
from app.utils import utils

class SubClippedVideoClip:
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        if duration is None:
            self.duration = end_time - start_time
        else:
            self.duration = duration

    def __str__(self):
        return f"SubClippedVideoClip(file_path={self.file_path}, start_time={self.start_time}, end_time={self.end_time}, duration={self.duration}, width={self.width}, height={self.height})"


def is_image_file(file_path: str) -> bool:
    """检查文件是否是图片文件"""
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
    _, ext = os.path.splitext(file_path.lower())
    return ext in image_extensions


def get_image_size(file_path: str) -> tuple:
    """获取图片尺寸"""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size
    except Exception as e:
        logger.error(f"Failed to get image size: {str(e)}")
        return (512, 768)


audio_codec = "aac"
video_codec = "libx264"
fps = 30

def close_clip(clip):
    if clip is None:
        return
        
    try:
        # close main resources
        if hasattr(clip, 'reader') and clip.reader is not None:
            clip.reader.close()
            
        # close audio resources
        if hasattr(clip, 'audio') and clip.audio is not None:
            if hasattr(clip.audio, 'reader') and clip.audio.reader is not None:
                clip.audio.reader.close()
            del clip.audio
            
        # close mask resources
        if hasattr(clip, 'mask') and clip.mask is not None:
            if hasattr(clip.mask, 'reader') and clip.mask.reader is not None:
                clip.mask.reader.close()
            del clip.mask
            
        # handle child clips in composite clips
        if hasattr(clip, 'clips') and clip.clips:
            for child_clip in clip.clips:
                if child_clip is not clip:  # avoid possible circular references
                    close_clip(child_clip)
            
        # clear clip list
        if hasattr(clip, 'clips'):
            clip.clips = []
            
    except Exception as e:
        logger.error(f"failed to close clip: {str(e)}")
    
    del clip
    gc.collect()

def delete_files(files: List[str] | str):
    if isinstance(files, str):
        files = [files]
        
    for file in files:
        try:
            os.remove(file)
        except:
            pass

def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        if not files:
            logger.warning(f"no bgm files found in {song_dir}")
            return ""
        return random.choice(files)

    return ""


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    video_transition_mode: VideoTransitionMode = VideoTransitionMode.none,
    max_clip_duration: int = 5,
    threads: int = 2,
) -> str:
    """Combine homogeneous local materials with narration using strict checks.

    The previous implementation returned the requested path even after ffmpeg
    failed and silently ignored video inputs whenever one image was present.
    This implementation either publishes a validated result or raises an error.
    """
    del video_concat_mode, video_transition_mode

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()
    thread_count = max(1, int(threads))
    audio_duration = validate_audio_file(audio_file)

    valid_paths = [path for path in video_paths if path and os.path.isfile(path)]
    if not valid_paths:
        raise MediaProcessingError("no valid image or video materials were supplied")

    image_paths = [path for path in valid_paths if is_image_file(path)]
    video_only_paths = [path for path in valid_paths if not is_image_file(path)]
    if image_paths and video_only_paths:
        raise MediaProcessingError(
            "mixed image and video materials are not supported in one render"
        )

    output_dir = os.path.dirname(combined_video_path) or "."
    os.makedirs(output_dir, exist_ok=True)
    temporary_output = create_temporary_output_path(combined_video_path)

    scale_filter = (
        f"scale={video_width}:{video_height}:force_original_aspect_ratio=increase,"
        f"crop={video_width}:{video_height},setsar=1"
    )

    try:
        with tempfile.TemporaryDirectory(prefix="render-", dir=output_dir) as work_dir:
            normalized_segments = []
            if image_paths:
                image_duration = audio_duration / len(image_paths)
                for index, image_path in enumerate(image_paths):
                    validate_image_file(image_path)
                    segment_path = os.path.join(work_dir, f"image-{index:04d}.mp4")
                    run_media_command(
                        [
                            "ffmpeg",
                            "-y",
                            "-loop",
                            "1",
                            "-i",
                            image_path,
                            "-an",
                            "-vf",
                            scale_filter,
                            "-t",
                            f"{image_duration:.6f}",
                            "-r",
                            str(fps),
                            "-c:v",
                            video_codec,
                            "-pix_fmt",
                            "yuv420p",
                            "-threads",
                            str(thread_count),
                            segment_path,
                        ],
                        stage=f"render image segment {index + 1}",
                    )
                    validate_video_file(segment_path, require_audio=False)
                    normalized_segments.append(segment_path)
            else:
                if max_clip_duration <= 0:
                    raise MediaProcessingError("max_clip_duration must be positive")
                for index, video_path in enumerate(video_only_paths):
                    segment_path = os.path.join(work_dir, f"video-{index:04d}.mp4")
                    run_media_command(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            video_path,
                            "-an",
                            "-vf",
                            scale_filter,
                            "-t",
                            str(max_clip_duration),
                            "-r",
                            str(fps),
                            "-c:v",
                            video_codec,
                            "-pix_fmt",
                            "yuv420p",
                            "-threads",
                            str(thread_count),
                            segment_path,
                        ],
                        stage=f"normalize video segment {index + 1}",
                    )
                    validate_video_file(segment_path, require_audio=False)
                    normalized_segments.append(segment_path)

            if not normalized_segments:
                raise MediaProcessingError("material normalization produced no segments")

            concat_list_path = os.path.join(work_dir, "segments.txt")
            with open(concat_list_path, "w", encoding="utf-8") as concat_file:
                for segment_path in normalized_segments:
                    concat_file.write(f"file '{segment_path}'\n")

            silent_video_path = os.path.join(work_dir, "silent-video.mp4")
            run_media_command(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_list_path,
                    "-c",
                    "copy",
                    silent_video_path,
                ],
                stage="concatenate normalized video segments",
            )
            validate_video_file(silent_video_path, require_audio=False)

            run_media_command(
                [
                    "ffmpeg",
                    "-y",
                    "-stream_loop",
                    "-1",
                    "-i",
                    silent_video_path,
                    "-i",
                    audio_file,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    audio_codec,
                    "-t",
                    f"{audio_duration:.6f}",
                    "-shortest",
                    temporary_output,
                ],
                stage="attach narration audio",
            )
            validate_video_file(
                temporary_output,
                expected_duration=audio_duration,
                require_audio=True,
            )
            publish_output(temporary_output, combined_video_path)
    finally:
        remove_file_safely(temporary_output)

    logger.info(f"video composition completed: {combined_video_path}")
    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    # Create ImageFont
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    return result, height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"generating video: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    # https://github.com/harry0703/MoneyPrinterTurbo/issues/217
    # PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'final-1.mp4.tempTEMP_MPY_wvf_snd.mp3'
    # write into the same directory as the output file
    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")

        logger.info(f"  ⑤ font: {font_path}")

    def create_text_clip(subtitle_item):
        params.font_size = int(params.font_size)
        params.stroke_width = int(params.stroke_width)
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        interline = int(params.font_size * 0.25)
        size=(int(max_width), int(txt_height + params.font_size * 0.25 + (interline * (wrapped_txt.count("\n") + 1))))

        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            # interline=interline,
            # size=size,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            # Ensure the subtitle is fully within the screen bounds
            margin = 10  # Additional margin, in pixels
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(
                min_y, min(custom_y, max_y)
            )  # Constrain the y value within the valid range
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
        return _clip

    video_clip = VideoFileClip(video_path).without_audio()
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=params.font_size,
        )

    if params.subtitle_enabled and subtitle_path and os.path.exists(subtitle_path):
        sub = SubtitlesClip(
            subtitles=subtitle_path, encoding="utf-8", make_textclip=make_textclip
        )
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [
                    afx.MultiplyVolume(params.bgm_volume),
                    afx.AudioFadeOut(3),
                    afx.AudioLoop(duration=video_clip.duration),
                ]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    expected_duration = validate_audio_file(audio_path)
    temporary_output = create_temporary_output_path(output_file)
    try:
        video_clip = video_clip.with_audio(audio_clip)
        video_clip.write_videofile(
            temporary_output,
            audio_codec=audio_codec,
            temp_audiofile_path=output_dir,
            threads=params.n_threads or 2,
            logger=None,
            fps=fps,
        )
        validate_video_file(
            temporary_output,
            expected_duration=expected_duration,
            require_audio=True,
        )
        publish_output(temporary_output, output_file)
    finally:
        remove_file_safely(temporary_output)
        close_clip(video_clip)
        close_clip(audio_clip)


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        try:
            clip = VideoFileClip(material.url)
        except Exception:
            clip = ImageClip(material.url)

        width = clip.size[0]
        height = clip.size[1]
        if width < 480 or height < 480:
            logger.warning(f"low resolution material: {width}x{height}, minimum 480x480 required")
            continue

        if ext in const.FILE_TYPE_IMAGES:
            logger.info(f"processing image: {material.url}")
            # Create an image clip and set its duration to 3 seconds
            clip = (
                ImageClip(material.url)
                .with_duration(clip_duration)
                .with_position("center")
            )
            # Apply a zoom effect using the resize method.
            # A lambda function is used to make the zoom effect dynamic over time.
            # The zoom effect starts from the original size and gradually scales up to 120%.
            # t represents the current time, and clip.duration is the total duration of the clip (3 seconds).
            # Note: 1 represents 100% size, so 1.2 represents 120% size.
            zoom_clip = clip.resized(
                lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
            )

            # Optionally, create a composite video clip containing the zoomed clip.
            # This is useful when you want to add other elements to the video.
            final_clip = CompositeVideoClip([zoom_clip])

            # Output the video to a file.
            video_file = f"{material.url}.mp4"
            final_clip.write_videofile(video_file, fps=30, logger=None)
            close_clip(clip)
            material.url = video_file
            logger.success(f"image processed: {video_file}")
    return materials
