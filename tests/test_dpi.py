import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from dpi import scale_of_dpi  # noqa: E402


class ScaleOfDpiTest(unittest.TestCase):
    def test_common_values(self):
        self.assertEqual(scale_of_dpi(96), 1.0)
        self.assertEqual(scale_of_dpi(144), 1.5)
        self.assertEqual(scale_of_dpi(192), 2.0)

    def test_bad_value_falls_back_to_one(self):
        self.assertEqual(scale_of_dpi(0), 1.0)
        self.assertEqual(scale_of_dpi(-5), 1.0)


if __name__ == '__main__':
    unittest.main()
