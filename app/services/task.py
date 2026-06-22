import asyncio
import os
import os.path
from os import path

from loguru import logger

from app.config import config
from app.models import const
from app.models.schema import VideoConcatMode, VideoParams
from app.services import llm, material, podcast_audio, subtitle, video
from app.services import state as sm
from app.utils import utils


def apply_speaker_voices(podcast_script, params):
    """将当前选择的主播音色写入每轮播客对话。"""
    speaker_1_voice = getattr(params, "speaker_1_voice", "")
    speaker_2_voice = getattr(params, "speaker_2_voice", "")

    for item in podcast_script or []:
        if speaker_1_voice:
            item.speaker_1_voice = speaker_1_voice
        if speaker_2_voice:
            item.speaker_2_voice = speaker_2_voice

    return podcast_script


def generate_script(task_id, params):
    logger.info("\n\n## generating podcast script")

    if params.podcast_script:
        logger.debug(f"using existing podcast script: {len(params.podcast_script)} turns")
        return apply_speaker_voices(params.podcast_script, params)

    if not params.article_text:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("no article text provided for podcast script generation.")
        return None

    podcast_script = llm.generate_podcast_script(
        article_text=params.article_text,
        language=params.video_language,
    )
    if not podcast_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate podcast script.")
        return None

    logger.debug(f"generated podcast script: {len(podcast_script)} turns")
    return apply_speaker_voices(podcast_script, params)


def generate_terms(task_id, params, podcast_script):
    logger.info("\n\n## generating podcast search terms")

    video_terms = params.video_terms
    if video_terms:
        if isinstance(video_terms, str):
            video_terms = [term.strip() for term in video_terms.replace("，", ",").split(",")]
            video_terms = [term for term in video_terms if term]
        elif isinstance(video_terms, list):
            video_terms = [str(term).strip() for term in video_terms if str(term).strip()]
        else:
            raise ValueError("video_terms must be a string or a list of strings.")
    else:
        video_terms = llm.generate_terms_from_podcast(
            podcast_script=podcast_script,
            amount=5,
        )

    if not video_terms:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error("failed to generate podcast search terms.")
        return None

    logger.debug(f"podcast search terms: {utils.to_json(video_terms)}")
    return video_terms


def save_script_data(task_id, podcast_script, video_terms, params):
    script_file = path.join(utils.task_dir(task_id), "script.json")
    script_data = {
        "podcast_script": podcast_script,
        "search_terms": video_terms,
        "params": params,
        "mode": "podcast",
    }

    with open(script_file, "w", encoding="utf-8") as f:
        f.write(utils.to_json(script_data))


def generate_audio(task_id, params, podcast_script):
    logger.info("\n\n## generating podcast audio")

    audio_file = path.join(utils.task_dir(task_id), "audio.mp3")

    try:
        audio_path, audio_duration = asyncio.run(
            podcast_audio.podcast_audio_generator.generate_podcast_audio(
                podcast_script=podcast_script,
                output_path=audio_file,
                voice_rate=getattr(params, "voice_rate", 1.0),
                voice_volume=getattr(params, "voice_volume", 1.0),
            )
        )

        if not audio_path or not os.path.exists(audio_path):
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("failed to generate podcast audio file.")
            return None, None

        logger.info(f"podcast audio generated: {audio_path}, duration: {audio_duration}s")
        return audio_path, audio_duration

    except Exception as e:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(f"failed to generate podcast audio: {str(e)}")
        return None, None


def generate_subtitle(task_id, params, podcast_script, audio_file):
    if not params.subtitle_enabled:
        return ""

    subtitle_path = path.join(utils.task_dir(task_id), "subtitle.srt")
    logger.info(f"\n\n## generating podcast subtitle from script")

    try:
        with open(subtitle_path, "w", encoding="utf-8") as f:
            idx = 1
            current_time = 0.0

            for i, turn in enumerate(podcast_script):
                logger.info(f"processing dialogue turn {i + 1}")

                if turn.speaker_1.strip():
                    speaker1_text = turn.speaker_1.strip()
                    duration = max(len(speaker1_text) * 0.07, 2.0)
                    start_time = current_time
                    end_time = current_time + duration
                    start_str = utils.time_convert_seconds_to_hmsm(start_time).replace(".", ",")
                    end_str = utils.time_convert_seconds_to_hmsm(end_time).replace(".", ",")

                    f.write(f"{idx}\n")
                    f.write(f"{start_str} --> {end_str}\n")
                    f.write(f"A: {speaker1_text}\n\n")

                    idx += 1
                    current_time = end_time + 0.5

                if turn.speaker_2.strip():
                    speaker2_text = turn.speaker_2.strip()
                    duration = max(len(speaker2_text) * 0.07, 2.0)
                    start_time = current_time
                    end_time = current_time + duration
                    start_str = utils.time_convert_seconds_to_hmsm(start_time).replace(".", ",")
                    end_str = utils.time_convert_seconds_to_hmsm(end_time).replace(".", ",")

                    f.write(f"{idx}\n")
                    f.write(f"{start_str} --> {end_str}\n")
                    f.write(f"B: {speaker2_text}\n\n")

                    idx += 1
                    current_time = end_time + 0.5

        if not os.path.exists(subtitle_path) or os.path.getsize(subtitle_path) == 0:
            logger.warning("subtitle file validation failed")
            return ""
        
        logger.info(f"subtitle generated successfully: {subtitle_path}")
        return subtitle_path
    except Exception as e:
        logger.error(f"failed to create podcast subtitle from script: {str(e)}")
        return ""


def enhance_podcast_subtitle(original_subtitle_path, podcast_script, task_id):
    """增强播客字幕，添加说话人标识"""
    logger.info("\n\n## enhancing podcast subtitle with speaker labels")

    try:
        subtitle_lines = subtitle.file_to_subtitles(original_subtitle_path)
        if not subtitle_lines:
            return original_subtitle_path

        enhanced_lines = []
        current_speaker = None
        script_index = 0

        for line_num, time_range, text in subtitle_lines:
            enhanced_text = text
            detected_speaker = detect_speaker_from_text(text, podcast_script, script_index)

            if detected_speaker and detected_speaker != current_speaker:
                enhanced_text = f"{detected_speaker}: {text}"
                current_speaker = detected_speaker

            enhanced_lines.append((line_num, time_range, enhanced_text))

        enhanced_subtitle_path = path.join(utils.task_dir(task_id), "subtitle_enhanced.srt")

        with open(enhanced_subtitle_path, "w", encoding="utf-8") as f:
            for line_num, time_range, text in enhanced_lines:
                f.write(f"{line_num}\n{time_range}\n{text}\n\n")

        logger.info(f"enhanced subtitle saved: {enhanced_subtitle_path}")
        return enhanced_subtitle_path

    except Exception as e:
        logger.error(f"failed to enhance podcast subtitle: {str(e)}")
        return original_subtitle_path


def detect_speaker_from_text(text, podcast_script, current_script_index):
    """基于文本内容和播客脚本推断说话人"""
    try:
        if not podcast_script or current_script_index >= len(podcast_script):
            return None

        current_turn = podcast_script[current_script_index]
        text_lower = text.lower().strip()
        speaker1_text = current_turn.speaker_1.lower()
        speaker2_text = current_turn.speaker_2.lower()

        words_text = set(text_lower.split())
        words_s1 = set(speaker1_text.split())
        words_s2 = set(speaker2_text.split())

        similarity_s1 = len(words_text.intersection(words_s1)) / max(len(words_text), 1)
        similarity_s2 = len(words_text.intersection(words_s2)) / max(len(words_text), 1)

        if similarity_s1 > similarity_s2 and similarity_s1 > 0.3:
            return "A"
        if similarity_s2 > similarity_s1 and similarity_s2 > 0.3:
            return "B"

        return None

    except Exception as e:
        logger.warning(f"failed to detect speaker: {str(e)}")
        return None


def get_video_materials(task_id, params, video_terms, audio_duration):
    if params.video_source == "local":
        logger.info("\n\n## preprocess local materials")
        materials = video.preprocess_video(
            materials=params.video_materials, clip_duration=params.video_clip_duration
        )
        if not materials:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            logger.error("no valid materials found, please check the materials and try again.")
            return None
        return [material_info.url for material_info in materials]

    logger.info(f"\n\n## downloading videos from {params.video_source}")
    downloaded_videos = material.download_videos(
        task_id=task_id,
        search_terms=video_terms,
        source=params.video_source,
        video_aspect=params.video_aspect,
        video_contact_mode=params.video_concat_mode,
        audio_duration=audio_duration * params.video_count,
        max_clip_duration=params.video_clip_duration,
    )
    if not downloaded_videos:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        logger.error(
            "failed to download videos, maybe the network is not available. if you are in China, please use a VPN."
        )
        return None
    return downloaded_videos


def generate_final_videos(task_id, params, downloaded_videos, audio_file, subtitle_path):
    final_video_paths = []
    combined_video_paths = []
    video_concat_mode = (
        params.video_concat_mode if params.video_count == 1 else VideoConcatMode.random
    )
    video_transition_mode = params.video_transition_mode

    _progress = 50
    for i in range(params.video_count):
        index = i + 1
        combined_video_path = path.join(utils.task_dir(task_id), f"combined-{index}.mp4")
        logger.info(f"\n\n## combining video: {index} => {combined_video_path}")
        video.combine_videos(
            combined_video_path=combined_video_path,
            video_paths=downloaded_videos,
            audio_file=audio_file,
            video_aspect=params.video_aspect,
            video_concat_mode=video_concat_mode,
            video_transition_mode=video_transition_mode,
            max_clip_duration=params.video_clip_duration,
            threads=params.n_threads,
        )

        _progress += 50 / params.video_count / 2
        sm.state.update_task(task_id, progress=_progress)

        final_video_path = path.join(utils.task_dir(task_id), f"final-{index}.mp4")

        logger.info(f"\n\n## generating video: {index} => {final_video_path}")
        video.generate_video(
            video_path=combined_video_path,
            audio_path=audio_file,
            subtitle_path=subtitle_path,
            output_file=final_video_path,
            params=params,
        )

        _progress += 50 / params.video_count / 2
        sm.state.update_task(task_id, progress=_progress)

        final_video_paths.append(final_video_path)
        combined_video_paths.append(combined_video_path)

    return final_video_paths, combined_video_paths


def start(task_id, params: VideoParams, stop_at: str = "video"):
    logger.info(f"start podcast task: {task_id}, stop_at: {stop_at}")
    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=5)

    if type(params.video_concat_mode) is str:
        params.video_concat_mode = VideoConcatMode(params.video_concat_mode)

    podcast_script = generate_script(task_id, params)
    if not podcast_script:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=10)

    if stop_at == "script":
        script_data = {"podcast_script": podcast_script}
        sm.state.update_task(
            task_id, state=const.TASK_STATE_COMPLETE, progress=100, **script_data
        )
        return script_data

    video_terms = ""
    if params.video_source != "local":
        video_terms = generate_terms(task_id, params, podcast_script)
        if not video_terms:
            sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
            return

    save_script_data(task_id, podcast_script, video_terms, params)

    if stop_at == "terms":
        result = {"podcast_script": podcast_script, "terms": video_terms}
        sm.state.update_task(
            task_id, state=const.TASK_STATE_COMPLETE, progress=100, **result
        )
        return result

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=20)

    audio_file, audio_duration = generate_audio(task_id, params, podcast_script)
    if not audio_file:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        return

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=30)

    if stop_at == "audio":
        result = {"audio_file": audio_file, "audio_duration": audio_duration}
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            **result,
        )
        return result

    subtitle_path = generate_subtitle(task_id, params, podcast_script, audio_file)

    if stop_at == "subtitle":
        result = {"subtitle_path": subtitle_path}
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            **result,
        )
        return result

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=40)

    downloaded_videos = get_video_materials(task_id, params, video_terms, audio_duration)
    if not downloaded_videos:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        return

    if stop_at == "materials":
        result = {"materials": downloaded_videos}
        sm.state.update_task(
            task_id,
            state=const.TASK_STATE_COMPLETE,
            progress=100,
            **result,
        )
        return result

    sm.state.update_task(task_id, state=const.TASK_STATE_PROCESSING, progress=50)

    final_video_paths, combined_video_paths = generate_final_videos(
        task_id, params, downloaded_videos, audio_file, subtitle_path
    )

    if not final_video_paths:
        sm.state.update_task(task_id, state=const.TASK_STATE_FAILED)
        return

    logger.success(f"task {task_id} finished, generated {len(final_video_paths)} videos.")

    kwargs = {
        "videos": final_video_paths,
        "combined_videos": combined_video_paths,
        "audio_file": audio_file,
        "audio_duration": audio_duration,
        "subtitle_path": subtitle_path,
        "materials": downloaded_videos,
        "podcast_script": podcast_script,
        "terms": video_terms,
    }

    sm.state.update_task(
        task_id, state=const.TASK_STATE_COMPLETE, progress=100, **kwargs
    )
    return kwargs


if __name__ == "__main__":
    task_id = "task_id"
    params = VideoParams(
        article_text="请根据这段文字生成一期双人播客。",
        voice_rate=1.0,
    )
    start(task_id, params, stop_at="script")
