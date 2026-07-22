"""Image material service used by the API pipeline."""
import os
from typing import List

from loguru import logger

from app.models.schema import VideoAspect
from app.services.media_utils import MediaProcessingError, validate_image_file
from app.utils import utils

# 图片生成服务
try:
    # Import only the symbol this module actually uses. Importing a removed
    # helper used to disable the entire API image pipeline.
    from app.services.image_generator import generate_word_images_from_script
except ImportError as error:
    logger.warning(
        f"image_generator module not available; image generation disabled: {error}"
    )
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
    
    task_dir = utils.task_dir(task_id)
    images_dir = os.path.join(task_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 使用 image_generator 的批量生成函数
    generated_paths = generate_word_images_from_script(
        script=script,
        keywords=keywords,
        output_dir=images_dir,
        max_images=max_images
    )

    valid_image_paths = []
    for image_path in generated_paths:
        try:
            valid_image_paths.append(validate_image_file(image_path))
        except MediaProcessingError as error:
            logger.error(f"Discarding invalid generated image: {error}")

    if len(valid_image_paths) != len(generated_paths):
        logger.warning(
            "Image material generation returned invalid files: "
            f"valid={len(valid_image_paths)}, generated={len(generated_paths)}"
        )

    logger.success(
        f"Generated {len(valid_image_paths)} validated images for task {task_id}"
    )
    return valid_image_paths
