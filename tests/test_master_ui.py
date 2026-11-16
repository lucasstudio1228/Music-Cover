"""Master hiện trên giao diện tab ②: trạng thái từng bản, master tay, đổi preset."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from backend.cover import mastering as m


def _cfg(**over):
    return m._merge(m.DEFAULT_CONFIG, over)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = self.tmp / "master_config.json"

    def test_save_keeps_hand_edited_values(self):
        self.path.write_text(json.dumps({"eq_mud": {"gain_db": -3}, "max_parallel": 1}),
                             encoding="utf-8")
        cfg = m.save_settings({"preset": "LOUD", "output_format": "MP3", "enabled": False},
                              self.path)
        self.assertEqual((cfg["preset"], cfg["output_format"], cfg["enabled"]),
                         ("loud", "mp3", False))
        saved = m.load_config(self.path)
        self.assertEqual(saved["preset"], "loud")
        self.assertEqual(saved["eq_mud"]["gain_db"], -3)
        self.assertEqual(saved["max_parallel"], 1)

    def test_invalid_values_rejected_and_file_untouched(self):
        m.save_settings({"preset": "dynamic"}, self.path)
        before = self.path.read_text(encoding="utf-8")
        for bad in ({"preset": "khong-co"}, {"output_format": "flac"}):
            with self.assertRaises(m.MasterError):
                m.save_settings(bad, self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp / "Bài A - cover.wav"
        self.src.write_bytes(b"RIFF")
        self.addCleanup(m._active.clear)

    def _fake_master(self, src, *a, **k):
        dest = m.master_paths(src, "wav")[0]
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(b"RIFF-master")
        return {"status": "done"}

    def test_none_then_done_with_info(self):
        self.assertEqual(m.status_of(self.src)["state"], "none")
        self._fake_master(self.src)
        m._write_info(self.src, {"preset": "natural", "before": {"lufs": -9.1, "tp": 0.2},
                                 "after": {"lufs": -14.0, "tp": -1.3}, "at": "x"})
        st = m.status_of(self.src)
        self.assertEqual((st["state"], st["file"], st["preset"]),
                         ("done", "Bài A - cover_master.wav", "natural"))
        self.assertEqual(st["after"]["lufs"], -14.0)

    def test_failure_is_remembered(self):
        with mock.patch.object(m, "resolve_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(m, "wait_ready", return_value=True), \
                mock.patch.object(m, "measure", side_effect=m.MasterError("đo hỏng")):
            res = m.master_file(self.src, _cfg(), log=lambda _: None)
        self.assertEqual(res["status"], "failed")
        st = m.status_of(self.src)
        self.assertEqual(st["state"], "failed")
        self.assertIn("đo hỏng", st["error"])
        self.assertFalse(m.is_busy())

    def test_submit_marks_queued_and_skips_duplicates(self):
        gate = threading.Event()
        started = threading.Event()

        def slow_batch(files, expected=None, log=print, **kw):
            started.set()
            gate.wait(5)
            with m._lock:
                for f in files:
                    m._active.pop(m._key(f), None)

        with mock.patch.object(m, "master_batch", side_effect=slow_batch) as batch:
            t = m.submit([self.src], log=lambda _: None, force=True, cfg={"enabled": True})
            self.assertEqual(m.status_of(self.src)["state"], "queued")
            self.assertTrue(m.is_busy())
            self.assertIsNone(m.submit([self.src], log=lambda _: None))   # đang chờ → bỏ qua
            started.wait(5)
            gate.set()
            t.join(5)
        self.assertEqual(batch.call_count, 1)
        self.assertEqual(batch.call_args.kwargs, {"force": True, "cfg": {"enabled": True}})
        self.assertFalse(m.is_busy())

    def test_force_remasters_existing(self):
        self._fake_master(self.src)
        calls = []
        with mock.patch.object(m, "resolve_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(m, "wait_ready", return_value=True), \
                mock.patch.object(m, "measure", side_effect=lambda *a, **k: calls.append(1) or
                                  (_ for _ in ()).throw(m.MasterError("stop"))):
            skipped = m.master_file(self.src, _cfg(), log=lambda _: None)
            forced = m.master_file(self.src, _cfg(), log=lambda _: None, force=True)
        self.assertEqual(skipped["status"], "skipped")
        self.assertEqual(forced["status"], "failed")       # force → thật sự chạy lại
        self.assertEqual(len(calls), 1)
        # bản master cũ vẫn còn khi lần làm lại bị lỗi
        self.assertEqual(m.find_master(self.src).read_bytes(), b"RIFF-master")
        self.assertEqual(m.status_of(self.src)["state"], "done")


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from sqlmodel import Session, SQLModel, create_engine
        from backend.database import get_session
        from backend.main import app
        from backend.models import CoverSong, Project, SourceSong, Track
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.engine = create_engine(f"sqlite:///{self.tmp / 's.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        covers = self.tmp / "ban_cover"
        covers.mkdir()
        self.files, self.tids = [], []
        with Session(self.engine) as s:
            proj = Project(name="Master UI")
            s.add(proj)
            s.commit()
            self.pid = proj.id
            src = SourceSong(project_id=self.pid, query="Bài A", status="manual")
            s.add(src)
            s.commit()
            for i in range(2):
                f = covers / f"Bài A - cover {i + 1}.wav"
                f.write_bytes(b"RIFF")
                t = Track(project_id=self.pid, filename=f.name, filepath=str(f),
                          duration_seconds=200, sample_rate=48000, channels=2,
                          format="WAV", is_lossy=False)
                s.add(t)
                s.commit()
                s.add(CoverSong(project_id=self.pid, track_id=t.id, position=i,
                                source_id=src.id, title="Bài A"))
                s.commit()
                self.files.append(f)
                self.tids.append(t.id)

        def _session():
            with Session(self.engine) as s:
                yield s
        app.dependency_overrides[get_session] = _session
        self.addCleanup(app.dependency_overrides.clear)
        self.cfg_path = self.tmp / "master_config.json"
        self.cfg_path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
        self.submit = mock.MagicMock()
        for p in (mock.patch.object(m, "CONFIG_FILE", self.cfg_path),
                  mock.patch.object(m, "submit", self.submit),
                  mock.patch.object(m, "resolve_ffmpeg", return_value="ffmpeg"),
                  mock.patch.object(m, "_ffmpeg_state",
                                    {"checked": True, "ok": True, "path": "ffmpeg",
                                     "version": "ffmpeg 8", "error": ""}),
                  mock.patch("backend.cover.cover_qc.evaluate", return_value={})):
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app)

    def _master(self, f: Path):
        dest = m.master_paths(f, "wav")[0]
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(b"RIFF-master")

    def test_list_shows_master_state(self):
        self._master(self.files[0])
        r = self.client.get(f"/api/sources/projects/{self.pid}")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("master_running", body)
        states = [c["master"]["state"] for c in body["items"][0]["covers"]]
        self.assertEqual(states, ["done", "none"])

    def test_manual_master_runs_even_when_auto_is_off(self):
        r = self.client.post(f"/api/sources/covers/{self.tids[0]}/master", json={"force": True})
        self.assertEqual(r.status_code, 200, r.text)
        args, kw = self.submit.call_args
        self.assertEqual(args[0], [self.files[0]])
        self.assertTrue(kw["force"])
        self.assertTrue(kw["cfg"]["enabled"])

    def test_missing_ffmpeg_gives_clear_error(self):
        with mock.patch.object(m, "resolve_ffmpeg", side_effect=m.MasterError("Không thấy ffmpeg")):
            r = self.client.post(f"/api/sources/covers/{self.tids[0]}/master", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("ffmpeg", r.json()["detail"])
        self.submit.assert_not_called()

    def test_project_master_only_unmastered_unless_force(self):
        self._master(self.files[0])
        r = self.client.post(f"/api/sources/projects/{self.pid}/master", json={})
        self.assertEqual(r.json(), {"queued": 1})
        self.assertEqual(self.submit.call_args.args[0], [self.files[1]])
        r = self.client.post(f"/api/sources/projects/{self.pid}/master", json={"force": True})
        self.assertEqual(r.json(), {"queued": 2})

    def test_master_audio(self):
        url = f"/api/sources/covers/{self.tids[0]}/master/audio"
        self.assertEqual(self.client.get(url).status_code, 404)
        self._master(self.files[0])
        r = self.client.get(url)
        self.assertEqual((r.status_code, r.content), (200, b"RIFF-master"))

    def test_settings_get_and_put(self):
        r = self.client.get("/api/sources/master/settings")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["enabled"], d["preset"], d["ffmpeg"]["ok"]), (False, "natural", True))
        self.assertEqual([p["name"] for p in d["presets"]], ["natural", "dynamic", "loud"])
        r = self.client.put("/api/sources/master/settings",
                            json={"preset": "dynamic", "output_format": "both", "enabled": True})
        self.assertEqual(r.status_code, 200, r.text)
        saved = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertEqual((saved["preset"], saved["output_format"], saved["enabled"]),
                         ("dynamic", "both", True))
        self.assertEqual(self.client.put("/api/sources/master/settings",
                                         json={"preset": "xyz"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
