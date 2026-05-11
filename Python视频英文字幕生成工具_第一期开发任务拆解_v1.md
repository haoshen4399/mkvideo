# Python 视频英文字幕生成工具第一期开发任务拆解文档

> 版本：v1.0  
> 依据文档：Python 视频英文字幕生成工具需求文档 v2.3 第一完整基础闭环版  
> 开发环境：Windows 10 + Python 3.12.1 + PyCharm  
> 硬件环境：Intel i9-14900K / i9-19400K 级别 CPU、32GB 内存、NVIDIA RTX4060  
> 第一阶段目标：完成“视频分离音频 → 音频转中文字幕 → AI 检查中文字幕 → AI 翻译英文字幕 → 视频截图定位字幕位置 → 英文字幕合成进视频 → 输出中文字幕、英文字幕、成品视频”的完整基础闭环。  

---

# 一、第一期目标说明

第一期不是做一个“只生成字幕”的小工具，而是要完成一个可以实际使用的基础闭环。

核心流程如下：

```text
输入中文视频
  ↓
视频基础校验
  ↓
分离/提取音频
  ↓
音频转中文字幕
  ↓
中文字幕后处理
  ↓
AI 检查中文字幕
  ↓
AI 理解整体字幕语义
  ↓
AI 翻译英文字幕
  ↓
英文字幕规则校验
  ↓
视频截图/抽帧
  ↓
分析字幕适合放置的位置
  ↓
生成 ASS 字幕文件
  ↓
将英文字幕合并进视频
  ↓
输出中文字幕、英文字幕、合并后视频
```

第一期最少必须输出：

```text
zh_ai_checked.srt          # AI 检查后的中文字幕
en_checked.srt             # 最终英文字幕
final_en_subtitled.mp4      # 合并英文字幕后的视频
```

同时必须保留每个步骤的中间产物，方便调试、复用和断点续跑。

---

# 二、开发环境建议

## 2.1 本机环境

| 项目 | 配置 |
|---|---|
| 操作系统 | Windows 10 |
| Python | 3.12.1 |
| IDE | PyCharm |
| CPU | Intel i9-14900K / i9-19400K 级别 |
| 内存 | 32GB |
| GPU | NVIDIA RTX4060 |
| CUDA | 建议安装与 PyTorch 匹配的 CUDA 版本 |
| 视频处理 | FFmpeg |
| ASR | faster-whisper 默认，openai-whisper 备用 |
| 大模型 API | OpenAI-compatible 网关 |

## 2.2 Python 版本说明

Python 3.12.1 可以用于该项目，但要注意：

1. `faster-whisper`、`ctranslate2`、`torch` 等依赖需要确认支持 Python 3.12；
2. 如果安装依赖遇到兼容问题，建议准备一个 Python 3.11.8 备用虚拟环境；
3. PyCharm 中建议为本项目单独创建虚拟环境；
4. 不建议使用系统 Python 直接开发。

## 2.3 推荐 PyCharm 项目目录

```text
video_subtitle_tool/
  main.py
  requirements-base.txt
  requirements-asr.txt
  requirements-dev.txt
  .env
  README.md

  app/
  core/
  engines/
  providers/
  utils/
  configs/
  prompts/
  tests/

  input/
  output/
  work/
```

---

# 三、第一期推荐技术选型

## 3.1 核心技术栈

| 模块 | 技术 |
|---|---|
| 视频检测 | FFmpeg / ffprobe |
| 音频提取 | FFmpeg |
| ASR | faster-whisper |
| 备用 ASR | openai-whisper |
| 字幕处理 | pysubs2 |
| AI 调用 | openai SDK / requests，OpenAI-compatible |
| 视频截图 | OpenCV |
| 字幕渲染 | ASS |
| 视频合成 | FFmpeg |
| 配置文件 | YAML |
| 环境变量 | python-dotenv |
| 日志 | loguru |
| 断点续跑 | task_state.json |

## 3.2 第一阶段不建议强制做的内容

| 内容 | 原因 |
|---|---|
| Demucs 高质量人声分离 | 耗时高，第一期先提取音频即可 |
| AI 视觉大模型定位字幕 | 第一阶段用 OpenCV + 规则即可 |
| 成品 5 帧 AI 质检 | 放第二期 |
| Web UI | 第一阶段先 CLI |
| 多语言翻译 | 第一阶段只做中文到英文 |
| 英文 TTS 配音 | 放后续扩展 |

---

# 四、推荐项目目录结构

```text
video_subtitle_tool/
  main.py

  app/
    cli.py
    config_loader.py
    pipeline.py
    task_state.py
    context.py

  core/
    video_probe.py
    audio_extractor.py
    subtitle_postprocessor.py
    zh_ai_checker.py
    translator.py
    subtitle_validator.py
    position_analyzer.py
    ass_builder.py
    video_renderer.py

  engines/
    faster_whisper_engine.py
    openai_whisper_engine.py

  providers/
    llm_base.py
    openai_compatible_provider.py

  utils/
    ffmpeg_utils.py
    file_utils.py
    log_utils.py
    srt_utils.py
    json_utils.py
    time_utils.py

  configs/
    config.example.yaml

  prompts/
    zh_check.txt
    translate_en.txt

  tests/
    test_video_probe.py
    test_audio_extractor.py
    test_srt_utils.py
    test_ass_builder.py

  input/
  output/
  work/
```

---

# 五、第一期开发任务总览

| 阶段 | 任务 | 目标产物 |
|---|---|---|
| 0 | 环境准备 | 可运行的 PyCharm 项目 |
| 1 | 项目骨架与配置 | main.py、config.yaml、日志、状态文件 |
| 2 | 视频检测 | video_info.json |
| 3 | 音频提取 | original.wav |
| 4 | 音频转中文字幕 | zh_raw.srt |
| 5 | 中文字幕后处理 | zh_clean.srt |
| 6 | AI 检查中文字幕 | zh_ai_checked.srt、zh_check_report.json |
| 7 | AI 翻译英文字幕 | en_raw.srt |
| 8 | 英文字幕规则校验 | en_checked.srt、en_check_report.json |
| 9 | 视频截图与字幕位置分析 | frame_001.jpg、subtitle_position.json |
| 10 | ASS 字幕生成 | english.ass / bilingual.ass |
| 11 | 英文字幕合并视频 | final_en_subtitled.mp4 |
| 12 | 断点续跑 | task_state.json |
| 13 | 集成测试 | 完整跑通一个视频 |

---

# 六、任务 0：环境准备

## 6.1 目标

在 Windows 10 + PyCharm + Python 3.12.1 环境下准备可开发、可调试的工程环境。

## 6.2 具体任务

1. 安装 Python 3.12.1；
2. 安装 PyCharm；
3. 创建项目目录；
4. 创建虚拟环境；
5. 安装 FFmpeg；
6. 配置 FFmpeg 到系统 PATH；
7. 安装 NVIDIA 显卡驱动；
8. 安装 PyTorch GPU 版本；
9. 验证 CUDA 是否可用；
10. 创建 `.env` 文件；
11. 创建 `config.example.yaml`。

## 6.3 推荐依赖拆分

### requirements-base.txt

```text
requests>=2.31.0
python-dotenv>=1.0.0
loguru>=0.7.2
tqdm>=4.66.0
pydantic>=2.0.0
PyYAML>=6.0.1
ffmpeg-python>=0.2.0
pysubs2>=1.6.0
opencv-python>=4.8.1.78
openai>=1.40.0
```

### requirements-asr.txt

```text
torch
torchaudio
faster-whisper>=1.0.0
```

### requirements-optional-whisper.txt

```text
openai-whisper>=20231117
```

## 6.4 验收标准

```text
python --version 能显示 3.12.1
ffmpeg -version 可正常输出
nvidia-smi 可看到 RTX4060
PyCharm 能正常运行 main.py
```

---

# 七、任务 1：项目骨架与配置系统

## 7.1 目标

搭建基础工程结构，支持配置文件、日志、输出目录、任务上下文和状态记录。

## 7.2 需要开发的文件

```text
main.py
app/cli.py
app/config_loader.py
app/pipeline.py
app/task_state.py
app/context.py
utils/log_utils.py
utils/file_utils.py
configs/config.example.yaml
```

## 7.3 功能要求

### 7.3.1 CLI 参数

支持以下命令：

```bash
python main.py --input ./input/demo.mp4 --output ./output
python main.py --input ./input/demo.mp4 --output ./output --resume
python main.py --input ./input/demo.mp4 --output ./output --start-from translate
python main.py --input ./input/demo.mp4 --output ./output --config ./configs/config.yaml
```

### 7.3.2 配置文件

第一期配置必须包含：

```yaml
app:
  mode: standard
  keep_intermediate: true
  max_video_minutes: 10
  resume: true

llm_providers:
  default:
    type: openai_compatible
    base_url: "https://openai.5054399.com/siliconflow/v1"
    api_key_env: "SILICONFLOW_API_KEY"
    default_model: "deepseek-ai/DeepSeek-V3.2"
    timeout: 180
    max_retries: 2

steps:
  probe_video:
    enabled: true

  extract_audio:
    enabled: true
    sample_rate: 16000
    channels: 1

  asr:
    enabled: true
    engine: faster-whisper
    fallback_engine: openai-whisper
    model: large-v3
    fallback_model: medium
    language: zh
    device: auto
    compute_type: auto

  zh_ai_check:
    enabled: true
    provider: default
    model: deepseek-ai/DeepSeek-V3.2

  translate:
    enabled: true
    provider: default
    model: deepseek-ai/DeepSeek-V3.2
    target_lang: en
    strategy: understand_full_context_first

  screenshot_position:
    enabled: true
    engine: opencv
    sample_count: 3

  render_video:
    enabled: true
    engine: ffmpeg
    crf: 20
    preset: medium
```

### 7.3.3 任务上下文

建议创建 `TaskContext`：

```python
class TaskContext:
    input_video: str
    output_dir: str
    work_dir: str
    video_info_path: str
    original_audio_path: str
    zh_raw_srt_path: str
    zh_clean_srt_path: str
    zh_ai_checked_srt_path: str
    en_raw_srt_path: str
    en_checked_srt_path: str
    subtitle_position_path: str
    ass_path: str
    final_video_path: str
    task_state_path: str
```

## 7.4 输出产物

```text
output/demo/
  task_state.json
  task_config_snapshot.yaml
  logs/run.log
```

## 7.5 验收标准

1. 命令行参数可解析；
2. 配置文件可读取；
3. `.env` 可读取 API Key；
4. 输出目录能自动创建；
5. `task_state.json` 能初始化；
6. 日志能写入文件。

---

# 八、任务 2：视频检测模块

## 8.1 目标

读取输入视频，检测视频基本信息，判断是否符合处理要求。

## 8.2 需要开发的文件

```text
core/video_probe.py
utils/ffmpeg_utils.py
```

## 8.3 输入

```text
input/demo.mp4
```

## 8.4 输出

```text
reports/video_info.json
```

## 8.5 检测内容

1. 文件是否存在；
2. 文件格式是否支持；
3. 视频时长；
4. 是否超过最大时长；
5. 是否存在音频流；
6. 视频分辨率；
7. 视频帧率；
8. 视频编码；
9. 音频编码；
10. 文件大小。

## 8.6 video_info.json 示例

```json
{
  "filename": "demo.mp4",
  "duration": 358.2,
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "has_audio": true,
  "video_codec": "h264",
  "audio_codec": "aac",
  "valid": true
}
```

## 8.7 验收标准

1. 正常视频能生成 `video_info.json`；
2. 无音频视频能给出明确错误；
3. 超过时长限制能给出明确错误；
4. 不支持格式能给出明确错误；
5. 检测失败不导致程序崩溃。

---

# 九、任务 3：视频分离/提取音频

## 9.1 目标

从视频中提取音频，转换为 ASR 可识别的 WAV 格式。

## 9.2 需要开发的文件

```text
core/audio_extractor.py
utils/ffmpeg_utils.py
```

## 9.3 输入

```text
input/demo.mp4
```

## 9.4 输出

```text
audio/original.wav
```

## 9.5 处理要求

1. 使用 FFmpeg；
2. 输出 WAV；
3. 采样率默认 16000Hz；
4. 单声道；
5. 适配 faster-whisper；
6. 保留日志；
7. 如果音频已存在且 overwrite=false，则跳过。

## 9.6 推荐 FFmpeg 命令

```bash
ffmpeg -y -i input.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 original.wav
```

## 9.7 验收标准

1. 能从 MP4 提取 WAV；
2. WAV 可播放；
3. WAV 采样率为 16000；
4. WAV 为单声道；
5. 出错时写入 `logs/ffmpeg.log`；
6. 产物路径写入 `task_state.json`。

---

# 十、任务 4：音频转中文字幕

## 10.1 目标

使用 faster-whisper 将音频转换为中文字幕 SRT。

## 10.2 需要开发的文件

```text
engines/faster_whisper_engine.py
engines/openai_whisper_engine.py
core/asr_engine.py
utils/srt_utils.py
```

## 10.3 输入

```text
audio/original.wav
```

## 10.4 输出

```text
subtitles/zh_raw.srt
reports/asr_report.json
```

## 10.5 ASR 推荐配置

由于机器为 RTX4060 + 32GB 内存，建议：

```yaml
asr:
  engine: faster-whisper
  model: large-v3
  fallback_model: medium
  device: cuda
  compute_type: float16
  language: zh
```

如果 large-v3 显存不够或速度过慢，切换为：

```yaml
model: medium
compute_type: float16
```

如果 CUDA 异常，切换为：

```yaml
device: cpu
compute_type: int8
model: medium
```

## 10.6 SRT 输出要求

```text
1
00:00:01,200 --> 00:00:03,800
大家好，欢迎来到今天的视频。

2
00:00:04,000 --> 00:00:06,500
我们来看一下这个工具怎么使用。
```

## 10.7 验收标准

1. 能输出合法 `zh_raw.srt`；
2. 字幕有序号；
3. 时间戳格式正确；
4. 时间戳不为空；
5. 中文内容不为空；
6. ASR 执行耗时写入 `asr_report.json`；
7. faster-whisper 失败时可配置回退 openai-whisper。

---

# 十一、任务 5：中文字幕规则后处理

## 11.1 目标

对 ASR 生成的 `zh_raw.srt` 做基础规则修复，输出更稳定的 `zh_clean.srt`。

## 11.2 需要开发的文件

```text
core/subtitle_postprocessor.py
utils/srt_utils.py
```

## 11.3 输入

```text
subtitles/zh_raw.srt
```

## 11.4 输出

```text
subtitles/zh_clean.srt
reports/zh_postprocess_report.json
```

## 11.5 处理规则

1. 删除空字幕；
2. 修复序号；
3. 修复时间戳重叠；
4. 修复开始时间大于结束时间；
5. 合并显示时间过短的字幕；
6. 限制单条字幕最长显示时间；
7. 统一中文标点；
8. 保留原始语义，不做大幅改写。

## 11.6 推荐参数

```yaml
zh_subtitle_postprocess:
  min_duration_ms: 800
  max_duration_ms: 7000
  fix_overlap: true
  remove_empty: true
  merge_short_subtitle: true
```

## 11.7 验收标准

1. 能输出 `zh_clean.srt`；
2. 序号连续；
3. 无空字幕；
4. 无明显时间戳重叠；
5. SRT 可被 pysubs2 读取；
6. 修复记录写入报告。

---

# 十二、任务 6：AI 检查中文字幕

## 12.1 目标

调用大模型检查并修正 `zh_clean.srt`，防止 ASR 错误进入英文翻译。

## 12.2 需要开发的文件

```text
core/zh_ai_checker.py
providers/llm_base.py
providers/openai_compatible_provider.py
prompts/zh_check.txt
```

## 12.3 输入

```text
subtitles/zh_clean.srt
```

## 12.4 输出

```text
subtitles/zh_ai_checked.srt
reports/zh_check_report.json
logs/llm_zh_check.log
```

## 12.5 AI 检查范围

1. 错别字；
2. 同音字误识别；
3. 多字；
4. 漏字；
5. 语义不通顺；
6. 上下文矛盾；
7. 明显断句错误；
8. SRT 格式是否被破坏。

## 12.6 AI 输出要求

建议让 AI 输出 JSON + 修正后的 SRT：

```json
{
  "passed": true,
  "error_count": 1,
  "errors": [
    {
      "index": 3,
      "type": "typo",
      "original": "原字幕",
      "suggestion": "修正字幕",
      "reason": "同音字识别错误"
    }
  ],
  "fixed_srt": "完整修正后的 SRT 内容"
}
```

## 12.7 大模型配置

```yaml
llm_providers:
  default:
    type: openai_compatible
    base_url: "https://openai.5054399.com/siliconflow/v1"
    api_key_env: "SILICONFLOW_API_KEY"
    default_model: "deepseek-ai/DeepSeek-V3.2"
    timeout: 180
    max_retries: 2
```

## 12.8 验收标准

1. 能调用大模型；
2. 能读取 `.env` 中的 API Key；
3. 能输出 `zh_ai_checked.srt`；
4. 能输出 `zh_check_report.json`；
5. AI 返回异常时能重试；
6. AI 返回格式异常时能记录错误；
7. 校验后的 SRT 仍然合法；
8. 不允许改变时间戳和序号。

---

# 十三、任务 7：AI 翻译英文字幕

## 13.1 目标

基于 AI 检查后的中文字幕，让 AI 先理解整体语义，再翻译为英文字幕。

## 13.2 需要开发的文件

```text
core/translator.py
providers/openai_compatible_provider.py
prompts/translate_en.txt
```

## 13.3 输入

优先输入：

```text
subtitles/zh_ai_checked.srt
```

备用输入：

```text
subtitles/zh_clean.srt
```

## 13.4 输出

```text
subtitles/en_raw.srt
reports/translation_report.json
logs/llm_translate.log
```

## 13.5 翻译要求

1. 先理解整段中文字幕；
2. 再逐条输出英文字幕；
3. 保持字幕序号不变；
4. 保持时间戳不变；
5. 保持字幕条数一致；
6. 英文表达自然；
7. 符合美国人日常表达习惯；
8. 不增加原文没有的信息；
9. 不删除原文核心含义；
10. 输出标准 SRT。

## 13.6 验收标准

1. 能输出 `en_raw.srt`；
2. 英文字幕条数与中文字幕一致；
3. 时间戳一致；
4. 无 Markdown 包裹；
5. 无多余解释；
6. 大模型失败时可重试；
7. 翻译日志可追踪。

---

# 十四、任务 8：英文字幕规则校验

## 14.1 目标

对 AI 输出的英文字幕进行程序规则校验，避免格式错误进入视频渲染。

## 14.2 需要开发的文件

```text
core/subtitle_validator.py
utils/srt_utils.py
```

## 14.3 输入

```text
subtitles/en_raw.srt
subtitles/zh_ai_checked.srt
```

## 14.4 输出

```text
subtitles/en_checked.srt
reports/en_check_report.json
```

## 14.5 校验规则

1. SRT 是否可解析；
2. 序号是否连续；
3. 条数是否与中文字幕一致；
4. 时间戳是否与中文字幕一致；
5. 是否存在空字幕；
6. 是否存在乱码；
7. 单条是否超过 2 行；
8. 单行是否超过 42 个英文字符；
9. CPS 是否超过 17；
10. 是否存在时间戳重叠。

## 14.6 验收标准

1. 能输出 `en_checked.srt`；
2. 格式错误能被发现；
3. 条数不一致能被发现；
4. 时间戳不一致能被发现；
5. 报告中能列出错误位置；
6. 校验通过后可进入 ASS 生成。

---

# 十五、任务 9：视频截图与字幕位置分析

## 15.1 目标

对原视频进行截图/抽帧，分析英文字幕适合放置的位置，输出字幕位置配置。

## 15.2 需要开发的文件

```text
core/position_analyzer.py
```

## 15.3 输入

```text
input/demo.mp4
reports/video_info.json
```

## 15.4 输出

```text
position/screenshots/frame_001.jpg
position/screenshots/frame_002.jpg
position/screenshots/frame_003.jpg
position/subtitle_position.json
```

## 15.5 截图策略

第一期建议截取：

1. 视频 10% 位置；
2. 视频 50% 位置；
3. 视频 90% 位置。

或者：

```text
start_middle_end
```

## 15.6 OpenCV 分析规则

第一期采用简单规则即可：

| 情况 | 策略 |
|---|---|
| 底部区域较干净 | bottom_center |
| 底部存在明显字幕/文字 | bottom_center_up |
| 底部过亮 | 加粗黑边 |
| 底部过暗 | 白字黑边 |
| 无法判断 | bottom_center |

## 15.7 subtitle_position.json 示例

```json
{
  "position": "bottom_center",
  "margin_v": 80,
  "font_size_en": 32,
  "font_color": "white",
  "outline_color": "black",
  "outline_width": 2,
  "shadow": 1,
  "sample_frames": [
    "frame_001.jpg",
    "frame_002.jpg",
    "frame_003.jpg"
  ],
  "reason": "bottom area is readable and no obvious existing subtitle detected"
}
```

## 15.8 验收标准

1. 能截取 3 张截图；
2. 能输出 `subtitle_position.json`；
3. 视频时长不同也能正常截图；
4. 位置配置能被 ASS 生成模块读取；
5. OpenCV 失败时使用默认底部居中。

---

# 十六、任务 10：ASS 字幕生成

## 16.1 目标

将英文字幕和字幕位置配置转换为 ASS 文件，供 FFmpeg 烧录。

## 16.2 需要开发的文件

```text
core/ass_builder.py
```

## 16.3 输入

```text
subtitles/en_checked.srt
position/subtitle_position.json
```

可选输入：

```text
subtitles/zh_ai_checked.srt
```

## 16.4 输出

```text
subtitles/english.ass
subtitles/bilingual.ass
```

## 16.5 字幕模式

第一期建议默认：

```text
en_only
```

也支持：

```text
bilingual
```

## 16.6 ASS 样式要求

1. 白字；
2. 黑色描边；
3. 底部居中；
4. 字号根据分辨率配置；
5. 支持 margin_v；
6. 支持英文单独显示；
7. 支持中英双语显示。

## 16.7 验收标准

1. 能生成 `english.ass`；
2. ASS 文件可被 FFmpeg 读取；
3. 字幕时间与 SRT 一致；
4. 字幕样式符合配置；
5. 支持英文字幕模式；
6. 支持双语字幕模式。

---

# 十七、任务 11：英文字幕合并进视频

## 17.1 目标

使用 FFmpeg 将 ASS 字幕烧录进原视频，输出最终成品视频。

## 17.2 需要开发的文件

```text
core/video_renderer.py
utils/ffmpeg_utils.py
```

## 17.3 输入

```text
input/demo.mp4
subtitles/english.ass
```

## 17.4 输出

```text
render/final_en_subtitled.mp4
reports/render_report.json
logs/ffmpeg.log
```

## 17.5 推荐 FFmpeg 方案

```bash
ffmpeg -y -i input.mp4 -vf "ass=english.ass" -c:v libx264 -crf 20 -preset medium -c:a copy final_en_subtitled.mp4
```

如音频编码兼容问题，改为：

```bash
ffmpeg -y -i input.mp4 -vf "ass=english.ass" -c:v libx264 -crf 20 -preset medium -c:a aac final_en_subtitled.mp4
```

## 17.6 输出要求

1. 保持原分辨率；
2. 保持原帧率；
3. 字幕烧录进画面；
4. 输出 MP4；
5. 视频可被 VLC / PotPlayer 播放；
6. 字幕不需要额外加载。

## 17.7 验收标准

1. 能输出 `final_en_subtitled.mp4`；
2. 视频能播放；
3. 英文字幕能显示；
4. 字幕时间与语音基本同步；
5. 音频正常；
6. 渲染失败能记录日志；
7. 渲染结果写入 `task_state.json`。

---

# 十八、任务 12：断点续跑与步骤调度

## 18.1 目标

实现 Pipeline 调度机制，使每个步骤可独立执行、失败可恢复。

## 18.2 需要开发的文件

```text
app/pipeline.py
app/task_state.py
app/context.py
```

## 18.3 步骤顺序

第一期固定顺序：

```text
probe_video
extract_audio
asr
zh_postprocess
zh_ai_check
translate
en_check
screenshot_position
build_ass
render_video
```

## 18.4 task_state.json 示例

```json
{
  "video": "demo.mp4",
  "status": "running",
  "last_success_step": "translate",
  "failed_step": null,
  "steps": {
    "probe_video": "success",
    "extract_audio": "success",
    "asr": "success",
    "zh_postprocess": "success",
    "zh_ai_check": "success",
    "translate": "success",
    "en_check": "pending",
    "screenshot_position": "pending",
    "build_ass": "pending",
    "render_video": "pending"
  }
}
```

## 18.5 支持命令

```bash
python main.py --input ./input/demo.mp4 --output ./output --resume
python main.py --input ./input/demo.mp4 --output ./output --start-from translate
python main.py --input ./input/demo.mp4 --output ./output --start-from render_video
```

## 18.6 验收标准

1. 每一步成功后更新状态；
2. 每一步失败后记录错误；
3. `--resume` 能从失败步骤继续；
4. `--start-from` 能从指定步骤开始；
5. 已成功步骤默认不重复执行；
6. 设置 overwrite=true 时可重新执行。

---

# 十九、任务 13：完整集成测试

## 19.1 目标

用一个真实中文视频跑完整流程，验证第一期闭环可用。

## 19.2 测试输入

建议准备 3 类视频：

| 视频 | 说明 |
|---|---|
| demo_clear.mp4 | 人声清晰，无背景音乐 |
| demo_music.mp4 | 有背景音乐 |
| demo_subtitle.mp4 | 原视频底部已有中文字幕 |

## 19.3 测试命令

```bash
python main.py --input ./input/demo_clear.mp4 --output ./output
```

## 19.4 验收文件

```text
output/demo_clear/
  audio/original.wav
  subtitles/zh_raw.srt
  subtitles/zh_clean.srt
  subtitles/zh_ai_checked.srt
  subtitles/en_raw.srt
  subtitles/en_checked.srt
  position/screenshots/frame_001.jpg
  position/screenshots/frame_002.jpg
  position/screenshots/frame_003.jpg
  position/subtitle_position.json
  subtitles/english.ass
  render/final_en_subtitled.mp4
  reports/video_info.json
  reports/asr_report.json
  reports/zh_check_report.json
  reports/translation_report.json
  reports/en_check_report.json
  reports/render_report.json
  logs/run.log
  logs/ffmpeg.log
  task_state.json
```

## 19.5 集成验收标准

1. 全流程可跑通；
2. 输出中文字幕；
3. 输出英文字幕；
4. 输出合并英文字幕的视频；
5. 每一步中间产物存在；
6. 日志能定位问题；
7. 断点续跑可用；
8. 英文字幕显示位置合理；
9. 视频音频正常；
10. 视频可播放。

---

# 二十、开发优先级建议

## 20.1 第一优先级：必须先做

```text
1. 项目骨架
2. 视频检测
3. 音频提取
4. faster-whisper 生成中文字幕
5. 中文字幕后处理
6. AI 中文字幕检查
7. AI 英文翻译
8. 英文字幕规则校验
9. ASS 字幕生成
10. FFmpeg 合成视频
```

## 20.2 第二优先级：保证工程稳定

```text
1. 断点续跑
2. 日志系统
3. task_state.json
4. 配置快照
5. 错误处理
6. 失败重试
```

## 20.3 第三优先级：优化体验

```text
1. OpenCV 截图定位字幕位置
2. 字幕样式自动调整
3. 批量处理
4. 进度条
5. 简单测试用例
```

---

# 二十一、建议开发节奏

## 第 1 阶段：跑通本地视频到音频

目标：

```text
输入 mp4 → 输出 original.wav
```

完成任务：

```text
任务 0
任务 1
任务 2
任务 3
```

## 第 2 阶段：跑通音频到中文字幕

目标：

```text
original.wav → zh_raw.srt → zh_clean.srt
```

完成任务：

```text
任务 4
任务 5
```

## 第 3 阶段：跑通 AI 检查与翻译

目标：

```text
zh_clean.srt → zh_ai_checked.srt → en_raw.srt → en_checked.srt
```

完成任务：

```text
任务 6
任务 7
任务 8
```

## 第 4 阶段：跑通截图定位与字幕文件

目标：

```text
video.mp4 → screenshots → subtitle_position.json → english.ass
```

完成任务：

```text
任务 9
任务 10
```

## 第 5 阶段：合成视频

目标：

```text
video.mp4 + english.ass → final_en_subtitled.mp4
```

完成任务：

```text
任务 11
```

## 第 6 阶段：断点续跑与集成测试

目标：

```text
完整流程稳定运行，失败可恢复
```

完成任务：

```text
任务 12
任务 13
```

---

# 二十二、第一期最终验收清单

## 22.1 功能验收

| 编号 | 验收项 | 是否必须 |
|---|---|---|
| 1 | 能读取输入视频 | 必须 |
| 2 | 能检测视频信息 | 必须 |
| 3 | 能提取音频 original.wav | 必须 |
| 4 | 能生成 zh_raw.srt | 必须 |
| 5 | 能生成 zh_clean.srt | 必须 |
| 6 | 能生成 zh_ai_checked.srt | 必须 |
| 7 | 能生成 zh_check_report.json | 必须 |
| 8 | 能生成 en_raw.srt | 必须 |
| 9 | 能生成 en_checked.srt | 必须 |
| 10 | 能生成 en_check_report.json | 必须 |
| 11 | 能截图 3 张 | 必须 |
| 12 | 能生成 subtitle_position.json | 必须 |
| 13 | 能生成 english.ass | 必须 |
| 14 | 能生成 final_en_subtitled.mp4 | 必须 |
| 15 | 每一步有日志 | 必须 |
| 16 | 每一步有状态记录 | 必须 |
| 17 | 支持断点续跑 | 必须 |
| 18 | 支持从指定步骤开始 | 必须 |

## 22.2 质量验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| 1 | SRT 格式 | 可被播放器/库解析 |
| 2 | 中文字幕 | 不为空，时间戳正常 |
| 3 | 英文字幕 | 不为空，条数一致 |
| 4 | 字幕位置 | 不超出画面 |
| 5 | 合成视频 | 可播放 |
| 6 | 音频 | 正常播放 |
| 7 | 视频 | 无明显卡顿 |
| 8 | 日志 | 可定位失败步骤 |

---

# 二十三、风险与处理建议

| 风险 | 可能原因 | 处理建议 |
|---|---|---|
| faster-whisper 安装失败 | Python 3.12 兼容问题 | 准备 Python 3.11 备用环境 |
| large-v3 显存不足 | RTX4060 显存有限 | 切换 medium 或 int8 |
| FFmpeg 不可用 | PATH 未配置 | 启动前检测 ffmpeg |
| AI 返回格式不稳定 | 大模型输出不严格 | 加 JSON 解析和兜底逻辑 |
| 英文字幕条数不一致 | AI 改变 SRT 结构 | 翻译后做规则校验，不通过重试 |
| ASS 字幕乱码 | 字体或编码问题 | 使用 UTF-8 BOM 或指定中文字体 |
| FFmpeg 烧录失败 | 路径包含中文/空格 | 路径转义，尽量使用英文路径 |
| 视频底部已有字幕 | 位置冲突 | OpenCV 检测后上移 |
| 断点续跑混乱 | 状态记录不完整 | 每一步统一写 task_state.json |

---

# 二十四、最终开发建议

建议第一期不要一上来追求复杂 AI 视觉识别和人声分离，而是优先完成以下闭环：

```text
输入视频
→ 提取音频
→ faster-whisper 生成中文字幕
→ AI 检查中文字幕
→ AI 翻译英文字幕
→ OpenCV 截图定位字幕位置
→ ASS 生成英文字幕样式
→ FFmpeg 合成字幕视频
→ 输出最终视频
```

第一期最重要的是：

```text
稳定
可配置
有产物
可断点续跑
能合成视频
能排查错误
```

第二期再增强：

```text
Demucs 人声分离
AI 英文深度校验
AI 视觉质检
批量任务队列
UI 页面
英文 TTS 配音
```
