import unittest
from unittest.mock import patch

from backend.cover import audio_sources


class AudioSourceTests(unittest.TestCase):
    def test_metadata_strips_variant_for_search(self):
        got = audio_sources.metadata_from_query(
            "Mở Lòng Vì Ai (Thazh x Đông Remix) - Inso")
        self.assertEqual(got["title"], "Mở Lòng Vì Ai")
        self.assertEqual(got["artist"], "Inso")

    def test_official_is_preferred_over_first_remix(self):
        rows = [
            {"title": "Tìm Em Remix", "artist": "Hngle, Bảo Anh", "url": "r"},
            {"title": "Tìm Em", "artist": "Hngle, Bảo Anh", "url": "o"},
        ]
        self.assertEqual(audio_sources._pick("Tìm Em - Hngle Bảo Anh", rows)["url"], "o")

    def test_remix_is_allowed_when_no_official_exists(self):
        rows = [{"title": "Mở Lòng Vì Ai Remix", "artist": "Inso", "url": "r"}]
        self.assertEqual(audio_sources._pick("Mở Lòng Vì Ai - Inso", rows)["url"], "r")

    @patch("backend.cover.audio_sources._youtube_candidates")
    def test_youtube_result_records_provider(self, candidates):
        candidates.return_value = [
            {"title": "Bài A Official Audio", "artist": "Ca sĩ A", "url": "https://youtu.be/a"}
        ]
        got = audio_sources.find_youtube("Bài A - Ca sĩ A", log=lambda _: None)
        self.assertEqual(got["provider"], "youtube")


if __name__ == "__main__":
    unittest.main()
