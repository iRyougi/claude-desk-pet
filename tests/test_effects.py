import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from effects import ZZ_LIFE, zz_marks  # noqa: E402


class ZzMarksTest(unittest.TestCase):
    def test_a_fresh_mark_is_fully_visible_at_the_start(self):
        marks = zz_marks(3.0, 1.0)
        newest = min(marks, key=lambda m: -m.alpha)
        self.assertEqual((newest.alpha, newest.dx, newest.dy), (255, 0.0, 0.0))

    def test_only_marks_younger_than_their_life_are_shown(self):
        self.assertEqual(len(zz_marks(4.0, 1.0)), 2)   # 1.5 秒和 3.0 秒冒出的两个；0 秒那个已经飘走了

    def test_older_marks_are_higher_and_fainter(self):
        a, b = sorted(zz_marks(4.0, 1.0), key=lambda m: m.alpha)
        self.assertLess(a.dy, b.dy)       # 更老的飘得更高（dy 更负）
        self.assertGreater(a.dx, b.dx)    # 也更往右

    def test_scale_multiplies_distance_and_size(self):
        a = zz_marks(4.0, 1.0)
        b = zz_marks(4.0, 2.0)
        self.assertAlmostEqual(b[0].dy, 2 * a[0].dy)
        self.assertEqual(b[0].size, 2 * a[0].size)

    def test_big_and_small_alternate(self):
        texts = {m.text for m in zz_marks(4.0, 1.0)}
        self.assertEqual(texts, {'Z', 'z'})

    def test_nothing_older_than_life(self):
        self.assertTrue(all(m.alpha > 0 for m in zz_marks(100.0, 1.0)))
        self.assertLessEqual(len(zz_marks(100.0, 1.0)), int(ZZ_LIFE / 1.5) + 1)


if __name__ == '__main__':
    unittest.main()
