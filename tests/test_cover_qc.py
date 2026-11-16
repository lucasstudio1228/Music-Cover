"""Tab ② Suno Cover: kiểm tra bản cover bị lỗi (so với chính bài gốc), tự nhập bài
cover + lời, «Tạo lại trên Suno». Không mở trình duyệt, không tốn credit — DB và
thư mục tạm, số đo audio giả (trừ 1 test đo file WAV tổng hợp thật)."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import cover_qc
from backend.routers.sources import clean_lyrics


def M(**kw):
    """Số đo 1 bài «sạch» (dạng track_qc.measure_array + clip_runs)."""
    m = {"duration": 240.0, "sample_rate": 44100, "rms_db": -14.0, "peak": 0.98,
         "clip_samples": 0, "clip_first": None, "gap_max": 0.0, "gap_at": None,
         "end_db": -40.0, "end_rel_db": -26.0, "hf_median": 4.0, "hf_p90": 6.0,
         "hf_blocks": [4.0] * 24, "clip_runs": 0}
    m.update(kw)
    return m


CTX = {"hf_median": 4.0, "rms_db": -14.0, "clip_runs": 0}


def codes(issues, level=None):
    return [i["code"] for i in issues if level is None or i["level"] == level]


class CleanLyricsTests(unittest.TestCase):
    def test_strips_lrc_tags_and_timestamps(self):
        raw = ("[ti:Bài A]\r\n[ar:Ca sĩ]\r\n[00:12.30]Câu một  \r\n[00:15.00][01:20.5]Câu hai\r\n"
               "\r\n\r\n\r\n  Câu ba\r\n\r\n")
        self.assertEqual(clean_lyrics(raw), "Câu một\nCâu hai\n\nCâu ba")

    def test_keeps_brackets_that_are_not_timestamps(self):
        self.assertEqual(clean_lyrics("[Điệp khúc]\nLa la"), "[Điệp khúc]\nLa la")
        self.assertEqual(clean_lyrics(""), "")

    def test_drops_nhaccuatui_title_header_only_at_top(self):
        from backend.cover import lyrics as cover_lyrics
        from backend.cover.nct import lyrics_from_html
        raw = "Bài hát: Sao Mình Chưa Nắm Tay Nhau - Yan Nguyễn\n\nRồi mùa yêu thương\nCâu hai"
        self.assertEqual(clean_lyrics(raw), "Rồi mùa yêu thương\nCâu hai")
        self.assertEqual(cover_lyrics.clean_lyrics(raw), ["Rồi mùa yêu thương", "Câu hai"])
        html = "Bài hát: Tên - Ca sĩ<br><br>Ca sĩ: A<br>Câu một<br>Câu hai " + "la " * 50
        self.assertTrue(lyrics_from_html(html).startswith("Câu một"))
        # Nằm giữa bài thì là lời thật → giữ.
        mid = "Câu một\nLời: anh nói thương em"
        self.assertEqual(cover_lyrics.strip_lyrics_header(mid), mid)


class JudgeTests(unittest.TestCase):
    def test_clean_cover_has_no_issue(self):
        self.assertEqual(cover_qc.judge(M(), M(), CTX), [])

    def test_bright_pop_cover_is_not_noise_when_original_is_bright_too(self):
        # Bản gốc phối sáng (5 %) → bản cover 7 % vẫn bình thường.
        self.assertEqual(codes(cover_qc.judge(M(hf_median=7.0), M(hf_median=5.0), CTX)), [])

    def test_noise_vs_original(self):
        blocks = [1.0] * 6 + [9.0] * 4 + [12.0] + [8.0] * 13
        issues = cover_qc.judge(M(hf_median=8.5, hf_blocks=blocks), M(hf_median=1.2), CTX)
        self.assertEqual(codes(issues, "error"), ["noise"])
        self.assertIn("1:00", issues[0]["message"])          # xuất hiện từ khối thứ 7

    def test_cut_short_vs_original(self):
        issues = cover_qc.judge(M(duration=100.0), M(duration=260.0), CTX)
        self.assertEqual(codes(issues, "error"), ["cut"])
        self.assertEqual(codes(cover_qc.judge(M(duration=200.0), M(duration=260.0), CTX)), [])
        self.assertEqual(codes(cover_qc.judge(M(duration=450.0), M(duration=260.0), CTX)),
                         ["long"])

    def test_without_original_short_file_is_error(self):
        self.assertEqual(codes(cover_qc.judge(M(duration=70.0), None, CTX), "error"), ["cut"])
        self.assertEqual(codes(cover_qc.judge(M(duration=150.0), None, CTX)), [])

    def test_clipping_relative_to_original(self):
        self.assertEqual(codes(cover_qc.judge(M(clip_runs=600), M(clip_runs=300), CTX)), [])
        issues = cover_qc.judge(M(clip_runs=600, clip_first=75.0), M(clip_runs=20), CTX)
        self.assertEqual(codes(issues, "error"), ["clipping"])
        self.assertEqual(codes(cover_qc.judge(M(clip_runs=60), M(clip_runs=0), CTX)), [])

    def test_dropout_only_if_original_has_none(self):
        self.assertEqual(codes(cover_qc.judge(M(gap_max=4.0, gap_at=90.0), M(), CTX), "error"),
                         ["dropout"])
        self.assertEqual(codes(cover_qc.judge(M(gap_max=4.0), M(gap_max=3.5), CTX)), [])

    def test_abrupt_end_is_only_a_warning_and_skipped_if_original_too(self):
        self.assertEqual(codes(cover_qc.judge(M(end_rel_db=-3.0), M(), CTX), "warning"),
                         ["abrupt_end"])
        self.assertEqual(codes(cover_qc.judge(M(end_rel_db=-3.0), M(end_rel_db=-4.0), CTX)), [])

    def test_silent(self):
        self.assertEqual(codes(cover_qc.judge(M(rms_db=-60.0), M(), CTX)), ["silent"])


class MeasureTests(unittest.TestCase):
    def test_clip_runs_counts_flat_tops_only(self):
        x = np.zeros((1000, 2), dtype=np.float32)
        x[10, 0] = 1.0                       # đỉnh lẻ (giải mã MP3) → không tính
        x[100:106, 0] = 1.0                  # 6 mẫu dẹt → 1 đoạn
        x[200:204, 1] = -1.0                 # 4 mẫu dẹt kênh phải → 1 đoạn
        x[300:303, 1] = 1.0                  # 3 mẫu → chưa đủ
        self.assertEqual(cover_qc.clip_runs(x), 2)

    def test_measure_real_wav(self):
        import soundfile as sf
        sr = 22050
        t = np.arange(sr * 150) / sr
        y = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        y[sr * 60: sr * 65] = 0.0           # 5 giây mất tiếng giữa bài
        with TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            sf.write(str(p), np.stack([y, y], axis=1), sr)
            m = cover_qc.measure_file(p)
        self.assertAlmostEqual(m["duration"], 150.0, places=1)
        self.assertGreaterEqual(m["gap_max"], 4.5)
        self.assertEqual(m["clip_runs"], 0)
        self.assertEqual(codes(cover_qc.judge(m, None, CTX), "error"), ["dropout"])


class ApiTests(unittest.TestCase):
    """API tab ②: tự nhập bài cover, kết quả kiểm tra lỗi, Báo lỗi / Nghe ổn, Tạo lại."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import Project
        from backend.video import config
        tmp = TemporaryDirectory(prefix="cover-qc-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            proj = Project(name="QC Test")
            s.add(proj)
            s.commit()
            self.pid = proj.id

        def _session():
            with Session(self.engine) as s:
                yield s
        app.dependency_overrides[get_session] = _session
        self.addCleanup(app.dependency_overrides.clear)
        self.qc = mock.MagicMock()
        self.nct = mock.MagicMock(side_effect=lambda ids: len(ids))
        for p in (mock.patch.object(config, "MEDIA_ROOT", self.root / "media"),
                  mock.patch("backend.cover.nct_jobs.submit", self.nct),
                  mock.patch("backend.cover.cover_qc.review_async", self.qc),
                  mock.patch("backend.core_bridge.probe_file", self._fake_probe)):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app)

    @staticmethod
    def _fake_probe(path):
        return SimpleNamespace(path=path, duration_seconds=240.0, sample_rate=48000,
                               channels=2, format="WAV", is_lossy=False, subtype="PCM_24")

    def _own(self, title="Bài A", artist="Ca sĩ A", lyrics="", n=2, original=True, **extra):
        files = [("files", (f"suno_{i}.wav", f"RIFF{i}".encode(), "audio/wav"))
                 for i in range(1, n + 1)]
        if original:
            files.append(("original", ("goc.mp3", b"ID3goc", "audio/mpeg")))
        data = {"title": title, "artist": artist, "lyrics": lyrics, **extra}
        return self.client.post(f"/api/sources/projects/{self.pid}/own", data=data, files=files)

    def _items(self):
        r = self.client.get(f"/api/sources/projects/{self.pid}")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["items"]

    def _review(self, metrics_by_name):
        """Chạy cover_qc.review thật trên DB tạm với số đo giả theo tên file."""
        def fake(path):
            for key, m in metrics_by_name.items():
                if key in Path(path).name:
                    return m
            return M()
        cover_qc.review(self.pid, engine=self.engine, measure=fake)

    def test_own_cover_creates_manual_song_with_lyrics_and_original(self):
        r = self._own(lyrics="[00:01.00]Dòng 1\r\n[00:03.00]Dòng 2\r\n")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([a["filename"] for a in r.json()["added"]],
                         ["Bài A - cover.wav", "Bài A - cover 2.wav"])
        self.qc.assert_called_once_with(self.pid)
        self.nct.assert_not_called()
        (item,) = self._items()
        self.assertEqual((item["status"], item["title"], item["artist"], item["lyrics_text"]),
                         ("manual", "Bài A", "Ca sĩ A", "Dòng 1\nDòng 2"))
        self.assertTrue(item["has_file"])
        self.assertEqual(item["file_name"], "Bài A - Ca sĩ A.mp3")
        self.assertEqual(len(item["covers"]), 2)
        self.assertEqual({c["qc"]["status"] for c in item["covers"]}, {"pending"})

        from sqlmodel import Session, select
        from backend.models import CoverSong
        with Session(self.engine) as s:
            songs = s.exec(select(CoverSong)).all()
            self.assertEqual({(c.title, c.artist, c.lyrics_text) for c in songs},
                             {("Bài A", "Ca sĩ A", "Dòng 1\nDòng 2")})

        # Bài tự nhập: không tải lại / tìm lại trên nhaccuatui.
        sid = item["id"]
        self.assertEqual(self.client.post(f"/api/sources/{sid}/retry").status_code, 400)
        self.assertEqual(self.client.put(f"/api/sources/{sid}", json={"query": "x"}).status_code,
                         400)
        self.assertEqual(self.client.post(f"/api/sources/projects/{self.pid}/start").json(),
                         {"queued": 0})

    def test_own_cover_rejects_bad_input_without_leaving_files(self):
        self.assertEqual(self._own(title="  ").status_code, 400)
        r = self.client.post(f"/api/sources/projects/{self.pid}/own", data={"title": "B"},
                             files=[("files", ("anh.png", b"x", "image/png"))])
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/sources/projects/{self.pid}/own", data={"title": "B"},
                             files=[("files", ("a.wav", b"RIFF", "audio/wav")),
                                    ("original", ("goc.txt", b"x", "text/plain"))])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._items(), [])
        self.assertEqual([p for p in (self.root / "media").rglob("*") if p.is_file()], [])

    def test_qc_flags_only_real_defects_and_marks(self):
        self._own(n=2)
        self._review({"cover.wav": M(hf_median=9.0), "cover 2.wav": M(hf_median=4.5),
                      "goc.mp3": M(hf_median=1.5), "Ca sĩ A.mp3": M(hf_median=1.5)})
        covers = self._items()[0]["covers"]
        bad, good = covers
        self.assertEqual(bad["qc"]["status"], "error")
        self.assertEqual(codes(bad["qc"]["issues"]), ["noise"])
        self.assertEqual(bad["qc"]["compared_with"], "original")
        self.assertEqual(good["qc"]["status"], "ok")

        # «✓ Nghe ổn» tắt báo đỏ; «🚩 Báo lỗi» bật đỏ cho bài máy thấy ổn.
        self.client.post(f"/api/sources/covers/{bad['track_id']}/mark", json={"dismissed": True})
        self.client.post(f"/api/sources/covers/{good['track_id']}/mark", json={"flagged": True})
        bad, good = self._items()[0]["covers"]
        self.assertEqual((bad["qc"]["status"], good["qc"]["status"]), ("ok", "error"))
        self.assertTrue(good["qc"]["manual_flag"])
        # Báo lỗi lại bản đã «Nghe ổn» → bỏ cờ «nghe ổn».
        self.client.post(f"/api/sources/covers/{bad['track_id']}/mark", json={"flagged": True})
        bad, _ = self._items()[0]["covers"]
        self.assertEqual((bad["qc"]["status"], bad["qc"]["dismissed"]), ("error", False))

        self.assertEqual(self.client.post(f"/api/sources/projects/{self.pid}/qc").json(),
                         {"running": True})
        self.qc.assert_called_with(self.pid)

    def test_changed_file_goes_back_to_pending(self):
        self._own(n=1, original=False)
        self._review({})
        (cover,) = self._items()[0]["covers"]
        self.assertEqual((cover["qc"]["status"], cover["qc"]["compared_with"]), ("ok", "others"))
        path = next((self.root / "media").rglob("ban_cover/*.wav"))
        path.write_bytes(b"RIFF-new-content")
        (cover,) = self._items()[0]["covers"]
        self.assertEqual(cover["qc"]["status"], "pending")

    def test_redo_moves_bad_cover_aside_and_new_import_clears_it(self):
        sid = self._own(n=2).json()["id"]
        bad, good = self._items()[0]["covers"]
        r = self.client.post(f"/api/sources/{sid}/redo", json={"track_ids": [bad["track_id"]]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["removed"], r.json()["moved"]), (1, 1))
        item = self._items()[0]
        self.assertEqual(item["suno_status"], "redo")
        self.assertEqual([c["track_id"] for c in item["covers"]], [good["track_id"]])
        cover_dir = next((self.root / "media").rglob("ban_cover"))
        self.assertEqual(sorted(p.name for p in cover_dir.rglob("*.wav")),
                         ["Bài A - cover 2.wav", "Bài A - cover.wav"])
        self.assertTrue((cover_dir / "_loi" / "Bài A - cover.wav").exists())

        # Bản cover không thuộc bài này → từ chối.
        other = self._own(title="Bài B", n=1).json()
        r = self.client.post(f"/api/sources/{sid}/redo",
                             json={"track_ids": [other["added"][0]["track_id"]]})
        self.assertEqual(r.status_code, 400)

        r = self.client.post(f"/api/sources/{sid}/covers",
                             files=[("files", ("moi.wav", b"RIFFnew", "audio/wav"))])
        self.assertEqual(r.status_code, 200, r.text)
        item = self._items()[0]
        self.assertEqual(item["suno_status"], "")
        self.assertEqual(len(item["covers"]), 2)

    def test_cover_audio(self):
        self._own(n=1, original=False)
        (cover,) = self._items()[0]["covers"]
        r = self.client.get(f"/api/sources/covers/{cover['track_id']}/audio")
        self.assertEqual((r.status_code, r.content), (200, b"RIFF1"))
        self.assertEqual(self.client.get("/api/sources/covers/999/audio").status_code, 404)


if __name__ == "__main__":
    unittest.main()
