"""Agent infrastructure: MCP communication and game engine."""

from agent.board import Board
from agent.llm import LLMConfig, LLMConfigBuilder, LLMFactory, LLMProvider
from agent.mcp.client import GameMCPClient
from agent.mcp.crypto import (
    canonical_json,
    create_commitment,
    hash_game_state,
    sign_message,
    verify_commitment,
    verify_signature,
)
from agent.mcp.discovery import ProtocolDiscovery
from agent.mcp.log import GameLog
from agent.mcp.messages import (
    ActionMessage,
    MessagePhase,
    StartGameMessage,
    validate_action_message,
    validate_start_game_message,
)
from agent.mcp.protocol import (
    ProtocolPhase,
    ProtocolState,
    ProtocolStateMachine,
    StepPhaseTracker,
)
from agent.mcp.server import AgentMCPServer
from agent.rules_engine import GameOutcome, RulesEngine

__all__ = [
    # Board & Rules
    "Board",
    "RulesEngine",
    "GameOutcome",
    # LLM Support
    "LLMProvider",
    "LLMConfig",
    "LLMConfigBuilder",
    "LLMFactory",
    # MCP Protocol
    "AgentMCPServer",
    "GameMCPClient",
    "ProtocolDiscovery",
    "StartGameMessage",
    "ActionMessage",
    "MessagePhase",
    "ProtocolPhase",
    "ProtocolState",
    "ProtocolStateMachine",
    "StepPhaseTracker",
    # Crypto
    "canonical_json",
    "sign_message",
    "verify_signature",
    "create_commitment",
    "verify_commitment",
    "hash_game_state",
    # Logging
    "GameLog",
    # Validation
    "validate_start_game_message",
    "validate_action_message",
]
