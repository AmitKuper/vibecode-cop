"""PeerAgentRuntime — production P2P runtime: MCP server + PeerRuntime.

Replaces the standalone GameOrchestrator in production entrypoints.
  PeerAgentRuntime = MCP server + PeerRuntime + strategy + report manager

Passive helpers (thief commit/reveal) are in peer_agent_passive.py.
"""

import asyncio
import json
import logging
import threading
from pathlib import Path

from agent.mcp.server import AgentMCPServer
from agent.peer_agent_passive import (
    handle_passive_commit,
    handle_passive_final_audit,
    handle_passive_game_end,
    handle_passive_reveal,
    init_passive_game,
)
from agent.peer_runtime import PeerRuntime

logger = logging.getLogger(__name__)

try:
    from agent.orchestrator_discovery import DiscoveryMixin as _DiscoveryMixin
except Exception as _disc_import_err:
    logger.warning(f"DiscoveryMixin unavailable ({_disc_import_err}); MCP discovery disabled")

    class _DiscoveryMixin:  # type: ignore[no-redef]
        def discover_protocol(self, game_id, peer_url):
            pass


class PeerAgentRuntime(_DiscoveryMixin):
    """Production agent runtime: wraps AgentMCPServer + PeerRuntime.

    Cop (role="cop"): active mode — PeerRuntime.run_game() is launched as a
    background asyncio task when start_game is received from the thief.

    Thief (role="thief"): passive mode — handles commit/reveal calls inline
    as the cop drives each turn; sends final_audit at game end.
    """

    def __init__(
        self,
        role: str,
        secret: str,
        config_sha256: str,
        opponent_url: str,
        games_dir: Path,
        group_name: str = "unknown",
        llm_dict: dict | None = None,
        my_endpoint: str = "",
        mode=None,
        orchestrator_config: dict | None = None,
    ):
        if role not in ("cop", "thief"):
            raise ValueError(f"role must be 'cop' or 'thief', got {role!r}")
        self.role = role
        self.secret = secret
        from agent.runtime_mode import RuntimeMode

        resolved_mode = mode if mode is not None else RuntimeMode.DEVELOPMENT
        self.mode = resolved_mode
        self._peer_runtime = PeerRuntime(
            role=role,
            secret=secret,
            config_sha256=config_sha256,
            opponent_url=opponent_url,
            games_dir=Path(games_dir),
            group_name=group_name,
            llm_dict=llm_dict,
            my_endpoint=my_endpoint,
            counted_mode=resolved_mode == RuntimeMode.COUNTED,
            orchestrator_config=orchestrator_config,
        )
        self.llm = self._peer_runtime.llm
        self._peer_url = opponent_url.rstrip("/").replace("/mcp", "")
        self.protocol_model: dict = {}
        self.mcp_skill = None
        self._rules_ref: list = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mcp_server = AgentMCPServer(
            role=role,
            secret=secret,
            config_sha256=config_sha256,
            games_dir=Path(games_dir),
            handler_callbacks={
                "on_start_game": self._on_start_game,
                "on_action": self._on_action,
            },
        )
        logger.info(f"PeerAgentRuntime initialised for {role}")

    def _on_start_game(self, message) -> dict:
        game_id = message.game_id
        self._peer_runtime._gamelet_number(game_id)
        self._peer_runtime._ensure_orchestrator(game_id)
        from agent.peer_step0 import (
            accept_remote_signed_declaration,
            build_local_signed_declaration,
            persist_step0_evidence,
        )

        local_signed = None
        agreement = None
        try:
            local_signed = build_local_signed_declaration(self._peer_runtime, game_id)
            agreement = accept_remote_signed_declaration(
                self._peer_runtime, game_id, message.signed_declaration
            )
        except Exception as exc:
            if self.mode.value == "counted":
                raise
            logger.warning("Development Step-0 compatibility fallback: %s", exc)
        if self.mode.value != "counted":
            try:
                self.discover_protocol(game_id, self._peer_url)
            except Exception as exc:
                logger.warning(
                    f"[PeerAgentRuntime/{self.role}] Discovery failed (non-fatal): {exc}"
                )
        if self.role == "cop":
            loop = self._loop
            if loop is None or not loop.is_running():
                logger.error("[PeerAgentRuntime/cop] No running event loop — cannot start game")
                return {"ok": False, "error": "No event loop", "game_id": game_id}
            asyncio.run_coroutine_threadsafe(self._peer_runtime.run_game(game_id), loop)
            logger.info(f"[PeerAgentRuntime/cop] Scheduled PeerRuntime.run_game({game_id})")
        else:
            init_passive_game(self._peer_runtime, game_id, self._rules_ref)
        if local_signed is not None and agreement is not None:
            persist_step0_evidence(self._peer_runtime, game_id)
        result = {
            "ok": True,
            "game_id": game_id,
        }
        if local_signed is not None and agreement is not None:
            result["signed_declaration"] = local_signed.to_dict()
            result["declaration_agreement_hash"] = agreement.agreement_hash
        return result

    def _on_action(self, game_id: str, message) -> dict:
        phase = message.phase
        if phase == "commit":
            return handle_passive_commit(self._peer_runtime, game_id, message, self._rules_ref)
        if phase == "reveal":
            return handle_passive_reveal(self._peer_runtime, game_id, message, self._rules_ref)
        if phase == "final_audit":
            return handle_passive_final_audit(self._peer_runtime, game_id, message)
        if phase == "result_agreement":
            from agent.peer_result import accept_and_sign_result

            result = accept_and_sign_result(self._peer_runtime, game_id, message)
            if result.get("ok"):
                self._send_report_async(game_id, result.get("signed_result_agreement"))
            return result
        if phase == "game_end":
            return handle_passive_game_end(self._peer_runtime, game_id, message, self._rules_ref)
        return {"ok": False, "error": f"Unknown phase: {phase}"}

    def _send_report_async(self, game_id: str, signed_result: dict | None) -> None:
        rt = self._peer_runtime
        if rt.orchestrator is None or signed_result is None:
            logger.warning("[PeerAgentRuntime/%s] Cannot schedule report: missing orchestrator or result", rt.role)
            return
        series_id = signed_result.get("agreement", {}).get("game_uid", game_id)
        idempotency_key = f"{series_id}_{rt.role}"
        result_json = json.dumps(signed_result, sort_keys=True)

        def _send() -> None:
            try:
                delivery_id = rt.orchestrator.send_report_via_gatekeeper(
                    idempotency_key=idempotency_key,
                    game_id=series_id,
                    result_json=result_json,
                )
                logger.info("[PeerAgentRuntime/%s] Report delivered: %s", rt.role, delivery_id)
            except Exception as exc:
                logger.warning("[PeerAgentRuntime/%s] Report delivery failed: %s", rt.role, exc)

        threading.Thread(target=_send, daemon=True, name=f"gmail-{series_id}").start()
        logger.info("[PeerAgentRuntime/%s] Gmail report scheduled for %s", rt.role, series_id)

    async def run_async(self, host: str = "0.0.0.0", port: int = 5000) -> None:
        """Start the MCP server. Cop's PeerRuntime loop starts on first start_game call."""
        self._loop = asyncio.get_running_loop()
        logger.info(f"[PeerAgentRuntime/{self.role}] Starting MCP server on {host}:{port}")
        # Start reference-v3 background tasks if opponent is configured
        if self._peer_url:
            if self.role == "cop":
                asyncio.ensure_future(self._reference_v3_cop_task())
            else:
                asyncio.ensure_future(self._reference_v3_thief_task())
        await self._mcp_server.run_async(host=host, port=port)

    def _build_reference_v3_outbound_caller(self):
        """Return an async callable that calls tools on the opponent's MCP endpoint."""
        from agent.adaptive.transport_probe import normalize_mcp_base_url
        peer_mcp = normalize_mcp_base_url(self._peer_url) + "/mcp"

        async def _call(tool_name: str, params: dict) -> dict:
            from fastmcp import Client
            from fastmcp.client.transports import StreamableHttpTransport
            transport = StreamableHttpTransport(peer_mcp)
            async with Client(transport) as client:
                result = await client.call_tool(tool_name, params)
            if not result.content:
                return {"ok": True}
            item = result.content[0]
            value = item.text if hasattr(item, "text") else str(item)
            try:
                import json
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {"ok": True, "raw": parsed}
            except Exception:
                return {"ok": True, "raw": value}

        return _call

    async def _reference_v3_cop_task(self) -> None:
        """Background: wait for startup, probe opponent; if reference-v3, drive series."""
        import asyncio as _asyncio
        await _asyncio.sleep(1.0)  # let our server finish binding
        try:
            from agent.adaptive.introspector import MCPIntrospector
            from agent.adaptive.reference_v3 import is_reference_v3_surface, default_terms
            from agent.adaptive.transport_probe import TransportProbe, normalize_mcp_base_url
            from agent.reference_v3_game import play_reference_v3_series

            peer_base = normalize_mcp_base_url(self._peer_url)
            peer_mcp = peer_base + "/mcp"  # used for the outbound caller only
            # Retry probing for up to 45s (opponent may start after us)
            probe = None
            for _attempt in range(15):
                probe = await TransportProbe(timeout_s=4.0).probe(peer_base)
                if probe.transport.value != "unknown":
                    break
                logger.info("[PeerAgentRuntime/cop] Waiting for ref-v3 opponent at %s (attempt %d)", peer_mcp, _attempt + 1)
                await _asyncio.sleep(3.0)
            if probe is None or probe.transport.value == "unknown":
                logger.info("[PeerAgentRuntime/cop] Ref-v3 opponent never came up at %s; giving up", peer_mcp)
                return
            intro = await MCPIntrospector(timeout_s=10.0).introspect(probe)
            if not is_reference_v3_surface(intro):
                logger.info("[PeerAgentRuntime/cop] Opponent is not reference-v3; skipping ref-v3 series")
                return
            logger.info("[PeerAgentRuntime/cop] Reference-v3 opponent detected — initiating series")
            caller = self._build_reference_v3_outbound_caller()
            rt = self._peer_runtime
            orchestrator = rt.orchestrator if rt.orchestrator is not None else None
            from agent.config.shared_config import load_shared_config
            shared = load_shared_config()
            group_id = getattr(rt, "group_name", "vibecode")
            group_name = group_id
            result = await play_reference_v3_series(
                local_session=self._mcp_server.reference_v3_session,
                outbound_caller=caller,
                starting_role="police",
                group_id=group_id,
                group_name=group_name,
                orchestrator=orchestrator,
                games_dir=rt.games_dir,
            )
            logger.info("[PeerAgentRuntime/cop] Ref-v3 series done: %s", result)
        except Exception as exc:
            logger.warning("[PeerAgentRuntime/cop] Ref-v3 cop task failed: %s", exc, exc_info=True)

    async def _reference_v3_thief_task(self) -> None:
        """Background: wait for police to send negotiate, then drive thief series."""
        import asyncio as _asyncio
        logger.info("[PeerAgentRuntime/thief] Ref-v3 thief task started; waiting for police negotiate")
        await _asyncio.sleep(1.0)
        session = self._mcp_server.reference_v3_session
        # Wait up to 300s for first negotiate (gives police time to start)
        deadline = _asyncio.get_event_loop().time() + 300.0
        while _asyncio.get_event_loop().time() < deadline:
            if session.agreements:
                break
            await _asyncio.sleep(0.2)
        if not session.agreements:
            logger.info("[PeerAgentRuntime/thief] No police negotiate received; ref-v3 task idle")
            return
        try:
            from agent.adaptive.reference_v3 import default_terms
            from agent.reference_v3_game import play_reference_v3_series

            caller = self._build_reference_v3_outbound_caller()
            rt = self._peer_runtime
            orchestrator = rt.orchestrator if rt.orchestrator is not None else None
            group_id = getattr(rt, "group_name", "vibecode")
            group_name = group_id
            result = await play_reference_v3_series(
                local_session=session,
                outbound_caller=caller,
                starting_role="thief",
                group_id=group_id,
                group_name=group_name,
                orchestrator=orchestrator,
                games_dir=rt.games_dir,
            )
            logger.info("[PeerAgentRuntime/thief] Ref-v3 series done: %s", result)
        except Exception as exc:
            logger.warning("[PeerAgentRuntime/thief] Ref-v3 thief task failed: %s", exc, exc_info=True)
