import colorsys
import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from tone import adjust, measure  # noqa: E402


def hsv(h: float, s: float, v: float) -> tuple:
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)) + (255,)


def sheet(hair: tuple, white: tuple, extra: tuple = ()) -> Image.Image:
    """左边一块头发色，右边一块白色，再加若干额外颜色的单像素。"""
    im = Image.new('RGBA', (40, 20), (0, 0, 0, 0))
    for x in range(0, 20):
        for y in range(20):
            im.putpixel((x, y), hair)
    for x in range(20, 40):
        for y in range(20):
            im.putpixel((x, y), white)
    for i, c in enumerate(extra):
        im.putpixel((i, 0), c)
    return im


OLD_HAIR = hsv(0.0451, 0.72, 0.772)
OLD_WHITE = (246, 229, 221, 255)
NEW_HAIR = hsv(0.0548, 0.827, 0.844)
NEW_WHITE = (252, 241, 233, 255)


class MeasureTest(unittest.TestCase):
    def test_reads_hair_and_white_tone(self):
        tone = measure([sheet(OLD_HAIR, OLD_WHITE)])
        self.assertAlmostEqual(tone.hair_h, 0.0451, delta=0.003)
        self.assertAlmostEqual(tone.hair_s, 0.72, delta=0.01)
        self.assertAlmostEqual(tone.hair_v, 0.772, delta=0.01)
        for got, want in zip(tone.white, OLD_WHITE[:3]):
            self.assertAlmostEqual(got, want, delta=1)

    def test_ignores_transparent_pixels(self):
        im = sheet(OLD_HAIR, OLD_WHITE)
        for x in range(0, 5):
            im.putpixel((x, 5), NEW_HAIR[:3] + (0,))  # 完全透明，不该参与统计
        tone = measure([im])
        self.assertAlmostEqual(tone.hair_s, 0.72, delta=0.01)

    def test_raises_without_hair(self):
        with self.assertRaises(ValueError):
            measure([sheet((0, 0, 255, 255), (0, 0, 255, 255))])


class AdjustTest(unittest.TestCase):
    def test_moves_tone_to_the_reference(self):
        src, ref = measure([sheet(NEW_HAIR, NEW_WHITE)]), measure([sheet(OLD_HAIR, OLD_WHITE)])
        out = adjust(sheet(NEW_HAIR, NEW_WHITE), src, ref)
        got = measure([out])
        self.assertAlmostEqual(got.hair_h, ref.hair_h, delta=0.003)
        self.assertAlmostEqual(got.hair_s, ref.hair_s, delta=0.01)
        self.assertAlmostEqual(got.hair_v, ref.hair_v, delta=0.01)
        for a, b in zip(got.white, ref.white):
            self.assertAlmostEqual(a, b, delta=1.5)

    def test_other_colors_are_untouched(self):
        brown, blue = (60, 30, 25, 255), (30, 60, 200, 255)
        src, ref = measure([sheet(NEW_HAIR, NEW_WHITE)]), measure([sheet(OLD_HAIR, OLD_WHITE)])
        out = adjust(sheet(NEW_HAIR, NEW_WHITE, (brown, blue)), src, ref)
        self.assertEqual(out.getpixel((0, 0)), brown)
        self.assertEqual(out.getpixel((1, 0)), blue)

    def test_alpha_and_transparent_pixels_are_preserved(self):
        im = sheet(NEW_HAIR, NEW_WHITE)
        im.putpixel((10, 10), NEW_HAIR[:3] + (128,))
        im.putpixel((11, 10), (0, 0, 0, 0))
        src, ref = measure([sheet(NEW_HAIR, NEW_WHITE)]), measure([sheet(OLD_HAIR, OLD_WHITE)])
        out = adjust(im, src, ref)
        self.assertEqual(out.getpixel((10, 10))[3], 128)
        self.assertEqual(out.getpixel((11, 10)), (0, 0, 0, 0))

    def test_identical_tone_is_a_noop(self):
        tone = measure([sheet(NEW_HAIR, NEW_WHITE)])
        im = sheet(NEW_HAIR, NEW_WHITE)
        out = adjust(im, tone, tone)
        for p in ((5, 5), (30, 5)):
            for a, b in zip(out.getpixel(p), im.getpixel(p)):
                self.assertAlmostEqual(a, b, delta=1)

    def test_does_not_modify_the_input(self):
        im = sheet(NEW_HAIR, NEW_WHITE)
        before = im.copy()
        src, ref = measure([im]), measure([sheet(OLD_HAIR, OLD_WHITE)])
        adjust(im, src, ref)
        self.assertEqual(list(im.tobytes()), list(before.tobytes()))



def spread_sheet(hair_values: list, dark=None, skin=None) -> Image.Image:
    """头发的饱和度/明度各不相同的一张图；可选地加一块深色和一块皮肤色。"""
    im = Image.new('RGBA', (len(hair_values), 3), (0, 0, 0, 0))
    for x, (s, v) in enumerate(hair_values):
        for y in range(3):
            im.putpixel((x, y), hsv(0.05, s, v))
    extra = Image.new('RGBA', (60, 3), (0, 0, 0, 0))
    for x in range(20):
        for y in range(3):
            extra.putpixel((x, y), NEW_WHITE)
            if dark:
                extra.putpixel((x + 20, y), hsv(0.03, dark, 0.15))
            if skin:
                extra.putpixel((x + 40, y), hsv(0.06, skin, 0.96))
    out = Image.new('RGBA', (im.width + 60, 3), (0, 0, 0, 0))
    out.paste(im, (0, 0))
    out.paste(extra, (im.width, 0))
    return out


def values(im: Image.Image, pick) -> list:
    out = []
    for x in range(im.width):
        r, g, b, a = im.getpixel((x, 1))
        if a:
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if pick(h, s, v):
                out.append((s, v))
    return out


def is_hair(h, s, v):
    return 0.015 <= h <= 0.11 and s >= 0.5 and v >= 0.45


class DistributionTest(unittest.TestCase):
    """平均值对上了不够：原图头发是一大块明度 0.97 的平涂橙，新图主色只有 0.92，要整条分布对齐。"""

    def setUp(self):
        self.new = [(0.62 + 0.30 * i / 99, 0.62 + 0.30 * i / 99) for i in range(100)]   # S、V 都在 0.62–0.92
        self.old = [(0.64 + 0.13 * i / 99, 0.70 + 0.28 * i / 99) for i in range(100)]   # S 窄，V 到 0.98

    def test_hair_saturation_and_value_ranges_follow_the_reference(self):
        src, ref = spread_sheet(self.new), spread_sheet(self.old)
        out = adjust(src, measure([src]), measure([ref]))
        got = values(out, is_hair)
        s = sorted(x[0] for x in got)
        v = sorted(x[1] for x in got)
        self.assertAlmostEqual(s[-5], 0.77, delta=0.04)   # 新图 S 最高到 0.92，要压到原图的 0.77 附近
        self.assertAlmostEqual(v[-5], 0.98, delta=0.04)   # 新图 V 最高 0.92，要提亮到原图的 0.98 附近
        self.assertAlmostEqual(v[4], 0.70, delta=0.04)

    def test_dark_pixels_lose_their_saturation(self):
        src, ref = spread_sheet(self.new, dark=0.62), spread_sheet(self.old, dark=0.35)
        out = adjust(src, measure([src]), measure([ref]))
        r, g, b, _ = out.getpixel((len(self.new) + 25, 1))
        self.assertAlmostEqual(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1], 0.35, delta=0.04)

    def test_skin_saturation_follows_the_reference(self):
        src, ref = spread_sheet(self.new, skin=0.20), spread_sheet(self.old, skin=0.15)
        out = adjust(src, measure([src]), measure([ref]))
        r, g, b, _ = out.getpixel((len(self.new) + 45, 1))
        self.assertAlmostEqual(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1], 0.15, delta=0.03)

    def test_missing_dark_or_skin_in_either_set_changes_nothing(self):
        src = spread_sheet(self.new, dark=0.62)
        ref = spread_sheet(self.old)              # 参考图里没有深色，没法对齐
        out = adjust(src, measure([src]), measure([ref]))
        self.assertEqual(out.getpixel((len(self.new) + 25, 1)), src.getpixel((len(self.new) + 25, 1)))


if __name__ == '__main__':
    unittest.main()
