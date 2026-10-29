import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from blink import BLINK_CLOSED, closed, start, step  # noqa: E402


class FixedRng:
    """uniform 永远返回 u，random 永远返回 r。"""
    def __init__(self, u=3.0, r=0.5):
        self.u, self.r = u, r

    def uniform(self, a, b):
        return self.u

    def random(self):
        return self.r


class BlinkTest(unittest.TestCase):
    def test_eyes_open_until_the_first_blink(self):
        b = start(0.0, FixedRng())
        self.assertFalse(closed(step(b, 2.9, FixedRng()), 2.9))

    def test_a_blink_closes_the_eyes_briefly(self):
        b = step(start(0.0, FixedRng()), 3.0, FixedRng())
        self.assertTrue(closed(b, 3.05))
        self.assertFalse(closed(b, 3.0 + BLINK_CLOSED + 0.01))
        self.assertAlmostEqual(b.next_at, 3.0 + BLINK_CLOSED + 3.0)

    def test_sometimes_blinks_twice(self):
        rng = FixedRng(r=0.1)
        b = step(start(0.0, rng), 3.0, rng)
        self.assertIsNotNone(b.again_at)
        b2 = step(b, b.again_at, rng)
        self.assertTrue(closed(b2, b.again_at + 0.05))
        self.assertIsNone(b2.again_at)

    def test_single_blink_when_the_dice_say_so(self):
        b = step(start(0.0, FixedRng(r=0.9)), 3.0, FixedRng(r=0.9))
        self.assertIsNone(b.again_at)

    def test_rate_over_a_long_time(self):
        rng, b, t, blinks, was = random.Random(7), None, 0.0, 0, False
        b = start(0.0, rng)
        while t < 1000.0:
            b = step(b, t, rng)
            now = closed(b, t)
            blinks += now and not was
            was, t = now, t + 1 / 30
        self.assertTrue(150 < blinks < 450, blinks)


if __name__ == '__main__':
    unittest.main()
