# AI-generated English Podcast Videos

Generate short educational videos from article text using an AI podcast workflow.

## Architecture

All AI capabilities use two providers:

| Capability | Provider | Model / Endpoint |
|------------|----------|------------------|
| **LLM** (script & keywords) | MiniMax | `MiniMax-M2.5` (`/v1/text/chatcompletion_v2`) |
| **TTS** (voice synthesis) | MiniMax | `speech-2.6-hd` (`/v1/t2a_v2`) |
| **Image** (material) | apimart | gemini-3 (`/v1/images/generations`) |

```text
article_text → MiniMax LLM (podcast script) → MiniMax LLM (keywords)
            → apimart (one image per sentence)
            → MiniMax TTS (one audio per speaker line)
            → ffmpeg (images+audio → segments → concat)
            → ffmpeg (mix background music)
            → final video
```

**No SiliconFlow.** LLM and TTS both use MiniMax exclusively. Image generation uses apimart. No Pexels/Pixabay keys required.

## Features

- Podcast script generation from an article (MiniMax LLM)
- Two-speaker voice selection and voice preview in WebUI (MiniMax TTS)
- Podcast audio synthesis
- AI image generation per sentence (apimart)
- Local material support (legacy)
- Background music: random / custom track / none, with volume control
- WebUI and HTTP API
- Portrait video output
- **No subtitles** — videos contain image + voice + music only

## Requirements

- Python 3.11
- FFmpeg + ffprobe on PATH (the WebUI calls `ffmpeg`/`ffprobe` directly by name)
- **CPU only** — no CUDA/GPU/torch needed. No ImageMagick needed. No Whisper model download needed.

## Quick Start

### 1. Clone the project

```shell
git clone https://github.com/liangdabiao/AI-generated-English-podcast-videos.git
cd AI-generated-English-podcast-videos
```

### 2. Install dependencies

```shell
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 3. Configure keys

Copy the example configuration and edit it:

```shell
copy config.example.toml config.toml  # Windows
# cp config.example.toml config.toml  # macOS/Linux
```

Edit `config.toml` — only two keys are required:

```toml
[MiniMax]
api_key = "your-minimax-key"     # REQUIRED: LLM (MiniMax-M2.5) + TTS (speech-2.6-hd)
llm_model = "MiniMax-M2.5"
tts_model = "speech-2.6-hd"

[apimart]
api_key = "your-apimart-key"     # REQUIRED: image generation (gemini-3)
```

The `[siliconflow]` section is deprecated and unused. No Pexels/Pixabay keys needed.

Optional API authentication (for exposing the HTTP API):

- set `auth_enabled = true`
- set `api_key` to a long random value
- send it with HTTP header `x-api-key`

Important: if a key was ever committed or shared, **revoke it** in the provider console and create a new one — deleting it from a later commit does not remove it from git history.

### 4. Verify environment

```shell
ffmpeg -version
ffprobe -version
```

Both must be on PATH. If not, add FFmpeg's `bin` folder to your PATH. (The WebUI calls `ffmpeg`/`ffprobe` directly by name.)

### 5. Run WebUI

```shell
streamlit run webui/Main.py --server.address=0.0.0.0 --server.port=8501
```

Open:

```text
http://127.0.0.1:8501
```

### 6. Run API

```shell
python main.py
```

Open API docs:

```text
http://127.0.0.1:8080/docs
```

## Docker

Create `config.toml` first, then run:

```shell
docker compose up
```

WebUI:

```text
http://127.0.0.1:8501
```

API docs:

```text
http://127.0.0.1:8080/docs
```

## API Flow

### Generate podcast script

`POST /api/v1/scripts`

```json
{
  "article_text": "Paste your article here...",
  "language": "en-US",
  "speaker_1_voice": "zh-CN-XiaoxiaoNeural-Female",
  "speaker_2_voice": "zh-CN-YunxiNeural-Male"
}
```

### Generate material terms

`POST /api/v1/terms`

```json
{
  "podcast_script": [
    {
      "speaker_1": "Welcome to today's episode...",
      "speaker_2": "Let's explore the topic...",
      "speaker_1_voice": "zh-CN-XiaoxiaoNeural-Female",
      "speaker_2_voice": "zh-CN-YunxiNeural-Male"
    }
  ],
  "amount": 5
}
```

### Generate video

`POST /api/v1/videos`

```json
{
  "article_text": "Paste your article here...",
  "podcast_script": [
    {
      "speaker_1": "Welcome to today's episode...",
      "speaker_2": "Let's explore the topic...",
      "speaker_1_voice": "zh-CN-XiaoxiaoNeural-Female",
      "speaker_2_voice": "zh-CN-YunxiNeural-Male"
    }
  ],
  "video_terms": "podcast studio, technology, city life",
  "video_source": "local",
  "video_aspect": "9:16",
  "video_count": 1
}
```

If `auth_enabled = true`, include:

```text
x-api-key: your-api-key
```

## Testing

Local syntax validation:

```shell
python -m compileall app webui
```

Unit tests without integration tests:

```shell
python -m pytest -q
```

Integration tests that call external services or start local servers are marked with `integration` and are skipped by default. Run them only after keys are configured and real external calls are authorized:

```shell
python -m pytest -q -m integration
```

Recommended real verification after configuring keys:

1. WebUI: paste an article, generate podcast dialogue, preview both voices, generate video.
2. API: call `/api/v1/scripts`, `/api/v1/terms`, then `/api/v1/videos`.
3. Security checks:
   - `/api/v1/stream/../../config.toml` should fail.
   - `/api/v1/download/../../config.toml` should fail.
   - BGM upload with a suspicious filename should be saved under a safe generated name.
   - If `auth_enabled = true`, API calls without `x-api-key` should return 401.

## Notes

- This is now a podcast-only application. Legacy fields such as `video_subject`, traditional `video_script`, `podcast_mode`, `voice_name`, and `paragraph_number` are no longer part of the request schema.
- `video_terms` is still used as the material search terms field for compatibility with existing internals.
- Keep `verify_ssl = true` unless debugging with a trusted local proxy.

## License

See [`LICENSE`](LICENSE).


## 🙏 致谢

- [SiliconFlow](https://cloud.siliconflow.cn/) - LLM 和 TTS 服务
- [apimart](https://apimart.ai/) - Gemini 图片生成服务
- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) - 项目参考
- [linuxdo](https://linux.do/) - linux.do 佬友
