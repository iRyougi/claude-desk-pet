import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from PIL import Image  # noqa: E402

from layered import premultiplied_bgra  # noqa: E402


class PremultiplyTest(unittest.TestCase):
    def test_half_transparent_red_becomes_premultiplied_bgra(self):
        im = Image.new('RGBA', (1, 1), (255, 0, 0, 128))
        self.assertEqual(premultiplied_bgra(im), bytes([0, 0, 128, 128]))

    def test_fully_transparent_pixel_is_all_zero(self):
        im = Image.new('RGBA', (1, 1), (200, 100, 50, 0))
        self.assertEqual(premultiplied_bgra(im), bytes([0, 0, 0, 0]))

    def test_opaque_pixel_keeps_color(self):
        im = Image.new('RGBA', (1, 1), (10, 20, 30, 255))
        self.assertEqual(premultiplied_bgra(im), bytes([30, 20, 10, 255]))

    def test_rgb_input_is_treated_as_opaque(self):
        im = Image.new('RGB', (2, 1), (1, 2, 3))
        self.assertEqual(premultiplied_bgra(im), bytes([3, 2, 1, 255] * 2))


if __name__ == '__main__':
    unittest.main()
