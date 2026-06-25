# AI 生成英语播客视频

通过 AI 播客工作流，将文章文本生成简短的教学视频。

## 架构

所有 AI 能力仅使用两个服务商：

| 能力 | 服务商 | 模型 / 接口 |
|------|--------|-------------|
| **LLM**（脚本与关键词） | MiniMax | `MiniMax-M2.5`（`/v1/text/chatcompletion_v2`） |
| **TTS**（语音合成） | MiniMax | `speech-2.6-hd`（`/v1/t2a_v2`） |
| **生图**（素材） | apimart | `gemini-3.1-flash-image-preview`（`/v1/images/generations`） |

```text
文章 → MiniMax LLM（播客脚本）→ MiniMax LLM（关键词）
     → apimart（逐句生成一张图片）
     → MiniMax TTS（逐句生成一段语音）
     → ffmpeg（图片+语音 → 片段 → 拼接）
     → ffmpeg（混合背景音乐）
     → 最终视频
```

**不再使用 SiliconFlow。** LLM 与 TTS 均统一使用 MiniMax，生图使用 apimart。无需 Pexels / Pixabay 的 key。

## 功能特性

- 根据文章生成播客脚本（MiniMax LLM）
- 双说话人音色选择与试听（MiniMax TTS）
- 播客语音合成
- 逐句 AI 生图（apimart）
- 本地素材支持（传统方式，可选）
- 背景音乐：随机 / 指定曲目 / 无，带音量调节
- WebUI 与 HTTP API
- 竖屏视频输出
- **无字幕** —— 视频只包含图片 + 语音 + 音乐

## 环境要求

- Python 3.11
- FFmpeg + ffprobe（需在 PATH 中，WebUI 直接按名字调用 `ffmpeg` / `ffprobe`）
- **纯 CPU 运行** —— 无需 CUDA / GPU / torch，无需 ImageMagick，无需下载 Whisper 模型

## 快速开始

### 1. 克隆项目

```shell
git clone https://github.com/liangdabiao/AI-generated-English-podcast-videos.git
cd AI-generated-English-podcast-videos
```

### 2. 安装依赖

```shell
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 3. 配置密钥

复制示例配置并编辑：

```shell
copy config.example.toml config.toml  # Windows
# cp config.example.toml config.toml  # macOS/Linux
```

编辑 `config.toml` —— 只需要两个 key：

```toml
[MiniMax]
api_key = "你的-minimax-key"     # 必填：LLM（MiniMax-M2.5）+ TTS（speech-2.6-hd）
llm_model = "MiniMax-M2.5"
tts_model = "speech-2.6-hd"

[apimart]
api_key = "你的-apimart-key"     # 必填：生图（gemini-3.1-flash-image-preview）
```

`[siliconflow]` 段已弃用，不再使用。无需 Pexels / Pixabay 的 key。

可选的 API 鉴权（用于对外暴露 HTTP API 时）：

- 设置 `auth_enabled = true`
- 设置 `api_key` 为一串足够长的随机字符串
- 调用时通过 HTTP 头 `x-api-key` 传入

> 安全提醒：如果某个 key 曾经被提交或分享过，请务必到服务商控制台**轮换 / 撤销**它——仅从后续提交中删除，并不能把它从 git 历史中移除。

### 4. 验证环境

```shell
ffmpeg -version
ffprobe -version
```

两者都必须能在 PATH 中找到。如果没有，请把 FFmpeg 的 `bin` 目录加到 PATH（WebUI 是直接按名字调用 `ffmpeg` / `ffprobe` 的）。

### 5. 启动 WebUI

```shell
streamlit run webui/Main.py --server.address=0.0.0.0 --server.port=8501
```

打开：

```text
http://127.0.0.1:8501
```

### 6. 启动 API

```shell
python main.py
```

API 文档：

```text
http://127.0.0.1:8080/docs
```

## WebUI 使用流程

1. 粘贴文章文本。
2. 选择对话人 1（女声）和对话人 2（男声）—— 默认为 MiniMax 英文音色。
3. 选择背景音乐：随机 / 指定曲目 / 无，并调节音乐音量，可试听选定曲目。
4. 点击生成。每句话会生成一张 AI 图片 + 一段 TTS 语音；片段拼接后混入背景音乐。

## 音色列表

MiniMax 英文音色（T2A V2，已验证可用）：
- `English_PassionateWarrior`（女声）
- `English_Graceful_Lady`（女声）
- `English_Cute_Girl`（女声）
- `English_Trustworth_Man`（男声）

## 背景音乐

音乐文件位于 `resource/songs/`（内置 29 个 mp3）。可选择随机，或在"指定曲目"模式下挑选某一首。

## 字幕

本版本**不渲染字幕轨**。视频只包含图片 + 语音 + 音乐。

## Docker

先创建 `config.toml`，然后运行：

```shell
docker compose up
```

WebUI：

```text
http://127.0.0.1:8501
```

API 文档：

```text
http://127.0.0.1:8080/docs
```

## API 流程

### 生成播客脚本

`POST /api/v1/scripts`

```json
{
  "article_text": "在此粘贴文章...",
  "language": "English",
  "speaker_1_voice": "MiniMax:speech-2.6-hd:English_Graceful_Lady-Female",
  "speaker_2_voice": "MiniMax:speech-2.6-hd:English_Trustworth_Man-Male"
}
```

### 生成素材关键词

`POST /api/v1/terms`

```json
{
  "podcast_script": [
    {
      "speaker_1": "Welcome to today's episode...",
      "speaker_2": "Let's explore the topic...",
      "speaker_1_voice": "MiniMax:speech-2.6-hd:English_Graceful_Lady-Female",
      "speaker_2_voice": "MiniMax:speech-2.6-hd:English_Trustworth_Man-Male"
    }
  ],
  "amount": 4
}
```

### 生成视频

`POST /api/v1/videos`

```json
{
  "article_text": "在此粘贴文章...",
  "podcast_script": [
    {
      "speaker_1": "Welcome to today's episode...",
      "speaker_2": "Let's explore the topic...",
      "speaker_1_voice": "MiniMax:speech-2.6-hd:English_Graceful_Lady-Female",
      "speaker_2_voice": "MiniMax:speech-2.6-hd:English_Trustworth_Man-Male"
    }
  ],
  "video_terms": "podcast studio, technology, city life",
  "video_source": "MiniMax",
  "video_aspect": "9:16",
  "video_count": 1
}
```

若开启了 `auth_enabled = true`，请求需带：

```text
x-api-key: 你的-api-key
```

## 测试

本地语法检查：

```shell
python -m compileall app webui
```

单元测试（不含联网集成测试）：

```shell
python -m pytest -q
```

调用真实外部服务或启动本地服务器的集成测试，默认标记为 `integration` 并跳过。只有在配置好 key 且授权真实外部调用后，才运行：

```shell
python -m pytest -q -m integration
```

配置好 key 后建议的真实验证步骤：

1. WebUI：粘贴文章 → 生成播客对话 → 试听两个音色 → 生成视频。
2. API：依次调用 `/api/v1/scripts`、`/api/v1/terms`、`/api/v1/videos`。
3. 安全检查：
   - `/api/v1/stream/../../config.toml` 应失败。
   - `/api/v1/download/../../config.toml` 应失败。
   - BGM 上传可疑文件名时，应被保存为安全生成的文件名。
   - 若 `auth_enabled = true`，不带 `x-api-key` 的请求应返回 401。

## 备注

- 本项目已是纯播客模式。`video_subject`、传统 `video_script`、`podcast_mode`、`voice_name`、`paragraph_number` 等遗留字段已不在请求 schema 中。
- `video_terms` 仍作为素材搜索关键词字段保留，以兼容现有内部逻辑。
- 除在可信本地代理下调试外，请保持 `verify_ssl = true`。

## 许可证

详见 [`LICENSE`](LICENSE)。

## 🙏 致谢

- [MiniMax](https://platform.minimaxi.com/) - LLM 与 TTS 服务
- [apimart](https://apimart.ai/) - Gemini 图片生成服务
- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) - 项目参考
- [linuxdo](https://linux.do/) - linux.do 佬友
