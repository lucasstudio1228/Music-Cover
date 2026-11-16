import unittest

from backend.cover.chatgpt_lyrics import (
    LyricsTransformError,
    _clean_reply,
    _validate,
    local_artistic_transform,
)


class ChatGPTLyricsTests(unittest.TestCase):
    def test_valid_uses_plain_unicode_and_natural_spaces(self):
        _validate("Xin chào\nEm ơi", "Xin chào\nEm ơi")

    def test_rejects_changed_line_count(self):
        with self.assertRaises(LyricsTransformError):
            _validate("Một\nHai", "𝓜ộ𝓽")

    def test_rejects_underscore_output(self):
        with self.assertRaises(LyricsTransformError):
            _validate("Xin chào", "Xin_chào")

    def test_clean_reply_removes_code_fence(self):
        self.assertEqual(_clean_reply("```text\n𝓧𝓲𝓷_𝓬𝓱à𝓸\n```"), "𝓧𝓲𝓷_𝓬𝓱à𝓸")

    def test_local_fallback_preserves_vietnamese_and_spaces(self):
        source = "Ngồi ngẩn ngơ\nEm ơi 123"
        result = local_artistic_transform(source)
        _validate(source, result)
        self.assertEqual(len(result.splitlines()), 2)
        self.assertIn(" ", result)
        self.assertNotIn("_", result)

    def test_rejects_translation_even_with_same_line_count(self):
        with self.assertRaises(LyricsTransformError):
            _validate("Em yêu anh", "나는 너를 사랑해")

    def test_removes_section_labels_but_keeps_lyrics(self):
        source = "[Verse 1: Hngle]\nNgồi ngẩn ngơ\n[Chorus: Hngle]\nĐi khắp thiên hà"
        result = local_artistic_transform(source)
        _validate(source, result)
        self.assertNotIn("[Verse", result)
        self.assertNotIn("[Chorus", result)
        self.assertIn("Ngồi ngẩn ngơ", result)
        self.assertIn("Đi khắp thiên hà", result)

    def test_unicode_ellipsis_is_not_reported_as_changed_content(self):
        source = "Sao anh không đau…\nEm đi rồi thôi…"
        result = local_artistic_transform(source)
        _validate(source, result)

    def test_removes_song_title_header_before_and_after_underscore_transform(self):
        expected = "Rồi mùa yêu thương dần đang đến"
        self.assertEqual(
            local_artistic_transform(
                "Bài hát: Sao Mình Chưa Nắm Tay Nhau - Yan Nguyễn\n\n"
                "Rồi mùa yêu thương dần đang đến"),
            expected,
        )
        self.assertEqual(
            local_artistic_transform(
                "Bài_hát:_Sao_Mình_Chưa_Nắm_Tay_Nhau_-_Yan_Nguyễn\n\n"
                "Rồi_mùa_yêu_thương_dần_đang_đến"),
            expected,
        )


if __name__ == "__main__":
    unittest.main()
