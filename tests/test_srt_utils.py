from utils.srt_utils import parse_srt_text, format_srt, validate_basic


def test_parse_and_format_srt():
    text = """1
00:00:01,000 --> 00:00:02,000
你好

2
00:00:02,100 --> 00:00:03,000
世界
"""
    items = parse_srt_text(text)
    assert len(items) == 2
    assert items[0].text == "你好"
    assert validate_basic(items) == []
    assert "00:00:01,000 --> 00:00:02,000" in format_srt(items)
