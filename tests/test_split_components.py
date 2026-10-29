import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from chroma import pixels  # noqa: E402
from fragments import split_by_components  # noqa: E402

SOLID = (255, 140, 30, 255)


def strip(*blocks, size=(300, 120)) -> Image.Image:
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    for x0, y0, x1, y1 in blocks:
        for x in range(x0, x1):
            for y in range(y0, y1):
                im.putpixel((x, y), SOLID)
    return im


def opaque_count(im) -> int:
    return sum(1 for p in pixels(im) if p[3] > 0)


# 三个"人"：A 又高又靠左，它的"靴尖"（下面那条）伸到 x=110；B 从 x=100 开始，头顶比 A 的靴尖高——
# 两者的横向范围重叠，按列切分线一定会切到其中一个。
A = [(10, 10, 60, 110), (60, 100, 110, 110)]
B = [(100, 10, 150, 90), (150, 80, 160, 90)]
C = [(200, 10, 260, 110)]


class SplitByComponentsTest(unittest.TestCase):
    def test_each_frame_is_exactly_one_figure_even_when_their_x_ranges_overlap(self):
        im = strip(*A, *B, *C)
        frames = split_by_components(im, 3)
        self.assertEqual(len(frames), 3)
        self.assertEqual([opaque_count(f) for f in frames], [50 * 100 + 50 * 10, 50 * 80 + 10 * 10, 60 * 100])

    def test_frames_are_ordered_left_to_right(self):
        frames = split_by_components(strip(*C, *A, *B), 3)
        left = [min(x for x in range(f.width) if any(f.getpixel((x, y))[3] for y in range(f.height))) for f in frames]
        self.assertEqual(left, sorted(left))

    def test_frames_keep_the_original_canvas_size(self):
        for f in split_by_components(strip(*A, *B, *C), 3):
            self.assertEqual(f.size, (300, 120))

    def test_small_specks_are_not_counted_as_frames(self):
        frames = split_by_components(strip(*A, *B, *C, (280, 5, 283, 8)), 3)
        self.assertEqual(len(frames), 3)

    def test_returns_none_when_figures_touch_and_cannot_be_told_apart(self):
        touching = strip((10, 10, 60, 110), (60, 10, 110, 110), *C)   # 前两个连在一起
        self.assertIsNone(split_by_components(touching, 3))

    def test_returns_none_when_there_are_too_many_pieces(self):
        self.assertIsNone(split_by_components(strip(*A, *B, *C), 2))

    def test_soft_edge_pixels_next_to_a_figure_are_kept_with_it(self):
        im = strip(*A, *B, *C)
        im.putpixel((9, 50), SOLID[:3] + (25,))   # A 左边的淡边，低于"实心"阈值
        frames = split_by_components(im, 3)
        self.assertEqual(frames[0].getpixel((9, 50))[3], 25)

    def test_does_not_modify_the_input(self):
        im = strip(*A, *B, *C)
        before = pixels(im)
        split_by_components(im, 3)
        self.assertEqual(pixels(im), before)


if __name__ == '__main__':
    unittest.main()
