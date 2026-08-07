"""ReferenceV3Adapter — wire normalisation for the reference-v3 protocol dialect."""

from __future__ import annotations

from league_manager.protocol.base import ProtocolAdapter


class ReferenceV3Adapter(ProtocolAdapter):
    """Wire adapter for the reference-v3 protocol dialect.

    Normalises raw MCP payloads to domain objects and serialises responses.
    Contains no game logic — only wire format translation.
    """

    PROTOCOL_NAME = "reference-v3"

    @classmethod
    def candidate_tool_names(cls) -> set[str]:
        """Return the 4 tool names that identify this as a reference-v3 endpoint."""
        return {"negotiate", "receive_turn", "submit_audit", "receive_control"}

    def normalise_negotiate(self, payload: dict) -> dict:
        """Normalise a raw negotiate payload to a domain object.

        Args:
            payload: Raw negotiate message dict from peer.

        Returns:
            Domain-normalised negotiate dict.
        """
        msg = payload.get("message", payload)
        return {
            "terms": msg.get("terms", {}),
            "group_id": msg.get("group_id", ""),
            "role": msg.get("role", ""),
            "sub_game_number": msg.get("sub_game_number", 1),
            "nonce": msg.get("nonce", ""),
            "signature": msg.get("signature", ""),
        }

    def normalise_turn(self, payload: dict) -> dict:
        """Normalise a raw receive_turn payload to a domain object.

        Args:
            payload: Raw turn payload dict from peer.

        Returns:
            Domain-normalised turn dict.
        """
        msg = payload.get("message", payload)
        return {
            "step": msg.get("step", 0),
            "sender": msg.get("sender", ""),
            "commit": msg.get("commit", ""),
            "hint": msg.get("hint", ""),
            "smell_grid": msg.get("smell_grid", {}),
            "timestamp": msg.get("timestamp", ""),
            "barrier_placed": msg.get("barrier_placed"),
            "capture_claim": msg.get("capture_claim"),
            "claim_response": msg.get("claim_response"),
            "win_claim": msg.get("win_claim"),
        }

    def normalise_audit(self, payload: dict) -> dict:
        """Normalise a raw submit_audit payload to a domain object.

        Args:
            payload: Raw audit payload dict from peer.

        Returns:
            Domain-normalised audit dict.
        """
        inner = payload.get("payload", payload)
        return {
            "sender": inner.get("sender", ""),
            "records": inner.get("records", []),
            "result_claim": inner.get("result_claim", ""),
        }

    def normalise_control(self, payload: dict) -> dict:
        """Normalise a raw receive_control payload to a domain object.

        Args:
            payload: Raw control signal dict from peer.

        Returns:
            Domain-normalised control dict.
        """
        msg = payload.get("message", payload)
        return {
            "type": msg.get("type", ""),
            "data": msg.get("data", {}),
        }

    def serialise_response(self, domain_response: dict) -> dict:
        """Serialise a domain response object back to wire format.

        Args:
            domain_response: Domain response dict.

        Returns:
            Wire-format response dict.
        """
        return dict(domain_response)
