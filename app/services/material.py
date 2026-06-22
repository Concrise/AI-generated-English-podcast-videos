"""
素材服务 - 简化版
仅支持 SiliconFlow 图片生成
"""
import os
from typing import List

from loguru import logger

from app.models.schema import VideoAspect
from app.utils import utils

# 图片生成服务
try:
    from app.services.image_generator import (
        generate_word_image,
        generate_educational_image,
        extract_words_with_phonetics,
        generate_word_images_from_script,
    )
except ImportError:
    logger.warning("image_generator module not found, image generation features disabled")
    generate_word_image = None
    generate_educational_image = None
    extract_words_with_phonetics = None
    generate_word_images_from_script = None


def generate_image_materials(
    task_id: str,
    script: list,
    keywords: List[str],
    audio_duration: float = 0.0,
    max_images: int = 5,
) -> List[str]:
    """
    使用 SiliconFlow 图片生成 API 生成教育英文单词标注图片作为视频素材
    
    Args:
        task_id: 任务ID
        script: 播客脚本列表
        keywords: 关键词列表
        audio_duration: 音频时长（秒）
        max_images: 最大生成图片数量
        
    Returns:
        生成的图片文件路径列表
    """
    if generate_word_images_from_script is None:
        logger.error("image_generator module not available")
        return []
    
    image_paths = []
    task_dir = utils.task_dir(task_id)
    images_dir = os.path.join(task_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 使用 image_generator 的批量生成函数
    image_paths = generate_word_images_from_script(
        script=script,
        keywords=keywords,
        output_dir=images_dir,
        max_images=max_images
    )
    
    logger.success(f"Generated {len(image_paths)} images for task {task_id}")
    return image_paths
