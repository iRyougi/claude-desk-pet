import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from PIL import Image, ImageFont  # noqa: E402

from bubble import BubbleLayout  # noqa: E402
from render import BubbleStyle, bubble_image, compose, draw_marks, paste  # noqa: E402
from effects import Mark  # noqa: E402

STYLE = BubbleStyle(font=ImageFont.load_default(13), small=ImageFont.load_default(11), scale=1.0)


def alphas(im):
    return list(im.getchannel('A').tobytes())


class BubbleImageTest(unittest.TestCase):
    def test_two_lines_taller_than_one(self):
        one = bubble_image(BubbleLayout(('abc',)), STYLE)
        two = bubble_image(BubbleLayout(('abc', 'def')), STYLE)
        self.assertGreater(two.height, one.height)

    def test_sub_line_makes_it_taller(self):
        plain = bubble_image(BubbleLayout(('abc',)), STYLE)
        with_sub = bubble_image(BubbleLayout(('abc',), 'x · y'), STYLE)
        self.assertGreater(with_sub.height, plain.height)

    def test_wider_text_wider_bubble(self):
        short = bubble_image(BubbleLayout(('ab',)), STYLE)
        long = bubble_image(BubbleLayout(('abcdefghijkl',)), STYLE)
        self.assertGreater(long.width, short.width)

    def test_edges_are_antialiased(self):
        a = alphas(bubble_image(BubbleLayout(('abc',)), STYLE))
        self.assertTrue(any(0 < v < 255 for v in a))
        self.assertEqual(a[0], 0)  # 圆角外面的角落是透明的

    def test_tail_tip_at_bottom_center(self):
        im = bubble_image(BubbleLayout(('abcdef',)), STYLE)
        self.assertGreater(im.getpixel((im.width // 2, im.height - 3))[3], 0)
        self.assertEqual(im.getpixel((2, im.height - 3))[3], 0)


class PasteTest(unittest.TestCase):
    def test_clips_negative_offset_without_error(self):
        dst = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        paste(dst, Image.new('RGBA', (3, 3), (255, 0, 0, 255)), -1, -1)
        self.assertEqual(dst.getpixel((0, 0))[3], 255)
        self.assertEqual(dst.getpixel((2, 2))[3], 0)

    def test_fully_outside_does_nothing(self):
        dst = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        paste(dst, Image.new('RGBA', (3, 3), (255, 0, 0, 255)), 10, 10)
        self.assertEqual(set(alphas(dst)), {0})


class ComposeTest(unittest.TestCase):
    def sprite(self, alpha=60):
        return Image.new('RGBA', (10, 20), (255, 0, 0, alpha))

    def test_keeps_partial_alpha(self):
        out = compose(self.sprite(60), sprite_bottom=90, bubble=None, bubble_bottom=0, min_w=40, height=100)
        self.assertEqual(out.getpixel((20, 85))[3], 60)

    def test_sprite_bottom_lands_on_line(self):
        out = compose(self.sprite(255), sprite_bottom=90, bubble=None, bubble_bottom=0, min_w=40, height=100)
        self.assertEqual(out.getpixel((20, 89))[3], 255)
        self.assertEqual(out.getpixel((20, 90))[3], 0)
        self.assertEqual(out.getpixel((20, 69))[3], 0)

    def test_rest_is_transparent(self):
        out = compose(self.sprite(255), sprite_bottom=90, bubble=None, bubble_bottom=0, min_w=40, height=100)
        self.assertEqual(out.getpixel((0, 0))[3], 0)
        self.assertEqual(out.getpixel((39, 99))[3], 0)

    def test_width_is_max_of_min_and_bubble(self):
        wide = Image.new('RGBA', (80, 10), (255, 255, 255, 255))
        self.assertEqual(compose(self.sprite(), 90, None, 0, 40, 100).width, 40)
        self.assertEqual(compose(self.sprite(), 90, wide, 20, 40, 100).width, 80)

    def test_bubble_bottom_and_centered(self):
        b = Image.new('RGBA', (20, 10), (255, 255, 255, 255))
        out = compose(self.sprite(), 90, b, bubble_bottom=30, min_w=40, height=100)
        self.assertEqual(out.getpixel((20, 29))[3], 255)
        self.assertEqual(out.getpixel((20, 30))[3], 0)
        self.assertEqual(out.getpixel((9, 25))[3], 0)
        self.assertEqual(out.getpixel((10, 25))[3], 255)


class DrawMarksTest(unittest.TestCase):
    def test_draws_near_the_origin(self):
        im = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
        draw_marks(im, [Mark('Z', 0.0, 0.0, 255, 20)], 30, 30)
        box = im.getchannel('A').getbbox()
        self.assertIsNotNone(box)
        self.assertTrue(25 <= box[0] <= 40 and 25 <= box[1] <= 45, box)

    def test_invisible_mark_draws_nothing(self):
        im = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
        draw_marks(im, [Mark('Z', 0.0, 0.0, 0, 20)], 30, 30)
        self.assertIsNone(im.getchannel('A').getbbox())

    def test_mark_has_a_light_fill_and_dark_outline(self):
        im = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
        draw_marks(im, [Mark('Z', 0.0, 0.0, 255, 30)], 20, 20)
        px = [p for p in im.convert('RGBA').get_flattened_data() if p[3] == 255]
        self.assertTrue(any(min(p[:3]) > 200 for p in px))   # 浅色的字
        self.assertTrue(any(max(p[:3]) < 90 for p in px))    # 深色的描边


if __name__ == '__main__':
    unittest.main()
