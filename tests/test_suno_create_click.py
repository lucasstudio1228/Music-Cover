"""Bấm Create khi menu Filters còn mở và trình duyệt đóng lúc chờ tải lại.
(Lỗi LIVE 2026-11-09: menu Filters mở → cú bấm Create chỉ đóng menu, Suno không
nhận lệnh; Cốc Cốc đóng giữa 60 giây chờ → TargetClosedError hỏng cả bài.)"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import suno_cover, suno_jobs
from backend.video import suno_driver


def _driver(page):
    drv = suno_cover.CoverDriver(page, dry_run=False, selectors={})
    drv._wait = mock.MagicMock()
    drv.logs = []
    drv._log = drv.logs.append
    return drv


class PrepareCreateClickTests(unittest.TestCase):
    def test_open_menu_closed_before_create(self):
        page = mock.MagicMock()
        menus = [1, 0, 0]
        page.evaluate.side_effect = lambda js, *a: (
            menus.pop(0) if js == suno_driver._JS_OPEN_MENUS and menus else 0)
        drv = _driver(page)
        button = mock.MagicMock()
        button.evaluate.return_value = ""
        drv._find = mock.MagicMock(return_value=button)
        drv._real_click = mock.MagicMock(return_value=True)
        drv.click_create()
        page.keyboard.press.assert_called_once_with("Escape")
        drv._real_click.assert_called_once_with(button)

    def test_blocked_button_dismisses_popups_then_clicks(self):
        page = mock.MagicMock()
        page.evaluate.return_value = 0
        drv = _driver(page)
        drv._dismiss_popups = mock.MagicMock()
        button = mock.MagicMock()
        button.evaluate.side_effect = ["div[role=menu] «Liked»", ""]
        drv._find = mock.MagicMock(return_value=button)
        drv._real_click = mock.MagicMock(return_value=True)
        drv.click_create()
        drv._dismiss_popups.assert_called_once_with()
        self.assertTrue(any("bị che" in m for m in drv.logs))
        self.assertFalse(any("CẢNH BÁO" in m for m in drv.logs))
        drv._real_click.assert_called_once_with(button)

    def test_clear_filters_failure_still_closes_menu(self):
        page = mock.MagicMock()
        page.locator.return_value.all_inner_texts.return_value = ["Filters (3)"]
        page.evaluate.return_value = []
        drv = _driver(page)
        drv.debug_dir = None
        drv._click = mock.MagicMock()
        drv._close_open_menus = mock.MagicMock(return_value=0)
        with mock.patch.object(suno_cover, "query_first", return_value=None):
            drv._clear_library_filters()
        drv._close_open_menus.assert_called_once_with()
        self.assertIn("Filters (3)", drv.logs[-1])


class LiveMarkupTests(unittest.TestCase):
    """JS chạy trên Chromium thật với menu đè lên nút Create."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls._pw = sync_playwright().start()
            cls._browser = cls._pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"Không chạy được Chromium: {e}")
        cls.page = cls._browser.new_page()

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()

    def test_menu_count_and_blocker(self):
        self.page.set_content(
            "<button aria-label='Create song' style='position:absolute;left:10px;"
            "top:10px;width:200px;height:40px'><span>Create</span></button>"
            "<div role=menu style='position:absolute;left:0;top:0;width:300px;"
            "height:100px;background:#000'><div role=menuitem>Liked</div></div>")
        btn = self.page.locator("button")
        self.assertEqual(self.page.evaluate(suno_driver._JS_OPEN_MENUS), 1)
        self.assertIn("menu", btn.evaluate(suno_driver._JS_CREATE_BLOCKER))
        self.page.evaluate("() => document.querySelector('[role=menu]').remove()")
        self.assertEqual(self.page.evaluate(suno_driver._JS_OPEN_MENUS), 0)
        self.assertEqual(btn.evaluate(suno_driver._JS_CREATE_BLOCKER), "")


class _Page:
    def __init__(self):
        self.closed = False
        self.context = SimpleNamespace(pages=[])

    def is_closed(self):
        return self.closed


class _Drv:
    """Bản 1 tải được, bản 2 lỗi; browser đóng trong lúc chờ 60 giây."""

    def __init__(self, fail_ids=()):
        self.page = _Page()
        self.fail_ids = set(fail_ids)
        self.downloaded = []

    def download_wav(self, song_id, dest, timeout_sec=0):
        if song_id in self.fail_ids:
            raise RuntimeError("Không bắt được quyền audio từ player Suno.")
        self.downloaded.append(song_id)
        Path(dest).write_bytes(b"RIFFcomplete")
        return dest

    def close_extra_tabs(self):
        pass

    def _wait(self, ms):
        self.page.closed = True
        raise RuntimeError("Page.wait_for_timeout: Target page, context or "
                           "browser has been closed")


IDS = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]
VALID = SimpleNamespace(valid=True, reason="")


class BrowserClosedDuringRetryWaitTests(unittest.TestCase):
    def test_reopens_and_downloads_missing_id(self):
        with TemporaryDirectory() as tmp, \
                mock.patch("backend.video.suno_verify.verify_wav", return_value=VALID):
            first, second = _Drv(fail_ids=[IDS[1]]), _Drv()
            files = suno_jobs._download_all(first, IDS, Path(tmp), "Bài",
                                            lambda _: None, reopen_driver=lambda: second)
        self.assertEqual(len(files), 2)
        self.assertEqual(second.downloaded, [IDS[1]])

    def test_without_reopen_keeps_downloaded_file(self):
        logs = []
        with TemporaryDirectory() as tmp, \
                mock.patch("backend.video.suno_verify.verify_wav", return_value=VALID):
            files = suno_jobs._download_all(_Drv(fail_ids=[IDS[1]]), IDS, Path(tmp),
                                            "Bài", logs.append)
        self.assertEqual(len(files), 1)
        self.assertTrue(any("không mở lại được" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
