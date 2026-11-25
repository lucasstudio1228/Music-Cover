"""Master tự động sau khi tải 2 bản Suno (backend/cover/mastering.py)."""
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from backend.cover import mastering as m

FFMPEG = shutil.which("ffmpeg")


def _cfg(**over):
    return m._merge(m.DEFAULT_CONFIG, over)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_gives_defaults_and_ensure_writes_it(self):
        path = self.tmp / "master_config.json"
        self.assertEqual(m.load_config(path), m.DEFAULT_CONFIG)
        m.ensure_config_file(path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["preset"], "natural")

    def test_ensure_never_overwrites_user_file(self):
        path = self.tmp / "master_config.json"
        path.write_text('{"preset": "loud"}', encoding="utf-8")
        m.ensure_config_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), '{"preset": "loud"}')

    def test_partial_override_keeps_other_defaults(self):
        path = self.tmp / "master_config.json"
        path.write_text(json.dumps({"preset": "dynamic", "eq_mud": {"gain_db": -3}}),
                        encoding="utf-8")
        cfg = m.load_config(path)
        self.assertEqual(cfg["preset"], "dynamic")
        self.assertEqual(cfg["eq_mud"], {"freq_hz": 300, "width_q": 1.0, "gain_db": -3})
        self.assertEqual(cfg["presets"]["loud"]["lufs"], -10)

    def test_broken_json_falls_back_to_defaults(self):
        path = self.tmp / "master_config.json"
        path.write_text("{hỏng", encoding="utf-8")
        self.assertEqual(m.load_config(path), m.DEFAULT_CONFIG)

    def test_presets(self):
        cfg = _cfg()
        self.assertEqual(m.preset_values(cfg), ("natural", {**cfg["presets"]["natural"]}))
        self.assertEqual(m.preset_values(cfg, "dynamic")[1]["ratio"], 1.5)
        loud = m.preset_values(cfg, "LOUD")[1]
        self.assertEqual((loud["lufs"], loud["ratio"]), (-10, 3))
        with self.assertRaises(m.MasterError):
            m.preset_values(cfg, "siêu to")


class FilterTests(unittest.TestCase):
    def test_full_chain_in_spec_order(self):
        cfg = _cfg()
        graph = m.build_filter(cfg, cfg["presets"]["natural"], "I=-14:TP=-1:LRA=11")
        order = ["highpass=f=30", "equalizer=f=300:t=q:w=1:g=-1.5",
                 "equalizer=f=3500:t=q:w=1.5:g=-1.5", "highshelf=f=10000:g=-1.5",
                 "acrossover=split=120[lo][hi]",
                 "[lo]pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1[lom]",
                 "amix=inputs=2:normalize=0",
                 "acompressor=threshold=-18dB:ratio=2:attack=20:release=200",
                 "loudnorm=I=-14:TP=-1:LRA=11"]
        pos = [graph.index(x) for x in order]
        self.assertEqual(pos, sorted(pos))
        self.assertTrue(graph.startswith("[0:a]") and graph.endswith("[out]"))

    def test_mono_bass_off_and_custom_numbers(self):
        cfg = _cfg(mono_bass={"enabled": False}, highpass_hz=25,
                   eq_harsh={"gain_db": -2})
        graph = m.build_filter(cfg, cfg["presets"]["loud"], "I=-10")
        self.assertNotIn("acrossover", graph)
        self.assertNotIn("amix", graph)
        self.assertIn("highpass=f=25", graph)
        self.assertIn("equalizer=f=3500:t=q:w=1.5:g=-2", graph)
        self.assertIn("ratio=3", graph)

    def test_loudnorm_pass2_args(self):
        cfg = _cfg()
        measured = {"input_i": "-20.1", "input_tp": "-3.2", "input_lra": "6.5",
                    "input_thresh": "-30.4", "target_offset": "0.3"}
        args = m._loudnorm_args(cfg, cfg["presets"]["natural"], measured)
        self.assertIn("TP=-1.5", m._loudnorm_args(cfg, cfg["presets"]["natural"], measured, 0.5))
        for part in ("I=-14", "TP=-1", "LRA=11", "measured_I=-20.1", "measured_TP=-3.2",
                     "measured_LRA=6.5", "measured_thresh=-30.4", "offset=0.3",
                     "linear=true"):
            self.assertIn(part, args)

    def test_parse_last_json_block(self):
        err = ('[Parsed_loudnorm_0 @ 1] \n{\n "input_i" : "-1.0", "input_tp" : "0",'
               ' "input_lra" : "1", "input_thresh" : "-9", "target_offset" : "0"\n}\n'
               'noise\n{\n "input_i" : "-23.50", "input_tp" : "-4.10", "input_lra" : "7.2",'
               ' "input_thresh" : "-34.0", "output_i" : "-14.0", "target_offset" : "0.1"\n}')
        self.assertEqual(m.parse_loudnorm_json(err)["input_i"], "-23.50")
        with self.assertRaises(m.MasterError):
            m.parse_loudnorm_json("không có json")
        silent = err.replace('"-23.50"', '"-inf"')
        with self.assertRaises(m.MasterError):
            m.parse_loudnorm_json(silent)

    def test_encode_args(self):
        self.assertEqual(m._encode_args("wav")[-4:], ["-c:a", "pcm_s24le", "-f", "wav"])
        mp3 = m._encode_args("mp3")
        self.assertIn("libmp3lame", mp3)
        self.assertIn("320k", mp3)
        self.assertIn("48000", mp3)


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_master_paths_and_skip_existing(self):
        src = self.tmp / "Bài - cover.wav"
        src.write_bytes(b"x")
        paths = m.master_paths(src, "both")
        self.assertEqual([p.name for p in paths],
                         ["Bài - cover_master.wav", "Bài - cover_master.mp3"])
        self.assertTrue(all(p.parent == self.tmp / "mastered" for p in paths))
        self.assertFalse(m.already_mastered(src, "wav"))
        paths[0].parent.mkdir()
        paths[0].write_bytes(b"done")
        self.assertTrue(m.already_mastered(src, "wav"))
        self.assertFalse(m.already_mastered(src, "both"))
        with self.assertRaises(m.MasterError):
            m.master_paths(src, "flac")

    def test_skip_existing_does_not_call_ffmpeg(self):
        src = self.tmp / "a.wav"
        src.write_bytes(b"x")
        dest = m.master_paths(src, "wav")[0]
        dest.parent.mkdir()
        dest.write_bytes(b"old")
        with mock.patch.object(m, "_ffmpeg") as ff:
            res = m.master_file(src, _cfg(), log=lambda _: None)
        self.assertEqual(res["status"], "skipped")
        ff.assert_not_called()
        self.assertEqual(dest.read_bytes(), b"old")

    def test_wait_ready_rules(self):
        f = self.tmp / "a.wav"
        self.assertFalse(m.wait_ready(f, 0.2, timeout_sec=0.5, poll=0.05))   # chưa có
        f.write_bytes(b"")
        self.assertFalse(m.wait_ready(f, 0.2, timeout_sec=0.5, poll=0.05))   # 0 byte
        f.write_bytes(b"abc")
        part = self.tmp / "a.wav.crdownload"
        part.write_bytes(b"")
        self.assertFalse(m.wait_ready(f, 0.2, timeout_sec=0.5, poll=0.05))   # còn file dở
        part.unlink()
        self.assertTrue(m.wait_ready(f, 0.2, timeout_sec=2, poll=0.05))
        self.assertFalse(m.wait_ready(self.tmp / "b.wav.part", 0.1, timeout_sec=1))

    def test_wait_ready_waits_until_size_stops_changing(self):
        f = self.tmp / "grow.wav"
        f.write_bytes(b"a")
        stop = time.monotonic() + 0.6

        def grow():
            while time.monotonic() < stop:
                with f.open("ab") as h:
                    h.write(b"b")
                time.sleep(0.05)

        t = threading.Thread(target=grow)
        t.start()
        t0 = time.monotonic()
        self.assertTrue(m.wait_ready(f, 0.3, timeout_sec=5, poll=0.05))
        self.assertGreaterEqual(time.monotonic() - t0, 0.8)
        t.join()

    def test_missing_ffmpeg_is_reported_not_raised(self):
        logs = []
        cfg = _cfg(ffmpeg_path="khong-co-ffmpeg-xyz")
        state = m.check_ffmpeg(cfg, log=logs.append)
        self.assertFalse(state["ok"])
        self.assertIn("gyan.dev", state["error"])
        self.assertIn("tải nhạc bình thường", logs[-1])
        src = self.tmp / "a.wav"
        src.write_bytes(b"x")
        self.assertEqual(m.master_batch([src], expected=2, log=logs.append, cfg=cfg), [])
        self.assertTrue(any("bỏ qua bước master" in x for x in logs))

    def test_disabled_does_nothing(self):
        with mock.patch.object(m, "master_file") as mf:
            self.assertEqual(m.master_batch([self.tmp / "a.wav"], cfg=_cfg(enabled=False),
                                            log=lambda _: None), [])
        mf.assert_not_called()

    def test_one_version_failed_still_masters_the_other(self):
        logs = []
        src = self.tmp / "a.wav"
        src.write_bytes(b"x")
        with mock.patch.object(m, "resolve_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(m, "master_file",
                                  return_value={"status": "done"}) as mf:
            res = m.master_batch([src], expected=2, log=logs.append, cfg=_cfg())
        self.assertEqual(res, [{"status": "done"}])
        mf.assert_called_once()
        self.assertTrue(any("1/2" in x for x in logs))
        self.assertIn("1/2", (self.tmp / "mastered" / m.LOG_NAME).read_text(encoding="utf-8"))

    def test_ffmpeg_error_keeps_original_and_writes_stderr_log(self):
        src = self.tmp / "a.wav"
        src.write_bytes(b"RIFF-original")
        bad = subprocess.CompletedProcess([], 1, "", "Lỗi giả: filter hỏng")
        with mock.patch.object(m, "resolve_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(m, "wait_ready", return_value=True), \
                mock.patch.object(m, "measure", return_value={"input_i": "-20",
                                                              "input_tp": "-3"}), \
                mock.patch.object(m, "_ffmpeg", return_value=bad):
            res = m.master_file(src, _cfg(), log=lambda _: None)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(src.read_bytes(), b"RIFF-original")
        log = (self.tmp / "mastered" / m.LOG_NAME).read_text(encoding="utf-8")
        self.assertIn("filter hỏng", log)
        self.assertEqual(list((self.tmp / "mastered").glob("*.wav")), [])


@unittest.skipUnless(FFMPEG, "máy không có ffmpeg")
class RealFfmpegTests(unittest.TestCase):
    """Master thật 2 file mẫu rồi đo lại: Integrated ±0.5 LU, True Peak ≤ -1 dBTP."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.files = []
        sources = [  # 2 «bài» khác nhau: 1 bản nhỏ tiếng, 1 bản to + nhiều bass
            ("Bai A - cover.wav", "sine=f=220:d=20,volume=0.12", "anoisesrc=c=pink:d=20:a=0.05"),
            ("Bai B - cover.wav", "sine=f=55:d=20,volume=0.7", "anoisesrc=c=pink:d=20:a=0.3"),
        ]
        for (name, a, b), rate in zip(sources, ("48000", "44100")):
            path = cls.tmp / name
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", a,
                            "-f", "lavfi", "-i", b, "-filter_complex",
                            "[0][1]amix=inputs=2:normalize=0,aformat=channel_layouts=stereo",
                            "-metadata", "title=Bai mau", "-ar", rate, "-c:a", "pcm_s16le",
                            str(path)], check=True)
            cls.files.append(path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _check(self, preset: str, fmt: str = "wav"):
        cfg = _cfg(preset=preset, output_format=fmt, stable_seconds=0.2)
        originals = {f: f.read_bytes() for f in self.files}
        logs = []
        res = m.master_batch(self.files, expected=2, log=logs.append, cfg=cfg)
        self.assertEqual([r["status"] for r in res], ["done", "done"], logs)
        target = cfg["presets"][preset]["lufs"]
        for r in res:
            for out in map(Path, r["outputs"]):
                got = m.measure(FFMPEG, out, target)
                self.assertLessEqual(abs(float(got["input_i"]) - target), 0.5, (out, got))
                self.assertLessEqual(float(got["input_tp"]), -1.0 + 1e-6, (out, got))
        for f, data in originals.items():        # file gốc không bị đụng
            self.assertEqual(f.read_bytes(), data)
        return res

    def test_natural_wav_24bit_48k_with_metadata(self):
        res = self._check("natural")
        out = Path(res[0]["outputs"][0])
        self.assertEqual(out.name, "Bai A - cover_master.wav")
        probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(out)],
                               capture_output=True, text=True).stderr
        self.assertIn("pcm_s24le", probe)
        self.assertIn("48000 Hz", probe)
        self.assertIn("Bai mau", probe)
        again = m.master_batch(self.files, cfg=_cfg(stable_seconds=0.2), log=lambda _: None)
        self.assertEqual([r["status"] for r in again], ["skipped", "skipped"])
        shutil.rmtree(self.tmp / "mastered")

    def test_loud_and_dynamic_mp3(self):
        for preset in ("loud", "dynamic"):
            self._check(preset, "mp3")
            shutil.rmtree(self.tmp / "mastered")


if __name__ == "__main__":
    unittest.main()
