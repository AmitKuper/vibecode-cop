"""Abstract transport layer — separates transport mechanism from game semantics."""
from abc import ABC, abstractmethod


class TransportPort(ABC):
    """Abstract transport. Game code depends only on this interface."""

    @abstractmethod
    async def send(self, tool_name: str, params: dict) -> dict:
        """Send a request and return the response dict."""

    @abstractmethod
    async def connect(self, endpoint: str) -> None:
        """Establish connection to endpoint."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""

    @property
    @abstractmethod
    def transport_type(self) -> str:
        """e.g. 'SSE', 'StreamableHTTP', 'stdio'"""


class SSETransportAdapter(TransportPort):
    """SSE transport — wraps the existing FastMCP SSE client."""

    def __init__(self, client_factory=None):
        self._client_factory = client_factory
        self._client = None
        self._endpoint = ""

    async def connect(self, endpoint: str) -> None:
        self._endpoint = endpoint
        # Lazy — real connection established on first send via FastMCP

    async def disconnect(self) -> None:
        if self._client is not None:
            # Close if client supports it
            pass

    async def send(self, tool_name: str, params: dict) -> dict:
        """Delegate to existing FastMCP call logic."""
        if self._client_factory:
            return await self._client_factory(self._endpoint, tool_name, params)
        raise RuntimeError("No client factory configured")

    @property
    def transport_type(self) -> str:
        return "SSE"


class StubTransportAdapter(TransportPort):
    """Deterministic in-process transport for testing."""

    def __init__(self, handler):
        self._handler = handler  # Callable(tool_name, params) -> dict
        self._connected = False

    async def connect(self, endpoint: str) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send(self, tool_name: str, params: dict) -> dict:
        if not self._connected:
            raise RuntimeError("Not connected")
        return await self._handler(tool_name, params)

    @property
    def transport_type(self) -> str:
        return "stub"
