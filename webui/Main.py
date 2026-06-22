#!/usr/bin/env python3
"""
简化版WebUI - 教育视频生成器
核心功能：输入文章 → 生成对话 → 生成视频
"""

import os
import sys
import time
import asyncio
import subprocess
from uuid import uuid4

import streamlit as st
from loguru import logger

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

# 页面配置
st.set_page_config(
    page_title="教育视频生成器",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 隐藏所有Streamlit默认样式
st.markdown("""
<style>
    .stApp > header {background-color: transparent;}
    .stApp > footer {display: none;}
    .stApp {padding-top: 1rem;}
    section[data-testid="stSidebar"] {display: none;}
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
</style>
""", unsafe_allow_html=True)

# 初始化日志
logger.remove()
logger.add(sys.stdout, level="INFO", format="{message}")

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

def generate_podcast_video(article_text: str, output_dir: str):
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
        st.info("📝 正在生成播客脚本...")
        podcast_script = llm.generate_podcast_script(
            article_text=article_text,
            language="English"
        )
        
        if not podcast_script:
            results["error"] = "生成播客脚本失败"
            return results
        
        # 设置语音
        for turn in podcast_script:
            turn.speaker_1_voice = "siliconflow:FunAudioLLM/CosyVoice2-0.5B:anna-Female"
            turn.speaker_2_voice = "siliconflow:FunAudioLLM/CosyVoice2-0.5B:benjamin-Male"
        
        results["script"] = podcast_script
        logger.info(f"✅ 成功生成 {len(podcast_script)} 轮对话")
        
        # 步骤2: 提取关键词
        st.info("🔑 正在提取关键词...")
        video_terms = llm.generate_terms_from_podcast(podcast_script=podcast_script, amount=5)
        results["terms"] = video_terms
        logger.info(f"✅ 关键词: {', '.join(video_terms)}")
        
        # 步骤3: 生成音频片段
        st.info("🔊 正在生成语音音频...")
        audio_segments = []
        segment_index = 0
        
        for turn_idx, turn in enumerate(podcast_script, 1):
            # Speaker 1 音频
            if turn.speaker_1:
                audio_path = os.path.join(output_dir, f"audio_segment_{segment_index}_speaker1.mp3")
                audio_file, duration = asyncio.run(
                    podcast_audio.podcast_audio_generator.generate_single_speaker_audio(
                        text=turn.speaker_1,
                        voice_name=turn.speaker_1_voice,
                        output_path=audio_path,
                        voice_rate=1.0,
                        voice_volume=1.0
                    )
                )
                if os.path.exists(audio_file):
                    audio_segments.append((audio_file, duration, segment_index))
                    logger.info(f"   音频片段 {segment_index}: {duration:.2f}秒")
                    segment_index += 1
            
            # Speaker 2 音频
            if turn.speaker_2:
                audio_path = os.path.join(output_dir, f"audio_segment_{segment_index}_speaker2.mp3")
                audio_file, duration = asyncio.run(
                    podcast_audio.podcast_audio_generator.generate_single_speaker_audio(
                        text=turn.speaker_2,
                        voice_name=turn.speaker_2_voice,
                        output_path=audio_path,
                        voice_rate=1.0,
                        voice_volume=1.0
                    )
                )
                if os.path.exists(audio_file):
                    audio_segments.append((audio_file, duration, segment_index))
                    logger.info(f"   音频片段 {segment_index}: {duration:.2f}秒")
                    segment_index += 1
        
        results["audio_segments"] = audio_segments
        logger.info(f"✅ 共生成 {len(audio_segments)} 个音频片段")
        
        # 步骤4: 生成教育图片
        st.info("🖼️ 正在生成教育图片...")
        image_paths = []
        image_index = 1
        
        for turn_idx, turn in enumerate(podcast_script, 1):
            # Speaker 1 图片
            if turn.speaker_1:
                output_path = os.path.join(output_dir, f"image_{image_index}_speaker1.png")
                result = generate_sentence_image(
                    sentence=turn.speaker_1,
                    keywords=video_terms,
                    output_path=output_path
                )
                if result and os.path.exists(result):
                    image_paths.append(result)
                    logger.info(f"   图片 {image_index}: ✅")
                    image_index += 1
            
            # Speaker 2 图片
            if turn.speaker_2:
                output_path = os.path.join(output_dir, f"image_{image_index}_speaker2.png")
                result = generate_sentence_image(
                    sentence=turn.speaker_2,
                    keywords=video_terms,
                    output_path=output_path
                )
                if result and os.path.exists(result):
                    image_paths.append(result)
                    logger.info(f"   图片 {image_index}: ✅")
                    image_index += 1
        
        results["images"] = image_paths
        logger.info(f"✅ 共生成 {len(image_paths)} 张图片")
        
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
        
        final_video = os.path.join(output_dir, "final_video.mp4")
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

# 标题
st.title("📚 教育视频生成器")
st.caption("输入文章内容，自动生成带语音和解说的教育短视频")

# 主布局
main_col = st.columns([1, 2])[1]

with main_col:
    # 文章输入
    st.subheader("📝 输入文章内容")
    article_text = st.text_area(
        "粘贴英文文章...",
        height=200,
        placeholder="请粘贴要转换为教育视频的英文文章内容...\n\n例如：\nThe Dragon Boat Festival is a traditional Chinese holiday..."
    )
    
    # 示例文章按钮
    if st.button("📋 使用示例文章", use_container_width=True):
        article_text = """
The Dragon Boat Festival is a traditional Chinese holiday celebrated on the fifth day of the fifth lunar month. 
People gather along rivers to watch exciting dragon boat races. 
Teams of paddlers row colorful dragon boats decorated with dragon heads and tails. 
The rhythmic drumming keeps everyone in perfect sync as they race toward the finish line.
Delicious zongzi, sticky rice dumplings wrapped in bamboo leaves, are eaten during this festival.
The festival commemorates the ancient poet Qu Yuan, who lived over two thousand years ago.
        """
        st.session_state["article_text"] = article_text
        st.rerun()
    
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
            
            # 视频播放器
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
    results = generate_podcast_video(article_text, output_dir)
    
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
