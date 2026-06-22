import os
import re
import requests
from loguru import logger

from app.config import config


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
    
    prompt = f"""
    Create an educational English vocabulary flashcard image with clean, modern design:
    
    Main content:
    - Large, clear English word: "{word}"
    - Phonetic transcription: "/{phonetic}/"
    - {f'Chinese definition: "{definition}"' if definition else ''}
    
    Design requirements:
    - Clean white or light gradient background
    - Word in bold blue or black font (large size)
    - Phonetic in smaller gray font below the word
    - Definition (if provided) in green font
    - Minimalist style, easy to read
    - Professional educational card style
    - Portrait orientation
    - No extra decorations, focus on readability
    
    Suitable for English learning app, simple and elegant.
    """.strip()
    
    url = "https://api.siliconflow.cn/v1/images/generations"
    
    # 根据文档，可用的图片生成模型
    models = [
        {
            "name": "Kwai-Kolors/Kolors",
            "image_size": "720x1280",  # 9:16 portrait
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
            "negative_prompt": "blurry, low quality, text errors, distorted letters, ugly, cluttered, dark background, watermark, logo, advertisement",
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


def extract_words_with_phonetics(text: str) -> list[tuple[str, str, str]]:
    """
    从文本中提取单词及其音标（简单规则匹配）
    
    Args:
        text: 包含单词和音标的文本
        
    Returns:
        单词列表，每个元素为 (word, phonetic, definition)
    """
    words = []
    
    pattern = r'([A-Za-z]+)\s*/([^/]+)/\s*[-—]?\s*([^\n]*)'
    matches = re.findall(pattern, text)
    
    for match in matches:
        word = match[0].strip()
        phonetic = match[1].strip()
        definition = match[2].strip()
        if word and phonetic:
            words.append((word, phonetic, definition))
    
    if not words:
        word_pattern = r'\b([A-Za-z]{3,})\b'
        found_words = re.findall(word_pattern, text)
        for word in found_words[:5]:
            words.append((word, "", ""))
    
    return words


def generate_word_images_from_script(script: list, keywords: list, output_dir: str, max_images: int = 5) -> list[str]:
    """
    从播客脚本中提取单词并生成图片
    
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
    
    all_text = ""
    for turn in script:
        if hasattr(turn, 'speaker_1'):
            all_text += " " + turn.speaker_1
        if hasattr(turn, 'speaker_2'):
            all_text += " " + turn.speaker_2
        elif isinstance(turn, dict):
            if 'speaker_1' in turn:
                all_text += " " + turn['speaker_1']
            if 'speaker_2' in turn:
                all_text += " " + turn['speaker_2']
    
    words = extract_words_with_phonetics(all_text)
    
    for keyword in keywords[:5]:
        words.append((keyword, "", ""))
    
    seen_words = set()
    unique_words = []
    for word, phonetic, definition in words:
        word_lower = word.lower()
        if word_lower not in seen_words:
            seen_words.add(word_lower)
            unique_words.append((word, phonetic, definition))
    
    generated_count = 0
    for word, phonetic, definition in unique_words[:max_images]:
        output_path = os.path.join(images_dir, f"word_{word.lower()}.png")
        
        if os.path.exists(output_path):
            image_paths.append(output_path)
            generated_count += 1
            continue
        
        logger.info(f"Generating image for word: {word} /{phonetic}/")
        result = generate_word_image(word, phonetic, definition, output_path)
        
        if result:
            image_paths.append(result)
            generated_count += 1
            
            if generated_count >= max_images:
                break
    
    if not image_paths and keywords:
        topic = keywords[0] if keywords else "English Learning"
        output_path = os.path.join(images_dir, f"educational_{topic.lower()}.png")
        result = generate_educational_image(topic, keywords[:3], output_path)
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
