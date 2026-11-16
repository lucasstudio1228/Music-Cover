import unittest
import unicodedata

from backend.cover.lyrics_export import build_srt, lyric_timeline


class LyricsSrtExportTests(unittest.TestCase):
    def test_srt_has_only_lyrics_in_mix_time(self):
        info = {"audio": {"total_duration_seconds": 60.0}, "tracks": [
            {"song_id": 1, "name": "Bài A", "start_seconds": 0.0, "end_seconds": 32.0,
             "src_offset_seconds": 10.0},
            {"song_id": 2, "name": "Bài B", "start_seconds": 28.0, "end_seconds": 60.0,
             "src_offset_seconds": 0.0},
        ]}
        nfd = unicodedata.normalize("NFD", "Mưa  đã tạnh")
        lines = {
            1: [{"text": "trước đoạn cắt", "start": 2.0, "end": 4.0},
                {"text": nfd, "start": 12.0, "end": 15.0},
                {"text": "câu hai", "start": 16.0, "end": 18.0}],
            2: [{"text": "bài sau", "start": 5.0, "end": 8.0}],
        }
        tl = lyric_timeline(info, lines)
        self.assertEqual([t for _, _, t in tl], ["Mưa đã tạnh", "câu hai", "bài sau"])
        self.assertEqual(tl[0][0], 2.0)              # 28 + (12 - 10) → 2s trong mix
        self.assertEqual(tl[0][1], 6.0)              # tới câu sau thì đổi
        self.assertAlmostEqual(tl[1][1], 10.0)       # hát xong + giữ 2s
        self.assertEqual(tl[2][0], 33.0)
        srt = build_srt(tl)
        self.assertTrue(srt.startswith("1\n00:00:02,000 --> 00:00:06,000\nMưa đã tạnh\n"))
        self.assertNotIn("Bài A", srt)
        self.assertNotIn("Bài B", srt)
        self.assertTrue(unicodedata.is_normalized("NFC", srt))


if __name__ == "__main__":
    unittest.main()
