"""Thư mục nhac_mix (2026-11-10): mỗi project giữ đúng 1 file nhạc đã mix."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.cover import mix_export
from backend.video import config


class MixExportTests(unittest.TestCase):
    def test_keeps_exactly_one_latest_mix_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "media"
            (media / "Bài A (#5)").mkdir(parents=True)
            first = root / "out1" / "mix.wav"
            first.parent.mkdir()
            first.write_bytes(b"first")
            second = root / "out2" / "mix.wav"
            second.parent.mkdir()
            second.write_bytes(b"second")
            with patch.object(config, "MEDIA_ROOT", media):
                d1 = mix_export.export_mix_audio(5, "Bài A", first)
                d2 = mix_export.export_mix_audio(5, "Bài A", second)
            folder = media / "Bài A (#5)" / "nhac_mix"
            self.assertEqual(d1, d2)
            self.assertEqual([p.name for p in folder.iterdir()], ["Bài A.wav"])
            self.assertEqual(d2.read_bytes(), b"second")
            # Mix gốc không bị đụng.
            self.assertEqual(first.read_bytes(), b"first")

    def test_missing_source_is_ignored(self):
        with TemporaryDirectory() as tmp:
            with patch.object(config, "MEDIA_ROOT", Path(tmp)):
                self.assertIsNone(mix_export.export_mix_audio(1, "x", Path(tmp) / "no.wav"))


if __name__ == "__main__":
    unittest.main()
