"""Suno tải lại ghi đè «cover 3.wav» → bản _master cũ (bài khác) phải bị coi là cũ."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from backend.cover import mastering


class StaleMasterTests(unittest.TestCase):
    def test_master_older_than_source_is_not_mastered(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "song - cover 3.wav"
            src.write_bytes(b"new")
            for dest in mastering.master_paths(src, "wav"):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"old master")
                old = time.time() - 3600
                os.utime(dest, (old, old))
            self.assertFalse(mastering.already_mastered(src, "wav"))
            for dest in mastering.master_paths(src, "wav"):
                now = time.time() + 5
                os.utime(dest, (now, now))
            self.assertTrue(mastering.already_mastered(src, "wav"))


if __name__ == "__main__":
    unittest.main()
