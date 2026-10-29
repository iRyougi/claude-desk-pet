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


if __name__ == '__main__':
    unittest.main()
