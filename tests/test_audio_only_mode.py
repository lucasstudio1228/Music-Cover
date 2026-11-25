"""Chạy auto 2 kiểu (Audio + Video / Chỉ audio) + nút mở thư mục audio/video."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from backend import batch_service
from backend.models import BatchRun, Project
from backend.routers import projects as projects_router
from backend.video import config as vconfig


class NoStartThread:
    def __init__(self, *args, **kwargs): pass
    def start(self): pass
    def is_alive(self): return False


class _Env:
    """DB sqlite tạm + MEDIA_ROOT tạm (không đụng dữ liệu thật)."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.engine = create_engine(f"sqlite:///{self.root / 'a.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self._patches = [
            patch.object(batch_service, "engine", self.engine),
            patch.object(batch_service.threading, "Thread", NoStartThread),
            patch.object(vconfig, "MEDIA_ROOT", self.media),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        self.engine.dispose()
        self.tmp.cleanup()


def _drop_threads(result):
    batch_service._threads.pop(result["batch_key"], None)
    batch_service._cancel_flags.pop(result["batch_key"], None)


class AudioOnlyBatchTests(unittest.TestCase):
    def test_singles_audio_only_saved_and_video_flags_off(self):
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                run = s.exec(select(BatchRun)).one()
                proj = s.exec(select(Project)).one()
                self.assertTrue(json.loads(run.params_json)["audio_only"])
                self.assertFalse(proj.auto_video)
                self.assertFalse(proj.auto_upload)
                pid = proj.id
            self.assertTrue(batch_service._is_audio_only(pid))

    def test_default_is_audio_plus_video(self):
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad", video_style="real")
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                self.assertTrue(proj.auto_video)
                pid = proj.id
            self.assertFalse(batch_service._is_audio_only(pid))

    def test_single_audio_only_done_when_mastered_file_exists(self):
        from backend.cover.nct_jobs import cover_dir
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                pid, name = proj.id, proj.name
            ok, _ = batch_service._verify_product(pid)
            self.assertFalse(ok)
            mastered = cover_dir(pid, name) / "mastered"
            mastered.mkdir(parents=True)
            (mastered / "Bai Mot - cover_master.wav").write_bytes(b"x")
            ok, _ = batch_service._verify_product(pid)
            self.assertTrue(ok)      # không đòi final.mp4 / nháp YouTube
            self.assertEqual(batch_service.audio_folder(pid), mastered)

    def test_mixset_audio_only_needs_the_mix(self):
        from backend.cover.mix_export import MIX_AUDIO_DIR
        from backend.cover.nct_jobs import cover_dir
        with _Env() as env:
            result = batch_service.create_cover_mixset(
                name="Set Thu", song_lines=["Bai Mot - Ca Si", "Bai Hai - Ca Si"],
                music_style="Ballad", video_style="real", audio_only=True)
            _drop_threads(result)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                pid, name = proj.id, proj.name
                self.assertFalse(proj.auto_video)
            mastered = cover_dir(pid, name) / "mastered"
            mastered.mkdir(parents=True)
            (mastered / "a_master.wav").write_bytes(b"x")
            ok, detail = batch_service._verify_product(pid)
            self.assertFalse(ok)
            self.assertIn("mix", detail)
            mix_dir = vconfig.project_dir(pid, name) / MIX_AUDIO_DIR
            mix_dir.mkdir(parents=True)
            (mix_dir / "Set Thu.wav").write_bytes(b"x")
            self.assertTrue(batch_service._verify_product(pid)[0])
            self.assertEqual(batch_service.audio_folder(pid), mix_dir)

    def test_set_audio_only_switches_mode_back_to_video(self):
        with _Env() as env:
            result = batch_service.create_cover_singles(
                song_lines=["Bai Mot - Ca Si"], music_style="Ballad",
                video_style="real", audio_only=True)
            _drop_threads(result)
            batch_service.set_audio_only(result["batch_key"], False)
            with Session(env.engine) as s:
                proj = s.exec(select(Project)).one()
                self.assertTrue(proj.auto_video)
                pid = proj.id
            self.assertFalse(batch_service._is_audio_only(pid))


class OpenFolderTests(unittest.TestCase):
    def _project(self, env, kind="single"):
        with Session(env.engine) as s:
            p = Project(name="Bai Mot - Ca Si", kind=kind)
            s.add(p)
            s.commit()
            return p.id, p.name

    def test_open_audio_folder_and_final_video(self):
        from backend.cover.nct_jobs import cover_dir
        with _Env() as env:
            pid, name = self._project(env)
            with Session(env.engine) as s:
                self.assertEqual(projects_router._project_folders(s, pid),
                                 {"audio": None, "video": None})
                with self.assertRaises(HTTPException) as ctx:
                    projects_router.open_project_folder(pid, "audio", s)
                self.assertEqual(ctx.exception.status_code, 404)
            folder = cover_dir(pid, name)
            folder.mkdir(parents=True)
            (folder / "Bai Mot - cover.wav").write_bytes(b"x")
            final = vconfig.final_dir(pid, name)
            final.mkdir(parents=True)
            (final / "final.mp4").write_bytes(b"x")
            with Session(env.engine) as s, \
                    patch("os.startfile", create=True) as startfile, \
                    patch("subprocess.Popen") as popen:
                res = projects_router.open_project_folder(pid, "audio", s)
                startfile.assert_called_once_with(str(folder))
                self.assertEqual(res["path"], str(folder))
                projects_router.open_project_folder(pid, "video", s)
                args = popen.call_args[0][0]
                self.assertEqual(args[:2], ["explorer", "/select,"])
                self.assertTrue(args[2].endswith("final.mp4"))
                with self.assertRaises(HTTPException):
                    projects_router.open_project_folder(pid, "evil", s)


if __name__ == "__main__":
    unittest.main()
