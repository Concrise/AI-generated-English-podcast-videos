import os
import re
import requests
import base64
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from app.config import config


def generate_sentence_image(sentence: str, keywords: list = None, output_path: str = "") -> str:
    """
    使用 apimart gemini-3 API 根据英文句子生成教育图片
    
    Args:
        sentence: 英文句子（作为图片内容描述）
        keywords: 关键词列表，用于标注音标
        output_path: 输出文件路径，如果为空则自动生成
    
    Returns:
        生成的图片文件路径，失败返回空字符串
    """
    # 使用 apimart API Key（从配置文件读取）
    api_key = config.apimart.get("api_key", "")
    
    if not api_key:
        logger.error("apimart API key is not set")
        return ""
    
    if not output_path:
        import uuid
        output_path = f"temp/sentence_image_{uuid.uuid4().hex[:8]}.png"
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # 构建生图提示语（中小学英语课本风格）
    prompt = f"""
    English textbook page for middle school students.
    
    CONTENT:
    Sentence at top: "{sentence}"
    Keywords below: {', '.join(keywords)} with phonetic symbols
    
    DESIGN:
    - Large readable English text (black font on white)
    - Simple colorful illustration related to sentence meaning
    - Clean educational layout
    - Portrait orientation 9:16
    - Style like Oxford English textbook
    - Include text AND picture
    
    Make educational flashcard with both text and illustration.
    """.strip()
    
    # apimart API配置
    url = "https://api.apimart.ai/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "gemini-3.1-flash-image-preview",
        "prompt": prompt,
        "size": "9:16",
        "resolution": "2K",
        "n": 1
    }
    
    try:
        logger.info(f"Generating sentence image with apimart gemini-3")
        logger.debug(f"Prompt: {prompt[:200]}...")
        
        # Step 1: 提交生成任务
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200 and data.get("data") and len(data["data"]) > 0:
                task_id = data["data"][0].get("task_id")
                logger.info(f"Task submitted successfully, task_id: {task_id}")
                
                # Step 2: 轮询查询任务状态
                import time
                max_retries = 60  # 增加重试次数
                retry_delay = 5  # 5秒间隔
                
                for attempt in range(max_retries):
                    # 正确的任务查询 URL 是 /v1/tasks/{task_id}
                    status_url = f"https://api.apimart.ai/v1/tasks/{task_id}"
                    status_response = requests.get(status_url, headers=headers, timeout=30)
                    
                    logger.debug(f"Status check attempt {attempt+1}: HTTP {status_response.status_code}")
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        logger.debug(f"Status response data: {status_data}")
                        
                        if status_data.get("code") == 200:
                            task_info = status_data.get("data", {})
                            # 尝试多种可能的状态字段
                            status = task_info.get("status") or task_info.get("task_status") or task_info.get("state")
                            
                            logger.info(f"Task status: {status}")
                            
                            if status == "completed" or status == "success":
                                # 从 result.images[0].url[0] 获取图片 URL
                                result_data = task_info.get("result", {})
                                images = result_data.get("images", []) or task_info.get("images", [])
                                if images and len(images) > 0:
                                    image_url_info = images[0]
                                    # URL 可能是数组或字符串
                                    image_url = image_url_info.get("url")
                                    if isinstance(image_url, list) and len(image_url) > 0:
                                        image_url = image_url[0]
                                    elif not image_url:
                                        image_url = image_url_info.get("image_url")
                                        
                                    if image_url:
                                        # 下载图片
                                        image_response = requests.get(image_url, timeout=60)
                                        if image_response.status_code == 200:
                                            with open(output_path, "wb") as f:
                                                f.write(image_response.content)
                                            
                                            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                                logger.info(f"Sentence image generated successfully: {output_path}")
                                                return output_path
                                    else:
                                        logger.warning(f"Image URL not found in response: {images[0]}")
                                else:
                                    logger.warning(f"No images found in response: {task_info}")
                            
                            elif status == "failed" or status == "error":
                                error_msg = task_info.get("error", {}).get("message", "Unknown error") or task_info.get("message", "Unknown error")
                                logger.error(f"Task failed: {error_msg}")
                                return ""
                            
                            elif status == "running" or status == "processing" or status == "pending" or status == "submitted":
                                logger.debug(f"Task running... ({attempt+1}/{max_retries})")
                            
                            else:
                                logger.debug(f"Unknown status: {status}")
                    
                    time.sleep(retry_delay)
                
                logger.error("apimart API task timeout after waiting")
                return ""
            else:
                logger.warning(f"apimart API response error: {data}")
                return ""
                
        else:
            logger.warning(f"apimart API failed: {response.status_code}")
            try:
                error_detail = response.json()
                logger.warning(f"Error detail: {error_detail}")
            except:
                logger.warning(f"Response: {response.text}")
            return ""
                
    except requests.exceptions.Timeout:
        logger.error("apimart API request timed out")
        return ""
    except requests.exceptions.ConnectionError:
        logger.error("apimart API connection error")
        return ""
    except Exception as e:
        logger.error(f"Error generating sentence image with apimart: {str(e)}")
        return ""
    
    return ""


def generate_word_image(word: str, phonetic: str, definition: str = "", output_path: str = "") -> str:
    """
    使用 SiliconFlow 图片生成 API 生成教育英文单词标注图片
    
    Args:
        word: 英文单词
        phonetic: 音标
        definition: 中文释义（可选）
        output_path: 输出文件路径，如果为空则自动生成
    
    Returns:
        生成的图片文件路径，失败返回空字符串
    """
    api_key = config.siliconflow.get("api_key", "")
    
    if not api_key:
        logger.error("SiliconFlow API key is not set")
        return ""
    
    if not output_path:
        import uuid
        output_path = f"temp/word_image_{uuid.uuid4().hex[:8]}.png"
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # 构建生图提示语：直接要求生成包含单词、音标、释义的图片
    prompt = f"""
    Create an educational English vocabulary flashcard image.
    
    Content to display clearly:
    - Word: "{word}" (large, bold, blue or black)
    - Phonetic: "/{phonetic}/" (smaller, gray, below the word)
    {f'- Meaning: "{definition}" (green, below phonetic)' if definition else ''}
    
    Design requirements:
    - Clean white or light gradient background
    - Professional educational card style
    - Portrait orientation (9:16)
    - Text centered and easy to read
    - Minimalist design
    - Add subtle decorative elements related to learning
    - No clutter, focus on readability
    
    Make it suitable for English vocabulary learning.
    """.strip()
    
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    # 使用文本到图像生成模型
    models = [
        {
            "name": "Qwen/Qwen-Image",
            "image_size": "928x1664",  # 9:16 portrait for Qwen-Image
            "guidance_scale": 7.5,
            "num_inference_steps": 25
        },
        {
            "name": "Kwai-Kolors/Kolors",
            "image_size": "720x1280",  # 9:16 portrait
            "guidance_scale": 7.5,
            "num_inference_steps": 25
        },
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    for model_info in models:
        payload = {
            "model": model_info["name"],
            "prompt": prompt,
            "negative_prompt": "blurry text, unreadable text, text errors, distorted letters, low quality, dark background, cluttered, ugly, watermark, logo, advertisement, bad typography",
            "image_size": model_info["image_size"],
            "num_inference_steps": model_info["num_inference_steps"],
            "guidance_scale": model_info["guidance_scale"],
            "batch_size": 1
        }
        
        try:
            logger.info(f"Generating word image for: {word}, model: {model_info['name']}")
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("images") and len(data["images"]) > 0:
                    image_url = data["images"][0].get("url")
                    if image_url:
                        # 下载图片
                        image_response = requests.get(image_url)
                        if image_response.status_code == 200:
                            with open(output_path, "wb") as f:
                                f.write(image_response.content)
                            
                            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                logger.info(f"Word image generated successfully: {output_path}")
                                return output_path
            
            logger.warning(f"Model {model_info['name']} failed: {response.status_code}")
            try:
                error_detail = response.json()
                logger.warning(f"Error detail: {error_detail}")
            except:
                logger.warning(f"Response: {response.text}")
                    
        except Exception as e:
            logger.error(f"Error generating word image with model {model_info['name']}: {str(e)}")
    
    return ""


def extract_key_sentences(script: list, max_sentences: int = 5) -> list[tuple[str, list[str]]]:
    """
    从播客脚本中提取关键句子
    
    Args:
        script: 播客脚本列表
        max_sentences: 最大提取句子数量
        
    Returns:
        句子列表，每个元素为 (sentence, keywords)
    """
    sentences = []
    
    for turn in script:
        # 获取对话内容
        speaker_1 = ""
        speaker_2 = ""
        
        if hasattr(turn, 'speaker_1'):
            speaker_1 = turn.speaker_1
        if hasattr(turn, 'speaker_2'):
            speaker_2 = turn.speaker_2
        elif isinstance(turn, dict):
            speaker_1 = turn.get('speaker_1', '')
            speaker_2 = turn.get('speaker_2', '')
        
        # 提取有意义的句子（长度适中，包含教育内容）
        for text in [speaker_1, speaker_2]:
            if not text:
                continue
            
            # 按句号分割
            for sentence in text.split('. '):
                sentence = sentence.strip()
                if len(sentence) > 20 and len(sentence) < 150:  # 适中长度的句子
                    # 提取关键词（简单方法：提取长单词）
                    words = re.findall(r'\b([A-Za-z]{4,})\b', sentence)
                    keywords = [w for w in words if w.lower() not in ['that', 'this', 'with', 'from', 'have', 'what', 'when', 'where', 'which', 'about', 'there', 'their', 'would', 'could', 'should']][:3]
                    
                    if keywords:  # 只保留有关键词的句子
                        sentences.append((sentence + ('.' if not sentence.endswith('.') else ''), keywords))
        
        if len(sentences) >= max_sentences:
            break
    
    return sentences[:max_sentences]


def generate_word_images_from_script(script: list, keywords: list, output_dir: str, max_images: int = 5) -> list[str]:
    """
    从播客脚本中提取关键句子并生成教育图片
    
    Args:
        script: 播客脚本列表
        keywords: 关键词列表
        output_dir: 输出目录
        max_images: 最大生成图片数量
        
    Returns:
        生成的图片文件路径列表
    """
    image_paths = []
    images_dir = output_dir
    os.makedirs(images_dir, exist_ok=True)
    
    # 提取关键句子
    sentences = extract_key_sentences(script, max_images)
    
    # 如果没有提取到句子，使用关键词生成单词卡片
    if not sentences and keywords:
        logger.info("No key sentences found, generating word cards from keywords")
        for i, keyword in enumerate(keywords[:max_images]):
            output_path = os.path.join(images_dir, f"keyword_{i+1}.png")
            result = generate_word_image(keyword, "", "", output_path)
            if result:
                image_paths.append(result)
        
        logger.success(f"Generated {len(image_paths)} images")
        return image_paths
    
    # 为每个句子生成图片
    for i, (sentence, sentence_keywords) in enumerate(sentences):
        output_path = os.path.join(images_dir, f"sentence_{i+1}.png")
        
        if os.path.exists(output_path):
            image_paths.append(output_path)
            continue
        
        logger.info(f"Generating image for sentence: {sentence[:50]}...")
        logger.info(f"Keywords: {sentence_keywords}")
        
        result = generate_sentence_image(sentence, sentence_keywords, output_path)
        
        if result:
            image_paths.append(result)
    
    # 如果图片数量不足，补充关键词卡片
    if len(image_paths) < max_images and keywords:
        remaining = max_images - len(image_paths)
        for keyword in keywords[:remaining]:
            output_path = os.path.join(images_dir, f"keyword_{keyword.lower()}.png")
            if not os.path.exists(output_path):
                result = generate_word_image(keyword, "", "", output_path)
                if result:
                    image_paths.append(result)
    
    logger.success(f"Generated {len(image_paths)} images")
    return image_paths


def generate_educational_image(topic: str, keywords: list, output_path: str = "") -> str:
    """
    生成教育主题图片
    
    Args:
        topic: 主题
        keywords: 关键词列表
        output_path: 输出文件路径
    
    Returns:
        生成的图片文件路径
    """
    api_key = config.siliconflow.get("api_key", "")
    
    if not api_key:
        logger.error("SiliconFlow API key is not set")
        return ""
    
    if not output_path:
        import uuid
        output_path = f"temp/educational_{uuid.uuid4().hex[:8]}.png"
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    keywords_str = ", ".join(keywords)
    
    prompt = f"""
    Create an educational infographic image about "{topic}":
    
    Key elements:
    - Title: "{topic}"
    - Keywords: {keywords_str}
    - Clean, modern educational design
    - Light blue or white background
    - Icons or illustrations related to the topic
    - Suitable for English learning content
    - Professional, clean typography
    - Portrait orientation (vertical)
    - No text errors, easy to read
    
    Style: minimalist, educational, engaging
    """.strip()
    
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    models = [
        {
            "name": "Kwai-Kolors/Kolors",
            "image_size": "720x1280",
            "guidance_scale": 7.5,
            "num_inference_steps": 20
        },
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    for model_info in models:
        payload = {
            "model": model_info["name"],
            "prompt": prompt,
            "negative_prompt": "blurry, low quality, dark background, cluttered, ugly, watermark, logo",
            "image_size": model_info["image_size"],
            "num_inference_steps": model_info["num_inference_steps"],
            "guidance_scale": model_info["guidance_scale"],
            "batch_size": 1
        }
        
        try:
            logger.info(f"Generating educational image for topic: {topic}, model: {model_info['name']}")
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("images") and len(data["images"]) > 0:
                    image_url = data["images"][0].get("url")
                    if image_url:
                        image_response = requests.get(image_url)
                        if image_response.status_code == 200:
                            with open(output_path, "wb") as f:
                                f.write(image_response.content)
                            
                            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                logger.info(f"Educational image generated: {output_path}")
                                return output_path
            
            logger.warning(f"Model {model_info['name']} failed: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Error generating educational image: {str(e)}")
    
    return ""
