import os
import random
from typing import List
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.utils import utils

# 图片生成服务
try:
    from app.services.image_generator import generate_word_image, generate_educational_image, extract_words_with_phonetics
except ImportError:
    logger.warning("image_generator module not found, image generation features disabled")
    generate_word_image = None
    generate_educational_image = None
    extract_words_with_phonetics = None

requested_count = 0


def request_verify_ssl() -> bool:
    return bool(config.app.get("verify_ssl", True))


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global requested_count
    requested_count += 1
    return api_keys[requested_count % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    # Build URL
    params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url,
            headers=headers,
            proxies=config.proxy,
            verify=request_verify_ssl(),
            timeout=(30, 60),
        )
        r.raise_for_status()
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["videos"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["video_files"]
            # loop through each url to determine the best quality
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                if w == video_width and h == video_height:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    video_width, video_height = aspect.to_resolution()

    api_key = get_api_key("pixabay_api_keys")
    # Build URL
    params = {
        "q": search_term,
        "video_type": "all",  # Accepted values: "all", "film", "animation"
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=request_verify_ssl(), timeout=(30, 60)
        )
        r.raise_for_status()
        response = r.json()

        video_items = []
        if "hits" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["hits"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            # loop through each url to determine the best quality
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                # h = int(video["height"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # if video does not exist, download it
    response = requests.get(
        video_url,
        headers=headers,
        proxies=config.proxy,
        verify=request_verify_ssl(),
        timeout=(60, 240),
    )
    response.raise_for_status()
    with open(video_path, "wb") as f:
        f.write(response.content)

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            clip.close()
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            try:
                os.remove(video_path)
            except Exception:
                pass
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    search_terms = optimize_podcast_search_terms(search_terms)
    logger.info(f"optimized podcast search terms: {search_terms}")

    for search_term in search_terms:
        video_items = search_videos(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(
                video_url=item.url, save_dir=material_directory
            )
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


def optimize_podcast_search_terms(search_terms: List[str]) -> List[str]:
    """优化播客搜索词，提高素材匹配质量"""
    logger.info("optimizing search terms for podcast mode")

    # 播客相关的通用高质量素材关键词
    podcast_common_terms = [
        "conversation", "discussion", "interview", "talk", "dialogue",
        "people talking", "communication", "meeting", "presentation",
        "technology", "innovation", "business", "office", "modern",
        "abstract", "background", "nature", "city", "space"
    ]

    # 扩展原始搜索词
    optimized_terms = []

    for term in search_terms:
        # 保留原始搜索词
        optimized_terms.append(term)

        # 添加播客相关的变体
        podcast_variants = [
            f"{term} conversation",
            f"{term} discussion",
            f"{term} technology",
            f"{term} innovation",
            f"{term} background"
        ]

        optimized_terms.extend(podcast_variants)

    # 添加通用播客素材词
    optimized_terms.extend(podcast_common_terms)

    # 去重并限制数量
    unique_terms = list(set(optimized_terms))
    return unique_terms[:15]  # 限制最多15个搜索词


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
    if generate_word_image is None:
        logger.error("image_generator module not available")
        return []
    
    image_paths = []
    task_dir = utils.task_dir(task_id)
    images_dir = os.path.join(task_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 从脚本中提取单词
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
    
    # 提取单词及其音标
    words = extract_words_with_phonetics(all_text)
    logger.info(f"Extracted {len(words)} words from script")
    
    # 使用关键词补充
    for keyword in keywords[:5]:
        words.append((keyword, "", ""))
    
    # 去重
    seen_words = set()
    unique_words = []
    for word, phonetic, definition in words:
        word_lower = word.lower()
        if word_lower not in seen_words:
            seen_words.add(word_lower)
            unique_words.append((word, phonetic, definition))
    
    # 生成图片
    generated_count = 0
    for word, phonetic, definition in unique_words[:max_images]:
        output_path = os.path.join(images_dir, f"word_{word.lower()}.png")
        
        # 如果图片已存在，跳过
        if os.path.exists(output_path):
            image_paths.append(output_path)
            generated_count += 1
            continue
        
        # 生成图片
        logger.info(f"Generating image for word: {word} /{phonetic}/")
        result = generate_word_image(word, phonetic, definition, output_path)
        
        if result:
            image_paths.append(result)
            generated_count += 1
            
            # 如果已经生成了足够的图片，停止
            if generated_count >= max_images:
                break
    
    # 如果没有生成任何图片，生成一个通用教育图片
    if not image_paths and keywords:
        topic = keywords[0] if keywords else "English Learning"
        output_path = os.path.join(images_dir, f"educational_{topic.lower()}.png")
        result = generate_educational_image(topic, keywords[:3], output_path)
        if result:
            image_paths.append(result)
    
    logger.success(f"Generated {len(image_paths)} images for task {task_id}")
    return image_paths


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )
