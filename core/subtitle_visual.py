from pathlib import Path
from typing import Any


def frame_has_subtitle_text(frame, step_config: dict[str, Any]) -> bool:
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    raw_mask = ((gray > 165) & (hsv[:, :, 1] < 140)).astype("uint8") * 255
    mask = raw_mask.copy()
    mask[: int(height * float(step_config.get("visual_subtitle_min_y_ratio", 0.50))), :] = 0
    mask[int(height * float(step_config.get("visual_subtitle_max_y_ratio", 0.92))) :, :] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 21), np.uint8), iterations=1)
    mask = cv2.dilate(mask, np.ones((3, 9), np.uint8), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        center_x = x + w / 2
        if not (width * 0.12 <= w <= width * 0.92):
            continue
        if not (height * 0.018 <= h <= height * 0.12):
            continue
        if abs(center_x - width / 2) > width * 0.42:
            continue
        roi = raw_mask[y : y + h, x : x + w]
        count, _, stats, _ = cv2.connectedComponentsWithStats((roi > 0).astype("uint8"), 8)
        component_count = 0
        for label in range(1, count):
            _, _, component_width, component_height, area = [int(value) for value in stats[label]]
            if 6 <= area <= 1600 and component_width >= 2 and component_height >= 5:
                component_count += 1
        if component_count >= int(step_config.get("visual_subtitle_min_components", 8)):
            return True
    return False


def subtitle_visible_near_time(video_path: Path, second: float, step_config: dict[str, Any]) -> bool | None:
    try:
        import cv2
    except ImportError:
        return None

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None
    fps = capture.get(cv2.CAP_PROP_FPS) or 25
    offsets = step_config.get("visual_presence_offsets_seconds", [-0.15, 0.0, 0.15])
    try:
        for offset in offsets:
            current = max(0.0, second + float(offset))
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(current * fps))
            success, frame = capture.read()
            if success and frame_has_subtitle_text(frame, step_config):
                return True
        return False
    finally:
        capture.release()
