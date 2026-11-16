"""Đổi tempo nhạc gốc: dải 0.2×–5×, xuất trong project và lưu DB."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import tempo


class TempoPureTests(unittest.TestCase):
    def test_atempo_chain_covers_extremes(self):
        self.assertEqual(tempo.atempo_filter(0.2), "atempo=0.5,atempo=0.5,atempo=0.8")
        self.assertEqual(tempo.atempo_filter(1), "atempo=1")
        self.assertEqual(tempo.atempo_filter(5), "atempo=2,atempo=2,atempo=1.25")

    def test_factor_bounds(self):
        for value in (0.199, 5.001, float("nan"), float("inf")):
            with self.assertRaises(tempo.TempoError):
                tempo.normalize_factor(value)


class TempoApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import Project, SourceSong
        from backend.video import config

        tmp = TemporaryDirectory(prefix="tempo-api-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        original = self.root / "original.mp3"
        original.write_bytes(b"ID3-original")
        with Session(self.engine) as session:
            project = Project(name="Tempo Test")
            session.add(project)
            session.commit()
            source = SourceSong(project_id=project.id, title="Bài A", artist="Ca sĩ A",
                                file_path=str(original), lyrics_text="Lời", status="done")
            session.add(source)
            session.commit()
            self.pid, self.sid = project.id, source.id

        def session_override():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.addCleanup(app.dependency_overrides.clear)
        self.media = self.root / "media"
        p = mock.patch.object(config, "MEDIA_ROOT", self.media)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)

    def test_export_persists_and_exposes_file(self):
        def fake_export(source, source_id, project_id, project_name, title, artist, query, factor):
            path = tempo.tempo_dir(project_id, project_name) / "adjusted.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"RIFF-adjusted")
            return path.resolve()

        with mock.patch.object(tempo, "export_file", side_effect=fake_export):
            response = self.client.post(f"/api/sources/{self.sid}/tempo",
                                        json={"tempo_factor": 0.2})
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()
        self.assertEqual(item["tempo_factor"], 0.2)
        self.assertTrue(item["tempo_ready"])
        self.assertEqual(item["tempo_file_name"], "adjusted.wav")
        audio = self.client.get(f"/api/sources/{self.sid}/tempo/audio")
        self.assertEqual((audio.status_code, audio.content), (200, b"RIFF-adjusted"))

    def test_export_rejects_outside_range(self):
        for factor in (0.19, 5.01):
            response = self.client.post(f"/api/sources/{self.sid}/tempo",
                                        json={"tempo_factor": factor})
            self.assertEqual(response.status_code, 400)

    def test_suno_requires_export(self):
        response = self.client.post(f"/api/sources/{self.sid}/suno", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("chỉnh tempo", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
