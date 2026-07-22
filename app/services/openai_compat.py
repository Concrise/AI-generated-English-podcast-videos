"""
OpenAI 兼容 API 客户端

支持任意 OpenAI 兼容第三方网关 / 中转站：
  - Chat Completions:  POST {base_url}/chat/completions
  - Images:            POST {base_url}/images/generations
  - Speech (TTS):      POST {base_url}/audio/speech

配置见 config.toml 的 [openai] 段。
当 openai.api_key 非空时，LLM / 生图 / TTS 优先走本模块。
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import requests
from loguru import logger

from app.config import config


def _section_dict(section_name: str) -> Dict[str, Any]:
    """安全读取 config 上的某个 toml section。"""
    return dict(getattr(config, section_name, None) or {})


def _normalize_base_url(base_url: str) -> str:
    return str(base_url or "").strip().rstrip("/")


def get_image_settings() -> Dict[str, Any]:
    """
    生图配置。
    优先 [image]；api_key 为空时回退 [openai]。
    """
    image_section = _section_dict("image")
    openai_section = _section_dict("openai")

    api_key = str(image_section.get("api_key") or openai_section.get("api_key") or "").strip()
    base_url = _normalize_base_url(
        image_section.get("base_url")
        or openai_section.get("base_url")
        or "https://api.openai.com/v1"
    )
    image_model = str(
        image_section.get("model")
        or image_section.get("image_model")
        or openai_section.get("image_model")
        or "dall-e-3"
    ).strip()
    image_size = str(
        image_section.get("size")
        or image_section.get("image_size")
        or openai_section.get("image_size")
        or "1024x1792"
    ).strip()
    timeout_value = int(
        image_section.get("timeout")
        or openai_section.get("timeout")
        or 120
    )
    return {
        "api_key": api_key,
        "base_url": base_url,
        "image_model": image_model,
        "image_size": image_size,
        "timeout": timeout_value,
    }


def get_tts_settings() -> Dict[str, Any]:
    """
    TTS 配置。
    优先 [tts]；api_key 为空时回退 [openai]。
    provider:
      - openai  : POST {base_url}/audio/speech
      - gemini  : POST {base_url}/v1beta/models/{model}:generateContent
    """
    tts_section = _section_dict("tts")
    openai_section = _section_dict("openai")

    api_key = str(tts_section.get("api_key") or openai_section.get("api_key") or "").strip()
    base_url = _normalize_base_url(
        tts_section.get("base_url")
        or openai_section.get("base_url")
        or "https://api.openai.com/v1"
    )
    tts_model = str(
        tts_section.get("model")
        or tts_section.get("tts_model")
        or openai_section.get("tts_model")
        or "tts-1"
    ).strip()
    tts_voice = str(
        tts_section.get("voice")
        or tts_section.get("tts_voice")
        or openai_section.get("tts_voice")
        or "Kore"
    ).strip()
    provider = str(tts_section.get("provider") or "").strip().lower()
    if not provider:
        # 模型名含 tts 且不像 openai tts-1 时，默认按 gemini 处理
        if "gemini" in tts_model.lower() or tts_model.endswith("-tts-preview"):
            provider = "gemini"
        else:
            provider = "openai"
    timeout_value = int(
        tts_section.get("timeout")
        or openai_section.get("timeout")
        or 120
    )
    return {
        "api_key": api_key,
        "base_url": base_url,
        "tts_model": tts_model,
        "tts_voice": tts_voice,
        "provider": provider,
        "timeout": timeout_value,
    }


def get_media_settings() -> Dict[str, Any]:
    """兼容旧调用：合并生图 + TTS 配置（字段并集）。"""
    image_settings = get_image_settings()
    tts_settings = get_tts_settings()
    openai_section = _section_dict("openai")
    return {
        "api_key": image_settings["api_key"] or tts_settings["api_key"],
        "base_url": image_settings["base_url"],
        "llm_model": str(openai_section.get("llm_model") or "gpt-4o-mini").strip(),
        "image_model": image_settings["image_model"],
        "image_size": image_settings["image_size"],
        "tts_model": tts_settings["tts_model"],
        "tts_voice": tts_settings["tts_voice"],
        "timeout": max(image_settings["timeout"], tts_settings["timeout"]),
    }


def get_llm_settings() -> Dict[str, Any]:
    """
    LLM 专用配置。
    优先 [llm]；若 api_key 为空则回退到 [openai]（旧配置兼容）。
    """
    llm_section = _section_dict("llm")
    openai_section = _section_dict("openai")

    api_key = str(llm_section.get("api_key") or "").strip()
    base_url = _normalize_base_url(llm_section.get("base_url") or "")
    model_name = str(llm_section.get("model") or llm_section.get("llm_model") or "").strip()
    timeout_value = llm_section.get("timeout")

    if not api_key:
        return {
            "api_key": str(openai_section.get("api_key") or "").strip(),
            "base_url": _normalize_base_url(
                openai_section.get("base_url") or "https://api.openai.com/v1"
            ),
            "model": str(openai_section.get("llm_model") or "gpt-4o-mini").strip(),
            "timeout": int(openai_section.get("timeout") or 120),
        }

    return {
        "api_key": api_key,
        "base_url": base_url
        or _normalize_base_url(openai_section.get("base_url") or "https://api.openai.com/v1"),
        "model": model_name
        or str(openai_section.get("llm_model") or "gpt-4o-mini").strip(),
        "timeout": int(timeout_value or openai_section.get("timeout") or 120),
    }


def get_openai_settings() -> Dict[str, Any]:
    """兼容旧调用名：返回媒体侧配置。"""
    return get_media_settings()


def is_openai_configured() -> bool:
    """生图或 TTS 任一已配置。"""
    return bool(
        str(get_image_settings().get("api_key", "")).strip()
        or str(get_tts_settings().get("api_key", "")).strip()
    )


def is_image_configured() -> bool:
    return bool(str(get_image_settings().get("api_key", "")).strip())


def is_tts_configured() -> bool:
    return bool(str(get_tts_settings().get("api_key", "")).strip())


def is_llm_configured() -> bool:
    """LLM 是否已配置（[llm] 或回退 [openai] 有 key）。"""
    return bool(str(get_llm_settings().get("api_key", "")).strip())


def _endpoint(base_url: str, path: str) -> str:
    """将 base_url 与相对 path 安全拼接。"""
    normalized_base = base_url if base_url.endswith("/") else base_url + "/"
    return urljoin(normalized_base, path.lstrip("/"))


def _auth_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def chat_completion(
    prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None,
    max_tokens: Optional[int] = None,
    max_retries: int = 3,
) -> str:
    """
    OpenAI 兼容 Chat Completions。
    使用 [llm]（可与 [openai] 不同站点）；成功返回助手文本。
    对 502/503/504、超时自动重试（中转站常见瞬时网关超时）。
    """
    import time

    settings = get_llm_settings()
    api_key = settings["api_key"]
    if not api_key:
        logger.error("LLM api_key is not set ([llm] / [openai])")
        return ""

    model_name = model or settings["model"]
    url = _endpoint(settings["base_url"], "chat/completions")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }
    # 限制输出长度，降低长推理导致上游 504 的概率
    token_limit = max_tokens if max_tokens is not None else 2048
    if token_limit > 0:
        payload["max_tokens"] = int(token_limit)

    retryable_status_codes = {408, 429, 500, 502, 503, 504}
    last_error = ""

    for attempt in range(1, max(1, max_retries) + 1):
        try:
            logger.info(
                f"Calling OpenAI-compatible LLM: model={model_name}, "
                f"url={url}, try={attempt}/{max_retries}"
            )
            response = requests.post(
                url,
                json=payload,
                headers=_auth_headers(api_key),
                timeout=settings["timeout"],
            )
            if response.status_code != 200:
                last_error = (
                    f"{response.status_code} {response.text[:200]}"
                )
                logger.warning(
                    f"OpenAI-compatible LLM failed: {last_error}"
                )
                if (
                    response.status_code in retryable_status_codes
                    and attempt < max_retries
                ):
                    sleep_seconds = min(8, 1.5 * attempt)
                    logger.info(
                        f"LLM retryable status, sleep {sleep_seconds:.1f}s "
                        f"then retry"
                    )
                    time.sleep(sleep_seconds)
                    continue
                return ""

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                last_error = f"empty choices: {str(data)[:200]}"
                logger.warning(f"OpenAI-compatible LLM {last_error}")
                if attempt < max_retries:
                    time.sleep(min(8, 1.5 * attempt))
                    continue
                return ""

            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text") or "")
                content = "".join(text_parts)

            content = (content or "").strip()
            reasoning_content = message.get("reasoning_content") or ""
            reasoning_length = (
                len(reasoning_content)
                if isinstance(reasoning_content, str)
                else 0
            )
            if not content:
                # reasoning_content 是模型的内部推理，绝不能作为业务结果使用。
                # 否则播客会把推理文字误当作脚本，造成与原文完全无关的成片。
                last_error = (
                    "empty final content "
                    f"(reasoning_content={reasoning_length} chars)"
                )
                logger.warning(f"OpenAI-compatible LLM {last_error}")
                if attempt < max_retries:
                    time.sleep(min(8, 1.5 * attempt))
                    continue
                return ""

            logger.info(
                "OpenAI-compatible LLM OK "
                f"(content={len(content)} chars, reasoning={reasoning_length} chars, "
                f"try={attempt})"
            )
            return content
        except requests.exceptions.Timeout as error:
            last_error = f"timeout: {error}"
            logger.warning(f"OpenAI-compatible LLM {last_error}")
            if attempt < max_retries:
                time.sleep(min(8, 1.5 * attempt))
                continue
            return ""
        except Exception as error:
            last_error = str(error)
            logger.warning(f"OpenAI-compatible LLM error: {error}")
            if attempt < max_retries:
                time.sleep(min(8, 1.5 * attempt))
                continue
            return ""

    if last_error:
        logger.warning(f"OpenAI-compatible LLM gave up: {last_error}")
    return ""


def generate_image(
    prompt: str,
    output_path: str,
    *,
    model: Optional[str] = None,
    size: Optional[str] = None,
) -> str:
    """
    OpenAI 兼容 Images Generations。
    支持响应中的 url 或 b64_json；成功返回本地文件路径。
    """
    settings = get_image_settings()
    api_key = settings["api_key"]
    if not api_key:
        logger.error("Image api_key is not set ([image] / [openai])")
        return ""

    model_name = model or settings["image_model"]
    image_size = size or settings["image_size"]
    url = _endpoint(settings["base_url"], "images/generations")

    payload = {
        "model": model_name,
        "prompt": prompt,
        "n": 1,
        "size": image_size,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    try:
        logger.info(
            f"Calling OpenAI-compatible image: model={model_name}, "
            f"size={image_size}, url={url}"
        )
        response = requests.post(
            url,
            json=payload,
            headers=_auth_headers(api_key),
            timeout=settings["timeout"],
        )
        if response.status_code != 200:
            logger.warning(
                f"OpenAI-compatible image failed: "
                f"{response.status_code} {response.text[:300]}"
            )
            return ""

        data = response.json()
        image_items = data.get("data") or []
        if not image_items:
            # 部分中转站把结果放在 images 字段
            image_items = data.get("images") or []
        if not image_items:
            logger.warning(f"OpenAI-compatible image empty data: {data}")
            return ""

        first_item = image_items[0] or {}
        if not _save_image_item(first_item, output_path):
            return ""

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"OpenAI-compatible image saved: {output_path}")
            return output_path

        logger.warning("OpenAI-compatible image file empty after save")
        return ""
    except Exception as error:
        logger.error(f"OpenAI-compatible image error: {error}")
        return ""


def _save_image_item(image_item: Dict[str, Any], output_path: str) -> bool:
    """从单条 image 结果写入本地文件（url 或 b64_json）。"""
    # 标准 OpenAI: b64_json
    b64_payload = image_item.get("b64_json") or image_item.get("b64")
    if b64_payload:
        try:
            with open(output_path, "wb") as file_handle:
                file_handle.write(base64.b64decode(b64_payload))
            return True
        except Exception as error:
            logger.error(f"Failed to decode b64 image: {error}")
            return False

    # 标准 OpenAI: url（也可能是 list）
    image_url = image_item.get("url") or image_item.get("image_url")
    if isinstance(image_url, list) and image_url:
        image_url = image_url[0]
    if not image_url and isinstance(image_item.get("image"), str):
        image_url = image_item.get("image")

    if not image_url:
        logger.warning(f"No image url/b64 in item: {image_item}")
        return False

    try:
        image_response = requests.get(image_url, timeout=60)
        if image_response.status_code != 200:
            logger.warning(
                f"Download image failed: {image_response.status_code}"
            )
            return False
        with open(output_path, "wb") as file_handle:
            file_handle.write(image_response.content)
        return True
    except Exception as error:
        logger.error(f"Download image error: {error}")
        return False


def text_to_speech(
    text: str,
    voice_file: str,
    *,
    model: Optional[str] = None,
    voice: Optional[str] = None,
    speed: float = 1.0,
) -> bool:
    """
    TTS 统一入口：
      - provider=gemini → Gemini generateContent（AUDIO）
      - provider=openai → OpenAI /audio/speech
    """
    settings = get_tts_settings()
    api_key = settings["api_key"]
    if not api_key:
        logger.error("TTS api_key is not set ([tts] / [openai])")
        return False

    model_name = model or settings["tts_model"]
    voice_name = voice or settings["tts_voice"]
    provider = settings["provider"]

    os.makedirs(os.path.dirname(voice_file) or ".", exist_ok=True)

    if provider == "gemini" or "gemini" in model_name.lower():
        return _gemini_text_to_speech(
            text=text,
            voice_file=voice_file,
            api_key=api_key,
            base_url=settings["base_url"],
            model_name=model_name,
            voice_name=voice_name,
            timeout=settings["timeout"],
        )

    return _openai_text_to_speech(
        text=text,
        voice_file=voice_file,
        api_key=api_key,
        base_url=settings["base_url"],
        model_name=model_name,
        voice_name=voice_name,
        speed=speed,
        timeout=settings["timeout"],
    )


def _openai_text_to_speech(
    text: str,
    voice_file: str,
    *,
    api_key: str,
    base_url: str,
    model_name: str,
    voice_name: str,
    speed: float,
    timeout: int,
) -> bool:
    """OpenAI 兼容 /audio/speech。"""
    clamped_speed = max(0.25, min(4.0, float(speed or 1.0)))
    url = _endpoint(base_url, "audio/speech")
    payload = {
        "model": model_name,
        "input": text.strip(),
        "voice": voice_name,
        "speed": clamped_speed,
        "response_format": "mp3",
    }

    for attempt in range(3):
        try:
            logger.info(
                f"OpenAI-compatible TTS: model={model_name}, "
                f"voice={voice_name}, try={attempt + 1}, url={url}"
            )
            response = requests.post(
                url,
                json=payload,
                headers=_auth_headers(api_key),
                timeout=timeout,
            )
            if response.status_code != 200:
                logger.error(
                    f"OpenAI-compatible TTS failed: "
                    f"{response.status_code} {response.text[:300]}"
                )
                continue

            content_type = (response.headers.get("Content-Type") or "").lower()
            if "application/json" in content_type:
                logger.error(
                    f"OpenAI-compatible TTS returned JSON error: "
                    f"{response.text[:300]}"
                )
                continue

            if not response.content:
                logger.error("OpenAI-compatible TTS empty audio body")
                continue

            with open(voice_file, "wb") as file_handle:
                file_handle.write(response.content)

            if os.path.exists(voice_file) and os.path.getsize(voice_file) > 0:
                logger.success(f"OpenAI-compatible TTS succeeded: {voice_file}")
                return True
        except Exception as error:
            logger.error(f"OpenAI-compatible TTS exception: {error}")

    return False


def _gemini_tts_root_url(base_url: str) -> str:
    """
    从配置 base_url 推出 Gemini 根地址。
    支持：
      https://build2api.wanyan.de
      https://build2api.wanyan.de/v1
      https://build2api.wanyan.de/v1beta
    """
    cleaned = _normalize_base_url(base_url)
    for suffix in ("/v1beta", "/v1"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned.rstrip("/")


def _parse_l16_mime(mime_type: str) -> Tuple[int, int]:
    """解析 audio/l16; rate=24000; channels=1 → (sample_rate, channels)。"""
    sample_rate = 24000
    channels = 1
    for part in (mime_type or "").split(";"):
        piece = part.strip().lower()
        if piece.startswith("rate="):
            try:
                sample_rate = int(piece.split("=", 1)[1])
            except ValueError:
                pass
        if piece.startswith("channels="):
            try:
                channels = int(piece.split("=", 1)[1])
            except ValueError:
                pass
    return sample_rate, channels


def _pcm_l16_to_mp3(
    pcm_bytes: bytes,
    output_mp3_path: str,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
) -> bool:
    """把 Gemini 返回的 L16 PCM 转成 mp3（依赖本机 ffmpeg）。"""
    import subprocess
    import tempfile

    if not pcm_bytes:
        return False

    raw_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as raw_file:
            raw_file.write(pcm_bytes)
            raw_path = raw_file.name

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-i",
            raw_path,
            "-c:a",
            "libmp3lame",
            # 所有片段规范成同一格式，才能与插入的静音安全拼接。
            "-ar",
            "44100",
            "-ac",
            "2",
            "-q:a",
            "2",
            output_mp3_path,
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            logger.error(
                f"ffmpeg pcm->mp3 failed: {completed.stderr[-400:]}"
            )
            return False
        if not (
            os.path.exists(output_mp3_path)
            and os.path.getsize(output_mp3_path) > 0
        ):
            return False

        probe_command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,duration",
            "-of",
            "default=noprint_wrappers=1",
            output_mp3_path,
        ]
        probe_result = subprocess.run(
            probe_command,
            capture_output=True,
            text=True,
            check=False,
        )
        if probe_result.returncode != 0 or "codec_name=mp3" not in probe_result.stdout:
            logger.error(
                f"Generated Gemini audio failed validation: {probe_result.stderr[-300:]}"
            )
            return False

        logger.info(
            "Normalized Gemini audio: "
            f"source={sample_rate}Hz/{channels}ch, output=44100Hz/2ch"
        )
        return True
    except Exception as error:
        logger.error(f"pcm->mp3 convert error: {error}")
        return False
    finally:
        if raw_path and os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except OSError:
                pass


def _extract_gemini_inline_audio(response_data: Dict[str, Any]) -> Tuple[bytes, str]:
    """从 Gemini generateContent 响应中提取 inlineData 音频。"""
    candidates = response_data.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data") or {}
            encoded = inline_data.get("data") or ""
            mime_type = (
                inline_data.get("mimeType")
                or inline_data.get("mime_type")
                or "audio/l16;rate=24000"
            )
            if encoded:
                try:
                    return base64.b64decode(encoded), mime_type
                except Exception as error:
                    logger.error(f"decode gemini audio failed: {error}")
    return b"", ""


def _gemini_text_to_speech(
    text: str,
    voice_file: str,
    *,
    api_key: str,
    base_url: str,
    model_name: str,
    voice_name: str,
    timeout: int,
) -> bool:
    """
    Gemini TTS：POST {root}/v1beta/models/{model}:generateContent
    返回 audio/l16 PCM，再转 mp3。
    """
    root_url = _gemini_tts_root_url(base_url)
    url = f"{root_url}/v1beta/models/{model_name}:generateContent"
    # Gemini 预置音色名：Kore / Puck / Charon / Fenrir / Aoede ...
    resolved_voice = (voice_name or "Kore").strip()
    # 去掉可能的 gemini: 前缀与性别后缀
    if resolved_voice.lower().startswith("gemini:"):
        resolved_voice = resolved_voice.split(":", 1)[-1]
    resolved_voice = resolved_voice.split("-")[0].strip() or "Kore"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": text.strip()}],
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": resolved_voice,
                    }
                }
            },
        },
    }

    for attempt in range(3):
        try:
            logger.info(
                f"Gemini TTS: model={model_name}, voice={resolved_voice}, "
                f"try={attempt + 1}, url={url}"
            )
            response = requests.post(
                url,
                json=payload,
                headers=_auth_headers(api_key),
                timeout=timeout,
            )
            if response.status_code != 200:
                logger.error(
                    f"Gemini TTS failed: "
                    f"{response.status_code} {response.text[:400]}"
                )
                continue

            response_data = response.json()
            pcm_bytes, mime_type = _extract_gemini_inline_audio(response_data)
            if not pcm_bytes:
                logger.error(
                    f"Gemini TTS empty audio in response: "
                    f"{str(response_data)[:300]}"
                )
                continue

            sample_rate, channels = _parse_l16_mime(mime_type)
            # 若已是 mp3/wav 等，直接落盘
            lower_mime = (mime_type or "").lower()
            if "mpeg" in lower_mime or "mp3" in lower_mime:
                with open(voice_file, "wb") as file_handle:
                    file_handle.write(pcm_bytes)
                logger.success(f"Gemini TTS succeeded (mp3): {voice_file}")
                return True

            if _pcm_l16_to_mp3(
                pcm_bytes,
                voice_file,
                sample_rate=sample_rate,
                channels=channels,
            ):
                logger.success(f"Gemini TTS succeeded: {voice_file}")
                return True
        except Exception as error:
            logger.error(f"Gemini TTS exception: {error}")

    return False


def parse_openai_voice_name(voice_name: str) -> Tuple[str, str]:
    """
    解析音色字符串，支持：
      - openai:alloy
      - openai:tts-1:alloy
      - openai:tts-1-hd:nova
      - gemini:Kore
      - gemini:gemini-3.1-flash-tts-preview:Kore
    返回 (model, voice_id)。
    """
    settings = get_tts_settings()
    default_voice = settings["tts_voice"]
    default_model = settings["tts_model"]

    raw = (voice_name or "").strip()
    if not raw:
        return default_model, default_voice

    lower_raw = raw.lower()
    for prefix in ("openai:", "openai_", "gemini:", "gemini_"):
        if lower_raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break

    parts = [part for part in raw.split(":") if part]
    if not parts:
        return default_model, default_voice
    if len(parts) == 1:
        # 仅音色名（如 Kore / alloy）
        return default_model, parts[0].split("-")[0]
    # model:voice
    return parts[0], parts[1].split("-")[0]
