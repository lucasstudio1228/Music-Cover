from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from datetime import datetime, timezone
import unittest
from unittest import mock

from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import CoverSong, DeletedTrack, Project, SourceSong, Track
from backend.routers import tracks


def _probe(path):
    return SimpleNamespace(
        path=path, duration_seconds=180.0, sample_rate=48000, channels=2,
        format="WAV", is_lossy=False, subtype="PCM_24")


class TrackRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="track-recovery-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)

    def test_delete_to_trash_and_restore_preserves_cover_metadata(self):
        audio = self.root / "cover.wav"
        audio.write_bytes(b"RIFFaudio")
        with Session(self.engine) as s:
            project = Project(name="P")
            s.add(project)
            s.commit()
            track = Track(project_id=project.id, filename=audio.name,
                          filepath=str(audio), duration_seconds=180,
                          sample_rate=48000, channels=2, format="WAV",
                          is_lossy=False, subtype="PCM_24")
            s.add(track)
            s.flush()
            s.add(CoverSong(project_id=project.id, track_id=track.id,
                            position=1, title="Bài A", artist="Ca sĩ",
                            lyrics_text="Lời", source_id=None,
                            align_status="done",
                            aligned_at=datetime.now(timezone.utc)))
            s.commit()

            tracks._trash_track(s, track)
            s.commit()
            self.assertIsNone(s.get(Track, track.id))
            row = s.exec(select(DeletedTrack)).one()
            self.assertTrue(audio.is_file())

            with mock.patch("backend.core_bridge.probe_file", side_effect=_probe):
                restored = tracks._restore_snapshot(s, row)
                s.commit()
            self.assertIsNotNone(restored)
            song = s.exec(select(CoverSong).where(
                CoverSong.track_id == restored.id)).one()
            self.assertEqual((song.title, song.artist, song.lyrics_text),
                             ("Bài A", "Ca sĩ", "Lời"))
            self.assertIsInstance(song.aligned_at, datetime)
            self.assertEqual(s.exec(select(DeletedTrack)).all(), [])

    def test_restore_all_discovers_old_orphan_cover_files(self):
        cover_dir = self.root / "ban_cover"
        cover_dir.mkdir()
        for name in ("Bài A - cover.wav", "Bài A - cover 2.wav"):
            (cover_dir / name).write_bytes(b"RIFFaudio")
        with Session(self.engine) as s:
            project = Project(name="P")
            s.add(project)
            s.commit()
            source = SourceSong(project_id=project.id, position=1, query="Bài A",
                                title="Bài A", artist="Ca sĩ", lyrics_text="Lời")
            s.add(source)
            s.commit()
            with (mock.patch("backend.cover.nct_jobs.cover_dir", return_value=cover_dir),
                  mock.patch("backend.core_bridge.probe_file", side_effect=_probe),
                  mock.patch("backend.cover.cover_qc.review_async")):
                result = tracks.restore_all_tracks(project.id, s)
            self.assertEqual(result["discovered"], 2)
            self.assertEqual(len(s.exec(select(Track)).all()), 2)
            songs = s.exec(select(CoverSong)).all()
            self.assertEqual(len(songs), 2)
            self.assertTrue(all(song.source_id == source.id for song in songs))

    def test_delete_one_cover_version_then_restore_it(self):
        """Nút «🗑 Xoá bản này» ở tab Suno Cover: xoá 1 trong nhiều bản, khôi phục lại."""
        cover_dir = self.root / "ban_cover"
        cover_dir.mkdir()
        files = [cover_dir / "Bài A - cover.wav", cover_dir / "Bài A - cover 2.wav"]
        for f in files:
            f.write_bytes(b"RIFFaudio")
        with Session(self.engine) as s:
            project = Project(name="P")
            s.add(project)
            s.commit()
            source = SourceSong(project_id=project.id, position=1, query="Bài A",
                                title="Bài A", artist="Ca sĩ", lyrics_text="Lời")
            s.add(source)
            s.commit()
            ids = []
            for pos, f in enumerate(files, 1):
                t = Track(project_id=project.id, filename=f.name, filepath=str(f.resolve()),
                          duration_seconds=180, sample_rate=48000, channels=2,
                          format="WAV", is_lossy=False, subtype="PCM_24")
                s.add(t)
                s.flush()
                s.add(CoverSong(project_id=project.id, track_id=t.id, position=pos,
                                title="Bài A", artist="Ca sĩ", lyrics_text="Lời",
                                source_id=source.id))
                ids.append(t.id)
            s.commit()

            tracks.delete_track(project.id, ids[1], s)
            self.assertTrue(files[1].is_file())          # file vẫn giữ
            self.assertEqual(len(s.exec(select(CoverSong)).all()), 1)
            with mock.patch("backend.cover.nct_jobs.cover_dir", return_value=cover_dir):
                info = tracks.recovery_info(project.id, s)
            self.assertEqual(info["trash_count"], 1)
            self.assertEqual(info["items"][0]["source_id"], source.id)
            self.assertEqual(info["orphan_files"], [])   # không trùng thành "file cũ"

            with (mock.patch("backend.cover.nct_jobs.cover_dir", return_value=cover_dir),
                  mock.patch("backend.core_bridge.probe_file", side_effect=_probe),
                  mock.patch("backend.cover.cover_qc.review_async")):
                res = tracks.restore_selected_tracks(
                    project.id, tracks.RestoreSelection(trash_ids=[info["items"][0]["id"]]), s)
            self.assertEqual((res["restored"], res["discovered"]), (1, 0))
            songs = s.exec(select(CoverSong).order_by(CoverSong.position)).all()
            self.assertEqual([(x.position, x.source_id) for x in songs],
                             [(1, source.id), (2, source.id)])


if __name__ == "__main__":
    unittest.main()
