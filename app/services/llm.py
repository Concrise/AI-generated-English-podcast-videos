"""
LLM 服务 - 简化版
仅支持 SiliconFlow OpenAI 兼容接口
参考文档: https://api-docs.siliconflow.cn/docs/api/chat-completions-post
"""
import json
import re
from typing import List

from loguru import logger
from openai import OpenAI

from app.config import config
from app.models.schema import PodcastScript


def _generate_response(prompt: str) -> str:
    """
    使用 SiliconFlow OpenAI 兼容 API 生成响应
    支持多模型重试机制
    """
    api_key = config.siliconflow.get("api_key", "")
    if not api_key:
        logger.error("SiliconFlow API key is not set")
        return ""

    # SiliconFlow OpenAI 兼容端点
    base_url = "https://api.siliconflow.cn/v1"
    
    # 根据文档，可用的聊天模型列表（按优先级排序）
    models = [
        "deepseek-ai/DeepSeek-V4-Pro",
        "deepseek-ai/DeepSeek-V3.2",
        "Qwen/Qwen3-8B",
    ]

    for model_name in models:
        try:
            logger.info(f"Trying model: {model_name}")
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2048
            )
            content = response.choices[0].message.content
            logger.debug(f"LLM response received: {content[:100]}...")
            return content

        except Exception as e:
            logger.warning(f"Model {model_name} failed: {str(e)}")
            continue

    logger.error("All models failed")
    return f"Error: All models failed"


def generate_podcast_script(article_text: str, language: str = "English") -> List[PodcastScript]:
    """
    生成播客脚本
    """
    logger.info(f"generating podcast script, language: {language}")

    prompt = f"""
    Create a podcast-style dialogue script based on the following article.
    
    Article:
    {article_text}
    
    Requirements:
    - Generate {language} dialogue between two speakers (Speaker 1 and Speaker 2)
    - Each speaker should have natural, conversational responses
    - Include 5-8 dialogue turns
    - Keep responses relatively short (2-3 sentences each)
    - Focus on the main topics from the article
    
    Output format (JSON array):
    [
        {{
            "speaker_1": "...",
            "speaker_2": "..."
        }},
        ...
    ]
    """

    response = _generate_response(prompt)
    
    try:
        # 尝试解析 JSON
        script_data = json.loads(response)
        result = []
        for item in script_data:
            script = PodcastScript(
                speaker_1=item.get("speaker_1", "").strip(),
                speaker_2=item.get("speaker_2", "").strip(),
                speaker_1_voice="",
                speaker_2_voice=""
            )
            result.append(script)
        return result
    except json.JSONDecodeError:
        # 如果 JSON 解析失败，尝试从文本中提取对话
        logger.warning("Failed to parse JSON response, falling back to text parsing")
        return _parse_dialogue_from_text(response)


def _parse_dialogue_from_text(text: str) -> List[PodcastScript]:
    """
    从文本中解析对话
    """
    result = []
    lines = text.split('\n')
    
    current_script = None
    for line in lines:
        line = line.strip()
        if line.startswith("Speaker 1:") or line.startswith("A:"):
            if current_script:
                result.append(current_script)
            speaker_1 = line.replace("Speaker 1:", "").replace("A:", "").strip()
            current_script = PodcastScript(
                speaker_1=speaker_1,
                speaker_2="",
                speaker_1_voice="",
                speaker_2_voice=""
            )
        elif line.startswith("Speaker 2:") or line.startswith("B:"):
            if current_script:
                current_script.speaker_2 = line.replace("Speaker 2:", "").replace("B:", "").strip()
    
    if current_script and (current_script.speaker_1 or current_script.speaker_2):
        result.append(current_script)
    
    return result


def generate_terms_from_podcast(podcast_script: List[PodcastScript], amount: int = 5) -> List[str]:
    """
    从播客脚本中提取关键词
    """
    logger.info("extracting keywords from podcast script")

    # 收集所有文本
    all_text = ""
    for script in podcast_script:
        all_text += " " + script.speaker_1
        all_text += " " + script.speaker_2

    prompt = f"""
    Extract {amount} key topics/keywords from the following podcast dialogue.
    
    Dialogue:
    {all_text}
    
    Output only the keywords as a comma-separated list, no extra text.
    """

    response = _generate_response(prompt)
    
    # 解析关键词
    terms = [t.strip() for t in response.split(',')]
    terms = [t for t in terms if t and len(t) > 2]
    
    return terms[:amount]


def generate_corrected_subtitle(subtitle_text: str, video_script: str) -> str:
    """
    校正字幕
    """
    logger.info("correcting subtitle")
    
    prompt = f"""
    Correct the following subtitle to match the video script better.
    
    Video Script:
    {video_script}
    
    Original Subtitle:
    {subtitle_text}
    
    Output the corrected subtitle in the same format.
    """
    
    return _generate_response(prompt)


# 测试函数
if __name__ == "__main__":
    test_text = "Artificial intelligence is transforming the world. Machine learning algorithms can analyze large amounts of data and make predictions. AI is being used in healthcare, finance, and many other industries."
    script = generate_podcast_script(test_text)
    print("Generated podcast script:")
    for i, turn in enumerate(script):
        print(f"\nTurn {i+1}:")
        print(f"  Speaker 1: {turn.speaker_1}")
        print(f"  Speaker 2: {turn.speaker_2}")
    
    terms = generate_terms_from_podcast(script)
    print(f"\nExtracted keywords: {terms}")
