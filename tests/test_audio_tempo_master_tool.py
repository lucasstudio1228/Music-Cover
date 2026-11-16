from pathlib import Path

import pytest

from audio_tempo_master_tool.audio_engine import (
    AudioToolError,
    atempo_filter,
    normalize_factor,
)


def test_default_4_5x_uses_ffmpeg_safe_atempo_stages():
    assert atempo_filter(4.5) == "atempo=2,atempo=2,atempo=1.125"


@pytest.mark.parametrize("value", [0.19, 5.01, float("nan"), float("inf")])
def test_tempo_rejects_out_of_range_values(value):
    with pytest.raises(AudioToolError):
        normalize_factor(value)


def test_tempo_accepts_full_supported_range():
    assert normalize_factor(0.2) == 0.2
    assert normalize_factor(4.5) == 4.5
    assert normalize_factor(5.0) == 5.0
