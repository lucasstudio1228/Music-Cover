"""Bước 6: chuẩn hoá lời cho ô Lyrics của Suno theo quy tắc người dùng chốt."""
import unittest
import unicodedata

from backend.cover.suno_lyrics import normalize_for_suno as norm


class LabelTests(unittest.TestCase):
    def test_label_only_lines_removed_and_become_paragraph_breaks(self):
        raw = "Intro\nCâu một\nVerse 1:\nCâu hai\n[Chorus]\nCâu ba\nĐK:\nCâu bốn\n(Pre-Chorus)\nCâu năm"
        self.assertEqual(norm(raw), "Câu một\n\nCâu hai\n\nCâu ba\n\nCâu bốn\n\nCâu năm")

    def test_vietnamese_labels(self):
        for label in ("Điệp khúc", "ĐK", "Đk:", "đk 2", "Phiên khúc", "PK", "Lời 1", "Lời 2:",
                      "Nhạc dạo", "Kết", "Rap", "Bridge", "Outro", "Interlude", "Instrumental",
                      "Hook", "Post-Chorus", "[Verse 2: Mỹ Tâm]", "*Chorus*", "ĐK (x2)", "(x2)"):
            self.assertEqual(norm(f"A b\n{label}\nC d"), "A b\n\nC d", label)

    def test_label_prefix_keeps_lyric(self):
        self.assertEqual(norm("Câu đầu\nĐK: Đừng buồn em ơi"), "Câu đầu\n\nĐừng buồn em ơi")
        self.assertEqual(norm("[Chorus] Baby đừng đi"), "Baby đừng đi")

    def test_lyric_starting_with_label_like_word_kept(self):
        self.assertEqual(norm("Kết thúc rồi em ơi\nRap đời anh"), "Kết thúc rồi em ơi\nRap đời anh")
        self.assertEqual(norm("(Oh oh oh)"), "(Oh oh oh)")


class CharacterTests(unittest.TestCase):
    def test_art_fonts_become_lowercase_letters(self):
        self.assertEqual(norm("𝐀𝐧𝐡 𝓨𝓮̂𝓾 Ｅｍ ⓐ 🅑 ᴄ"), "anh yêu em a b c")

    def test_underscore_and_underscore_comma(self):
        self.assertEqual(norm("Anh_đi_tìm_em_,_giữa_phố"), "Anh đi tìm em, giữa phố")
        self.assertEqual(norm("Anh_đi_,về"), "Anh đi, về")

    def test_invisible_nbsp_emoji_markdown_removed(self):
        raw = "\ufeff# Anh\u200b\u00a0đi 🎵❤️\n> - **về** nhà ♪"
        self.assertEqual(norm(raw), "Anh đi\nvề nhà")

    def test_vietnamese_nfc_and_case_kept(self):
        decomposed = unicodedata.normalize("NFD", "Người Ơi, Tình Yêu")
        out = norm(decomposed)
        self.assertEqual(out, "Người Ơi, Tình Yêu")
        self.assertTrue(unicodedata.is_normalized("NFC", out))

    def test_header_line_removed(self):
        self.assertEqual(norm("Bài hát: Tìm Em - Hngle\nCâu một"), "Câu một")


class PunctuationTests(unittest.TestCase):
    def test_spacing_and_merging(self):
        self.assertEqual(norm("em ơi ,anh đây..,  về đi !!"), "em ơi, anh đây. về đi!")
        self.assertEqual(norm("chờ em ... mãi ,, mãi"), "chờ em… mãi, mãi")
        self.assertEqual(norm("thật sao ?!"), "thật sao?!")

    def test_ellipsis_kept(self):
        self.assertEqual(norm("anh nhớ em…  rất nhiều"), "anh nhớ em… rất nhiều")

    def test_no_new_punctuation(self):
        self.assertEqual(norm("anh đi về nhà"), "anh đi về nhà")


class LineAndParagraphTests(unittest.TestCase):
    def test_long_line_split_at_middle_comma(self):
        raw = "dù cho mưa rơi ướt áo vai gầy, và đêm nay lạnh lẽo quá em ơi"
        self.assertEqual(norm(raw), "dù cho mưa rơi ướt áo vai gầy\nvà đêm nay lạnh lẽo quá em ơi")

    def test_short_or_commaless_lines_not_split(self):
        short = "anh đi, em về"
        self.assertEqual(norm(short), short)
        long_no_comma = "dù cho mưa rơi ướt áo vai gầy và đêm nay lạnh lẽo quá em ơi"
        self.assertEqual(norm(long_no_comma), long_no_comma)

    def test_comma_near_edge_not_used(self):
        raw = "ừ, dù cho mưa rơi ướt áo vai gầy và đêm nay lạnh lẽo quá em ơi"
        self.assertEqual(norm(raw), raw)

    def test_exactly_one_blank_line_between_paragraphs(self):
        raw = "\n\n  Câu một  \n\n\n\nCâu   hai\n \n\t\nCâu ba\n\n"
        self.assertEqual(norm(raw), "Câu một\n\nCâu hai\n\nCâu ba")

    def test_repeats_kept(self):
        raw = "Đừng buồn\nĐừng buồn\n\nĐK\nĐừng buồn"
        self.assertEqual(norm(raw), "Đừng buồn\nĐừng buồn\n\nĐừng buồn")

    def test_old_underscore_output_normalises_the_same(self):
        plain = "Verse 1\nAnh đi tìm em, giữa phố\n\nChorus\nĐừng buồn"
        old_step6 = plain.replace(" ", "_")
        self.assertEqual(norm(old_step6), norm(plain))


if __name__ == "__main__":
    unittest.main()
