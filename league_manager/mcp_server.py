"""External MCP server exposing 4 ref-v3 tools to the peer."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LMMCPServer:
    """Exposes the 4 ref-v3 MCP tools to the peer (opponent).

    Wire normalisation happens here. Routing happens in Router.
    Workers receive domain objects, not raw dicts.
    """

    def __init__(self, router, adapter) -> None:
        """Initialise with a Router and a locked ProtocolAdapter.

        Args:
            router: Router instance for dispatching to workers.
            adapter: Locked ProtocolAdapter for wire normalisation.
        """
        self._router = router
        self._adapter = adapter

    def negotiate(self, payload: dict) -> dict:
        """Handle a negotiate tool call from the peer.

        Police calls this on thief's endpoint to agree terms.
        LM handles series initialisation; does not forward to worker.

        Args:
            payload: Raw negotiate payload from peer.

        Returns:
            Agreed terms dict.
        """
        normalised = self._adapter.normalise_negotiate(payload)
        logger.info("negotiate received: %s", normalised)
        # Series registration happens here in production.
        return {"ok": True, "agreed_terms": payload.get("proposed_terms", {})}

    def receive_turn(self, payload: dict) -> dict:
        """Handle a receive_turn tool call — forward opponent turn to worker.

        The ``receive_turn`` tool takes a ``message`` argument (not ``payload``);
        the handler receives the raw turn dict directly after the __main__ fix.
        ``game_uid`` and ``sub_game_number`` may not be present in all turn shapes,
        so both use ``.get()`` with safe defaults.

        Args:
            payload: Raw turn payload dict from peer (may be the turn dict directly).

        Returns:
            Worker response dict.
        """
        game_uid = payload.get("game_uid", "")
        sg = payload.get("sub_game_number", 1)
        normalised = self._adapter.normalise_turn(payload)
        return self._router.route(
            game_uid,
            sg,
            "deliver_event",
            {
                "event_type": "opponent_turn",
                "payload": normalised,
            },
        )

    def submit_audit(self, payload: dict) -> dict:
        """Handle a submit_audit tool call — forward audit bundle to worker.

        ``submit_audit`` takes a ``payload`` argument (not ``message``); this is
        the load-bearing asymmetry in the ref-v3 wire.  The outer ``payload``
        parameter here IS the audit dict; ``game_uid`` and ``sub_game_number`` are
        not present in audit messages, so both use ``.get()`` with safe defaults.

        Args:
            payload: Raw audit payload dict from peer (the AuditPayload wire form).

        Returns:
            Worker response dict.
        """
        game_uid = payload.get("game_uid", "")
        sg = payload.get("sub_game_number", 1)
        normalised = self._adapter.normalise_audit(payload)
        return self._router.route(
            game_uid,
            sg,
            "deliver_event",
            {
                "event_type": "opponent_audit",
                "payload": normalised,
            },
        )

    def receive_control(self, payload: dict) -> dict:
        """Handle a receive_control tool call — forward control signal to worker.

        Args:
            payload: Raw control signal from peer.

        Returns:
            Worker response dict.
        """
        game_uid = payload.get("game_uid", "")
        sg = payload.get("sub_game_number", 1)
        normalised = self._adapter.normalise_control(payload)
        if game_uid:
            return self._router.route(
                game_uid,
                sg,
                "deliver_event",
                {
                    "event_type": "control_signal",
                    "payload": normalised,
                },
            )
        return {"ok": True}
