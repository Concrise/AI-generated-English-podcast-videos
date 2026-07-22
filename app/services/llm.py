"""
LLM 服务
优先使用 OpenAI 兼容第三方网关；未配置时回退 MiniMax。
"""
import json
import re
from typing import List

from loguru import logger
import requests

from app.config import config
from app.models.schema import PodcastScript
from app.services.openai_compat import chat_completion, is_llm_configured


def _generate_response(
    prompt: str,
    max_tokens: int = 768,
    temperature: float = 0.7,
) -> str:
    """
    生成 LLM 响应：
    1) 若配置了 [llm]（或回退 [openai]），走 OpenAI 兼容 /chat/completions
    2) 否则回退 MiniMax 原生接口
    """
    # 1) OpenAI 兼容第三方（[llm] 可与生图/TTS 的 [openai] 分站点）
    if is_llm_configured():
        content = chat_completion(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if content:
            return content
        logger.warning("OpenAI-compatible LLM failed, trying MiniMax fallback")

    # 2) MiniMax 原生
    MiniMax_key = config.MiniMax.get("api_key", "")
    if MiniMax_key:
        # 优先使用配置中的 base_url，兼容旧硬编码路径
        base_url = str(
            config.MiniMax.get("base_url") or "https://api.minimaxi.com/v1"
        ).rstrip("/")
        # MiniMax 官方路径是 text/chatcompletion_v2；若 base_url 已是兼容网关则走 chat/completions
        if "minimaxi.com" in base_url:
            url = f"{base_url}/text/chatcompletion_v2"
        else:
            url = f"{base_url}/chat/completions"
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
                # MiniMax 在配额/错误时可能返回 "choices": null，必须先判空再取下标，
                # 否则 None[0] 会抛 TypeError: 'NoneType' object is not subscriptable
                choices = data.get("choices") or []
                if not choices:
                    # 记录 MiniMax 的错误信息（如有 base_resp）
                    base_resp = data.get("base_resp") or {}
                    status_msg = base_resp.get("status_msg") or base_resp.get("status_code")
                    logger.warning(f"MiniMax LLM empty choices: {status_msg or data}")
                else:
                    message = choices[0].get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        logger.info(f"MiniMax LLM OK ({len(content)} chars)")
                        return content
                    else:
                        logger.warning(f"MiniMax LLM empty content: {data}")
            else:
                logger.warning(f"MiniMax LLM failed: {r.status_code} {r.text[:200]}")
        except Exception as e:
            logger.warning(f"MiniMax LLM error: {str(e)}")

    logger.error("LLM failed (no provider available)")
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
    
    # 文章过长时截断，避免中转站 504（Cloudflare 约 60–100s）
    article_for_prompt = article_text.strip()
    max_article_chars = 6000
    if len(article_for_prompt) > max_article_chars:
        logger.warning(
            f"Article too long ({len(article_for_prompt)} chars), "
            f"truncating to {max_article_chars} for LLM"
        )
        article_for_prompt = article_for_prompt[:max_article_chars] + "\n...(truncated)"

    prompt = f"""You create a faithful educational podcast dialogue.
Output ONLY a valid JSON array. Do not output analysis, reasoning, markdown, or any text outside the JSON array.

The SOURCE ARTICLE below is the only factual source. The dialogue must be about this exact article, not a generic topic.

<source_article>
{article_for_prompt}
</source_article>

Create exactly {dialogue_turns} turns of a {language} dialogue between two people.

Grounding rules:
- Every turn must explain, question, or clarify a fact explicitly present in the source article.
- Preserve the article's specific people, places, events, objects, numbers, and key terms when they exist.
- Do not introduce unrelated topics, invented examples, new events, or facts absent from the source article.
- Do not replace the article's topic with a generic English-learning, culture, school-life, or lifestyle conversation.
- Cover the article's central facts across the dialogue.
- speaker_1 opens or asks; speaker_2 responds directly.
- Use one concise sentence per speaker so each utterance can be represented by one video scene.
{diff_req}

Respond with exactly {dialogue_turns} objects in this schema:
[
  {{"speaker_1": "faithful question or explanation", "speaker_2": "faithful response"}}
]
"""

    # DeepSeek 网关可能先生成一段推理内容，再输出最终 JSON。
    # 600 tokens 对两轮对话不足，模型会在 JSON 之前被截断。保留至少
    # 2048 tokens，且给较长对话更多空间，同时用上限控制网关超时风险。
    script_token_limit = min(4096, max(2600, dialogue_turns * 450))
    response = _generate_response(
        prompt,
        max_tokens=script_token_limit,
        temperature=0.2,
    )

    if not response or not response.strip():
        logger.error("LLM returned empty response, cannot generate podcast script")
        return []

    result = _parse_podcast_json(response)
    if result and _has_source_term_overlap(article_for_prompt, result):
        return result

    # 某些 DeepSeek 中转会先输出推理/说明文字。重新请求一次，明确要求极短回答，
    # 避免把无关文本误判为可用播客脚本。
    logger.warning(
        "LLM response was not a valid podcast JSON; requesting a concise retry"
    )
    retry_prompt = (
        prompt
        + "\nIMPORTANT: Start your response with `[` and return only the JSON array. "
        "Do not include analysis, reasoning, or markdown. Every speaker sentence must "
        "reuse at least one concrete noun, named entity, number, or key term from the "
        "source article."
    )
    retry_response = _generate_response(
        retry_prompt,
        max_tokens=script_token_limit,
        temperature=0.0,
    )
    result = _parse_podcast_json(retry_response)
    if result and _has_source_term_overlap(article_for_prompt, result):
        return result

    logger.error(
        "Podcast response failed source-grounding validation; refusing to create "
        "an unrelated video"
    )
    return []


def _strip_code_fences(text: str) -> str:
    """去除 markdown 代码围栏，返回纯 JSON 文本"""
    s = text.strip()
    # 去除开头的 ```json 或 ```
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1:]
        else:
            s = s[3:]
    # 去除结尾的 ```
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def _parse_podcast_json(response: str) -> List[PodcastScript]:
    """从模型输出中提取 JSON 数组，兼容前后包含说明文字或代码围栏的情况。"""
    cleaned = _strip_code_fences(response)
    decoder = json.JSONDecoder()

    # 模型有时在 JSON 前增加一句说明；逐个尝试数组起始位置。
    for start_index, character in enumerate(cleaned):
        if character != "[":
            continue
        try:
            script_data, _ = decoder.raw_decode(cleaned[start_index:])
        except json.JSONDecodeError:
            continue

        if not isinstance(script_data, list):
            continue

        result = []
        for item in script_data:
            if not isinstance(item, dict):
                continue
            speaker_1 = str(item.get("speaker_1") or "").strip()
            speaker_2 = str(item.get("speaker_2") or "").strip()
            if speaker_1 or speaker_2:
                result.append(
                    PodcastScript(
                        speaker_1=speaker_1,
                        speaker_2=speaker_2,
                        speaker_1_voice="",
                        speaker_2_voice="",
                    )
                )
        if result:
            return result

    return []


def _has_source_term_overlap(
    article_text: str,
    podcast_script: List[PodcastScript],
) -> bool:
    """拒绝与原文没有任何实质词汇关联的模型输出。"""
    ignored_words = {
        "about", "after", "also", "because", "before", "between", "could",
        "every", "first", "from", "have", "into", "just", "more", "most",
        "only", "other", "should", "their", "there", "these", "they", "this",
        "what", "when", "where", "which", "with", "would", "your",
    }
    source_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", article_text)
        if term.lower() not in ignored_words
    }
    dialogue_text = " ".join(
        f"{turn.speaker_1} {turn.speaker_2}" for turn in podcast_script
    )
    dialogue_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", dialogue_text)
    }
    matched_terms = source_terms & dialogue_terms
    logger.info(
        f"Podcast source-grounding: {len(matched_terms)} shared terms "
        f"({', '.join(sorted(matched_terms)[:8])})"
    )
    return len(matched_terms) >= 2



def _parse_dialogue_from_text(text: str) -> List[PodcastScript]:
    """
    从文本中解析对话。兼容两种格式：
    1. 换行分隔：每行 "Speaker 1:" / "Speaker 2:" 开头
    2. 内联连续：同一行内多次出现 "Speaker 1:" / "Speaker 2:"（M2-her 模型常见）
    用正则把所有说话人片段提取出来，再按 S1->S2 配对成 PodcastScript。
    """
    if not text:
        return []

    # 正则匹配 "Speaker 1:" 或 "A:" 或 "Speaker 2:" 或 "B:" 标记
    # 命名分组：speaker=1或A 视为说话人1，speaker=2或B 视为说话人2
    pattern = re.compile(
        r'(?:Speaker\s*([12])\s*:|([AB])\s*:)',
        re.IGNORECASE,
    )

    # 找到所有标记位置，提取每段文本
    matches = list(pattern.finditer(text))
    if not matches:
        logger.warning("no speaker markers found in text")
        return []

    segments = []  # [(who, content), ...]  who=1 or 2
    for i, m in enumerate(matches):
        # 判断说话人
        if m.group(1):
            who = int(m.group(1))
        else:
            who = 1 if m.group(2).upper() == "A" else 2
        # 内容 = 从本标记后到下一标记前
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        # 清理多余空白和舞台指示
        content = re.sub(r'\s+', ' ', content).strip()
        if content:
            segments.append((who, content))

    # 按 (说话人1, 说话人2) 配对
    result = []
    current = None
    for who, content in segments:
        if who == 1:
            if current and (current.speaker_1 or current.speaker_2):
                result.append(current)
            current = PodcastScript(
                speaker_1=content,
                speaker_2="",
                speaker_1_voice="",
                speaker_2_voice="",
            )
        else:  # who == 2
            if current is None:
                # 没有前置的 speaker1，创建一个空的
                current = PodcastScript(
                    speaker_1="",
                    speaker_2=content,
                    speaker_1_voice="",
                    speaker_2_voice="",
                )
            else:
                current.speaker_2 = content
    if current and (current.speaker_1 or current.speaker_2):
        result.append(current)

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
