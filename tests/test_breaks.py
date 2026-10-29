import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from breaks import (  # noqa: E402
    ACK_LINES, BreakConfig, BreakState, acknowledge, is_night, pick_line, step,
)

TICK = 2.0
MIN = 60.0


def run(cfg: BreakConfig, minutes: float, idle: float = 0.0, state: BreakState | None = None,
        start: float = 1000.0):
    """从 start 开始每 2 秒走一步，返回 (最终状态, [(经过的分钟数, 事件)])。"""
    state = state or BreakState()
    events = []
    t = start
    end = start + minutes * MIN
    while t <= end:
        state, ev = step(state, t, idle, cfg)
        if ev is not None:
            events.append((round((t - start) / MIN, 1), ev))
        t += TICK
    return state, events


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = BreakConfig.from_settings({})
        self.assertEqual((cfg.work_min, cfg.escalate_min, cfg.repeat_min, cfg.away_min), (50, 10, 5, 5))
        self.assertTrue(cfg.enabled)

    def test_reads_settings(self):
        cfg = BreakConfig.from_settings({'breakWork': 25, 'breakEnabled': False})
        self.assertEqual(cfg.work_min, 25)
        self.assertFalse(cfg.enabled)

    def test_invalid_values_fall_back_to_defaults(self):
        cfg = BreakConfig.from_settings({'breakWork': -3, 'breakEscalate': 'abc', 'breakAway': None,
                                         'breakRepeat': True, 'breakEnabled': 'yes'})
        self.assertEqual((cfg.work_min, cfg.escalate_min, cfg.repeat_min, cfg.away_min), (50, 10, 5, 5))
        self.assertTrue(cfg.enabled)


class StepTest(unittest.TestCase):
    cfg = BreakConfig()

    def test_no_event_before_the_work_interval(self):
        _, events = run(self.cfg, 49)
        self.assertEqual(events, [])

    def test_gentle_reminder_after_continuous_work(self):
        _, events = run(self.cfg, 51)
        self.assertEqual([(m, e.level) for m, e in events], [(50.0, 1)])

    def test_escalates_if_ignored(self):
        _, events = run(self.cfg, 50 + 31)
        got = [(m, e.level, e.repeat) for m, e in events]
        self.assertEqual(got[:3], [(50.0, 1, False), (60.0, 2, False), (70.0, 3, False)])
        self.assertEqual(got[3:], [(75.0, 3, True), (80.0, 3, True)])  # 最高一级每 5 分钟再催一次

    def test_disabled_never_fires(self):
        cfg = BreakConfig(enabled=False)
        _, events = run(cfg, 200)
        self.assertEqual(events, [])

    def test_long_idle_resets_the_work_timer(self):
        state, _ = run(self.cfg, 40)
        state, _ = run(self.cfg, 6, idle=400.0, state=state, start=1000 + 41 * MIN)  # 离开 6 分钟
        self.assertEqual(state.active_s, 0)
        _, events = run(self.cfg, 49, state=state, start=1000 + 47 * MIN + TICK)
        self.assertEqual(events, [])  # 重新累计，49 分钟还没到

    def test_short_idle_neither_counts_nor_resets(self):
        state, _ = run(self.cfg, 10)
        before = state.active_s
        state, _ = run(self.cfg, 2, idle=200.0, state=state, start=1000 + 10 * MIN + TICK)
        self.assertAlmostEqual(state.active_s, before, delta=TICK)

    def test_leaving_during_a_reminder_clears_it_without_a_new_event(self):
        state, _ = run(self.cfg, 52)
        self.assertEqual(state.level, 1)
        state, events = run(self.cfg, 6, idle=400.0, state=state, start=1000 + 53 * MIN)
        self.assertEqual((state.level, events), (0, []))

    def test_acknowledge_restarts_everything(self):
        state, _ = run(self.cfg, 62)
        self.assertEqual(state.level, 2)
        state = acknowledge(state, 5000.0)
        self.assertEqual((state.level, state.active_s), (0, 0))
        _, events = run(self.cfg, 49, state=state, start=5000.0)
        self.assertEqual(events, [])

    def test_a_clock_jump_such_as_sleep_does_not_count_as_work(self):
        state, _ = run(self.cfg, 10)
        state, ev = step(state, 1000 + 10 * MIN + 3 * 3600, 0.0, self.cfg)  # 睡眠 3 小时后醒来
        self.assertIsNone(ev)
        self.assertLess(state.active_s, 11 * MIN)

    def test_state_is_immutable(self):
        state = BreakState()
        step(state, 100.0, 0.0, self.cfg)
        self.assertEqual(state, BreakState())

    def test_scaled_down_intervals_for_testing(self):
        cfg = BreakConfig(work_min=0.1, escalate_min=0.1, repeat_min=0.1)
        _, events = run(cfg, 0.5)
        self.assertEqual([e.level for _, e in events][:3], [1, 2, 3])


class LinesTest(unittest.TestCase):
    def test_night_hours(self):
        self.assertTrue(is_night(23))
        self.assertTrue(is_night(2))
        self.assertTrue(is_night(4))
        self.assertFalse(is_night(5))
        self.assertFalse(is_night(14))
        self.assertFalse(is_night(22))

    def test_every_level_has_day_and_night_lines(self):
        rng = random.Random(1)
        for level in (1, 2, 3):
            for night in (False, True):
                self.assertTrue(pick_line(level, night, rng))

    def test_night_lines_differ_from_day_lines(self):
        rng = random.Random(2)
        day = {pick_line(1, False, rng) for _ in range(30)}
        night = {pick_line(1, True, rng) for _ in range(30)}
        self.assertFalse(day & night)

    def test_does_not_repeat_the_previous_line(self):
        rng = random.Random(3)
        last = pick_line(3, False, rng)
        for _ in range(50):
            nxt = pick_line(3, False, rng, last=last)
            self.assertNotEqual(nxt, last)
            last = nxt

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError):
            pick_line(9, False, random.Random(0))

    def test_ack_lines_exist(self):
        self.assertTrue(ACK_LINES)


if __name__ == '__main__':
    unittest.main()
