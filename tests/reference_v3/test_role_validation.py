"""Test role validation for sub-game routing."""

from league_manager.router import DEFAULT_ROLE_SCHEDULE

# DEFAULT_ROLE_SCHEDULE: {1:"cop", 2:"thief", 3:"cop", 4:"thief", 5:"cop", 6:"thief"}


def test_cop_role_in_odd_sub_games():
    """Default schedule must assign cop to sub-games 1, 3, 5."""
    for sg in [1, 3, 5]:
        assert DEFAULT_ROLE_SCHEDULE[sg] == "cop", (
            f"Expected cop at sub_game {sg}, got {DEFAULT_ROLE_SCHEDULE[sg]}"
        )


def test_thief_role_in_even_sub_games():
    """Default schedule must assign thief to sub-games 2, 4, 6."""
    for sg in [2, 4, 6]:
        assert DEFAULT_ROLE_SCHEDULE[sg] == "thief", (
            f"Expected thief at sub_game {sg}, got {DEFAULT_ROLE_SCHEDULE[sg]}"
        )


def test_role_schedule_structure():
    """Role schedule must have exactly 6 entries covering sub-games 1-6."""
    assert set(DEFAULT_ROLE_SCHEDULE.keys()) == {1, 2, 3, 4, 5, 6}
    assert DEFAULT_ROLE_SCHEDULE[1] == "cop"
    assert DEFAULT_ROLE_SCHEDULE[2] == "thief"
