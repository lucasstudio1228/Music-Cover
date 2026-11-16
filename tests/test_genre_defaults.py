"""Cài đặt video cover tự theo thể loại project (ô trống = theo thể loại)."""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.cover import genre_defaults as g


class GenreTests(unittest.TestCase):
    def test_style_from_genre(self):
        for genre, style in (("Deep House", "remix"), ("Mix Việt", "remix"),
                             ("Tropical House", "remix"), ("Ballad", "ballad"),
                             ("R&B", "ballad"), ("Lofi", "ballad"), ("Pop", "original"),
                             ("Rock", "original"), ("Acoustic", "acoustic")):
            self.assertEqual(g.genre_defaults(genre)["cover_style"], style, genre)

    def test_music_style_wins_over_name_then_falls_back(self):
        # tên có «Ballad» nhưng thể loại R&B → vẫn ballad; Deep House → remix
        self.assertEqual(g.genre_defaults("Deep House", name="Ballad mùa thu")["cover_style"],
                         "remix")
        self.assertEqual(g.genre_defaults("", name="Vietmix Deep Chill")["cover_style"], "remix")
        self.assertEqual(g.genre_defaults("")["cover_style"], "ballad")

    def test_language_from_music_line(self):
        self.assertEqual(g.genre_defaults("Pop", "US-UK")["language"], "en")
        for line in ("VN", "", "Chinese"):
            self.assertEqual(g.genre_defaults("Pop", line)["language"], "vi")

    def test_resolve_auto_vs_manual(self):
        proj = {"music_style": "Deep House", "music_line": "VN"}
        auto = g.resolve({"language": "", "cover_style": "", "thumb_subtitle": ""}, proj)
        self.assertEqual((auto["language"], auto["cover_style"]), ("vi", "remix"))
        self.assertEqual(auto["thumb_subtitle"], "Nhạc Deep House Cover Cực Cuốn")
        self.assertTrue(all(auto["auto"].values()))
        manual = g.resolve({"language": "en", "cover_style": "ballad",
                            "thumb_subtitle": "Chữ riêng"}, proj)
        self.assertEqual((manual["language"], manual["cover_style"], manual["thumb_subtitle"]),
                         ("en", "ballad", "Chữ riêng"))
        self.assertFalse(any(manual["auto"].values()))
        self.assertEqual(manual["suggested"]["cover_style"], "remix")


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = self.tmp / "app.db"
        c = sqlite3.connect(self.db)
        c.executescript("""
            CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT, description TEXT,
                                  music_style TEXT, music_line TEXT);
            CREATE TABLE coversettings (id INTEGER PRIMARY KEY, project_id INTEGER,
                language TEXT, cover_style TEXT, thumb_subtitle TEXT);
            INSERT INTO project VALUES (1, 'Vietmix', '', 'Deep House', 'VN'),
                                       (2, 'Test', '', '', ''),
                                       (3, 'Rock', '', 'Rock', 'US-UK');
            INSERT INTO coversettings VALUES (1, 1, 'vi', 'ballad', ''),
                                             (2, 2, 'en', 'ballad', ''),
                                             (3, 3, 'en', 'acoustic', '');
        """)
        c.commit()
        c.close()

    def test_migration_moves_old_defaults_to_auto_once(self):
        from backend import migrations as m
        with mock.patch.object(m, "DB_PATH", self.db):
            m.migrate_cover_settings_follow_genre()
            c = sqlite3.connect(self.db)
            rows = c.execute("SELECT project_id, language, cover_style FROM coversettings "
                             "ORDER BY project_id").fetchall()
            # 1: mặc định cũ → theo thể loại; 2: 'en' tự chọn (không phải US-UK) giữ;
            # 3: 'en' trùng gợi ý US-UK → tự; 'acoustic' tự chọn → giữ
            self.assertEqual(rows, [(1, "", ""), (2, "en", ""), (3, "", "acoustic")])
            c.execute("UPDATE coversettings SET cover_style = 'ballad' WHERE project_id = 1")
            c.commit()
            c.close()
            m.migrate_cover_settings_follow_genre()      # chỉ chạy 1 lần
        c = sqlite3.connect(self.db)
        self.assertEqual(c.execute("SELECT cover_style FROM coversettings WHERE "
                                   "project_id = 1").fetchone()[0], "ballad")
        c.close()

    def test_branding_and_overlay_use_genre(self):
        from backend.cover import branding
        c = sqlite3.connect(self.db)
        c.execute("UPDATE coversettings SET language = '', cover_style = ''")
        c.commit()
        c.close()
        with mock.patch.object(branding, "DB_PATH", self.db):
            self.assertEqual(branding.project_cover(1)["cover_style"], "remix")
            self.assertEqual(branding.cover_subtitle(1), "Nhạc Deep House Cover Cực Cuốn")
            self.assertEqual(branding.project_cover(3)["language"], "en")
            self.assertEqual(branding.project_cover(99)["cover_style"], "ballad")


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import Project
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.engine = create_engine(f"sqlite:///{self.tmp / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as s:
            p = Project(name="Vietmix", music_style="Deep House", music_line="VN")
            s.add(p)
            s.commit()
            self.pid = p.id

        def _session():
            with Session(self.engine) as s:
                yield s
        app.dependency_overrides[get_session] = _session
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.url = f"/api/cover/projects/{self.pid}/settings"

    def test_new_project_follows_genre(self):
        d = self.client.get(self.url).json()
        self.assertEqual((d["language"], d["cover_style"]), ("", ""))
        self.assertEqual((d["effective"]["language"], d["effective"]["cover_style"]),
                         ("vi", "remix"))

    def test_manual_then_back_to_genre(self):
        d = self.client.put(self.url, json={"cover_style": "ballad"}).json()
        self.assertEqual(d["effective"]["cover_style"], "ballad")
        self.assertFalse(d["effective"]["auto"]["cover_style"])
        d = self.client.put(self.url, json={"cover_style": "", "language": ""}).json()
        self.assertEqual(d["effective"]["cover_style"], "remix")
        self.assertEqual(self.client.put(self.url, json={"cover_style": "xyz"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
