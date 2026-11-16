"""Chế độ BÁN THỦ CÔNG (2026-11-09): người dùng tự chỉnh Tempo + Save as New Song
trong Suno Editor và tự bấm Create; tool upload, mở Editor, Remix → Cover, điền
lyrics/style/thông số, nhận 2 bản đúng lượt Create, tải về, master. Không mở
trình duyệt thật."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backend.cover import suno_jobs
from backend.cover.suno_cover import CoverDriver, SunoCoverRejected

TOAST = "Couldn't generate that. Your lyrics contain copyrighted material."
EDITOR = "11111111-1111-1111-1111-111111111111"
SAVED = "22222222-2222-2222-2222-222222222222"


def bare_driver():
    drv = CoverDriver.__new__(CoverDriver)
    drv.page = SimpleNamespace(url=f"https://suno.com/edit/{EDITOR}")
    drv.logs, drv.humans = [], []
    drv._log = drv.logs.append
    drv.on_human = drv.humans.append
    return drv


class WaitUserEditorSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "Em Là Nhất Miền Tây - tempo.wav"
        self.file.write_bytes(b"x")

    def _drv(self, save_after=3, tempo=72):
        drv = bare_driver()
        drv.ticks = 0
        for name in ("_clear_library_filters", "_open_uploaded_audio_in_editor",
                     "_wait_upload_dialog_clear", "_wait_editor_loaded", "check_rejection"):
            setattr(drv, name, mock.MagicMock())
        drv.set_editor_tempo = mock.MagicMock(side_effect=AssertionError("tool không chỉnh Tempo"))
        drv.save_editor_as_new_song = mock.MagicMock(side_effect=AssertionError("tool không bấm Save"))
        drv.snapshot_song_ids = lambda: {"old-1"}
        drv._pick_saved_song = lambda fresh, hint: ""
        drv.read_editor_tempo = lambda: tempo

        def wait(ms):
            drv.ticks += 1
            if drv.ticks >= save_after:
                drv.page.url = f"https://suno.com/edit/{SAVED}"
        drv._wait = wait
        return drv

    def test_detects_song_user_saved_and_reads_tempo(self):
        drv = self._drv()
        alerts = []
        self.assertEqual(drv.wait_user_editor_save(self.file, 80, alert=alerts.append), SAVED)
        self.assertEqual(drv.last_editor_tempo, 72)
        self.assertEqual(len(alerts), 1)
        self.assertIn("Save as New Song", alerts[0])
        self.assertIn("80", alerts[0])
        drv._open_uploaded_audio_in_editor.assert_called_once()
        drv.set_editor_tempo.assert_not_called()
        drv.save_editor_as_new_song.assert_not_called()
        self.assertTrue(any("gợi ý là 80" in m for m in drv.logs))

    def test_editor_url_itself_is_not_a_saved_song(self):
        drv = self._drv(save_after=10 ** 9)
        with mock.patch("backend.cover.suno_cover.time") as t:
            now = [0.0]
            t.time = lambda: now[0]

            def wait(ms):
                now[0] += 100
            drv._wait = wait
            with self.assertRaises(Exception) as cm:
                drv.wait_user_editor_save(self.file, 80, timeout_sec=600)
        self.assertIn("Save as New Song", str(cm.exception))

    def test_library_title_match_also_detected(self):
        drv = self._drv(save_after=10 ** 9)
        # Bài lưu xuất hiện trong thư viện SAU khi tool mở Editor (URL không đổi).
        drv.snapshot_song_ids = lambda: {"old-1", SAVED} if drv.ticks >= 2 else {"old-1"}
        drv._pick_saved_song = lambda fresh, hint: SAVED if SAVED in fresh else ""
        self.assertEqual(drv.wait_user_editor_save(self.file, 80), SAVED)


class PrepareCoverManualTests(unittest.TestCase):
    def test_manual_editor_skips_tool_tempo_and_save(self):
        drv = bare_driver()
        names = ("open_create_page", "select_advanced_mode", "clear_form",
                 "ensure_more_options", "ensure_duration_auto", "_remix_cover_from_library",
                 "select_model", "fill_styles", "fill_title", "fill_song_lyrics",
                 "set_vocal_gender", "set_max_mode", "set_creative_sliders",
                 "check_rejection", "save_debug")
        for name in names:
            setattr(drv, name, mock.MagicMock())
        drv.read_credits = lambda: 500
        drv._settle = lambda *a: True
        drv.cover_ready = lambda: True
        drv.prepare_editor_source = mock.MagicMock(side_effect=AssertionError("không tự chỉnh"))
        drv.wait_user_editor_save = mock.MagicMock(return_value=SAVED)
        saved = []
        drv.prepare_cover(Path("x.wav"), "Bài", "lời", "male", 10, editor_bpm=80,
                          styles="ballad", on_editor_saved=saved.append,
                          manual_editor=True, alert=print)
        drv.wait_user_editor_save.assert_called_once()
        drv._remix_cover_from_library.assert_called_once_with(SAVED)
        drv.fill_song_lyrics.assert_called_once_with("lời")
        drv.fill_styles.assert_called_once_with("ballad")
        self.assertEqual(saved, [SAVED])


class SemiDrv:
    """Suno sau khi tool điền form: người dùng tự bấm Create."""

    def __init__(self, script):
        self.script = script          # tick → hàm đổi trạng thái
        self.ticks = 0
        self._gen_batches, self._gen_events = [], []
        self._gen_response_ids = set()
        self.toast = ""
        self.armed = 0

    def _arm_create_watch(self):
        self.armed += 1
        self._gen_batches.clear()
        self._gen_events.clear()

    def snapshot_song_ids(self):
        return {"old-1"}

    def create_rejection_text(self):
        return self.toast

    def save_debug(self, tag):
        return ""

    def click_create(self):
        raise AssertionError("tool không được bấm Create")

    def _wait(self, ms):
        self.ticks += 1
        fn = self.script.get(self.ticks)
        if fn:
            fn(self)

    def user_create(self, ids):
        self._gen_events.append("generate_sent")
        self._gen_batches.append(list(ids))


class AwaitSemiCreateTests(unittest.TestCase):
    def setUp(self):
        self.mark = mock.MagicMock()
        p = mock.patch.object(suno_jobs, "_mark", self.mark)
        p.start()
        self.addCleanup(p.stop)
        self.alerts, self.logs = [], []

    def _run(self, drv):
        return suno_jobs._await_semi_create(drv, 9, {"old-1"}, self.logs.append,
                                            self.alerts.append)

    def test_user_create_returns_two_ids(self):
        drv = SemiDrv({3: lambda d: d.user_create(["a1", "a2"])})
        self.assertEqual(self._run(drv), (["a1", "a2"], ""))
        self.assertEqual(drv.armed, 1)
        self.assertIn("tự bấm Create", self.alerts[0])
        self.assertEqual(self.mark.call_args.kwargs.get("suno_song_ids"), "")

    def test_copyright_toast_excludes_rejected_batch_then_takes_next(self):
        def toast(d):
            d._gen_events.append("generate_sent")
            d._gen_batches.append([])          # response chưa có ID
            d.toast = TOAST

        def late_rejected_ids(d):
            d._gen_batches[0].extend(["r1", "r2"])   # ID lượt bị từ chối tới MUỘN

        drv = SemiDrv({2: toast, 4: late_rejected_ids,
                       6: lambda d: d.user_create(["n1", "n2"])})
        ids, stale = self._run(drv)
        self.assertEqual(ids, ["n1", "n2"])
        self.assertEqual(stale, TOAST)
        self.assertEqual(len(self.alerts), 2)
        self.assertIn("bản quyền", self.alerts[1])
        self.assertIsNone(suno_jobs.awaiting_lyrics())

    def test_skip_during_copyright_wait(self):
        def toast(d):
            d.toast = TOAST

        def skip(d):
            self.assertEqual(suno_jobs.awaiting_lyrics()["source_id"], 9)
            suno_jobs.skip_lyrics(9)
        drv = SemiDrv({1: toast, 3: skip})
        with self.assertRaises(SunoCoverRejected):
            self._run(drv)

    def test_timeout_is_need_input(self):
        with mock.patch.object(suno_jobs, "MANUAL_WAIT_SEC", 0):
            with self.assertRaises(suno_jobs._NeedInput):
                self._run(SemiDrv({}))


class WorkflowSettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(suno_jobs, "WORKFLOW_FILE", Path(self.tmp.name) / "wf.json")
        p.start()
        self.addCleanup(p.stop)

    def test_default_off_and_toggle(self):
        self.assertFalse(suno_jobs.get_workflow()["semi_manual"])
        self.assertTrue(suno_jobs.set_workflow(True)["semi_manual"])
        self.assertTrue(suno_jobs.status()["semi_manual"])

    def test_api(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        c = TestClient(app)
        r = c.put("/api/sources/suno/workflow", json={"semi_manual": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["semi_manual"])
        self.assertTrue(c.get("/api/sources/suno/workflow").json()["semi_manual"])


if __name__ == "__main__":
    unittest.main()


class RemixCoverRetryTests(unittest.TestCase):
    """Đo LIVE 12/11/2026: bấm Cover ngay sau Save as New Song không ăn; lần sau ăn."""

    def _drv(self, results):
        drv = bare_driver()
        drv._ensure_song_open = mock.MagicMock()
        drv._wait_preparing_done = mock.MagicMock()
        drv._wait = mock.MagicMock()
        drv.page = mock.MagicMock()
        drv._remix_cover_once = mock.MagicMock(side_effect=results)
        return drv

    def test_retries_until_suno_navigates(self):
        drv = self._drv([False, True])
        drv._remix_cover_from_library(SAVED)
        self.assertEqual(drv._remix_cover_once.call_count, 2)
        drv.page.reload.assert_called_once()

    def test_gives_up_after_three_tries_without_navigating(self):
        drv = self._drv([False, False, False])
        drv._ui_changed = lambda msg, tag: RuntimeError(msg)
        with self.assertRaises(RuntimeError) as ctx:
            drv._remix_cover_from_library(SAVED)
        self.assertIn("3 lần", str(ctx.exception))
        self.assertEqual(drv._remix_cover_once.call_count, 3)
        drv.page.goto.assert_not_called()
