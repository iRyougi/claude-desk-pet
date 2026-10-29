import os
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from motion import Rect, Surface, hold, spawn  # noqa: E402
from screen import choose_z, is_fullscreen  # noqa: E402

MON = Rect(0, 0, 1920, 1080)
WIN = Surface(key=1234, left=100.0, right=900.0, y=300.0, kind='window')
GROUND = Surface(key=('ground', 0, 0, None), left=0.0, right=1920.0, y=1040.0, kind='ground')


class FullscreenTest(unittest.TestCase):
    def test_covering_the_whole_monitor_is_fullscreen(self):
        self.assertTrue(is_fullscreen(Rect(0, 0, 1920, 1080), 'UnityWndClass', MON))

    def test_zoomed_window_is_not_fullscreen(self):
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1080), 'Chrome_WidgetWin_1', MON, zoomed=True))

    def test_slightly_larger_still_counts(self):
        self.assertTrue(is_fullscreen(Rect(-8, -8, 1928, 1088), 'Chrome_WidgetWin_1', MON))

    def test_maximized_above_the_taskbar_is_not(self):
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1040), 'Chrome_WidgetWin_1', MON))

    def test_desktop_is_not(self):
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1080), 'Progman', MON))
        self.assertFalse(is_fullscreen(Rect(0, 0, 1920, 1080), 'WorkerW', MON))

    def test_fullscreen_on_another_monitor_is_not(self):
        self.assertFalse(is_fullscreen(Rect(1920, 0, 3840, 1080), 'UnityWndClass', MON))


class ChooseZTest(unittest.TestCase):
    def test_sitting_on_a_window_stays_just_above_it(self):
        self.assertEqual(choose_z(spawn(WIN, 0.5, 0.0), 0, False), 1234)

    def test_walking_on_a_window_too(self):
        m = replace(spawn(WIN, 0.5, 0.0), mode='walk', target_frac=0.8)
        self.assertEqual(choose_z(m, 0, False), 1234)

    def test_on_the_ground_is_topmost(self):
        self.assertEqual(choose_z(spawn(GROUND, 0.5, 0.0), 0, False), 'top')

    def test_held_reminding_or_speaking_is_topmost(self):
        m = spawn(WIN, 0.5, 0.0)
        self.assertEqual(choose_z(hold(m, 5.0, 5.0), 0, False), 'top')
        self.assertEqual(choose_z(m, 2, False), 'top')
        self.assertEqual(choose_z(m, 0, True), 'top')

    def test_no_body_is_topmost(self):
        self.assertEqual(choose_z(None, 0, False), 'top')


if __name__ == '__main__':
    unittest.main()
