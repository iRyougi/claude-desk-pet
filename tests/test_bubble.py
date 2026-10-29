import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from bubble import BubbleLayout, fit_end, layout, shorten_path  # noqa: E402

M = len   # 每个字宽 1：测试里"宽度"就是字数
W = 10


class ShortenPathTest(unittest.TestCase):
    def test_keeps_first_dir_and_file_name(self):
        self.assertEqual(shorten_path('pet/sprites/extra/motion.py'), 'pet/…/motion.py')

    def test_short_path_unchanged(self):
        self.assertEqual(shorten_path('pet/motion.py'), 'pet/motion.py')

    def test_backslash_path(self):
        self.assertEqual(shorten_path('C:\\code\\pet\\motion.py'), 'C:\\…\\motion.py')


class FitEndTest(unittest.TestCase):
    def test_fits_unchanged(self):
        self.assertEqual(fit_end('一二三', M, W), '一二三')

    def test_too_long_gets_ellipsis_within_width(self):
        out = fit_end('一二三四五六七八九十十一', M, W)
        self.assertEqual(out, '一二三四五六七八九…')
        self.assertLessEqual(M(out), W)


class LayoutTest(unittest.TestCase):
    def test_short_text_one_line(self):
        self.assertEqual(layout('轮到你啦！', M, W), BubbleLayout(('轮到你啦！',)))

    def test_wraps_into_two_lines(self):
        text = '一二三四五六七八九十甲乙丙丁戊'
        self.assertEqual(layout(text, M, W).lines, ('一二三四五六七八九十', '甲乙丙丁戊'))

    def test_more_than_two_lines_truncates_second(self):
        text = '一二三四五六七八九十' + '甲乙丙丁戊己庚辛壬癸' + '子丑寅卯'
        lines = layout(text, M, W).lines
        self.assertEqual(lines, ('一二三四五六七八九十', '甲乙丙丁戊己庚辛壬…'))

    def test_long_path_is_shortened_in_the_middle(self):
        lines = layout('在改 pet/sprites/extra/motion.py', M, W).lines
        self.assertEqual(''.join(lines), '在改 pet/…/motion.py')
        self.assertEqual(len(lines), 2)

    def test_path_left_alone_when_it_fits(self):
        self.assertEqual(''.join(layout('改 a/b/c.py', M, W).lines), '改 a/b/c.py')

    def test_sub_line_leaves_one_body_line(self):
        out = layout('一二三四五六七八九十十一', M, W, sub='claude-desk-pet · sts2-ai 在等你')
        self.assertEqual(out.lines, ('一二三四五六七八九…',))
        self.assertEqual(out.sub, 'claude-de…')

    def test_line_does_not_start_with_space(self):
        lines = layout('aaaaaaaaaa bbb', M, W).lines
        self.assertEqual(lines, ('aaaaaaaaaa', 'bbb'))

    def test_newline_starts_new_line(self):
        self.assertEqual(layout('第一行\n第二行', M, W).lines, ('第一行', '第二行'))

    def test_empty_text(self):
        self.assertEqual(layout('', M, W).lines, ('',))

    def test_trailing_newline_ignored(self):
        self.assertEqual(layout('完成\n', M, W).lines, ('完成',))
        self.assertEqual(layout('完成\n', M, W, sub='x').lines, ('完成',))


if __name__ == '__main__':
    unittest.main()
