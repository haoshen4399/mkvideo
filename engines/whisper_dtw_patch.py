from __future__ import annotations

from typing import Any

import numpy as np


def force_python_dtw() -> bool:
    """Avoid numba/llvmlite DTW crashes on Windows Python 3.12.

    OpenAI Whisper, stable-ts, and related timestamp engines use
    whisper.timing.dtw_cpu for word alignment. In this environment llvmlite can
    crash the whole interpreter while compiling that function, so we replace the
    numba dispatchers with their original Python functions before transcription.
    """
    try:
        import whisper
        import whisper.timing as timing
    except ImportError:
        return False

    timing.backtrace = _backtrace_python
    timing.dtw_cpu = _dtw_cpu_python
    timing.dtw = _dtw_python
    if hasattr(whisper, "timing"):
        whisper.timing.backtrace = _backtrace_python
        whisper.timing.dtw_cpu = _dtw_cpu_python
        whisper.timing.dtw = _dtw_python
    return True


def _dtw_python(x: Any) -> np.ndarray:
    """Pure Python/NumPy DTW entrypoint that bypasses numba entirely."""
    if hasattr(x, "double"):
        x = x.double().cpu().numpy()
    return _dtw_cpu_python(np.asarray(x, dtype=np.float64))


def _dtw_cpu_python(x: np.ndarray) -> np.ndarray:
    n, m = x.shape
    cost = np.ones((n + 1, m + 1), dtype=np.float64) * np.inf
    trace = -np.ones((n + 1, m + 1), dtype=np.int8)
    cost[0, 0] = 0.0

    for j in range(1, m + 1):
        for i in range(1, n + 1):
            c0 = cost[i - 1, j - 1]
            c1 = cost[i - 1, j]
            c2 = cost[i, j - 1]
            if c0 < c1 and c0 < c2:
                c, t = c0, 0
            elif c1 < c0 and c1 < c2:
                c, t = c1, 1
            else:
                c, t = c2, 2
            cost[i, j] = float(x[i - 1, j - 1]) + c
            trace[i, j] = t

    return _backtrace_python(trace)


def _backtrace_python(trace: np.ndarray) -> np.ndarray:
    i = trace.shape[0] - 1
    j = trace.shape[1] - 1
    trace[0, :] = 2
    trace[:, 0] = 1

    result: list[tuple[int, int]] = []
    while i > 0 or j > 0:
        result.append((i - 1, j - 1))
        value = trace[i, j]
        if value == 0:
            i -= 1
            j -= 1
        elif value == 1:
            i -= 1
        elif value == 2:
            j -= 1
        else:
            raise ValueError(f"Unexpected trace value: {value}")

    return np.array(result, dtype=np.int64)[::-1, :].T
