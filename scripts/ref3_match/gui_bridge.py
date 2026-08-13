"""Optional live-GUI bridge for the split role worker — zero effect when off.

The role worker starts the local-truth GUI (cop_worker.gui) only when its init
dict carries ``gui_port`` (plumbed from [network] gui_cop_port/gui_thief_port
in runtime.toml, absent by default). The mover publishes its own position and
the opponent-scent heatmap through :func:`publish_view`; the disabled path is a
single ``None`` check, and every enabled step is try/except-guarded so a GUI
failure can NEVER affect play. Only local-truth data is published — never an
opponent coordinate (LiveViewModel re-verifies this on every update).
"""

from __future__ import annotations

_VIEW_MODEL = None  # set only when a GUI was started; None => publish is a no-op
_TURN = 0


def set_view_model(vm) -> None:
    """Register (or clear, with None) the live view model fed by publish_view."""
    global _VIEW_MODEL, _TURN
    _VIEW_MODEL = vm
    _TURN = 0


def publish_view(mover, heatmap) -> None:
    """Publish own position + belief/scent heatmap. No-op unless a GUI is registered.

    ``heatmap`` is an NxN list-of-lists in wire (row, col) orientation; the
    mover's ``pos`` is [x, y] and is converted to the same orientation.
    """
    if _VIEW_MODEL is None:  # disabled path: one comparison, zero cost
        return
    global _TURN
    try:
        from cop_worker.observation import SafeLiveView

        _TURN += 1
        grid = [[float(v) for v in row] for row in (heatmap or [])]
        view = SafeLiveView(
            own_position=(int(mover.pos[1]), int(mover.pos[0])),  # wire (row, col)
            belief_heatmap=grid,
            opponent_scent=grid,
            last_hint="",
            hint_reliability=0.0,
            turn=_TURN,
            gamelet=0,
            score={"cop": 0, "thief": 0},
            own_barriers_remaining=int(getattr(mover, "barriers_remaining", 0)),
            protocol_state="GAMEPLAY",
            your_turn=True,
            connection_healthy=True,
        )
        _VIEW_MODEL.update(view)
    except Exception:  # the GUI must never be able to touch play
        return


async def maybe_start_gui(role: str, init: dict):
    """Start the local-truth GUI iff the init dict carries an int ``gui_port``.

    Returns the asyncio server task, or None (no port configured / any failure).
    Never raises — a broken GUI stack must not stop the role worker.
    """
    port = init.get("gui_port")
    if not isinstance(port, int) or isinstance(port, bool):
        return None
    try:
        import asyncio

        import uvicorn

        from cop_worker.gui import app as gui_app
        from cop_worker.gui.live_view_model import LiveViewModel

        vm = LiveViewModel(
            "cop" if role == "police" else "thief",
            int((init.get("terms") or {}).get("board_size", 7)),
        )
        gui_app.set_view_model(vm)
        set_view_model(vm)
        server = uvicorn.Server(
            uvicorn.Config(gui_app.app, host="127.0.0.1", port=port, log_level="warning")
        )
        task = asyncio.get_event_loop().create_task(server.serve())
        print(f"[{role}-worker] live GUI on http://127.0.0.1:{port}")
        return task
    except Exception as exc:
        print(f"[{role}-worker] live GUI disabled ({type(exc).__name__}: {exc})")
        return None


def stop_gui(task) -> None:
    """Tear down the GUI: clear the registered view model, cancel the server task."""
    set_view_model(None)
    if task is not None:
        task.cancel()
