"""peersim01 — realistic league-peer simulator implementation package (bench-only).

A stand-in opponent that behaves like the real peers we faced (najamjad,
imreeyal, uoh-sqak) rather than like the kit's gentle sparring client: one
single-URL server for all six windows, lean najamjad-shaped greetings, eager and
duplicate greeting quirks, slow dials, pre-decay scent, and — crucially — a clean
MCP session close (DELETE) at every window end, the wedge trigger our thief door
hit in a live game. One module per concern, each 150 lines or fewer; the CLI
facade is ``scripts/peer_sim.py``.
"""
