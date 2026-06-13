"""Unit tests for the sparkline / render_row trend helpers (pure functions)."""

from runforlife.skills.analysis.sparkline import render_row, sparkline


def test_empty_series_is_empty_string():
    assert sparkline([]) == ""
    assert sparkline([None, None]) == ""


def test_flat_series_renders_lowest_block():
    assert sparkline([5, 5, 5]) == "▁▁▁"


def test_ascending_series_spans_low_to_high():
    s = sparkline([0, 1, 2, 3, 4, 5, 6, 7])
    assert s[0] == "▁"          # lowest
    assert s[-1] == "█"         # highest
    assert len(s) == 8


def test_gaps_render_as_space():
    s = sparkline([1, None, 9])
    assert s[1] == " "
    assert s[0] == "▁" and s[2] == "█"


def test_two_point_min_max():
    assert sparkline([10, 20]) == "▁█"


def test_render_row_direction_and_range():
    row = render_row("RHR", [50, 49, 48, 47], unit="bpm")
    assert "RHR" in row
    assert "↓" in row            # falling
    assert "50" in row and "47" in row
    assert "47–50" in row


def test_render_row_no_data():
    assert "(no data)" in render_row("HRV", [None, None])


def test_render_row_flat_uses_right_arrow():
    assert "→" in render_row("X", [3, 3, 3])
