import warnings
from enum import Enum
from typing import Any, List, Optional, Union

import pydantic
from pydantic import BaseModel, ConfigDict, Field

warnings.filterwarnings("ignore", category=UserWarning, message="Field name.*shadows an attribute in parent.*")

class VideoConcatMode(str, Enum):
    random = "random"
    sequential = "sequential"

class VideoTransitionMode(str, Enum):
    none = "none"
    shuffle = "Shuffle"
    fade_in = "FadeIn"
    fade_out = "FadeOut"
    slide_in = "SlideIn"
    slide_out = "SlideOut"

class VideoAspect(str, Enum):
    landscape = "16:9"
    portrait = "9:16"
    square = "1:1"

    def to_resolution(self):
        if self == VideoAspect.landscape:
            return 1920, 1080
        elif self == VideoAspect.portrait:
            return 1080, 1920
        elif self == VideoAspect.square:
            return 1080, 1080
        return 1080, 1920

@pydantic.dataclasses.dataclass(config=ConfigDict(arbitrary_types_allowed=True))
class MaterialInfo:
    provider: str = "local"
    url: str = ""
    duration: int = 0

class PodcastScript(BaseModel):
    """播客对话脚本"""
    model_config = ConfigDict(validate_default=True)

    speaker_1: str = Field(min_length=1, max_length=4000)
    speaker_2: str = Field(min_length=1, max_length=4000)
    speaker_1_voice: str = Field(min_length=1, max_length=200)
    speaker_2_voice: str = Field(min_length=1, max_length=200)

class VideoParams(BaseModel):
    """播客视频生成参数"""
    model_config = ConfigDict(validate_default=True)

    article_text: str = Field(default="", max_length=50000)
    podcast_script: Optional[List[PodcastScript]] = Field(default=None, max_length=40)
    video_terms: Optional[str | List[str]] = None
    video_aspect: VideoAspect = VideoAspect.portrait
    video_concat_mode: VideoConcatMode = VideoConcatMode.random
    video_transition_mode: VideoTransitionMode = VideoTransitionMode.none
    video_clip_duration: int = Field(default=5, ge=1, le=60)
    video_count: int = Field(default=1, ge=1, le=10)
    video_source: str = Field(default="local", max_length=50)
    video_materials: Optional[List[MaterialInfo]] = None
    video_language: str = Field(default="", max_length=50)
    speaker_1_voice: str = Field(default="gemini:Kore", min_length=1, max_length=200)
    speaker_2_voice: str = Field(default="gemini:Puck", min_length=1, max_length=200)
    voice_volume: float = Field(default=1.0, ge=0.0, le=2.0)
    voice_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    bgm_type: str = Field(default="random", max_length=20)
    bgm_file: str = Field(default="", max_length=1000)
    bgm_volume: float = Field(default=0.2, ge=0.0, le=1.0)
    subtitle_enabled: bool = False
    subtitle_position: str = Field(default="bottom", pattern="^(bottom|top|center|custom)$")
    custom_position: float = Field(default=70.0, ge=0.0, le=100.0)
    font_name: str = Field(default="STHeitiMedium.ttc", max_length=200)
    text_fore_color: str = Field(default="#FFFFFF", max_length=32)
    text_background_color: Union[bool, str] = True
    font_size: int = Field(default=60, ge=12, le=180)
    stroke_color: str = Field(default="#000000", max_length=32)
    stroke_width: float = Field(default=1.5, ge=0.0, le=10.0)
    n_threads: int = Field(default=2, ge=1, le=16)

class SubtitleRequest(VideoParams):
    """播客字幕生成请求"""
    video_source: Optional[str] = "local"


class AudioRequest(VideoParams):
    """播客音频生成请求"""
    video_source: Optional[str] = "local"


class PodcastScriptRequest(BaseModel):
    """播客脚本生成请求"""
    article_text: str = Field(min_length=1, max_length=50000)
    language: str = Field(default="English", max_length=50)
    speaker_1_voice: str = Field(default="gemini:Kore", max_length=200)
    speaker_2_voice: str = Field(default="gemini:Puck", max_length=200)


class PodcastTermsRequest(BaseModel):
    """播客素材关键词生成请求"""
    podcast_script: List[PodcastScript] = Field(min_length=1, max_length=40)
    amount: int = Field(default=5, ge=1, le=20)

class BaseResponse(BaseModel):
    status: int = 200
    message: Optional[str] = "success"
    data: Any = None

class TaskVideoRequest(VideoParams, BaseModel):
    pass

class TaskQueryRequest(BaseModel):
    pass


class TaskResponse(BaseResponse):
    class TaskResponseData(BaseModel):
        task_id: str
    data: TaskResponseData

class TaskQueryResponse(BaseResponse):
    pass

class TaskDeletionResponse(BaseResponse):
    pass

class PodcastScriptResponse(BaseResponse):
    pass

class PodcastTermsResponse(BaseResponse):
    pass

class BgmRetrieveResponse(BaseResponse):
    pass

class BgmUploadResponse(BaseResponse):
    pass
