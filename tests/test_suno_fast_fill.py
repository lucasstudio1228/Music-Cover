"""Điền form Cover nhanh (LIVE 2026-11-09): nhận đúng bài Editor vừa lưu khi
thư viện có nhiều bài «(Edit)» mới, dán lyrics một lần, thanh trượt đặt bằng
phím trước (kéo chuột là dự phòng), không thử xoá Filters mặc định 2 lần.
Không mở trình duyệt."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.cover import suno_cover
from backend.cover.suno_cover import CoverDriver

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"
C = "cccccccc-1111-2222-3333-444444444444"
STEM = "Em Là Nhất Miền Tây - Võ Lê Mi, Jin Tuấn Nam - tempo 4.5x (#149)"


def _driver():
    drv = CoverDriver(mock.MagicMock(), dry_run=True, selectors={})
    drv._wait = mock.MagicMock()
    drv.logs = []
    drv._log = drv.logs.append
    return drv


class PickSavedSongTests(unittest.TestCase):
    def test_single_fresh_id(self):
        self.assertEqual(_driver()._pick_saved_song({A}, STEM), A)

    def test_many_fresh_ids_pick_newest_edit_with_title(self):
        drv = _driver()
        drv.page.evaluate.return_value = [
            [f"/song/{C}", "Bài khác (Edit)"],
            [f"/song/{B}", STEM + " (Edit)"],          # mới nhất đúng tên
            [f"/song/{A}", STEM + " (Edit)"],
            [f"/song/{A}", STEM],
        ]
        self.assertEqual(drv._pick_saved_song({A, B, C}, STEM), B)

    def test_title_match_ignores_spacing_and_case(self):
        drv = _driver()
        drv.page.evaluate.return_value = [
            [f"/song/{A}", STEM.upper().replace(" - ", "  -\n ") + " (EDIT)"]]
        self.assertEqual(drv._pick_saved_song({A, B}, STEM), A)

    def test_no_match_returns_empty(self):
        drv = _driver()
        drv.page.evaluate.return_value = [[f"/song/{A}", STEM]]   # không có (Edit)
        self.assertEqual(drv._pick_saved_song({A, B}, STEM), "")
        self.assertEqual(drv._pick_saved_song(set(), STEM), "")


class _Editor:
    """Ô Lexical giả: paste_works=False → sự kiện paste không ăn."""
    def __init__(self, paste_works=True):
        self.text, self.paste_works, self.typed = "", paste_works, []

    def get_attribute(self, name):
        return None

    def click(self):
        pass

    def evaluate(self, js, arg=None):
        if js == suno_cover._JS_PASTE_TEXT and self.paste_works:
            self.text = arg
        return True

    def inner_text(self):
        return self.text


class LyricsPasteTests(unittest.TestCase):
    LYRICS = "Câu một\nCâu hai\n\nCâu ba"

    def _fill(self, editor):
        drv = _driver()
        drv._find = mock.MagicMock(return_value=editor)
        kb = drv.page.keyboard

        def press(key):
            if key == "Delete":
                editor.text = ""
            elif key == "Enter":
                editor.text += "\n"
        kb.press.side_effect = press
        kb.insert_text.side_effect = lambda t: (editor.typed.append(t),
                                                setattr(editor, "text", editor.text + t))
        drv.fill_song_lyrics(self.LYRICS)
        return editor

    def test_paste_once_no_typing(self):
        ed = self._fill(_Editor())
        self.assertEqual(ed.typed, [])
        self.assertEqual(ed.text, self.LYRICS)

    def test_falls_back_to_typing_when_paste_ignored(self):
        ed = self._fill(_Editor(paste_works=False))
        self.assertEqual(ed.typed, ["Câu một", "Câu hai", "Câu ba"])


class _Slider:
    def __init__(self, now, keys_work=True):
        self.now, self.keys_work = now, keys_work

    def get_attribute(self, name):
        return {"aria-valuenow": str(self.now), "aria-valuemin": "0",
                "aria-valuemax": "100"}.get(name)

    def focus(self):
        pass

    def evaluate(self, js, arg=None):
        if js == CoverDriver._JS_SLIDER_KEYS:
            key, n, _ = arg
            if self.keys_work:
                self.now += n if key == "ArrowRight" else -n
            return True
        return True                                  # đang có focus


class SliderTests(unittest.TestCase):
    def test_keys_first_no_drag(self):
        drv = _driver()
        s = _Slider(46)
        drv._slider = mock.MagicMock(return_value=s)
        drv._drag_slider = mock.MagicMock()
        self.assertEqual(drv.set_slider("weirdness", 10), 10)
        drv._drag_slider.assert_not_called()
        drv.page.keyboard.press.assert_not_called()

    def test_already_at_target_does_nothing(self):
        drv = _driver()
        drv._slider = mock.MagicMock(return_value=_Slider(75))
        drv._keyboard_slider = mock.MagicMock()
        self.assertEqual(drv.set_slider("style_influence", 75), 75)
        drv._keyboard_slider.assert_not_called()

    def test_drag_fallback_when_keys_fail(self):
        drv = _driver()
        s = _Slider(46, keys_work=False)
        drv._slider = mock.MagicMock(return_value=s)

        def drag(loc, v):
            s.now = v
            return v
        drv._drag_slider = mock.MagicMock(side_effect=drag)
        self.assertEqual(drv.set_slider("weirdness", 10), 10)
        drv._drag_slider.assert_called_once()

    def test_still_wrong_raises(self):
        drv = _driver()
        drv._slider = mock.MagicMock(return_value=_Slider(46, keys_work=False))
        drv._drag_slider = mock.MagicMock(return_value=46)
        with self.assertRaises(suno_cover.SunoUIChanged):
            drv.set_slider("weirdness", 10)


class StuckFiltersTests(unittest.TestCase):
    def test_default_filters_tried_only_once(self):
        drv = _driver()
        drv.page.locator.return_value.all_inner_texts.return_value = ["Filters (3)"]
        drv.page.evaluate.return_value = []
        drv._close_open_menus = mock.MagicMock()
        drv.save_debug = mock.MagicMock(return_value="")
        with mock.patch.object(suno_cover, "query_first", return_value=None) as q:
            drv._clear_library_filters()
            first = q.call_count
            drv._clear_library_filters()
        self.assertGreater(first, 0)
        self.assertEqual(q.call_count, first)        # lần 2 bỏ qua ngay
        self.assertEqual(drv._filters_stuck_at, 3)

    def test_new_filter_count_is_retried(self):
        drv = _driver()
        drv._filters_stuck_at = 3
        drv.page.locator.return_value.all_inner_texts.return_value = ["Filters (4)"]
        drv.page.evaluate.return_value = []
        drv._close_open_menus = mock.MagicMock()
        drv.save_debug = mock.MagicMock(return_value="")
        with mock.patch.object(suno_cover, "query_first", return_value=None) as q:
            drv._clear_library_filters()
        self.assertGreater(q.call_count, 0)


if __name__ == "__main__":
    unittest.main()
