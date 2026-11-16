import unittest
from MIUroutine.diff import diff_sessions, has_changes, render_changes, render_schedule, render_warnings
from MIUroutine.grid import Grid, content_hash
from MIUroutine.routine import _batch_matches, _minutes, parse_routine


class TestRoutine(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(_minutes(9, 0), 540)
        self.assertEqual(_minutes(1, 0), 780)
        self.assertEqual(_minutes(12, 30), 750)

    def test_batch_matches(self):
        self.assertTrue(_batch_matches("71", "71"))
        self.assertTrue(_batch_matches("71/GED1102/BT", "71"))
        self.assertTrue(_batch_matches("(65+71)", "71"))
        self.assertFalse(_batch_matches("62/CSE4271/ABN", "71"))
        self.assertFalse(_batch_matches("70M", "71"))

    def test_diff_sessions(self):
        s1 = {
            "day": "Sunday",
            "start": 540,
            "end": 600,
            "code": "GED1102",
            "title": "English",
            "teacher": "Bushra Tasnim",
            "room": "C108",
        }
        s2 = {
            "day": "Sunday",
            "start": 600,
            "end": 660,
            "code": "GED1102",
            "title": "English",
            "teacher": "Bushra Tasnim",
            "room": "C109",
        }
        diff = diff_sessions([s1], [s2])
        self.assertTrue(has_changes(diff))
        self.assertEqual(len(diff["changed"]), 1)
        self.assertEqual(diff["changed"][0], (s1, s2))
        self.assertEqual(len(diff["added"]), 0)
        self.assertEqual(len(diff["removed"]), 0)

    def test_rendering(self):
        s1 = {
            "day": "Sunday",
            "start": 540,
            "end": 600,
            "code": "GED1102",
            "title": "English",
            "teacher": "Bushra Tasnim",
            "room": "C108",
        }
        sched = render_schedule([s1])
        self.assertIn("Sunday", sched)
        self.assertIn("9:00–10:00 AM", sched)
        self.assertIn("English (GED1102)", sched)

        warn = render_warnings(["Test warning"])
        self.assertIn("⚠️ Test warning", warn)


if __name__ == "__main__":
    unittest.main()
