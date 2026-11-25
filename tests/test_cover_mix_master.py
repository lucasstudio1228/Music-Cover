"""Mix dùng bản _master (nếu có), chưa có thì dùng file gốc."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlmodel import Session, SQLModel, create_engine

from backend.cover import mastering
from backend.cover import mix as cover_mix
from backend.models import CoverSong, Project, Track
from tests.helpers import generate_test_wav


class CoverMixMasterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = self.tmp / "app.db"
        engine = create_engine(f"sqlite:///{self.db}")
        self.addCleanup(engine.dispose)
        SQLModel.metadata.create_all(engine)
        covers = self.tmp / "ban_cover"
        covers.mkdir()
        self.files = []
        with Session(engine) as s:
            project = Project(name="Thử mix")
            s.add(project)
            s.commit()
            s.refresh(project)
            self.pid = project.id
            for i, (name, freq) in enumerate((("Bài A - cover.wav", 440),
                                              ("Bài B - cover.wav", 330))):
                path = covers / name
                generate_test_wav(str(path), duration_sec=20, frequency=freq)
                self.files.append(path)
                t = Track(project_id=self.pid, filename=name, filepath=str(path),
                          duration_seconds=20, sample_rate=48000, channels=2,
                          format="WAV", is_lossy=False)
                s.add(t)
                s.commit()
                s.refresh(t)
                s.add(CoverSong(project_id=self.pid, track_id=t.id, position=i,
                                title=Path(name).stem.split(" - ")[0], artist="Ca sĩ"))
            s.commit()
        p = mock.patch.object(mastering, "load_config",
                              return_value=mastering._merge(mastering.DEFAULT_CONFIG, {}))
        p.start()
        self.addCleanup(p.stop)

    def _master(self, src: Path) -> Path:
        dest = mastering.master_paths(src, "wav")[0]
        dest.parent.mkdir(exist_ok=True)
        generate_test_wav(str(dest), duration_sec=20, frequency=550)
        return dest

    def _run(self, balance=True):
        out = self.tmp / "out"
        seen = []
        real = cover_mix._load_normalized

        def spy(track, sr, target_lufs=None):
            seen.append(target_lufs)
            return real(track, sr, target_lufs)

        with mock.patch.object(cover_mix, "_load_normalized", side_effect=spy):
            cover_mix.run_cover_mix_job(1, lambda *a, **k: None, self.pid, str(out),
                                        0, 2.0, 48000, 24, str(self.db),
                                        loudness_balance=balance)
        info = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
        if balance:
            seen = [info["loudness"]["target_lufs"]] * len(info["tracks"])
        return info["tracks"], seen

    def test_ordered_songs_prefers_master_wav_then_mp3(self):
        mp3 = mastering.master_paths(self.files[1], "mp3")[0]
        mp3.parent.mkdir()
        mp3.write_bytes(b"ID3")
        wav = self._master(self.files[0])
        songs = cover_mix.ordered_songs(str(self.db), self.pid)
        self.assertEqual([s["path"] for s in songs], [str(wav), str(mp3)])
        self.assertEqual([s["source_file"] for s in songs],
                         ["Bài A - cover.wav", "Bài B - cover.wav"])
        self.assertTrue(all(s["mastered"] for s in songs))

    def test_mix_uses_master_and_keeps_original_name(self):
        master = self._master(self.files[0])
        tracks, seen = self._run()
        self.assertEqual([t["source_file"] for t in tracks],
                         ["Bài A - cover.wav", "Bài B - cover.wav"])
        self.assertEqual([t["audio_file"] for t in tracks],
                         [master.name, "Bài B - cover.wav"])
        self.assertEqual(seen, [-14.0, -14.0])          # cả 2 bài theo preset natural
        self.assertTrue(self.files[0].is_file())         # file gốc còn nguyên

    def test_no_master_targets_minus_16(self):
        tracks, seen = self._run()
        self.assertEqual([t["audio_file"] for t in tracks],
                         ["Bài A - cover.wav", "Bài B - cover.wav"])
        self.assertEqual(seen, [-16.0, -16.0])           # vẫn -16 LUFS như trước

    def test_balance_off_keeps_old_integrated_normalize(self):
        _, seen = self._run(balance=False)
        self.assertEqual(seen, [None, None])


if __name__ == "__main__":
    unittest.main()
