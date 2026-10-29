import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from PIL import Image, ImageDraw  # noqa: E402

from blink_patch import build_patch, export_image, placement  # noqa: E402

SKIN = (240, 210, 190, 255)


def sprite():
    """100×160 的假立绘：中间一块肤色身体，四周透明。"""
    im = Image.new('RGBA', (100, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((10, 10, 89, 149), fill=SKIN)
    return im


def to_export(p, x, y):
    return p.x + x * p.k, p.y + y * p.k


class PlacementTest(unittest.TestCase):
    def test_fits_into_the_canvas_with_feet_60px_above_bottom(self):
        p = placement((100, 160))
        self.assertAlmostEqual(p.k, 8.5)
        self.assertEqual((p.x, p.y), ((1024 - 850) // 2, 1536 - 60 - 1360))

    def test_export_is_green_outside_and_sprite_inside(self):
        im, p = export_image(sprite()), placement((100, 160))
        self.assertEqual(im.size, (1024, 1536))
        self.assertEqual(im.getpixel((0, 0)), (0, 255, 0))
        x, y = to_export(p, 50, 80)
        self.assertEqual(im.getpixel((round(x), round(y))), SKIN[:3])


class BuildPatchTest(unittest.TestCase):
    def edited(self, s, block=(40, 40, 60, 50)):
        a = export_image(s)
        b = a.copy()
        p = placement(s.size)
        d = ImageDraw.Draw(b)
        d.rectangle((*to_export(p, block[0], block[1]), *to_export(p, block[2], block[3])), fill=(40, 30, 30))
        # 压缩噪点：一条贯穿身体的 2 像素细线，不能被当成改动
        d.line([to_export(p, 10, 120), to_export(p, 89, 120)], fill=(0, 0, 0), width=2)
        return a, b

    def test_patch_covers_the_changed_block_only(self):
        s = sprite()
        a, b = self.edited(s)
        patch, (x, y) = build_patch(s, a, b)
        self.assertTrue(35 <= x <= 40 and 35 <= y <= 40, (x, y))
        self.assertTrue(60 <= x + patch.width <= 65 and 50 <= y + patch.height <= 55, (x, y, patch.size))

    def test_patch_center_is_opaque_and_dark(self):
        s = sprite()
        a, b = self.edited(s)
        patch, (x, y) = build_patch(s, a, b)
        r, g, bl, alpha = patch.getpixel((50 - x, 45 - y))
        self.assertEqual(alpha, 255)
        self.assertLess(r, 80)

    def test_patch_is_transparent_where_the_sprite_is(self):
        s = sprite()
        a, b = self.edited(s, block=(0, 40, 20, 50))  # 一半在身体外面
        patch, (x, y) = build_patch(s, a, b)
        self.assertEqual(patch.getpixel((5 - x, 45 - y))[3], 0)

    def test_no_change_is_an_error(self):
        s = sprite()
        a = export_image(s)
        with self.assertRaises(ValueError):
            build_patch(s, a, a.copy())


if __name__ == '__main__':
    unittest.main()
