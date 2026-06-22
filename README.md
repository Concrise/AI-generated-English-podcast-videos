# AI-generated-English-podcast-videos 📚

<div align="center">

**一键将英文文章转换为教育短视频** - 自动生成双人对话、语音讲解、教育图片，合成高清视频

</div>

---

## ✨ 功能特性

- 🎯 **全自动流程**: 文章 → 对话脚本 → 教育图片 → 语音音频 → 视频合成
- 🎨 **教育图片**: 使用 Gemini-3 生成中小学英语课本风格的图片（句子置顶、关键词音标、彩色插图）
- 🔊 **语音合成**: SiliconFlow TTS 生成的英文语音，支持 anna（女声）和 benjamin（男声）
- 🎬 **智能同步**: 每个对话片段的音频与对应图片精确匹配
- 📐 **多种尺寸**: 支持竖屏（9:16）和横屏（16:9）视频输出
- 🌐 **Web界面**: 简洁易用的网页界面，一键生成视频
- ⚙️ **配置简单**: 所有配置集中在 config.toml，无需在界面配置

## 🛠️ 技术架构

| 模块 | 技术 |
|------|------|
| 对话生成 | SiliconFlow API (LLM) |
| 图片生成 | apimart Gemini-3 |
| 语音合成 | SiliconFlow TTS (CosyVoice2-0.5B) |
| 视频合成 | ffmpeg + MoviePy |
| Web界面 | Streamlit |

## 🚀 快速开始

### 1. 克隆代码

```bash
git clone https://github.com/liangdabiao/AI-generated-English-podcast-videos.git
cd AI-generated-English-podcast-videos
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

复制配置文件并填写您的 API Key：

```bash
copy config.example.toml config.toml
```

编辑 `config.toml`：

```toml
[siliconflow]
api_key = "your-siliconflow-api-key"  # LLM + TTS

[apimart]
api_key = "your-apimart-api-key"  # 图片生成
```

**API Key 申请地址：**
- SiliconFlow: https://cloud.siliconflow.cn/
- apimart: https://apimart.ai/keys

### 4. 运行 Web 界面

```bash
cd webui
streamlit run Main.py --server.port 8501
```

打开浏览器访问 http://localhost:8501

### 5. 生成视频

1. 输入英文文章（或点击"使用示例文章"）
2. 点击"开始生成视频"
3. 等待生成完成，预览并下载视频

## 📁 项目结构

```
AI-generated-English-podcast-videos/
├── app/
│   ├── config.py          # 配置管理
│   ├── models/            # 数据模型
│   │   └── schema.py
│   └── services/
│       ├── llm.py         # LLM 对话生成
│       ├── voice.py       # 语音合成
│       ├── image_generator.py  # 图片生成
│       ├── video.py       # 视频合成
│       └── podcast_audio.py    # 播客音频
├── webui/
│   └── Main.py            # Web 界面
├── config.toml            # 配置文件
├── config.example.toml     # 配置示例
└── requirements.txt       # 依赖列表
```

## 🔧 配置说明

### 配置文件结构

```toml
[siliconflow]
api_key = "your-siliconflow-api-key"  # LLM + TTS

[apimart]
api_key = "your-apimart-api-key"  # 图片生成

[app.podcast]
default_speaker_1_voice = "siliconflow:FunAudioLLM/CosyVoice2-0.5B:anna-Female"
default_speaker_2_voice = "siliconflow:FunAudioLLM/CosyVoice2-0.5B:benjamin-Male"
```

### 视频尺寸

- 竖屏: 9:16 (1080x1920)
- 横屏: 16:9 (1920x1080)

## 🎬 工作流程

```
┌─────────────┐
│  输入文章    │
└──────┬──────┘
       ▼
┌─────────────────┐
│  生成双人对话脚本  │
│  (Speaker 1/2)  │
└──────┬──────────┘
       ▼
┌─────────────────┐     ┌─────────────────┐
│  生成教育图片    │     │  生成语音音频    │
│  (apimart)      │     │  (SiliconFlow)  │
└──────┬──────────┘     └──────┬──────────┘
       ▼                       ▼
┌─────────────────────────────────────┐
│  视频合成：图片与音频精确匹配         │
│  每个对话片段时长 = 对应图片显示时长   │
└────────────────┬────────────────────┘
                 ▼
          ┌───────────┐
          │  最终视频  │
          └───────────┘
```

## 📝 示例输出

### 输入文章

```
The Dragon Boat Festival is a traditional Chinese holiday...
```

### 生成对话

```
Speaker 1: Welcome to our English learning podcast! Today we're talking about the Dragon Boat Festival.

Speaker 2: That sounds exciting! When is the Dragon Boat Festival celebrated?

Speaker 1: It's on the fifth day of the fifth lunar month. People gather along rivers to watch dragon boat races.
```

### 生成视频

- 每段对话对应一张教育图片
- 图片显示时长 = 对话音频时长
- 自动拼接成最终视频

## 🔍 常见问题

### Q: 图片生成失败？

1. 检查 apimart API Key 是否正确配置
2. 检查 apimart 账户余额是否充足
3. 查看日志中的详细错误信息

### Q: 视频合成失败？

1. 确保 ffmpeg 已安装并添加到 PATH
2. 检查生成的图片和音频文件是否完整
3. 查看日志中的详细错误信息

### Q: 语音合成失败？

1. 检查 SiliconFlow API Key 是否正确配置
2. 检查账户余额是否充足
3. 确认网络连接正常

## 📄 许可证

MIT License

## 🙏 致谢

- [SiliconFlow](https://cloud.siliconflow.cn/) - LLM 和 TTS 服务
- [apimart](https://apimart.ai/) - Gemini 图片生成服务
- [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) - 项目参考
