import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from interact import Touch, on_click, on_double, on_move, on_tick  # noqa: E402


def rub(s, t0, xs, dt=0.1, in_head=True):
    """在头上按 xs 依次移动；返回 (最后的状态, 所有反应)。"""
    out = []
    for i, x in enumerate(xs):
        s, r = on_move(s, t0 + i * dt, x, in_head)
        if r:
            out.append(r)
    return s, out


class PetTest(unittest.TestCase):
    def test_three_turns_on_the_head_is_a_pet(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0])
        self.assertEqual(rs, ['pet'])

    def test_moving_one_way_is_not_a_pet(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 40, 60, 80, 100])
        self.assertEqual(rs, [])

    def test_too_slow_does_not_count(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0], dt=1.0)
        self.assertEqual(rs, [])

    def test_not_on_the_head_does_not_count(self):
        _, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0], in_head=False)
        self.assertEqual(rs, [])

    def test_tiny_jitter_is_ignored(self):
        _, rs = rub(Touch(), 0.0, [0, 1, 0, 1, 0, 1, 0])
        self.assertEqual(rs, [])

    def test_cooldown_after_a_pet(self):
        s, rs = rub(Touch(), 0.0, [0, 20, 0, 20, 0])
        s, rs2 = rub(s, 1.0, [0, 20, 0, 20, 0])
        self.assertEqual(rs2, [])
        _, rs3 = rub(s, 6.0, [0, 20, 0, 20, 0])
        self.assertEqual(rs3, ['pet'])


class PokeTest(unittest.TestCase):
    def test_single_click_becomes_a_poke_after_the_wait(self):
        s = on_click(Touch(), 1.0)
        s, r = on_tick(s, 1.2)
        self.assertIsNone(r)
        s, r = on_tick(s, 1.31)
        self.assertEqual(r, 'poke')
        self.assertEqual(on_tick(s, 2.0)[1], None)  # 只算一次

    def test_double_click_is_not_a_poke(self):
        s = on_click(Touch(), 1.0)
        s = on_double(s)
        s = on_click(s, 1.15)   # 双击的第二下松开也会来一次，要忽略
        _, r = on_tick(s, 2.0)
        self.assertIsNone(r)

    def test_four_pokes_in_five_seconds_makes_her_angry(self):
        s, rs = Touch(), []
        for i in range(4):
            s = on_click(s, i * 1.0)
            s, r = on_tick(s, i * 1.0 + 0.5)
            rs.append(r)
        self.assertEqual(rs, ['poke', 'poke', 'poke', 'angry'])

    def test_after_angry_pokes_only_get_a_huff(self):
        s = Touch()
        for i in range(4):
            s, _ = on_tick(on_click(s, i * 1.0), i * 1.0 + 0.5)
        s, r = on_tick(on_click(s, 5.0), 5.5)
        self.assertEqual(r, 'huff')
        s, r = on_tick(on_click(s, 20.0), 20.5)
        self.assertEqual(r, 'poke')

    def test_slow_pokes_never_anger(self):
        s, rs = Touch(), []
        for i in range(6):
            s, r = on_tick(on_click(s, i * 3.0), i * 3.0 + 0.5)
            rs.append(r)
        self.assertNotIn('angry', rs)


if __name__ == '__main__':
    unittest.main()
