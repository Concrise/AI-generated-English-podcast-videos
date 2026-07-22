#!/usr/bin/env python3
"""
简化版WebUI - 教育视频生成器
核心功能：输入文章 → 生成对话 → 生成视频
"""

import os
import sys
import time
import subprocess
from uuid import uuid4
import textwrap

import streamlit as st
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

# 添加项目根目录到系统路径
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from app.config import config
from app.models.schema import PodcastScript, VideoAspect
from app.services import llm
from app.services import podcast_audio
from app.services.image_generator import generate_sentence_image
from app.utils import utils
from app.services.video import get_bgm_file
from app.services.voice import get_siliconflow_voices, siliconflow_tts, MiniMax_tts, get_audio_duration
from app.services.voice import SubMaker


def _get_audio_file_duration(audio_file: str) -> float:
    """读取实际 MP3 时长，避免用字幕/文字长度估算导致画面错位。"""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_file,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return max(0.0, float(completed.stdout.strip()))
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as error:
        logger.warning(f"Unable to probe audio duration for {audio_file}: {error}")
        return 0.0


def _synthesize_speech(voice_name: str, text: str, voice_file: str) -> "SubMaker | None":
    """
    统一语音合成入口：根据音色名前缀分发到对应 TTS 引擎。
    支持：
      - gemini:Kore / gemini:gemini-3.1-flash-tts-preview:Puck
      - openai:alloy
      - MiniMax:model:voice
      - siliconflow:model:voice
    """
    from app.services.openai_compat import is_tts_configured
    from app.services.voice import openai_compatible_tts

    raw_name = (voice_name or "").strip()
    lower_name = raw_name.lower()

    # Gemini / OpenAI 兼容 TTS（可只有音色名，如 Kore）
    if (
        lower_name.startswith("gemini:")
        or lower_name.startswith("openai:")
        or lower_name in {"kore", "puck", "charon", "fenrir", "aoede", "alloy", "nova", "echo", "fable", "onyx", "shimmer"}
        or ":" not in raw_name
    ):
        if is_tts_configured():
            normalized = raw_name
            if ":" not in normalized:
                normalized = f"gemini:{normalized}"
            result = openai_compatible_tts(
                text=text,
                voice_name=normalized,
                voice_rate=1.0,
                voice_file=voice_file,
            )
            if result:
                return result
            logger.warning(f"compat TTS failed for voice={raw_name}")

    parts = raw_name.split(":")
    if len(parts) < 3:
        # 已配置 TTS 时，任意短名再试一次默认 Gemini 音色
        if is_tts_configured():
            return openai_compatible_tts(
                text=text,
                voice_name=f"gemini:{raw_name}" if raw_name else "gemini:Kore",
                voice_rate=1.0,
                voice_file=voice_file,
            )
        logger.error(f"❌ 无效的语音名称格式: {voice_name}")
        return None

    provider = parts[0].lower()
    model = parts[1]
    voice_with_gender = parts[2]
    voice = voice_with_gender.split("-")[0]

    if provider in ("gemini", "openai"):
        return openai_compatible_tts(
            text=text,
            voice_name=raw_name,
            voice_rate=1.0,
            voice_file=voice_file,
        )

    if provider == "minimax":
        return MiniMax_tts(
            text=text,
            model=model,
            voice=voice,
            voice_rate=1.0,
            voice_file=voice_file,
            voice_volume=1.0,
        )

    full_voice = f"{model}:{voice}"
    return siliconflow_tts(
        text=text,
        model=model,
        voice=full_voice,
        voice_rate=1.0,
        voice_file=voice_file,
        voice_volume=1.0,
    )

# 页面配置
st.set_page_config(
    page_title="教育视频生成器",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 隐藏Streamlit默认样式（保留侧边栏）
st.markdown("""
<style>
    /* 隐藏顶部 header */
    .stApp > header {
        display: none !important;
    }
    /* 隐藏底部 footer */
    .stApp > footer {
        display: none !important;
    }
    /* 调整主内容区域 padding */
    .stApp {
        padding-top: 0 !important;
    }
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
    }
    /* 侧边栏样式 */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa;
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 2rem !important;
    }
    /* 确保标题不被遮挡 */
    .stTitle {
        margin-top: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# 初始化日志 - 显示详细信息
logger.remove()
logger.add(sys.stdout, level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# ============ 会话状态初始化 ============
if "podcast_script" not in st.session_state:
    st.session_state["podcast_script"] = None
if "video_terms" not in st.session_state:
    st.session_state["video_terms"] = []
if "task_output_dir" not in st.session_state:
    st.session_state["task_output_dir"] = None
if "generation_complete" not in st.session_state:
    st.session_state["generation_complete"] = False
if "error_message" not in st.session_state:
    st.session_state["error_message"] = None

# ============ 核心功能函数 ============

def generate_fallback_image(sentence: str, keywords: list, output_path: str, speaker: str = "Speaker") -> str:
    """
    使用 PIL 生成备选图片（当 AI 图片生成失败时）
    创建一个带文案和关键词的教育风格图片
    """
    try:
        # 9:16 竖版尺寸 (1080x1920)
        width, height = 1080, 1920
        
        # 创建图片
        img = Image.new('RGB', (width, height), color='#F5F5DC')  # 米黄色背景
        draw = ImageDraw.Draw(img)
        
        # 尝试加载字体
        try:
            # Windows 系统字体
            title_font = ImageFont.truetype("arial.ttf", 48)
            sentence_font = ImageFont.truetype("arial.ttf", 36)
            keyword_font = ImageFont.truetype("arial.ttf", 28)
        except:
            # 使用默认字体
            title_font = ImageFont.load_default()
            sentence_font = ImageFont.load_default()
            keyword_font = ImageFont.load_default()
        
        # 绘制顶部标题区域
        draw.rectangle([0, 0, width, 150], fill='#4A90D9')  # 蓝色标题栏
        draw.text((width//2, 75), "English Learning", font=title_font, fill='white', anchor='mm')
        
        # 绘制 Speaker 标签
        speaker_color = '#FF6B6B' if '1' in speaker else '#4ECDC4'  # 女/男不同颜色
        draw.rectangle([50, 180, 250, 230], fill=speaker_color)
        draw.text((150, 205), speaker, font=sentence_font, fill='white', anchor='mm')
        
        # 绘制句子（居中，自动换行）
        y_position = 300
        wrapped_lines = textwrap.wrap(sentence, width=40)
        for line in wrapped_lines:
            draw.text((width//2, y_position), line, font=sentence_font, fill='#333333', anchor='mm')
            y_position += 50
        
        # 绘制关键词区域
        if keywords:
            y_position = height - 400
            draw.rectangle([50, y_position - 30, width - 50, y_position + 150], fill='#E8E8E8')
            draw.text((width//2, y_position), "Keywords:", font=keyword_font, fill='#666666', anchor='mm')
            
            y_position += 50
            for kw in keywords[:3]:  # 只显示前3个关键词
                # 关键词卡片
                kw_width = 200
                kw_x = width//2 - kw_width//2
                draw.rectangle([kw_x, y_position - 20, kw_x + kw_width, y_position + 20], fill='#FFD700')
                draw.text((width//2, y_position), kw, font=keyword_font, fill='#333333', anchor='mm')
                y_position += 50
        
        # 保存图片
        img.save(output_path, 'PNG')
        logger.info(f"   PIL 备选图片生成成功: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"   PIL 备选图片生成失败: {e}")
        # 创建最简单的纯色图片
        img = Image.new('RGB', (1080, 1920), color='#CCCCCC')
        draw = ImageDraw.Draw(img)
        draw.text((540, 960), sentence[:50], fill='black', anchor='mm')
        img.save(output_path, 'PNG')
        return output_path


def generate_podcast_video(article_text: str, output_dir: str, 
                            dialogue_turns: int = 5,
                            difficulty: str = "middle",
                            speaker_1_voice: str = "gemini:Kore",
                            speaker_2_voice: str = "gemini:Puck",
                            bgm_type: str = "random", bgm_volume: float = 0.2,
                            bgm_file: str = ""):
    """生成播客视频的完整流程"""
    
    results = {
        "success": False,
        "script": None,
        "terms": [],
        "images": [],
        "audio_segments": [],
        "video_path": None,
        "error": None
    }
    
    try:
        # 步骤1: 生成播客脚本
        st.info(f"📝 正在生成播客脚本（{dialogue_turns}轮对话，{difficulty}难度）...")
        podcast_script = llm.generate_podcast_script(
            article_text=article_text,
            language="English",
            dialogue_turns=dialogue_turns,
            difficulty=difficulty
        )
        
        if not podcast_script:
            results["error"] = "生成播客脚本失败"
            return results
        
        # 设置语音（使用用户选择的语音）
        for turn in podcast_script:
            turn.speaker_1_voice = speaker_1_voice
            turn.speaker_2_voice = speaker_2_voice
        
        results["script"] = podcast_script
        logger.info(f"✅ 成功生成 {len(podcast_script)} 轮对话")
        
        # 步骤2: 一次性提取每个句子的关键词
        st.info("🔑 正在提取关键词...")
        sentence_keywords = llm.generate_terms_for_each_sentence(podcast_script=podcast_script, amount=3)
        
        # 同时提取全局关键词用于显示
        video_terms = llm.generate_terms_from_podcast(podcast_script=podcast_script, amount=5)
        results["terms"] = video_terms
        logger.info(f"✅ 全局关键词: {', '.join(video_terms)}")
        logger.info(f"✅ 已为 {len(sentence_keywords)} 个句子提取独立关键词")
        
        # 步骤3: 生成音频片段（直接使用 siliconflow_tts）
        st.info("🔊 正在生成语音音频...")
        audio_segments = []
        segment_index = 0
        
        for turn_idx, turn in enumerate(podcast_script, 1):
            # Speaker 1 音频
            if turn.speaker_1:
                audio_path = os.path.join(output_dir, f"audio_segment_{segment_index}_speaker1.mp3")
                logger.info(f"   生成音频片段 {segment_index} (Speaker 1): {turn.speaker_1[:50]}...")
                
                try:
                    # 统一语音合成（按音色前缀分发，主用 MiniMax TTS）
                    sub_maker = _synthesize_speech(
                        voice_name=turn.speaker_1_voice,
                        text=turn.speaker_1,
                        voice_file=audio_path,
                    )

                    if sub_maker and os.path.exists(audio_path):
                        duration = _get_audio_file_duration(audio_path)
                        if duration <= 0:
                            raise RuntimeError("Unable to read generated audio duration")
                        audio_segments.append((audio_path, duration, segment_index))
                        logger.info(f"   ✅ 音频片段 {segment_index}: {duration:.2f}秒")
                        segment_index += 1
                    else:
                        logger.error(f"   ❌ 音频片段 {segment_index} 生成失败")
                        results["error"] = f"音频片段 {segment_index} 生成失败"
                        return results
                except Exception as e:
                    logger.error(f"   ❌ 音频生成异常: {str(e)}")
                    results["error"] = f"音频生成异常: {str(e)}"
                    return results
            
            # Speaker 2 音频
            if turn.speaker_2:
                audio_path = os.path.join(output_dir, f"audio_segment_{segment_index}_speaker2.mp3")
                logger.info(f"   生成音频片段 {segment_index} (Speaker 2): {turn.speaker_2[:50]}...")
                
                try:
                    # 统一语音合成（按音色前缀分发，主用 MiniMax TTS）
                    sub_maker = _synthesize_speech(
                        voice_name=turn.speaker_2_voice,
                        text=turn.speaker_2,
                        voice_file=audio_path,
                    )

                    if sub_maker and os.path.exists(audio_path):
                        duration = _get_audio_file_duration(audio_path)
                        if duration <= 0:
                            raise RuntimeError("Unable to read generated audio duration")
                        audio_segments.append((audio_path, duration, segment_index))
                        logger.info(f"   ✅ 音频片段 {segment_index}: {duration:.2f}秒")
                        segment_index += 1
                    else:
                        logger.error(f"   ❌ 音频片段 {segment_index} 生成失败")
                        results["error"] = f"音频片段 {segment_index} 生成失败"
                        return results
                except Exception as e:
                    logger.error(f"   ❌ 音频生成异常: {str(e)}")
                    results["error"] = f"音频生成异常: {str(e)}"
                    return results
        
        results["audio_segments"] = audio_segments
        logger.info(f"✅ 共生成 {len(audio_segments)} 个音频片段")
        
        # 步骤4: 生成教育图片（每个图片使用对应的关键词）
        st.info("🖼️ 正在生成教育图片...")
        image_paths = []
        image_index = 0
        
        for turn_idx, turn in enumerate(podcast_script, 1):
            # Speaker 1 图片
            if turn.speaker_1:
                output_path = os.path.join(output_dir, f"image_{image_index}_speaker1.png")
                # 使用该句子对应的关键词
                keywords = sentence_keywords.get(image_index, video_terms)
                
                # 尝试 AI 生成图片
                result = generate_sentence_image(
                    sentence=turn.speaker_1,
                    keywords=keywords,
                    output_path=output_path
                )
                
                # 如果 AI 生成失败，使用 PIL 备选图片
                if result and os.path.exists(result):
                    image_paths.append(result)
                    logger.info(f"   图片 {image_index}: AI生成成功, 关键词={keywords} ✅")
                else:
                    logger.warning(f"   图片 {image_index}: AI生成失败，使用PIL备选图片")
                    fallback_path = generate_fallback_image(
                        sentence=turn.speaker_1,
                        keywords=keywords,
                        output_path=output_path,
                        speaker="Speaker 1"
                    )
                    image_paths.append(fallback_path)
                    logger.info(f"   图片 {image_index}: PIL备选图片 ✅")
                
                image_index += 1
            
            # Speaker 2 图片
            if turn.speaker_2:
                output_path = os.path.join(output_dir, f"image_{image_index}_speaker2.png")
                # 使用该句子对应的关键词
                keywords = sentence_keywords.get(image_index, video_terms)
                
                # 尝试 AI 生成图片
                result = generate_sentence_image(
                    sentence=turn.speaker_2,
                    keywords=keywords,
                    output_path=output_path
                )
                
                # 如果 AI 生成失败，使用 PIL 备选图片
                if result and os.path.exists(result):
                    image_paths.append(result)
                    logger.info(f"   图片 {image_index}: AI生成成功, 关键词={keywords} ✅")
                else:
                    logger.warning(f"   图片 {image_index}: AI生成失败，使用PIL备选图片")
                    fallback_path = generate_fallback_image(
                        sentence=turn.speaker_2,
                        keywords=keywords,
                        output_path=output_path,
                        speaker="Speaker 2"
                    )
                    image_paths.append(fallback_path)
                    logger.info(f"   图片 {image_index}: PIL备选图片 ✅")
                
                image_index += 1
        
        results["images"] = image_paths
        logger.info(f"✅ 共生成 {len(image_paths)} 张图片（确保与音频片段数量一致）")
        
        # 步骤5: 合成视频
        st.info("🎬 正在合成视频...")
        
        # 匹配图片和音频
        if len(image_paths) != len(audio_segments):
            count = min(len(image_paths), len(audio_segments))
            image_paths = image_paths[:count]
            audio_segments = audio_segments[:count]
        
        # 创建视频片段
        video_segments = []
        aspect = VideoAspect.portrait
        video_width, video_height = aspect.to_resolution()
        
        for i, (image_path, (audio_file, audio_duration, _)) in enumerate(zip(image_paths, audio_segments)):
            segment_video = os.path.join(output_dir, f"segment_{i}.mp4")
            
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-i', image_path,
                '-i', audio_file,
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-vf', f'scale={video_width}:{video_height}',
                '-t', str(audio_duration),
                '-shortest',
                '-threads', '2',
                segment_video
            ]
            
            subprocess.run(cmd, capture_output=True, text=True)
            if os.path.exists(segment_video):
                video_segments.append(segment_video)
                logger.info(f"   片段 {i}: {audio_duration:.2f}秒 ✅")
        
        # 拼接视频片段
        video_list_file = os.path.join(output_dir, "video_list.txt")
        with open(video_list_file, "w") as f:
            for video_path in video_segments:
                f.write(f"file '{os.path.abspath(video_path)}'\n")
        
        final_video = os.path.join(output_dir, "final_video_no_bgm.mp4")
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', video_list_file,
            '-c', 'copy',
            final_video
        ]
        
        subprocess.run(cmd, capture_output=True, text=True)
        
        # 清理临时文件
        try:
            os.remove(video_list_file)
            for seg in video_segments:
                os.remove(seg)
        except:
            pass
        
        # 步骤6: 混合背景音乐
        if bgm_type and bgm_type != "none":
            st.info("🎵 正在添加背景音乐...")
            # custom 模式使用用户指定的曲目，random 模式让 get_bgm_file 随机选
            resolved_bgm_file = bgm_file if (bgm_type == "custom" and bgm_file) else ""
            if bgm_type != "custom":
                resolved_bgm_file = get_bgm_file(bgm_type=bgm_type, bgm_file="")

            if resolved_bgm_file and os.path.exists(resolved_bgm_file):
                logger.info(f"   使用背景音乐: {os.path.basename(resolved_bgm_file)}")
                final_video_with_bgm = os.path.join(output_dir, "final_video.mp4")

                # 使用 ffmpeg 混合语音和背景音乐
                # 关键：先用 volume 滤镜把背景音乐降到 bgm_volume，再 amix，
                # 否则音量滑块无效（旧行为是死代码）。
                filter_complex = (
                    f"[1:a]volume={bgm_volume}[bg];"
                    f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]"
                )

                cmd = [
                    'ffmpeg', '-y',
                    '-i', final_video,
                    '-stream_loop', '-1',
                    '-i', resolved_bgm_file,
                    '-filter_complex', filter_complex,
                    '-map', '0:v',
                    '-map', '[aout]',
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',
                    '-threads', '2',
                    final_video_with_bgm
                ]

                proc = subprocess.run(cmd, capture_output=True, text=True)

                if os.path.exists(final_video_with_bgm) and os.path.getsize(final_video_with_bgm) > 0:
                    final_video = final_video_with_bgm
                    logger.info(f"   ✅ 背景音乐已添加 (音量: {bgm_volume})")
                else:
                    logger.error(f"   ⚠️ 背景音乐混合失败: {proc.stderr[-300:] if proc.stderr else ''}")
                    st.error("背景音乐混合失败，已使用无音乐版本")
            else:
                logger.warning(f"   ⚠️ 未找到背景音乐文件")
                st.warning("未找到背景音乐文件（检查 resource/songs 是否有 mp3），已使用无音乐版本")
                # 重命名为最终文件名
                final_video_with_bgm = os.path.join(output_dir, "final_video.mp4")
                if os.path.exists(final_video):
                    import shutil
                    shutil.copy2(final_video, final_video_with_bgm)
                    final_video = final_video_with_bgm
        else:
            # 不需要背景音乐，直接重命名为最终文件名
            final_video_with_bgm = os.path.join(output_dir, "final_video.mp4")
            if os.path.exists(final_video):
                import shutil
                shutil.copy2(final_video, final_video_with_bgm)
                final_video = final_video_with_bgm
        
        if os.path.exists(final_video):
            results["video_path"] = final_video
            logger.info(f"✅ 视频生成成功: {final_video}")
            results["success"] = True
        else:
            results["error"] = "视频合成失败"
            
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"生成视频时出错: {e}")
    
    return results


def format_script_preview(script: list) -> str:
    """格式化脚本预览"""
    lines = []
    for i, turn in enumerate(script, 1):
        lines.append(f"**第 {i} 轮对话**")
        lines.append(f"👤 Speaker 1: {turn.speaker_1}")
        lines.append(f"👤 Speaker 2: {turn.speaker_2}")
        lines.append("")
    return "\n".join(lines)


# ============ WebUI 界面 ============

# ===== 左边栏设置 =====
with st.sidebar:
    st.header("⚙️ 设置")
    
    # 对话设置
    st.subheader("💬 对话设置")
    
    # 难度选择
    difficulty = st.selectbox(
        "难度级别",
        options=["elementary", "middle", "high", "university"],
        format_func=lambda x: {
            "elementary": "小学水平 📚",
            "middle": "初中水平 📖",
            "high": "高中水平 📓",
            "university": "大学水平 🎓"
        }.get(x, x),
        index=1,  # 默认初中
        help="选择对话内容的难度级别，影响词汇复杂度和句式结构",
        key="difficulty_select"
    )
    
    # 显示难度说明
    difficulty_desc = {
        "elementary": "简单词汇、短句（5-8词）、基础语法",
        "middle": "中等词汇、中长句（8-15词）、复合句",
        "high": "高级词汇、长句（15-25词）、复杂句式",
        "university": "学术词汇、复杂句（20-35词）、专业表达"
    }
    st.caption(f"💡 {difficulty_desc.get(difficulty, '')}")
    
    # 对话轮数
    dialogue_turns = st.slider(
        "对话轮数",
        min_value=2,
        max_value=10,
        value=5,
        step=1,
        help="设置生成的对话轮数（每轮包含 Speaker 1 和 Speaker 2 的对话）",
        key="dialogue_turns_slider"
    )
    
    st.caption(f"📊 将生成 {dialogue_turns} 轮对话（{dialogue_turns * 2} 个片段）")
    
    st.divider()
    
    # 语音设置（Gemini TTS）
    st.subheader("🎙️ 语音设置")
    st.caption("使用 Gemini TTS（build2api.wanyan.de）")

    gemini_female_voices = [
        "gemini:Kore",
        "gemini:Aoede",
    ]
    gemini_male_voices = [
        "gemini:Puck",
        "gemini:Charon",
        "gemini:Fenrir",
    ]

    speaker_1_voice = st.selectbox(
        "对话人 1 (女声)",
        options=gemini_female_voices,
        index=0,
        format_func=lambda x: x.split(":")[-1],
        key="speaker_1_voice_select",
    )

    speaker_2_voice = st.selectbox(
        "对话人 2 (男声)",
        options=gemini_male_voices,
        index=0,
        format_func=lambda x: x.split(":")[-1],
        key="speaker_2_voice_select",
    )
    
    st.divider()
    
    # 音乐设置
    st.subheader("🎵 背景音乐")

    bgm_type = st.selectbox(
        "音乐类型",
        options=["random", "custom", "none"],
        format_func=lambda x: {"random": "随机选择", "custom": "指定曲目", "none": "无背景音乐"}[x],
        key="bgm_type_select"
    )

    bgm_volume = st.slider(
        "音乐音量",
        min_value=0.0,
        max_value=0.5,
        value=0.15,
        step=0.05,
        format="%.2f",
        help="建议设置为 0.1-0.2，避免盖过语音",
        key="bgm_volume_slider"
    )

    # 音乐库列表与指定曲目选择
    song_dir = utils.song_dir()
    mp3_files = sorted([f for f in os.listdir(song_dir) if f.endswith('.mp3')]) if os.path.exists(song_dir) else []
    if mp3_files:
        st.caption(f"📂 音乐库: {len(mp3_files)} 个文件")

    bgm_file = ""
    if bgm_type == "custom":
        if not mp3_files:
            st.warning("音乐库为空（resource/songs 无 mp3），将无法添加背景音乐")
        else:
            selected_song = st.selectbox(
                "选择曲目",
                options=mp3_files,
                key="bgm_song_select"
            )
            bgm_file = os.path.join(song_dir, selected_song) if selected_song else ""
            if bgm_file and os.path.exists(bgm_file):
                with open(bgm_file, "rb") as _af:
                    st.audio(_af.read(), format="audio/mp3")

# ===== 主界面 =====
# 标题
st.title("📚 教育视频生成器")
st.caption("输入文章内容，自动生成带语音和解说的教育短视频")

# 文章输入
st.subheader("📝 输入文章内容")
article_text = st.text_area(
    "粘贴英文文章...",
    height=200,
    placeholder="请粘贴要转换为教育视频的英文文章内容...\n\n例如：\nThe Dragon Boat Festival is a traditional Chinese holiday..."
)

# 保存到session state
st.session_state["article_text"] = article_text

# 分隔线
st.divider()

# 生成按钮
col1, col2 = st.columns(2)

with col1:
    generate_btn = st.button(
        "🚀 开始生成视频",
        type="primary",
        use_container_width=True,
        disabled=not article_text.strip()
    )

with col2:
    clear_btn = st.button(
        "🗑️ 清空",
        use_container_width=True
    )

if clear_btn:
    st.session_state["article_text"] = ""
    st.session_state["podcast_script"] = None
    st.session_state["generation_complete"] = False
    st.session_state["error_message"] = None
    st.rerun()

# 显示结果区域
results_container = st.container()

with results_container:
    # 如果有生成的脚本，显示预览
    if st.session_state.get("podcast_script"):
        st.divider()
        st.subheader("📖 生成的对话脚本")
        
        for i, turn in enumerate(st.session_state["podcast_script"], 1):
            with st.expander(f"第 {i} 轮对话", expanded=i==1):
                st.markdown(f"**👤 Speaker 1:**\n{turn.speaker_1}")
                st.markdown(f"**👤 Speaker 2:**\n{turn.speaker_2}")
        
        st.divider()
    
    # 显示关键词
    if st.session_state.get("video_terms"):
        st.subheader("🔑 关键词")
        keywords_str = " | ".join(st.session_state["video_terms"])
        st.info(keywords_str)
        st.divider()
    
    # 显示视频预览
    if st.session_state.get("video_path") and os.path.exists(st.session_state["video_path"]):
        st.subheader("🎬 生成的视频")
        
        # 视频信息
        video_size = os.path.getsize(st.session_state["video_path"]) / (1024 * 1024)
        st.success(f"✅ 视频生成完成！文件大小: {video_size:.2f} MB")
        
        # 视频播放器 - 使用一半宽度显示
        col1, col2 = st.columns([1, 1])
        with col1:
            st.video(st.session_state["video_path"])
        
        # 下载按钮
        video_filename = f"education_video_{int(time.time())}.mp4"
        with open(st.session_state["video_path"], "rb") as f:
            st.download_button(
                "📥 下载视频",
                f,
                file_name=video_filename,
                mime="video/mp4",
                use_container_width=True
            )
        
        st.divider()
    
    # 显示错误信息
    if st.session_state.get("error_message"):
        st.error(f"❌ 生成失败: {st.session_state['error_message']}")
        st.divider()

# 处理生成
if generate_btn and article_text.strip():
    # 创建输出目录
    task_id = f"task_{uuid4().hex[:8]}"
    output_dir = os.path.join(root_dir, "storage", "tasks", task_id)
    os.makedirs(output_dir, exist_ok=True)
    st.session_state["task_output_dir"] = output_dir
    
    # 显示进度
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 更新进度
    progress_bar.progress(10)
    status_text.text("📝 正在生成播客脚本...")
    
    # 运行生成流程
    results = generate_podcast_video(
        article_text, 
        output_dir, 
        dialogue_turns=dialogue_turns,
        difficulty=difficulty,
        speaker_1_voice=speaker_1_voice,
        speaker_2_voice=speaker_2_voice,
        bgm_type=bgm_type, 
        bgm_volume=bgm_volume,
        bgm_file=bgm_file
    )
    
    progress_bar.progress(100)
    
    if results["success"]:
        st.session_state["podcast_script"] = results["script"]
        st.session_state["video_terms"] = results["terms"]
        st.session_state["video_path"] = results["video_path"]
        st.session_state["generation_complete"] = True
        st.session_state["error_message"] = None
        
        status_text.text("✅ 生成完成！")
        st.balloons()
        
        # 滚动到结果区域
        st.rerun()
    else:
        st.session_state["error_message"] = results["error"]
        st.session_state["generation_complete"] = False
        
        status_text.text("❌ 生成失败")
        st.error(results["error"])

# 底部信息
st.divider()
st.caption("📚 教育视频生成器 - 基于 SiliconFlow API | 使用 apimart Gemini-3 生成图片")
