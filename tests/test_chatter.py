import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from chatter import (  # noqa: E402
    CHAT_EVERY, DEFAULT_LINES, Chatter, Context, load_lines, next_line, pick, start,
)


class FixedRng:
    def __init__(self, u=None):
        self.u = u

    def uniform(self, a, b):
        return a if self.u is None else self.u

    def choice(self, seq):
        return seq[0]


LINES = {
    'greet': {'morning': ['早'], 'afternoon': ['午'], 'evening': ['晚']},
    'meal': ['吃饭'], 'chat': ['一', '二'], 'work': ['在写 {project}'],
    'pet': ['嘿嘿'], 'poke': ['呀'], 'angry': ['哼！'], 'huff': ['哼'],
}


def ctx(now=0.0, date='2026-10-29', hour=10, quiet=False, project='p'):
    return Context(now=now, date=date, hour=hour, quiet=quiet, project=project)


class NextLineTest(unittest.TestCase):
    def test_first_line_of_the_day_is_a_greeting(self):
        c, line = next_line(start(0.0, FixedRng()), ctx(hour=9), LINES, FixedRng())
        self.assertEqual(line, '早')
        self.assertEqual(next_line(c, ctx(now=1.0, hour=9), LINES, FixedRng())[1], None)

    def test_greeting_depends_on_the_hour(self):
        self.assertEqual(next_line(start(0.0, FixedRng()), ctx(hour=14), LINES, FixedRng())[1], '午')
        self.assertEqual(next_line(start(0.0, FixedRng()), ctx(hour=21), LINES, FixedRng())[1], '晚')

    def test_quiet_means_no_line_at_all(self):
        self.assertEqual(next_line(start(0.0, FixedRng()), ctx(quiet=True), LINES, FixedRng())[1], None)

    def test_meal_reminder_once_per_meal(self):
        c, _ = next_line(start(0.0, FixedRng()), ctx(hour=11), LINES, FixedRng())   # 先问候
        c, line = next_line(c, ctx(now=10.0, hour=12), LINES, FixedRng())
        self.assertEqual(line, '吃饭')
        self.assertIsNone(next_line(c, ctx(now=20.0, hour=12), LINES, FixedRng())[1])

    def test_chat_after_the_interval_and_not_before(self):
        c, _ = next_line(start(0.0, FixedRng()), ctx(), LINES, FixedRng())
        self.assertIsNone(next_line(c, ctx(now=CHAT_EVERY[0] - 1), LINES, FixedRng())[1])
        _, line = next_line(c, ctx(now=CHAT_EVERY[0] + 1), LINES, FixedRng())
        self.assertIn(line, ['一', '二', '在写 p'])

    def test_project_fills_the_work_placeholder(self):
        lines = {**LINES, 'chat': []}
        c, _ = next_line(start(0.0, FixedRng()), ctx(), lines, FixedRng())
        _, line = next_line(c, ctx(now=CHAT_EVERY[1] + 1, project='claude-desk-pet'), lines, FixedRng())
        self.assertEqual(line, '在写 claude-desk-pet')

    def test_no_project_skips_work_lines(self):
        lines = {**LINES, 'chat': ['一']}
        c, _ = next_line(start(0.0, FixedRng()), ctx(), lines, FixedRng())
        _, line = next_line(c, ctx(now=CHAT_EVERY[1] + 1, project=''), lines, FixedRng())
        self.assertEqual(line, '一')


class PickTest(unittest.TestCase):
    def test_does_not_repeat_the_last_line(self):
        self.assertEqual(pick(['一', '二'], '一', FixedRng()), '二')

    def test_single_line_may_repeat(self):
        self.assertEqual(pick(['一'], '一', FixedRng()), '一')


class LoadLinesTest(unittest.TestCase):
    def test_missing_file_gives_defaults_and_an_error(self):
        lines, err = load_lines(os.path.join(tempfile.gettempdir(), 'no-such-lines.json'))
        self.assertEqual(lines, DEFAULT_LINES)
        self.assertIsNotNone(err)

    def test_file_overrides_defaults_key_by_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'lines.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'chat': ['自定义']}, f, ensure_ascii=False)
            lines, err = load_lines(p)
        self.assertIsNone(err)
        self.assertEqual(lines['chat'], ['自定义'])
        self.assertEqual(lines['poke'], DEFAULT_LINES['poke'])

    def test_bundled_file_loads_cleanly(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet', 'lines.json')
        lines, err = load_lines(path)
        self.assertIsNone(err)
        for key in ('greet', 'meal', 'chat', 'work', 'pet', 'poke', 'angry', 'huff'):
            self.assertTrue(lines[key])


if __name__ == '__main__':
    unittest.main()
