"""Edge cases cho bản tempo: thay thế nguyên tử, cleanup và Suno state.

Chỉ dùng DB/thư mục tạm; ffmpeg và worker ngoài đều được giả lập.
"""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, SQLModel, create_engine

from backend.cover import tempo
from backend.models import CoverSong, Project, SourceSong, Track
from backend.routers import sources


class TempoAtomicExportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="tempo-atomic-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.mp3"
        self.source.write_bytes(b"ID3-source")
        patcher = mock.patch.object(tempo.vconfig, "MEDIA_ROOT", self.root / "media")
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _ffmpeg_result(returncode=0, stderr=""):
        return SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")

    def test_success_writes_inside_project_and_uses_pitch_preserving_filter(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            Path(cmd[-1]).write_bytes(b"RIFF" + b"x" * 64)
            return self._ffmpeg_result()

        with mock.patch.object(tempo.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(tempo.subprocess, "run", side_effect=fake_run):
            out = tempo.export_file(self.source, 11, 7, "Tên project",
                                    "Bài", "Ca sĩ", "", 0.2)

        expected = tempo.tempo_dir(7, "Tên project").resolve()
        self.assertEqual(out.parent, expected)
        self.assertEqual(out.suffix, ".wav")
        self.assertEqual(calls[0][0][calls[0][0].index("-filter:a") + 1],
                         "atempo=0.5,atempo=0.5,atempo=0.8")
        self.assertEqual(calls[0][0][calls[0][0].index("-c:a") + 1], "pcm_s16le")
        self.assertFalse(any(p.name.endswith(".tmp.wav") for p in expected.iterdir()))

    def test_failed_reexport_keeps_previous_file_and_removes_partial_temp(self):
        folder = tempo.tempo_dir(7, "Tên project")
        folder.mkdir(parents=True)
        existing = folder / "Bài - Ca sĩ - tempo 1.5x.wav"
        existing.write_bytes(b"previous-good")

        def fake_run(cmd, **_kwargs):
            Path(cmd[-1]).write_bytes(b"partial")
            return self._ffmpeg_result(1, "decode failed")

        with mock.patch.object(tempo.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(tempo.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(tempo.TempoError, "decode failed"):
                tempo.export_file(self.source, 11, 7, "Tên project",
                                  "Bài", "Ca sĩ", "", 1.5)

        self.assertEqual(existing.read_bytes(), b"previous-good")
        self.assertFalse(any(p.name.endswith(".tmp.wav") for p in folder.iterdir()))


class TempoStateEdgeTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="tempo-state-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.media = self.root / "media"
        self.engine = create_engine(f"sqlite:///{self.root / 'state.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)

        self.project = Project(name="Tempo State")
        self.session.add(self.project)
        self.session.commit()
        project_dir = self.media / f"Tempo State (#{self.project.id})"
        self.original = project_dir / "nhac_goc" / "Bài.mp3"
        self.original.parent.mkdir(parents=True)
        self.original.write_bytes(b"ID3-original")
        self.old_tempo = project_dir / tempo.TEMPO_STEM / "old.wav"
        self.old_tempo.parent.mkdir(parents=True)
        self.old_tempo.write_bytes(b"RIFF-old")
        self.source = SourceSong(
            project_id=self.project.id, query="Bài - Ca sĩ", title="Bài", artist="Ca sĩ",
            file_path=str(self.original), tempo_factor=0.8,
            tempo_file_path=str(self.old_tempo), lyrics_text="Một câu", status="done",
            suno_status="done", suno_song_ids="old-a,old-b",
        )
        self.session.add(self.source)
        self.session.commit()

        for target, value in (
                ("backend.video.config.MEDIA_ROOT", self.media),
                ("backend.cover.nct_jobs.is_active", lambda _sid: False),
                ("backend.cover.suno_jobs.is_active", lambda _sid: False),
                ("backend.cover.cover_qc.evaluate", lambda *_a, **_k: {}),
                ("backend.cover.cover_qc.review_async", mock.MagicMock()),
                ("backend.cover.nct_jobs.submit", mock.MagicMock(return_value=1))):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _add_cover(self):
        track = Track(project_id=self.project.id, filename="cover.wav", filepath="cover.wav",
                      duration_seconds=1, sample_rate=44100, channels=2,
                      format="WAV", is_lossy=False)
        self.session.add(track)
        self.session.flush()
        self.session.add(CoverSong(project_id=self.project.id, track_id=track.id,
                                   source_id=self.source.id))
        self.session.commit()

    def test_reexport_invalidates_old_suno_ids_and_marks_existing_cover_for_redo(self):
        self._add_cover()
        new_file = tempo.tempo_dir(self.project.id, self.project.name) / "new.wav"

        def fake_export(*_args, **_kwargs):
            new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.write_bytes(b"RIFF-new")
            return new_file.resolve()

        with mock.patch.object(tempo, "export_file", side_effect=fake_export):
            result = sources.export_tempo(self.source.id, sources.TempoIn(tempo_factor=1.5),
                                          self.session)

        self.session.refresh(self.source)
        self.assertEqual((self.source.tempo_factor, self.source.tempo_file_path),
                         (1.5, str(new_file.resolve())))
        self.assertEqual((self.source.suno_song_ids, self.source.suno_status), ("", "redo"))
        self.assertFalse(self.old_tempo.exists())
        self.assertTrue(result["tempo_ready"])

    def test_reexport_never_deletes_previous_path_outside_project(self):
        external = self.root / "external.wav"
        external.write_bytes(b"keep-me")
        self.source.tempo_file_path = str(external)
        self.session.add(self.source)
        self.session.commit()
        new_file = tempo.tempo_dir(self.project.id, self.project.name) / "new.wav"

        def fake_export(*_args, **_kwargs):
            new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.write_bytes(b"RIFF-new")
            return new_file.resolve()

        with mock.patch.object(tempo, "export_file", side_effect=fake_export):
            sources.export_tempo(self.source.id, sources.TempoIn(tempo_factor=2), self.session)
        self.assertEqual(external.read_bytes(), b"keep-me")

    def test_changing_search_query_removes_stale_tempo_file_and_resets_fields(self):
        result = sources.update_source(
            self.source.id, sources.SourceIn(query="Bài khác - Ca sĩ khác"), self.session)
        self.session.refresh(self.source)
        self.assertFalse(self.old_tempo.exists())
        self.assertEqual((self.source.tempo_factor, self.source.tempo_file_path), (1.0, ""))
        self.assertFalse(result["tempo_ready"])


if __name__ == "__main__":
    unittest.main()
