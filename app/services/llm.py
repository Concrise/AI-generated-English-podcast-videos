"""
LLM 服务
支持 MiniMax (主要) 和 SiliconFlow (备选)
参考文档: https://platform.minimaxi.com/document/ChatCompletion
"""
import json
import re
from typing import List

from loguru import logger
import requests

from app.config import config
from app.models.schema import PodcastScript


def _generate_response(prompt: str) -> str:
    """
    使用 MiniMax API 生成响应 (主要)
    SiliconFlow 作为备选
    """
    # 优先使用 MiniMax
    MiniMax_key = config.MiniMax.get("api_key", "")
    if MiniMax_key:
        url = "https://api.minimaxi.com/v1/text/chatcompletion_v2"
        model = config.MiniMax.get("llm_model", "M2-her")
        headers = {
            "Authorization": f"Bearer {MiniMax_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }
        try:
            logger.info(f"Calling MiniMax LLM: {model}")
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            if r.status_code == 200:
                data = r.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    logger.info(f"MiniMax LLM OK ({len(content)} chars)")
                    return content
                else:
                    logger.warning(f"MiniMax LLM empty content: {data}")
            else:
                logger.warning(f"MiniMax LLM failed: {r.status_code} {r.text[:200]}")
        except Exception as e:
            logger.warning(f"MiniMax LLM error: {str(e)}")

    # Fallback to SiliconFlow
    sf_key = config.siliconflow.get("api_key", "")
    if sf_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=sf_key, base_url="https://api.siliconflow.cn/v1")
            for model_name in ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-7B-Instruct"]:
                try:
                    logger.info(f"Fallback to SiliconFlow: {model_name}")
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        max_tokens=2048
                    )
                    content = response.choices[0].message.content
                    if content:
                        return content
                except Exception as e:
                    logger.warning(f"SiliconFlow {model_name} failed: {e}")
                    continue
        except Exception as e:
            logger.warning(f"SiliconFlow client error: {e}")

    logger.error("All LLM providers failed")
    return ""


def generate_podcast_script(article_text: str, language: str = "English", dialogue_turns: int = 5, difficulty: str = "middle") -> List[PodcastScript]:
    """
    生成播客脚本
    dialogue_turns: 对话轮数（默认5轮）
    difficulty: 难度级别 - elementary(小学), middle(初中), high(高中)
    """
    logger.info(f"generating podcast script, language: {language}, turns: {dialogue_turns}, difficulty: {difficulty}")
    
    # 根据难度设置词汇和句式要求
    difficulty_requirements = {
        "elementary": """
        - Use simple vocabulary (basic words like: happy, sad, big, small, go, eat, play)
        - Short sentences (5-8 words each)
        - Simple grammar structures (present tense, basic questions)
        - Avoid complex idioms or phrasal verbs
        - Focus on everyday topics familiar to children
        """,
        "middle": """
        - Use intermediate vocabulary (words like: exciting, celebrate, tradition, festival, race)
        - Medium-length sentences (8-15 words each)
        - Include some compound sentences and basic idioms
        - Use present, past, and future tenses appropriately
        - Cover topics about culture, school life, hobbies
        """,
        "high": """
        - Use advanced vocabulary (words like: commemorate, heritage, synchronize, rhythmic, paddle)
        - Longer sentences with complex structures (15-25 words)
        - Include idioms, phrasal verbs, and figurative language
        - Use various tenses and conditional structures
        - Discuss abstract concepts, history, cultural significance
        """,
        "university": """
        - Use sophisticated vocabulary (words like: indigenous, paradigm, sociocultural, anthropological, discourse)
        - Complex sentences with academic structures (20-35 words)
        - Include scholarly expressions, technical terms, and nuanced language
        - Use sophisticated rhetorical devices and argumentative structures
        - Discuss theoretical frameworks, research perspectives, critical analysis
        - Include references to academic concepts, historical contexts, cultural studies
        """
    }
    
    difficulty_desc = {
        "elementary": "小学水平（简单词汇和短句）",
        "middle": "初中水平（中等词汇和句式）",
        "high": "高中水平（高级词汇和复杂句式）",
        "university": "大学水平（学术词汇和专业表达）"
    }
    
    diff_req = difficulty_requirements.get(difficulty, difficulty_requirements["middle"])
    
    prompt = f"""
    Create a podcast-style dialogue script based on the following article.
    
    Article:
    {article_text}
    
    Requirements:
    - Generate {language} dialogue between two speakers (Speaker 1 and Speaker 2)
    - Each speaker should have natural, conversational responses
    - Include exactly {dialogue_turns} dialogue turns
    - Keep responses relatively short (2-3 sentences each)
    - Focus on the main topics from the article
    
    Difficulty Level: {difficulty_desc.get(difficulty, "初中水平")}
    {diff_req}
    
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
    从播客脚本中提取全局关键词（用于整体主题）
    """
    logger.info("extracting global keywords from podcast script")

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


def generate_terms_for_each_sentence(podcast_script: List[PodcastScript], amount: int = 3) -> dict:
    """
    一次性为每个对话句子提取关键词
    返回: {sentence_index: [keywords]}
    """
    logger.info("extracting keywords for each sentence in one call")

    # 构建带索引的对话文本
    sentences = []
    sentence_index = 0
    for script in podcast_script:
        if script.speaker_1:
            sentences.append(f"[{sentence_index}] Speaker 1: {script.speaker_1}")
            sentence_index += 1
        if script.speaker_2:
            sentences.append(f"[{sentence_index}] Speaker 2: {script.speaker_2}")
            sentence_index += 1

    sentences_text = "\n".join(sentences)

    prompt = f"""
    For each sentence below, extract {amount} keywords that are most relevant to that specific sentence.
    
    Sentences:
    {sentences_text}
    
    Output format (JSON):
    {{
        "0": ["keyword1", "keyword2", "keyword3"],
        "1": ["keyword1", "keyword2", "keyword3"],
        ...
    }}
    
    Output only the JSON, no extra text.
    """

    response = _generate_response(prompt)
    
    # 解析 JSON
    try:
        # 清理响应中的多余内容
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        import json
        keywords_dict = json.loads(response)
        
        # 确保所有索引都有关键词
        result = {}
        for i in range(sentence_index):
            key = str(i)
            if key in keywords_dict:
                result[i] = keywords_dict[key][:amount]
            else:
                result[i] = []
        
        return result
    except Exception as e:
        logger.warning(f"Failed to parse keywords JSON: {e}, using fallback")
        # 回退：使用全局关键词
        global_terms = generate_terms_from_podcast(podcast_script, amount)
        return {i: global_terms for i in range(sentence_index)}


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
