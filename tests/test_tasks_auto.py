import unittest
from unittest import mock

from backend.routers import tasks


class AutoRunStateTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(tasks._auto_state)
        tasks._auto_state.clear()

    def tearDown(self):
        tasks._auto_state.clear()
        tasks._auto_state.update(self.old)

    def test_terminal_state_gets_timestamp_for_taskbar_history(self):
        with mock.patch.object(tasks.time, "time", return_value=123.0):
            tasks._auto_update(7, status="failed", error="boom")
        self.assertEqual(tasks._auto_state[7]["finished_at"], 123.0)

    def test_running_state_does_not_fake_finished_timestamp(self):
        tasks._auto_update(8, status="running", message="work")
        self.assertNotIn("finished_at", tasks._auto_state[8])


if __name__ == "__main__":
    unittest.main()
