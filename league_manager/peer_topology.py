"""PeerTopology — describes how to reach the opponent's MCP server(s)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PeerTopology:
    """Describes peer connectivity mode and URL(s).

    Our deployment always uses mode='single'. The peer may use either mode.
    LM must handle both when making outbound calls.
    """

    mode: Literal["single", "role_split"]
    single_url: str | None = None
    cop_url: str | None = None
    thief_url: str | None = None

    def get_url_for_role(self, role: str) -> str:
        """Return the correct peer URL for a given role.

        Args:
            role: 'police' or 'thief'.

        Returns:
            URL string for outbound calls.

        Raises:
            ValueError: If mode is unknown or required URL is missing.
        """
        if self.mode == "single":
            if not self.single_url:
                raise ValueError("single_url is required for mode='single'")
            return self.single_url
        if self.mode == "role_split":
            if role == "police":
                if not self.cop_url:
                    raise ValueError("cop_url required for role_split mode")
                return self.cop_url
            if not self.thief_url:
                raise ValueError("thief_url required for role_split mode")
            return self.thief_url
        raise ValueError(f"Unknown topology mode: {self.mode!r}")

    @classmethod
    def single(cls, url: str) -> PeerTopology:
        """Convenience constructor for single-address topology."""
        return cls(mode="single", single_url=url)

    @classmethod
    def role_split(cls, cop_url: str, thief_url: str) -> PeerTopology:
        """Convenience constructor for role-split topology."""
        return cls(mode="role_split", cop_url=cop_url, thief_url=thief_url)
