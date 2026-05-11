from core.ass_builder import _ass_time, _escape_ass


def test_ass_helpers():
    assert _ass_time(1234) == "0:00:01.23"
    assert _escape_ass("a\nb") == r"a\Nb"
