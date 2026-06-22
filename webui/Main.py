import asyncio
import os
import platform
import sys
from uuid import uuid4

import streamlit as st
from loguru import logger

# Add the root directory of the project to the system path to allow importing modules from the project
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
    print("******** sys.path ********")
    print(sys.path)
    print("")

from app.config import config
from typing import List
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
    PodcastScript,
)
from app.services import llm, voice
from app.services import task as tm
from app.services.podcast_audio import podcast_audio_generator
from app.utils import utils

st.set_page_config(
    page_title="MoneyPrinterTurbo - 播客视频生成器",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/harry0703/MoneyPrinterTurbo/issues",
        "About": "# MoneyPrinterTurbo 播客视频生成器\n"
        "粘贴文章内容，自动生成双人播客对话，并合成带字幕的高清短视频。\n"
        "支持多种音色组合，智能匹配视频素材，一键生成专业播客视频。\n\n"
        "https://github.com/harry0703/MoneyPrinterTurbo",
    },
)


streamlit_style = """
<style>
h1 {
    padding-top: 0 !important;
}
</style>
"""
st.markdown(streamlit_style, unsafe_allow_html=True)

# 定义资源目录
font_dir = os.path.join(root_dir, "resource", "fonts")
song_dir = os.path.join(root_dir, "resource", "songs")
i18n_dir = os.path.join(root_dir, "webui", "i18n")
config_file = os.path.join(root_dir, "webui", ".streamlit", "webui.toml")
system_locale = utils.get_system_locale()


if "video_terms" not in st.session_state:
    st.session_state["video_terms"] = ""
if "ui_language" not in st.session_state:
    st.session_state["ui_language"] = config.ui.get("language", system_locale)

# 播客相关状态
if "article_text" not in st.session_state:
    st.session_state["article_text"] = ""
if "podcast_script" not in st.session_state:
    st.session_state["podcast_script"] = None
if "speaker_1_voice" not in st.session_state:
    st.session_state["speaker_1_voice"] = config.app.get("podcast", {}).get("default_speaker_1_voice", "zh-CN-XiaoxiaoNeural-Female")
if "speaker_2_voice" not in st.session_state:
    st.session_state["speaker_2_voice"] = config.app.get("podcast", {}).get("default_speaker_2_voice", "zh-CN-YunxiNeural-Male")

# 加载语言文件
locales = utils.load_locales(i18n_dir)

# 创建一个顶部栏，包含标题和语言选择
title_col, lang_col = st.columns([3, 1])

with title_col:
    st.title(f"MoneyPrinterTurbo v{config.project_version}")

with lang_col:
    display_languages = []
    selected_index = 0
    for i, code in enumerate(locales.keys()):
        display_languages.append(f"{code} - {locales[code].get('Language')}")
        if code == st.session_state.get("ui_language", ""):
            selected_index = i

    selected_language = st.selectbox(
        "Language / 语言",
        options=display_languages,
        index=selected_index,
        key="top_language_selector",
        label_visibility="collapsed",
    )
    if selected_language:
        code = selected_language.split(" - ")[0].strip()
        st.session_state["ui_language"] = code
        config.ui["language"] = code

support_locales = [
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "de-DE",
    "en-US",
    "fr-FR",
    "vi-VN",
    "th-TH",
]


def get_all_fonts():
    fonts = []
    for root, dirs, files in os.walk(font_dir):
        for file in files:
            if file.endswith(".ttf") or file.endswith(".ttc"):
                fonts.append(file)
    fonts.sort()
    return fonts


def get_all_songs():
    songs = []
    for root, dirs, files in os.walk(song_dir):
        for file in files:
            if file.endswith(".mp3"):
                songs.append(file)
    return songs


def open_task_folder(task_id):
    try:
        sys = platform.system()
        path = os.path.join(root_dir, "storage", "tasks", task_id)
        if os.path.exists(path):
            if sys == "Windows":
                os.system(f"start {path}")
            if sys == "Darwin":
                os.system(f"open {path}")
    except Exception as e:
        logger.error(e)


def _format_podcast_script(podcast_script: List[PodcastScript]) -> str:
    """将播客对话脚本格式化为便于预览的文本。"""
    if not podcast_script:
        return ""

    script_lines = []
    for i, dialogue in enumerate(podcast_script):
        script_lines.append(f"第 {i + 1} 轮")
        script_lines.append(f"A: {dialogue.speaker_1}")
        script_lines.append(f"B: {dialogue.speaker_2}")
        if i < len(podcast_script) - 1:
            script_lines.append("")

    return "\n".join(script_lines)


def apply_selected_voices(podcast_script: List[PodcastScript]) -> List[PodcastScript]:
    for dialogue in podcast_script or []:
        dialogue.speaker_1_voice = st.session_state["speaker_1_voice"]
        dialogue.speaker_2_voice = st.session_state["speaker_2_voice"]
    return podcast_script


def run_tts_preview(text: str, voice_name: str, voice_rate: float) -> str:
    temp_dir = utils.storage_dir("temp", create=True)
    audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}.mp3")
    asyncio.run(
        voice.tts(
            text=text,
            voice_name=voice_name,
            voice_rate=voice_rate,
            voice_file=audio_file,
        )
    )
    return audio_file if os.path.exists(audio_file) else ""


def scroll_to_bottom():
    js = """
    <script>
        console.log("scroll_to_bottom");
        function scroll(dummy_var_to_force_repeat_execution){
            var sections = parent.document.querySelectorAll('section.main');
            console.log(sections);
            for(let index = 0; index<sections.length; index++) {
                sections[index].scrollTop = sections[index].scrollHeight;
            }
        }
        scroll(1);
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def init_log():
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        # 获取日志记录中的文件全路径
        file_path = record["file"].path
        # 将绝对路径转换为相对于项目根目录的路径
        relative_path = os.path.relpath(file_path, root_dir)
        # 更新记录中的文件路径
        record["file"].path = f"./{relative_path}"
        # 返回修改后的格式字符串
        # 您可以根据需要调整这里的格式
        record["message"] = record["message"].replace(root_dir, ".")

        _format = (
            "<green>{time:%Y-%m-%d %H:%M:%S}</> | "
            + "<level>{level}</> | "
            + '"{file.path}:{line}":<blue> {function}</> '
            + "- <level>{message}</>"
            + "\n"
        )
        return _format

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
    )


init_log()

locales = utils.load_locales(i18n_dir)


def tr(key):
    loc = locales.get(st.session_state["ui_language"], {})
    return loc.get("Translation", {}).get(key, key)


# 创建基础设置折叠框
if not config.app.get("hide_config", False):
    with st.expander(tr("Basic Settings"), expanded=False):
        config_panels = st.columns(3)
        left_config_panel = config_panels[0]
        middle_config_panel = config_panels[1]
        right_config_panel = config_panels[2]

        # 左侧面板 - 日志设置
        with left_config_panel:
            # 是否隐藏配置面板
            hide_config = st.checkbox(
                tr("Hide Basic Settings"), value=config.app.get("hide_config", False)
            )
            config.app["hide_config"] = hide_config

            # 是否禁用日志显示
            hide_log = st.checkbox(
                tr("Hide Log"), value=config.ui.get("hide_log", False)
            )
            config.ui["hide_log"] = hide_log

        # 中间面板 - LLM 设置 (仅使用 SiliconFlow)

        with middle_config_panel:
            st.write(tr("LLM Settings"))
            
            # 固定使用 SiliconFlow
            st.info("使用 SiliconFlow 作为 LLM 提供商")
            llm_provider = "siliconflow"
            
            siliconflow_api_key = config.siliconflow.get("api_key", "")
            st_siliconflow_api_key = st.text_input(
                "SiliconFlow API Key", 
                value=siliconflow_api_key, 
                type="password"
            )
            
            if st_siliconflow_api_key:
                config.siliconflow["api_key"] = st_siliconflow_api_key
            
            tips = """
                    ##### SiliconFlow 配置说明
                    - **API Key**: [点击到官网申请](https://cloud.siliconflow.cn/)
                    - 支持模型: Qwen/Qwen3-8B, zai-org/GLM-4.6, deepseek-ai/DeepSeek-V3.2
                    - 国内可直接访问，不需要VPN
                    - 注册就送额度
                    """
            st.info(tips)

        # 右侧面板 - SiliconFlow 设置
        with right_config_panel:
            st.write(tr("SiliconFlow Settings"))
            
            # SiliconFlow 图片生成 API Key
            siliconflow_image_key = config.siliconflow.get("api_key", "")
            siliconflow_image_key = st.text_input(
                "SiliconFlow API Key", 
                value=siliconflow_image_key, 
                type="password"
            )
            if siliconflow_image_key:
                config.siliconflow["api_key"] = siliconflow_image_key

panel = st.columns(3)
left_panel = panel[0]
middle_panel = panel[1]
right_panel = panel[2]

params = VideoParams()
uploaded_files = []

with left_panel:
    with st.container(border=True):
        st.write(tr("播客视频设置"))

        # 文章输入区域
        st.session_state["article_text"] = st.text_area(
            tr("粘贴文章内容"),
            value=st.session_state["article_text"],
            height=300,
            help=tr("请输入要转换为播客视频的文章内容"),
            key="article_text_input"
        ).strip()

        # 播客音色选择
        st.subheader(tr("音色设置"))

        # 获取推荐音色配对
        voice_pairs = podcast_audio_generator.get_recommended_voice_pairs()

        # 创建音色选择列
        voice_cols = st.columns(2)

        with voice_cols[0]:
            # 说话人1音色
            speaker_1_voices = [pair[0] for pair in voice_pairs]
            speaker_1_index = 0
            for i, voice_option in enumerate(speaker_1_voices):
                if voice_option == st.session_state["speaker_1_voice"]:
                    speaker_1_index = i
                    break

            selected_speaker_1_voice = st.selectbox(
                tr("说话人1音色"),
                options=speaker_1_voices,
                index=speaker_1_index,
                key="speaker_1_voice_select"
            )
            st.session_state["speaker_1_voice"] = selected_speaker_1_voice

        with voice_cols[1]:
            # 说话人2音色
            speaker_2_voices = [pair[1] for pair in voice_pairs]
            speaker_2_index = 0
            for i, voice_option in enumerate(speaker_2_voices):
                if voice_option == st.session_state["speaker_2_voice"]:
                    speaker_2_index = i
                    break

            selected_speaker_2_voice = st.selectbox(
                tr("说话人2音色"),
                options=speaker_2_voices,
                index=speaker_2_index,
                key="speaker_2_voice_select"
            )
            st.session_state["speaker_2_voice"] = selected_speaker_2_voice

        # 语言选择
        video_languages = [
            (tr("Auto Detect"), ""),
        ]
        for code in support_locales:
            video_languages.append((code, code))

        selected_index = st.selectbox(
            tr("脚本语言"),
            index=0,
            options=range(
                len(video_languages)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_languages[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_language = video_languages[selected_index][1]

        # 生成播客对话按钮
        if st.button(
            tr("生成播客对话"), key="generate_podcast_script"
        ):
            if not st.session_state["article_text"]:
                st.error(tr("请输入文章内容"))
                st.stop()

            with st.spinner(tr("正在生成播客对话...")):
                try:
                    # 生成播客脚本
                    podcast_script = llm.generate_podcast_script(
                        article_text=st.session_state["article_text"],
                        language=params.video_language
                    )

                    if podcast_script:
                        podcast_script = apply_selected_voices(podcast_script)
                        st.session_state["podcast_script"] = podcast_script
                        st.success(tr("播客对话生成成功！"))

                        # 显示生成的对话预览
                        with st.expander(tr("查看生成的播客对话"), expanded=True):
                            for i, dialogue in enumerate(podcast_script):
                                st.write(f"**说话人1**: {dialogue.speaker_1}")
                                st.write(f"**说话人2**: {dialogue.speaker_2}")
                                if i < len(podcast_script) - 1:
                                    st.write("---")
                    else:
                        st.error(tr("播客对话生成失败，请重试"))

                except Exception as e:
                    st.error(tr(f"生成播客对话时出错: {str(e)}"))

        # 显示生成的播客脚本（只读）
        if st.session_state["podcast_script"]:
            st.subheader(tr("生成的播客脚本"))
            st.text_area(
                tr("播客脚本"),
                value=_format_podcast_script(st.session_state["podcast_script"]),
                height=240,
                disabled=True
            )

with middle_panel:
    with st.container(border=True):
        st.write(tr("Video Settings"))
        video_concat_modes = [
            (tr("Sequential"), "sequential"),
            (tr("Random"), "random"),
        ]
        video_sources = [
            (tr("SiliconFlow AI"), "siliconflow"),
        ]

        saved_video_source_name = config.app.get("video_source", "siliconflow")
        saved_video_source_index = [v[1] for v in video_sources].index(
            saved_video_source_name
        )

        selected_index = st.selectbox(
            tr("Video Source"),
            options=range(len(video_sources)),
            format_func=lambda x: video_sources[x][0],
            index=saved_video_source_index,
        )
        params.video_source = video_sources[selected_index][1]
        config.app["video_source"] = params.video_source

        if params.video_source == "local":
            uploaded_files = st.file_uploader(
                "Upload Local Files",
                type=["mp4", "mov", "avi", "flv", "mkv", "jpg", "jpeg", "png"],
                accept_multiple_files=True,
            )

        selected_index = st.selectbox(
            tr("Video Concat Mode"),
            index=1,
            options=range(
                len(video_concat_modes)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_concat_modes[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_concat_mode = VideoConcatMode(
            video_concat_modes[selected_index][1]
        )

        # 视频转场模式
        video_transition_modes = [
            (tr("None"), VideoTransitionMode.none.value),
            (tr("Shuffle"), VideoTransitionMode.shuffle.value),
            (tr("FadeIn"), VideoTransitionMode.fade_in.value),
            (tr("FadeOut"), VideoTransitionMode.fade_out.value),
            (tr("SlideIn"), VideoTransitionMode.slide_in.value),
            (tr("SlideOut"), VideoTransitionMode.slide_out.value),
        ]
        selected_index = st.selectbox(
            tr("Video Transition Mode"),
            options=range(len(video_transition_modes)),
            format_func=lambda x: video_transition_modes[x][0],
            index=0,
        )
        params.video_transition_mode = VideoTransitionMode(
            video_transition_modes[selected_index][1]
        )

        video_aspect_ratios = [
            (tr("Portrait"), VideoAspect.portrait.value),
            (tr("Landscape"), VideoAspect.landscape.value),
        ]
        selected_index = st.selectbox(
            tr("Video Ratio"),
            options=range(
                len(video_aspect_ratios)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_aspect_ratios[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])

        params.video_clip_duration = st.selectbox(
            tr("Clip Duration"), options=[2, 3, 4, 5, 6, 7, 8, 9, 10], index=1
        )
        params.video_count = st.selectbox(
            tr("Number of Videos Generated Simultaneously"),
            options=[1, 2, 3, 4, 5],
            index=0,
        )
    with st.container(border=True):
        st.write(tr("Audio Settings"))

        # TTS 服务器（固定使用 SiliconFlow）
        st.info("使用 SiliconFlow 作为 TTS 服务")
        selected_tts_server = "siliconflow"
        config.ui["tts_server"] = selected_tts_server

        # 获取 SiliconFlow 的声音列表
        filtered_voices = voice.get_siliconflow_voices()

        voice_name = st.session_state["speaker_1_voice"]
        if not filtered_voices:
            st.warning(
                tr(
                    "No voices available for the selected TTS server. Please select another server."
                )
            )

        preview_cols = st.columns(2)
        preview_text = tr("Voice Example")
        if st.session_state["podcast_script"]:
            first_dialogue = st.session_state["podcast_script"][0]
            preview_text = first_dialogue.speaker_1 or first_dialogue.speaker_2 or preview_text

        with preview_cols[0]:
            if st.button(tr("试听说话人1")):
                with st.spinner(tr("Synthesizing Voice")):
                    audio_file = run_tts_preview(
                        preview_text,
                        st.session_state["speaker_1_voice"],
                        params.voice_rate,
                    )
                    if audio_file:
                        st.audio(audio_file, format="audio/mp3")
                        os.remove(audio_file)
                    else:
                        st.error(tr("语音试听生成失败"))

        with preview_cols[1]:
            if st.button(tr("试听说话人2")):
                with st.spinner(tr("Synthesizing Voice")):
                    audio_file = run_tts_preview(
                        preview_text,
                        st.session_state["speaker_2_voice"],
                        params.voice_rate,
                    )
                    if audio_file:
                        st.audio(audio_file, format="audio/mp3")
                        os.remove(audio_file)
                    else:
                        st.error(tr("语音试听生成失败"))

        # SiliconFlow API Key 配置
        saved_siliconflow_api_key = config.siliconflow.get("api_key", "")
        siliconflow_api_key = st.text_input(
            tr("SiliconFlow API Key"),
            value=saved_siliconflow_api_key,
            type="password",
            key="siliconflow_api_key_input",
        )

        # 显示 SiliconFlow 的说明信息
        st.info(
            tr("SiliconFlow TTS Settings")
            + ":\n"
            + "- "
            + tr("Speed: Range [0.25, 4.0], default is 1.0")
            + "\n"
            + "- "
            + tr("Volume: Uses Speech Volume setting, default 1.0 maps to gain 0")
        )

        config.siliconflow["api_key"] = siliconflow_api_key

        params.voice_volume = st.selectbox(
            tr("Speech Volume"),
            options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
            index=2,
        )

        params.voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )

        bgm_options = [
            (tr("No Background Music"), ""),
            (tr("Random Background Music"), "random"),
            (tr("Custom Background Music"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Background Music"),
            index=1,
            options=range(
                len(bgm_options)
            ),  # Use the index as the internal option value
            format_func=lambda x: bgm_options[x][
                0
            ],  # The label is displayed to the user
        )
        # Get the selected background music type
        params.bgm_type = bgm_options[selected_index][1]

        # Show or hide components based on the selection
        if params.bgm_type == "custom":
            custom_bgm_file = st.text_input(
                tr("Custom Background Music File"), key="custom_bgm_file_input"
            )
            if custom_bgm_file and os.path.exists(custom_bgm_file):
                params.bgm_file = custom_bgm_file
                # st.write(f":red[已选择自定义背景音乐]：**{custom_bgm_file}**")
        params.bgm_volume = st.selectbox(
            tr("Background Music Volume"),
            options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            index=2,
        )

with right_panel:
    with st.container(border=True):
        st.write(tr("Subtitle Settings"))
        params.subtitle_enabled = st.checkbox(tr("Enable Subtitles"), value=True)
        font_names = get_all_fonts()
        saved_font_name = config.ui.get("font_name", "MicrosoftYaHeiBold.ttc")
        saved_font_name_index = 0
        if saved_font_name in font_names:
            saved_font_name_index = font_names.index(saved_font_name)
        params.font_name = st.selectbox(
            tr("Font"), font_names, index=saved_font_name_index
        )
        config.ui["font_name"] = params.font_name

        subtitle_positions = [
            (tr("Top"), "top"),
            (tr("Center"), "center"),
            (tr("Bottom"), "bottom"),
            (tr("Custom"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Position"),
            index=2,
            options=range(len(subtitle_positions)),
            format_func=lambda x: subtitle_positions[x][0],
        )
        params.subtitle_position = subtitle_positions[selected_index][1]

        if params.subtitle_position == "custom":
            custom_position = st.text_input(
                tr("Custom Position (% from top)"),
                value="70.0",
                key="custom_position_input",
            )
            try:
                params.custom_position = float(custom_position)
                if params.custom_position < 0 or params.custom_position > 100:
                    st.error(tr("Please enter a value between 0 and 100"))
            except ValueError:
                st.error(tr("Please enter a valid number"))

        font_cols = st.columns([0.3, 0.7])
        with font_cols[0]:
            saved_text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")
            params.text_fore_color = st.color_picker(
                tr("Font Color"), saved_text_fore_color
            )
            config.ui["text_fore_color"] = params.text_fore_color

        with font_cols[1]:
            saved_font_size = config.ui.get("font_size", 60)
            params.font_size = st.slider(tr("Font Size"), 30, 100, saved_font_size)
            config.ui["font_size"] = params.font_size

        stroke_cols = st.columns([0.3, 0.7])
        with stroke_cols[0]:
            params.stroke_color = st.color_picker(tr("Stroke Color"), "#000000")
        with stroke_cols[1]:
            params.stroke_width = st.slider(tr("Stroke Width"), 0.0, 10.0, 1.5)

start_button = st.button(tr("生成播客视频"), use_container_width=True, type="primary")
if start_button:
    config.save_config()
    task_id = str(uuid4())

    # 播客模式验证
    if not st.session_state["article_text"]:
        st.error(tr("请输入文章内容"))
        scroll_to_bottom()
        st.stop()

    if not st.session_state["podcast_script"]:
        st.error(tr("请先生成播客对话"))
        scroll_to_bottom()
        st.stop()

    # 设置播客相关参数
    params.article_text = st.session_state["article_text"]
    params.podcast_script = apply_selected_voices(st.session_state["podcast_script"])
    params.speaker_1_voice = st.session_state["speaker_1_voice"]
    params.speaker_2_voice = st.session_state["speaker_2_voice"]
    params.video_terms = llm.generate_terms_from_podcast(params.podcast_script)

    if params.video_source not in ["siliconflow"]:
        st.error(tr("Please Select a Valid Video Source"))
        scroll_to_bottom()
        st.stop()

    if uploaded_files:
        local_videos_dir = utils.storage_dir("local_videos", create=True)
        for file in uploaded_files:
            file_path = os.path.join(local_videos_dir, f"{file.file_id}_{file.name}")
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
                m = MaterialInfo()
                m.provider = "local"
                m.url = file_path
                if not params.video_materials:
                    params.video_materials = []
                params.video_materials.append(m)

    log_container = st.empty()
    log_records = []

    def log_received(msg):
        if config.ui["hide_log"]:
            return
        with log_container:
            log_records.append(msg)
            st.code("\n".join(log_records))

    logger.add(log_received)

    st.toast(tr("Generating Video"))
    logger.info(tr("Start Generating Video"))
    logger.info(utils.to_json(params))
    scroll_to_bottom()

    result = tm.start(task_id=task_id, params=params)
    if not result or "videos" not in result:
        st.error(tr("Video Generation Failed"))
        logger.error(tr("Video Generation Failed"))
        scroll_to_bottom()
        st.stop()

    video_files = result.get("videos", [])
    st.success(tr("Video Generation Completed"))
    try:
        if video_files:
            player_cols = st.columns(len(video_files) * 2 + 1)
            for i, url in enumerate(video_files):
                player_cols[i * 2 + 1].video(url)
    except Exception:
        pass

    open_task_folder(task_id)
    logger.info(tr("Video Generation Completed"))
    scroll_to_bottom()

config.save_config()