import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from commands import Command, parse  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_bare_pet_means_show(self):
        self.assertEqual(parse(''), Command('show'))
        self.assertEqual(parse('   '), Command('show'))

    def test_simple_commands(self):
        for word in ('show', 'hide', 'home', 'rest', 'quit'):
            self.assertEqual(parse(word), Command(word))

    def test_size(self):
        self.assertEqual(parse('size small'), Command('size', '小'))
        self.assertEqual(parse('size medium'), Command('size', '中'))
        self.assertEqual(parse('size large'), Command('size', '大'))

    def test_switches(self):
        self.assertEqual(parse('follow on'), Command('follow', True))
        self.assertEqual(parse('roam off'), Command('roam', False))
        self.assertEqual(parse('sound off'), Command('sound', False))
        self.assertEqual(parse('chat on'), Command('chat', True))

    def test_break(self):
        self.assertEqual(parse('break off'), Command('break', False))
        self.assertEqual(parse('break 45'), Command('break-minutes', 45))
        self.assertEqual(parse('break test'), Command('break-test'))

    def test_case_and_spaces_do_not_matter(self):
        self.assertEqual(parse('  Size   LARGE '), Command('size', '大'))

    def test_mistakes_give_a_message(self):
        for bad in ('size huge', 'follow maybe', 'break 42', 'hide now', 'jump', 'size', '隐藏'):
            out = parse(bad)
            self.assertIsInstance(out, str, bad)
            self.assertIn('/pet help', out)


if __name__ == '__main__':
    unittest.main()
