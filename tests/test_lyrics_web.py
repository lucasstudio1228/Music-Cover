"""Tìm lời trên Google khi nhaccuatui chưa có lời (backend/cover/lyrics_web.py)."""
import base64
import unittest
from unittest import mock

from backend.cover import lyrics_web as lw

STANZA = [
    "Ai tìm ai trên phố vắng ngược lối cơn mưa chiều giăng giăng",
    "Ai tìm ai dưới trăng nghiêng bóng ngõ dài vằng vặc",
    "Ai đặt tên cho ký ức là nỗi đau của ngày hôm qua",
    "Ai đặt tên chúng ta là người lạ",
    "Có phải đêm qua thức trắng để gấp con tim làm hai ngăn",
    "Ngăn phải ôm nỗi đau còn ngăn trái chứa hạt nhiệm màu",
    "Kịp sáng mang đến làm quà cô dâu sợ mai kia sương phai",
    "Anh đợi em anh chọn ngăn nỗi đau",
    "Vì mai người ta đã đi lấy chồng",
]
LYRICS = "\n".join(STANZA)
TITLE, ARTIST = "Ngày Mai Người Ta Lấy Chồng", "Thành Đạt"


class CleanLinesTest(unittest.TestCase):
    def test_keeps_bracket_sections_but_removes_other_labels_chords_and_meta(self):
        raw = "\n".join([
            "Lời bài hát Ngày Mai Người Ta Lấy Chồng - Thành Đạt",
            "Sáng tác: Đông Thiên Đức",
            "[Verse 1]",
            "Ai tìm [Am]ai trên phố [C]vắng",
            "*ĐK:",
            "ĐK: Anh đợi em anh chọn ngăn nỗi đau (x2)",
            "Verse 2:",
            "[Chorus: Thành Đạt]",
            "Điệp khúc",
            "Rap:",
            "Chorus (Mỹ Tâm):",
            "(Điệp khúc x2)",
            "Hỡi diêu bông x2",
            "2. Có phải đêm qua thức trắng",
            "Vì mai người ta đã đi lấy chồng. ==> (Dạo Nhạc) Trở lại 2.",
            "",
            "Nguồn tin: LyricFind",
            "Nhạc sĩ: Đông Thiên Đức / Hữu Đức Đặng",
            "Lời bài hát Ngày Mai Người Ta Lấy Chồng © Bhmedia",
            "12 Contributors",
            "Xem thêm",
        ])
        self.assertEqual(lw.clean_lines(raw, TITLE, ARTIST).split("\n"), [
            "[Verse 1]",
            "Ai tìm ai trên phố vắng",
            "Anh đợi em anh chọn ngăn nỗi đau",
            "[Chorus: Thành Đạt]",
            "Hỡi diêu bông",
            "Có phải đêm qua thức trắng",
            "Vì mai người ta đã đi lấy chồng.",
        ])

    def test_keeps_real_lyrics_that_look_like_labels(self):
        raw = "Nam ơi em đi\nChia sẻ cùng anh\nAnh đã khóc 3 lần\nKết thúc rồi em ơi"
        self.assertEqual(lw.clean_lines(raw), raw)

    def test_keeps_one_blank_line_between_stanzas(self):
        raw = "\n\n[Intro]\nCâu một ở đây\n\n\n[Chorus]\n\nCâu hai ở đây\n\n"
        self.assertEqual(
            lw.clean_lines(raw),
            "[Intro]\nCâu một ở đây\n\n[Chorus]\n\nCâu hai ở đây",
        )


class CoreBlockTest(unittest.TestCase):
    def test_cuts_page_header_and_footer(self):
        page = "\n".join([
            "Lời bài hát Ngày mai người ta lấy chồng (Thành Đạt)| Lyrics",
            "MV Ngày mai người ta lấy chồng | Official Music Video",
            "Mua Pro 99.000đ",
            *STANZA,
            "",
            "Karaoke Ngày mai người ta lấy chồng",
            "Những bài hát khác của Thành Đạt",
            "Cạn tình như thế",
        ])
        self.assertEqual(lw.core_block(page), LYRICS)

    def test_empty(self):
        self.assertEqual(lw.core_block(""), "")


class LinksTest(unittest.TestCase):
    def test_rank_links_skips_useless_and_prefers_lyrics_sites(self):
        links = [
            "https://lyrics.lyricfind.com/",
            "https://zingmp3.vn/bai-hat/x.html",
            "https://www.youtube.com/watch?v=1",
            "https://www.nhaccuatui.com/song/abc",
            "https://example.com/blog/bai-viet",
            "https://hopamviet.vn/chord/song/x.html",
            "https://hopamviet.vn/chord/song/x.html#top",
        ]
        self.assertEqual(lw.rank_links(links), [
            "https://hopamviet.vn/chord/song/x.html", "https://example.com/blog/bai-viet"])

    def test_unwrap_bing_redirect(self):
        real = "https://loibaihat.co/bai-hat/abc"
        enc = base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
        self.assertEqual(lw.unwrap_link(f"https://www.bing.com/ck/a?!&&p=1&u=a1{enc}&ntb=1"), real)
        self.assertEqual(lw.unwrap_link(real), real)


class FindLyricsTest(unittest.TestCase):
    def _run(self, google=("", [], False), bing=(), blocks=None, ai=None, ai_on=False,
             page_title="", existing="", lrclib=None, zing=None):
        page = mock.MagicMock()
        page.title.return_value = page_title
        blocks = blocks or {}
        with mock.patch.object(lw, "google_search", return_value=google), \
             mock.patch.object(lw, "bing_search", return_value=list(bing)) as bing_m, \
             mock.patch.object(lw, "read_block", side_effect=lambda pg, url: blocks.get(url, "")), \
             mock.patch.object(lw, "ai_available", return_value=ai_on), \
             mock.patch.object(lw, "ai_extract", side_effect=ai or (lambda *a: None)), \
             mock.patch.object(lw, "lrclib_candidate", return_value=lrclib):
            with mock.patch.object(lw, "zing_candidate", return_value=zing):
                got = lw.find_lyrics(page, TITLE, ARTIST, log=lambda m: None,
                                     existing_lyrics=existing)
        return got, bing_m

    def test_zing_provider_used_when_only_reliable_source(self):
        zing = lw.LyricsCandidate(LYRICS, "Zing MP3 (menu Lời bài hát)", 50)
        got, _ = self._run(zing=zing)
        self.assertEqual(got["lyrics"], LYRICS)
        self.assertEqual(got["confidence"], "provider")
        self.assertIn("Zing MP3", got["source"])

    def test_zing_and_lrclib_are_verified_before_google(self):
        zing = lw.LyricsCandidate(LYRICS, "Zing MP3 (menu Lời bài hát)", 50)
        lrclib = lw.LyricsCandidate(LYRICS, "LRCLIB #1", 30)
        got, _ = self._run(zing=zing, lrclib=lrclib)
        self.assertEqual(got["confidence"], "verified")
        self.assertIn("Zing MP3", got["source"])
    def test_google_panel_used_first(self):
        got, bing = self._run(google=(LYRICS + "\nNguồn tin: LyricFind", ["https://a.vn/x"], False))
        self.assertEqual(got["lyrics"], LYRICS)
        self.assertEqual(got["confidence"], "provider")
        self.assertIn("Google lyrics panel", got["source"])
        bing.assert_not_called()

    def test_pages_without_ai_need_title_on_page(self):
        other = "\n".join(f"Câu hát bài khác số {i} ở đây" for i in range(10))
        got, _ = self._run(google=("", ["https://a.vn/1", "https://b.vn/2", "https://c.vn/3"], False),
                           blocks={"https://a.vn/1": other,
                                   "https://b.vn/2": f"{TITLE}\n{LYRICS}",
                                   "https://c.vn/3": f"{TITLE}\n{LYRICS}"})
        self.assertEqual(got["lyrics"], LYRICS)
        self.assertEqual(got["confidence"], "verified")
        self.assertIn("https://b.vn/2", got["source"])
        self.assertIn("https://c.vn/3", got["source"])

    def test_ai_rejects_wrong_song_then_accepts(self):
        answers = iter(["", "[Verse]\n" + LYRICS])
        got, _ = self._run(google=("", ["https://a.vn/1", "https://b.vn/2"], False),
                           blocks={"https://a.vn/1": LYRICS, "https://b.vn/2": LYRICS},
                           ai_on=True, ai=lambda *a: next(answers), existing=LYRICS)
        self.assertEqual(got["lyrics"], LYRICS)
        self.assertEqual(got["confidence"], "verified")

    def test_captcha_falls_back_to_bing(self):
        got, bing = self._run(
            google=("", [], True), bing=["https://c.vn/3"],
            blocks={"https://c.vn/3": LYRICS}, page_title=f"Lời {TITLE}",
            lrclib=lw.LyricsCandidate(LYRICS, "LRCLIB #1", 30))
        bing.assert_called_once()
        self.assertEqual(got["confidence"], "verified")
        self.assertIn("https://c.vn/3", got["source"])

    def test_nothing_found(self):
        got, _ = self._run(google=("", ["https://a.vn/1"], False), blocks={"https://a.vn/1": "ngắn"})
        self.assertEqual(got, {})

    def test_one_unverified_page_is_not_auto_accepted(self):
        got, _ = self._run(
            google=("", ["https://a.vn/1"], False),
            blocks={"https://a.vn/1": f"{TITLE}\n{LYRICS}"})
        self.assertEqual(got["confidence"], "needs_review")
        self.assertNotIn("lyrics", got)


class ZingSelectionTest(unittest.TestCase):
    def test_chooses_exact_official_and_rejects_remix(self):
        rows = [
            {"index": 0, "title": "Tìm Em (Remix)", "artist": "Hngle, Bảo Anh"},
            {"index": 1, "title": "Tìm Em", "artist": "Hngle, Bảo Anh"},
        ]
        self.assertIs(lw.pick_zing_result("Tìm Em", "Hngle, Bảo Anh", rows), rows[1])

    def test_zing_ui_more_then_lyrics(self):
        page = mock.MagicMock()
        page.evaluate.side_effect = [[
            {"index": 0, "title": "Tìm Em (Remix)", "artist": "Hngle, Bảo Anh"},
            {"index": 1, "title": "Tìm Em", "artist": "Hngle, Bảo Anh"},
        ], LYRICS]
        menu_item = mock.MagicMock()
        with mock.patch.object(lw, "wait_ms"), \
             mock.patch.object(lw, "dismiss_zing_popups"), \
             mock.patch.object(lw, "query_first", return_value=menu_item):
            got = lw.zing_candidate(page, "Tìm Em", "Hngle, Bảo Anh", log=lambda m: None)
        self.assertIsNotNone(got)
        self.assertEqual(got.lyrics, LYRICS)
        self.assertIn("Zing MP3", got.source)
        page.locator.assert_any_call('[data-tool-zing-more="1"]')
        menu_item.click.assert_called_once_with(force=True)


class ConsensusTest(unittest.TestCase):
    def test_two_matching_sources_are_verified(self):
        picked, sources = lw.choose_consensus([
            lw.LyricsCandidate(LYRICS, "NCT", 20),
            lw.LyricsCandidate("[Verse]\n" + LYRICS, "LRCLIB", 30),
        ])
        self.assertIsNotNone(picked)
        self.assertEqual(set(sources), {"NCT", "LRCLIB"})

    def test_disagreeing_sources_are_rejected(self):
        wrong = "\n".join(f"Lời sai hoàn toàn dòng số {i}" for i in range(10))
        picked, _ = lw.choose_consensus([
            lw.LyricsCandidate(LYRICS, "A"), lw.LyricsCandidate(wrong, "B")])
        self.assertIsNone(picked)

    def test_no_title_no_search(self):
        page = mock.MagicMock()
        with mock.patch.object(lw, "google_search") as g:
            self.assertEqual(lw.find_lyrics(page, "  ", ARTIST, log=lambda m: None), {})
        g.assert_not_called()


class AiExtractTest(unittest.TestCase):
    def _client(self, text):
        client = mock.MagicMock()
        client.chat.completions.create.return_value.choices = [
            mock.MagicMock(message=mock.MagicMock(content=text))]
        return client

    def test_strips_code_fence(self):
        with mock.patch.object(lw, "_ai_client", return_value=(self._client("```\nA b c\n```"), "m")):
            self.assertEqual(lw.ai_extract("x", TITLE, ARTIST), "A b c")

    def test_not_lyrics(self):
        with mock.patch.object(lw, "_ai_client", return_value=(self._client("KHONG_CO_LOI"), "m")):
            self.assertEqual(lw.ai_extract("x", TITLE, ARTIST), "")

    def test_no_api_key(self):
        with mock.patch.object(lw, "_ai_client", return_value=(None, "")):
            self.assertIsNone(lw.ai_extract("x", TITLE, ARTIST))


if __name__ == "__main__":
    unittest.main()
