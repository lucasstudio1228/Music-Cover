"""So khớp «Tên bài - Ca sĩ» (dòng docx) với kết quả của mọi nguồn nhạc."""
import unittest
from unittest import mock

from backend.cover import audio_sources, nct, song_match as sm


class EvaluateTests(unittest.TestCase):
    Q = "Sao Mình Chưa Nắm Tay Nhau - Yan Nguyễn"

    def tier(self, title, artist="", extra="", query=None):
        return sm.evaluate(query or self.Q, title, artist, extra).tier

    def test_exact_title_and_artist(self):
        self.assertEqual(self.tier("Sao Mình Chưa Nắm Tay Nhau", "Yan Nguyễn"), sm.EXACT)

    def test_other_singer_is_title_only(self):
        self.assertEqual(self.tier("Sao Mình Chưa Nắm Tay Nhau", "Ca Sĩ Khác"), sm.TITLE_ONLY)

    def test_youtube_style_title_with_singer_and_decoration(self):
        self.assertEqual(self.tier("Yan Nguyễn - Sao Mình Chưa Nắm Tay Nhau | Official MV",
                                   "Kênh Bất Kỳ"), sm.EXACT)

    def test_same_singer_remix_is_exact_variant(self):
        self.assertEqual(self.tier("Sao Mình Chưa Nắm Tay Nhau (Đại Mèo Remix)", "Yan Nguyễn"),
                         sm.EXACT_VARIANT)

    def test_different_song_with_similar_words_rejected(self):
        for title in ("Sao Ta Chưa Nắm Tay Nhau", "Sao Mình Chưa Nắm Tay",
                      "Sao Mình Chưa Nắm Tay (Tachi Drill)"):
            self.assertEqual(self.tier(title, "Yan Nguyễn"), sm.NONE, title)

    def test_karaoke_and_beat_never_chosen(self):
        for title in ("Sao Mình Chưa Nắm Tay Nhau Karaoke", "Sao Mình Chưa Nắm Tay Nhau (Beat)"):
            self.assertEqual(self.tier(title, "Yan Nguyễn"), sm.NONE, title)

    def test_multiple_artists_any_order(self):
        self.assertEqual(sm.evaluate("Tìm Em - Hngle Bảo Anh", "Tìm Em", "Bảo Anh, Hngle").tier,
                         sm.EXACT)
        self.assertEqual(sm.evaluate("Tìm Em - Hngle x Bảo Anh", "Tìm Em", "Hngle").tier,
                         sm.EXACT)

    def test_title_with_singers_written_in_youtube_style(self):
        q = "Tìm Em - Hngle Bảo Anh"
        self.assertEqual(sm.evaluate(q, "Hngle x Bảo Anh - Tìm Em | Official MV", "Kênh X").tier,
                         sm.EXACT)
        self.assertEqual(sm.evaluate(q, "Tìm Em (feat. Bảo Anh)", "Hngle").tier, sm.EXACT)

    def test_partial_singer_word_does_not_make_another_song_match(self):
        q = "Tìm Em - Hngle Bảo Anh"
        self.assertEqual(sm.evaluate(q, "anh tìm em", "hoo, thanhluan").tier, sm.NONE)
        # đọc ngược «Ca sĩ - Tên» chỉ được nhận khi đúng ca sĩ
        self.assertEqual(sm.evaluate(q, "Hngle Bảo Anh", "Soulvex Aura").tier, sm.NONE)
        self.assertEqual(sm.evaluate("Hngle - Tìm Em", "Tìm Em", "Hngle, Bảo Anh").tier,
                         sm.EXACT)

    def test_line_without_dash(self):
        self.assertEqual(sm.evaluate("Sao Mình Chưa Nắm Tay Nhau Yan Nguyễn",
                                     "Sao Mình Chưa Nắm Tay Nhau", "Yan Nguyễn").tier, sm.EXACT)

    def test_rank_prefers_exact_then_same_singer_variant(self):
        rows = [
            {"title": "Sao Mình Chưa Nắm Tay Nhau", "artist": "Ca Sĩ Khác", "url": "other"},
            {"title": "Sao Mình Chưa Nắm Tay Nhau (Remix)", "artist": "Yan Nguyễn", "url": "remix"},
            {"title": "Sao Mình Chưa Nắm Tay Nhau Karaoke", "artist": "Yan Nguyễn", "url": "kara"},
            {"title": "Sao Mình Chưa Nắm Tay Nhau", "artist": "Yan Nguyễn", "url": "official"},
        ]
        self.assertEqual([r["url"] for r, _ in sm.rank(self.Q, rows)],
                         ["official", "remix", "other"])


class FallbackSourceTests(unittest.TestCase):
    Q = "Bài A - Ca sĩ A"

    def test_collects_all_providers_even_after_exact_match(self):
        zing = [{"title": "Bài A", "artist": "Ca sĩ B", "url": "z", "provider": "zingmp3"}]
        ytm = [{"title": "Bài A", "artist": "Ca sĩ A", "url": "m", "provider": "ytmusic"}]
        with mock.patch.object(audio_sources, "zing_rows", return_value=zing), \
             mock.patch.object(audio_sources, "ytmusic_rows", return_value=ytm), \
             mock.patch.object(audio_sources, "youtube_rows") as yt:
            pool = audio_sources.find_best(None, self.Q, log=lambda _: None)
        yt.assert_called_once()
        self.assertEqual([r["url"] for r, _ in pool], ["m", "z"])

    def test_download_reaches_later_provider_after_many_broken_links(self):
        broken = [({"title": "Bài A", "artist": "Ca sĩ A", "url": f"z{i}",
                    "provider": "zingmp3"}, sm.evaluate(self.Q, "Bài A", "Ca sĩ A"))
                  for i in range(8)]
        good = ({"title": "Bài A", "artist": "Ca sĩ A", "url": "youtube-ok",
                 "provider": "youtube"}, sm.evaluate(self.Q, "Bài A", "Ca sĩ A"))
        def download(url, _dest, _stem):
            if url != "youtube-ok":
                raise RuntimeError("expired")
            return "ok.mp3"
        with mock.patch.object(audio_sources, "_download_with_ytdlp", side_effect=download):
            path, quality, _ = audio_sources.download_fallback(
                None, None, "stem", self.Q, log=lambda _: None,
                candidates=[*broken, good])
        self.assertEqual((path, quality), ("ok.mp3", "youtube_mp3"))

    def test_download_uses_best_match_and_tags_quality(self):
        rows = [{"title": "Bài A", "artist": "Ca sĩ A", "url": "m", "provider": "ytmusic"}]
        with mock.patch.object(audio_sources, "zing_rows", return_value=[]), \
             mock.patch.object(audio_sources, "ytmusic_rows", return_value=rows), \
             mock.patch.object(audio_sources, "_download_with_ytdlp",
                               return_value="a.mp3") as dl:
            path, quality, row = audio_sources.download_fallback(
                None, None, "stem", self.Q, log=lambda _: None)
        dl.assert_called_once_with("m", None, "stem")
        self.assertEqual((path, quality, row["match_note"]), ("a.mp3", "ytmusic_mp3", ""))

    def test_other_singer_only_downloads_with_warning(self):
        rows = [{"title": "Bài A", "artist": "Ca sĩ B", "url": "y", "provider": "youtube"}]
        with mock.patch.object(audio_sources, "zing_rows", return_value=[]), \
             mock.patch.object(audio_sources, "ytmusic_rows", return_value=[]), \
             mock.patch.object(audio_sources, "youtube_rows", return_value=rows), \
             mock.patch.object(audio_sources, "_download_with_ytdlp", return_value="a.mp3"):
            _, quality, row = audio_sources.download_fallback(
                None, None, "stem", self.Q, log=lambda _: None)
        self.assertEqual(quality, "youtube_mp3")
        self.assertTrue(row["match_note"].startswith("⚠"))
        self.assertIn("KHÁC ca sĩ", row["match_note"])

    def test_no_matching_song_raises(self):
        rows = [{"title": "Bài Khác", "artist": "Ca sĩ A", "url": "y", "provider": "youtube"}]
        with mock.patch.object(audio_sources, "zing_rows", return_value=[]), \
             mock.patch.object(audio_sources, "ytmusic_rows", return_value=[]), \
             mock.patch.object(audio_sources, "youtube_rows", return_value=rows), \
             mock.patch.object(audio_sources, "_download_with_ytdlp") as dl:
            with self.assertRaises(audio_sources.AudioSourceError):
                audio_sources.download_fallback(None, None, "stem", self.Q, log=lambda _: None)
        dl.assert_not_called()


class NctStrictTests(unittest.TestCase):
    def test_strict_opens_exact_singer_not_first_result(self):
        rows = [{"index": 0, "title": "Bài A", "artist": "Ca sĩ B"},
                {"index": 1, "title": "Bài A", "artist": "Ca sĩ A"}]
        with mock.patch.object(nct, "search", return_value=rows), \
             mock.patch.object(nct, "open_result") as open_result, \
             mock.patch.object(nct, "read_song",
                               return_value={"title": "Bài A", "artist": "Ca sĩ A",
                                             "lyrics": "L", "url": "u"}):
            info = nct.find_and_open(None, "Bài A - Ca sĩ A", log=lambda _: None, strict=True)
        open_result.assert_called_once_with(None, 1)
        self.assertEqual(info["match_tier"], sm.EXACT)

    def test_strict_without_exact_raises_with_best_candidate(self):
        rows = [{"index": 0, "title": "Bài A (Remix)", "artist": "Ca sĩ A"}]
        with mock.patch.object(nct, "search", return_value=rows), \
             mock.patch.object(nct, "open_result") as open_result:
            with self.assertRaises(nct.NctNoExactMatch) as ctx:
                nct.find_and_open(None, "Bài A - Ca sĩ A", log=lambda _: None, strict=True)
        open_result.assert_not_called()
        self.assertIs(ctx.exception.row, rows[0])
        self.assertEqual(ctx.exception.match.tier, sm.EXACT_VARIANT)


class NctOrBetterTests(unittest.TestCase):
    def miss(self, tier):
        row = {"index": 0, "title": "Bài A (Remix)", "artist": "Ca sĩ A"}
        return nct.NctNoExactMatch("không có", row=row, match=sm.Match(tier, 1.0),
                                   search_query="Bài A - Ca sĩ A")

    def test_exact_elsewhere_beats_nct_variant(self):
        from backend.cover import nct_jobs
        better = [({"title": "Bài A", "url": "m"}, sm.Match(sm.EXACT, 1.0))]
        with mock.patch.object(audio_sources, "find_best", return_value=better), \
             mock.patch.object(nct, "open_candidate") as reopen:
            info, pool = nct_jobs._nct_or_better(None, "Bài A - Ca sĩ A",
                                                 self.miss(sm.EXACT_VARIANT), lambda _: None)
        reopen.assert_not_called()
        self.assertIsNone(info)
        self.assertIs(pool, better)

    def test_nct_wins_tie_and_carries_warning(self):
        from backend.cover import nct_jobs
        same = [({"title": "Bài A Remix", "url": "m"}, sm.Match(sm.EXACT_VARIANT, 1.0))]
        with mock.patch.object(audio_sources, "find_best", return_value=same), \
             mock.patch.object(nct, "open_candidate",
                               return_value={"title": "Bài A (Remix)", "lyrics": "L"}):
            info, pool = nct_jobs._nct_or_better(None, "Bài A - Ca sĩ A",
                                                 self.miss(sm.EXACT_VARIANT), lambda _: None)
        self.assertIsNone(pool)
        self.assertTrue(info["match_note"].startswith("⚠"))


class ZingMoreButtonTests(unittest.TestCase):
    def test_album_header_more_button_is_never_used(self):
        """Trang album Zing: «…» cột trái là của album (không có «Lời bài hát»);
        phải dùng «…» ở cột phải của dòng bài hát."""
        from backend.cover import lyrics_web
        js = lyrics_web._JS_ZING_RESULTS
        self.assertIn(".playlist-header", js)
        self.assertIn(".media-right .ic-more", js)
        import inspect
        src = inspect.getsource(lyrics_web.zing_candidate)
        self.assertNotIn('"button:has(.ic-more)"', src)
        self.assertIn(".media-item .media-right button:has(.ic-more)", src)


class ZingLyricsPickTests(unittest.TestCase):
    def test_lyrics_of_same_title_other_singer_not_used(self):
        from backend.cover import lyrics_web
        rows = [{"index": 0, "title": "Tìm Em", "artist": "Ca Sĩ Khác"}]
        self.assertIsNone(lyrics_web.pick_zing_result("Tìm Em", "Hngle, Bảo Anh", rows))


if __name__ == "__main__":
    unittest.main()
