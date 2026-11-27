"""Track lẻ (mỗi bài 1 project) + chia thư mục media Mix Set / Track lẻ."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select

from backend import batch_service
from backend.models import BatchRun, Project, SourceSong, Track
from backend.video import config as vconfig


class NoStartThread:
    def __init__(self, *args, **kwargs): pass
    def start(self): pass
    def is_alive(self): return False


class _Db:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'singles.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        return self

    def __exit__(self, *exc):
        self.engine.dispose()
        self.tmp.cleanup()


class CreateSinglesTests(unittest.TestCase):
    def test_one_project_per_song_marked_single(self):
        with _Db() as db, patch.object(batch_service, "engine", db.engine), \
                patch.object(batch_service.threading, "Thread", NoStartThread):
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si", "Bai Hai - Ca Si", "Bai Mot - Ca Si"],
                music_style="Ballad", video_style="real")
            batch_service._threads.pop(result["batch_key"], None)
            batch_service._cancel_flags.pop(result["batch_key"], None)
            self.assertEqual(2, result["total"])
            # Các bài vừa tạo ở trạng thái queued (chưa chạy tải NCT) không bị liệt kê nhầm là thiếu lời.
            self.assertEqual(0, len(result["missing_lyrics"]))
            with Session(db.engine) as session:
                projects = session.exec(select(Project).order_by(Project.id)).all()
                self.assertEqual(["Bai Mot - Ca Si", "Bai Hai - Ca Si"],
                                 [p.name for p in projects])
                self.assertEqual({"single"}, {p.kind for p in projects})
                for p in projects:
                    songs = session.exec(select(SourceSong).where(
                        SourceSong.project_id == p.id)).all()
                    self.assertEqual([p.name], [s.query for s in songs])

    def test_rejects_bad_lines(self):
        with self.assertRaisesRegex(RuntimeError, "Tên bài - Ca sĩ"):
            batch_service.create_cover_singles(
                song_lines=["Khong co ca si"], music_style="Ballad", video_style="real")


class RunSinglesTests(unittest.TestCase):
    def _batch(self, db, n=3):
        with Session(db.engine) as session:
            ids = []
            for i in range(n):
                p = Project(name=f"Bai {i} - Ca Si", description="", batch_id="k",
                            kind="single")
                session.add(p)
                session.flush()
                session.add(SourceSong(project_id=p.id, position=1, query=p.name,
                                       lyrics_text="loi"))
                ids.append(p.id)
            session.add(BatchRun(batch_key="k", total=n, status="running",
                                 params_json='{"kind": "cover_singles"}'))
            session.commit()
        batch_service._cancel_flags["k"] = threading.Event()
        return ids

    def _run(self, db, chain):
        with patch.object(batch_service, "engine", db.engine), \
                patch.object(batch_service, "_cover_chain", chain), \
                patch.object(batch_service, "_verify_product", return_value=(False, "")), \
                patch.object(batch_service, "_wait_until_idle", return_value=True), \
                patch.object(batch_service, "_schedule_auto_skip"):
            batch_service._run_cover_singles("k")
            with Session(db.engine) as session:
                return session.exec(select(BatchRun)).one()

    def test_song_error_skips_to_next(self):
        with _Db() as db:
            ids = self._batch(db)
            seen = []

            def chain(_key, pid, _src, _ev, _prefix):
                seen.append(pid)
                if pid == ids[1]:
                    raise RuntimeError("không tải được")
            run = self._run(db, chain)
        self.assertEqual(ids, seen)
        self.assertEqual(("completed", 2, 1), (run.status, run.completed, run.failed))
        self.assertIn("2/3 bài xong", run.message)

    def test_suno_block_stops_whole_batch(self):
        with _Db() as db:
            ids = self._batch(db)
            seen = []

            def chain(_key, pid, _src, _ev, _prefix):
                seen.append(pid)
                raise batch_service._StopAll("Suno hết credit")
            run = self._run(db, chain)
        self.assertEqual([ids[0]], seen)
        self.assertEqual("blocked", run.status)
        self.assertIn("Suno hết credit", run.message)

    def test_missing_lyrics_waits_but_others_continue(self):
        with _Db() as db:
            ids = self._batch(db)

            def chain(_key, pid, _src, _ev, _prefix):
                if pid == ids[0]:
                    raise batch_service._MissingLyricsWait("thiếu lời")
            run = self._run(db, chain)
        self.assertEqual(("blocked", 2), (run.status, run.completed))
        self.assertIn("CHỜ BỔ SUNG LYRICS cho 1 bài", run.message)


class MediaGroupTests(unittest.TestCase):
    def test_new_folders_go_to_group_old_ones_stay(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(root / "Track lẻ" / "A (#1)",
                             vconfig.project_dir(1, "A", kind="single", root=root))
            self.assertEqual(root / "Mix Set" / "B (#2)",
                             vconfig.project_dir(2, "B", kind="mixset", root=root))
            (root / "C (#3)").mkdir()           # project cũ nằm thẳng trong media/
            self.assertEqual(root / "C (#3)",
                             vconfig.project_dir(3, "C", kind="single", root=root))

    def test_cleanup_owns_grouped_folder(self):
        from backend.project_cleanup import CleanupRoots, owned_paths
        with tempfile.TemporaryDirectory() as d:
            roots = CleanupRoots(Path(d))
            folder = roots.media / "Track lẻ" / "Ten Cu (#7)"
            folder.mkdir(parents=True)
            (roots.media / "Track lẻ" / "Khac (#70)").mkdir()
            paths = [p for _r, p in owned_paths(7, "Ten Moi", roots)]
        self.assertEqual([folder], paths)

    def test_change_kind_moves_folder_and_db_paths(self):
        from backend.project_rename import change_kind
        with _Db() as db, tempfile.TemporaryDirectory() as media:
            media = Path(media)
            old = media / "Bai (#1)"
            (old / "ban_cover").mkdir(parents=True)
            (old / "ban_cover" / "a.wav").write_bytes(b"x")
            with Session(db.engine) as session:
                p = Project(name="Bai", description="")
                session.add(p)
                session.flush()
                session.add(Track(project_id=p.id, filename="a.wav",
                                  filepath=str(old / "ban_cover" / "a.wav"),
                                  duration_seconds=1.0, sample_rate=48000, channels=2,
                                  format="WAV", is_lossy=False))
                session.commit()
                with patch("backend.project_cleanup._guard_idle") as guard:
                    guard.return_value.__enter__.return_value = None
                    out = change_kind(session, p, "single", media_root=media)
                track = session.exec(select(Track)).one()
                new = media / "Track lẻ" / "Bai (#1)"
                self.assertTrue(out["moved"])
                self.assertEqual("single", p.kind)
                self.assertFalse(old.exists())
                self.assertTrue((new / "ban_cover" / "a.wav").is_file())
                self.assertEqual(str(new / "ban_cover" / "a.wav"), track.filepath)


if __name__ == "__main__":
    unittest.main()


class FirstCoverAudioTests(unittest.TestCase):
    """Track lẻ giữ cả 2 bản Suno; video luôn dùng bản 1 (vị trí nhỏ nhất)."""

    def test_picks_version_one_even_if_version_two_is_newer(self):
        from backend.models import CoverSong
        with _Db() as db:
            v1, v2 = db.root / "bai - cover.wav", db.root / "bai - cover 2.wav"
            v1.write_bytes(b"1")
            v2.write_bytes(b"2")
            with Session(db.engine) as s:
                p = Project(name="Bai", kind="single")
                s.add(p)
                s.commit()
                src = SourceSong(project_id=p.id, position=1, query="Bai")
                s.add(src)
                s.commit()
                for pos, f in ((2, v2), (1, v1)):
                    t = Track(project_id=p.id, filename=f.name, filepath=str(f),
                              duration_seconds=200, sample_rate=48000, channels=2,
                              format="WAV", is_lossy=False, subtype="PCM_24")
                    s.add(t)
                    s.commit()
                    s.add(CoverSong(project_id=p.id, track_id=t.id, position=pos,
                                    title="Bai", source_id=src.id))
                s.commit()
                sid = src.id
            with patch.object(batch_service, "engine", db.engine):
                self.assertEqual(batch_service._first_cover_audio([sid]), str(v1))
                v1.unlink()
                self.assertEqual(batch_service._first_cover_audio([sid]), str(v2))
