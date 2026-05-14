from core.ass_builder import _ass_time, _dynamic_source_visual_bottom, _escape_ass


def test_ass_helpers():
    assert _ass_time(1234) == "0:00:01.23"
    assert _escape_ass("a\nb") == r"a\Nb"


def test_dynamic_source_visual_bottom_uses_small_visual_pad():
    band = {"y2": 829}

    assert _dynamic_source_visual_bottom(band, 32, {}) == 834
    assert _dynamic_source_visual_bottom(band, 32, {"dynamic_source_visual_bottom_pad_px": 6}) == 835
