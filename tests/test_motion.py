import os
import random
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pet'))

from motion import (  # noqa: E402
    Motion, Rect, Surface, WinInfo, build_surfaces, choose_pose, choose_surface, drop, hold, hop_to,
    release, spawn, tick, walk_to,
)

S = Surface(key=1, left=100.0, right=900.0, y=300.0, kind='window')
G = Surface(key=('ground', 0, 0, None), left=0.0, right=1920.0, y=1040.0, kind='ground')
WORK = Rect(0, 0, 1920, 1040)
DT = 1 / 30


def step(m, surfaces, now, dt=DT, **kw):
    kw.setdefault('can_wander', False)
    return tick(m, surfaces, now, dt, **kw)


def rng():
    return random.Random(1)


class ChooseSurfaceTest(unittest.TestCase):
    def win(self, rect, maximized=False, hwnd=77):
        return WinInfo(hwnd=hwnd, rect=rect, work=WORK, maximized=maximized)

    def test_window_with_room_above_becomes_the_surface(self):
        s = choose_surface(self.win(Rect(200, 400, 1000, 800)), WORK, need_above=250, margin=24)
        self.assertEqual((s.kind, s.key, s.left, s.right, s.y), ('window', 77, 224, 976, 400))

    def test_without_headroom_she_stays_within_that_windows_width(self):
        s = choose_surface(self.win(Rect(200, 100, 1000, 800)), WORK, need_above=250, margin=24)
        self.assertEqual((s.kind, s.y, s.left, s.right), ('ground', 1040, 224, 976))

    def test_maximized_window_keeps_her_inside_its_width_too(self):
        s = choose_surface(self.win(Rect(0, 0, 1920, 1040), maximized=True), WORK, need_above=250, margin=24)
        self.assertEqual((s.kind, s.y, s.left, s.right), ('ground', 1040, 24, 1896))

    def test_ground_of_different_windows_is_a_different_surface(self):
        a = choose_surface(self.win(Rect(200, 100, 1000, 800), hwnd=1), WORK, need_above=250)
        b = choose_surface(self.win(Rect(200, 100, 1000, 800), hwnd=2), WORK, need_above=250)
        self.assertNotEqual(a.key, b.key)

    def test_narrow_window_falls_back_to_the_whole_screen_width(self):
        s = choose_surface(self.win(Rect(200, 400, 400, 800)), WORK, need_above=250, min_width=240)
        self.assertEqual((s.kind, s.left, s.right), ('ground', 0, 1920))

    def test_no_window_uses_the_fallback_work_area(self):
        s = choose_surface(None, WORK, need_above=250)
        self.assertEqual((s.kind, s.y), ('ground', 1040))

    def test_ground_key_differs_per_monitor(self):
        a = choose_surface(None, Rect(0, 0, 1920, 1040), need_above=250)
        b = choose_surface(None, Rect(1920, 0, 3840, 1040), need_above=250)
        self.assertNotEqual(a.key, b.key)


class BuildSurfacesTest(unittest.TestCase):
    def test_one_ground_per_monitor_and_one_top_per_normal_window(self):
        wins = [WinInfo(10, Rect(200, 400, 1000, 800), WORK), WinInfo(11, Rect(1200, 300, 1800, 700), WORK)]
        out = build_surfaces(wins, [WORK, Rect(1920, 0, 3840, 1040)])
        self.assertEqual(sorted(s.kind for s in out), ['ground', 'ground', 'window', 'window'])
        top = next(s for s in out if s.key == 10)
        self.assertEqual((top.left, top.right, top.y), (224.0, 976.0, 400.0))

    def test_maximized_and_narrow_windows_are_not_floors(self):
        wins = [WinInfo(10, Rect(0, 0, 1920, 1040), WORK, maximized=True), WinInfo(11, Rect(100, 300, 300, 700), WORK)]
        self.assertEqual([s.kind for s in build_surfaces(wins, [WORK])], ['ground'])


class PerchTest(unittest.TestCase):
    def test_spawn_sits_at_the_fraction_of_the_surface(self):
        m = spawn(S, 0.5, now=0.0, rng=rng())
        self.assertEqual((m.mode, m.x, m.y, m.support), ('perch', 500.0, 300.0, 1))

    def test_follows_a_window_that_moves(self):
        m = spawn(S, 0.5, 0.0, rng=rng())
        moved = Surface(key=1, left=300.0, right=1100.0, y=500.0, kind='window')
        m = step(m, [moved, G], 1.0)
        self.assertEqual((m.mode, m.x, m.y), ('perch', 700.0, 500.0))

    def test_follows_a_window_that_resizes(self):
        m = spawn(S, 0.5, 0.0, rng=rng())
        wider = Surface(key=1, left=100.0, right=1700.0, y=300.0, kind='window')
        self.assertEqual(step(m, [wider, G], 1.0).x, 900.0)

    def test_falls_when_the_window_under_her_disappears(self):
        m = step(spawn(S, 0.5, 0.0, rng=rng()), [G], 1.0)
        self.assertEqual(m.mode, 'fall')
        self.assertIsNone(m.support)


class FallTest(unittest.TestCase):
    def fall_until_landed(self, m, surfaces, limit=10.0):
        t = 0.0
        while m.mode == 'fall' and t < limit:
            t += DT
            m = step(m, surfaces, t)
        return m

    def test_lands_on_the_window_below_her(self):
        m = self.fall_until_landed(drop(500.0, 100.0, 0.0, rng=rng()), [S, G])
        self.assertEqual((m.mode, m.y, m.support), ('perch', 300.0, 1))
        self.assertAlmostEqual(m.frac, (500 - 100) / 800, places=2)

    def test_misses_the_window_when_x_is_outside_it_and_lands_on_the_ground(self):
        m = self.fall_until_landed(drop(1500.0, 100.0, 0.0, rng=rng()), [S, G])
        self.assertEqual((m.y, m.support), (1040.0, G.key))

    def test_ignores_surfaces_that_are_above_her(self):
        m = self.fall_until_landed(drop(500.0, 500.0, 0.0, rng=rng()), [S, G])
        self.assertEqual(m.y, 1040.0)

    def test_picks_the_highest_surface_below_her(self):
        lower = Surface(key=2, left=100.0, right=900.0, y=600.0, kind='window')
        m = self.fall_until_landed(drop(500.0, 100.0, 0.0, rng=rng()), [lower, S, G])
        self.assertEqual(m.support, 1)

    def test_accelerates(self):
        m = drop(500.0, 0.0, 0.0, rng=rng())
        a = step(m, [G], DT)
        b = step(a, [G], 2 * DT)
        c = step(b, [G], 3 * DT)
        self.assertGreater(c.y - b.y, b.y - a.y)

    def test_a_long_frame_does_not_tunnel_through_a_surface(self):
        m = step(drop(500.0, 100.0, 0.0, rng=rng()), [S, G], 1.0, dt=0.5)
        self.assertEqual((m.mode, m.y, m.support), ('perch', 300.0, 1))

    def test_keeps_its_horizontal_velocity_while_falling(self):
        m = drop(500.0, 0.0, 0.0, vx=300.0, rng=rng())
        self.assertGreater(step(m, [G], DT).x, 500.0)

    def test_landing_sets_the_landing_time(self):
        m = self.fall_until_landed(drop(500.0, 100.0, 0.0, rng=rng()), [S, G])
        self.assertGreater(m.landed_at, 0.0)

    def test_below_every_surface_she_lands_on_the_lowest_one(self):
        m = step(drop(5000.0, 2000.0, 0.0, rng=rng()), [S, G], 1.0)
        self.assertEqual((m.mode, m.y), ('perch', 1040.0))
        self.assertLessEqual(m.x, G.right)


class HoldTest(unittest.TestCase):
    def test_a_held_pet_does_not_move_by_itself(self):
        m = hold(spawn(S, 0.5, 0.0, rng=rng()), 700.0, 400.0)
        self.assertEqual((m.mode, m.x, m.y), ('held', 700.0, 400.0))
        again = step(m, [S, G], 5.0)
        self.assertEqual((again.mode, again.x, again.y), ('held', 700.0, 400.0))

    def test_release_starts_a_fall_with_the_throw_velocity(self):
        m = release(hold(spawn(S, 0.5, 0.0, rng=rng()), 700.0, 400.0), vx=250.0, vy=-100.0)
        self.assertEqual((m.mode, m.vx, m.vy), ('fall', 250.0, -100.0))

    def test_release_of_something_not_held_changes_nothing(self):
        m = spawn(S, 0.5, 0.0, rng=rng())
        self.assertIs(release(m), m)

    def test_dropped_on_a_window_she_stays_there_and_does_not_go_back(self):
        m = release(hold(spawn(G, 0.5, 0.0, rng=rng()), 500.0, 100.0))
        t = 0.0
        while m.mode == 'fall':
            t += DT
            m = step(m, [S, G], t)
        later = step(m, [S, G], t + 60.0)
        self.assertEqual((later.mode, later.support), ('perch', 1))


class HopTest(unittest.TestCase):
    other = Surface(key=2, left=1000.0, right=1800.0, y=600.0, kind='window')

    def start(self):
        m = spawn(S, 0.5, 0.0, rng=rng())
        return m, hop_to(m, self.other, 5.0)

    def test_hopping_starts_from_where_she_is(self):
        before, m = self.start()
        self.assertEqual(m.mode, 'hop')
        self.assertEqual((m.x, m.y), (before.x, before.y))
        self.assertTrue(0.45 <= m.jump.dur <= 1.0)

    def test_the_hop_lands_on_the_target(self):
        _, m = self.start()
        landing = 5.0 + m.jump.dur + 0.01
        m = step(m, [S, self.other, G], landing)
        self.assertEqual((m.mode, m.x, m.y, m.support), ('perch', 1400.0, 600.0, 2))
        self.assertEqual(m.landed_at, landing)

    def test_the_path_is_an_arc_above_the_straight_line(self):
        _, m = self.start()
        mid = step(m, [S, self.other, G], 5.0 + m.jump.dur / 2)
        self.assertEqual(mid.mode, 'hop')
        self.assertLess(mid.y, (300.0 + 600.0) / 2 - 10)

    def test_the_target_can_move_during_the_hop(self):
        _, m = self.start()
        moved = Surface(key=2, left=1000.0, right=1800.0, y=700.0, kind='window')
        m = step(m, [S, moved, G], 5.0 + m.jump.dur + 0.01)
        self.assertEqual(m.y, 700.0)

    def test_she_falls_if_the_target_vanishes_mid_hop(self):
        _, m = self.start()
        self.assertEqual(step(m, [S, G], 5.3).mode, 'fall')

    def test_hopping_again_restarts_from_the_current_position(self):
        _, m = self.start()
        mid = step(m, [S, self.other, G], 5.3)
        third = Surface(key=3, left=0.0, right=500.0, y=200.0, kind='window')
        again = hop_to(mid, third, 5.4)
        self.assertEqual((again.jump.x0, again.jump.y0), (mid.x, mid.y))

    def test_longer_distance_takes_longer(self):
        near = Surface(key=2, left=150.0, right=950.0, y=320.0, kind='window')
        far = Surface(key=3, left=3000.0, right=3800.0, y=900.0, kind='window')
        m = spawn(S, 0.5, 0.0, rng=rng())
        self.assertLess(hop_to(m, near, 1.0).jump.dur, hop_to(m, far, 1.0).jump.dur)


class WalkTest(unittest.TestCase):
    def test_walks_toward_the_target_at_the_given_speed(self):
        m = walk_to(spawn(S, 0.2, 0.0, rng=rng()), 0.8, 1.0)
        self.assertEqual(m.mode, 'walk')
        m = step(m, [S, G], 1.5, dt=0.5, speed=100.0)
        self.assertAlmostEqual(m.x, 260.0 + 50.0)
        self.assertEqual(m.face, 1)

    def test_arrives_without_overshooting(self):
        m = walk_to(spawn(S, 0.2, 0.0, rng=rng()), 0.8, 1.0)
        m = step(m, [S, G], 9.0, dt=5.0, speed=500.0)
        self.assertEqual((m.mode, m.x, m.frac), ('perch', 740.0, 0.8))

    def test_walking_left_faces_left(self):
        m = walk_to(spawn(S, 0.8, 0.0, rng=rng()), 0.2, 1.0)
        self.assertEqual(m.face, -1)
        self.assertLess(step(m, [S, G], 1.1, dt=0.1, speed=100.0).x, 740.0)

    def test_walking_keeps_following_a_moving_window(self):
        m = walk_to(spawn(S, 0.2, 0.0, rng=rng()), 0.8, 1.0)
        moved = Surface(key=1, left=100.0, right=900.0, y=450.0, kind='window')
        self.assertEqual(step(m, [moved, G], 1.1, dt=0.1, speed=100.0).y, 450.0)

    def test_walk_orders_are_ignored_while_in_the_air_or_held(self):
        for m in (hop_to(spawn(S, 0.5, 0.0, rng=rng()), G, 1.0), drop(500.0, 100.0, 0.0),
                  hold(spawn(S, 0.5, 0.0, rng=rng()), 5.0, 5.0)):
            self.assertEqual(walk_to(m, 0.1, 2.0).mode, m.mode)


class WanderTest(unittest.TestCase):
    def test_does_not_wander_when_not_allowed(self):
        m = spawn(S, 0.5, 0.0, rng=rng())
        self.assertEqual(tick(m, [S, G], 999.0, DT, can_wander=False).mode, 'perch')

    def test_wanders_after_the_timer_when_allowed(self):
        r = rng()
        m = spawn(S, 0.5, 0.0, rng=r)
        m = tick(m, [S, G], 999.0, DT, can_wander=True, rng=r)
        self.assertEqual(m.mode, 'walk')
        self.assertTrue(0.1 <= m.target_frac <= 0.9)
        self.assertGreaterEqual(abs(m.target_frac - 0.5), 0.15)

    def test_does_not_wander_before_the_timer(self):
        r = rng()
        m = spawn(S, 0.5, 0.0, rng=r)
        self.assertEqual(tick(m, [S, G], 1.0, DT, can_wander=True, rng=r).mode, 'perch')


class SwingTest(unittest.TestCase):
    """坐着大部分时间是静止的；晃腿是偶尔抽中的、有时长的小行为（Shimeji 的做法）。"""

    def fresh(self):
        r = rng()
        m = spawn(S, 0.5, 0.0, rng=r)
        return replace(m, next_wander=1e9), r  # 不让她去溜达，只看晃腿

    def test_no_swing_before_the_timer(self):
        m, r = self.fresh()
        out = tick(m, [S, G], m.next_swing - 1.0, DT, can_wander=True, rng=r)
        self.assertLessEqual(out.swing_until, m.next_swing - 1.0)

    def test_a_swing_starts_after_the_timer_when_idle(self):
        m, r = self.fresh()
        now = m.next_swing + 0.1
        out = tick(m, [S, G], now, DT, can_wander=True, rng=r)
        self.assertTrue(3.0 <= out.swing_until - now <= 6.0)
        self.assertGreater(out.next_swing, out.swing_until)  # 做完之后要隔一阵才会有下一次

    def test_the_gap_between_swings_is_long(self):
        m, r = self.fresh()
        out = tick(m, [S, G], m.next_swing + 0.1, DT, can_wander=True, rng=r)
        self.assertGreaterEqual(out.next_swing - out.swing_until, 20.0)

    def test_no_swing_when_she_is_busy(self):
        m, r = self.fresh()
        now = m.next_swing + 100.0
        out = tick(m, [S, G], now, DT, can_wander=False, rng=r)
        self.assertLessEqual(out.swing_until, now)

    def test_a_swing_in_progress_is_not_restarted(self):
        m, r = self.fresh()
        now = m.next_swing + 0.1
        once = tick(m, [S, G], now, DT, can_wander=True, rng=r)
        twice = tick(once, [S, G], now + 1.0, DT, can_wander=True, rng=r)
        self.assertEqual(twice.swing_until, once.swing_until)


class ChoosePoseTest(unittest.TestCase):
    def perched(self, frac=0.8):
        return spawn(S, frac, 0.0, rng=rng())

    def pose(self, m, state='waiting', age=100.0, now=50.0, **kw):
        return choose_pose(m, now, state, age, **kw)

    def test_in_the_air_she_uses_the_jump_pose(self):
        self.assertEqual(self.pose(drop(500.0, 0.0, 0.0)).file, 'jump')
        self.assertEqual(self.pose(hold(self.perched(), 5.0, 5.0)).file, 'jump')
        self.assertEqual(self.pose(hop_to(self.perched(), G, 1.0)).file, 'jump')

    def test_after_landing_she_shows_the_land_pose_briefly(self):
        m = step(drop(500.0, 100.0, 0.0, rng=rng()), [S, G], 1.0, dt=0.5)
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
        self.assertEqual(self.pose(m, now=10.0, px_per_frame=50.0).file, self.pose(m, now=99.0, px_per_frame=50.0).file)

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

    def test_waiting_knocks_first_then_sits_still(self):
        self.assertEqual(self.pose(self.perched(), state='waiting', age=2.0).file, 'knock')
        files = {self.pose(self.perched(), state='waiting', age=60.0, now=t / 2).file for t in range(60)}
        self.assertEqual(files, {'sit-swing-1'})  # 没抽中晃腿的时候，一直是同一帧，不来回换

    def test_while_swinging_the_two_frames_alternate_slowly(self):
        m = replace(self.perched(), swing_until=100.0)
        files = [self.pose(m, state='idle', now=t / 10).file for t in range(0, 40)]
        self.assertEqual(set(files), {'sit-swing-1', 'sit-swing-2'})
        changes = sum(1 for a, b in zip(files, files[1:]) if a != b)
        self.assertLessEqual(changes, 5)  # 4 秒里最多换 5 次，不是一直抖

    def test_swing_ends_when_the_timer_runs_out(self):
        m = replace(self.perched(), swing_until=10.0)
        self.assertEqual(self.pose(m, state='idle', now=20.0).file, 'sit-swing-1')

    def test_event_states_stand_up_on_the_edge(self):
        for state, file in (('celebrate', 'confetti'), ('error', 'panic'), ('aborted', 'guilty'),
                            ('stone', 'stone')):
            p = self.pose(self.perched(), state=state)
            self.assertEqual((p.file, p.anchor), (file, 1.0))

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
        m = spawn(S, 0.5, 0.0, rng=rng())
        snapshot = (m.mode, m.x, m.y, m.frac)
        tick(m, [G], 1.0, DT)
        self.assertEqual((m.mode, m.x, m.y, m.frac), snapshot)
        self.assertIsInstance(m, Motion)


if __name__ == '__main__':
    unittest.main()
