from app.services.llm import generate_podcast_script, generate_terms_from_podcast
from app.services.voice import get_siliconflow_voices
from app.services.image_generator import generate_word_image
import os

print('='*60)
print('          系统功能测试')
print('='*60)

# 测试 LLM
print('\n🔍 测试 LLM 服务...')
script = generate_podcast_script('Artificial intelligence is transforming the world.')
print(f'✅ LLM 服务正常，生成了 {len(script)} 轮对话')

# 测试语音列表
print('\n🔍 测试语音列表获取...')
voices = get_siliconflow_voices()
print(f'✅ 语音列表获取成功，可用语音数量: {len(voices)}')

# 测试图片生成
print('\n🔍 测试图片生成...')
result = generate_word_image('test', 'test', '测试', 'test.png')
if result and os.path.exists(result):
    print(f'✅ 图片生成成功: {result}')
    os.remove(result)
else:
    print('⚠️ 图片生成失败（可能是API Key问题）')

print('\n' + '='*60)
print('          测试完成')
print('='*60)