from pathlib import Path

from loguru import logger


def setup_logger(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO", backtrace=False, diagnose=False)
    logger.add(log_path, level="DEBUG", encoding="utf-8", rotation="10 MB", backtrace=False, diagnose=False)
