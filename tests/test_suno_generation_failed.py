"""Bài Suno 'failed to generate' (asset trả HTTP 404) phải được phân loại là
SunoGenerationFailed để job giữ bài chờ nhập thủ công, không tải lại vô ích."""
import unittest
from unittest import mock

from backend.video.suno_driver import SunoDriver, SunoGenerationFailed

SONG_ID = "c16acf1c-0000-4000-8000-000000000000"


def _driver(page_url: str = f"https://suno.com/song/{SONG_ID}"):
    drv = object.__new__(SunoDriver)
    drv.dry_run = False
    drv._log = lambda *_a, **_k: None
    drv._wait = lambda *_a, **_k: None
    drv.page = mock.MagicMock()
    drv.page.url = page_url
    return drv


class GenerationFailedTest(unittest.TestCase):
    def test_404_on_failed_song_raises_generation_failed(self):
        drv = _driver()
        with mock.patch("backend.cover.suno_wav_downloader."
                        "download_authorized_song_as_wav",
                        side_effect=RuntimeError("HTTP Error 404: Not Found")), \
             mock.patch("backend.video.suno_driver.query_first",
                        return_value=object()):
            with self.assertRaises(SunoGenerationFailed):
                drv.download_asset_wav(SONG_ID, "out.wav")

    def test_404_on_normal_song_keeps_original_error(self):
        drv = _driver()
        with mock.patch("backend.cover.suno_wav_downloader."
                        "download_authorized_song_as_wav",
                        side_effect=RuntimeError("HTTP Error 404: Not Found")), \
             mock.patch("backend.video.suno_driver.query_first",
                        return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                drv.download_asset_wav(SONG_ID, "out.wav")
            self.assertNotIsInstance(ctx.exception, SunoGenerationFailed)

    def _download_with_page(self, results):
        """results: các giá trị lần lượt của _JS_SONG_404 (True = trang 404)."""
        from backend.video import suno_driver
        drv = _driver()
        seq = list(results)
        drv.page.evaluate.side_effect = lambda js, *a: (
            seq.pop(0) if js == suno_driver._JS_SONG_404 and seq else False)
        with mock.patch("backend.cover.suno_wav_downloader."
                        "download_authorized_song_as_wav",
                        side_effect=RuntimeError("Không bắt được quyền audio từ player Suno.")),              mock.patch("backend.video.suno_driver.query_first", return_value=None):
            try:
                drv.download_asset_wav(SONG_ID, "out.wav")
            except Exception as e:  # noqa: BLE001
                return drv, e
        self.fail("phải ném lỗi")

    def test_removed_song_page_404_is_generation_failed(self):
        # LIVE 2026-11-09: lyrics dính bản quyền → trang /song/<id> báo 404.
        drv, e = self._download_with_page([True, True])
        self.assertIsInstance(e, SunoGenerationFailed)
        self.assertIn("404", str(e))
        self.assertTrue(drv._song_removed)
        drv.page.goto.assert_called_once()          # nạp lại 1 lần để chắc chắn

    def test_transient_404_keeps_original_error(self):
        drv, e = self._download_with_page([True, False])
        self.assertNotIsInstance(e, SunoGenerationFailed)
        self.assertFalse(drv._song_removed)


class Song404MarkupTest(unittest.TestCase):
    """JS nhận trang 404 của Suno thật trên Chromium."""

    def test_js_on_real_markup(self):
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"Không chạy được Chromium: {e}")
        from backend.video import suno_driver
        try:
            page = browser.new_page()
            page.set_content("<nav>Home Explore Create Library</nav><main><p>404</p>"
                             "<h1>Page not found</h1><p>Oops, looks like this link is "
                             "broken.</p><a>Explore Suno</a></main>")
            self.assertTrue(page.evaluate(suno_driver._JS_SONG_404))
            page.set_content("<main><h1>Em Là Nhất Miền Tây</h1><p>v5 · 4:04 · "
                             "404 plays</p></main>")
            self.assertFalse(page.evaluate(suno_driver._JS_SONG_404))
        finally:
            browser.close()
            pw.stop()


if __name__ == "__main__":
    unittest.main()
