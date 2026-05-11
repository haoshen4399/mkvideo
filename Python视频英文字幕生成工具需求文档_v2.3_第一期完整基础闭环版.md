# Python 视频英文字幕生成工具需求文档 v2

> 版本：v2.3  
> 定位：第一期完整基础闭环版：视频分离音频 → 音频转中文字幕 → AI 检查中文字幕 → AI 翻译英文字幕 → 视频截图定位字幕位置 → 英文字幕合成进视频 → 输出字幕与成品视频；第二期做质量增强与智能优化  
> 适用对象：产品经理、架构师、开发人员、测试人员、后续 AI 辅助开发使用  

---

# 一、项目背景

本项目用于将中文视频自动转换为英文字幕视频，主要面向短视频、影视解说、课程视频、海外平台内容发布等场景。

工具采用本地 Python 运行方式，支持用户通过配置文件灵活选择 ASR 模型、大模型翻译服务、字幕样式、渲染方式、质检方式等。

本版本在原需求基础上做了重点调整：

1. 默认 ASR 引擎改为 `faster-whisper`；
2. 默认模型支持 `large-v3` 或 `medium`；
3. 备用 ASR 引擎支持 `openai-whisper`；
4. 每个步骤均支持配置化；
5. 每个步骤均支持中间产物保存；
6. 支持断点续跑；
7. 支持从指定步骤开始执行；
8. 整体分为两期开发：第一期稳定出片，第二期智能增强。

---

# 二、项目目标

## 2.1 核心目标

本工具第一阶段的核心目标不是一次性实现完全无人值守的工业级闭环，而是优先保证：

1. 能稳定处理中文视频；
2. 能生成合法、可编辑的中文字幕；
3. 能通过大模型生成英文字幕；
4. 能输出英文字幕文件；
5. 第一期必须合成带英文字幕或中英双语字幕的视频，字幕必须进入视频画面，不能只输出字幕文件；
6. 每一步都可追踪、可配置、可重跑；
7. 失败后不需要从头开始；
8. 后续可扩展 AI 校验、视觉质检、人声分离、TTS 配音等能力。

## 2.2 产品定位

本工具定位为：

> 一款面向中文视频海外化处理的本地 Python 自动字幕生成工具。

适合场景包括：

| 场景 | 说明 |
|---|---|
| TikTok / YouTube Shorts | 中文短视频快速生成英文字幕 |
| 影视娱乐切片 | 中文影视解说、娱乐视频转英文字幕 |
| 体育视频切片 | 中文体育解说生成英文字幕 |
| 课程视频 | 中文课程、培训视频生成英文字幕 |
| 海外内容分发 | 中文内容面向海外用户二次发布 |
| 批量字幕处理 | 多个短视频统一生成英文字幕 |

---

# 三、开发分期规划

本项目拆分为两期开发。

---

## 3.1 第一期：完整基础闭环版

第一期目标：

> 完成一个最基础但完整可用的闭环：视频分离音频 → 音频转中文字幕 → AI 检查中文字幕 → AI 翻译英文字幕 → 视频截图定位字幕位置 → 英文字幕合成进视频 → 输出中文字幕、英文字幕、成品视频。

第一期不是简单导出字幕文件，而是必须输出可以直接查看的成品视频。

### 3.1.1 第一期核心流程

```text
输入中文视频
  ↓
视频基础校验
  ↓
从视频分离/提取音频
  ↓
音频转中文字幕
  ↓
AI 检查中文字幕是否有误
  ↓
AI 基于整体字幕语义翻译为英文字幕
  ↓
对视频进行截图/抽帧
  ↓
分析截图，找出英文字幕适合放置的位置
  ↓
生成字幕渲染配置
  ↓
将英文字幕合并到视频中
  ↓
输出中文字幕、英文字幕、合并完字幕的视频
```

### 3.1.2 第一期必做能力

| 模块 | 是否必做 | 说明 |
|---|---:|---|
| 视频输入校验 | 必做 | 校验格式、时长、音轨、分辨率 |
| 视频分离/提取音频 | 必做 | 从视频中提取可供 ASR 使用的音频文件 |
| 音频转中文字幕 | 必做 | 默认 faster-whisper，备用 openai-whisper |
| 中文字幕规则后处理 | 必做 | 修复时间重叠、空字幕、过短字幕 |
| AI 中文字幕检查 | 必做 | 检查 ASR 错字、漏字、多字、语义不通顺，并输出检查报告 |
| AI 翻译英文字幕 | 必做 | AI 先理解整段字幕含义，再翻译为英文字幕 |
| 视频截图/抽帧 | 必做 | 对原视频截图，用于判断字幕位置 |
| 字幕位置分析 | 必做 | 基于截图判断英文字幕放置位置，第一期可采用 OpenCV + 规则方式 |
| 字幕渲染配置生成 | 必做 | 输出字幕位置、字号、描边、边距等配置 |
| 英文字幕合并进视频 | 必做 | 必须输出带英文字幕的视频 |
| 输出中文字幕文件 | 必做 | 输出 AI 检查后的中文字幕 |
| 输出英文字幕文件 | 必做 | 输出最终英文字幕 |
| 输出合并后视频 | 必做 | 输出可直接播放的 MP4 |
| 中间文件保存 | 必做 | 每个步骤都要保存产物 |
| 断点续跑 | 必做 | 失败后可从失败步骤继续 |
| 配置文件 | 必做 | 每个步骤尽量配置化 |
| 日志系统 | 必做 | 记录每一步执行情况 |

### 3.1.3 第一期默认输出文件

第一期最少必须输出：

```text
1. 中文字幕文件：zh_ai_checked.srt
2. 英文字幕文件：en_checked.srt
3. 合并英文字幕后的视频：final_en_subtitled.mp4
```

同时建议保存以下中间产物：

```text
1. 原始音频：original.wav
2. 原始中文字幕：zh_raw.srt
3. 后处理中文字幕：zh_clean.srt
4. AI 检查报告：zh_check_report.json
5. 原始英文字幕：en_raw.srt
6. 英文字幕校验报告：en_check_report.json
7. 视频截图：frame_001.jpg / frame_002.jpg / frame_003.jpg
8. 字幕位置配置：subtitle_position.json
9. ASS 字幕文件：english.ass 或 bilingual.ass
10. 渲染日志：ffmpeg.log
11. 任务状态文件：task_state.json
```

### 3.1.4 第一期暂不重点做的能力

以下能力第一期可以预留接口，但不作为核心验收重点：

| 能力 | 说明 |
|---|---|
| Demucs 高质量人声分离 | 第一期先做音频提取，复杂人声/背景音乐分离放第二期增强 |
| 英文字幕 AI 深度二次校验 | 第一期先做基础规则校验，第二期增强双语语义复核 |
| AI 视觉大模型质检 | 第一期优先用 OpenCV 截图和规则判断字幕位置 |
| 多轮自动修复闭环 | 第二期再增强 |
| UI 界面 | 第一期优先 CLI |
| 批量复杂任务队列 | 第二期增强 |

## 3.2 第二期：AI 智能增强版

第二期目标：

> 在第一期完整基础闭环的基础上，提升字幕质量、字幕位置判断准确性、自动判断能力、自动修复能力和用户体验。

第二期重点包括：

1. 人声分离；
2. 中文字幕 AI 校验；
3. 英文字幕 AI 校验；
4. 视频画面 AI 分析；
5. 成品视频 5 帧 AI 质检；
6. 自动重试与自动修复；
7. 人工修正入口；
8. 简单 UI；
9. 多 ASR 引擎扩展；
10. 后续可接入英文 TTS 配音。

### 3.2.1 第二期增强能力

| 模块 | 是否第二期 | 说明 |
|---|---:|---|
| Demucs 人声分离 | 增强 | 对背景音乐较重的视频启用 |
| AI 中文字幕校验增强 | 增强 | 第一期已有基础 AI 校验，第二期增强为多轮校验、术语库、人工确认机制 |
| AI 英文翻译校验 | 增强 | 检查翻译偏差、语法问题 |
| OpenCV 字幕位置优化增强 | 增强 | 第一期已有基础截图定位，第二期增强亮度、底部已有字幕、人物/主体区域判断 |
| AI 视觉画面分析 | 增强 | 在 OpenCV 规则不足时，调用视觉模型进一步判断字幕安全区域 |
| 成品 5 帧 AI 质检 | 增强 | 检查遮挡、溢出、翻译一致性 |
| 自动重试机制 | 增强 | 翻译失败、校验失败、渲染失败自动重试 |
| 人工修正入口 | 增强 | 支持修改字幕后继续渲染 |
| 简单 UI 界面 | 增强 | 输入目录、配置模型、查看进度 |
| 多 ASR 引擎切换 | 增强 | faster-whisper / openai-whisper / whisperX |
| 字幕智能重切 | 增强 | 优化英文长度和阅读节奏 |
| 英文 TTS 配音 | 预留 | 后续支持中文视频生成英文配音版 |

---

# 四、总体业务流程

## 4.1 第一期业务流程

```text
输入视频
  ↓
视频基础校验
  ↓
视频分离/提取音频
  ↓
音频转中文字幕
  ↓
中文字幕规则后处理
  ↓
AI 检查并修正中文字幕
  ↓
AI 理解整段中文字幕整体语义
  ↓
AI 翻译生成英文字幕
  ↓
英文字幕规则校验
  ↓
OpenCV 截图/抽帧
  ↓
分析截图并给出英文字幕位置
  ↓
生成 ASS 字幕
  ↓
FFmpeg + ASS 将英文字幕合并到视频中
  ↓
输出中文字幕、英文字幕、合并后视频、中间文件、日志
```

## 4.2 第二期业务流程

```text
输入视频
  ↓
视频基础校验
  ↓
音频质量检测
  ↓
是否启用人声分离
  ↓
提取纯人声
  ↓
ASR 生成中文字幕
  ↓
中文字幕规则校验
  ↓
中文字幕 AI 校验
  ↓
AI 翻译英文字幕
  ↓
英文字幕规则校验
  ↓
英文字幕 AI 校验
  ↓
视频画面 AI 分析
  ↓
生成双语 ASS 字幕
  ↓
FFmpeg 合成视频
  ↓
成品 5 帧截图
  ↓
AI 成品质检
  ↓
通过则输出，不通过则重试或提示人工干预
```

---

# 五、核心设计原则

## 5.1 每个步骤都必须配置化

每个步骤必须支持以下配置：

1. 是否启用；
2. 使用哪个引擎；
3. 输入文件路径；
4. 输出文件路径；
5. 是否覆盖已有结果；
6. 失败是否重试；
7. 最大重试次数；
8. 是否允许跳过；
9. 是否可从该步骤开始执行；
10. 是否使用已有中间产物。

## 5.2 每个步骤都必须保存中间产物

系统不得只输出最终视频。必须保存：

1. 原始音频；
2. 分离后人声音频；
3. 原始中文字幕；
4. 后处理中文字幕；
5. 原始英文字幕；
6. 校验后英文字幕；
7. ASS 字幕文件；
8. 成品视频；
9. 截图质检图片；
10. 每一步日志；
11. 任务状态文件；
12. 本次配置快照。

## 5.3 每个步骤都必须支持断点续跑

如果流程失败，系统必须支持：

1. 从失败步骤继续；
2. 从指定步骤开始；
3. 跳过已成功步骤；
4. 手动修改中间文件后继续执行；
5. 只重新翻译；
6. 只重新渲染；
7. 只重新质检。

## 5.4 不强制所有能力串死

以下步骤必须可选：

1. 人声分离；
2. 英文字幕 AI 深度校验；
3. 视觉分析；
4. 成品 AI 质检；
5. 自动重试；
6. 批量处理；
7. UI 操作。

注意：第一期中 `中文字幕 AI 校验`、`英文字幕生成`、`字幕合成进视频` 不允许关闭，只允许配置模型、重试、是否覆盖已有结果。

## 5.5 第一期字幕合成必须完成

第一期必须输出可直接发布的视频文件。

最低交付要求：

1. 生成英文字幕 SRT；
2. 生成中文字幕 AI 校验版 SRT；
3. 生成用于渲染的 ASS 字幕；
4. 将英文字幕或中英双语字幕烧录进视频；
5. 输出 MP4 成品视频；
6. 输出渲染日志。

实现建议：

1. 第一优先方案：FFmpeg + ASS；
2. OpenCV 第一阶段不建议作为主渲染方案，因为逐帧写字会导致性能低、音视频同步和编码复杂；
3. OpenCV 第一阶段可用于截图、抽帧、基础质检；
4. 第二期再使用 OpenCV 分析字幕安全区、亮度、原字幕位置，并动态调整 ASS 样式。


## 5.6 基础校验优先用规则，AI 只做增强

系统必须先做程序规则校验，再做 AI 语义校验。

程序规则校验包括：

1. SRT 是否可解析；
2. 序号是否连续；
3. 时间戳是否重叠；
4. 开始时间是否小于结束时间；
5. 中英字幕条数是否一致；
6. 单条字幕是否为空；
7. 单条字幕是否过长；
8. 单条字幕显示时间是否过短；
9. 字幕是否超出视频总时长；
10. 是否存在乱码。

AI 校验用于：

1. 中文是否通顺；
2. 英文是否自然；
3. 翻译是否符合原意；
4. 是否符合美式英语表达；
5. 是否存在语义偏差；
6. 是否存在视觉遮挡。

---

# 六、ASR 语音识别方案

## 6.1 默认 ASR 引擎

第一期默认使用：

```text
faster-whisper
```

默认模型优先级：

```text
large-v3
medium
small
```

## 6.2 推荐模型策略

| 场景 | 推荐模型 |
|---|---|
| 追求准确率 | large-v3 |
| 速度与准确率平衡 | medium |
| 电脑配置一般 | small / medium |
| 显存充足 | large-v3 + GPU |
| 显存不足 | medium + int8 |
| 批量处理 | medium |
| 高质量单视频 | large-v3 |

## 6.3 备用 ASR 引擎

备用引擎：

```text
openai-whisper
```

备用场景：

1. faster-whisper 安装失败；
2. faster-whisper 识别异常；
3. faster-whisper 输出格式异常；
4. 用户手动指定备用引擎；
5. 特定视频在 faster-whisper 下识别效果不好。

## 6.4 后续可扩展 ASR

第二期或后续可支持：

| ASR 引擎 | 用途 |
|---|---|
| whisperX | 更精细时间戳对齐 |
| 云端 ASR API | 本地机器跑不动时备用 |
| FunASR | 中文识别增强 |
| Paraformer | 中文语音识别可选方案 |

---

# 七、任务步骤定义

系统将完整流程拆分为固定步骤。

| 步骤编号 | 步骤名称 | 说明 | 是否可跳过 | 是否可重跑 |
|---|---|---|---:|---:|
| step_01 | probe_video | 视频信息检测 | 否 | 是 |
| step_02 | extract_audio | 提取音频 | 否 | 是 |
| step_03 | vocal_separation | 人声分离 | 是 | 是 |
| step_04 | asr | 生成中文字幕 | 否 | 是 |
| step_05 | zh_postprocess | 中文字幕后处理 | 否 | 是 |
| step_06 | zh_ai_check | 中文字幕 AI 校验 | 是 | 是 |
| step_07 | translate | 翻译英文字幕 | 否 | 是 |
| step_08 | en_check | 英文字幕校验 | 否 | 是 |
| step_09 | build_ass | 生成 ASS 字幕 | 否 | 是 |
| step_10 | render_video | 合成视频 | 否 | 是 |
| step_11 | screenshot_position | 视频截图与字幕位置分析 | 否 | 是 |
| step_12 | visual_ai_qc | AI 视觉质检 | 是 | 是 |

## 7.1 第一期默认启用步骤

```text
step_01 probe_video
step_02 extract_audio
step_04 asr
step_05 zh_postprocess
step_06 zh_ai_check
step_07 translate
step_08 en_check
step_11 screenshot_position
step_09 build_ass
step_10 render_video
```

## 7.2 第一期默认关闭步骤

```text
step_03 vocal_separation
step_12 visual_ai_qc
```

## 7.3 第二期增强启用步骤

第二期可根据配置启用：

```text
step_03 vocal_separation
step_12 visual_ai_qc
```

---

# 八、配置文件设计

建议使用 `config.yaml` 作为主配置文件。

## 8.1 总体配置示例

```yaml
app:
  mode: standard
  input_dir: "./input"
  output_dir: "./output"
  work_dir: "./work"
  keep_intermediate: true
  max_video_minutes: 10
  batch_size: 5
  resume: true

steps:
  probe_video:
    enabled: true

  extract_audio:
    enabled: true
    overwrite: false

  vocal_separation:
    enabled: false
    engine: demucs
    model: htdemucs
    overwrite: false
    max_retries: 1

  asr:
    enabled: true
    engine: faster-whisper
    fallback_engine: openai-whisper
    model: large-v3
    fallback_model: medium
    language: zh
    device: auto
    compute_type: auto
    overwrite: false
    max_retries: 1

  zh_subtitle_postprocess:
    enabled: true
    merge_short_subtitle: true
    min_duration_ms: 800
    max_duration_ms: 7000
    fix_overlap: true
    remove_empty: true
    overwrite: false

  zh_ai_check:
    enabled: true
    provider: default
    model: Qwen/Qwen3-30B-A3B-Instruct-2507
    check_items:
      typo: true
      missing_words: true
      extra_words: true
      semantic_smoothness: true
      context_consistency: true
      srt_format: true
    auto_fix_minor_errors: true
    output_checked_srt: true
    max_retries: 1

  translate:
    enabled: true
    provider: default
    model: Qwen/Qwen3-30B-A3B-Instruct-2507
    source_lang: zh
    target_lang: en
    translation_strategy: understand_full_context_first
    style: american_natural
    keep_timestamp: true
    keep_subtitle_count: true
    max_retries: 2
    overwrite: false

  en_subtitle_check:
    enabled: true
    rule_check: true
    ai_check: false
    max_chars_per_line: 42
    max_lines: 2
    max_cps: 17
    fix_format: true

  build_ass:
    enabled: true
    subtitle_mode: bilingual
    overwrite: false

  render_video:
    enabled: true
    engine: ffmpeg
    video_codec: libx264
    audio_codec: aac
    crf: 20
    preset: medium
    overwrite: false

  screenshot_position:
    enabled: true
    engine: opencv
    sample_count: 3
    sample_strategy: start_middle_end
    analyze_brightness: true
    analyze_bottom_area: true
    detect_existing_subtitle_area: true
    output_position_json: true
    default_position: bottom_center

  visual_ai_qc:
    enabled: false
    provider: default
    model: vision-model-name
    max_retries: 1
```

---

# 九、大模型配置设计

建议所有大模型调用统一采用 OpenAI-compatible 方式封装。

## 9.1 大模型配置示例

```yaml
llm_providers:
  default:
    type: openai_compatible
    base_url: "https://openai.5054399.com/siliconflow/v1"
    api_key_env: "SILICONFLOW_API_KEY"
    default_model: "deepseek-ai/DeepSeek-V3.2"
    timeout: 180
    max_retries: 2

  siliconflow_official:
    type: openai_compatible
    base_url: "https://api.siliconflow.cn/v1"
    api_key_env: "SILICONFLOW_API_KEY"
    default_model: "Qwen/Qwen3-30B-A3B-Instruct-2507"
    timeout: 120
    max_retries: 2

  openai:
    type: openai_compatible
    base_url: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
    default_model: "gpt-4.1"
    timeout: 120
    max_retries: 2

  zhipu:
    type: zhipu
    api_key_env: "ZHIPU_API_KEY"
    default_model: "glm-4.5"
    timeout: 120
    max_retries: 2

  dashscope:
    type: dashscope
    api_key_env: "DASHSCOPE_API_KEY"
    default_model: "qwen-plus"
    timeout: 120
    max_retries: 2
```

## 9.2 用户当前推荐网关配置

根据当前项目要求，第一期默认可使用以下 OpenAI-compatible 配置：

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

对应 `.env`：

```env
SILICONFLOW_API_KEY=你的实际秘钥
```

代码调用时不要把 `base_url`、`model`、`api_key` 写死在模块里，必须统一从配置文件读取。

第一期至少有两个地方要使用该模型配置：

1. `zh_ai_check`：中文字幕 AI 校验与修正；
2. `translate`：AI 理解整体字幕语义后翻译英文。

## 9.3 API Key 管理

API Key 不允许硬编码在代码中。

建议使用 `.env` 文件：

```env
SILICONFLOW_API_KEY=你的 5054399/SiliconFlow 网关秘钥
OPENAI_API_KEY=你的OpenAI秘钥
ZHIPU_API_KEY=你的智谱秘钥
DASHSCOPE_API_KEY=你的通义秘钥
```

---

# 十、断点续跑设计

## 10.1 状态文件

每个视频处理目录下必须生成：

```text
task_state.json
```

示例：

```json
{
  "video": "demo.mp4",
  "current_status": "failed",
  "last_success_step": "translate",
  "failed_step": "render_video",
  "steps": {
    "probe_video": "success",
    "extract_audio": "success",
    "asr": "success",
    "zh_subtitle_postprocess": "success",
    "translate": "success",
    "en_subtitle_check": "success",
    "build_ass": "success",
    "render_video": "failed"
  },
  "error": {
    "step": "render_video",
    "message": "ffmpeg render failed"
  }
}
```

## 10.2 断点续跑规则

系统必须支持：

```bash
python main.py --input ./input/demo.mp4 --output ./output --resume
```

系统行为：

1. 读取 `task_state.json`；
2. 找到最后成功步骤；
3. 从失败步骤继续；
4. 已成功且未设置 overwrite 的步骤自动跳过；
5. 新结果覆盖对应失败步骤后的产物。

## 10.3 从指定步骤开始

系统必须支持：

```bash
python main.py --input ./input/demo.mp4 --output ./output --start-from translate
```

示例场景：

| 场景 | 命令 |
|---|---|
| 只重新翻译 | `--start-from translate` |
| 只重新生成 ASS | `--start-from build_ass` |
| 只重新渲染 | `--start-from render_video` |
| 修改字幕后继续合成 | `--start-from build_ass` |
| AI 质检失败后重新质检 | `--start-from screenshot_qc` |

---

# 十一、输出目录设计

每个视频必须有独立输出目录。

```text
output/
  demo/
    input/
      demo.mp4

    audio/
      original.wav
      vocals.wav

    subtitles/
      zh_raw.srt
      zh_clean.srt
      zh_ai_checked.srt
      en_raw.srt
      en_checked.srt
      en_ai_checked.srt
      bilingual.ass

    render/
      final_bilingual.mp4
      final_en_only.mp4

    position/
      screenshots/
        frame_001.jpg
        frame_002.jpg
        frame_003.jpg
      subtitle_position.json

    qc/
      screenshots/
        qc_frame_001.jpg
        qc_frame_002.jpg
        qc_frame_003.jpg
        qc_frame_004.jpg
        qc_frame_005.jpg
      qc_report.json
      visual_qc_report.json

    reports/
      video_info.json
      asr_report.json
      zh_check_report.json
      translation_report.json
      en_check_report.json
      render_report.json

    logs/
      run.log
      ffmpeg.log
      llm_translate.log
      error.log

    task_state.json
    task_config_snapshot.yaml
```

## 11.1 关键文件说明

| 文件 | 说明 |
|---|---|
| original.wav | 原视频提取音频 |
| vocals.wav | 人声分离后的音频，第二期可选 |
| zh_raw.srt | ASR 原始中文字幕 |
| zh_clean.srt | 后处理后的中文字幕 |
| en_raw.srt | 基于 zh_ai_checked.srt 或 zh_clean.srt 的大模型初始英文翻译 |
| en_checked.srt | 规则校验后的英文字幕 |
| subtitle_position.json | 第一期通过 OpenCV 截图/规则分析得到的字幕位置配置 |
| bilingual.ass | 双语字幕渲染文件 |
| final_bilingual.mp4 | 最终双语字幕视频 |
| task_state.json | 任务执行状态 |
| task_config_snapshot.yaml | 本次执行配置快照 |
| run.log | 主流程日志 |

---

# 十二、命令行设计

第一期优先实现 CLI。

## 12.1 全流程执行

```bash
python main.py --input ./input --output ./output --mode standard
```

## 12.2 指定单个视频

```bash
python main.py --input ./input/demo.mp4 --output ./output
```

## 12.3 从失败点继续

```bash
python main.py --input ./input/demo.mp4 --output ./output --resume
```

## 12.4 从指定步骤开始

```bash
python main.py --input ./input/demo.mp4 --output ./output --start-from translate
```

## 12.5 只生成字幕，不合成视频

```bash
python main.py --input ./input/demo.mp4 --output ./output --task subtitle
```

## 12.6 只重新渲染视频

```bash
python main.py --input ./input/demo.mp4 --output ./output --task render
```

## 12.7 强制启用人声分离

```bash
python main.py --input ./input/demo.mp4 --output ./output --enable-vocal-separation
```

## 12.8 指定 ASR 模型

```bash
python main.py --input ./input/demo.mp4 --output ./output --asr-engine faster-whisper --asr-model large-v3
```

---

# 十三、字幕处理设计

## 13.1 中文字幕后处理规则

系统对 `zh_raw.srt` 进行后处理，输出 `zh_clean.srt`。

处理规则：

1. 删除空字幕；
2. 修复时间戳重叠；
3. 修复开始时间大于结束时间的问题；
4. 合并过短字幕；
5. 拆分过长字幕；
6. 修复字幕序号；
7. 统一标点；
8. 可选去除无意义语气词；
9. 保证 SRT 可解析。


## 13.2 第一期 AI 中文字幕校验与修正

第一期必须对 `zh_clean.srt` 进行 AI 校验，输出 `zh_ai_checked.srt` 和 `zh_check_report.json`。

该步骤的目的不是简单润色，而是防止 ASR 识别错误被带入英文翻译。

AI 中文字幕校验范围：

1. 检查错别字；
2. 检查同音字误识别；
3. 检查多字、漏字；
4. 检查明显语义不通顺；
5. 检查上下文前后矛盾；
6. 检查字幕断句是否严重影响理解；
7. 检查 SRT 格式是否仍然合法；
8. 对轻微错误自动修正；
9. 对无法确认的内容写入报告，保留原文或标记需人工确认。

输出要求：

1. `zh_ai_checked.srt`：AI 校验/修正后的中文字幕；
2. `zh_check_report.json`：校验报告；
3. 如果 AI 校验失败，应允许用户继续使用 `zh_clean.srt`，但日志中必须明确标记风险；
4. 后续英文翻译默认优先读取 `zh_ai_checked.srt`。


## 13.3 英文字幕规则校验

系统对 `en_raw.srt` 进行规则校验，输出 `en_checked.srt`。

校验规则：

1. SRT 格式合法；
2. 字幕序号连续；
3. 英文字幕条数与中文字幕一致；
4. 英文字幕时间戳与中文字幕一致；
5. 不允许空字幕；
6. 每条最多 2 行；
7. 每行建议不超过 42 个英文字符；
8. CPS 建议不超过 17；
9. 不允许明显乱码；
10. 不允许字幕时间重叠。

---

# 十五、ASS 字幕渲染设计

## 15.1 为什么使用 ASS

虽然输出字幕可以保留 SRT，但视频硬字幕渲染建议使用 ASS。

原因：

1. SRT 对样式控制能力弱；
2. ASS 支持字体、字号、描边、阴影、位置；
3. ASS 更适合中英双语字幕；
4. FFmpeg 对 ASS 烧录支持成熟；
5. 后续可根据视觉分析动态调整字幕位置。

## 15.2 字幕样式配置

```yaml
subtitle_style:
  font_name: "Microsoft YaHei"
  font_size_zh: 36
  font_size_en: 32
  font_color: "white"
  outline_color: "black"
  outline_width: 2
  shadow: 1
  alignment: "bottom_center"
  margin_v: 80
  line_spacing: 8
```

## 15.3 字幕模式

支持三种字幕模式：

| 模式 | 说明 |
|---|---|
| en_only | 只显示英文字幕 |
| zh_only | 只显示中文字幕 |
| bilingual | 中文在上，英文在下 |

第一期默认：

```text
bilingual
```

---

# 十六、视频渲染设计

## 16.1 渲染工具

第一期主渲染工具使用：

```text
FFmpeg + ASS
```

OpenCV 在第一期只作为截图、抽帧、简单质检辅助工具，不作为主字幕合成方案。

原因：

1. FFmpeg + ASS 更适合字幕烧录；
2. ASS 对字体、描边、行距、位置控制更稳定；
3. OpenCV 逐帧写字幕会增加编码、音频同步、性能和跨平台字体处理复杂度；
4. 第二期可以使用 OpenCV 分析字幕位置，再把分析结果转换为 ASS 样式参数。

## 16.2 输出编码

默认输出：

```text
MP4
H.264 视频编码
AAC 音频编码
```

## 16.3 画质配置

不建议写“无画质损耗”，因为硬字幕烧录需要重新编码。

建议使用：

```yaml
render:
  video_codec: libx264
  audio_codec: aac
  crf: 20
  preset: medium
  keep_resolution: true
  keep_fps: true
```

说明：

| 参数 | 说明 |
|---|---|
| crf 18 | 质量高，文件更大 |
| crf 20 | 推荐默认值 |
| crf 23 | 文件更小，质量略低 |
| preset medium | 速度与压缩率平衡 |
| preset fast | 更快但文件略大 |

---

# 十七、AI 提示词设计要求

## 17.1 第一期 AI 中文字幕校验提示词原则

中文字幕 AI 校验必须遵守：

1. 不改变原字幕时间戳；
2. 不改变字幕序号；
3. 不随意扩写原文；
4. 重点修正 ASR 明显错误；
5. 对无法判断的人名、品牌名、专有名词保留原文并写入报告；
6. 输出必须可被程序解析；
7. 校验后的 SRT 必须仍然合法。

## 17.2 翻译提示词原则

英文字幕翻译必须遵守：

1. 先理解整段中文语义；
2. 再按字幕条逐条翻译；
3. 保持时间戳不变；
4. 保持字幕条数不变；
5. 英文表达自然；
6. 符合美国人日常表达；
7. 避免机械直译；
8. 不增加原文没有的信息；
9. 不删除原文核心含义；
10. 输出必须是标准 SRT。

## 17.3 建议翻译提示词

```text
你是一名专业视频字幕翻译专家，擅长将中文视频字幕翻译成自然、地道、符合美国人日常表达习惯的英文字幕。

请严格遵守以下要求：

1. 请先整体理解中文字幕的上下文，再进行翻译，不要逐字硬译。
2. 英文表达要自然、简洁、适合视频字幕阅读。
3. 不允许增加中文原文没有的信息。
4. 不允许删除中文原文的重要含义。
5. 必须保持原 SRT 的字幕序号不变。
6. 必须保持原 SRT 的时间戳完全不变。
7. 必须保持字幕条数完全一致。
8. 每条英文字幕尽量不超过 2 行。
9. 每行英文建议不超过 42 个字符。
10. 只输出英文 SRT 内容，不要输出解释、说明、Markdown 或其他多余内容。

以下是中文字幕 SRT：

【此处插入 zh_clean.srt】
```

## 17.4 AI 校验输出格式

第二期 AI 校验建议统一输出 JSON。

示例：

```json
{
  "passed": false,
  "error_count": 2,
  "errors": [
    {
      "index": 12,
      "type": "translation_error",
      "source": "中文原文",
      "target": "英文字幕",
      "suggestion": "建议修改后的英文"
    }
  ],
  "fixed_srt": "修正后的完整 SRT"
}
```

---

# 十八、第一期技术架构

## 22.1 推荐目录结构

```text
video_subtitle_tool/
  main.py

  app/
    cli.py
    config_loader.py
    pipeline.py
    task_state.py

  core/
    video_probe.py
    audio_extractor.py
    asr_engine.py
    subtitle_postprocessor.py
    zh_ai_checker.py
    subtitle_validator.py
    translator.py
    ass_builder.py
    position_analyzer.py
    video_renderer.py
    screenshot_qc.py

  providers/
    llm_base.py
    openai_compatible_provider.py
    siliconflow_provider.py

  engines/
    faster_whisper_engine.py
    openai_whisper_engine.py

  utils/
    ffmpeg_utils.py
    file_utils.py
    log_utils.py
    retry_utils.py
    srt_utils.py

  configs/
    config.example.yaml

  prompts/
    zh_check.txt
    translate_en.txt

  tests/
```

## 22.2 第二期扩展目录

```text
video_subtitle_tool/
  core/
    vocal_separator.py
    zh_ai_checker.py
    en_ai_checker.py
    visual_analyzer.py
    visual_qc.py
    auto_retry_manager.py

  providers/
    zhipu_provider.py
    dashscope_provider.py
    vision_provider.py

  prompts/
    zh_check.yaml
    en_check.yaml
    visual_qc.yaml
```

## 22.3 核心架构原则

```text
CLI 负责接收参数。
ConfigLoader 负责加载配置。
Pipeline 负责任务编排。
TaskState 负责状态记录。
每个 Step 独立处理输入输出。
每个 Provider 只负责模型调用。
每个 Engine 只负责具体 ASR 实现。
```

---

# 十九、第一期开发任务拆分

## 22.1 任务 1：项目骨架

内容：

1. 创建项目目录；
2. 创建 `main.py`；
3. 创建 `config.yaml`；
4. 创建 CLI 参数解析；
5. 创建日志系统；
6. 创建输出目录管理；
7. 创建任务状态管理。

交付物：

```text
main.py
config.example.yaml
app/cli.py
app/config_loader.py
app/task_state.py
```

## 22.2 任务 2：视频检测模块

内容：

1. 读取视频路径；
2. 检测视频格式；
3. 检测视频时长；
4. 检测是否有音频流；
5. 检测分辨率；
6. 检测帧率；
7. 检测编码格式；
8. 输出 `video_info.json`。

交付物：

```text
core/video_probe.py
reports/video_info.json
```

## 22.3 任务 3：音频提取模块

内容：

1. 使用 FFmpeg 提取音频；
2. 输出 WAV；
3. 支持 16kHz；
4. 支持单声道；
5. 失败写入日志；
6. 可配置是否覆盖已有音频。

交付物：

```text
core/audio_extractor.py
audio/original.wav
```

## 22.4 任务 4：ASR 模块

内容：

1. 集成 faster-whisper；
2. 支持 large-v3；
3. 支持 medium；
4. 支持 device auto/cuda/cpu；
5. 支持 compute_type auto/float16/int8；
6. 输出 `zh_raw.srt`；
7. 支持 openai-whisper 备用；
8. 支持失败回退。

交付物：

```text
engines/faster_whisper_engine.py
engines/openai_whisper_engine.py
core/asr_engine.py
subtitles/zh_raw.srt
```

## 22.5 任务 5：中文字幕后处理

内容：

1. 修复时间戳重叠；
2. 删除空字幕；
3. 合并过短字幕；
4. 限制最长显示时间；
5. 修复序号；
6. 输出 `zh_clean.srt`。

交付物：

```text
core/subtitle_postprocessor.py
subtitles/zh_clean.srt
```

## 22.6 任务 6：AI 中文字幕校验与修正模块

内容：

1. 读取 `zh_clean.srt`；
2. 调用大模型进行中文字幕校验；
3. 检查 ASR 错字、漏字、多字、同音字误识别；
4. 检查语义是否通顺；
5. 检查上下文是否矛盾；
6. 自动修正轻微错误；
7. 输出 `zh_ai_checked.srt`；
8. 输出 `zh_check_report.json`；
9. 如果 AI 校验失败，允许配置是否继续使用 `zh_clean.srt`。

交付物：

```text
core/zh_ai_checker.py
prompts/zh_check.txt
subtitles/zh_ai_checked.srt
reports/zh_check_report.json
```

## 22.7 任务 7：大模型翻译模块

内容：

1. 默认读取 `zh_ai_checked.srt`，若不存在则按配置读取 `zh_clean.srt`；
2. 调用 OpenAI-compatible API；
3. AI 先理解整段中文字幕整体语义；
4. 再翻译为英文 SRT；
4. 保持条数；
5. 保持时间戳；
6. 输出 `en_raw.srt`；
7. 记录模型请求日志。

交付物：

```text
providers/llm_base.py
providers/openai_compatible_provider.py
providers/siliconflow_provider.py
core/translator.py
subtitles/en_raw.srt
logs/llm_translate.log
```

## 22.8 任务 8：英文字幕规则校验

内容：

1. 检查 SRT 格式；
2. 检查条数一致；
3. 检查时间戳一致；
4. 检查字符长度；
5. 检查空字幕；
6. 输出 `en_checked.srt`；
7. 输出 `validation_report.json`。

交付物：

```text
core/subtitle_validator.py
subtitles/en_checked.srt
reports/en_check_report.json
```

## 22.9 任务 9：ASS 字幕生成

内容：

1. 读取 `zh_clean.srt`；
2. 读取 `en_checked.srt`；
3. 生成 `bilingual.ass`；
4. 支持字体配置；
5. 支持字号配置；
6. 支持描边配置；
7. 支持位置配置；
8. 支持英文单独字幕模式。

交付物：

```text
core/ass_builder.py
subtitles/bilingual.ass
```

## 22.10 任务 10：视频渲染模块

内容：

1. 调用 FFmpeg；
2. 烧录 ASS 字幕；
3. 第一期必须输出带英文字幕或中英双语字幕的 MP4；
4. 保留原分辨率；
5. 支持 CRF 配置；
6. 支持渲染日志；
7. 失败写入状态文件。

交付物：

```text
core/video_renderer.py
render/final_bilingual.mp4
logs/ffmpeg.log
```

## 22.11 任务 11：断点续跑

内容：

1. 每一步写入 `task_state.json`；
2. 支持 `--resume`；
3. 支持 `--start-from`；
4. 支持跳过已成功步骤；
5. 支持失败后继续；
6. 支持覆盖指定步骤结果。

交付物：

```text
app/pipeline.py
app/task_state.py
task_state.json
```

---

# 二十、第二期开发任务拆分

## 22.1 任务 1：Demucs 人声分离

内容：

1. 支持配置启用；
2. 支持 Demucs 模型配置；
3. 输出 `vocals.wav`；
4. 分离失败可回退 `original.wav`；
5. 记录分离耗时和错误信息。

## 22.2 任务 2：中文字幕 AI 校验

内容：

1. 输入 `zh_clean.srt`；
2. 调用大模型检查错别字；
3. 检查语义不通顺；
4. 输出 `zh_ai_checked.srt`；
5. 输出 `zh_ai_check_report.json`。

## 22.3 任务 3：英文字幕 AI 校验

内容：

1. 输入 `zh_clean.srt`；
2. 输入 `en_raw.srt`；
3. 检查翻译准确性；
4. 检查英文自然度；
5. 检查是否符合美式表达；
6. 输出 `en_ai_checked.srt`；
7. 输出 `en_ai_check_report.json`。

## 22.4 任务 4：OpenCV 字幕位置优化与视觉画面分析

内容：

1. 使用 OpenCV 从视频中截取 3–5 帧；
2. 分析画面亮度、底部复杂度、边缘区域、是否存在原字幕区域；
3. 优先用规则判断字幕底部位置是否合适；
4. 根据画面情况调整字幕高度、字号、描边、背景阴影；
5. 如 OpenCV 规则无法判断，再调用视觉模型；
6. 输出 `subtitle_style.json`；
7. 该能力第二期开发，第一期采用默认底部居中样式。

## 22.5 任务 5：成品 5 帧质检

内容：

1. 从成品视频截取 5 帧；
2. 调用视觉模型；
3. 检查字幕是否遮挡主体；
4. 检查字幕是否超出边界；
5. 检查中英字幕显示是否完整；
6. 输出 `visual_qc_report.json`。

## 22.6 任务 6：自动重试闭环

内容：

1. 翻译失败自动重试；
2. AI 校验失败自动修正；
3. 视觉质检失败重新生成 ASS；
4. 渲染失败自动重试；
5. 所有重试次数配置化；
6. 达到最大重试次数后提示人工处理。

## 22.7 任务 7：人工修正入口

内容：

1. 允许用户修改 `zh_clean.srt`；
2. 允许用户修改 `en_checked.srt`；
3. 允许用户修改 `subtitle_style.json`；
4. 支持从 `build_ass` 继续；
5. 支持从 `render_video` 继续。

## 22.8 任务 8：简单 UI

内容：

1. 选择输入目录；
2. 选择输出目录；
3. 选择 ASR 模型；
4. 填写大模型配置；
5. 查看处理进度；
6. 查看失败原因；
7. 一键从失败点继续；
8. 查看输出文件。

---

# 二十一、依赖设计

## 22.1 第一期基础依赖

建议第一期依赖尽量简洁。

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
torch>=2.1.0
torchaudio>=2.1.0
faster-whisper>=1.0.0
openai>=1.40.0
```

## 22.2 备用 ASR 依赖

```text
openai-whisper>=20231117
```

## 22.3 第二期增强依赖

```text
demucs>=4.0.1
librosa>=0.10.1
soundfile>=0.12.1
```

## 22.4 不应写入 requirements 的内容

以下为 Python 标准库，不应写入 requirements：

```text
os
sys
json
time
pathlib
subprocess
logging
configparser
```

FFmpeg 是系统级依赖，也不建议作为普通 pip 依赖写成 `ffmpeg>=6.0`。

正确说明方式：

```text
Windows：安装 ffmpeg.exe 并配置环境变量
Mac：brew install ffmpeg
Linux：sudo apt install ffmpeg
```

---

# 二十二、第一期验收标准

第一期不要使用难以验证的“识别准确率 98%”作为硬性验收，而应使用可测试、可复现的系统指标。

## 22.1 功能验收

| 验收项 | 标准 |
|---|---|
| 视频格式识别 | 支持 MP4/MOV/MKV |
| 音频提取 | 能正常输出 WAV |
| 中文字幕生成 | 能生成合法 SRT |
| AI 中文字幕校验 | 能输出 zh_ai_checked.srt 和 zh_check_report.json |
| 英文字幕生成 | 基于 AI 校验后的中文字幕生成合法 SRT |
| 中英字幕条数 | 默认保持一致 |
| 时间戳 | 无重叠、无乱序 |
| ASS 字幕 | 能正常生成 |
| 视频截图定位 | 必须输出截图和 subtitle_position.json |
| 视频合成 | 第一期必须输出带英文字幕或中英双语硬字幕的 MP4，且可播放 |
| 中间文件 | 每一步文件完整保存 |
| 断点续跑 | 失败后可从失败步骤继续 |
| 配置生效 | 修改配置后对应步骤行为变化 |
| 日志 | 失败时能定位具体步骤和错误 |

## 22.2 性能验收

| 场景 | 建议标准 |
|---|---|
| 10 分钟视频，GPU + medium | 尽量 10–20 分钟内完成 |
| 10 分钟视频，GPU + large-v3 | 可接受 20–40 分钟 |
| 批量 5 个视频 | 不崩溃，可逐个输出状态 |
| 单个步骤失败 | 不影响其他已完成步骤产物 |
| 从失败步骤继续 | 不重复执行已成功步骤 |

## 22.3 质量验收

| 项目 | 标准 |
|---|---|
| SRT 格式合法 | 100% |
| 时间戳重叠 | 不允许 |
| 字幕为空 | 不允许 |
| 英文字幕明显乱码 | 不允许 |
| 视频无法播放 | 不允许 |
| 字幕超出画面 | 不允许 |
| 字幕位置 | 第一期默认底部居中；第二期再用 OpenCV 优化位置 |
| 中文字幕与英文字幕条数 | 默认一致 |

---

# 二十三、第二期验收标准

| 验收项 | 标准 |
|---|---|
| Demucs 人声分离 | 可配置启用，失败可回退原音频 |
| 中文字幕 AI 校验 | 能输出结构化问题报告 |
| 英文字幕 AI 校验 | 能输出翻译问题和修正建议 |
| 视觉分析 | 能输出字幕安全区域 JSON |
| 成品 5 帧质检 | 能输出截图和质检报告 |
| 自动重试 | 翻译/质检失败可按配置重试 |
| 人工修正 | 用户修改 SRT 后可继续渲染 |
| 多模型切换 | 可通过配置切换不同 LLM |
| 失败回退 | 第二期增强步骤失败不影响基础产物输出 |

---

# 二十四、主要风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| faster-whisper 模型下载失败 | 无法识别字幕 | 支持手动模型路径配置 |
| large-v3 运行慢 | 处理耗时过长 | 支持 medium 模型 |
| 显存不足 | ASR 失败 | 支持 int8 / CPU / medium |
| 大模型翻译失败 | 无法生成英文字幕 | 支持重试与备用模型 |
| 英文字幕过长 | 视频中显示不完整 | 规则校验限制字符数 |
| FFmpeg 未安装 | 无法提取音频/渲染视频 | 启动前检测 FFmpeg |
| 字幕样式不理想 | 影响观看体验 | 支持配置字体、字号、位置 |
| AI 质检误判 | 阻塞流程 | 第二期 AI 质检默认不作为唯一依据 |
| 批量处理崩溃 | 多视频任务中断 | 单视频独立状态文件 |
| 失败后重跑成本高 | 浪费时间 | 支持断点续跑 |

---

# 二十五、后续可扩展方向

## 25.1 英文 TTS 配音

后续可增加：

```text
中文字幕
  ↓
英文字幕
  ↓
英文 TTS
  ↓
替换原视频人声
  ↓
输出英文配音视频
```

## 25.2 原声去除 + 背景音乐保留

可扩展为：

1. 分离人声；
2. 保留背景音乐；
3. 生成英文 TTS；
4. 英文 TTS 与背景音乐重新混音；
5. 输出英文配音视频。

## 25.3 多语言字幕

支持：

1. 英文；
2. 日文；
3. 韩文；
4. 西班牙文；
5. 法文；
6. 德文。

## 25.4 Web UI

后续可做成本地 Web 页面：

1. 上传视频；
2. 选择模型；
3. 查看进度；
4. 在线编辑字幕；
5. 一键重新渲染；
6. 下载成品视频。

---

# 二十六、最终结论

本项目正式建议命名为：

```text
Python 视频英文字幕生成工具 v2
```

开发路线：

```text
第一期：视频分离音频 + 音频转中文字幕 + AI 检查 + AI 翻译英文 + 截图定位字幕位置 + 英文字幕合成视频 + 可配置断点续跑版
第二期：OpenCV 字幕位置优化 + AI 智能质检增强版
```

第一期交付目标：

```text
能稳定完成视频分离音频、音频转中文字幕、AI 检查中文字幕、AI 翻译英文字幕、视频截图定位字幕位置、英文字幕合成进视频。
必须输出中文字幕、英文字幕、合并字幕后的视频。
每个关键步骤必须保留中间产物。
导出的中文字幕必须先经过 AI 校验与必要修正。
英文翻译必须基于 AI 对整体字幕语义的理解。
英文字幕必须合成进视频，输出可直接发布的 MP4。
失败后能从指定步骤继续。
每个步骤都能配置。
所有中间产物都能保存。
```

第二期交付目标：

```text
优化字幕在画面中的位置。
优先使用 OpenCV 进行截图、亮度、底部区域和字幕安全区分析。
必要时增加 AI 视觉质检。
提升自动化程度。
减少人工修正成本。
```

整体原则：

```text
先稳定，再智能。
先 CLI，再 UI。
先规则校验，再 AI 校验。
先可断点续跑，再自动闭环。
先英文字幕，再英文配音。
```
