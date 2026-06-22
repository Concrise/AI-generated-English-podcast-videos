import json
import re
from typing import List

import requests
from loguru import logger
from openai import AzureOpenAI, OpenAI

from app.config import config
from app.models.schema import PodcastScript

_max_retries = 5


def _generate_response(prompt: str) -> str:
    try:
        content = ""
        llm_provider = config.app.get("llm_provider", "openai")
        logger.info(f"llm provider: {llm_provider}")
        
        api_version = ""  # for azure
        if llm_provider == "moonshot":
            api_key = config.app.get("moonshot_api_key")
            model_name = config.app.get("moonshot_model_name")
            base_url = "https://api.moonshot.cn/v1"
        elif llm_provider == "ollama":
            # api_key = config.app.get("openai_api_key")
            api_key = "ollama"  # any string works but you are required to have one
            model_name = config.app.get("ollama_model_name")
            base_url = config.app.get("ollama_base_url", "")
            if not base_url:
                base_url = "http://localhost:11434/v1"
        elif llm_provider == "openai":
            api_key = config.app.get("openai_api_key")
            model_name = config.app.get("openai_model_name")
            base_url = config.app.get("openai_base_url", "")
            if not base_url:
                base_url = "https://api.openai.com/v1"
        elif llm_provider == "oneapi":
            api_key = config.app.get("oneapi_api_key")
            model_name = config.app.get("oneapi_model_name")
            base_url = config.app.get("oneapi_base_url", "")
        elif llm_provider == "azure":
            api_key = config.app.get("azure_api_key")
            model_name = config.app.get("azure_model_name")
            base_url = config.app.get("azure_base_url", "")
            api_version = config.app.get("azure_api_version", "2024-02-15-preview")
        elif llm_provider == "gemini":
            api_key = config.app.get("gemini_api_key")
            model_name = config.app.get("gemini_model_name")
            base_url = "***"
        elif llm_provider == "qwen":
            api_key = config.app.get("qwen_api_key")
            model_name = config.app.get("qwen_model_name")
            base_url = "***"
        elif llm_provider == "cloudflare":
            api_key = config.app.get("cloudflare_api_key")
            model_name = config.app.get("cloudflare_model_name")
            account_id = config.app.get("cloudflare_account_id")
            base_url = "***"
        elif llm_provider == "deepseek":
            api_key = config.app.get("deepseek_api_key")
            model_name = config.app.get("deepseek_model_name")
            base_url = config.app.get("deepseek_base_url")
            if not base_url:
                base_url = "https://api.deepseek.com"
        elif llm_provider == "ernie":
            api_key = config.app.get("ernie_api_key")
            secret_key = config.app.get("ernie_secret_key")
            base_url = config.app.get("ernie_base_url")
            model_name = "***"
            if not secret_key:
                raise ValueError(
                    f"{llm_provider}: secret_key is not set, please set it in the config.toml file."
                )
        elif llm_provider == "pollinations":
            try:
                base_url = config.app.get("pollinations_base_url", "")
                if not base_url:
                    base_url = "https://text.pollinations.ai/openai"
                model_name = config.app.get("pollinations_model_name", "openai-fast")
               
                # Prepare the payload
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "seed": 101  # Optional but helps with reproducibility
                }
                
                # Optional parameters if configured
                if config.app.get("pollinations_private"):
                    payload["private"] = True
                if config.app.get("pollinations_referrer"):
                    payload["referrer"] = config.app.get("pollinations_referrer")
                
                headers = {
                    "Content-Type": "application/json"
                }
                
                # Make the API request
                response = requests.post(base_url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                
                if result and "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    return content.replace("\n", "")
                else:
                    raise Exception(f"[{llm_provider}] returned an invalid response format")
                        
            except requests.exceptions.RequestException as e:
                raise Exception(f"[{llm_provider}] request failed: {str(e)}")
            except Exception as e:
                raise Exception(f"[{llm_provider}] error: {str(e)}")

        if llm_provider not in ["pollinations", "ollama"]:  # Skip validation for providers that don't require API key
            if not api_key:
                raise ValueError(
                    f"{llm_provider}: api_key is not set, please set it in the config.toml file."
                )
            if not model_name:
                raise ValueError(
                    f"{llm_provider}: model_name is not set, please set it in the config.toml file."
                )
            if not base_url:
                raise ValueError(
                    f"{llm_provider}: base_url is not set, please set it in the config.toml file."
                )

        if llm_provider == "qwen":
            import dashscope
            from dashscope.api_entities.dashscope_response import GenerationResponse

            dashscope.api_key = api_key
            response = dashscope.Generation.call(
                model=model_name, messages=[{"role": "user", "content": prompt}]
            )
            if response:
                if isinstance(response, GenerationResponse):
                    status_code = response.status_code
                    if status_code != 200:
                        raise Exception(
                            f'[{llm_provider}] returned an error response: "{response}"'
                        )

                    content = response["output"]["text"]
                    return content.replace("\n", "")
                else:
                    raise Exception(
                        f'[{llm_provider}] returned an invalid response: "{response}"'
                    )
            else:
                raise Exception(f"[{llm_provider}] returned an empty response")

        if llm_provider == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=api_key, transport="rest")

            generation_config = {
                "temperature": 0.5,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 2048,
            }

            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_ONLY_HIGH",
                },
            ]

            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
                safety_settings=safety_settings,
            )

            try:
                response = model.generate_content(prompt)
                candidates = response.candidates
                generated_text = candidates[0].content.parts[0].text
            except (AttributeError, IndexError) as e:
                print("Gemini Error:", e)

            return generated_text

        if llm_provider == "cloudflare":
            response = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a friendly assistant",
                        },
                        {"role": "user", "content": prompt},
                    ]
                },
            )
            result = response.json()
            logger.info(result)
            return result["result"]["response"]

        if llm_provider == "ernie":
            response = requests.post(
                "https://aip.baidubce.com/oauth/2.0/token", 
                params={
                    "grant_type": "client_credentials",
                    "client_id": api_key,
                    "client_secret": secret_key,
                }
            )
            access_token = response.json().get("access_token")
            url = f"{base_url}?access_token={access_token}"

            payload = json.dumps(
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "top_p": 0.8,
                    "penalty_score": 1,
                    "disable_search": False,
                    "enable_citation": False,
                    "response_format": "text",
                }
            )
            headers = {"Content-Type": "application/json"}

            response = requests.request(
                "POST", url, headers=headers, data=payload
            ).json()
            return response.get("result")

        if llm_provider == "azure":
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=base_url,
            )
        else:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )

        response = client.chat.completions.create(
            model=model_name, messages=[{"role": "user", "content": prompt}]
        )
        if response:
            content = response.choices[0].message.content
        else:
            raise Exception(
                f"[{llm_provider}] returned an empty response, please check your network connection and try again."
            )

        return content.replace("\n", "")
    except Exception as e:
        return f"Error: {str(e)}"


# 播客相关功能
def generate_podcast_script(article_text: str, language: str = "") -> List[PodcastScript]:
    """基于文章生成双人对话播客脚本。"""
    # 获取配置中的最大对话轮数
    max_turns = config.app.get("podcast", {}).get("max_dialogue_turns", 6)

    # 根据语言参数选择提示语言
    if language and language.lower().startswith("en"):
        # 英文提示
        prompt = f"""
# Role: Podcast Dialogue Script Generator

## Task:
Convert the following article into a natural and engaging two-person podcast dialogue with the following requirements:

1. Dialogue Design:
   - Two hosts (A and B) naturally discuss the article content
   - A tends to ask questions and guide, B tends to explain and go deeper
   - Each person's speech should be 2-4 sentences long
   - Cover the core viewpoints and key information from the article
   - Generate exactly {max_turns} rounds of dialogue

2. Language Style:
   - Conversational, natural, and fluent
   - Avoid stiff, reading-style expressions
   - Appropriately add interjections and transitional phrases
   - Maintain coherence and logical flow

3. Content Requirements:
   - Ensure all important information from the article is covered
   - The dialogue should be insightful, not just simple repetition
   - Can add relevant examples or metaphors appropriately

## Original Article:
{article_text}

## Output Format:
Strictly follow JSON format, each round of dialogue includes content from Speaker A and Speaker B:
[
  {{
    "speaker_1": "What Speaker A says...",
    "speaker_2": "What Speaker B says..."
  }},
  {{
    "speaker_1": "What Speaker A says...",
    "speaker_2": "What Speaker B says..."
  }}
]

Note:
- Output must be valid JSON format
- Do not add any other explanatory text
- Ensure the dialogue is natural and fits podcast style
"""
    else:
        # 中文提示（默认）
        prompt = f"""
# Role: 播客对话脚本生成器

## 任务：
将以下文章转换成自然有趣的双人播客对话，要求：

1. 对话设计：
   - 两个主持人（A和B）自然讨论文章内容
   - A偏向提问和引导，B偏向解释和深入
   - 每人发言控制在2-4句话内
   - 对话要覆盖文章的核心观点和关键信息
   - 生成恰好{max_turns}轮对话

2. 语言风格：
   - 口语化、自然流畅
   - 避免生硬的朗读式表达
   - 适当加入感叹词和过渡语
   - 保持对话的连贯性和逻辑性

3. 内容要求：
   - 确保涵盖文章的所有重要信息
   - 对话要有启发性，不仅仅是简单复述
   - 可以适当加入一些相关例子或比喻

## 原文：
{article_text}

## 输出格式：
严格按照JSON格式输出，每轮对话包含说话人A和说话人B的内容：
[
  {{
    "speaker_1": "A说的话...",
    "speaker_2": "B说的话..."
  }},
  {{
    "speaker_1": "A说的话...",
    "speaker_2": "B说的话..."
  }}
]

注意：
- 输出必须是有效的JSON格式
- 不要添加任何其他说明文字
- 确保对话自然流畅，符合播客风格
"""

    for i in range(_max_retries):
        try:
            response = _generate_response(prompt)
            return parse_podcast_response(response)
        except Exception as e:
            logger.error(f"生成播客脚本失败: {e}")
            if i < _max_retries - 1:
                logger.warning(f"重试第 {i + 1} 次...")
                continue

    raise Exception("无法生成播客脚本")


def parse_podcast_response(response: str) -> List[PodcastScript]:
    """解析LLM返回的播客脚本"""
    try:
        # 清理响应文本，提取JSON部分
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]

        data = json.loads(response)
        podcast_scripts = []

        # 从配置中获取默认音色
        default_speaker_1_voice = config.app.get("podcast", {}).get("default_speaker_1_voice", "zh-CN-XiaoxiaoNeural-Female")
        default_speaker_2_voice = config.app.get("podcast", {}).get("default_speaker_2_voice", "zh-CN-YunxiNeural-Male")

        for item in data:
            podcast_scripts.append(PodcastScript(
                speaker_1=item["speaker_1"],
                speaker_2=item["speaker_2"],
                speaker_1_voice=default_speaker_1_voice,
                speaker_2_voice=default_speaker_2_voice
            ))

        return podcast_scripts
    except Exception as e:
        logger.error(f"解析播客脚本失败: {e}")
        raise


def fallback_terms_from_text(text: str, common_words: set, amount: int) -> List[str]:
    words = re.findall(r'\b\w+\b', text.lower())
    filtered_words = [word for word in words if word not in common_words]
    if len(filtered_words) >= amount:
        return filtered_words[:amount]
    return words[:amount]


def generate_terms_from_podcast(podcast_script: List[PodcastScript], amount: int = 5) -> List[str]:
    """从播客脚本中提取素材搜索关键词。"""
    common_words = {
        "about", "have", "you", "heard", "hey", "the", "a", "an", "and", "or", "but", "is", "are",
        "to", "of", "in", "on", "for", "with", "this", "that", "it", "we", "they", "i",
    }
    if not podcast_script:
        return []

    # 将所有对话内容合并
    all_text = " ".join([
        dialogue.speaker_1 + " " + dialogue.speaker_2
        for dialogue in podcast_script
    ])

    prompt = f'''
# Role: 播客核心关键词提取器

## 任务：
从以下播客对话内容中提取 {amount} 个最能反映内容核心主题的关键词，用于视频素材匹配。

## 播客内容：
{all_text}

## 提取要求：
1. 选择与播客主题直接相关的核心概念、技术、话题或重要对象
2. 避免选择无意义的常用词，如 "about"、"have"、"you"、"heard"、"Hey" 等
3. 每个关键词可以是单个词或由2-3个词组成的短语
4. 确保选择的关键词能够准确反映播客讨论的主要内容

## 输出要求：
返回JSON格式的关键词列表，使用英文表达：
["keyword1", "keyword2", "keyword3", ...]
'''.strip()

    response = _generate_response(prompt)
    if response.startswith("Error: "):
        logger.warning(response)
        return fallback_terms_from_text(all_text, common_words, amount)

    try:
        # 清理响应文本，提取JSON部分
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]
            
        keywords = json.loads(response)
        
        # 过滤关键词，移除常见无意义词汇
        filtered_keywords = []
        
        for keyword in keywords:
            # 检查关键词或关键词中的单词是否在常见词列表中
            words = keyword.lower().split()
            if not any(word in common_words for word in words) and keyword.strip():
                filtered_keywords.append(keyword)
                
        # 如果过滤后关键词不足，从原始关键词中补充
        if len(filtered_keywords) < amount:
            for keyword in keywords:
                if keyword not in filtered_keywords:
                    filtered_keywords.append(keyword)
                if len(filtered_keywords) >= amount:
                    break
                    
        return filtered_keywords[:amount]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"failed to parse podcast terms response: {str(e)}")
        return fallback_terms_from_text(all_text, common_words, amount)
