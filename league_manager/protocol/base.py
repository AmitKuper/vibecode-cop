"""Abstract base class for protocol adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProtocolAdapter(ABC):
    """Abstract interface that all protocol adapters must implement.

    A ProtocolAdapter handles wire serialisation/deserialisation for one
    specific protocol dialect (e.g., reference-v3). It does NOT contain
    game logic — only wire format translation.
    """

    @classmethod
    @abstractmethod
    def candidate_tool_names(cls) -> set[str]:
        """Return the MCP tool names that identify this protocol as a candidate."""

    @abstractmethod
    def normalise_negotiate(self, payload: dict) -> dict:
        """Normalise a raw negotiate payload to a domain object."""

    @abstractmethod
    def normalise_turn(self, payload: dict) -> dict:
        """Normalise a raw receive_turn payload to a domain object."""

    @abstractmethod
    def normalise_audit(self, payload: dict) -> dict:
        """Normalise a raw submit_audit payload to a domain object."""

    @abstractmethod
    def normalise_control(self, payload: dict) -> dict:
        """Normalise a raw receive_control payload to a domain object."""

    @abstractmethod
    def serialise_response(self, domain_response: dict) -> dict:
        """Serialise a domain response object back to wire format."""
