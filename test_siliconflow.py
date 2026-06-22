#!/usr/bin/env python3
"""
测试 SiliconFlow API 功能：语音生成、图片生成
"""
import os
import sys
import asyncio

print("="*60)
print("      SiliconFlow API 功能测试")
print("="*60)

# 测试配置加载
print("\n🔍 测试配置文件加载...")
try:
    from app.config import config
    print(f"✅ 配置文件加载成功")
    print(f"   - LLM提供商: {config.app.get('llm_provider')}")
    print(f"   - 视频来源: {config.app.get('video_source')}")
    print(f"   - SiliconFlow API Key: {'已配置' if config.siliconflow.get('api_key') else '未配置'}")
except Exception as e:
    print(f"❌ 配置文件加载失败: {str(e)}")
    sys.exit(1)

# 测试 SiliconFlow 语音列表获取
print("\n🔍 测试 SiliconFlow 语音列表获取...")
try:
    from app.services.voice import get_siliconflow_voices
    voices = get_siliconflow_voices()
    print(f"✅ 语音列表获取成功")
    print(f"   - 可用语音数量: {len(voices)}")
    for i, voice in enumerate(voices[:3]):
        print(f"     {i+1}. {voice}")
except Exception as e:
    print(f"❌ 语音列表获取失败: {str(e)}")

# 测试 SiliconFlow TTS
print("\n🔍 测试 SiliconFlow TTS...")
try:
    from app.services.voice import siliconflow_tts
    
    test_text = "Hello, this is a test of SiliconFlow text to speech."
    output_file = "test_siliconflow_tts.mp3"
    
    result = siliconflow_tts(
        text=test_text,
        model="FunAudioLLM/CosyVoice2-0.5B",
        voice="FunAudioLLM/CosyVoice2-0.5B:alex",
        voice_rate=1.0,
        voice_file=output_file
    )
    
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        file_size = os.path.getsize(output_file)
        print(f"✅ SiliconFlow TTS 调用成功")
        print(f"   - 生成音频文件: {output_file}")
        print(f"   - 文件大小: {file_size / 1024:.2f} KB")
        os.remove(output_file)
    else:
        print("❌ SiliconFlow TTS 返回空结果")
except Exception as e:
    print(f"❌ SiliconFlow TTS 调用失败: {str(e)}")

# 测试图片生成
print("\n🔍 测试 SiliconFlow 图片生成...")
try:
    from app.services.image_generator import generate_word_image, generate_educational_image
    
    # 测试单词图片生成
    word_output = "test_word_image.png"
    result = generate_word_image("learning", "lɜːrnɪŋ", "学习", word_output)
    
    if result and os.path.exists(result):
        file_size = os.path.getsize(result)
        print(f"✅ 单词图片生成成功")
        print(f"   - 生成图片: {result}")
        print(f"   - 文件大小: {file_size / 1024:.2f} KB")
        os.remove(result)
    else:
        print("❌ 单词图片生成失败")
        
    # 测试教育图片生成
    edu_output = "test_educational_image.png"
    result = generate_educational_image("English Learning", ["vocabulary", "grammar", "pronunciation"], edu_output)
    
    if result and os.path.exists(result):
        file_size = os.path.getsize(result)
        print(f"✅ 教育图片生成成功")
        print(f"   - 生成图片: {result}")
        print(f"   - 文件大小: {file_size / 1024:.2f} KB")
        os.remove(result)
    else:
        print("❌ 教育图片生成失败")
        
except Exception as e:
    print(f"❌ 图片生成失败: {str(e)}")

# 测试视频合成（图片作为素材）
print("\n🔍 测试视频合成（图片作为素材）...")
try:
    from app.services.video import is_image_file, combine_videos
    
    # 创建测试图片
    test_image = "test_clip.png"
    from PIL import Image
    img = Image.new('RGB', (512, 768), color=(255, 255, 255))
    img.save(test_image)
    
    # 检查图片检测功能
    if is_image_file(test_image):
        print("✅ 图片检测功能正常")
    else:
        print("❌ 图片检测功能异常")
    
    os.remove(test_image)
except Exception as e:
    print(f"❌ 视频合成测试失败: {str(e)}")

print("\n" + "="*60)
print("                    测试完成")
print("="*60)
