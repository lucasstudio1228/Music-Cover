"""Project tạo tay dùng cùng công cụ cover, nhưng không tự chạy end-to-end."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import Project, SourceSong
from backend.cover.style_prompt import NO_CREATIVE_INSTRUMENT
from backend.routers.projects import create_project
from backend.routers.sources import AddIn, add_sources
from backend.schemas import ProjectCreate


class ManualProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="manual-project-")
        self.addCleanup(tmp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(tmp.name) / 'app.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)

    def test_manual_project_keeps_tools_without_auto_start(self):
        with Session(self.engine) as session:
            response = create_project(ProjectCreate(
                name="Project thủ công", music_style="Ballad", kind="mixset",
                creative_instrument=False, footage_scene_mode="screen_only"), session)
            self.assertFalse(response.creative_instrument)
            self.assertEqual("screen_only", response.footage_scene_mode)
            project = session.get(Project, response.id)
            self.assertFalse(project.auto_video)
            self.assertFalse(project.auto_upload)
            added = add_sources(response.id, AddIn(
                text="Bài Một - Ca Sĩ", start=False), session)
            self.assertEqual(1, added["added"])
            source = session.exec(select(SourceSong)).one()
            self.assertEqual(NO_CREATIVE_INSTRUMENT, source.featured_instrument)


if __name__ == "__main__":
    unittest.main()
