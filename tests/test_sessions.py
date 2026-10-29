import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from sessions import ACTIVE_S, Session, Summary, summarize  # noqa: E402

NOW = 10_000.0


def s(age, state='tool', project='a', text=''):
    return Session(mtime=NOW - age, state=state, text=text, project=project)


class SummarizeTest(unittest.TestCase):
    def test_nothing(self):
        self.assertEqual(summarize([], NOW), Summary(None, None))

    def test_one_session_has_no_second_line(self):
        a = s(5)
        self.assertEqual(summarize([a], NOW), Summary(a, None))

    def test_latest_wins_and_others_are_summarised(self):
        a, b = s(5, project='a'), s(60, state='tool', project='b')
        self.assertEqual(summarize([b, a], NOW), Summary(a, 'a · 另有 1 个在忙'))

    def test_finished_sessions_count_as_waiting_not_busy(self):
        a = s(5, project='a')
        self.assertEqual(summarize([a, s(60, state='celebrate', project='b')], NOW).sub, 'a · b 在等你')
        self.assertEqual(summarize([a, s(60, state='aborted', project='b')], NOW).sub, 'a · b 在等你')

    def test_waiting_beats_busy(self):
        a, b, c = s(5, project='a'), s(60, project='b'), s(90, state='waiting', project='c')
        self.assertEqual(summarize([a, b, c], NOW).sub, 'a · c 在等你')

    def test_several_waiting(self):
        a, b, c = s(5, project='a'), s(60, state='waiting', project='b'), s(90, state='waiting', project='c')
        self.assertEqual(summarize([a, b, c], NOW).sub, 'a · 2 个会话在等你')

    def test_error_beats_waiting(self):
        a, b, c = s(5), s(60, state='waiting', project='b'), s(90, state='error', project='c')
        self.assertEqual(summarize([a, b, c], NOW).sub, 'a · c 出错了')

    def test_stale_sessions_are_ignored(self):
        a, old = s(5), s(ACTIVE_S + 1, state='waiting', project='old')
        self.assertEqual(summarize([a, old], NOW).sub, None)

    def test_unnamed_project(self):
        a, b = s(5, project=''), s(60, state='waiting', project='')
        self.assertEqual(summarize([a, b], NOW).sub, '当前会话 · 另一个会话 在等你')


if __name__ == '__main__':
    unittest.main()
