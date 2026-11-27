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
        # open_create_page bị mock → giả lập trình duyệt đang ở trang Create.
        drv.page = SimpleNamespace(url="https://suno.com/create")
        names = ("open_create_page", "select_advanced_mode", "clear_form",
                 "ensure_more_options", "ensure_duration_auto", "_remix_cover_from_library",
                 "select_model", "fill_styles", "fill_title", "fill_song_lyrics",
                 "fill_exclusions", "set_vocal_gender", "set_max_mode",
                 "set_creative_sliders", "check_rejection", "save_debug")
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
        self.assertEqual(drv.wait_user_editor_save.call_args.kwargs.get("lyrics"), "lời")
        self.assertEqual(drv.wait_user_editor_save.call_args.kwargs.get("styles"), "ballad")
        drv._remix_cover_from_library.assert_called_once_with(SAVED)
        drv.fill_song_lyrics.assert_called_once_with("lời")
        drv.fill_styles.assert_called_once_with("ballad")
        self.assertEqual(saved, [SAVED])

    def test_auto_editor_passes_lyrics_and_styles_to_prepare_editor_source(self):
        drv = bare_driver()
        drv.page = SimpleNamespace(url="https://suno.com/create")
        names = ("open_create_page", "select_advanced_mode", "clear_form",
                 "ensure_more_options", "ensure_duration_auto", "_remix_cover_from_library",
                 "select_model", "fill_styles", "fill_title", "fill_song_lyrics",
                 "fill_exclusions", "set_vocal_gender", "set_max_mode",
                 "set_creative_sliders", "check_rejection", "save_debug")
        for name in names:
            setattr(drv, name, mock.MagicMock())
        drv.read_credits = lambda: 500
        drv._settle = lambda *a: True
        drv.cover_ready = lambda: True
        drv.prepare_editor_source = mock.MagicMock(return_value=SAVED)
        drv.prepare_cover(Path("x.wav"), "Bài", "Câu hát một\nCâu hát hai",
                          "female", 10, editor_bpm=32, styles="Ballad AI prompt",
                          manual_editor=False)
        drv.prepare_editor_source.assert_called_once_with(
            Path("x.wav"), 32,
            lyrics="Câu hát một\nCâu hát hai", styles="Ballad AI prompt")
        drv.fill_styles.assert_called_once_with("Ballad AI prompt")


class SongEditorLyricsAndStylesTests(unittest.TestCase):
    """Song Editor Beta: bung «Add Lyrics» điền lời nối «_» + đồng bộ ô «Styles» AI."""

    def test_expands_add_lyrics_replaces_spaces_with_underscores_and_syncs_ai_styles(self):
        from backend.cover import suno_cover

        drv = bare_driver()
        drv._wait = mock.MagicMock()
        drv._click = mock.MagicMock()
        drv.page = mock.MagicMock()

        styles_box = mock.MagicMock()
        styles_state = {"val": "An electronic dance instrumental featuring a synthesizer"}
        styles_box.click = mock.MagicMock()
        styles_box.fill = lambda v: styles_state.__setitem__("val", v)
        styles_box.input_value = lambda: styles_state["val"]

        lyrics_box = mock.MagicMock()
        lyrics_state = {"val": "", "opened": False}
        lyrics_box.click = mock.MagicMock()
        lyrics_box.fill = lambda v: lyrics_state.__setitem__("val", v)
        lyrics_box.input_value = lambda: lyrics_state["val"]

        add_lyrics_btn = mock.MagicMock()

        def click_side_effect(loc):
            if loc is add_lyrics_btn:
                lyrics_state["opened"] = True

        drv._click.side_effect = click_side_effect

        def fake_eval(js, arg=None):
            if js == suno_cover._JS_MARK_EDITOR_EDIT_TAB:
                return {"active": True}
            if js == suno_cover._JS_MARK_EDITOR_STYLES:
                return {"state": "ready", "tag": "TEXTAREA", "editable": False}
            if js == suno_cover._JS_MARK_EDITOR_LYRICS:
                if not lyrics_state["opened"]:
                    return {"state": "collapsed", "hasBtn": True, "hasRow": True}
                return {"state": "ready", "tag": "TEXTAREA", "editable": False, "hasApply": False}
            return None

        drv.page.evaluate.side_effect = fake_eval

        def fake_query_first(_page, selectors, **_kw):
            sels = list(selectors)
            if "[data-tool-editor-styles='1']" in sels:
                return styles_box
            if "[data-tool-editor-add-lyrics-btn='1']" in sels:
                return add_lyrics_btn
            if "[data-tool-editor-lyrics='1']" in sels:
                return lyrics_box
            return None

        ai_styles = ("Ballad, 68-82 BPM, warm piano, subtle saxophone, "
                     "female vocals, sung in Vietnamese, clear upfront vocals, "
                     "continuous vocal melody throughout, no instrumental solo")
        raw_lyrics = "Đêm nay ai đưa em về\nĐường khuya sao trời lấp lánh"

        with mock.patch.object(suno_cover, "query_first", side_effect=fake_query_first):
            res = drv.sync_editor_lyrics_and_styles(lyrics=raw_lyrics, styles=ai_styles)

        self.assertEqual(res, {"styles": True, "lyrics": True})
        self.assertTrue(lyrics_state["opened"])
        self.assertEqual(styles_state["val"], ai_styles)
        self.assertEqual(
            lyrics_state["val"],
            "Đêm_nay_ai_đưa_em_về\nĐường_khuya_sao_trời_lấp_lánh",
        )

    def test_lexical_contenteditable_lyrics_in_song_editor(self):
        from backend.cover import suno_cover

        drv = bare_driver()
        drv._wait = mock.MagicMock()
        drv._click = mock.MagicMock()
        drv.page = mock.MagicMock()

        lex_box = mock.MagicMock()
        state = {"txt": ""}
        lex_box.inner_text = lambda: state["txt"]

        def box_eval(js, arg=None):
            if js == suno_cover._JS_PASTE_TEXT:
                state["txt"] = arg
                return True
            return None

        lex_box.evaluate.side_effect = box_eval

        def fake_eval(js, arg=None):
            if js == suno_cover._JS_MARK_EDITOR_EDIT_TAB:
                return {"active": True}
            if js == suno_cover._JS_MARK_EDITOR_LYRICS:
                return {"state": "ready", "tag": "DIV", "editable": True, "hasApply": False}
            return None

        drv.page.evaluate.side_effect = fake_eval

        with mock.patch.object(suno_cover, "query_first", return_value=lex_box):
            ok = drv.fill_editor_lyrics("Dĩ vãng nhạt nhòa\nTiếng mưa rơi đêm")

        self.assertTrue(ok)
        self.assertEqual(state["txt"], "Dĩ_vãng_nhạt_nhòa\nTiếng_mưa_rơi_đêm")

    def test_js_mark_editor_styles_shared_card_with_exclude_styles_in_real_dom(self):
        """Kiểm chứng trực tiếp _JS_MARK_EDITOR_STYLES trên Chromium thật với đúng cấu trúc
        ảnh chụp thực tế: Styles + nút ↺ + ô nhập + Exclude Styles nằm chung 1 thẻ bo góc."""
        from playwright.sync_api import sync_playwright
        from backend.cover import suno_cover

        html = """
        <!doctype html><html><body style="margin:0;width:1920px;height:1080px;">
          <div style="width:280px;padding:12px;">
            <div style="border:1px solid #333;border-radius:12px;padding:10px;margin-bottom:8px;">
              <div><span>Add Lyrics</span><button>v</button></div>
              <div contenteditable="true" role="textbox" style="height:300px;">Lời_đã_điền</div>
            </div>
            <div id="shared-card" style="border:1px solid #333;border-radius:12px;padding:12px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span>Styles</span>
                <button aria-label="Reset">↺</button>
              </div>
              <div contenteditable="true" id="styles-editor"
                   style="margin-top:8px;min-height:80px;border:1px solid #555;padding:8px;">An electronic dance instrumental featuring a synthesizer and drum machine, with an energetic mood.</div>
              <div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center;">
                <span>Exclude Styles</span>
                <button>⌄</button>
              </div>
              <input id="exclude-input" type="text" value="do-not-touch" style="margin-top:6px;width:220px;" />
            </div>
          </div>
        </body></html>
        """
        ai_prompt = "Ballad, 68-82 BPM, slow 4/4 restrained groove, piano, male vocals, sung in Vietnamese"
        import asyncio
        import sys
        old_policy = asyncio.get_event_loop_policy() if sys.platform == "win32" else None
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1920, "height": 1080})
                    page.set_content(html)
                    drv = CoverDriver(page, dry_run=True, selectors={})
                    drv._wait = lambda _ms: None
                    ok = drv.fill_editor_styles(ai_prompt)
                    self.assertTrue(ok)
                    self.assertEqual(page.locator("#styles-editor").inner_text().strip(), ai_prompt)
                    self.assertEqual(page.locator("#exclude-input").input_value(), "do-not-touch")
                finally:
                    browser.close()
        finally:
            if old_policy is not None:
                asyncio.set_event_loop_policy(old_policy)


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


class SemiManualAutoClicksCreateTests(unittest.TestCase):
    """Bán thủ công vẫn chờ người dùng lưu Editor, nhưng điền xong form thì TỰ bấm Create."""

    def test_semi_manual_auto_clicks_create_and_continues_pipeline(self):
        from sqlmodel import Session, SQLModel, create_engine
        from backend.models import Project, SourceSong
        from backend.video import config as vconfig

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            eng = create_engine(f"sqlite:///{root / 'semi.sqlite'}")
            try:
                SQLModel.metadata.create_all(eng)
                orig = root / "orig.mp3"
                adj = root / "tempo.wav"
                orig.write_bytes(b"orig")
                adj.write_bytes(b"tempo")
                with Session(eng) as s:
                    p = Project(name="Bai Test", music_style="Ballad")
                    s.add(p)
                    s.flush()
                    src = SourceSong(project_id=p.id, position=1, query="Bai Test - Ca Si",
                                     title="Bai Test", artist="Ca Si", vocal_gender="male",
                                     lyrics_text="Câu hát đầu tiên\nCâu hát thứ hai",
                                     file_path=str(orig), tempo_file_path=str(adj),
                                     tempo_factor=4.5, status="done")
                    s.add(src)
                    s.commit()
                    sid = src.id

                events = []

                class FakeCoverDrv:
                    def __init__(self, page, **_kw):
                        self.page = page
                        self.debug_dir = None
                        self.last_editor_tempo = 32

                    def prepare_cover(self, *_a, **kw):
                        events.append(("prepare_cover", bool(kw.get("manual_editor"))))

                    def _clear_library_filters(self):
                        events.append("clear_filters")

                    def snapshot_song_ids(self):
                        return {"old"}

                    def click_create(self):
                        events.append("click_create")

                    def save_debug(self, _tag):
                        return ""

                wav1, wav2 = root / "c1.wav", root / "c2.wav"
                wav1.write_bytes(b"1")
                wav2.write_bytes(b"2")

                with mock.patch.object(vconfig, "MEDIA_ROOT", root / "media"), \
                     mock.patch.object(suno_jobs, "engine", eng), \
                     mock.patch.object(suno_jobs, "get_workflow", return_value={"semi_manual": True}), \
                     mock.patch.object(suno_jobs, "CoverDriver", FakeCoverDrv), \
                     mock.patch("backend.core_bridge.get_api_config_from_db", return_value=SimpleNamespace(api_key=None)), \
                     mock.patch.object(suno_jobs, "generate_cover_styles",
                                       return_value=("Ballad, male vocals, sung in Vietnamese, clear upfront vocals, continuous vocal melody throughout, no instrumental solo", "fallback")), \
                     mock.patch.object(suno_jobs, "_pace"), \
                     mock.patch.object(suno_jobs, "_create_and_watch", return_value=["id1", "id2"]) as watch, \
                     mock.patch.object(suno_jobs, "_download_all", return_value=[wav1, wav2]) as dl, \
                     mock.patch.object(suno_jobs.mastering, "submit") as master_sub, \
                     mock.patch.object(suno_jobs, "_attach") as attach, \
                     mock.patch.object(suno_jobs, "_await_semi_create",
                                       side_effect=AssertionError("không được dừng chờ bấm Create tay")):
                    suno_jobs._process(sid, "page", dry=False)
            finally:
                eng.dispose()

            self.assertIn(("prepare_cover", True), events)
            self.assertIn("click_create", events)
            watch.assert_called_once()
            dl.assert_called_once()
            master_sub.assert_called_once()
            attach.assert_called_once()
