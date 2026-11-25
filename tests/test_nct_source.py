"""Tab ① Tải nhạc gốc: chọn đúng kết quả nhaccuatui, tách lời, chọn chất lượng,
và API danh sách bài gốc (thêm / sửa / xoá / nhập file cover / Tạo lời bài hát).
Không mở trình duyệt thật — hàng đợi tải được thay bằng mock; chỉ dùng DB/thư mục tạm."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import nct
from backend.routers.sources import parse_lines


class NctPureTests(unittest.TestCase):
    def test_fold_strips_accents_and_d(self):
        self.assertEqual(nct.fold("Đừng Làm Trái Tim Anh Đau!"), "dung lam trai tim anh dau")

    def test_split_query_keeps_hyphen_inside_names(self):
        self.assertEqual(nct.split_query("Em Của Ngày Hôm Qua - Sơn Tùng M-TP"),
                         ["Em Của Ngày Hôm Qua", "Sơn Tùng M-TP"])
        self.assertEqual(nct.split_query("Mỹ Tâm – Đúng Cũng Thành Sai"),
                         ["Mỹ Tâm", "Đúng Cũng Thành Sai"])

    def test_is_song_url(self):
        self.assertTrue(nct.is_song_url("https://www.nhaccuatui.com/song/AbC123xyz"))
        self.assertTrue(nct.is_song_url("https://nhaccuatui.com/bai-hat/em-cua-ngay-hom-qua.x"))
        self.assertFalse(nct.is_song_url("https://www.nhaccuatui.com/search?key=abc"))
        self.assertFalse(nct.is_song_url("Em của ngày hôm qua"))

    def test_pick_best_prefers_original_over_remix(self):
        results = [
            {"title": "Em Của Ngày Hôm Qua (Remix)", "artist": "Sơn Tùng M-TP"},
            {"title": "Em Của Ngày Hôm Qua", "artist": "Sơn Tùng M-TP"},
            {"title": "Em Của Ngày Hôm Qua", "artist": "V.A"},
        ]
        best = nct.pick_best("Em của ngày hôm qua - Sơn Tùng M-TP", results)
        self.assertIs(best, results[1])

    def test_pick_best_still_uses_official_when_query_says_remix(self):
        results = [
            {"title": "Em Của Ngày Hôm Qua", "artist": "Sơn Tùng M-TP"},
            {"title": "Em Của Ngày Hôm Qua (Remix)", "artist": "Sơn Tùng M-TP"},
        ]
        self.assertIs(nct.pick_best("Em của ngày hôm qua remix", results), results[0])

    def test_pick_best_refuses_variant_only_results(self):
        results = [
            {"title": "Tìm Em (Remix)", "artist": "Hngle, Bảo Anh"},
            {"title": "Tìm Em (Cover)", "artist": "Ca sĩ khác"},
        ]
        self.assertIsNone(nct.pick_best("Tìm Em - Hngle Bảo Anh", results))

    def test_variant_only_results_use_best_fallback(self):
        hits = [
            {"index": 0, "title": "Mở Lòng Vì Ai (Remix)", "artist": "Inso"},
            {"index": 1, "title": "Mở Lòng Vì Ai (Cover)", "artist": "Ca sĩ khác"},
        ]
        with mock.patch.object(nct, "search", return_value=hits), \
             mock.patch.object(nct, "open_result"), \
             mock.patch.object(nct, "read_song", return_value={
                 "title": "Mở Lòng Vì Ai (Remix)", "artist": "Inso"}):
            got = nct.find_and_open(None, "Mở Lòng Vì Ai - Inso", log=lambda m: None)
        self.assertTrue(got["variant_fallback"])
        self.assertEqual(got["candidate"], hits[0])

    def test_self_cover_is_preferred_over_remixes(self):
        hits = [
            {"index": 0, "title": "Mở Lòng Vì Ai (Thazh x Đông Remix)", "artist": "Inso"},
            {"index": 1, "title": "Mở Lòng Vì Ai (LD Remix)", "artist": "Inso"},
            {"index": 2, "title": "Mở Lòng Vì Ai (Inso Cover)", "artist": "Inso"},
            {"index": 3, "title": "Mở Lòng Vì Ai (WEO Remix)", "artist": "Inso, WEO"},
        ]
        best = nct.pick_best(
            "Mở Lòng Vì Ai - Inso", hits, allow_variants=True)
        self.assertIs(best, hits[2])

    def test_original_artist_remix_beats_other_artist_cover(self):
        hits = [
            {"title": "Mở Lòng Vì Ai (Remix)", "artist": "Inso"},
            {"title": "Mở Lòng Vì Ai (Cover)", "artist": "Ca sĩ khác"},
        ]
        best = nct.pick_best(
            "Mở Lòng Vì Ai - Inso", hits, allow_variants=True)
        self.assertIs(best, hits[0])

    def test_download_menu_selector_accepts_current_plain_download_items(self):
        self.assertIn(".download-item", nct.SEL_MENU_ITEM)

    def test_official_query_removes_variant_parenthesis(self):
        self.assertEqual(
            nct.official_query("Mở Lòng Vì Ai (Thazh x Đông Remix) - Inso"),
            "Mở Lòng Vì Ai - Inso")

    def test_direct_variant_link_is_allowed_as_explicit_fallback(self):
        page = mock.MagicMock()
        with mock.patch.object(nct, "read_song", return_value={
                "title": "Tìm Em (Remix)", "artist": "Hngle"}):
            got = nct.find_and_open(page, "https://www.nhaccuatui.com/song/abc")
        self.assertEqual(got["title"], "Tìm Em (Remix)")

    def test_pick_best_none_when_unrelated(self):
        results = [{"title": "Hãy Trao Cho Anh", "artist": "Sơn Tùng M-TP"}]
        self.assertIsNone(nct.pick_best("Đúng cũng thành sai - Mỹ Tâm", results))
        self.assertIsNone(nct.pick_best("abc", []))

    def test_lyrics_from_html(self):
        raw = ("Đăng bởi: ai đó<br>Câu một<br/>Câu hai&nbsp;<br><br><br><br>"
               "Câu ba &amp; bốn<br>")
        self.assertEqual(nct.lyrics_from_html(raw), "Câu một\nCâu hai\n\nCâu ba & bốn")

    def test_lyrics_from_html_placeholder_is_empty(self):
        self.assertEqual(nct.lyrics_from_html("Hiện chưa có lời bài hát nào cho bài này"), "")
        self.assertEqual(nct.lyrics_from_html(""), "")

    def test_choose_quality_order(self):
        labels = ["Chất lượng thường (128kbps)", "Lossless", "High Quality 320kbps"]
        self.assertEqual(nct.choose_quality(labels),
                         [(2, "high"), (0, "normal"), (1, "lossless")])
        self.assertEqual(nct.choose_quality(["Thêm vào playlist"]), [])

    def test_choose_quality_real_menu_skips_vip(self):
        """Menu thật (2026-10-28): Standard / High / Lossless + huy hiệu VIP."""
        labels = ["Standard quality (~4.3MB)", "High quality (~10.7MB)",
                  "Lossless (~42.1MB) [VIP]"]
        order = nct.choose_quality(labels)
        self.assertEqual(order[:2], [(1, "high"), (0, "normal")])
        self.assertTrue(nct._PAYWALL_RE.search(labels[order[2][0]]))

    def test_is_audio_download_url(self):
        self.assertTrue(nct.is_audio_download_url(
            "https://stream.nct.vn/resa/2606/6b/f5/abc_hq.mp3?st=x&e=1&download=true"))
        self.assertFalse(nct.is_audio_download_url("https://stream.nct.vn/abc_hq.mp3?st=x"))
        self.assertFalse(nct.is_audio_download_url(
            "https://www.nhaccuatui.com/api/x?download=true"))

    def test_search_fallbacks_title_first(self):
        self.assertEqual(nct.search_fallbacks("Tìm Em - Hngle Bảo Anh"),
                         ["Tìm Em", "Hngle Bảo Anh"])
        self.assertEqual(nct.search_fallbacks("Tìm Em"), [])

    def test_find_and_open_retries_with_title_only(self):
        """nhaccuatui ra 0 kết quả cho cả dòng → tìm lại theo tên bài."""
        hits = [{"index": 0, "title": "Tìm Em", "artist": "Hngle, Bảo Anh"}]
        calls = []

        def fake_search(page, q, log=print):
            calls.append(q)
            return hits if q == "Tìm Em" else []

        with mock.patch.object(nct, "search", side_effect=fake_search), \
                mock.patch.object(nct, "open_result") as opened, \
                mock.patch.object(nct, "read_song", return_value={"title": "Tìm Em"}):
            info = nct.find_and_open(None, "Tìm Em - Hngle Bảo Anh", log=lambda m: None)
        self.assertEqual(calls, ["Tìm Em - Hngle Bảo Anh", "Tìm Em"])
        opened.assert_called_once_with(None, 0)
        self.assertIs(info["candidate"], hits[0])

    def test_pick_best_avoids_tropical_variant(self):
        results = [{"title": "Hơn Cả Yêu (Tropical)", "artist": "Đức Phúc"},
                   {"title": "Hơn Cả Yêu", "artist": "Đức Phúc"}]
        self.assertIs(nct.pick_best("Hơn Cả Yêu - Đức Phúc", results), results[1])

    def test_lyrics_coming_soon_is_empty(self):
        self.assertEqual(nct.lyrics_from_html("Lyrics for this song will be available soon..."),
                         "")

    def test_safe_name(self):
        self.assertEqual(nct.safe_name('Bài: "A/B"?'), "Bài_ _A_B__")
        self.assertEqual(nct.safe_name("..."), "bai_hat")

    def test_parse_lines_dedupes_and_strips_numbering(self):
        text = ("1. Em của ngày hôm qua - Sơn Tùng\n\n"
                "- em cua ngay hom qua - son tung\n"
                "2) https://www.nhaccuatui.com/song/AbC\n"
                "https://www.nhaccuatui.com/song/AbC\n")
        self.assertEqual(parse_lines(text), ["Em của ngày hôm qua - Sơn Tùng",
                                             "https://www.nhaccuatui.com/song/AbC"])


class SourcesApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import Project
        from backend.video import config
        tmp = TemporaryDirectory(prefix="nct-source-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            proj = Project(name="Cover Test")
            s.add(proj)
            s.commit()
            self.pid = proj.id

        def _session():
            with Session(self.engine) as s:
                yield s
        app.dependency_overrides[get_session] = _session
        self.addCleanup(app.dependency_overrides.clear)
        self.submit = mock.MagicMock(side_effect=lambda ids: len(ids))
        self.align = mock.MagicMock(side_effect=lambda pid, ids: len(ids))
        self.qc = mock.MagicMock()
        for p in (mock.patch.object(config, "MEDIA_ROOT", self.root / "media"),
                  mock.patch("backend.cover.nct_jobs.submit", self.submit),
                  mock.patch("backend.cover.jobs.submit", self.align),
                  mock.patch("backend.cover.cover_qc.review_async", self.qc),
                  mock.patch("backend.core_bridge.probe_file", self._fake_probe)):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app)

    @staticmethod
    def _fake_probe(path):
        return SimpleNamespace(path=path, duration_seconds=200.0, sample_rate=48000,
                               channels=2, format="WAV", is_lossy=False, subtype="PCM_24")

    def _add(self, text, start=False):
        r = self.client.post(f"/api/sources/projects/{self.pid}",
                             json={"text": text, "start": start})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _items(self):
        return self.client.get(f"/api/sources/projects/{self.pid}").json()["items"]

    def _set(self, sid, **kw):
        from sqlmodel import Session
        from backend.models import SourceSong
        with Session(self.engine) as s:
            src = s.get(SourceSong, sid)
            for k, v in kw.items():
                setattr(src, k, v)
            s.add(src)
            s.commit()

    def test_add_and_list(self):
        body = self._add("Bài A - Ca sĩ A\nhttps://www.nhaccuatui.com/song/XyZ?st=1", start=True)
        self.assertEqual(body["added"], 2)
        self.submit.assert_called_once_with(body["ids"])
        items = self._items()
        self.assertEqual([i["query"] for i in items],
                         ["Bài A - Ca sĩ A", "https://www.nhaccuatui.com/song/XyZ?st=1"])
        self.assertEqual(items[1]["nct_url"], "https://www.nhaccuatui.com/song/XyZ")
        # Không có hàng đợi thật → "queued" hiển thị thành "stopped".
        self.assertEqual({i["status"] for i in items}, {"stopped"})

    def test_add_rejects_empty_and_too_many(self):
        r = self.client.post(f"/api/sources/projects/{self.pid}", json={"text": "\n \n"})
        self.assertEqual(r.status_code, 400)
        many = "\n".join(f"Bài số {i}" for i in range(51))
        r = self.client.post(f"/api/sources/projects/{self.pid}", json={"text": many})
        self.assertEqual(r.status_code, 400)

    def test_edit_lyrics_keeps_file_and_new_query_resets(self):
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        folder = self.root / "media" / "nhac_goc"
        folder.mkdir(parents=True)
        audio = folder / "Bài A.mp3"
        audio.write_bytes(b"x" * 10)
        audio.with_suffix(".txt").write_text("lời", encoding="utf-8")
        self._set(sid, title="Bài A", artist="Ca sĩ A", lyrics_text="cũ",
                  file_path=str(audio), status="done")

        r = self.client.put(f"/api/sources/{sid}", json={"lyrics_text": "Dòng 1\r\nDòng 2"})
        self.assertEqual(r.json()["lyrics_text"], "Dòng 1\nDòng 2")
        self.assertEqual(r.json()["lyric_line_count"], 2)
        self.assertTrue(audio.exists())
        self.submit.assert_not_called()

        r = self.client.put(f"/api/sources/{sid}", json={"query": "Bài A (bản khác)"})
        out = r.json()
        self.assertEqual((out["title"], out["lyrics_text"], out["has_file"]), ("", "", False))
        self.assertFalse(audio.exists())
        self.assertFalse(audio.with_suffix(".txt").exists())
        self.submit.assert_called_once_with([sid])

    def test_edit_lyrics_clears_web_source(self):
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        self._set(sid, lyrics_text="Lời mạng", lyrics_source="https://a.vn/x")
        self.assertEqual(self._items()[0]["lyrics_source"], "https://a.vn/x")
        r = self.client.put(f"/api/sources/{sid}", json={"lyrics_text": "Lời tôi sửa"})
        self.assertEqual(r.json()["lyrics_source"], "")

    def _run_process(self, sid, nct_lyrics, web):
        from backend.cover import lyrics_web, nct, nct_jobs, tempo
        bs, page = mock.MagicMock(), mock.MagicMock()
        info = {"title": "Bài A", "artist": "Ca sĩ A", "url": "https://www.nhaccuatui.com/song/A",
                "lyrics": nct_lyrics}
        audio = self.root / "a.mp3"
        audio.write_bytes(b"x")
        def export_tempo(*args, **kwargs):
            out = self.root / "tempo" / f"source-{sid}-4.5x.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"RIFF-auto-tempo")
            return out
        with mock.patch.object(nct_jobs, "engine", self.engine), \
             mock.patch.object(nct, "find_and_open", return_value=info), \
             mock.patch.object(nct, "login_state", return_value="logged_in"), \
             mock.patch.object(nct, "download", return_value=(audio, "high")), \
             mock.patch.object(tempo, "export_file", side_effect=export_tempo), \
             mock.patch.object(lyrics_web, "find_lyrics", **(
                 {"side_effect": web} if isinstance(web, Exception) else {"return_value": web})
             ) as find:
            nct_jobs._process(sid, bs, page)
        return find, bs

    def test_process_fetches_web_lyrics_when_nct_has_none(self):
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        find, bs = self._run_process(sid, "", {"lyrics": "Câu 1\nCâu 2", "source": "https://a.vn/x"})
        find.assert_called_once()
        self.assertEqual(find.call_args.args[1:3], ("Bài A", "Ca sĩ A"))
        bs.new_page.return_value.close.assert_called_once()    # tab tìm lời được đóng
        item = self._items()[0]
        self.assertEqual((item["lyrics_text"], item["lyrics_source"], item["status"]),
                         ("Câu 1\nCâu 2", "https://a.vn/x", "done"))
        from backend.cover import nct_jobs
        txt = nct_jobs.source_dir(self.pid, "Cover Test") / "Bài A - Ca sĩ A.txt"
        self.assertIn("Lời lấy trên mạng: https://a.vn/x", txt.read_text(encoding="utf-8"))

    def test_process_skips_web_when_nct_or_user_has_lyrics(self):
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        find, _ = self._run_process(sid, "Lời nhaccuatui", {})
        find.assert_not_called()
        self.assertEqual(self._items()[0]["lyrics_source"], "")
        sid2 = self._add("Bài B")["ids"][0]
        self._set(sid2, lyrics_text="Lời tôi dán")
        find, _ = self._run_process(sid2, "", {})
        find.assert_not_called()

    def test_process_web_lyrics_failure_skips_without_tempo_or_suno(self):
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        find, _ = self._run_process(sid, "", RuntimeError("Google lỗi"))
        find.assert_called_once()
        item = self._items()[0]
        self.assertEqual((item["status"], item["lyrics_text"]),
                         ("skipped_no_lyrics", ""))
        self.assertFalse(item["tempo_ready"])
        self.assertFalse(item["suno_created"])

    def test_new_download_replaces_old_tempo_with_automatic_4_5x_export(self):
        from backend.cover import tempo
        from sqlmodel import Session
        from backend.models import SourceSong
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        old = tempo.tempo_dir(self.pid, "Cover Test") / "old.wav"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b"RIFF-old")
        self._set(sid, tempo_factor=0.5, tempo_file_path=str(old),
                  suno_song_ids="old-id", suno_status="failed")
        self._run_process(sid, "Lời", {})
        with Session(self.engine) as session:
            src = session.get(SourceSong, sid)
            self.assertEqual(src.tempo_factor, 4.5)
            self.assertTrue(Path(src.tempo_file_path).is_file())
            self.assertEqual((src.suno_song_ids, src.suno_status), ("", ""))
        self.assertFalse(old.exists())

    def test_delete_never_touches_files_outside_tool_folder(self):
        sid = self._add("Bài A")["ids"][0]
        outside = self.root / "nhac_cua_ban.mp3"
        outside.write_bytes(b"x")
        self._set(sid, file_path=str(outside))
        r = self.client.delete(f"/api/sources/{sid}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(outside.exists())
        self.assertEqual(self._items(), [])

    def test_delete_lyrics_only_removes_its_txt(self):
        from backend.cover import nct_jobs
        sid = self._add("Bài B")["ids"][0]
        self._set(sid, title="Bài B", artist="Ca sĩ B", lyrics_text="lời", status="login")
        txt = nct_jobs.source_dir(self.pid, "Cover Test") / "Bài B - Ca sĩ B.txt"
        txt.parent.mkdir(parents=True)
        txt.write_text("lời", encoding="utf-8")
        self.assertEqual(self.client.delete(f"/api/sources/{sid}").status_code, 200)
        self.assertFalse(txt.exists())

    def test_import_covers_then_make_lyrics(self):
        from sqlmodel import Session, select
        from backend.models import CoverSong
        sid = self._add("Bài A - Ca sĩ A")["ids"][0]
        self._set(sid, title="Bài A", artist="Ca sĩ A", lyrics_text="Dòng 1\nDòng 2")

        files = [("files", ("suno_1.wav", b"RIFF1", "audio/wav")),
                 ("files", ("suno_2.wav", b"RIFF2", "audio/wav"))]
        r = self.client.post(f"/api/sources/{sid}/covers", files=files)
        self.assertEqual(r.status_code, 200, r.text)
        names = [a["filename"] for a in r.json()["added"]]
        self.assertEqual(names, ["Bài A - cover.wav", "Bài A - cover 2.wav"])
        saved = sorted(p.name for p in (self.root / "media").rglob("ban_cover/*.wav"))
        self.assertEqual(saved, ["Bài A - cover 2.wav", "Bài A - cover.wav"])
        self.assertEqual(len(self._items()[0]["covers"]), 2)

        with Session(self.engine) as s:
            songs = s.exec(select(CoverSong).order_by(CoverSong.position)).all()
            self.assertEqual([(c.title, c.artist, c.source_id) for c in songs],
                             [("Bài A", "Ca sĩ A", sid)] * 2)
            songs[1].lyrics_text = ""        # giả sử lời bị xoá → «Tạo lời» điền lại
            s.add(songs[1])
            s.commit()

        r = self.client.post(f"/api/sources/projects/{self.pid}/make-lyrics")
        self.assertEqual(r.json(), {"songs": 2, "filled": 1, "queued": 2})

    def test_import_covers_rejects_non_audio(self):
        sid = self._add("Bài A")["ids"][0]
        r = self.client.post(f"/api/sources/{sid}/covers",
                             files=[("files", ("anh.png", b"x", "image/png"))])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._items()[0]["covers"], [])


if __name__ == "__main__":
    unittest.main()
