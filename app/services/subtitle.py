import json
import os.path
import re

from loguru import logger

from app.config import config
from app.utils import utils


def create(audio_file, subtitle_file: str = ""):
    """
    创建字幕文件（基于 Whisper 模型）
    注意：此功能需要安装 faster-whisper 包
    """
    logger.warning("Whisper subtitle generation is not available (faster-whisper not installed)")
    logger.warning("Using script-based subtitle generation instead")
    return None


def file_to_subtitles(filename):
    """
    从字幕文件中读取字幕内容
    """
    if not filename or not os.path.isfile(filename):
        return []

    times_texts = []
    current_times = None
    current_text = ""
    index = 0
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            times = re.findall("([0-9]*:[0-9]*:[0-9]*,[0-9]*)", line)
            if times:
                current_times = times
            elif line.strip().isdigit():
                index = int(line.strip())
            elif line.strip() == "" and current_times is not None:
                if current_text.strip():
                    times_texts.append((index, current_times[0], current_times[1], current_text.strip()))
                current_text = ""
                current_times = None
            elif current_times is not None:
                current_text += line

    if current_times is not None and current_text.strip():
        times_texts.append((index, current_times[0], current_times[1], current_text.strip()))

    return times_texts


def correct(subtitle_file, video_script):
    """
    校正字幕内容
    """
    logger.info("subtitle correction is not implemented without Whisper")
    return subtitle_file


def generate_subtitle_text(text, language=""):
    """
    生成字幕文本（简化版本）
    """
    if not text:
        return ""
    
    lines = text.split('\n')
    result = []
    idx = 1
    current_time = 0.0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        duration = max(len(line) * 0.07, 2.0)
        start_time = current_time
        end_time = current_time + duration
        
        start_str = utils.time_convert_seconds_to_hmsm(start_time).replace(".", ",")
        end_str = utils.time_convert_seconds_to_hmsm(end_time).replace(".", ",")
        
        result.append(f"{idx}")
        result.append(f"{start_str} --> {end_str}")
        result.append(line)
        result.append("")
        
        idx += 1
        current_time = end_time + 0.5
    
    return "\n".join(result)
