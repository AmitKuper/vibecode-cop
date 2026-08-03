"""Tests that role-filtered live endpoints exclude the opponent's position."""

from unittest.mock import patch

import pytest


class TestLiveViewRoleFiltering:
    @pytest.mark.asyncio
    async def test_cop_endpoint_excludes_thief_position(self):
        from webserver.routes.live_view import live_cop_view

        full_state = {
            "game_id": "g001",
            "cop_position": [1, 2],
            "thief_position": [5, 6],
            "turn": 3,
        }

        with patch("webserver.routes.live_view.game_registry") as mock_reg:
            mock_reg.get.return_value = full_state
            result = await live_cop_view("g001")

        assert "thief_position" not in result
        assert result.get("cop_position") == [1, 2]
        assert result.get("role") == "cop"

    @pytest.mark.asyncio
    async def test_thief_endpoint_excludes_cop_position(self):
        from webserver.routes.live_view import live_thief_view

        full_state = {
            "game_id": "g001",
            "cop_position": [1, 2],
            "thief_position": [5, 6],
            "turn": 3,
        }

        with patch("webserver.routes.live_view.game_registry") as mock_reg:
            mock_reg.get.return_value = full_state
            result = await live_thief_view("g001")

        assert "cop_position" not in result
        assert result.get("thief_position") == [5, 6]
        assert result.get("role") == "thief"

    @pytest.mark.asyncio
    async def test_cop_endpoint_returns_404_for_unknown_game(self):
        from fastapi import HTTPException

        from webserver.routes.live_view import live_cop_view

        with patch("webserver.routes.live_view.game_registry") as mock_reg:
            mock_reg.get.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await live_cop_view("unknown")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_thief_endpoint_returns_404_for_unknown_game(self):
        from fastapi import HTTPException

        from webserver.routes.live_view import live_thief_view

        with patch("webserver.routes.live_view.game_registry") as mock_reg:
            mock_reg.get.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await live_thief_view("unknown")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cop_and_thief_views_are_disjoint_on_position_keys(self):
        from webserver.routes.live_view import live_cop_view, live_thief_view

        full_state = {
            "game_id": "g001",
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
            "move_history": [],
        }

        with patch("webserver.routes.live_view.game_registry") as mock_reg:
            mock_reg.get.return_value = full_state
            cop_view = await live_cop_view("g001")

        with patch("webserver.routes.live_view.game_registry") as mock_reg:
            mock_reg.get.return_value = full_state
            thief_view = await live_thief_view("g001")

        # Each role sees its own position, not the opponent's
        assert "cop_position" in cop_view and "thief_position" not in cop_view
        assert "thief_position" in thief_view and "cop_position" not in thief_view
