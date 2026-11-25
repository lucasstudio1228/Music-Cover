"""Settings → Kênh YouTube: ô «dòng nhạc» (VN / US-UK / Chinese…) thay cho nhạc cụ."""
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))


class _ApiBase(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        tmp = TemporaryDirectory(prefix="music-line-test-")
        self.addCleanup(tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(tmp.name) / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)

        def _session():
            with Session(self.engine) as s:
                yield s
        app.dependency_overrides[get_session] = _session
        self.addCleanup(app.dependency_overrides.clear)
        p = mock.patch("backend.video.channel_looks.ensure_channel_looks")
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)


class MusicLineApiTests(_ApiBase):
    def test_create_and_update_keep_old_instrument(self):
        from sqlmodel import Session
        from backend.models import ChannelMapping
        r = self.client.post("/api/youtube/mappings", json={
            "music_line": "US-UK", "music_style": "Ballad", "gpm_profile_id": "p1",
            "channel_name": "", "visual_look": "painterly"})
        self.assertEqual(r.status_code, 200, r.text)        # dòng nhạc đủ để nhận ra kênh
        self.assertEqual(r.json()["music_line"], "US-UK")
        mid = r.json()["id"]
        with Session(self.engine) as s:                     # kênh cũ có nhạc cụ
            m = s.get(ChannelMapping, mid)
            m.instrument = "Piano"
            s.add(m)
            s.commit()
        r = self.client.patch(f"/api/youtube/mappings/{mid}", json={
            "music_line": "Chinese", "music_style": "Ballad", "gpm_profile_id": "p1",
            "channel_name": "Kênh Hoa"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["music_line"], r.json()["instrument"]), ("Chinese", "Piano"))

    def test_needs_name_or_music_line(self):
        r = self.client.post("/api/youtube/mappings", json={"gpm_profile_id": "p1"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("dòng nhạc", r.json()["detail"])


def _row(id_, line="", style="", ins=""):
    return {"id": id_, "music_line": line, "music_style": style, "instrument": ins}


class MatchChannelTests(unittest.TestCase):
    """Project chưa chọn kênh: tự chọn theo dòng nhạc + thể loại."""

    def match(self, rows, style, line="", ins=""):
        from backend.video.service import match_channel
        m = match_channel(rows, ins, style, line)
        return m and m["id"]

    def test_tiers(self):
        rows = [_row(1, "VN", "Pop"), _row(2, "VN", ""), _row(3, "", "Ballad"),
                _row(4, "US-UK", "Ballad")]
        self.assertEqual(self.match(rows + [_row(5, "vn ", "ballad")], "Ballad", "VN"), 5)
        self.assertEqual(self.match(rows, "Ballad", "VN"), 2)      # kênh VN chưa ghi thể loại
        self.assertEqual(self.match(rows[:1] + rows[2:], "Ballad", "VN"), 1)  # cùng dòng nhạc
        self.assertEqual(self.match(rows, "Ballad", "Chinese"), 3)  # kênh chưa ghi dòng nhạc
        self.assertIsNone(self.match(rows[:2] + rows[3:], "Ballad", "Chinese"))
        self.assertEqual(self.match(rows, "", "US-UK"), 4)         # chưa chọn thể loại
        self.assertIsNone(self.match(rows, "", ""))

    def test_no_line_matches_style_only(self):
        rows = [_row(1, "VN", "Ballad"), _row(2, "US-UK", "Ballad"), _row(3, "", "Pop")]
        self.assertEqual(self.match(rows, "Ballad"), 2)            # dòng mới nhất thắng
        self.assertEqual(self.match(rows, "pop"), 3)

    def test_old_tool_instrument_unchanged(self):
        rows = [_row(1, "", "Lofi", "Piano"), _row(2, "VN", "Lofi", "")]
        self.assertEqual(self.match(rows, "Lofi", ins="piano"), 1)
        self.assertIsNone(self.match(rows, "", "VN", ins="piano"))


class ChannelForTests(unittest.TestCase):
    """Bước đăng nháp tìm đúng kênh tự chọn dù project không có nhạc cụ."""

    def setUp(self):
        from sqlmodel import Session, SQLModel, create_engine
        from backend.models import ChannelMapping, Project
        tmp = TemporaryDirectory(prefix="channel-for-test-")
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "app.db"
        engine = create_engine(f"sqlite:///{db}")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(ChannelMapping(gpm_profile_id="p-vn", channel_name="Kênh VN",
                                 music_line="VN", music_style=""))
            s.add(ChannelMapping(gpm_profile_id="p-us", channel_name="Kênh US",
                                 music_line="US-UK", music_style="Ballad"))
            s.add(Project(name="A", music_line="VN", music_style="Ballad"))
            s.commit()
        engine.dispose()
        p = mock.patch("backend.database.DB_PATH", db)
        p.start()
        self.addCleanup(p.stop)

    def test_channel_for_without_instrument(self):
        from backend.video import service
        self.assertEqual(service.channel_for(None, "", "Ballad", "VN")["gpm_profile_id"], "p-vn")
        self.assertEqual(service.channel_for(None, "", "Ballad")["gpm_profile_id"], "p-us")
        self.assertIsNone(service.channel_for(None, "", ""))
        self.assertEqual(service.channel_for_project(1)["gpm_profile_id"], "p-vn")

    def test_no_channel_error_mentions_line(self):
        from backend.video import service
        msg = service._no_channel_error("", "Rock", music_line="Japanese")
        self.assertIn("dòng nhạc 'Japanese' + thể loại 'Rock'", msg)


class ProjectMusicLineApiTests(_ApiBase):
    def test_create_project_auto_picks_channel_by_line(self):
        from sqlmodel import Session
        from backend.models import ChannelMapping
        with Session(self.engine) as s:
            s.add(ChannelMapping(gpm_profile_id="p-us", channel_name="Kênh US",
                                 music_line="US-UK", music_style="Ballad"))
            s.add(ChannelMapping(gpm_profile_id="p-cn", channel_name="Kênh Hoa",
                                 music_line="Chinese", music_style=""))
            s.commit()
        with mock.patch("backend.routers.projects._ideas_to_english", side_effect=lambda v: v):
            r = self.client.post("/api/projects", json={
                "name": "Cover thử", "music_style": "Ballad", "music_line": " Chinese "})
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertEqual((body["music_line"], body["effective_channel_name"]),
                             ("Chinese", "Kênh Hoa"))
            r = self.client.patch(f"/api/projects/{body['id']}", json={"music_line": "US-UK"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["effective_channel_name"], "Kênh US")


class MigrationTests(unittest.TestCase):
    def test_m022_adds_project_music_line(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO project (name) VALUES ('A')")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_project_music_line()
                migrations.migrate_add_project_music_line()
            conn = sqlite3.connect(db)
            row = conn.execute("SELECT name, music_line FROM project").fetchone()
            conn.close()
        self.assertEqual(row, ("A", ""))

    def test_m021_adds_music_line(self):
        from backend import migrations
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE channelmapping (id INTEGER PRIMARY KEY, instrument TEXT)")
            conn.execute("INSERT INTO channelmapping (instrument) VALUES ('Piano')")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_channelmapping_music_line()
                migrations.migrate_add_channelmapping_music_line()   # chạy lại không lỗi
            conn = sqlite3.connect(db)
            row = conn.execute("SELECT instrument, music_line FROM channelmapping").fetchone()
            conn.close()
        self.assertEqual(row, ("Piano", ""))


if __name__ == "__main__":
    unittest.main()
