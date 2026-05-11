def seconds_to_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    millis = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt_time_to_ms(value: str) -> int:
    hours_part, millis_part = value.split(",")
    hours, minutes, seconds = [int(part) for part in hours_part.split(":")]
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + int(millis_part)


def ms_to_srt_time(ms: int) -> str:
    return seconds_to_srt_time(ms / 1000)
