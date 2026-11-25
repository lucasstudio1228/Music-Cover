"""Bước 6: chuẩn hoá lời cho ô Lyrics của Suno theo quy tắc người dùng chốt."""
import unittest
import unicodedata

from backend.cover.suno_lyrics import normalize_for_suno as norm


class LabelTests(unittest.TestCase):
    def test_label_only_lines_removed_and_become_paragraph_breaks(self):
        raw = "Intro\nCâu một\nVerse 1:\nCâu hai\n[Chorus]\nCâu ba\nĐK:\nCâu bốn\n(Pre-Chorus)\nCâu năm"
        self.assertEqual(norm(raw), "Câu_một\n\nCâu_hai\n\nCâu_ba\n\nCâu_bốn\n\nCâu_năm")

    def test_vietnamese_labels(self):
        for label in ("Điệp khúc", "ĐK", "Đk:", "đk 2", "Phiên khúc", "PK", "Lời 1", "Lời 2:",
                      "Nhạc dạo", "Kết", "Rap", "Bridge", "Outro", "Interlude", "Instrumental",
                      "Hook", "Post-Chorus", "[Verse 2: Mỹ Tâm]", "*Chorus*", "ĐK (x2)", "(x2)"):
            self.assertEqual(norm(f"A b\n{label}\nC d"), "A_b\n\nC_d", label)

    def test_label_prefix_keeps_lyric(self):
        self.assertEqual(norm("Câu đầu\nĐK: Đừng buồn em ơi"), "Câu_đầu\n\nĐừng_buồn_em_ơi")
        self.assertEqual(norm("[Chorus] Baby đừng đi"), "Baby_đừng_đi")

    def test_lyric_starting_with_label_like_word_kept(self):
        self.assertEqual(norm("Kết thúc rồi em ơi\nRap đời anh"), "Kết_thúc_rồi_em_ơi\nRap_đời_anh")
        self.assertEqual(norm("(Oh oh oh)"), "(Oh_oh_oh)")


class CharacterTests(unittest.TestCase):
    def test_art_fonts_become_lowercase_letters(self):
        self.assertEqual(norm("𝐀𝐧𝐡 𝓨𝓮̂𝓾 Ｅｍ ⓐ 🅑 ᴄ"), "anh_yêu_em_a_b_c")

    def test_underscore_and_underscore_comma(self):
        self.assertEqual(norm("Anh_đi_tìm_em_,_giữa_phố"), "Anh_đi_tìm_em,_giữa_phố")
        self.assertEqual(norm("Anh_đi_,về"), "Anh_đi,_về")

    def test_invisible_nbsp_emoji_markdown_removed(self):
        raw = "\ufeff# Anh\u200b\u00a0đi 🎵❤️\n> - **về** nhà ♪"
        self.assertEqual(norm(raw), "Anh_đi\nvề_nhà")

    def test_vietnamese_nfc_and_case_kept(self):
        decomposed = unicodedata.normalize("NFD", "Người Ơi, Tình Yêu")
        out = norm(decomposed)
        self.assertEqual(out, "Người_Ơi,_Tình_Yêu")
        self.assertTrue(unicodedata.is_normalized("NFC", out))

    def test_header_line_removed(self):
        self.assertEqual(norm("Bài hát: Tìm Em - Hngle\nCâu một"), "Câu_một")


class PunctuationTests(unittest.TestCase):
    def test_spacing_and_merging(self):
        self.assertEqual(norm("em ơi ,anh đây..,  về đi !!"), "em_ơi,_anh_đây._về_đi!")
        self.assertEqual(norm("chờ em ... mãi ,, mãi"), "chờ_em…_mãi,_mãi")
        self.assertEqual(norm("thật sao ?!"), "thật_sao?!")

    def test_ellipsis_kept(self):
        self.assertEqual(norm("anh nhớ em…  rất nhiều"), "anh_nhớ_em…_rất_nhiều")

    def test_no_new_punctuation(self):
        self.assertEqual(norm("anh đi về nhà"), "anh_đi_về_nhà")


class LineAndParagraphTests(unittest.TestCase):
    def test_long_line_split_at_middle_comma(self):
        raw = "dù cho mưa rơi ướt áo vai gầy, và đêm nay lạnh lẽo quá em ơi"
        self.assertEqual(norm(raw), "dù_cho_mưa_rơi_ướt_áo_vai_gầy\nvà_đêm_nay_lạnh_lẽo_quá_em_ơi")

    def test_short_or_commaless_lines_not_split(self):
        short = "anh đi, em về"
        self.assertEqual(norm(short), "anh_đi,_em_về")
        long_no_comma = "dù cho mưa rơi ướt áo vai gầy và đêm nay lạnh lẽo quá em ơi"
        self.assertEqual(norm(long_no_comma), long_no_comma.replace(" ", "_"))

    def test_comma_near_edge_not_used(self):
        raw = "ừ, dù cho mưa rơi ướt áo vai gầy và đêm nay lạnh lẽo quá em ơi"
        self.assertEqual(norm(raw), raw.replace(" ", "_"))

    def test_exactly_one_blank_line_between_paragraphs(self):
        raw = "\n\n  Câu một  \n\n\n\nCâu   hai\n \n\t\nCâu ba\n\n"
        self.assertEqual(norm(raw), "Câu_một\n\nCâu_hai\n\nCâu_ba")

    def test_repeats_kept(self):
        raw = "Đừng buồn\nĐừng buồn\n\nĐK\nĐừng buồn"
        self.assertEqual(norm(raw), "Đừng_buồn\nĐừng_buồn\n\nĐừng_buồn")

    def test_idempotent_with_underscores(self):
        plain = "Verse 1\nAnh đi tìm em, giữa phố\n\nChorus\nĐừng buồn"
        once = norm(plain)
        self.assertEqual(once, "Anh_đi_tìm_em,_giữa_phố\n\nĐừng_buồn")
        self.assertEqual(norm(once), once)


if __name__ == "__main__":
    unittest.main()
