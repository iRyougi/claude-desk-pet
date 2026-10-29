import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from chroma import pixels  # noqa: E402
from fragments import drop_fragments  # noqa: E402

SOLID = (255, 140, 30, 255)


def canvas(*blocks) -> Image.Image:
    """200x200 的透明画布；blocks 是 (x0, y0, x1, y1) 的实心方块。主体放 (50,50)-(150,150)，面积 10000。"""
    im = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    for x0, y0, x1, y1 in blocks:
        for x in range(x0, x1):
            for y in range(y0, y1):
                im.putpixel((x, y), SOLID)
    return im


def opaque_at(im, x, y) -> bool:
    return im.getpixel((x, y))[3] > 0


MAIN = (50, 50, 150, 150)


class DropFragmentsTest(unittest.TestCase):
    def test_small_piece_touching_the_left_edge_is_removed(self):
        out = drop_fragments(canvas(MAIN, (0, 160, 10, 170)))   # 邻居帧的靴尖：100 像素，约 1%
        self.assertFalse(opaque_at(out, 5, 165))
        self.assertTrue(opaque_at(out, 100, 100))

    def test_small_piece_touching_the_right_edge_is_removed(self):
        out = drop_fragments(canvas(MAIN, (190, 20, 200, 30)))
        self.assertFalse(opaque_at(out, 195, 25))

    def test_tiny_isolated_speck_is_removed(self):
        out = drop_fragments(canvas(MAIN, (20, 20, 22, 22)))    # 4 像素，不贴边
        self.assertFalse(opaque_at(out, 20, 20))

    def test_a_modest_detached_piece_away_from_the_edge_is_kept(self):
        out = drop_fragments(canvas(MAIN, (20, 100, 26, 106)))  # 36 像素，像流苏耳坠，不贴边
        self.assertTrue(opaque_at(out, 22, 102))

    def test_a_big_piece_touching_the_edge_is_kept(self):
        out = drop_fragments(canvas(MAIN, (0, 160, 30, 190)))   # 900 像素，约 9%，是角色的一部分
        self.assertTrue(opaque_at(out, 10, 170))

    def test_faint_halo_around_a_removed_piece_is_cleared_too(self):
        im = canvas(MAIN, (0, 160, 10, 170))
        for y in range(158, 172):
            im.putpixel((11, y), SOLID[:3] + (25,))             # 抗锯齿留下的淡边，低于"实心"阈值
        out = drop_fragments(im)
        self.assertEqual(out.getpixel((11, 165))[3], 0)

    def test_the_main_body_is_untouched_pixel_for_pixel(self):
        im = canvas(MAIN, (0, 160, 10, 170))
        out = drop_fragments(im)
        for x in range(50, 150):
            for y in range(50, 150):
                self.assertEqual(out.getpixel((x, y)), im.getpixel((x, y)))

    def test_does_not_modify_the_input(self):
        im = canvas(MAIN, (0, 160, 10, 170))
        before = pixels(im)
        drop_fragments(im)
        self.assertEqual(pixels(im), before)

    def test_empty_image_is_returned_as_is(self):
        out = drop_fragments(Image.new('RGBA', (20, 20), (0, 0, 0, 0)))
        self.assertEqual(out.size, (20, 20))


if __name__ == '__main__':
    unittest.main()
