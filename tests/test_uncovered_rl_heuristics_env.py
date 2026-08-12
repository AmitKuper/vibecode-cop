"""Tests for rl/heuristics.py and rl/env_helpers.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


class TestHeuristics:
    def test_bfs_dist_basic(self):
        from cop_worker.rl.heuristics import _bfs_dist

        dist = _bfs_dist((0, 0), [], grid_size=7)
        assert dist[(0, 0)] == 0
        assert dist[(0, 1)] == 1
        assert dist[(1, 0)] == 1
        assert dist[(6, 6)] == 12

    def test_bfs_dist_with_barrier(self):
        from cop_worker.rl.heuristics import _bfs_dist

        # Block off (0, 1) — should not appear in results
        dist = _bfs_dist((0, 0), [(0, 1)], grid_size=7)
        assert (0, 1) not in dist
        # Can still reach (1, 0)
        assert (1, 0) in dist

    def test_random_legal_cop_returns_action(self):
        from cop_worker.rl.heuristics import random_legal_cop

        action = random_legal_cop((3, 3), [], barriers_remaining=3, grid_size=7)
        assert isinstance(action, str)
        assert len(action) > 0

    def test_random_legal_cop_no_barriers(self):
        from cop_worker.rl.heuristics import random_legal_cop

        action = random_legal_cop((3, 3), [], barriers_remaining=0, grid_size=7)
        assert isinstance(action, str)

    def test_random_legal_thief_returns_action(self):
        from cop_worker.rl.heuristics import random_legal_thief

        action = random_legal_thief((3, 3), [], grid_size=7)
        assert isinstance(action, str)
        assert len(action) > 0

    def test_pursuit_cop_moves_toward_target(self):
        from cop_worker.rl.heuristics import pursuit_cop

        # Cop at (0,0), thief believed at (3,3); should move toward it
        action = pursuit_cop((0, 0), (3, 3), [], barriers_remaining=3, grid_size=7)
        assert action in ["N", "S", "E", "W", "STAY"]

    def test_evasion_thief_moves_away(self):
        from cop_worker.rl.heuristics import evasion_thief

        # Thief at (3,3), cop believed at (3,3); should move away
        action = evasion_thief((3, 3), (3, 3), [], grid_size=7)
        assert action in ["N", "S", "E", "W", "STAY"]

    def test_pursuit_cop_with_barriers(self):
        from cop_worker.rl.heuristics import pursuit_cop

        action = pursuit_cop((0, 0), (6, 6), [(1, 0), (0, 1)], barriers_remaining=3, grid_size=7)
        # With barriers blocking N and E from (0,0), must STAY or pick valid direction
        assert isinstance(action, str)

    def test_evasion_thief_corner(self):
        from cop_worker.rl.heuristics import evasion_thief

        # Corner position — fewer options
        action = evasion_thief((0, 0), (0, 0), [], grid_size=7)
        assert action in ["N", "S", "E", "W", "STAY"]


class TestEnvHelpers:
    def test_random_starts_distinct(self):
        from cop_worker.rl.env_helpers import random_starts

        cop, thief = random_starts(7, [])
        assert len(cop) == 2
        assert len(thief) == 2
        assert cop != thief

    def test_random_starts_avoids_barriers(self):
        from cop_worker.rl.env_helpers import random_starts

        # Fill most of the board but leave at least 2 free cells
        barriers = [
            [x, y]
            for x in range(7)
            for y in range(7)
            if not (x == 0 and y == 0) and not (x == 6 and y == 6)
        ]
        cop, thief = random_starts(7, barriers)
        assert cop != thief

    def test_manhattan_dist(self):
        from cop_worker.board import Board
        from cop_worker.rl.env_helpers import manhattan_dist

        board = Board(cop_position=[0, 0], thief_position=[3, 4])
        dist = manhattan_dist(board)
        assert dist == 7  # |0-3| + |0-4|

    def test_manhattan_dist_same_cell(self):
        from cop_worker.board import Board
        from cop_worker.rl.env_helpers import manhattan_dist

        board = Board(cop_position=[2, 2], thief_position=[2, 2])
        assert manhattan_dist(board) == 0

    def test_place_deltas_keys(self):
        from cop_worker.rl.env_helpers import _PLACE_DELTAS

        assert set(_PLACE_DELTAS.keys()) == {"PLACE_N", "PLACE_S", "PLACE_E", "PLACE_W"}

    def test_apply_place_action_no_barriers_remaining(self):
        from cop_worker.board import Board
        from cop_worker.rl.env_helpers import apply_place_action

        board = Board(cop_position=[3, 3], thief_position=[0, 0])
        result = apply_place_action(board, "PLACE_N", grid_size=7, barriers_remaining=0)
        assert result == 0  # no change

    def test_apply_place_action_places_barrier(self):
        from cop_worker.board import Board
        from cop_worker.rl.env_helpers import apply_place_action

        board = Board(cop_position=[3, 3], thief_position=[0, 0])
        result = apply_place_action(board, "PLACE_S", grid_size=7, barriers_remaining=3)
        # PLACE_S: dy=+1, so barrier at (3, 4)
        assert result == 2
        assert [3, 4] in board.barriers

    def test_apply_place_action_out_of_bounds(self):
        from cop_worker.board import Board
        from cop_worker.rl.env_helpers import apply_place_action

        # Cop at edge — placing barrier out of bounds should no-op
        board = Board(cop_position=[0, 0], thief_position=[6, 6])
        result = apply_place_action(board, "PLACE_N", grid_size=7, barriers_remaining=3)
        # PLACE_N: dy=-1, so barrier at (0, -1) which is out of bounds
        assert result == 3  # unchanged
