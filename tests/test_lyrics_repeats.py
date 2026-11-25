import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from backend.cover.align import _vocal_regions, align_lines, expand_repeated_lyrics


def seg(text, start):
    return {"text": text, "start": start, "end": start + 2.0}


class RepeatLyricsTests(unittest.TestCase):
    def test_full_song_sung_twice_is_expanded_twice(self):
        lines = ["Câu mở đầu", "Câu tiếp theo", "Điệp khúc một", "Điệp khúc hai"]
        heard = [seg(text, i * 3) for i, text in enumerate(lines + lines)]
        self.assertEqual(expand_repeated_lyrics(lines, heard), lines + lines)

    def test_only_chorus_repeated_does_not_repeat_verse(self):
        lines = ["Verse câu một", "Verse câu hai", "Chorus câu một", "Chorus câu hai"]
        expected = lines + lines[2:]
        heard = [seg(text, i * 3) for i, text in enumerate(expected)]
        self.assertEqual(expand_repeated_lyrics(lines, heard), expected)

    def test_minor_asr_spelling_errors_still_match(self):
        lines = ["Mùa đông năm này tô son", "Màu xuân xanh đón em về"]
        heard = [seg("mua dong nam nay to son", 0), seg("mau xuan xanh don em ve", 3),
                 seg("mùa đông năm nay tô xon", 20), seg("màu xuân xanh đón em về", 23)]
        self.assertEqual(expand_repeated_lyrics(lines, heard), lines + lines)

    def test_adjacent_split_segments_do_not_duplicate_one_line(self):
        lines = ["Giọt sương âm thầm giăng mây", "Rét đôi vai gầy"]
        heard = [seg("Giọt sương âm thầm", 0), seg("giăng mây", 2.1),
                 seg("Rét đôi vai gầy", 5)]
        self.assertEqual(expand_repeated_lyrics(lines, heard), lines)

    def test_sparse_transcript_never_drops_original_lyrics(self):
        lines = [f"Câu lời số {i}" for i in range(16)]
        heard = [seg(lines[i], pos * 4) for pos, i in enumerate((0, 2, 5, 8, 11, 14))]
        self.assertEqual(expand_repeated_lyrics(lines, heard), lines)

    def test_long_late_vocal_region_repeats_tail_when_asr_hallucinates(self):
        lines = [f"Câu hát riêng biệt số {i}" for i in range(16)]
        heard = [seg(text, 32 + i * 4) for i, text in enumerate(lines)]
        # Vùng vocal sau dài khoảng nửa lượt đầu nhưng ASR nghe sai toàn bộ.
        heard += [
            {"text": "hãy đăng ký theo dõi kênh chương trình", "start": 128, "end": 139},
            {"text": "cảm ơn các bạn đã theo dõi", "start": 153, "end": 159},
        ]
        expanded = expand_repeated_lyrics(lines, heard)
        self.assertEqual(expanded[:16], lines)
        self.assertEqual(expanded[16:], lines[-8:])

    def test_late_vocal_energy_recovers_repeat_when_asr_returns_nothing(self):
        lines = [f"Câu hát riêng biệt số {i}" for i in range(16)]
        heard = [seg(text, 32 + i * 4) for i, text in enumerate(lines)]
        expanded = expand_repeated_lyrics(
            lines, heard, vocal_regions=[(32, 96), (128, 160)])
        self.assertEqual(expanded, lines + lines[-8:])

    def test_vocal_region_detector_ignores_short_noise(self):
        audio = np.zeros(12 * 16000, dtype=np.float32)
        audio[1 * 16000:2 * 16000] = 0.2       # tiếng rò ngắn
        audio[5 * 16000:10 * 16000] = 0.2      # vùng hát đủ dài
        regions = _vocal_regions(audio)
        self.assertEqual(len(regions), 1)
        self.assertAlmostEqual(regions[0][0], 5.0, delta=0.3)
        self.assertAlmostEqual(regions[0][1], 10.0, delta=0.3)

    def test_align_lines_forces_every_detected_repeat_into_timeline(self):
        lines = ["Verse một", "Verse hai", "Điệp khúc một", "Điệp khúc hai"]
        sung = lines + lines[2:]

        class FakeModel:
            aligned_text = ""
            transcribe_language = ""
            align_language = ""

            def transcribe(self, *_args, **kwargs):
                self.transcribe_language = kwargs.get("language")
                return SimpleNamespace(segments=[
                    SimpleNamespace(text=text, start=i * 3.0, end=i * 3.0 + 2.0)
                    for i, text in enumerate(sung)
                ])

            def align(self, _audio, text, **kwargs):
                self.aligned_text = text
                self.align_language = kwargs.get("language")
                requested = text.splitlines()
                return SimpleNamespace(segments=[
                    SimpleNamespace(text=value, start=i * 3.0, end=i * 3.0 + 2.0)
                    for i, value in enumerate(requested)
                ])

        model = FakeModel()
        with patch("backend.cover.align._load_mono16k",
                   return_value=np.zeros(16000, dtype=np.float32)), \
             patch("backend.cover.align._get_whisper", return_value=model):
            result = align_lines("unused.wav", lines, "en")

        self.assertEqual(model.aligned_text.splitlines(), sung)
        self.assertEqual(model.transcribe_language, "vi")
        self.assertEqual(model.align_language, "vi")
        self.assertEqual([row["text"] for row in result], sung)
        self.assertEqual(result[-1]["start"], 15.0)


if __name__ == "__main__":
    unittest.main()
