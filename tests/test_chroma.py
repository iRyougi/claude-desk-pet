import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from chroma import estimate_bg, key_green, pixels, split_valleys  # noqa: E402

BG = (2, 250, 5)
ORANGE = (255, 140, 30)
WHITE = (250, 245, 240)


def canvas(size=(40, 40), bg=BG):
    return Image.new('RGB', size, bg)


class EstimateBgTest(unittest.TestCase):
    def test_uses_green_border_pixels(self):
        im = canvas(bg=(3, 248, 40))
        self.assertEqual(estimate_bg(im), (3, 248, 40))

    def test_ignores_subject_touching_the_border(self):
        im = canvas()
        for x in range(0, 10):
            im.putpixel((x, 0), ORANGE)  # 头发碰到了画布上边缘
        self.assertEqual(estimate_bg(im), BG)


class KeyGreenTest(unittest.TestCase):
    def test_background_becomes_transparent_and_subject_stays_opaque(self):
        im = canvas()
        for x in range(15, 25):
            for y in range(15, 25):
                im.putpixel((x, y), ORANGE)
        out = key_green(im)
        self.assertEqual(out.mode, 'RGBA')
        self.assertEqual(out.getpixel((1, 1))[3], 0)
        self.assertEqual(out.getpixel((20, 20)), ORANGE + (255,))

    def test_enclosed_green_hole_is_also_removed(self):
        im = canvas()
        for x in range(10, 30):
            for y in range(10, 30):
                im.putpixel((x, y), WHITE)
        for x in range(18, 22):
            for y in range(18, 22):
                im.putpixel((x, y), BG)  # 头发缝隙里漏出来的绿
        out = key_green(im)
        self.assertEqual(out.getpixel((20, 20))[3], 0)
        self.assertEqual(out.getpixel((12, 12))[3], 255)

    def test_edge_blend_is_partially_transparent_and_despilled(self):
        im = canvas()
        for x in range(10, 30):
            for y in range(10, 30):
                im.putpixel((x, y), WHITE)
        im.putpixel((9, 20), (126, 247, 122))  # 白色和绿色各占一半的抗锯齿像素
        r, g, b, a = key_green(im).getpixel((9, 20))
        self.assertTrue(0 < a < 255)
        self.assertLessEqual(g, max(r, b))

    def test_noisy_background_is_fully_transparent(self):
        # AI 出的绿底常有轻微的明暗噪点，不能留下微弱的半透明残影
        im = canvas()
        for x in range(40):
            for y in range(40):
                if (x + y) % 2:
                    im.putpixel((x, y), (2, 230, 45))
        for x in range(15, 25):
            for y in range(15, 25):
                im.putpixel((x, y), ORANGE)
        out = key_green(im)
        stray = [out.getpixel((x, y))[3] for x in range(40) for y in range(40)
                 if not (15 <= x < 25 and 15 <= y < 25)]
        self.assertEqual(max(stray), 0)

    def test_does_not_modify_the_input(self):
        im = canvas()
        before = pixels(im)
        key_green(im)
        self.assertEqual(pixels(im), before)

    def test_per_image_background_color(self):
        im = canvas(bg=(2, 250, 49))
        for x in range(15, 25):
            for y in range(15, 25):
                im.putpixel((x, y), ORANGE)
        out = key_green(im)
        self.assertEqual(out.getpixel((1, 1))[3], 0)
        self.assertEqual(out.getpixel((20, 20))[3], 255)


class SplitValleysTest(unittest.TestCase):
    def test_cuts_at_the_emptiest_column_near_each_boundary(self):
        # 4 个"身体"，第 2、3 个之间发梢相连（那一列覆盖最少但不为 0）
        cols = [0] * 400
        for start in (10, 110, 215, 310):
            for x in range(start, start + 80):
                cols[x] = 50
        for x in range(190, 215):
            cols[x] = 3
        cuts = split_valleys(cols, 4)
        self.assertEqual(len(cuts), 4)
        self.assertEqual(cuts[0][0], 0)
        self.assertEqual(cuts[-1][1], 400)
        for left, right in zip(cuts, cuts[1:]):
            self.assertEqual(left[1], right[0])  # 相邻两帧共用同一条切线
        self.assertTrue(190 <= cuts[1][1] <= 215)

    def test_single_frame_covers_everything(self):
        self.assertEqual(split_valleys([1, 2, 3], 1), [(0, 3)])


if __name__ == '__main__':
    unittest.main()
