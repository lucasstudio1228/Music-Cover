"""Mở Editor từ hàng UPLOAD trên Suno: chọn đúng hàng, đúng mục «Edit» /
«Open in Editor», thử lại khi submenu không bung và không dừng cả hàng đợi.
(Lỗi LIVE 2026-11-08.) Test JS chạy trên Chromium headless với markup chép từ
Suno thật; các test còn lại không mở trình duyệt."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import suno_cover

WAV = Path("Mở Lòng Vì Ai (Inso Cover) - Inso - tempo 4.5x (#148).wav")


def _driver(row_found=True):
    page = mock.MagicMock()
    page.evaluate.side_effect = lambda js, *a: (
        row_found if js == suno_cover._JS_MARK_UPLOAD_MORE else ["Remix", "Edit"])
    drv = suno_cover.CoverDriver(page, dry_run=True, selectors={})
    drv._wait = mock.MagicMock()
    drv._dismiss_popups = mock.MagicMock()
    drv._real_click = mock.MagicMock(return_value=True)
    drv._hover_real = mock.MagicMock(return_value=True)
    drv._click = mock.MagicMock()
    drv._click_menu_item = mock.MagicMock()
    drv.logs = []
    drv._log = drv.logs.append
    return drv


class UploadRowRetryTests(unittest.TestCase):
    def test_retries_menu_until_editor_opens(self):
        drv = _driver()
        drv._editor_from_open_menu = mock.MagicMock(
            side_effect=["Submenu Edit chưa bung «Open in Editor»", ""])
        self.assertTrue(drv._open_matching_upload_in_editor(WAV))
        self.assertEqual(drv._real_click.call_count, 2)       # bấm ⋯ hai lần
        self.assertTrue(any("lần 1/3" in m for m in drv.logs))

    def test_gives_up_without_stopping_queue(self):
        drv = _driver()
        drv._editor_from_open_menu = mock.MagicMock(return_value="Menu ⋯ chưa có mục «Edit»")
        self.assertFalse(drv._open_matching_upload_in_editor(WAV))
        self.assertEqual(drv._real_click.call_count, 3)
        self.assertIn("upload lại", drv.logs[-1])
        self.assertTrue(any("menu đang thấy: Remix, Edit" in m for m in drv.logs))

    def test_no_upload_row_returns_false_without_clicking(self):
        drv = _driver(row_found=False)
        self.assertFalse(drv._open_matching_upload_in_editor(WAV))
        drv._real_click.assert_not_called()

    def test_polling_loop_tries_only_one_round(self):
        drv = _driver()
        drv._open_matching_upload_in_editor = mock.MagicMock(side_effect=[False, True])
        drv._pick_file = mock.MagicMock(return_value="ô chọn file ẩn")
        drv.check_rejection = mock.MagicMock()
        drv._editor_control = mock.MagicMock(return_value=None)
        drv.snapshot_song_ids = mock.MagicMock(return_value=set())
        drv._handle_dialog = mock.MagicMock(return_value=False)
        drv._open_uploaded_audio_in_editor(WAV, set())
        self.assertEqual(drv._open_matching_upload_in_editor.call_args_list,
                         [mock.call(WAV), mock.call(WAV, rounds=1)])

    def test_new_upload_song_menu_is_retried(self):
        drv = _driver()
        drv._ensure_song_open = mock.MagicMock()
        drv._open_song_menu = mock.MagicMock()
        drv._editor_from_open_menu = mock.MagicMock(
            side_effect=["Submenu Edit chưa bung «Open in Editor»", ""])
        drv._open_editor_from_song("song-id")
        self.assertEqual(drv._open_song_menu.call_count, 2)


class EditorFromMenuTests(unittest.TestCase):
    def test_hover_edit_then_click_open_in_editor(self):
        drv = _driver()
        edit, open_editor = mock.MagicMock(), mock.MagicMock()
        drv._menu_item = mock.MagicMock(side_effect=[edit, open_editor])
        drv.page.url = "https://suno.com/create"
        drv._click_menu_item.side_effect = lambda loc: setattr(
            drv.page, "url", "https://suno.com/edit/c6f38f33?wid=default")
        self.assertEqual(drv._editor_from_open_menu(), "")
        drv._hover_real.assert_called_once_with(edit)
        drv._click_menu_item.assert_called_once_with(open_editor)

    def test_click_that_misses_editor_is_reported_and_page_restored(self):
        """LIVE 02:43: bấm trúng hàng bài khác, URL không sang /edit/."""
        drv = _driver()
        drv._menu_item = mock.MagicMock(side_effect=[mock.MagicMock(), mock.MagicMock()])
        drv.page.url = "https://suno.com/create"
        drv._click_menu_item.side_effect = lambda loc: setattr(
            drv.page, "url", "https://suno.com/song/other-song")
        with mock.patch.object(suno_cover.time, "time", side_effect=[0, 0, 99]):
            problem = drv._editor_from_open_menu()
        self.assertIn("Editor chưa mở", problem)
        drv.page.goto.assert_called_once_with("https://suno.com/create")

    def test_upload_row_retries_when_editor_did_not_open(self):
        drv = _driver()
        drv._editor_from_open_menu = mock.MagicMock(
            side_effect=["Đã bấm «Open in Editor» nhưng Editor chưa mở (trang: x)", ""])
        self.assertTrue(drv._open_matching_upload_in_editor(WAV))
        self.assertEqual(drv._real_click.call_count, 2)

    def test_falls_back_to_click_then_arrow_key(self):
        drv = _driver()
        edit = mock.MagicMock()
        drv._menu_item = mock.MagicMock(side_effect=[edit, None, None, None])
        self.assertIn("Open in Editor", drv._editor_from_open_menu())
        drv._click.assert_called_once_with(edit)
        drv.page.keyboard.press.assert_called_once_with("ArrowRight")
        drv._click_menu_item.assert_not_called()

    def test_missing_edit_item(self):
        drv = _driver()
        drv._menu_item = mock.MagicMock(return_value=None)
        self.assertIn("«Edit»", drv._editor_from_open_menu())


# Markup rút gọn từ menu ⋯ của Suno thật (2026-11-08): chữ nằm trong <span>,
# mục «Open in Editor» có thêm huy hiệu «Pro» ở dòng sau.
_SUNO_MENU = """
<div role=menu>
  <div role=menuitem class="hxc-menu-item hxc-submenu-trigger"><svg></svg><span class=flex-1>Remix</span><svg></svg></div>
  <div role=menuitem class="hxc-menu-item hxc-submenu-trigger"><svg></svg><span class=flex-1>Edit</span><svg></svg></div>
  <div role=menuitem class="hxc-menu-item"><svg></svg><span>Credits</span></div>
</div>
<div role=menu>
  <div role=menuitem class="hxc-menu-item"><svg></svg><span>Edit Details</span></div>
  <div role=menuitem class="hxc-menu-item"><svg></svg><span>Open in Studio</span><div>New</div></div>
  <div role=menuitem class="hxc-menu-item"><svg></svg><span>Open in Editor</span><div>Pro</div></div>
</div>"""

_ROW = ('<div style="height:86px"><span>{t}</span>{b}'
        '<button aria-label="More options">...</button></div>')
_STEM = "Mở Lòng Vì Ai (Inso Cover) - Inso - tempo 4.5x (#148)"


class LiveMarkupJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls._pw = sync_playwright().start()
            cls._browser = cls._pw.chromium.launch()
        except Exception as e:                      # máy không có Chromium
            raise unittest.SkipTest(f"Không chạy được Chromium: {e}")
        cls.page = cls._browser.new_page()

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()

    def _mark(self, label):
        ok = self.page.evaluate(suno_cover._JS_MARK_MENU_ITEM, label)
        loc = self.page.locator("[data-tool-menu-item]")
        return ok, (loc.first.inner_text().split("\n")[0] if loc.count() else None)

    def test_menu_item_found_although_text_is_in_span(self):
        self.page.set_content(_SUNO_MENU)
        self.assertEqual(self._mark("Edit"), (True, "Edit"))
        self.assertEqual(self._mark("Open in Editor"), (True, "Open in Editor"))
        self.assertEqual(self._mark("Open in Studio"), (True, "Open in Studio"))
        self.assertEqual(self._mark("Edit Song"), (False, None))

    def test_edit_row_next_to_other_upload_row_not_marked(self):
        self.page.set_content("<div><div>" + _ROW.format(
            t="Em Là Nhất Miền Tây (#149)", b="<i>UPLOAD</i>") + _ROW.format(
            t=_STEM + " (Edit)", b="") + "</div></div>")
        self.assertFalse(self.page.evaluate(suno_cover._JS_MARK_UPLOAD_MORE, _STEM))

    def test_real_upload_row_marked(self):
        self.page.set_content("<div><div>" + _ROW.format(t=_STEM + " (Edit)", b="")
                              + _ROW.format(t=_STEM, b="<i>UPLOAD</i>") + "</div></div>")
        self.assertTrue(self.page.evaluate(suno_cover._JS_MARK_UPLOAD_MORE, _STEM))
        text = self.page.evaluate(
            "() => document.querySelector(\"[data-tool-upload-more='1']\").parentElement.innerText")
        self.assertNotIn("(Edit)", text)


if __name__ == "__main__":
    unittest.main()
