"""外呼任务时间窗逻辑单元测试。"""
from datetime import datetime, timezone

from app.workers.voice_worker import _in_window


def test_in_window_shanghai_daytime():
    # 10:00 UTC = 18:00 Asia/Shanghai
    utc = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    assert _in_window(utc, "Asia/Shanghai", "09:00", "21:00") is True


def test_in_window_shanghai_outside():
    # 22:00 UTC Jan 1 = Jan 2 06:00 Shanghai — 不在 09:00–21:00
    utc = datetime(2025, 1, 1, 22, 0, tzinfo=timezone.utc)
    assert _in_window(utc, "Asia/Shanghai", "09:00", "21:00") is False


def test_in_window_cross_midnight_inside_evening():
    # 15:00 UTC = 23:00 Shanghai，跨午夜窗 22:00–06:00
    utc = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)
    assert _in_window(utc, "Asia/Shanghai", "22:00", "06:00") is True


def test_in_window_cross_midnight_early_morning():
    # 21:00 UTC Jan 1 = Jan 2 05:00 Shanghai
    utc = datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc)
    assert _in_window(utc, "Asia/Shanghai", "22:00", "06:00") is True


def test_in_window_cross_midnight_outside():
    # 04:00 UTC = 12:00 Shanghai — 不在 22:00–06:00
    utc = datetime(2025, 1, 1, 4, 0, tzinfo=timezone.utc)
    assert _in_window(utc, "Asia/Shanghai", "22:00", "06:00") is False


def test_in_window_empty_window_always_true():
    utc = datetime(2025, 1, 1, 4, 0, tzinfo=timezone.utc)
    assert _in_window(utc, "Asia/Shanghai", None, None) is True
