# Python 视频英文字幕生成工具

第一期实现一个本地 CLI 闭环：输入中文视频，提取音频，生成中文字幕，AI 校对中文字幕，AI 翻译英文字幕，截图分析字幕位置，生成 ASS 字幕，并用 FFmpeg 烧录成英文字幕视频。

## 环境

需要本机安装：

- Python 3.12 或兼容版本
- FFmpeg / ffprobe，并加入 PATH
- 可选 GPU 环境，用于 faster-whisper

安装依赖：

```bash
pip install -r requirements.txt
```

临时配置大模型 API Key：

先编辑项目根目录的 `config.yaml`，把 `llm_providers.default.api_key` 填成实际密钥。完整跑通后，再迁移到 `.env` 或系统环境变量 `SILICONFLOW_API_KEY`。

## 使用

按 `config.yaml` 里的 `app.input_dir` 批量处理目录内视频：

```bash
python main.py
```

```bash
python main.py --input ./input/demo.mp4 --output ./output
```

断点续跑：

```bash
python main.py --input ./input/demo.mp4 --output ./output --resume
```

从指定步骤开始：

```bash
python main.py --input ./input/demo.mp4 --output ./output --start-from translate
```

指定配置：

```bash
python main.py --input ./input/demo.mp4 --output ./output --config ./configs/config.example.yaml
```

当前推荐使用根目录配置：

```bash
python main.py --input ./input/demo.mp4 --output ./output --config ./config.yaml
```

也可以在 `config.yaml` 里调试某个环节：

```yaml
app:
  start_from: translate
  stop_after: en_check
  only_steps: []
  overwrite_steps:
    - translate
```

只运行单个环节时：

```yaml
app:
  only_steps:
    - translate
  overwrite_steps:
    - translate
```

## 输出

单个视频会输出到 `output/<视频名>/`：

- `audio/original.wav`
- `subtitles/zh_raw.srt`
- `subtitles/zh_clean.srt`
- `subtitles/zh_ai_checked.srt`
- `subtitles/en_raw.srt`
- `subtitles/en_checked.srt`
- `position/screenshots/frame_001.jpg`
- `position/subtitle_position.json`
- `subtitles/english.ass`
- `render/final_en_subtitled.mp4`
- `final_qc/screenshots/final_qc_001.jpg`
- `reports/final_visual_qc_report.json`
- `task_state.json`
- `logs/run.log`

## 注意

`zh_ai_check` 默认在 AI 失败时继续使用 `zh_clean.srt`，但 `translate` 默认不生成占位英文字幕，缺少 API Key 或网络失败会停止在翻译步骤，方便人工处理后续跑。

`screenshot_position` 会在视频中点附近按 1 秒间隔截取 3 张原视频画面，并调用 `qwen3.6-plus-2026-04-02` 给出英文字幕字号和位置建议，尽量避开原视频中文字幕。`final_visual_qc` 会在成品视频中点附近按 1 秒间隔截取 10 张图，先用 OpenCV 硬规则检查字幕是否裁切、过大、过近或重叠，再用视觉模型辅助判断是否影响观看。
