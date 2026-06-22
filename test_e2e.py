"""Test LLM and TTS end-to-end with MiniMax"""
import sys
sys.path.insert(0, '.')

from app.services import llm
from app.services.voice import MiniMax_tts

print("=" * 60)
print("Test 1: LLM with MiniMax")
print("=" * 60)
result = llm._generate_response("Generate a 2-line English podcast dialogue about Dragon Boat Festival, format each line as: Speaker N: text")
print("LLM result:")
print(result[:500] if result else "EMPTY")

print()
print("=" * 60)
print("Test 2: TTS with MiniMax")
print("=" * 60)
test_text = "Hello, this is a test of the MiniMax text to speech system."
sub_maker = MiniMax_tts(
    text=test_text,
    model="speech-2.6-hd",
    voice="English_PassionateWarrior",
    voice_rate=1.0,
    voice_file="test_end2end.mp3",
    voice_volume=1.0
)
if sub_maker:
    print(f"TTS succeeded, subs: {sub_maker.subs[:2]}")
    import os
    if os.path.exists("test_end2end.mp3"):
        print(f"File size: {os.path.getsize('test_end2end.mp3')} bytes")
else:
    print("TTS failed")
