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
        # 生成唯一的输出路径
        import uuid
        output_path = f"temp/word_image_{uuid.uuid4().hex[:8]}.png"
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # 创建图片生成提示词
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
    
    payload = {
        "model": "stabilityai/stable-diffusion-3-medium",
        "prompt": prompt,
        "negative_prompt": "blurry, low quality, text errors, distorted letters, ugly, cluttered, dark background, watermark, logo, advertisement",
        "width": 512,
        "height": 768,
        "steps": 20,
        "guidance_scale": 7.5,
        "response_format": "png"
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    for i in range(3):
        try:
            logger.info(f"Generating word image for: {word}, try: {i + 1}")
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                # 保存图片文件
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    logger.info(f"Word image generated successfully: {output_path}")
                    return output_path
                else:
                    logger.warning("Generated image is empty")
            else:
                logger.error(f"Failed to generate image: {response.status_code}")
                try:
                    error_detail = response.json()
                    logger.error(f"Error detail: {error_detail}")
                except:
                    logger.error(f"Response: {response.text}")
        
        except Exception as e:
            logger.error(f"Error generating word image: {str(e)}")
    
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
    
    # 匹配格式：word /phonetic/ - definition
    pattern = r'([A-Za-z]+)\s*/([^/]+)/\s*[-—]?\s*([^\n]*)'
    matches = re.findall(pattern, text)
    
    for match in matches:
        word = match[0].strip()
        phonetic = match[1].strip()
        definition = match[2].strip()
        if word and phonetic:
            words.append((word, phonetic, definition))
    
    # 如果没有匹配到带音标的格式，尝试简单提取英文单词
    if not words:
        # 提取所有英文单词
        word_pattern = r'\b([A-Za-z]{3,})\b'
        found_words = re.findall(word_pattern, text)
        for word in found_words[:5]:  # 最多提取5个
            words.append((word, "", ""))
    
    return words


def generate_word_images_from_script(script: list, output_dir: str) -> list[str]:
    """
    从播客脚本中提取单词并生成图片
    
    Args:
        script: 播客脚本列表
        output_dir: 输出目录
        
    Returns:
        生成的图片文件路径列表
    """
    images = []
    
    # 收集所有对话文本
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
    
    # 提取单词
    words = extract_words_with_phonetics(all_text)
    
    # 为每个单词生成图片
    for word, phonetic, definition in words[:3]:  # 最多生成3张图片
        output_path = os.path.join(output_dir, f"word_{word.lower()}.png")
        image_path = generate_word_image(word, phonetic, definition, output_path)
        if image_path:
            images.append(image_path)
    
    return images


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
    
    payload = {
        "model": "stabilityai/stable-diffusion-3-medium",
        "prompt": prompt,
        "negative_prompt": "blurry, low quality, dark background, cluttered, ugly, watermark, logo",
        "width": 512,
        "height": 768,
        "steps": 20,
        "guidance_scale": 7.5,
        "response_format": "png"
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Generating educational image for topic: {topic}")
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Educational image generated: {output_path}")
                return output_path
        
        logger.error(f"Failed to generate image: {response.status_code}")
        
    except Exception as e:
        logger.error(f"Error generating educational image: {str(e)}")
    
    return ""
