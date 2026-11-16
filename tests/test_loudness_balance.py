"""Đo + cân bằng độ to giữa các bài trong Mix (backend/cover/loudness_balance.py)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pyloudnorm as pyln

from backend.cover import loudness_balance as lb

SR = 48000


def tone(seconds: float, amp: float, freq: float = 440.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    x = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


def dynamic_song() -> np.ndarray:
    """Verse nhỏ 20 s + điệp khúc to 10 s — dải động lớn."""
    return np.concatenate([tone(20, 0.05), tone(10, 0.4)])


class AnalyzeTests(unittest.TestCase):
    def test_integrated_matches_pyloudnorm(self):
        a = dynamic_song()
        got = lb.analyze(a, SR)
        ref = pyln.Meter(SR).integrated_loudness(a)
        self.assertAlmostEqual(got["integrated"], ref, delta=0.05)
        self.assertGreater(got["loud"], got["integrated"])      # đoạn to > trung bình
        self.assertGreater(got["lra"], 10)
        self.assertAlmostEqual(got["peak_db"], 20 * np.log10(0.4), delta=0.05)

    def test_silence_and_short_audio(self):
        self.assertIsNone(lb.analyze(np.zeros((SR * 5, 2), np.float32), SR)["integrated"])
        short = lb.analyze(tone(1.0, 0.3), SR)      # < 3 s: đoạn to = tích hợp
        self.assertEqual(short["loud"], short["integrated"])

    def test_cache_by_mtime(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.wav"
            f.write_bytes(b"x")

            def load():
                calls.append(1)
                return tone(4, 0.2), SR
            lb.analyze_cached(str(f), load)
            lb.analyze_cached(str(f), load)
        self.assertEqual(len(calls), 1)


class PlanTests(unittest.TestCase):
    def test_loud_parts_equalised_and_median_hits_target(self):
        songs = [tone(30, 0.3), dynamic_song(), tone(30, 0.1)]
        stats = [lb.analyze(a, SR) for a in songs]
        plan = lb.plan(stats, -14.0)
        louds = [p["after_loud"] for p in plan]
        self.assertLess(max(louds) - min(louds), 0.01)
        self.assertAlmostEqual(float(np.median([p["after_integrated"] for p in plan])),
                               -14.0, delta=0.01)
        self.assertTrue(plan[2]["flag"])            # bài nhỏ hơn hẳn bị đánh dấu

    def test_manual_offset_and_unmeasurable_song(self):
        stats = [lb.analyze(tone(10, 0.2), SR), {"integrated": None, "loud": None,
                                                  "peak_db": None}]
        base = lb.plan(stats, -14.0)[0]["gain_db"]
        plan = lb.plan(stats, -14.0, [2.0, 3.0])
        self.assertAlmostEqual(plan[0]["gain_db"], base + 2.0, delta=0.01)
        self.assertEqual(plan[1]["gain_db"], 0.0)

    def test_plan_is_json_serialisable(self):
        import json
        stats = [lb.analyze(tone(10, 0.9), SR), lb.analyze(tone(10, 0.01), SR)]
        json.dumps({"stats": stats, "plan": lb.plan(stats, -14.0)})   # không numpy

    def test_single_song_equals_integrated_normalize(self):
        st = lb.analyze(dynamic_song(), SR)
        self.assertAlmostEqual(lb.plan([st], -16.0)[0]["after_integrated"], -16.0,
                               delta=0.01)


class LimiterTests(unittest.TestCase):
    def test_boost_is_limited_not_scaled_down(self):
        a = dynamic_song()
        out, reduced = lb.apply(a, SR, 12.0)           # 0.4 × 4 ≈ 1.6 → vượt trần
        ceiling = 10 ** (lb.CEILING_DB / 20)
        self.assertLessEqual(float(np.max(np.abs(out))), ceiling + 1e-6)
        self.assertGreater(reduced, 3.0)
        # Đoạn verse nhỏ vẫn được tăng đủ 12 dB (không bị hạ cả bài như cách cũ).
        verse_gain = np.max(np.abs(out[SR:SR * 15])) / np.max(np.abs(a[SR:SR * 15]))
        self.assertAlmostEqual(20 * np.log10(verse_gain), 12.0, delta=0.1)

    def test_no_change_below_ceiling(self):
        a = tone(5, 0.1)
        out, reduced = lb.limit(a, SR)
        self.assertEqual(reduced, 0.0)
        np.testing.assert_array_equal(out, a)


class MigrationM035Tests(unittest.TestCase):
    def test_adds_columns_once(self):
        from backend import migrations
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "app.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("CREATE TABLE coversong (id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute("INSERT INTO project VALUES (1, 'Cũ')")
            conn.commit()
            conn.close()
            with mock.patch.object(migrations, "DB_PATH", db):
                migrations.migrate_add_mix_gain_and_project_kind()
                migrations.migrate_add_mix_gain_and_project_kind()
            conn = sqlite3.connect(db)
            kind = conn.execute("SELECT kind FROM project").fetchone()[0]
            cols = [r[1] for r in conn.execute("PRAGMA table_info(coversong)")]
            conn.close()
        self.assertEqual(kind, "mixset")
        self.assertIn("mix_gain_db", cols)


if __name__ == "__main__":
    unittest.main()
