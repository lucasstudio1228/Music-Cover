"""Chỉnh tempo bản cover đã tải (tab ②): thanh tempo + OK → file mới cho Lời/Mix."""
import json
import shutil
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import cover_tempo, mastering
from tests.helpers import generate_test_wav

HAS_FFMPEG = shutil.which("ffmpeg") is not None


class PureTests(unittest.TestCase):
    def test_factor_bounds(self):
        self.assertEqual(cover_tempo.normalize_factor("1.1"), 1.1)
        for bad in (0.49, 1.51, float("nan"), "abc", None):
            with self.assertRaises(cover_tempo.CoverTempoError):
                cover_tempo.normalize_factor(bad)
        self.assertEqual(cover_tempo.normalize_factor(None, strict=False), 1.0)

    def test_scale_lyrics(self):
        self.assertIsNone(cover_tempo.scale_lyrics("[]", 0.5))
        out = json.loads(cover_tempo.scale_lyrics(
            json.dumps([{"text": "a", "start": 2.0, "end": 4.0},
                        {"text": "b", "start": 4.0, "end": 6.0}]), 0.8))
        self.assertEqual([(l["start"], l["end"]) for l in out], [(1.6, 3.2), (3.2, 4.8)])

    def test_only_files_directly_in_cover_dir(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "ban_cover"
            self.assertTrue(cover_tempo.is_tool_file(folder / "a.wav", folder))
            self.assertFalse(cover_tempo.is_tool_file(folder / "_loi" / "a.wav", folder))
            self.assertFalse(cover_tempo.is_tool_file(Path(tmp) / "a.wav", folder))


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg")
class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.cover import cover_qc, nct_jobs
        from backend.database import get_session
        from backend.main import app
        from backend.models import CoverSong, Project, SourceSong, Track
        from backend.video import config

        tmp = TemporaryDirectory(prefix="cover-tempo-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.media = self.root / "media"
        for target, attr, value in (
                (config, "MEDIA_ROOT", self.media),
                (mastering, "load_config",
                 lambda *a, **k: mastering._merge(mastering.DEFAULT_CONFIG, {}))):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        self.submit = mock.patch.object(mastering, "submit").start()
        self.review = mock.patch.object(cover_qc, "review_async").start()
        self.addCleanup(mock.patch.stopall)

        with Session(self.engine) as session:
            project = Project(name="Tempo Cover")
            session.add(project)
            session.commit()
            folder = nct_jobs.cover_dir(project.id, project.name)
            folder.mkdir(parents=True)
            self.file = folder / "Bài A - cover.wav"
            generate_test_wav(str(self.file), duration_sec=6.0)
            info = sf.info(str(self.file))
            source = SourceSong(project_id=project.id, title="Bài A", status="done")
            session.add(source)
            session.commit()
            track = Track(project_id=project.id, filename=self.file.name,
                          filepath=str(self.file), duration_seconds=info.duration,
                          sample_rate=info.samplerate, channels=info.channels, format="WAV",
                          is_lossy=False, subtype=info.subtype)
            session.add(track)
            session.commit()
            song = CoverSong(project_id=project.id, track_id=track.id, title="Bài A",
                             source_id=source.id, align_status="done",
                             lyrics_json=json.dumps([{"text": "câu 1", "start": 2.0,
                                                      "end": 4.0}]))
            session.add(song)
            session.commit()
            self.pid, self.tid, self.song_id = project.id, track.id, song.id

        def session_override():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.CoverSong, self.Track, self.Session = CoverSong, Track, Session

    def _post(self, factor):
        return self.client.post(f"/api/sources/covers/{self.tid}/tempo", json={"factor": factor})

    def _state(self):
        with self.Session(self.engine) as s:
            song, track = s.get(self.CoverSong, self.song_id), s.get(self.Track, self.tid)
            return song, track

    def test_ok_converts_file_rescales_lyrics_and_remasters(self):
        original = self.file.read_bytes()
        master = mastering.master_paths(self.file, "wav")[0]
        master.parent.mkdir()
        master.write_bytes(b"RIFF-old-master")

        r = self._post(1.25)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["changed"] and body["remastering"] and body["lyrics_rescaled"])
        self.assertAlmostEqual(sf.info(str(self.file)).duration, 4.8, delta=0.05)
        backup = cover_tempo.backup_path_for(self.file)
        self.assertEqual(backup.read_bytes(), original)          # bản Suno gốc được cất
        self.assertFalse(master.exists())                         # master tempo cũ bị bỏ
        self.assertTrue(self.submit.call_args.kwargs["force"])
        self.review.assert_called_once_with(self.pid)
        song, track = self._state()
        self.assertEqual(song.tempo_factor, 1.25)
        self.assertAlmostEqual(track.duration_seconds, 4.8, delta=0.05)
        line = json.loads(song.lyrics_json)[0]
        self.assertEqual((line["start"], line["end"]), (1.6, 3.2))
        self.assertEqual(song.align_status, "done")

        listed = self.client.get(f"/api/sources/projects/{self.pid}").json()
        self.assertEqual(listed["items"][0]["covers"][0]["tempo_factor"], 1.25)
        self.assertEqual(self.client.get(f"/api/cover/songs/{self.song_id}/audio").content,
                         self.file.read_bytes())

    def test_readjust_works_from_original_and_one_restores_it(self):
        original = self.file.read_bytes()
        self.assertEqual(self._post(1.25).status_code, 200)
        r = self._post(0.8)
        self.assertEqual(r.status_code, 200, r.text)
        # 6s / 0.8 = 7.5s (tính từ bản gốc, không chồng lên bản 1.25×)
        self.assertAlmostEqual(sf.info(str(self.file)).duration, 7.5, delta=0.05)
        line = json.loads(self._state()[0].lyrics_json)[0]
        self.assertEqual(line["start"], 2.5)
        self.assertFalse(self.submit.called)          # chưa từng master → không tự master
        r = self._post(1.0)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.file.read_bytes(), original)
        song, track = self._state()
        self.assertEqual(song.tempo_factor, 1.0)
        self.assertEqual(json.loads(song.lyrics_json)[0]["start"], 2.0)
        self.assertFalse(self._post(1.0).json()["changed"])

    def test_rejects_bad_factor_busy_master_and_outside_files(self):
        self.assertEqual(self._post(1.6).status_code, 400)
        with mock.patch.object(mastering, "status_of", return_value={"state": "running"}):
            self.assertEqual(self._post(1.1).status_code, 409)
        outside = self.root / "ngoai.wav"
        shutil.copy(self.file, outside)
        with self.Session(self.engine) as s:
            track = s.get(self.Track, self.tid)
            track.filepath = str(outside)
            s.add(track)
            s.commit()
        self.assertEqual(self._post(1.1).status_code, 400)
        self.assertFalse(cover_tempo.backup_path_for(outside).exists())


if __name__ == "__main__":
    unittest.main()
