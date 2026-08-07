"""Series lifecycle — tracks gamelet settlement toward series closure."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SERIES_GAMELET_COUNT = 6


@dataclass
class SeriesResult:
    """Aggregated result of a completed series."""

    game_uid: str
    game_id: str
    cop_total: int
    thief_total: int
    gamelet_results: list[dict] = field(default_factory=list)


class SeriesLifecycle:
    """Tracks gamelet settlement events toward series closure.

    A series closes when exactly 6 gamelet_settled events are received.
    Technical losses still require a subsequent gamelet_settled event.
    Once closed, the series refuses to accept further events.
    """

    def __init__(self, game_uid: str, game_id: str) -> None:
        """Initialise lifecycle tracker for one series.

        Args:
            game_uid: Canonical series identity.
            game_id: Protocol/course game ID.
        """
        self.game_uid = game_uid
        self.game_id = game_id
        self.settled_count: int = 0
        self.is_closed: bool = False
        self._gamelet_results: list[dict] = []
        self._on_close_callbacks: list = []
        self._result: SeriesResult | None = None

    def on_event(self, event: str, data: dict) -> None:
        """Process a series event.

        Only gamelet_settled increments the counter.
        gamelet_technical_loss is recorded but does not settle alone.

        Args:
            event: Event name string.
            data: Event data dict.
        """
        if self.is_closed:
            logger.warning("Event %r received after series closed — ignored", event)
            return
        if event == "gamelet_settled":
            self.settled_count += 1
            self._gamelet_results.append(data)
            logger.info(
                "gamelet_settled sg=%s settled=%d/%d",
                data.get("sub_game_number"),
                self.settled_count,
                SERIES_GAMELET_COUNT,
            )
            if self.settled_count == SERIES_GAMELET_COUNT:
                self._close_series()
        elif event == "gamelet_technical_loss":
            logger.info(
                "gamelet_technical_loss sg=%s reason=%s",
                data.get("sub_game_number"),
                data.get("reason"),
            )

    def _close_series(self) -> None:
        """Mark the series as closed and compute aggregate scores."""
        self.is_closed = True
        cop_wins = sum(1 for r in self._gamelet_results if r.get("winner") == "police")
        thief_wins = self.settled_count - cop_wins
        self._result = SeriesResult(
            game_uid=self.game_uid,
            game_id=self.game_id,
            cop_total=cop_wins,
            thief_total=thief_wins,
            gamelet_results=list(self._gamelet_results),
        )
        logger.info("Series closed cop=%d thief=%d", cop_wins, thief_wins)
        for cb in self._on_close_callbacks:
            cb(self._result)

    def add_close_callback(self, callback) -> None:
        """Register a callback to be called when the series closes."""
        self._on_close_callbacks.append(callback)

    @property
    def result(self) -> SeriesResult | None:
        """Return series result if closed, else None."""
        return self._result if self.is_closed else None
