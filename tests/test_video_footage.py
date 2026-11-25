"""Upload footage: một file/project, kiểm tra video và xoá độc lập với audio."""
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, SQLModel, create_engine

from backend.models import Project
from backend.video import config
from backend.routers import video


class FootageApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="video-footage-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{root / 'app.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as db:
            p = Project(name="Footage Project")
            db.add(p)
            db.commit()
            self.pid = p.id

        self.media = patch.object(config, "MEDIA_ROOT", root / "media")
        self.busy = patch("backend.routers.video.video_job_manager.is_busy",
                          return_value=False)
        self.duration = patch("backend.video.assembler.probe_duration", return_value=12.5)
        self.fps = patch("backend.video.assembler.probe_fps", return_value=30.0)
        for p in (self.media, self.busy, self.duration, self.fps):
            p.start()
            self.addCleanup(p.stop)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

    def test_upload_adds_preview_and_delete(self):
        first = UploadFile(filename="real scene.mp4", file=io.BytesIO(b"first"))
        r = video.upload_footage(self.pid, first, self.db)
        self.assertEqual(r["count"], 1)
        root = config.footage_dir(self.pid, "Footage Project")
        self.assertEqual([p.name for p in root.iterdir()], ["real scene.mp4"])
        self.assertEqual(config.footage_file(self.pid, "Footage Project").read_bytes(), b"first")

        # Upload thêm KHÔNG thay footage cũ — project giữ nhiều footage.
        second = UploadFile(filename="new.mov", file=io.BytesIO(b"second"))
        r = video.upload_footage(self.pid, second, self.db)
        self.assertEqual(r["count"], 2)
        self.assertEqual(sorted(p.name for p in root.iterdir()), ["new.mov", "real scene.mp4"])
        self.assertTrue(video.delete_footage(self.pid, db=self.db)["deleted"])
        self.assertIsNone(config.footage_file(self.pid, "Footage Project"))

    def test_rejects_non_video_extension(self):
        bad = UploadFile(filename="notes.txt", file=io.BytesIO(b"x"))
        with self.assertRaises(HTTPException) as cm:
            video.upload_footage(self.pid, bad, self.db)
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
