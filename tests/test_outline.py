import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from outline import OUTLINE, add_outline  # noqa: E402

ORANGE = (255, 140, 30, 255)


def block(size=30, lo=10, hi=20) -> Image.Image:
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    for x in range(lo, hi):
        for y in range(lo, hi):
            im.putpixel((x, y), ORANGE)
    return im


class OutlineTest(unittest.TestCase):
    def test_first_ring_is_solid_outline_color(self):
        out = add_outline(block())
        self.assertEqual(out.getpixel((9, 15)), OUTLINE + (255,))
        self.assertEqual(out.getpixel((20, 15)), OUTLINE + (255,))

    def test_second_ring_is_softer(self):
        a = add_outline(block()).getpixel((8, 15))[3]
        self.assertTrue(0 < a < 255)

    def test_nothing_beyond_two_pixels(self):
        out = add_outline(block())
        self.assertEqual(out.getpixel((7, 15))[3], 0)
        self.assertEqual(out.getpixel((0, 0))[3], 0)

    def test_character_pixels_are_untouched(self):
        out = add_outline(block())
        for p in ((10, 10), (15, 15), (19, 19)):
            self.assertEqual(out.getpixel(p), ORANGE)

    def test_never_makes_a_pixel_more_transparent(self):
        im = block()
        im.putpixel((9, 15), ORANGE[:3] + (120,))  # 抗锯齿的半透明边缘
        out = add_outline(im)
        self.assertGreaterEqual(out.getpixel((9, 15))[3], 120)

    def test_does_not_modify_the_input(self):
        im = block()
        before = im.tobytes()
        add_outline(im)
        self.assertEqual(im.tobytes(), before)

    def test_size_is_unchanged(self):
        self.assertEqual(add_outline(block()).size, (30, 30))


if __name__ == '__main__':
    unittest.main()
