import argparse
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from app.config_loader import load_config
from app.context import TaskContext
from app.pipeline import Pipeline
from utils.log_utils import setup_logger

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate English subtitles and render them into a video.")
    parser.add_argument("--input", help="Input video path. Overrides app.input_path and app.input_dir.")
    parser.add_argument("--input-dir", help="Input directory. Overrides app.input_dir.")
    parser.add_argument("--output", help="Output root directory. Overrides app.output_dir.")
    parser.add_argument("--config", default="./config.yaml", help="YAML config path.")
    parser.add_argument("--resume", action="store_true", help="Resume from failed or pending step.")
    parser.add_argument("--start-from", choices=Pipeline.STEP_ORDER, help="Start from a specific step.")
    parser.add_argument("--stop-after", choices=Pipeline.STEP_ORDER, help="Stop after a specific step.")
    parser.add_argument("--only-step", action="append", choices=Pipeline.STEP_ORDER, help="Run only this step. Can be used multiple times.")
    parser.add_argument("--overwrite-step", action="append", choices=Pipeline.STEP_ORDER, help="Force rerun this step. Can be used multiple times.")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    config = load_config(Path(args.config))
    input_videos = resolve_input_videos(args, config)
    output_dir = Path(args.output or config.get("app", {}).get("output_dir", "./output"))
    if not input_videos:
        raise FileNotFoundError("No supported videos found. Check --input, --input-dir, or app.input_dir in config.yaml.")

    batch_log = output_dir.expanduser().resolve() / "batch.log"
    setup_logger(batch_log)
    logger.info("Found {} video(s) to process.", len(input_videos))

    failures: list[tuple[Path, str]] = []
    for video in input_videos:
        try:
            context = TaskContext.create(video, output_dir, config)
            setup_logger(context.logs_dir / "run.log")
            logger.info("Processing video: {}", video)
            Pipeline(
                config=config,
                context=context,
                resume=args.resume or bool(config.get("app", {}).get("resume", True)),
                start_from=args.start_from or config.get("app", {}).get("start_from"),
                stop_after=args.stop_after or config.get("app", {}).get("stop_after"),
                only_steps=args.only_step or config.get("app", {}).get("only_steps") or [],
                overwrite_steps=args.overwrite_step or config.get("app", {}).get("overwrite_steps") or [],
            ).run()
        except Exception as exc:
            failures.append((video, str(exc)))
            logger.error("Video failed: {} | {}", video, exc)

    if failures:
        failed = "\n".join(f"{path}: {error}" for path, error in failures)
        raise RuntimeError(f"{len(failures)} video(s) failed:\n{failed}")


def resolve_input_videos(args: argparse.Namespace, config: dict) -> list[Path]:
    app_config = config.get("app", {})
    if args.input:
        return [Path(args.input).expanduser().resolve()]
    configured_input = app_config.get("input_path")
    if configured_input:
        return [Path(configured_input).expanduser().resolve()]
    input_dir = Path(args.input_dir or app_config.get("input_dir", "./input")).expanduser().resolve()
    if not input_dir.exists():
        return []
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )
