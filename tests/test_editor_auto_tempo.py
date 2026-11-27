"""Kiểm thử cơ chế tự động căn Tempo Suno Song Editor về đúng 100% độ dài gốc."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sqlmodel import SQLModel, Session, create_engine

from backend.cover import suno_cover, suno_jobs
from backend.models import CoverSettings, Project, SourceSong
from backend.routers import sources as sources_router


def _write_silence_wav(path: Path, seconds: float, sr: int = 8000) -> Path:
    nframes = int(round(seconds * sr))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * nframes)
    return path


def _bare_driver() -> suno_cover.CoverDriver:
    drv = suno_cover.CoverDriver.__new__(suno_cover.CoverDriver)
    drv.logs = []
    drv._log = drv.logs.append
    drv._wait = lambda ms: None
    drv.dry_run = False
    drv.debug_dir = None
    drv.page = SimpleNamespace(url="https://suno.com/edit/abc")
    drv._wait_editor_loaded = lambda *a, **k: None
    drv._unlock_editor_manual_bpm = lambda: None
    return drv


class ComputeDurationMatchedBpmTests(unittest.TestCase):
    def test_exact_proportional_examples(self):
        # 4.5x: 270s -> 60s
        self.assertEqual(suno_cover.compute_duration_matched_bpm(144, 60.0, 270.0), 32)
        self.assertEqual(suno_cover.compute_duration_matched_bpm(180, 60.0, 270.0), 40)
        self.assertEqual(suno_cover.compute_duration_matched_bpm(120, 60.0, 270.0), 27)

    def test_clamps_to_suno_bounds(self):
        self.assertEqual(suno_cover.compute_duration_matched_bpm(45, 60.0, 270.0), 20)
        self.assertEqual(suno_cover.compute_duration_matched_bpm(250, 300.0, 100.0), 300)


class SetEditorTempoForDurationTests(unittest.TestCase):
    def test_converges_in_one_pass_when_timeline_matches_100_percent(self):
        drv = _bare_driver()
        state = {"bpm": 180}
        set_calls: list[int] = []

        def fake_read_bpm():
            return state["bpm"]

        def fake_read_dur():
            # B * D = 180 * 60 = 10800 -> tai 40 BPM dat dung 270.0s
            return 10800.0 / state["bpm"]

        def fake_set_bpm(b: int) -> int:
            set_calls.append(b)
            state["bpm"] = b
            return b

        drv.read_editor_tempo = fake_read_bpm
        drv.read_editor_duration_seconds = fake_read_dur
        drv.set_editor_tempo = fake_set_bpm

        actual = drv.set_editor_tempo_for_duration(270.0, fallback_bpm=32, adjusted_duration_sec=60.0)
        self.assertEqual(actual, 40)
        self.assertEqual(set_calls, [40])

    def test_closed_loop_corrects_when_suno_beat_grid_shifts(self):
        drv = _bare_driver()
        state = {"bpm": 150}
        set_calls: list[int] = []
        # Gia lap Suno bi lech luoi beat: o 33 BPM lai dai 295s thay vi 272.7s,
        # sau khi bu len 36 BPM moi ve sat 270.4s (B*D_thuc = 9735).
        durations = {150: 60.0, 33: 295.0, 36: 270.4}

        drv.read_editor_tempo = lambda: state["bpm"]
        drv.read_editor_duration_seconds = lambda: durations[state["bpm"]]

        def fake_set_bpm(b: int) -> int:
            set_calls.append(b)
            state["bpm"] = b
            return b

        drv.set_editor_tempo = fake_set_bpm

        actual = drv.set_editor_tempo_for_duration(270.0, fallback_bpm=32, adjusted_duration_sec=60.0)
        self.assertEqual(actual, 36)
        self.assertEqual(set_calls, [33, 36])

    def test_picks_closest_integer_without_oscillating(self):
        drv = _bare_driver()
        state = {"bpm": 160}
        set_calls: list[int] = []
        # 160*60/270 = 35.55 -> thu 36 (268s, lech 2s), neu thu 35 (276s, lech 6s)
        # Gia lap lan dau tinh ra 35 (lech 6s > half_step), bu sang 36 (lech 2s) -> chot 36.
        durations = {160: 59.0, 35: 276.0, 36: 268.0}

        drv.read_editor_tempo = lambda: state["bpm"]
        drv.read_editor_duration_seconds = lambda: durations[state["bpm"]]

        def fake_set_bpm(b: int) -> int:
            set_calls.append(b)
            state["bpm"] = b
            return b

        drv.set_editor_tempo = fake_set_bpm

        actual = drv.set_editor_tempo_for_duration(270.0, fallback_bpm=32, adjusted_duration_sec=59.0)
        self.assertEqual(actual, 36)
        self.assertEqual(set_calls, [35, 36])

    def test_keeps_ratio_result_when_dom_duration_does_not_update(self):
        drv = _bare_driver()
        state = {"bpm": 180}
        set_calls: list[int] = []

        drv.read_editor_tempo = lambda: state["bpm"]
        # DOM luon tra 60.0 du BPM da doi -> dung ngay tai 40, khong lap sai.
        drv.read_editor_duration_seconds = lambda: 60.0

        def fake_set_bpm(b: int) -> int:
            set_calls.append(b)
            state["bpm"] = b
            return b

        drv.set_editor_tempo = fake_set_bpm

        actual = drv.set_editor_tempo_for_duration(270.0, fallback_bpm=32, adjusted_duration_sec=60.0)
        self.assertEqual(actual, 40)
        self.assertEqual(set_calls, [40])

    def test_falls_back_when_initial_bpm_unreadable(self):
        drv = _bare_driver()
        drv.read_editor_tempo = lambda: None
        drv.set_editor_tempo = mock.MagicMock(return_value=35)

        actual = drv.set_editor_tempo_for_duration(270.0, fallback_bpm=35, adjusted_duration_sec=60.0)
        self.assertEqual(actual, 35)
        drv.set_editor_tempo.assert_called_once_with(35)


class PrepareCoverAndWorkflowIntegrationTests(unittest.TestCase):
    def test_prepare_cover_passes_target_duration_only_when_provided(self):
        drv = _bare_driver()
        for name in (
            "open_create_page", "_prepare_create_form", "_remix_cover_from_library",
            "select_model", "fill_styles", "fill_title", "fill_song_lyrics",
            "ensure_more_options", "fill_exclusions", "set_vocal_gender",
            "set_max_mode", "set_creative_sliders", "check_rejection", "save_debug",
        ):
            setattr(drv, name, mock.MagicMock())
        drv.read_credits = lambda: 500
        drv._settle = lambda *a: True
        drv.cover_ready = lambda: True
        drv.prepare_editor_source = mock.MagicMock(return_value="saved-id")

        drv.prepare_cover(
            Path("adj.wav"), "Bài A", "[Verse]\nA_B", "female", 10,
            editor_bpm=32, styles="Ballad", target_duration_sec=240.0,
        )
        drv.prepare_editor_source.assert_called_once_with(
            Path("adj.wav"), 32,
            lyrics="[Verse]\nA_B", styles="Ballad", target_duration_sec=240.0,
        )

    def test_suno_jobs_auto_measures_original_duration_and_respects_manual_bpm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orig_wav = _write_silence_wav(root / "orig.wav", 24.0)
            adj_wav = _write_silence_wav(root / "adj.wav", 6.0)
            db_path = root / "test.db"
            eng = create_engine(f"sqlite:///{db_path}")
            try:
                SQLModel.metadata.create_all(eng)
                with Session(eng) as s:
                    proj = Project(name="P1", music_style="Ballad", music_line="VN")
                    s.add(proj)
                    s.commit()
                    s.refresh(proj)
                    s.add(CoverSettings(project_id=proj.id))
                    auto_src = SourceSong(
                        project_id=proj.id,
                        title="Auto Song",
                        lyrics_text="Câu một\nCâu hai",
                        file_path=str(orig_wav),
                        tempo_file_path=str(adj_wav),
                        tempo_factor=4.0,
                        vocal_gender="female",
                        suno_editor_bpm=0,
                        suno_style_prompt="Ballad, 72 BPM",
                        suno_style_signature="",
                    )
                    manual_src = SourceSong(
                        project_id=proj.id,
                        title="Manual Song",
                        lyrics_text="Câu một\nCâu hai",
                        file_path=str(orig_wav),
                        tempo_file_path=str(adj_wav),
                        tempo_factor=4.0,
                        vocal_gender="female",
                        suno_editor_bpm=55,
                        suno_style_prompt="Ballad, 72 BPM",
                        suno_style_signature="",
                    )
                    s.add(auto_src)
                    s.add(manual_src)
                    s.commit()
                    s.refresh(auto_src)
                    s.refresh(manual_src)
                    auto_id, manual_id = auto_src.id, manual_src.id

                captured: list[dict] = []

                class FakeDriver:
                    def __init__(self, page, **kwargs):
                        self.page = page
                        self.last_editor_tempo = 41

                    def prepare_cover(self, original, title, lyrics, gender, min_credits, **kwargs):
                        captured.append({"title": title, **kwargs})
                        if kwargs.get("target_duration_sec"):
                            self.last_editor_tempo = 41
                        else:
                            self.last_editor_tempo = int(kwargs.get("editor_bpm", 32))

                    def save_debug(self, name):
                        return ""

                fake_dir_res = SimpleNamespace(
                    lyrics="[Verse 1]\nCâu_một\nCâu_hai",
                    style="Vietnamese ballad, 72 BPM, warm piano",
                    exclude_styles="heavy metal",
                    sliders={"weirdness": 25, "style_influence": 80, "variety": 0, "audio_influence": 50},
                    max_mode=True,
                    vocal_gender="female",
                    source="local",
                    raw_package={"suno": {"weirdness": 25}},
                )

                with mock.patch.object(suno_jobs, "engine", eng), \
                     mock.patch.object(suno_jobs, "CoverDriver", FakeDriver), \
                     mock.patch.object(suno_jobs, "run_music_director", return_value=fake_dir_res), \
                     mock.patch.object(suno_jobs, "get_workflow", return_value={"semi_manual": False}), \
                     mock.patch.object(suno_jobs, "_is_automated_batch_project", return_value=False), \
                     mock.patch.object(suno_jobs, "record_login"), \
                     mock.patch.object(suno_jobs.nct_jobs, "cover_dir", return_value=root / "covers"):
                    suno_jobs._process(auto_id, SimpleNamespace(), dry=True)
                    suno_jobs._process(manual_id, SimpleNamespace(), dry=True)

                self.assertEqual(len(captured), 2)
                self.assertAlmostEqual(captured[0].get("target_duration_sec"), 24.0, places=1)
                self.assertNotIn("target_duration_sec", captured[1])
                self.assertEqual(captured[1].get("editor_bpm"), 55)

                with Session(eng) as s:
                    self.assertEqual(s.get(SourceSong, auto_id).suno_editor_bpm, 41)
                    self.assertEqual(s.get(SourceSong, manual_id).suno_editor_bpm, 55)
            finally:
                eng.dispose()

    def test_export_tempo_resets_saved_editor_bpm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orig_wav = _write_silence_wav(root / "orig.wav", 10.0)
            out_wav = _write_silence_wav(root / "out.wav", 5.0)
            db_path = root / "test.db"
            eng = create_engine(f"sqlite:///{db_path}")
            try:
                SQLModel.metadata.create_all(eng)
                with Session(eng) as s:
                    proj = Project(name="P2", music_style="Ballad")
                    s.add(proj)
                    s.commit()
                    s.refresh(proj)
                    src = SourceSong(
                        project_id=proj.id,
                        title="Bài X",
                        lyrics_text="Lời hát",
                        file_path=str(orig_wav),
                        suno_editor_bpm=42,
                        suno_editor_song_id="old-edit-id",
                    )
                    s.add(src)
                    s.commit()
                    s.refresh(src)
                    with mock.patch.object(sources_router.tempo, "export_file", return_value=out_wav), \
                         mock.patch.object(sources_router.cover_qc, "review_async"):
                        sources_router.export_tempo(src.id, sources_router.TempoIn(tempo_factor=2.0), s)
                    s.refresh(src)
                    self.assertEqual(src.suno_editor_bpm, 0)
                    self.assertEqual(src.suno_editor_song_id, "")
            finally:
                eng.dispose()


if __name__ == "__main__":
    unittest.main()
