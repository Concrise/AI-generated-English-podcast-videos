# AI-generated English Podcast Videos

This project generates short videos from long-form article text using a podcast-only workflow.

The traditional single-speaker/topic-based video mode has been removed. The current pipeline is:

```text
article_text → podcast_script → material search terms → podcast audio → subtitles → materials → final video
```

## Features

- Podcast script generation from an article
- Two-speaker voice selection and voice preview in WebUI
- Podcast audio synthesis
- Subtitle generation from podcast dialogue/audio
- Material search from Pexels or Pixabay
- Local material support
- WebUI and HTTP API
- Portrait and landscape video output

## Requirements

- Python 3.11 is recommended
- FFmpeg
- ImageMagick for subtitle rendering
- Optional: GPU for Whisper subtitle generation

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

At minimum, configure:

- One LLM provider key, depending on `llm_provider`:
  - `moonshot_api_key`, or
  - `openai_api_key`, or
  - `qwen_api_key`, `deepseek_api_key`, `gemini_api_key`, etc.
- One material provider key:
  - `pexels_api_keys`, or
  - `pixabay_api_keys`
- TTS keys only when using paid/non-Edge voices:
  - `[azure].speech_key` and `[azure].speech_region`
  - `[siliconflow].api_key`
- Optional API authentication:
  - set `auth_enabled = true`
  - set `api_key` to a long random value
  - send it with HTTP header `x-api-key`

Important: if a key was ever committed or shared, revoke it in the provider console and create a new one.

### 4. Run WebUI

```shell
streamlit run webui/Main.py --server.address=0.0.0.0 --server.port=8501
```

Open:

```text
http://127.0.0.1:8501
```

### 5. Run API

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
