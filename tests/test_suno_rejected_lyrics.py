"""Suno từ chối lyrics (LIVE 2026-11-09, #149): không được Create lại với đúng
lyrics cũ. Phải dán lyrics khác (người dùng xác nhận tự sáng tác/được phép) thì
bài mới hết bị khoá. Không mở trình duyệt, không gọi Suno."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

OLD = "Câu một của bài\nCâu hai của bài"


class RejectedLyricsApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import Project, SourceSong

        tmp = TemporaryDirectory(prefix="rejected-lyrics-test-")
        self.addCleanup(tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(tmp.name) / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as session:
            project = Project(name="Rejected Test")
            session.add(project)
            session.commit()
            src = SourceSong(project_id=project.id, title="Bài A", artist="Ca sĩ A",
                             lyrics_text=OLD, lyrics_suno_text=OLD, status="done",
                             suno_status="rejected", suno_error="Suno gỡ cả 2 bản (lyrics)")
            session.add(src)
            session.commit()
            self.sid = src.id

        def session_override():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.addCleanup(app.dependency_overrides.clear)
        from backend.routers import sources
        for name, value in (("_suno_missing", lambda s: ""),):
            p = mock.patch.object(sources, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(sources.suno_jobs, "submit", return_value=1)
        self.submit = p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)

    def _src(self):
        from sqlmodel import Session
        from backend.models import SourceSong
        with Session(self.engine) as session:
            return session.get(SourceSong, self.sid)

    def _put(self, lyrics, authorized=True):
        return self.client.put(f"/api/sources/{self.sid}",
                               json={"lyrics_text": lyrics, "authorized_lyrics": authorized})

    def test_redo_with_old_lyrics_is_refused(self):
        r = self.client.post(f"/api/sources/{self.sid}/suno", json={"fresh": True})
        self.assertEqual(r.status_code, 409)
        self.assertIn("lyrics", r.json()["detail"])
        self.submit.assert_not_called()
        self.assertEqual(self._src().suno_status, "rejected")

    def test_dry_run_is_refused_too(self):
        r = self.client.post(f"/api/sources/{self.sid}/suno", json={"dry_run": True})
        self.assertEqual(r.status_code, 409)
        self.submit.assert_not_called()

    def test_redo_button_with_confirmation_is_queued(self):
        # Nút «↻ Làm lại trên Suno»: người dùng xác nhận lyrics tự sáng tác/được phép.
        r = self.client.post(f"/api/sources/{self.sid}/suno",
                             json={"fresh": True, "authorized_lyrics": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.submit.assert_called_once_with([self.sid], dry_run=False)
        self.assertEqual(self._src().suno_status, "")
        self.assertEqual(self._src().lyrics_text, OLD)       # tool không sửa lyrics

    def test_same_lyrics_reformatted_is_refused(self):
        for same in (OLD, "CÂU MỘT, của bài!\n\n  câu hai của   bài.",
                     "[Verse]\nCâu một của bài\nCâu hai của bài"):
            r = self._put(same)
            self.assertEqual(r.status_code, 400, same)
            self.assertIn("giống hệt", r.json()["detail"])
        self.assertEqual(self._src().suno_status, "rejected")

    def test_new_lyrics_need_authorization(self):
        r = self._put("Lời mới tôi tự viết\nCâu thứ hai", authorized=False)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._src().suno_status, "rejected")
        self.assertEqual(self._src().lyrics_text, OLD)

    def test_new_authorized_lyrics_unlock_redo(self):
        r = self._put("Lời mới tôi tự viết\nCâu thứ hai")
        self.assertEqual(r.status_code, 200, r.text)
        src = self._src()
        self.assertEqual(src.suno_status, "")
        self.assertEqual(src.lyrics_text, "Lời mới tôi tự viết\nCâu thứ hai")
        self.assertEqual(src.lyrics_suno_text, "")          # bước chuẩn hoá chạy lại
        r = self.client.post(f"/api/sources/{self.sid}/suno", json={"fresh": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.submit.assert_called_once_with([self.sid], dry_run=False)

    def test_title_edit_does_not_unlock(self):
        r = self.client.put(f"/api/sources/{self.sid}", json={"title": "Bài A mới"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._src().suno_status, "rejected")


class SubmitSkipsRejectedTests(unittest.TestCase):
    def setUp(self):
        from sqlmodel import Session, SQLModel, create_engine
        from backend.cover import suno_jobs
        from backend.models import Project, SourceSong
        tmp = TemporaryDirectory(prefix="rejected-submit-test-")
        self.addCleanup(tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(tmp.name) / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as session:
            project = Project(name="P")
            session.add(project)
            session.commit()
            src = SourceSong(project_id=project.id, title="X", lyrics_text=OLD,
                             status="done", suno_status="rejected")
            session.add(src)
            session.commit()
            self.sid = src.id
        self.jobs = suno_jobs
        p = mock.patch.object(suno_jobs, "engine", self.engine)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(suno_jobs, "_executor")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self._reset)

    def _reset(self):
        with self.jobs._lock:
            self.jobs._pending.clear()
            self.jobs._manual_watch.discard(self.sid)
            self.jobs._state["draining"] = False

    def test_rejected_song_is_never_queued_for_create(self):
        self.assertEqual(self.jobs.submit([self.sid]), 0)
        self.assertNotIn(self.sid, self.jobs._pending)

    def test_manual_watch_still_allowed(self):
        self.assertEqual(self.jobs.submit_manual_watch(self.sid), 1)
        self.assertIn(self.sid, self.jobs._pending)


class LyricsKeyTests(unittest.TestCase):
    def test_key(self):
        from backend.routers.sources import lyrics_key
        self.assertEqual(lyrics_key("[Chorus]\nAnh  YÊU em!"), "anh yêu em")
        self.assertNotEqual(lyrics_key("Anh yêu em"), lyrics_key("Anh thương em"))
        self.assertEqual(lyrics_key(""), "")


if __name__ == "__main__":
    unittest.main()
