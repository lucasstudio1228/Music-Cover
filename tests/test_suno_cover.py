"""Đợt B — tool tự làm cover trên Suno (tab ② Suno Cover).

Không mở trình duyệt, không tốn credit: driver Suno giả, DB + thư mục tạm."""
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import suno_cover, suno_jobs
from backend.video.suno_driver import SunoCaptchaRequired, SunoError, SunoUIChanged


class PlaywrightIsolationTests(unittest.TestCase):
    def test_legacy_transform_is_local_and_keeps_natural_spaces(self):
        logs = []
        result = suno_jobs._transform_lyrics_isolated("Câu một", logs.append)
        self.assertEqual(result, "Câu một")
        self.assertNotIn("_", result)
        self.assertTrue(any("cục bộ" in line for line in logs))


class DownloadRecoveryTests(unittest.TestCase):
    def test_both_created_ids_use_continuous_asset_downloader(self):
        """Production bỏ Studio/PCM realtime và tải đúng cả hai ID vừa tạo."""
        with TemporaryDirectory(prefix="suno-studio-two-ids-") as tmp:
            out = Path(tmp)
            ids = ["11111111-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                   "22222222-bbbb-bbbb-bbbb-bbbbbbbbbbbb"]
            direct = []

            class Driver:
                def download_asset_wav(self, song_id, dest):
                    direct.append(song_id)
                    Path(dest).write_bytes(b"RIFF" + b"\0" * 4 + b"WAVEasset")
                    return {"path": str(dest), "mode": "authorized_continuous_decrypt_pcm16"}

                def download_wav(self, song_id, dest, timeout_sec=0):
                    raise AssertionError("Không được quay lại Studio")

                def close_extra_tabs(self):
                    pass

            valid = SimpleNamespace(valid=True, reason="")
            with mock.patch("backend.video.suno_verify.verify_wav", return_value=valid):
                files = suno_jobs._download_all(Driver(), ids, out, "Bài", lambda _: None)

            self.assertEqual(direct, ids)
            self.assertEqual(len(files), 2)
            self.assertTrue(all(path.is_file() for path in files))

    def test_direct_failure_retries_direct_and_never_uses_studio(self):
        with TemporaryDirectory(prefix="suno-download-no-fallback-") as tmp:
            out = Path(tmp)
            song_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
            logs = []
            calls = []

            class Driver:
                def download_asset_wav(self, _song_id, _dest):
                    calls.append(_song_id)
                    raise RuntimeError("Suno rights temporarily unavailable")

                def download_wav(self, *_args, **_kwargs):
                    raise AssertionError("Không được quay lại Studio")

                def close_extra_tabs(self):
                    pass

                def _wait(self, _ms):
                    pass

            valid = SimpleNamespace(valid=True, reason="")
            with mock.patch(
                    "backend.cover.suno_wav_downloader.download_song_id_to_path",
                    side_effect=AssertionError("Không được tải trực tiếp")), \
                 mock.patch("backend.video.suno_verify.verify_wav", return_value=valid), \
                 mock.patch.object(suno_jobs, "DOWNLOAD_PASSES", 2):
                with self.assertRaises(RuntimeError) as ctx:
                    suno_jobs._download_all(Driver(), [song_id], out, "Bài", logs.append)

            self.assertEqual(calls, [song_id, song_id])
            self.assertIn("rights temporarily unavailable", str(ctx.exception))

    def test_reuses_valid_orphan_wav_without_downloading_again(self):
        with TemporaryDirectory(prefix="suno-download-recovery-") as tmp:
            out = Path(tmp)
            wav = out / "Bài - cover.wav"
            wav.write_bytes(b"RIFForphan")
            song_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            suno_jobs._write_ledger(out / suno_jobs.WORK_STEM / suno_jobs.DOWNLOAD_LEDGER,
                                    {song_id: wav.name})
            drv = mock.MagicMock()
            valid = SimpleNamespace(valid=True, reason="")
            with mock.patch("backend.video.suno_verify.verify_wav", return_value=valid):
                files = suno_jobs._download_all(drv, [song_id], out, "Bài", lambda _: None)
            self.assertEqual(files, [wav])
            drv.download_wav.assert_not_called()

    def test_wav_of_an_older_create_is_never_reused_for_new_ids(self):
        """Lượt Create mới: WAV cũ (của ID khác / không rõ ID) còn trong thư mục
        → vẫn tải CẢ 2 bản mới qua Studio, không nhận nhầm file cũ."""
        with TemporaryDirectory(prefix="suno-download-recovery-") as tmp:
            out = Path(tmp)
            old = out / "Bài - cover.wav"
            old.write_bytes(b"RIFFold")
            ledger = out / suno_jobs.WORK_STEM / suno_jobs.DOWNLOAD_LEDGER
            suno_jobs._write_ledger(ledger, {"old-id": old.name})
            new_ids = ["cccccccc-cccc-cccc-cccc-cccccccccccc",
                       "dddddddd-dddd-dddd-dddd-dddddddddddd"]
            downloaded = []

            class Driver:
                def download_wav(self, song_id, dest, timeout_sec=0):
                    downloaded.append(song_id)
                    Path(dest).write_bytes(b"RIFFnew")
                    return dest

                def close_extra_tabs(self):
                    pass

            valid = SimpleNamespace(valid=True, reason="")
            with mock.patch("backend.video.suno_verify.verify_wav", return_value=valid):
                files = suno_jobs._download_all(Driver(), new_ids, out, "Bài",
                                                lambda _: None)
            self.assertEqual(new_ids, downloaded)
            self.assertNotIn(old, files)
            self.assertEqual(b"RIFFold", old.read_bytes())     # file cũ vẫn giữ
            saved = suno_jobs._read_ledger(ledger)
            self.assertEqual({f.name for f in files}, {saved[i] for i in new_ids})

    def test_accepts_wav_written_before_browser_closed_error(self):
        with TemporaryDirectory(prefix="suno-download-recovery-") as tmp:
            out = Path(tmp)

            class ClosedAfterWrite:
                def download_wav(self, song_id, dest, timeout_sec=0):
                    Path(dest).write_bytes(b"RIFFcomplete")
                    raise RuntimeError("Target page, context or browser has been closed")

                def close_extra_tabs(self):
                    pass

            valid = SimpleNamespace(valid=True, reason="")
            with mock.patch("backend.video.suno_verify.verify_wav", return_value=valid):
                files = suno_jobs._download_all(
                    ClosedAfterWrite(), ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
                    out, "Bài", lambda _: None)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].is_file())

    def test_reopens_browser_after_first_wav_and_downloads_remaining_id(self):
        with TemporaryDirectory(prefix="suno-download-recovery-") as tmp:
            out = Path(tmp)

            class FakeContext:
                @property
                def pages(self):
                    return []

            class FakePage:
                def __init__(self, closed=False):
                    self.closed = closed
                    self.context = FakeContext()

                def is_closed(self):
                    return self.closed

            class Driver:
                def __init__(self, closes_after_download=False):
                    self.page = FakePage()
                    self.closes_after_download = closes_after_download
                    self.downloaded = []

                def download_wav(self, song_id, dest, timeout_sec=0):
                    self.downloaded.append(song_id)
                    Path(dest).write_bytes(b"RIFFcomplete")
                    if self.closes_after_download:
                        self.page.closed = True
                    return dest

                def close_extra_tabs(self):
                    if self.page.closed:
                        raise RuntimeError(
                            "Target page, context or browser has been closed")

            first = Driver(closes_after_download=True)
            replacement = Driver()
            reopened = []

            def reopen_driver():
                reopened.append(True)
                return replacement

            ids = ["11111111-1111-1111-1111-111111111111",
                   "22222222-2222-2222-2222-222222222222"]
            valid = SimpleNamespace(valid=True, reason="")
            with mock.patch("backend.video.suno_verify.verify_wav", return_value=valid):
                files = suno_jobs._download_all(
                    first, ids, out, "Bài", lambda _: None,
                    reopen_driver=reopen_driver)

            self.assertEqual(len(files), 2)
            self.assertEqual(len(reopened), 1)
            self.assertEqual(first.downloaded, [ids[0]])
            self.assertEqual(replacement.downloaded, [ids[1]])
            self.assertTrue(all(path.is_file() for path in files))


class _Base(unittest.TestCase):
    """DB + media tạm, API client, các hàm nặng được thay bằng đồ giả."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import Project
        from backend.video import config
        tmp = TemporaryDirectory(prefix="suno-cover-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            proj = Project(name="Suno Test")
            s.add(proj)
            s.commit()
            self.pid = proj.id

        def _session():
            with Session(self.engine) as s:
                yield s
        app.dependency_overrides[get_session] = _session
        self.addCleanup(app.dependency_overrides.clear)
        self.qc = mock.MagicMock()
        self.master = mock.MagicMock()       # master thật đã có test riêng (test_mastering)
        self.submit = mock.MagicMock(side_effect=lambda ids, dry_run=False: len(ids))
        for p in (mock.patch.object(config, "MEDIA_ROOT", self.root / "media"),
                  mock.patch("backend.cover.nct_jobs.submit", mock.MagicMock()),
                  mock.patch("backend.cover.cover_qc.review_async", self.qc),
                  mock.patch("backend.cover.mastering.submit", self.master),
                  mock.patch("backend.core_bridge.probe_file", self._fake_probe),
                  mock.patch.object(suno_jobs, "engine", self.engine),
                  mock.patch.object(suno_jobs, "LOGIN_FILE", self.root / "suno_login.json")):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app)
        with suno_jobs._lock:
            suno_jobs._pending.clear()
            suno_jobs._state.update(current=None, human="")

    @staticmethod
    def _fake_probe(path):
        return SimpleNamespace(path=path, duration_seconds=240.0, sample_rate=48000,
                               channels=2, format="WAV", is_lossy=False, subtype="PCM_24")

    def _source(self, title="Bài A", artist="Ca sĩ A", lyrics="Câu 1\nCâu 2",
                original=True, **fields):
        from sqlmodel import Session
        from backend.models import SourceSong
        path = ""
        if original:
            p = self.root / "goc" / f"{title}.mp3"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"ID3goc")
            path = str(p)
            adjusted = self.root / "tempo" / f"{title}.wav"
            adjusted.parent.mkdir(parents=True, exist_ok=True)
            adjusted.write_bytes(b"RIFFtempo")
            fields.setdefault("tempo_file_path", str(adjusted))
        with Session(self.engine) as s:
            src = SourceSong(project_id=self.pid, position=1, query=f"{title} - {artist}",
                             title=title, artist=artist, lyrics_text=lyrics,
                             file_path=path, status="done", **fields)
            s.add(src)
            s.commit()
            return src.id

    def _get(self, sid):
        from sqlmodel import Session
        from backend.models import SourceSong
        with Session(self.engine) as s:
            return s.get(SourceSong, sid)

    def _items(self):
        r = self.client.get(f"/api/sources/projects/{self.pid}")
        self.assertEqual(r.status_code, 200, r.text)
        return {it["id"]: it for it in r.json()["items"]}

    def _add_cover(self, sid, name="cover.wav"):
        r = self.client.post(f"/api/sources/{sid}/covers",
                             files=[("files", (name, b"RIFFx", "audio/wav"))])
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["added"][0]["track_id"]


# ───────────────────────────── API ─────────────────────────────
class ApiTests(_Base):
    def setUp(self):
        super().setUp()
        p = mock.patch("backend.cover.suno_jobs.submit", self.submit)
        p.start()
        self.addCleanup(p.stop)

    def test_list_has_suno_worker_and_fields(self):
        sid = self._source(suno_status="running", suno_error="x", vocal_gender="female",
                           suno_song_ids="a,b")
        r = self.client.get(f"/api/sources/projects/{self.pid}").json()
        self.assertIn("suno_worker", r)
        self.assertFalse(r["suno_worker"]["busy"])
        item = r["items"][0]
        self.assertEqual(item["id"], sid)
        # «running» nhưng hàng đợi không chạy (server khởi động lại) → hiện «stopped».
        self.assertEqual(item["suno_status"], "stopped")
        self.assertEqual((item["suno_error"], item["vocal_gender"], item["suno_created"]),
                         ("x", "female", True))

    def test_exclude_and_restore_song_after_cover_download(self):
        from sqlmodel import Session, select
        from backend.models import CoverSong, SourceSong, Track
        from backend.routers import sources as sources_router
        sid = self._source()
        cover_path = self.root / "cover.wav"
        cover_path.write_bytes(b"RIFFcover")
        with Session(self.engine) as session:
            track = Track(project_id=self.pid, filename=cover_path.name,
                          filepath=str(cover_path), duration_seconds=200,
                          sample_rate=48000, channels=2, format="WAV", is_lossy=False)
            session.add(track)
            session.flush()
            session.add(CoverSong(project_id=self.pid, track_id=track.id,
                                  source_id=sid, title="Bài A"))
            session.commit()
            removed = sources_router.exclude_source(sid, session)
            self.assertEqual(1, removed["removed_covers"])
            self.assertEqual("excluded", session.get(SourceSong, sid).status)
            self.assertEqual([], session.exec(select(CoverSong)).all())
            with mock.patch("backend.core_bridge.probe_file", return_value=self._fake_probe(cover_path)):
                restored = sources_router.include_source(sid, session)
            self.assertEqual(1, restored["restored_covers"])
            self.assertEqual("done", session.get(SourceSong, sid).status)
            self.assertEqual(1, len(session.exec(select(CoverSong)).all()))

    def test_recreate_with_custom_editor_bpm_clears_old_suno_ids(self):
        from sqlmodel import Session
        from backend.models import SourceSong
        from backend.routers import sources as sources_router
        sid = self._source(suno_song_ids="old-a,old-b",
                           suno_editor_song_id="old-editor", suno_status="done")
        with Session(self.engine) as session:
            result = sources_router.suno_one(
                sid, sources_router.SunoOneIn(editor_bpm=55), session)
            self.assertEqual(1, result["queued"])
            src = session.get(SourceSong, sid)
            self.assertEqual(55, src.suno_editor_bpm)
            self.assertEqual("", src.suno_song_ids)
            self.assertEqual("", src.suno_editor_song_id)

    def test_recreate_applies_changed_instrument_instead_of_preserving_old_style(self):
        from sqlmodel import Session
        from backend.models import SourceSong
        from backend.routers import sources as sources_router
        sid = self._source(
            suno_style_prompt="Ballad vocal cover, supporting piano",
            suno_style_signature=sources_router.INSTRUMENT_STYLE_DIRTY,
            suno_preserve_style=False,
            featured_instrument="Saxophone")
        with Session(self.engine) as session:
            result = sources_router.suno_one(
                sid, sources_router.SunoOneIn(
                    fresh=True, editor_bpm=32, tempo_only=True), session)
            self.assertEqual(1, result["queued"])
            src = session.get(SourceSong, sid)
            self.assertEqual("Saxophone", src.featured_instrument)
            self.assertFalse(src.suno_preserve_style)
            self.assertEqual(sources_router.INSTRUMENT_STYLE_DIRTY,
                             src.suno_style_signature)

    def test_redo_bad_cover_only_changes_tempo_and_forces_new_editor(self):
        from sqlmodel import Session
        from backend.models import CoverSong, SourceSong, Track
        from backend.routers import sources as sources_router
        old_style = ("Latin Dance Cumbia Remix, warm nylon guitar, congas, "
                     "expressive violin, relaxed organic syncopation at 100-105 BPM")
        sid = self._source(suno_song_ids="old-a,old-b",
                           suno_editor_song_id="old-editor", suno_status="done",
                           suno_style_prompt=old_style,
                           suno_style_signature="old-signature")
        cover_path = self.root / "bad-cover.wav"
        cover_path.write_bytes(b"RIFFbad")
        with Session(self.engine) as session:
            track = Track(project_id=self.pid, filename=cover_path.name,
                          filepath=str(cover_path), duration_seconds=200,
                          sample_rate=48000, channels=2, format="WAV", is_lossy=False)
            session.add(track)
            session.flush()
            session.add(CoverSong(project_id=self.pid, track_id=track.id,
                                  source_id=sid, title="Bài A"))
            session.commit()
            result = sources_router.redo_cover(
                sid, sources_router.RedoIn(
                    track_ids=[track.id], editor_bpm=35, tempo_only=True), session)
            self.assertTrue(result["queued"])
            src = session.get(SourceSong, sid)
            self.assertEqual(src.suno_editor_bpm, 35)
            self.assertEqual(src.suno_song_ids, "")
            self.assertEqual(src.suno_editor_song_id, "")
            self.assertTrue(src.suno_preserve_style)
        self.assertEqual(src.suno_style_prompt, old_style)
        self.submit.assert_called_once_with([sid])

    def test_start_picks_songs_needing_suno(self):
        fresh = self._source(title="Mới")                        # chưa có cover → làm
        done = self._source(title="Xong")
        self._add_cover(done)                                   # đã có cover → bỏ
        failed = self._source(title="Lỗi lần trước")
        self._add_cover(failed)
        self._source(title="Bị từ chối", suno_status="rejected")  # Suno từ chối → bỏ
        self._source(title="Thiếu lời", lyrics="")                # thiếu lời → bỏ + đếm
        self._source(title="Thiếu file", original=False)
        from sqlmodel import Session
        from backend.models import SourceSong
        with Session(self.engine) as s:          # nhập cover tay xoá trạng thái → đặt lại
            src = s.get(SourceSong, failed)
            src.suno_status = "failed"
            s.add(src)
            s.commit()
        r = self.client.post(f"/api/sources/projects/{self.pid}/suno/start",
                             json={"dry_run": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"queued": 2, "skipped": 2})
        self.submit.assert_called_once_with([fresh, failed], dry_run=False)

        self.submit.reset_mock()
        r = self.client.post(f"/api/sources/projects/{self.pid}/suno/start",
                             json={"dry_run": True})
        self.assertEqual(r.json()["queued"], 1)                 # chạy thử: 1 bài
        self.submit.assert_called_once_with([fresh], dry_run=True)

    def test_fresh_start_recreates_all_ready_songs_and_clears_saved_ids(self):
        fresh = self._source(title="Mới")
        done = self._source(title="Đã có cover", suno_song_ids="old-a,old-b",
                            suno_editor_song_id="old-editor", suno_status="done")
        self._add_cover(done)
        r = self.client.post(f"/api/sources/projects/{self.pid}/suno/start",
                             json={"dry_run": False, "fresh": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["queued"], 2)
        self.submit.assert_called_once_with([fresh, done], dry_run=False)
        src = self._get(done)
        self.assertEqual(src.suno_song_ids, "")
        self.assertEqual(src.suno_editor_song_id, "")

    def test_fresh_start_reactivates_excluded_source_without_restoring_old_cover(self):
        from sqlmodel import Session
        from backend.routers import sources as sources_router
        sid = self._source(title="Bài thay thế", suno_song_ids="old-a,old-b",
                           suno_editor_song_id="old-editor", suno_status="done")
        with Session(self.engine) as session:
            sources_router.exclude_source(sid, session)
        self.assertEqual(self._get(sid).status, "excluded")
        r = self.client.post(f"/api/sources/projects/{self.pid}/suno/start",
                             json={"dry_run": False, "fresh": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["queued"], 1)
        self.assertEqual(self._get(sid).status, "done")
        self.assertEqual(self._get(sid).suno_song_ids, "")
        self.submit.assert_called_once_with([sid], dry_run=False)

    def test_one_song_can_replace_excluded_source(self):
        from sqlmodel import Session
        from backend.routers import sources as sources_router
        sid = self._source(title="Bài bị loại")
        with Session(self.engine) as session:
            sources_router.exclude_source(sid, session)
        r = self.client.post(f"/api/sources/{sid}/suno", json={"fresh": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["queued"], 1)
        self.assertEqual(self._get(sid).status, "done")
        self.submit.assert_called_once_with([sid], dry_run=False)

    def test_resume_start_keeps_saved_ids(self):
        sid = self._source(title="Đang tải dở", suno_song_ids="a,b",
                           suno_editor_song_id="editor", suno_status="failed")
        r = self.client.post(f"/api/sources/projects/{self.pid}/suno/start",
                             json={"dry_run": False, "fresh": False})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._get(sid).suno_song_ids, "a,b")
        self.submit.assert_called_once_with([sid], dry_run=False)

    def test_redo_enqueues_suno(self):
        sid = self._source()
        tid = self._add_cover(sid)
        r = self.client.post(f"/api/sources/{sid}/redo", json={"track_ids": [tid]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["queued"])
        self.submit.assert_called_once_with([sid])
        src = self._get(sid)
        self.assertEqual((src.suno_status, src.suno_error, src.suno_song_ids),
                         ("redo", None, ""))

    def test_redo_without_lyrics_only_marks_waiting(self):
        sid = self._source(lyrics="")
        tid = self._add_cover(sid)
        r = self.client.post(f"/api/sources/{sid}/redo", json={"track_ids": [tid]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["queued"])
        self.assertIn("chưa có lời", r.json()["missing"])
        self.submit.assert_not_called()
        self.assertEqual(self._get(sid).suno_status, "redo")

    def test_one_song(self):
        sid = self._source(original=False)
        r = self.client.post(f"/api/sources/{sid}/suno", json={})
        self.assertEqual(r.status_code, 400)               # thiếu file bài gốc
        self.assertIn("file bài gốc", r.json()["detail"])

        # Đã Create trên Suno từ trước → cho tải lại dù thiếu file gốc (không Create).
        sid2 = self._source(title="B", original=False, suno_song_ids="a,b")
        r = self.client.post(f"/api/sources/{sid2}/suno", json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.submit.assert_called_once_with([sid2], dry_run=False)
        self.assertEqual(self._get(sid2).suno_song_ids, "a,b")

        sid3 = self._source(title="C", suno_song_ids="a,b")
        r = self.client.post(f"/api/sources/{sid3}/suno", json={"fresh": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._get(sid3).suno_song_ids, "")   # tạo bản MỚI

    def test_active_song_is_locked(self):
        sid = self._source()
        with mock.patch.object(suno_jobs, "is_active", return_value=True):
            self.assertEqual(self.client.put(f"/api/sources/{sid}", json={"title": "X"})
                             .status_code, 409)
            self.assertEqual(self.client.delete(f"/api/sources/{sid}").status_code, 409)
            self.assertEqual(self.client.post(f"/api/sources/{sid}/suno", json={})
                             .status_code, 409)

    def test_vocal_gender(self):
        sid = self._source()
        r = self.client.put(f"/api/sources/{sid}", json={"vocal_gender": "male"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["vocal_gender"], "male")
        r = self.client.put(f"/api/sources/{sid}", json={"vocal_gender": "duet"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["vocal_gender"], "duet")
        r = self.client.put(f"/api/sources/{sid}", json={"vocal_gender": "robot"})
        self.assertEqual(r.status_code, 400)

    def test_featured_instrument_is_optional_and_saved_per_song(self):
        sid = self._source()
        r = self.client.put(f"/api/sources/{sid}",
                            json={"featured_instrument": "Saxophone"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["featured_instrument"], "Saxophone")
        r = self.client.put(f"/api/sources/{sid}",
                            json={"featured_instrument": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["featured_instrument"], "")
        r = self.client.put(
            f"/api/sources/{sid}",
            json={"featured_instrument": "__no_creative_instrument__"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            r.json()["featured_instrument"], "__no_creative_instrument__")
        r = self.client.put(f"/api/sources/{sid}",
                            json={"featured_instrument": "x" * 81})
        self.assertEqual(r.status_code, 400)

    def test_changed_instrument_marks_cached_style_for_regeneration(self):
        from sqlmodel import Session
        from backend.models import SourceSong
        from backend.routers import sources as sources_router
        sid = self._source(suno_style_prompt="Ballad vocal cover, supporting piano",
                           suno_style_signature="ai:old-signature",
                           suno_preserve_style=True)

        r = self.client.put(f"/api/sources/{sid}",
                            json={"featured_instrument": "Saxophone"})

        self.assertEqual(r.status_code, 200, r.text)
        with Session(self.engine) as session:
            src = session.get(SourceSong, sid)
            self.assertEqual(src.featured_instrument, "Saxophone")
            self.assertEqual(src.suno_style_signature,
                             sources_router.INSTRUMENT_STYLE_DIRTY)
            self.assertFalse(src.suno_preserve_style)

    def test_manual_import_clears_failed_state(self):
        sid = self._source(suno_status="rejected", suno_error="Suno từ chối")
        self._add_cover(sid)
        src = self._get(sid)
        self.assertEqual((src.suno_status, src.suno_error), ("", None))


# ───────────────────────── hàng đợi (driver giả) ─────────────────────────
class FakeDriver:
    last = None
    prepare_exc = None
    wait_exc = None
    fail_downloads = False

    def __init__(self, page, dry_run=True, selectors=None, log=None, on_human=None):
        self.page, self.dry_run, self.log = page, dry_run, log
        self.calls: list = []
        self.debug_dir = None
        FakeDriver.last = self

    def open_create_page(self):
        self.calls.append("open")

    def prepare_cover(self, original, title, lyrics, gender, min_credits,
                      editor_bpm=suno_cover.EDITOR_TEMPO_SLOW,
                      editor_song_id="", styles="", on_editor_saved=None):
        self.prepared_path = str(original)
        self.prepared_styles = styles
        self.calls.append(("prepare", title, gender, editor_bpm, editor_song_id))
        if FakeDriver.prepare_exc:
            raise FakeDriver.prepare_exc

    def save_debug(self, tag):
        return None

    def snapshot_song_ids(self):
        return {"old"}

    def click_create(self):
        assert not self.dry_run
        self.calls.append("create")

    def wait_for_new_songs(self, before, expected, **kw):
        if FakeDriver.wait_exc:
            raise FakeDriver.wait_exc
        return [SimpleNamespace(song_id="aaaa1111-x"), SimpleNamespace(song_id="bbbb2222-y")]

    def _wait(self, ms):
        pass

    def download_wav(self, song_id, dest, timeout_sec=180):
        self.calls.append(("download", song_id))
        if FakeDriver.fail_downloads:
            raise SunoError("Studio chưa mở được")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"RIFF" + song_id.encode())
        return str(dest)

    def close_extra_tabs(self):
        pass


class JobTests(_Base):
    def setUp(self):
        super().setUp()
        FakeDriver.last = None
        FakeDriver.prepare_exc = FakeDriver.wait_exc = None
        FakeDriver.fail_downloads = False
        ok = SimpleNamespace(valid=True, reason="", duration_seconds=200.0, sha256="x")
        for p in (mock.patch.object(suno_jobs, "CoverDriver", FakeDriver),
                  mock.patch.object(suno_jobs, "guess_vocal_gender", return_value="female"),
                  mock.patch.object(
                      suno_jobs, "_transform_lyrics_isolated",
                      side_effect=lambda text, log: text.replace(" ", "_")),
                  mock.patch.object(
                      suno_jobs, "generate_cover_styles",
                      return_value=("Vietnamese test cover, natural vocal, clear "
                                    "Vietnamese pronunciation, preserve lyrics exactly",
                                    "fallback:test")),
                  mock.patch.object(suno_jobs, "DOWNLOAD_PASSES", 2),
                  mock.patch("backend.video.suno_verify.verify_wav", return_value=ok)):
            p.start()
            self.addCleanup(p.stop)

    def _run(self, sid, dry=False):
        with suno_jobs._lock:
            suno_jobs._state["current"] = sid
        try:
            suno_jobs._process(sid, page=None, dry=dry)
        finally:
            with suno_jobs._lock:
                suno_jobs._state["current"] = None

    def test_success_creates_downloads_and_imports(self):
        sid = self._source(title="Bài A", artist="Ca sĩ A")
        self._run(sid)
        calls = FakeDriver.last.calls
        self.assertEqual(calls[0], ("prepare", "Bài A", "female", 32, ""))
        self.assertIn("tempo", FakeDriver.last.prepared_path)        # không upload file gốc
        self.assertIn("create", calls)
        src = self._get(sid)
        self.assertEqual((src.suno_status, src.suno_error, src.suno_song_ids),
                         ("done", None, ""))
        self.assertEqual(src.vocal_gender, "female")                 # AI đoán → lưu lại
        covers = self._items()[sid]["covers"]
        self.assertEqual(sorted(c["filename"] for c in covers),
                         ["Bài A - cover 2.wav", "Bài A - cover.wav"])
        self.qc.assert_called_once_with(self.pid)
        files = self.master.call_args.args[0]                       # tải xong → master 2 bản
        self.assertEqual(sorted(f.name for f in files),
                         ["Bài A - cover 2.wav", "Bài A - cover.wav"])
        self.assertEqual(self.master.call_args.kwargs["expected"], 2)

    def test_user_gender_is_kept(self):
        sid = self._source(vocal_gender="male")
        with mock.patch.object(suno_jobs, "guess_vocal_gender") as guess:
            self._run(sid)
        guess.assert_not_called()
        self.assertEqual(FakeDriver.last.calls[0][2], "male")

    def test_house_project_uses_editor_tempo_35(self):
        from sqlmodel import Session
        from backend.models import Project
        with Session(self.engine) as session:
            project = session.get(Project, self.pid)
            project.music_style = "Deep House"
            session.add(project)
            session.commit()
        sid = self._source()
        self._run(sid)
        self.assertEqual(FakeDriver.last.calls[0][3], 35)

    def test_tempo_only_reuses_exact_cached_style_without_ai(self):
        cached = "Vietnamese ballad, warm piano, exact old arrangement, 35 BPM"
        sid = self._source(
            suno_style_prompt=cached,
            suno_style_signature="signature-no-longer-matches",
            suno_preserve_style=True,
            suno_editor_bpm=35,
        )
        with mock.patch.object(suno_jobs, "generate_cover_styles") as generate:
            self._run(sid)
        generate.assert_not_called()
        guarded = FakeDriver.last.prepared_styles
        self.assertTrue(guarded.startswith(cached))
        self.assertIn("continuous dominant lead singing", guarded)
        self.assertIn("no instrumental solos", guarded)
        self.assertFalse(self._get(sid).suno_preserve_style)

    def test_saved_ids_only_download(self):
        sid = self._source(suno_song_ids="aaaa1111-x,bbbb2222-y", suno_status="failed")
        self._run(sid)
        calls = FakeDriver.last.calls
        self.assertNotIn("create", calls)
        self.assertFalse(any(c[0] == "prepare" for c in calls if isinstance(c, tuple)))
        self.assertEqual(self._get(sid).suno_status, "done")
        self.assertEqual(len(self._items()[sid]["covers"]), 2)

    def test_download_failure_keeps_song_ids(self):
        FakeDriver.fail_downloads = True
        sid = self._source()
        self._run(sid)
        src = self._get(sid)
        self.assertEqual(src.suno_status, "failed")
        self.assertEqual(src.suno_song_ids, "aaaa1111-x,bbbb2222-y")   # lần sau chỉ tải
        self.assertIn("không tốn credit", src.suno_error)
        self.master.assert_not_called()                             # không bản nào → không master

    def test_rejected_does_not_halt_queue(self):
        FakeDriver.prepare_exc = suno_cover.SunoCoverRejected("Suno từ chối bài gốc: copyright")
        sid, other = self._source(), self._source(title="B")
        suno_jobs._pending.append(other)
        self._run(sid)
        self.assertEqual(self._get(sid).suno_status, "rejected")
        self.assertEqual(list(suno_jobs._pending), [other])

    def test_copyright_toast_after_create_is_rejected(self):
        FakeDriver.wait_exc = SunoError("Generation failed: uploaded audio matches copyrighted content")
        sid = self._source()
        self._run(sid)
        self.assertEqual(self._get(sid).suno_status, "rejected")

    def test_captcha_halts_queue_and_never_retries_create(self):
        FakeDriver.wait_exc = SunoCaptchaRequired("captcha không được giải")
        sid, other = self._source(), self._source(title="B")
        suno_jobs._pending.append(other)
        self._run(sid)
        self.assertEqual(FakeDriver.last.calls.count("create"), 1)
        self.assertEqual(self._get(sid).suno_status, "failed")
        self.assertEqual(list(suno_jobs._pending), [])
        self.assertEqual(self._get(other).suno_status, "stopped")

    def test_ui_changed_halts_queue(self):
        FakeDriver.prepare_exc = SunoUIChanged("không thấy Audio Influence")
        sid, other = self._source(), self._source(title="B")
        suno_jobs._pending.append(other)
        self._run(sid)
        self.assertEqual(self._get(sid).suno_status, "failed")
        self.assertEqual(self._get(other).suno_status, "stopped")
        self.assertNotIn("create", FakeDriver.last.calls)

    def test_dry_run_never_creates(self):
        sid = self._source()
        self._run(sid, dry=True)
        self.assertTrue(FakeDriver.last.dry_run)
        self.assertNotIn("create", FakeDriver.last.calls)
        src = self._get(sid)
        self.assertEqual(src.suno_status, "tested")
        self.assertEqual(self._items()[sid]["covers"], [])

    def test_missing_original_never_opens_form(self):
        sid = self._source(original=False)
        self._run(sid)
        self.assertEqual(FakeDriver.last.calls, [])
        src = self._get(sid)
        self.assertEqual(src.suno_status, "failed")
        self.assertIn("file bài gốc", src.suno_error)

    def test_missing_lyrics_stops_before_chatgpt_and_suno_form(self):
        sid = self._source(lyrics="")
        with mock.patch.object(suno_jobs, "_transform_lyrics_isolated") as transform:
            self._run(sid)
        transform.assert_not_called()
        self.assertEqual(FakeDriver.last.calls, [])
        src = self._get(sid)
        self.assertEqual(src.suno_status, "failed")
        self.assertIn("chưa có lời", src.suno_error.lower())


# ───────────────────────── driver Cover (trang giả) ─────────────────────────
class FakePage:
    def __init__(self, result=None):
        self.result = result
        self.url = "https://suno.com/create"

    def evaluate(self, js, arg=None):
        return self.result(js, arg) if callable(self.result) else self.result


class DriverTests(unittest.TestCase):
    def _drv(self, page=None):
        return suno_cover.CoverDriver(page or FakePage(), dry_run=True, selectors={})

    def test_editor_tempo_by_genre(self):
        slow = ("lofi", "R&B", "Jazz", "Blue", "Pop", "Ballad")
        for genre in slow:
            with self.subTest(genre=genre):
                self.assertEqual(suno_cover.editor_tempo_for_genre(genre), 32)
        for genre in ("Remix", "Progressive House", "Deep House", "DeepHouse",
                      "Vietmix", "Viet Mix", "Rock", "Pop Rock"):
            with self.subTest(genre=genre):
                self.assertEqual(suno_cover.editor_tempo_for_genre(genre), 35)
        self.assertEqual(suno_cover.editor_tempo_for_genre("Pop House"), 35)
        self.assertEqual(suno_cover.editor_tempo_for_genre("không xác định"), 32)

    def test_create_prefers_real_mouse_click(self):
        drv = suno_cover.CoverDriver(FakePage(), dry_run=False, selectors={})
        button = mock.MagicMock()
        drv._find = mock.MagicMock(return_value=button)
        drv._arm_create_watch = mock.MagicMock()
        drv._real_click = mock.MagicMock(return_value=True)

        drv.click_create()

        drv._arm_create_watch.assert_called_once_with()
        drv._real_click.assert_called_once_with(button)
        button.click.assert_not_called()

    def test_create_falls_back_to_locator_when_button_has_no_box(self):
        drv = suno_cover.CoverDriver(FakePage(), dry_run=False, selectors={})
        button = mock.MagicMock()
        drv._find = mock.MagicMock(return_value=button)
        drv._arm_create_watch = mock.MagicMock()
        drv._real_click = mock.MagicMock(return_value=False)

        drv.click_create()

        button.click.assert_called_once_with()

    def test_editor_loading_falls_back_to_legacy_after_45_seconds(self):
        state = {"ready": False}

        class Body:
            def inner_text(self, timeout=0):
                return "Editor ready" if state["ready"] else "Loading Edit Session..."

        class Page(FakePage):
            def locator(self, selector):
                return Body()

        drv = self._drv(Page())
        drv._wait = mock.MagicMock()
        drv._click = mock.MagicMock(side_effect=lambda _: state.update(ready=True))
        legacy = object()
        with mock.patch.object(suno_cover, "query_first", return_value=legacy), \
             mock.patch.object(suno_cover.time, "time", side_effect=[0, 0, 46, 47]):
            drv._wait_editor_loaded()
        drv._click.assert_called_once_with(legacy)

    def test_deep_house_and_vietmix_override_legacy_ballad_cover_setting(self):
        for genre in ("Deep House", "DeepHouse", "Vietmix DeepHouse"):
            with self.subTest(genre=genre):
                styles = suno_cover.cover_styles_for_project(
                    genre, "", "ballad", "")
                self.assertIn("Deep House cover", styles)
                self.assertIn("four-on-the-floor", styles)
                self.assertNotIn("emotional ballad", styles)

    def test_ballad_style_stays_ballad_without_remix_keyword(self):
        styles = suno_cover.cover_styles_for_project("Ballad", "", "", "")
        self.assertIn("emotional ballad", styles)

    def test_prepare_cover_goes_through_editor_before_title(self):
        drv = self._drv()
        names = (
            "open_create_page", "read_credits", "select_advanced_mode", "clear_form",
            "ensure_more_options", "ensure_duration_auto", "prepare_editor_source",
            "_remix_cover_from_library", "_settle", "select_model", "fill_styles", "fill_title",
            "fill_song_lyrics", "set_vocal_gender", "set_max_mode",
            "set_creative_sliders", "check_rejection", "cover_ready", "save_debug")
        for name in names:
            setattr(drv, name, mock.MagicMock())
        drv.read_credits.return_value = 100
        drv.prepare_editor_source.return_value = "11111111-1111-1111-1111-111111111111"
        drv._settle.return_value = True
        drv.cover_ready.return_value = True
        events = []
        drv.prepare_editor_source.side_effect = lambda *a, **k: (
            events.append("editor") or "11111111-1111-1111-1111-111111111111")
        drv._remix_cover_from_library.side_effect = lambda *a, **k: events.append("remix")
        drv.fill_title.side_effect = lambda *a, **k: events.append("title")

        credits = drv.prepare_cover(Path("adjusted.wav"), "Tên bài", "Câu 1",
                                    "female", 20, editor_bpm=25,
                                    styles="Vietnamese ballad")

        self.assertEqual(credits, 100)
        drv.prepare_editor_source.assert_called_once_with(Path("adjusted.wav"), 25)
        drv._remix_cover_from_library.assert_called_once_with(
            "11111111-1111-1111-1111-111111111111")
        drv.fill_title.assert_called_once_with("Tên bài")
        drv.fill_styles.assert_called_once_with("Vietnamese ballad")
        self.assertEqual(events, ["editor", "remix", "title"])

    def test_upload_row_menu_is_used_when_editor_button_is_not_global(self):
        drv = self._drv()
        drv._open_matching_upload_in_editor = mock.MagicMock(return_value=False)
        drv._pick_file = mock.MagicMock(return_value="ô chọn file ẩn")
        drv.check_rejection = mock.MagicMock()
        drv._editor_control = mock.MagicMock(return_value=None)
        song_id = "22222222-2222-2222-2222-222222222222"
        drv.snapshot_song_ids = mock.MagicMock(return_value={song_id})
        drv._open_editor_from_song = mock.MagicMock()

        drv._open_uploaded_audio_in_editor(Path("tempo.wav"), set())

        drv._open_editor_from_song.assert_called_once_with(song_id)

    def test_existing_upload_row_is_reused_without_uploading_duplicate(self):
        drv = self._drv()
        drv._open_matching_upload_in_editor = mock.MagicMock(return_value=True)
        drv._pick_file = mock.MagicMock()

        drv._open_uploaded_audio_in_editor(Path("tempo.wav"), set())

        drv._open_matching_upload_in_editor.assert_called_once_with(Path("tempo.wav"))
        drv._pick_file.assert_not_called()

    def test_prepare_editor_waits_for_upload_modal_before_tempo(self):
        drv = self._drv()
        order = []
        drv.snapshot_song_ids = mock.MagicMock(side_effect=[set(), set()])
        drv._open_uploaded_audio_in_editor = mock.MagicMock(
            side_effect=lambda *_args: order.append("open"))
        drv._wait_upload_dialog_clear = mock.MagicMock(
            side_effect=lambda *_args: order.append("dialog"))
        drv.set_editor_tempo = mock.MagicMock(
            side_effect=lambda *_args: order.append("tempo"))
        drv.save_editor_as_new_song = mock.MagicMock(return_value="new-song-id")

        with mock.patch.object(Path, "exists", return_value=True):
            got = drv.prepare_editor_source(Path("tempo.wav"), 35)

        self.assertEqual(got, "new-song-id")
        self.assertEqual(order, ["open", "dialog", "tempo"])

    def test_editor_tempo_stepper_changes_91_to_32(self):
        state = {"value": 91, "clicks": 0}

        class Step:
            first = None

            def click(self, timeout=0):
                state["value"] -= 1
                state["clicks"] += 1

        step = Step()
        step.first = step

        class StepperPage(FakePage):
            def evaluate(self, js, arg=None):
                return {"value": state["value"], "down": "-", "up": "+"}

            def locator(self, selector):
                return step

        drv = self._drv(StepperPage())
        # Suno đồng thời render một input number disabled trong portal. Control
        # ``− / BPM / +`` đang hiện phải luôn được ưu tiên và input kia không
        # được đụng tới.
        drv._find_editor_tempo = mock.MagicMock(
            side_effect=AssertionError("không được chọn input portal disabled"))
        drv._wait = mock.MagicMock()

        actual = drv.set_editor_tempo(32)

        self.assertEqual(state, {"value": 32, "clicks": 59})
        self.assertEqual(actual, 32)
        drv._find_editor_tempo.assert_not_called()

    def test_editor_tempo_input_falls_back_when_modal_overlay_intercepts(self):
        state = {"value": "116", "forced": False, "evaluated": False}

        class TempoInput:
            def get_attribute(self, name):
                return {"type": "number", "role": "", "contenteditable": ""}.get(name, "")

            def click(self, timeout=0):
                raise RuntimeError("modal-overlay intercepts pointer events")

            def fill(self, value, force=False):
                state["value"] = value
                state["forced"] = force

            def evaluate(self, _js):
                state["evaluated"] = True

            def input_value(self):
                return state["value"]

        drv = self._drv()
        drv._wait_editor_loaded = mock.MagicMock()
        drv._find_editor_tempo = mock.MagicMock(return_value=TempoInput())
        drv._wait = mock.MagicMock()

        drv.set_editor_tempo(35)

        self.assertEqual(state["value"], "35")
        self.assertTrue(state["forced"])
        self.assertTrue(state["evaluated"])

    def test_editor_tempo_ignores_disabled_portal_input(self):
        disabled = mock.MagicMock()
        disabled.is_enabled.return_value = False
        disabled.get_attribute.side_effect = lambda name: (
            "" if name == "disabled" else None)
        page = FakePage(result=None)
        drv = self._drv(page)
        drv._editor_control = mock.MagicMock(return_value=disabled)

        found = drv._find_editor_tempo()

        self.assertIsNone(found)
        disabled.click.assert_not_called()

    def test_rejection_ignores_terms_dialog(self):
        terms = {"dialogs": ["By uploading you confirm you own the rights to this audio. "
                             "Do not upload copyrighted material."], "toasts": []}
        self.assertEqual(self._drv(FakePage(terms)).rejection_text(), "")
        bad = {"dialogs": [], "toasts": ["This audio matches copyrighted content and can't be used"]}
        self.assertIn("copyrighted", self._drv(FakePage(bad)).rejection_text())
        with mock.patch.object(suno_cover.CoverDriver, "save_debug", return_value=None):
            with self.assertRaises(suno_cover.SunoCoverRejected):
                self._drv(FakePage(bad)).check_rejection()

    def test_sliders_order_and_variety_optional(self):
        drv = self._drv()
        done = []
        with mock.patch.object(drv, "_slider", side_effect=lambda k: None if k == "variety" else object()), \
                mock.patch.object(drv, "set_slider", side_effect=lambda k, v: done.append((k, v)) or v):
            out = drv.set_creative_sliders(suno_cover.COVER_SLIDERS)
        self.assertEqual(done, [("weirdness", 10), ("style_influence", 75), ("audio_influence", 50)])
        self.assertEqual(out, {"weirdness": 10, "style_influence": 75, "audio_influence": 50})

    def test_lyrics_too_long(self):
        with self.assertRaises(SunoError):
            self._drv().fill_song_lyrics("a" * (suno_cover.LYRICS_LIMIT + 1))
        with self.assertRaises(SunoError):
            self._drv().fill_song_lyrics("  \n ")

    def test_vocal_gender_already_selected_is_not_clicked(self):
        drv = self._drv(FakePage({"Male": False, "Female": True}))
        with mock.patch.object(drv, "_click") as click:
            drv.set_vocal_gender("female")
        click.assert_not_called()

    def test_vocal_gender_row_missing_is_skipped(self):
        drv = self._drv(FakePage(None))
        with mock.patch.object(drv, "ensure_more_options"), mock.patch.object(drv, "_click") as click:
            drv.set_vocal_gender("male")
        click.assert_not_called()

    def test_vocal_gender_hidden_state_clicks_once_and_continues(self):
        page = mock.MagicMock()
        page.evaluate.return_value = {
            "Male": False, "Female": False, "verifiable": False,
            "desiredDisabled": False,
        }
        drv = self._drv(page)
        with mock.patch.object(drv, "_click") as click, \
                mock.patch.object(drv, "_wait"):
            drv.set_vocal_gender("female")
        click.assert_called_once()
        # 1 lần kiểm tra More Options + trạng thái trước/sau khi bấm.
        self.assertEqual(page.evaluate.call_count, 3)


class MigrationTests(unittest.TestCase):
    def test_m032_adds_custom_editor_bpm(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_editor_bpm()
                migrations.migrate_add_sourcesong_editor_bpm()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            value = conn.execute("SELECT suno_editor_bpm FROM sourcesong").fetchone()[0]
            conn.close()
        self.assertIn("suno_editor_bpm", cols)
        self.assertEqual(0, value)

    def test_m033_adds_preserve_style_flag(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_preserve_style()
                migrations.migrate_add_sourcesong_preserve_style()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            value = conn.execute(
                "SELECT suno_preserve_style FROM sourcesong").fetchone()[0]
            conn.close()
        self.assertIn("suno_preserve_style", cols)
        self.assertEqual(0, value)

    def test_m020_adds_columns(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY, suno_status TEXT)")
            conn.execute("INSERT INTO sourcesong (suno_status) VALUES ('redo')")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_suno_fields()
                migrations.migrate_add_sourcesong_suno_fields()     # chạy lại không lỗi
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            row = conn.execute("SELECT suno_song_ids, vocal_gender FROM sourcesong").fetchone()
            conn.close()
        self.assertTrue({"suno_error", "suno_song_ids", "vocal_gender"} <= set(cols))
        self.assertEqual(row, ("", ""))

    def test_m024_adds_tempo_columns(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_tempo_fields()
                migrations.migrate_add_sourcesong_tempo_fields()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            row = conn.execute("SELECT tempo_factor, tempo_file_path FROM sourcesong").fetchone()
            conn.close()
        self.assertTrue({"tempo_factor", "tempo_file_path"} <= set(cols))
        self.assertEqual(row, (1.0, ""))

    def test_m025_adds_editor_song_id(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_editor_song_id()
                migrations.migrate_add_sourcesong_editor_song_id()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            value = conn.execute(
                "SELECT suno_editor_song_id FROM sourcesong").fetchone()[0]
            conn.close()
        self.assertIn("suno_editor_song_id", cols)
        self.assertEqual(value, "")

    def test_m026_adds_suno_lyrics(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_suno_lyrics()
                migrations.migrate_add_sourcesong_suno_lyrics()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            value = conn.execute(
                "SELECT lyrics_suno_text FROM sourcesong").fetchone()[0]
            conn.close()
        self.assertIn("lyrics_suno_text", cols)
        self.assertEqual(value, "")

    def test_m027_adds_suno_style_prompt_cache(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_suno_style_prompt()
                migrations.migrate_add_sourcesong_suno_style_prompt()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            row = conn.execute(
                "SELECT suno_style_prompt, suno_style_signature FROM sourcesong"
            ).fetchone()
            conn.close()
        self.assertTrue({"suno_style_prompt", "suno_style_signature"} <= set(cols))
        self.assertEqual(row, ("", ""))

    def test_m028_adds_featured_instrument(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE sourcesong (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO sourcesong DEFAULT VALUES")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_sourcesong_featured_instrument()
                migrations.migrate_add_sourcesong_featured_instrument()
            conn = sqlite3.connect(db)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sourcesong)")]
            value = conn.execute(
                "SELECT featured_instrument FROM sourcesong").fetchone()[0]
            conn.close()
        self.assertIn("featured_instrument", cols)
        self.assertEqual(value, "")


if __name__ == "__main__":
    unittest.main()


class SelectiveRestoreTests(_Base):
    """Bản cover đã xác nhận rồi xoá: người dùng tự chọn bản nào khôi phục."""

    def test_restore_only_the_picked_covers(self):
        sid = self._source()
        ids = [self._add_cover(sid, f"cover {i}.wav") for i in (1, 2, 3)]
        for tid in ids:
            r = self.client.delete(f"/api/projects/{self.pid}/tracks/{tid}")
            self.assertEqual(r.status_code, 200, r.text)
        info = self.client.get(f"/api/projects/{self.pid}/tracks/recovery").json()
        self.assertEqual(3, info["trash_count"])
        by_name = {it["filename"]: it["id"] for it in info["items"]}
        pick = by_name["Bài A - cover 2.wav"]
        audio = self.client.get(f"/api/projects/{self.pid}/tracks/recovery/{pick}/audio")
        self.assertEqual(audio.status_code, 200)
        r = self.client.post(f"/api/projects/{self.pid}/tracks/recovery/restore",
                             json={"trash_ids": [pick], "orphan_files": []})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(1, r.json()["total"])
        tracks = self.client.get(f"/api/projects/{self.pid}/tracks").json()
        self.assertEqual(["Bài A - cover 2.wav"], [t["filename"] for t in tracks])
        left = self.client.get(f"/api/projects/{self.pid}/tracks/recovery").json()
        self.assertEqual({"Bài A - cover.wav", "Bài A - cover 3.wav"},
                         {it["filename"] for it in left["items"]})

    def test_empty_selection_is_rejected(self):
        r = self.client.post(f"/api/projects/{self.pid}/tracks/recovery/restore",
                             json={"trash_ids": [], "orphan_files": []})
        self.assertEqual(r.status_code, 400)
