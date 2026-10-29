import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from files import write_json_atomic  # noqa: E402


class WriteJsonAtomicTest(unittest.TestCase):
    def test_writes_utf8_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'settings.json')
            write_json_atomic(p, {'size': '中'})
            with open(p, encoding='utf-8') as f:
                self.assertEqual(json.load(f), {'size': '中'})
            self.assertFalse(os.path.exists(p + '.tmp'))

    def test_a_failed_write_leaves_the_old_file_alone(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'settings.json')
            write_json_atomic(p, {'size': '大'})
            with self.assertRaises(TypeError):
                write_json_atomic(p, {'bad': {1, 2}})   # set 不能写成 JSON
            with open(p, encoding='utf-8') as f:
                self.assertEqual(json.load(f), {'size': '大'})
            self.assertFalse(os.path.exists(p + '.tmp'))

    def test_creates_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'sub', 'settings.json')
            write_json_atomic(p, {})
            self.assertTrue(os.path.exists(p))


if __name__ == '__main__':
    unittest.main()
