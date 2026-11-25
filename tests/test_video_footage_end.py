"""Quy trình footage (2026-11-09): có footage thì mỗi clip AI chạy đúng 1 lần,
sau đó các footage (màu phim, giảm saturation, hạt film) lặp liên tục tới hết
video; nhạc giữ nguyên độ dài. Test ghép thật bằng ffmpeg (video nhỏ)."""
import io
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, SQLModel, create_engine

from backend.models import Project
from backend.routers import video
from backend.video import config
from backend.video.assembler import assemble_video_blend, probe_duration

W, H, FPS = 320, 180, 30


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _pixel(path, t, x, y):
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
         "-vf", f"format=rgb24,crop=2:2:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout
    return tuple(raw[:3])


@unittest.skipUnless(shutil.which("ffmpeg"), "cần ffmpeg")
class FootageLoopRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="footage-loop-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clips = []
        for i, color in enumerate(("blue", "navy", "darkblue", "blue")):
            c = self.root / f"clip_{i:02d}.mp4"
            _ff("-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={FPS}:d=4",
                "-pix_fmt", "yuv420p", str(c))
            self.clips.append(str(c))
        self.audio = self.root / "mix.wav"
        _ff("-f", "lavfi", "-i", "sine=frequency=440:duration=30", str(self.audio))
        self.red = self.root / "red.mp4"
        _ff("-f", "lavfi", "-i", f"color=c=red:s={W}x{H}:r={FPS}:d=3",
            "-pix_fmt", "yuv420p", str(self.red))
        self.green = self.root / "green.mp4"
        _ff("-f", "lavfi", "-i", f"color=c=lime:s={W}x{H}:r={FPS}:d=3",
            "-pix_fmt", "yuv420p", str(self.green))
        # Giữa màn chiếu (không có nền → màn chiếu căn giữa).
        self.xy = (W // 2, int(H * 0.18) + int(H * 0.43) // 2)

    def test_clips_once_then_footage_loops_to_the_end(self):
        out = self.root / "final" / "final.mp4"
        res = assemble_video_blend(
            self.clips, str(self.audio), str(out), blend_seconds=0.5, slow_speed=1.0,
            width=W, height=H, fps=FPS, footage_paths=[str(self.red), str(self.green)])
        self.assertEqual(res["footage_position"], "loop_to_end")
        self.assertTrue(res["clips_play_once"])
        self.assertEqual(res["footage_clips"], 2)
        # 4 clip × 4s, 3 lần chuyển cảnh 0.5s trong lượt duy nhất → footage ~ giây 14.
        self.assertLess(res["footage_start"], 16.0)
        self.assertAlmostEqual(res["footage_loop_seconds"], 5.0, delta=0.1)
        self.assertAlmostEqual(probe_duration(str(out)), 30.0, delta=0.3)
        # Không quay lại clip AI: từ footage_start tới cuối chỉ có đỏ/xanh lá.
        colors = []
        for t in (18.0, 21.0, 24.0, 27.0, 29.5):
            r, g, b = _pixel(out, t, *self.xy)
            self.assertLess(b, max(r, g), (t, r, g, b))
            colors.append("r" if r > g else "g")
        self.assertIn("r", colors)
        self.assertIn("g", colors)
        # Footage đỏ xuất hiện nhiều lần (lặp lại).
        self.assertGreaterEqual(colors.count("r"), 2, colors)
        r, g, b = _pixel(out, 6.0, *self.xy)
        self.assertGreater(b, r, (r, g, b))

    def test_without_footage_keeps_cycle_loop(self):
        out = self.root / "final2" / "final.mp4"
        res = assemble_video_blend(
            self.clips, str(self.audio), str(out), blend_seconds=0.5, slow_speed=1.0,
            width=W, height=H, fps=FPS)
        self.assertIsNone(res["footage_position"])
        self.assertFalse(res["clips_play_once"])
        self.assertAlmostEqual(probe_duration(str(out)), 30.0, delta=0.3)


class FootageApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="footage-api-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{root / 'app.sqlite'}")
        SQLModel.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as db:
            p = Project(name="Footage End")
            db.add(p)
            db.commit()
            self.pid = p.id
        patches = [patch.object(config, "MEDIA_ROOT", root / "media"),
                   patch("backend.routers.video.video_job_manager.is_busy", return_value=False),
                   patch("backend.video.assembler.probe_duration", return_value=5.0),
                   patch("backend.video.assembler.probe_fps", return_value=30.0)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

    def _upload(self, name):
        return video.upload_footage(self.pid, UploadFile(filename=name,
                                                         file=io.BytesIO(b"x")), self.db)

    def test_requires_footage(self):
        with self.assertRaises(HTTPException) as cm:
            video.render_with_footage(self.pid, self.db)
        self.assertEqual(cm.exception.status_code, 400)

    def test_submits_assemble_with_footage(self):
        self._upload("real.mp4")
        with patch("backend.routers.video.video_job_manager.submit") as sub:
            video.render_with_footage(self.pid, self.db)
        self.assertTrue(sub.call_args.kwargs["footage_at_end"])
        self.assertEqual(sub.call_args.args[1], "assemble")

    def test_multiple_uploads_are_kept_and_deleted_by_name(self):
        self.assertEqual(self._upload("a.mp4")["count"], 1)
        self.assertEqual(self._upload("b.mp4")["count"], 2)
        dup = self._upload("a.mp4")
        self.assertEqual(dup["name"], "a (2).mp4")
        self.assertEqual(dup["count"], 3)
        names = {f.name for f in config.footage_files(self.pid, "Footage End")}
        self.assertEqual(names, {"a.mp4", "b.mp4", "a (2).mp4"})
        r = video.delete_footage(self.pid, name="b.mp4", db=self.db)
        self.assertEqual(r["count"], 1)
        names = {f.name for f in config.footage_files(self.pid, "Footage End")}
        self.assertEqual(names, {"a.mp4", "a (2).mp4"})
        r = video.delete_footage(self.pid, name=None, db=self.db)
        self.assertEqual(r["count"], 2)
        self.assertEqual(config.footage_files(self.pid, "Footage End"), [])


if __name__ == "__main__":
    unittest.main()
