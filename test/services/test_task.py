import os

import pytest

pytestmark = pytest.mark.integration
if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("integration test skipped by default", allow_module_level=True)
import sys
import unittest
from pathlib import Path

# add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models.schema import MaterialInfo, PodcastScript, VideoParams
from app.services import task as tm

resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")


class TestTaskService(unittest.TestCase):
    def test_task_local_materials(self):
        task_id = "00000000-0000-0000-0000-000000000000"
        video_materials = []
        for i in range(1, 4):
            video_materials.append(MaterialInfo(
                provider="local",
                url=os.path.join(resources_dir, f"{i}.png"),
                duration=0,
            ))

        params = VideoParams(
            article_text="金钱不仅是交换媒介，更是社会资源的分配工具。它能满足基本生存需求，也能提供教育、医疗等提升生活品质的机会。",
            podcast_script=[PodcastScript(
                speaker_1="今天我们聊聊金钱在现代社会中的作用。",
                speaker_2="它既是交换媒介，也会影响资源分配和个人选择。",
                speaker_1_voice="zh-CN-XiaoxiaoNeural-Female",
                speaker_2_voice="zh-CN-YunxiNeural-Male",
            )],
            video_terms="money importance, wealth and society, financial freedom, role of money",
            video_aspect="9:16",
            video_concat_mode="random",
            video_transition_mode="none",
            video_clip_duration=3,
            video_count=1,
            video_source="local",
            video_materials=video_materials,
            video_language="",
            speaker_1_voice="zh-CN-XiaoxiaoNeural-Female",
            speaker_2_voice="zh-CN-YunxiNeural-Male",
            voice_volume=1.0,
            voice_rate=1.0,
            bgm_type="random",
            bgm_file="",
            bgm_volume=0.2,
            subtitle_enabled=True,
            subtitle_position="bottom",
            custom_position=70.0,
            font_name="MicrosoftYaHeiBold.ttc",
            text_fore_color="#FFFFFF",
            text_background_color=True,
            font_size=60,
            stroke_color="#000000",
            stroke_width=1.5,
            n_threads=2,
        )
        result = tm.start(task_id=task_id, params=params)
        print(result)


if __name__ == "__main__":
    unittest.main()
