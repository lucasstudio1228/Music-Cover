"""Bảng cam Suno sau Create (LIVE 2026-11-09): «Couldn't generate that. Your lyrics
contain copyrighted material. Please change it and try again.» → tool chỉ báo popup;
người dùng tự sửa lyrics + tự Create trên Suno, tool theo dõi 2 bản mới. Tool không
điền lyrics, không bấm Create lại. Không mở trình duyệt."""
from pathlib import Path
import sys
import threading
import time
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

TOAST = ("Couldn't generate that. Your lyrics contain copyrighted material. "
         "Please change it and try again.")
OLD = "Câu một của bài\nCâu hai của bài"


class _Song:
    def __init__(self, i):
        self.song_id = i


class FakeDrv:
    """Mô phỏng: wait_for_new_songs trả 2 ID; toast hiện sau ``toast_after`` lần đọc."""

    def __init__(self, toast_after=None, stale=False):
        self.reads = 0
        self.toast_after = toast_after
        self.stale = stale

    def wait_for_new_songs(self, *a, **k):
        return [_Song("id-a"), _Song("id-b")]

    def create_rejection_text(self):
        self.reads += 1
        if self.stale and self.reads <= 2:
            return TOAST
        if self.stale and self.reads <= 4:
            return ""
        if self.toast_after is not None and self.reads > self.toast_after:
            return TOAST
        return ""

    def _wait(self, ms):
        pass


class CreateWatchTests(unittest.TestCase):
    def setUp(self):
        from backend.cover import suno_jobs
        self.jobs = suno_jobs
        for name, val in (("_mark", mock.MagicMock()), ("FIRST_DOWNLOAD_WAIT_SEC", 3)):
            p = mock.patch.object(suno_jobs, name, val)
            p.start()
            self.addCleanup(p.stop)

    def _run(self, drv, stale=""):
        return self.jobs._create_and_watch(drv, 1, set(), stale, lambda m: None,
                                           lambda m: None)

    def test_no_toast_returns_ids(self):
        self.assertEqual(self._run(FakeDrv()), ["id-a", "id-b"])

    def test_toast_right_after_ids(self):
        with self.assertRaises(self.jobs._CopyrightToast) as cm:
            self._run(FakeDrv(toast_after=0))
        self.assertIn("copyrighted", str(cm.exception))

    def test_toast_during_wait_before_download(self):
        with self.assertRaises(self.jobs._CopyrightToast):
            self._run(FakeDrv(toast_after=1))

    def test_stale_toast_ignored_until_it_reappears(self):
        drv = FakeDrv(stale=True)
        # Bảng cũ đọng lại → biến mất → không hiện lại: không tính là lỗi mới.
        self.assertEqual(self._run(drv, stale=TOAST), ["id-a", "id-b"])

    def test_wait_error_with_toast_text_becomes_toast(self):
        from backend.video.suno_driver import SunoSubmissionUncertain
        drv = FakeDrv()
        drv.wait_for_new_songs = mock.Mock(side_effect=SunoSubmissionUncertain(
            f"Suno báo lỗi sau Create: «{TOAST}» — lượt này KHÔNG được nhận."))
        drv.create_rejection_text = lambda: ""
        with self.assertRaises(self.jobs._CopyrightToast) as cm:
            self._run(drv)
        self.assertEqual(str(cm.exception), TOAST)

    def test_other_wait_errors_still_raise(self):
        from backend.video.suno_driver import SunoSubmissionUncertain
        drv = FakeDrv()
        drv.wait_for_new_songs = mock.Mock(side_effect=SunoSubmissionUncertain("timeout"))
        with self.assertRaises(SunoSubmissionUncertain):
            self._run(drv)


class ManualDrv:
    """Suno sau bảng cam: người dùng tự Create → 2 ID mới xuất hiện sau vài nhịp."""

    def __init__(self, appear_after=None):
        self.ticks = 0
        self.appear_after = appear_after
        self._gen_response_ids = set()
        self.filled = self.clicked = False

    def snapshot_song_ids(self):
        ids = {"old-1", "dead-1"}
        if self.appear_after is not None and self.ticks >= self.appear_after:
            ids |= {"new-1", "new-2"}
        return ids

    def _wait(self, ms):
        self.ticks += 1

    def fill_song_lyrics(self, text):
        self.filled = True

    def click_create(self):
        self.clicked = True


class AwaitManualCreateTests(unittest.TestCase):
    def setUp(self):
        from backend.cover import suno_jobs
        self.jobs = suno_jobs
        self.mark = mock.MagicMock()
        p = mock.patch.object(suno_jobs, "_mark", self.mark)
        p.start()
        self.addCleanup(p.stop)
        self.alerts = []

    def _run(self, drv):
        return self.jobs._await_manual_create(drv, 7, TOAST, 1, lambda m: None,
                                              self.alerts.append)

    def test_returns_ids_user_created_without_touching_suno(self):
        drv = ManualDrv(appear_after=3)
        self.assertEqual(sorted(self._run(drv)), ["new-1", "new-2"])
        self.assertFalse(drv.filled)
        self.assertFalse(drv.clicked)
        self.assertEqual(len(self.alerts), 1)
        self.assertIn("tự bấm", self.alerts[0])
        self.assertEqual(self.mark.call_args.kwargs.get("suno_song_ids"), "")
        self.assertIsNone(self.jobs.awaiting_lyrics())

    def test_status_while_waiting_then_skip(self):
        drv = ManualDrv()
        drv._wait = lambda ms: time.sleep(0.01)
        out = {}

        def run():
            try:
                self._run(drv)
            except Exception as e:  # noqa: BLE001
                out["err"] = e
        t = threading.Thread(target=run)
        t.start()
        for _ in range(200):
            if self.jobs.awaiting_lyrics():
                break
            time.sleep(0.01)
        st = self.jobs.status()["awaiting_lyrics"]
        self.assertEqual(st["source_id"], 7)
        self.assertIn("copyrighted", st["why"])
        self.assertFalse(self.jobs.skip_lyrics(8))
        self.assertTrue(self.jobs.skip_lyrics(7))
        t.join(5)
        from backend.cover.suno_cover import SunoCoverRejected
        self.assertIsInstance(out.get("err"), SunoCoverRejected)
        self.assertIsNone(self.jobs.awaiting_lyrics())

    def test_timeout(self):
        from backend.cover.suno_cover import SunoCoverRejected
        with mock.patch.object(self.jobs, "MANUAL_WAIT_SEC", 0):
            with self.assertRaises(SunoCoverRejected):
                self._run(ManualDrv())

    def test_stop_cancels(self):
        from backend.video.browser_base import OperationCancelled
        self.jobs._stop.set()
        try:
            with self.assertRaises(OperationCancelled):
                self._run(ManualDrv())
        finally:
            self.jobs._stop.clear()

    def test_no_paste_lyrics_api_any_more(self):
        self.assertFalse(hasattr(self.jobs, "provide_lyrics"))


class BatchDrv(ManualDrv):
    """LIVE 09:15: ID 2 bản bị từ chối tới MUỘN (sau bảng cam), rồi mới tới 2 bản
    người dùng tự Create. Phải nhận đúng 2 bản của người dùng."""

    def __init__(self):
        super().__init__()
        self._gen_events = ["generate_sent"]
        self._gen_batches = []

    def snapshot_song_ids(self):
        ids = {"old-1"}
        if self.ticks >= 1:
            ids |= {"rej-1", "rej-2"}
        if self.ticks >= 3:
            ids |= {"user-1", "user-2"}
        return ids

    def _wait(self, ms):
        self.ticks += 1
        if self.ticks == 1:
            self._gen_batches.append(["rej-1", "rej-2"])
            self._gen_response_ids |= {"rej-1", "rej-2"}
        if self.ticks == 3:
            self._gen_events.append("generate_sent")
            self._gen_batches.append(["user-1", "user-2"])
            self._gen_response_ids |= {"user-1", "user-2"}


class LateRejectedIdsTests(unittest.TestCase):
    def setUp(self):
        from backend.cover import suno_jobs
        self.jobs = suno_jobs
        p = mock.patch.object(suno_jobs, "_mark", mock.MagicMock())
        p.start()
        self.addCleanup(p.stop)

    def test_late_rejected_ids_are_not_taken(self):
        ids = self.jobs._await_manual_create(BatchDrv(), 7, TOAST, 1, lambda m: None,
                                             lambda m: None)
        self.assertEqual(sorted(ids), ["user-1", "user-2"])

    def test_rejected_batch_already_there(self):
        drv = BatchDrv()
        drv._gen_batches.append(["rej-1", "rej-2"])
        drv.ticks = 1
        ids = self.jobs._await_manual_create(drv, 7, TOAST, 1, lambda m: None,
                                             lambda m: None)
        self.assertEqual(sorted(ids), ["user-1", "user-2"])

    def test_driver_records_batches_per_generate(self):
        from backend.video.suno_driver import SunoDriver
        drv = SunoDriver.__new__(SunoDriver)
        drv._gen_events, drv._gen_bad, drv._gen_logical_errors = [], [], []
        drv._gen_response_ids, drv._gen_batches = set(), []
        drv._is_generate = lambda url: True
        uid = "11111111-2222-3333-4444-555555555555"
        resp = mock.Mock(status=200, url="x")
        resp.request.method = "POST"
        resp.text = lambda: '{"clips": [{"id": "%s", "title": "a"}]}' % uid
        drv._on_response(resp)
        bad = mock.Mock(status=422, url="x")
        bad.request.method = "POST"
        drv._on_response(bad)
        self.assertEqual(drv._gen_batches, [[uid], []])


class WatchManualIdsTests(unittest.TestCase):
    def setUp(self):
        from backend.cover import suno_jobs
        self.jobs = suno_jobs
        for name, val in (("_mark", mock.MagicMock()), ("FIRST_DOWNLOAD_WAIT_SEC", 3)):
            p = mock.patch.object(suno_jobs, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_given_ids_skip_waiting_for_create(self):
        drv = FakeDrv()
        drv.wait_for_new_songs = mock.Mock(side_effect=AssertionError("không được chờ"))
        self.assertEqual(self.jobs._create_and_watch(
            drv, 1, set(), TOAST, lambda m: None, lambda m: None,
            song_ids=["new-1", "new-2"]), ["new-1", "new-2"])

    def test_toast_again_after_manual_create(self):
        drv = FakeDrv(stale=True)
        drv.reads = 0
        orig = drv.create_rejection_text

        def again():
            t = orig()
            return t or (TOAST if drv.reads > 3 else "")
        drv.create_rejection_text = again
        with self.assertRaises(self.jobs._CopyrightToast):
            self.jobs._create_and_watch(drv, 1, set(), TOAST, lambda m: None,
                                        lambda m: None, song_ids=["n1", "n2"])


class DriverToastTests(unittest.TestCase):
    def _drv(self, texts):
        from backend.cover.suno_cover import CoverDriver
        drv = CoverDriver.__new__(CoverDriver)
        drv.page = mock.Mock()
        drv.page.evaluate = mock.Mock(side_effect=lambda js, *a: texts
                                      if "createTreeWalker" in js else {})
        return drv

    def test_orange_toast_detected(self):
        self.assertIn("copyrighted", self._drv([TOAST]).create_rejection_text())

    def test_terms_dialog_not_counted(self):
        self.assertEqual(self._drv(["By uploading you confirm you own the rights to "
                                    "this copyright"]).create_rejection_text(), "")

    def test_gen_state_regex_covers_orange_toast(self):
        from backend.video import suno_driver
        self.assertIn("couldn.?t generate", suno_driver._JS_GEN_STATE)


class CopyrightSkipApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.routers import sources
        self.skip = mock.MagicMock(return_value=True)
        p = mock.patch.object(sources.suno_jobs, "skip_lyrics", self.skip)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)

    def test_skip(self):
        self.assertEqual(self.client.post("/api/sources/5/suno/copyright-skip").status_code, 200)
        self.skip.assert_called_once_with(5)

    def test_skip_when_not_waiting(self):
        self.skip.return_value = False
        self.assertEqual(self.client.post("/api/sources/5/suno/copyright-skip").status_code, 409)

    def test_paste_lyrics_endpoint_removed(self):
        r = self.client.post("/api/sources/5/suno/replacement-lyrics",
                             json={"lyrics_text": "x", "authorized_lyrics": True})
        self.assertIn(r.status_code, (404, 405))


if __name__ == "__main__":
    unittest.main()
