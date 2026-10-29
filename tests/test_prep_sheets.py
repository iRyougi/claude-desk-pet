import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from prep_sprites import SHEETS, available  # noqa: E402


def touch(folder, name):
    open(os.path.join(folder, name), 'wb').close()


class AvailableTest(unittest.TestCase):
    def test_only_sheets_with_a_source_are_returned(self):
        with tempfile.TemporaryDirectory() as d:
            touch(d, '瞌睡两帧.png')
            touch(d, '说明.txt')
            found = available(d)
            self.assertEqual([s.keyword for s, _ in found], ['瞌睡两帧'])
            self.assertEqual(found[0][1], os.path.join(d, '瞌睡两帧.png'))

    def test_two_sources_for_one_keyword_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            touch(d, '害羞.png')
            touch(d, '害羞-v2.png')
            with self.assertRaises(SystemExit):
                available(d)

    def test_empty_folder_gives_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(available(d), [])


class SheetsTest(unittest.TestCase):
    def test_new_sprites_are_registered(self):
        names = {n for s in SHEETS for n in s.names}
        for n in ('sit-down-1', 'sit-down-2', 'held', 'held-swing', 'fall', 'sleep-1', 'sleep-2', 'shy', 'poked'):
            self.assertIn(n, names)

    def test_keywords_do_not_overlap(self):
        keys = [s.keyword for s in SHEETS]
        for a in keys:
            for b in keys:
                if a != b:
                    self.assertNotIn(a, b)


if __name__ == '__main__':
    unittest.main()
