import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from chroma import pixels  # noqa: E402
from prep_sprites import align_on_head, head_x  # noqa: E402

SOLID = (255, 140, 30, 255)


def figure(head_left: int, body_left: int, size=(80, 100)) -> Image.Image:
    """头在上（20 宽 x 25 高），身体在下（30 宽 x 75 高），可以各自左右偏移。"""
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    for x in range(head_left, head_left + 20):
        for y in range(0, 25):
            im.putpixel((x, y), SOLID)
    for x in range(body_left, body_left + 30):
        for y in range(25, 100):
            im.putpixel((x, y), SOLID)
    return im


class HeadXTest(unittest.TestCase):
    def test_is_the_center_of_the_top_quarter(self):
        self.assertAlmostEqual(head_x(figure(30, 10)), 39.5, delta=0.6)

    def test_ignores_the_body_below(self):
        self.assertAlmostEqual(head_x(figure(30, 10)), head_x(figure(30, 45)), delta=0.6)


class AlignOnHeadTest(unittest.TestCase):
    def test_heads_end_up_at_the_same_x_even_if_bodies_differ(self):
        a, b = figure(10, 5), figure(40, 30)  # 两帧的头相差 30 像素，身体位置也各不相同
        out = align_on_head([a, b])
        self.assertEqual(out[0].size, out[1].size)
        self.assertAlmostEqual(head_x(out[0]), head_x(out[1]), delta=0.6)

    def test_nothing_is_cropped(self):
        a, b = figure(10, 5), figure(40, 30)
        for src, dst in zip((a, b), align_on_head([a, b])):
            self.assertEqual(sum(1 for p in pixels(src) if p[3]), sum(1 for p in pixels(dst) if p[3]))

    def test_single_frame_is_kept(self):
        a = figure(10, 5)
        self.assertEqual(len(align_on_head([a])), 1)


if __name__ == '__main__':
    unittest.main()
