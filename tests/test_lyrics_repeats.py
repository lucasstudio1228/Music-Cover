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

    def test_expand_source_lyrics_from_audio_and_auto_stanzas(self):
        import tempfile
        from pathlib import Path
        from backend.cover.align import expand_source_lyrics_from_audio
        from backend.cover.suno_lyrics import normalize_for_suno

        lines = [
            "Từ lúc quen nhau chưa nói lời nào",
            "Nhiều đêm ngắm sao mơ ước duyên mình",
            "Nhớ thương đầy vơi mộng thấy ai về",
            "Để rồi buồn ơi ánh trăng còn đó",
            "Hôm nay nhìn xe kết hoa xuôi ngược",
            "Gửi thư trao người vài câu luyến thương",
            "Chiều tím không mây đường cũ bước về",
            "Sầu dâng lên tím biết bao giờ khuây",
        ]
        sung = lines + lines[4:]

        class FakeModel:
            def transcribe(self, *_args, **_kwargs):
                return SimpleNamespace(segments=[
                    SimpleNamespace(text=text, start=i * 6.0, end=i * 6.0 + 4.0)
                    for i, text in enumerate(sung)
                ])

        with tempfile.TemporaryDirectory() as d:
            audio_file = Path(d) / "song.wav"
            audio_file.write_bytes(b"fake")
            with patch("soundfile.info", return_value=SimpleNamespace(duration=240.0)), \
                 patch("backend.cover.align._load_mono16k",
                       return_value=np.zeros(16000, dtype=np.float32)), \
                 patch("backend.cover.align._get_whisper", return_value=FakeModel()), \
                 patch("backend.cover.align.release_models"):
                expanded_txt = expand_source_lyrics_from_audio(
                    audio_file, "\n".join(lines))

        self.assertEqual(expanded_txt.splitlines(), sung)
        # Bài dính liền 1 khối >= 8 câu được tự ngắt thành các khổ 4 câu cách nhau 1 dòng trống.
        suno_txt = normalize_for_suno(expanded_txt)
        paragraphs = suno_txt.split("\n\n")
        self.assertEqual(len(paragraphs), 3)
        self.assertTrue(all(len(p.splitlines()) == 4 for p in paragraphs))
        self.assertTrue(all("_" in ln for p in paragraphs for ln in p.splitlines()))

    def test_align_between_first_and_last_anchors_locks_edges_and_realigns_middle(self):
        from backend.cover.align import WHISPER_SR, align_between_anchors

        lines_in = [
            {"text": "Câu mở đầu đã căn tay", "start": 25.0, "end": 29.0},
            {"text": "Câu giữa một bị lệch", "start": 2.0, "end": 4.0},
            {"text": "Câu giữa hai bị lệch", "start": 5.0, "end": 7.0},
            {"text": "Câu giữa ba bị lệch", "start": 8.0, "end": 10.0},
            {"text": "Câu kết bài đã căn tay", "start": 180.0, "end": 185.5},
        ]
        seen_slices = []

        class SliceModel:
            def align(self, audio_slice, text, **_kw):
                seen_slices.append((len(audio_slice) / WHISPER_SR, text.splitlines()))
                # Trả mốc tương đối tính từ 0 của lát cắt [29.0s .. 180.0s]
                return SimpleNamespace(segments=[
                    SimpleNamespace(text="Câu giữa một bị lệch", start=4.0, end=9.0),
                    SimpleNamespace(text="Câu giữa hai bị lệch", start=50.0, end=56.0),
                    SimpleNamespace(text="Câu giữa ba bị lệch", start=110.0, end=116.5),
                ])

        fake_audio = np.zeros(220 * WHISPER_SR, dtype=np.float32)
        with patch("backend.cover.align.separate_vocals", return_value="vocals.wav"), \
             patch("backend.cover.align._load_mono16k", return_value=fake_audio), \
             patch("backend.cover.align._get_whisper", return_value=SliceModel()):
            out = align_between_anchors(1, "song.wav", lines_in)

        self.assertEqual(len(seen_slices), 1)
        self.assertAlmostEqual(seen_slices[0][0], 180.0 - 29.0, places=2)
        self.assertEqual(seen_slices[0][1], [
            "Câu giữa một bị lệch", "Câu giữa hai bị lệch", "Câu giữa ba bị lệch",
        ])
        # Câu đầu & câu cuối giữ nguyên tuyệt đối mốc người dùng đã chỉnh.
        self.assertEqual(out[0], {"text": "Câu mở đầu đã căn tay", "start": 25.0, "end": 29.0})
        self.assertEqual(out[-1], {"text": "Câu kết bài đã căn tay", "start": 180.0, "end": 185.5})
        # Các câu giữa được cộng đúng offset 29.0s của cuối câu đầu.
        self.assertEqual(out[1], {"text": "Câu giữa một bị lệch", "start": 33.0, "end": 38.0})
        self.assertEqual(out[2], {"text": "Câu giữa hai bị lệch", "start": 79.0, "end": 85.0})
        self.assertEqual(out[3], {"text": "Câu giữa ba bị lệch", "start": 139.0, "end": 145.5})

    def test_align_between_handles_start_only_first_anchor_and_rejects_inverted_anchors(self):
        from backend.cover.align import WHISPER_SR, align_between_anchors

        # Người dùng mới chấm start=30s cho câu đầu nhưng end cũ vẫn là 95s (>15s):
        lines_in = [
            {"text": "Câu đầu", "start": 30.0, "end": 95.0},
            {"text": "Câu giữa", "start": 1.0, "end": 2.0},
            {"text": "Câu cuối", "start": 90.0, "end": 94.0},
        ]

        class JointModel:
            def align(self, _audio_slice, text, **_kw):
                assert text.splitlines() == ["Câu đầu", "Câu giữa"]
                return SimpleNamespace(segments=[
                    SimpleNamespace(text="Câu đầu", start=0.0, end=4.2),
                    SimpleNamespace(text="Câu giữa", start=20.0, end=25.0),
                ])

        fake_audio = np.zeros(120 * WHISPER_SR, dtype=np.float32)
        with patch("backend.cover.align.separate_vocals", return_value="vocals.wav"), \
             patch("backend.cover.align._load_mono16k", return_value=fake_audio), \
             patch("backend.cover.align._get_whisper", return_value=JointModel()):
            out = align_between_anchors(1, "song.wav", lines_in)

        self.assertEqual(out[0]["start"], 30.0)
        self.assertAlmostEqual(out[0]["end"], 34.2, places=2)
        self.assertEqual(out[1], {"text": "Câu giữa", "start": 50.0, "end": 55.0})
        self.assertEqual(out[2], {"text": "Câu cuối", "start": 90.0, "end": 94.0})

        # Câu cuối nhỏ hơn câu đầu → báo lỗi rõ ràng.
        bad_lines = [
            {"text": "Đầu", "start": 100.0, "end": 103.0},
            {"text": "Giữa", "start": 50.0, "end": 52.0},
            {"text": "Cuối", "start": 80.0, "end": 84.0},
        ]
        with self.assertRaisesRegex(ValueError, "phải lớn hơn"):
            align_between_anchors(1, "song.wav", bad_lines)

    def test_align_between_repairs_collapsed_middle_cluster_after_solo(self):
        """Khi Whisper gom chụm 3 câu giữa bài vào 158.12..158.24s (0.00s) trước câu
        ở 184.68s sau đoạn nhạc dạo, bộ sửa cụm chụm phải phân bổ lại trên vùng vocal."""
        from backend.cover.align import WHISPER_SR, align_between_anchors

        lines_in = [
            {"text": "Câu mở đầu", "start": 12.0, "end": 20.0},
            {"text": "Câu ổn trước nhạc dạo", "start": 138.0, "end": 146.5},
            {"text": "Hôm nay nhìn xe kết hoa xuôi ngược nẻo đường", "start": 158.12, "end": 158.24},
            {"text": "Gửi thư trao cho người yêu vài câu luyến thương", "start": 158.24, "end": 158.24},
            {"text": "Hân hoan hồn như nở hoa trông chờ hồi âm", "start": 158.24, "end": 159.5},
            {"text": "Tắt ngay trong lòng chỉ thấy thiệp hồng", "start": 184.68, "end": 189.12},
            {"text": "Câu kết cuối bài", "start": 238.0, "end": 245.0},
        ]

        class CollapsedMiddleModel:
            def align(self, _audio_slice, text, **_kw):
                assert len(text.splitlines()) == 5
                # win_start = 20.0 → cộng thêm 20s sẽ tái hiện đúng cụm chụm 158.12..158.24
                return SimpleNamespace(segments=[
                    SimpleNamespace(text="1", start=118.0, end=126.5),
                    SimpleNamespace(text="2", start=138.12, end=138.24),
                    SimpleNamespace(text="3", start=138.24, end=138.24),
                    SimpleNamespace(text="4", start=138.24, end=138.30),
                    SimpleNamespace(text="5", start=164.68, end=169.12),
                ])

        fake_audio = np.zeros(260 * WHISPER_SR, dtype=np.float32)
        with patch("backend.cover.align.separate_vocals", return_value="vocals.wav"), \
             patch("backend.cover.align._load_mono16k", return_value=fake_audio), \
             patch("backend.cover.align._vocal_regions", return_value=[(12.0, 146.5), (168.0, 245.0)]), \
             patch("backend.cover.align._get_whisper", return_value=CollapsedMiddleModel()):
            out = align_between_anchors(1, "song.wav", lines_in)

        # Cụm câu [2..4] không còn bị chụm 0 giây ở 158s mà được dải vào vùng hát 168..184.68s
        for idx in (2, 3, 4):
            self.assertGreaterEqual(out[idx]["start"], 168.0)
            self.assertLessEqual(out[idx]["end"], 184.7)
            self.assertGreaterEqual(out[idx]["end"] - out[idx]["start"], 1.5)
        self.assertAlmostEqual(out[1]["start"], 138.0, places=2)
        self.assertAlmostEqual(out[5]["start"], 184.68, places=2)


if __name__ == "__main__":
    unittest.main()
