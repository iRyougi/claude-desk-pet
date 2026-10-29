import os
import random
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from motion import (  # noqa: E402
    Motion, Rect, Surface, WinInfo, choose_pose, choose_surface, spawn, tick, walk_to,
)

S = Surface(key=1, left=100.0, right=900.0, y=300.0, kind='window')
WORK = Rect(0, 0, 1920, 1040)


def settle(m, surface, now, dt=0.03, **kw):
    return tick(m, surface, now, dt, can_wander=False, **kw)


class ChooseSurfaceTest(unittest.TestCase):
    def win(self, rect, maximized=False):
        return WinInfo(hwnd=77, rect=rect, work=WORK, maximized=maximized)

    def test_window_with_room_above_becomes_the_surface(self):
        s = choose_surface(self.win(Rect(200, 400, 1000, 800)), WORK, need_above=250, margin=24)
        self.assertEqual((s.kind, s.key, s.left, s.right, s.y), ('window', 77, 224, 976, 400))

    def test_maximized_window_falls_back_to_the_taskbar(self):
        s = choose_surface(self.win(Rect(0, 0, 1920, 1040), maximized=True), WORK, need_above=250)
        self.assertEqual((s.kind, s.y), ('ground', 1040))

    def test_window_too_close_to_the_screen_top_falls_back(self):
        s = choose_surface(self.win(Rect(200, 100, 1000, 800)), WORK, need_above=250)
        self.assertEqual(s.kind, 'ground')

    def test_without_headroom_she_stays_within_that_windows_width(self):
        s = choose_surface(self.win(Rect(200, 100, 1000, 800)), WORK, need_above=250, margin=24)
        self.assertEqual((s.kind, s.y, s.left, s.right), ('ground', 1040, 224, 976))

    def test_maximized_window_keeps_her_inside_its_width_too(self):
        s = choose_surface(self.win(Rect(0, 0, 1920, 1040), maximized=True), WORK, need_above=250, margin=24)
        self.assertEqual((s.left, s.right), (24, 1896))

    def test_ground_of_different_windows_is_a_different_surface(self):
        a = choose_surface(WinInfo(1, Rect(200, 100, 1000, 800), WORK), WORK, need_above=250)
        b = choose_surface(WinInfo(2, Rect(200, 100, 1000, 800), WORK), WORK, need_above=250)
        self.assertNotEqual(a.key, b.key)  # 切到另一个窗口，她要跳过去

    def test_narrow_window_falls_back_to_the_whole_screen_width(self):
        s = choose_surface(self.win(Rect(200, 400, 400, 800)), WORK, need_above=250, min_width=240)
        self.assertEqual((s.kind, s.left, s.right), ('ground', 0, 1920))

    def test_narrow_window_falls_back(self):
        s = choose_surface(self.win(Rect(200, 400, 400, 800)), WORK, need_above=250, min_width=240)
        self.assertEqual(s.kind, 'ground')

    def test_no_window_uses_the_fallback_work_area(self):
        s = choose_surface(None, WORK, need_above=250)
        self.assertEqual((s.kind, s.y), ('ground', 1040))

    def test_ground_key_differs_per_monitor(self):
        a = choose_surface(None, Rect(0, 0, 1920, 1040), need_above=250)
        b = choose_surface(None, Rect(1920, 0, 3840, 1040), need_above=250)
        self.assertNotEqual(a.key, b.key)


class PerchTest(unittest.TestCase):
    def test_spawn_sits_at_the_fraction_of_the_surface(self):
        m = spawn(S, 0.5, now=0.0, rng=random.Random(1))
        self.assertEqual((m.mode, m.x, m.y), ('perch', 500.0, 300.0))

    def test_follows_a_window_that_moves(self):
        m = spawn(S, 0.5, 0.0, rng=random.Random(1))
        moved = Surface(key=1, left=300.0, right=1100.0, y=500.0, kind='window')
        m = settle(m, moved, 1.0)
        self.assertEqual((m.mode, m.x, m.y), ('perch', 700.0, 500.0))

    def test_follows_a_window_that_resizes(self):
        m = spawn(S, 0.5, 0.0, rng=random.Random(1))
        wider = Surface(key=1, left=100.0, right=1700.0, y=300.0, kind='window')
        self.assertEqual(settle(m, wider, 1.0).x, 900.0)


class JumpTest(unittest.TestCase):
    other = Surface(key=2, left=1000.0, right=1800.0, y=600.0, kind='window')

    def start(self):
        m = spawn(S, 0.5, 0.0, rng=random.Random(1))
        return m, settle(m, self.other, 5.0)

    def test_a_new_surface_starts_a_jump_from_where_she_is(self):
        before, m = self.start()
        self.assertEqual(m.mode, 'jump')
        self.assertEqual((m.x, m.y), (before.x, before.y))
        self.assertTrue(0.45 <= m.jump.dur <= 1.0)

    def test_the_jump_lands_on_the_new_surface(self):
        _, m = self.start()
        landing = 5.0 + m.jump.dur + 0.01
        m = settle(m, self.other, landing)
        self.assertEqual((m.mode, m.x, m.y), ('perch', 1400.0, 600.0))
        self.assertEqual(m.landed_at, landing)

    def test_the_path_is_an_arc_above_the_straight_line(self):
        _, m = self.start()
        mid = settle(m, self.other, 5.0 + m.jump.dur / 2)
        self.assertEqual(mid.mode, 'jump')
        self.assertLess(mid.y, (300.0 + 600.0) / 2 - 10)  # y 向下为正，更小就是更高

    def test_changing_target_mid_jump_restarts_from_the_current_position(self):
        _, m = self.start()
        mid = settle(m, self.other, 5.3)
        third = Surface(key=3, left=0.0, right=500.0, y=200.0, kind='window')
        again = settle(mid, third, 5.4)
        self.assertEqual(again.mode, 'jump')
        self.assertEqual((again.jump.x0, again.jump.y0), (mid.x, mid.y))

    def test_longer_distance_takes_longer(self):
        near = Surface(key=2, left=150.0, right=950.0, y=320.0, kind='window')
        far = Surface(key=3, left=3000.0, right=3800.0, y=900.0, kind='window')
        m = spawn(S, 0.5, 0.0, rng=random.Random(1))
        self.assertLess(settle(m, near, 1.0).jump.dur, settle(m, far, 1.0).jump.dur)


class WalkTest(unittest.TestCase):
    def test_walks_toward_the_target_at_the_given_speed(self):
        m = walk_to(spawn(S, 0.2, 0.0, rng=random.Random(1)), 0.8, 1.0)
        self.assertEqual(m.mode, 'walk')
        m = settle(m, S, 1.5, dt=0.5, speed=100.0)
        self.assertAlmostEqual(m.x, 260.0 + 50.0)
        self.assertEqual(m.face, 1)

    def test_arrives_without_overshooting(self):
        m = walk_to(spawn(S, 0.2, 0.0, rng=random.Random(1)), 0.8, 1.0)
        m = settle(m, S, 9.0, dt=5.0, speed=500.0)
        self.assertEqual((m.mode, m.x, m.frac), ('perch', 740.0, 0.8))

    def test_walking_left_faces_left(self):
        m = walk_to(spawn(S, 0.8, 0.0, rng=random.Random(1)), 0.2, 1.0)
        self.assertEqual(m.face, -1)
        self.assertLess(settle(m, S, 1.1, dt=0.1, speed=100.0).x, 740.0)

    def test_walking_keeps_following_a_moving_window(self):
        m = walk_to(spawn(S, 0.2, 0.0, rng=random.Random(1)), 0.8, 1.0)
        moved = Surface(key=1, left=100.0, right=900.0, y=450.0, kind='window')
        self.assertEqual(settle(m, moved, 1.1, dt=0.1, speed=100.0).y, 450.0)

    def test_walk_to_a_jumping_motion_is_ignored(self):
        other = Surface(key=2, left=1000.0, right=1800.0, y=600.0, kind='window')
        jumping = settle(spawn(S, 0.5, 0.0, rng=random.Random(1)), other, 1.0)
        self.assertEqual(walk_to(jumping, 0.1, 1.1).mode, 'jump')


class WanderTest(unittest.TestCase):
    def test_does_not_wander_when_not_allowed(self):
        m = spawn(S, 0.5, 0.0, rng=random.Random(1))
        self.assertEqual(tick(m, S, 999.0, 0.03, can_wander=False).mode, 'perch')

    def test_wanders_after_the_timer_when_allowed(self):
        rng = random.Random(1)
        m = spawn(S, 0.5, 0.0, rng=rng)
        m = tick(m, S, 999.0, 0.03, can_wander=True, rng=rng)
        self.assertEqual(m.mode, 'walk')
        self.assertTrue(0.1 <= m.target_frac <= 0.9)
        self.assertGreaterEqual(abs(m.target_frac - 0.5), 0.15)

    def test_does_not_wander_before_the_timer(self):
        rng = random.Random(1)
        m = spawn(S, 0.5, 0.0, rng=rng)
        self.assertEqual(tick(m, S, 1.0, 0.03, can_wander=True, rng=rng).mode, 'perch')


class ChoosePoseTest(unittest.TestCase):
    def perched(self, frac=0.8):
        return spawn(S, frac, 0.0, rng=random.Random(1))

    def pose(self, m, state='waiting', age=100.0, now=50.0, **kw):
        return choose_pose(m, now, state, age, **kw)

    def test_jump_then_land(self):
        other = Surface(key=2, left=1000.0, right=1800.0, y=600.0, kind='window')
        m = settle(self.perched(), other, 5.0)
        self.assertEqual(self.pose(m, now=5.0).file, 'jump')
        m = settle(m, other, 5.0 + m.jump.dur + 0.01)
        self.assertEqual(self.pose(m, now=m.landed_at + 0.1).file, 'land')
        self.assertTrue(self.pose(m, now=m.landed_at + 5).file.startswith('sit'))

    def test_walking_cycles_through_six_frames_and_flips_when_going_left(self):
        m = walk_to(self.perched(0.8), 0.2, 1.0)
        files = {self.pose(m, now=t / 20).file for t in range(40)}
        self.assertEqual(files, {f'walk-{i}' for i in range(1, 7)})
        self.assertTrue(self.pose(m).flip)
        m = walk_to(self.perched(0.2), 0.8, 1.0)
        self.assertFalse(self.pose(m).flip)

    def walking(self, x, face):
        m = walk_to(self.perched(0.8 if face < 0 else 0.2), 0.2 if face < 0 else 0.8, 1.0)
        return replace(m, x=x)

    def test_gait_follows_distance_not_time(self):
        m = self.walking(0.0, 1)
        a = self.pose(m, now=10.0, px_per_frame=50.0).file
        b = self.pose(m, now=99.0, px_per_frame=50.0).file
        self.assertEqual(a, b)  # 站着不动的那一刻，不管过了多久都是同一帧——脚不会在原地滑

    def test_one_frame_per_stride_sixth_walking_right(self):
        files = [self.pose(self.walking(x, 1), px_per_frame=50.0).file for x in range(0, 350, 50)]
        self.assertEqual(files, ['walk-1', 'walk-2', 'walk-3', 'walk-4', 'walk-5', 'walk-6', 'walk-1'])

    def test_gait_runs_forward_when_walking_left(self):
        files = [self.pose(self.walking(x, -1), px_per_frame=50.0).file for x in (300, 250, 200, 150, 100, 50)]
        self.assertEqual(files, [f'walk-{i}' for i in range(1, 7)])

    def test_working_states_sit_and_watch(self):
        for state in ('thinking', 'reading'):
            p = self.pose(self.perched(), state=state)
            self.assertEqual((p.file, p.anchor), ('sit-watch', 0.70))
        self.assertEqual(self.pose(self.perched(), state='tool').file, 'typing')

    def test_sit_watch_looks_toward_the_middle_of_the_window(self):
        self.assertFalse(self.pose(self.perched(0.8), state='thinking').flip)
        self.assertTrue(self.pose(self.perched(0.2), state='thinking').flip)

    def test_waiting_swings_her_legs_after_the_knock(self):
        self.assertEqual(self.pose(self.perched(), state='waiting', age=2.0).file, 'knock')
        files = {self.pose(self.perched(), state='waiting', age=60.0, now=t / 2).file for t in range(20)}
        self.assertEqual(files, {'sit-swing-1', 'sit-swing-2'})

    def test_event_states_stand_up_on_the_edge(self):
        for state, file in (('celebrate', 'confetti'), ('error', 'panic'), ('aborted', 'guilty'),
                            ('stone', 'stone')):
            p = self.pose(self.perched(), state=state)
            self.assertEqual((p.file, p.anchor), (file, 1.0))

    def test_idle_swings_her_legs(self):
        self.assertTrue(self.pose(self.perched(), state='idle').file.startswith('sit-swing'))

    def test_reminder_stands_with_the_level_sprite(self):
        self.assertEqual(self.pose(self.perched(), remind=3).file, 'remind-3')
        self.assertEqual(self.pose(self.perched(), remind=1, state='tool').file, 'remind-1')

    def test_speech_sprite_overrides_when_perched(self):
        self.assertEqual(self.pose(self.perched(), speech='idle').file, 'smile')

    def test_fixed_mode_uses_the_original_state_sprites_bottom_aligned(self):
        for state, file in (('thinking', 'smile-closed'), ('tool', 'typing'), ('reading', 'notes'),
                            ('waiting', 'knock'), ('idle', 'smile')):
            p = choose_pose(None, 0.0, state, 0.0, roam=False)
            self.assertEqual((p.file, p.anchor, p.flip), (file, 1.0, False))
        self.assertEqual(choose_pose(None, 0.0, 'tool', 0.0, remind=2, roam=False).file, 'remind-2')

    def test_unknown_state_does_not_crash(self):
        self.assertTrue(self.pose(self.perched(), state='???').file)
        self.assertTrue(choose_pose(None, 0.0, '???', 0.0, roam=False).file)


class MotionIsImmutableTest(unittest.TestCase):
    def test_tick_does_not_modify_its_input(self):
        m = spawn(S, 0.5, 0.0, rng=random.Random(1))
        snapshot = (m.mode, m.x, m.y, m.frac)
        tick(m, Surface(key=9, left=0.0, right=100.0, y=0.0, kind='window'), 1.0, 0.03)
        self.assertEqual((m.mode, m.x, m.y, m.frac), snapshot)
        self.assertIsInstance(m, Motion)


if __name__ == '__main__':
    unittest.main()
