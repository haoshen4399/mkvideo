# mkvideo

本项目是一个本地视频字幕自动化流水线：把中文短剧视频批量处理成带英文字幕、双语封面标题和 1 秒封面片头的成品视频。

默认使用 `config.yaml` 控制所有行为。日常只需要把视频放进 `input/`，然后运行：

```bash
python main.py
```

## 功能

- 批量读取 `input/` 下的 `.mp4`、`.mov`、`.mkv`
- 提取音频并执行中文 ASR
- 中文字幕后处理和 AI 校对
- AI 翻译英文字幕，并做英文字幕长度、行数、阅读速度检查
- 根据原视频中文字幕位置生成英文 ASS 字幕
- 渲染英文字幕到视频
- 自动检测中英文字幕间距，并迭代调整字幕位置
- 根据字幕内容生成中英双语封面标题图
- 把封面图插入为成品视频最前面的 1 秒片头
- 使用 OpenCV 硬规则和视觉模型做最终视觉质检
- 每个视频输出步骤状态、报告和日志，方便定位失败点

## 环境

需要本机安装：

- Python 3.12
- FFmpeg / ffprobe
- 项目依赖：

```bash
pip install -r requirements.txt
```

如果 FFmpeg 不在 PATH，可以在 `config.yaml` 的 `app.ffmpeg_path`、`app.ffprobe_path` 中配置绝对路径。

## 配置

主要配置都在 `config.yaml`：

```yaml
app:
  input_dir: ./input
  output_dir: ./output
  resume: false
```

常用行为：

- `app.resume: false`：默认从头执行，不因为旧输出直接结束。
- `app.resume: true`：断点续跑，已成功且配置未变化的步骤会跳过。
- `app.only_steps`：只执行某些步骤，适合调试。
- `app.overwrite_steps`：强制重跑某些步骤。

大模型配置在 `llm_providers`。建议把 API Key 放到 `.env` 或系统环境变量，不要提交真实密钥。

## 处理流程

流水线顺序：

1. `probe_video`
2. `extract_audio`
3. `asr`
4. `zh_postprocess`
5. `zh_ai_check`
6. `translate`
7. `en_check`
8. `cover_title`
9. `screenshot_position`
10. `build_ass`
11. `render_video`
12. `subtitle_layout_fit`
13. `cover_intro`
14. `final_visual_qc`

`cover_intro` 是幂等步骤：会保留 `render/final_en_subtitled.no_cover_intro.mp4` 作为未插封面的底稿，重复执行时不会一层一层叠加封面。

`final_visual_qc` 会考虑封面片头带来的时间轴偏移，比较原视频和最终视频时会自动跳过封面片头的偏移量。

## 输出

每个视频会输出到：

```text
output/<视频文件名>/
```

常见文件：

- `audio/original.wav`
- `subtitles/zh_raw.srt`
- `subtitles/zh_clean.srt`
- `subtitles/zh_ai_checked.srt`
- `subtitles/en_raw.srt`
- `subtitles/en_checked.srt`
- `subtitles/english.ass`
- `cover/cover.jpg`
- `render/final_en_subtitled.mp4`
- `render/final_en_subtitled.no_cover_intro.mp4`
- `position/subtitle_position.json`
- `final_qc/screenshots/*.jpg`
- `reports/*.json`
- `logs/run.log`
- `task_state.json`

## 稳定性设计

### ASR 隔离

Whisper、stable-ts、torch、numba、llvmlite 在 Windows / Python 3.12 下可能触发 native crash。ASR 默认在独立子进程中运行，主流程可以拿到明确失败信息，并尽量释放资源。

配置项：

```yaml
steps:
  asr:
    isolate_process: true
    word_timestamps: false
```

`word_timestamps: false` 用于避免 Whisper 词级 DTW 在 Windows 上触发 llvmlite/numba 崩溃。当前项目以句级字幕为主，不依赖词级时间戳。

### LLM 子进程

OpenAI-compatible 请求通过独立 worker 执行，减少 SDK、证书、代理、导入崩溃对主进程的影响。worker 输出 JSON，主进程负责解析和报错。

### 字幕布局闭环

`subtitle_layout_fit` 会在渲染后重新抽帧检测真实字幕位置，自动调整 ASS 坐标并重渲染，目标是让中文和英文字幕贴近但不重叠。

### 最终视觉质检

`final_visual_qc` 以 OpenCV 几何硬规则为主，视觉模型作为辅助提醒。视觉模型单独误判时默认不会让整个流程失败：

```yaml
steps:
  final_visual_qc:
    fail_on_ai_visual_fail: false
```

如果 OpenCV 检测到明确重叠、裁切或字幕缺失，仍会失败，方便及时修正。

## 清理残留进程

如果 PyCharm 或终端中断导致 Python / FFmpeg 子进程残留，可以运行：

```bat
cleanup_processes.bat
```

强制清理：

```bat
cleanup_processes_force.bat
```

也可以直接运行 Python 工具：

```bash
python tools/cleanup_processes.py --dry-run
python tools/cleanup_processes.py --force
```

## 日志和排错

- 总批次日志：`output/batch.log`
- 单个视频日志：`output/<视频名>/logs/run.log`
- FFmpeg 渲染日志：`logs/ffmpeg.log`
- 封面片头日志：`logs/ffmpeg_cover_intro.log`
- 每个步骤状态：`task_state.json`

如果最终控制台报错，优先看对应视频的 `task_state.json` 和 `reports/*.json`。批总结会列出每个视频每个步骤的状态。

## 开发验证

常用检查：

```bash
python -m py_compile app\pipeline.py core\final_visual_qc.py core\cover_intro.py utils\ffmpeg_utils.py
```

运行测试：

```bash
pytest
```
