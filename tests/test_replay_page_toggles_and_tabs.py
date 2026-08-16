"""The web replay page: scent toggles, tab embedding, and the way back.

Split from test_gui_routes_and_stepping.py (150-line rule). These pin the
fixes for two user-reported breaks: 'cop scent' doing nothing (single field
with an 'instead of' switch) and history links navigating the dashboard away.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from cop_worker.gui import app as live_gui
from cop_worker.gui.dashboard import app as dashboard_app

client = TestClient(dashboard_app)
live_client = TestClient(live_gui.app)


def test_replay_page_has_show_hide_toggles_and_stays_embeddable():
    body = live_client.get("/replay").text
    for marker in ('id="tg-cop"', 'id="tg-thief"', 'id="tg-scent"', "subtractive_chebyshev_v1"):
        assert marker in body, marker


def test_replay_scent_toggles_are_independent_overlays():
    """'cop scent' must work on its own: two fields, two colors, blend when both.

    The original design was one field with an 'instead of' switch that silently
    required the other toggle too - reported broken by the user.
    """
    body = live_client.get("/replay").text
    assert "scent_cop" in body and "scent_thief" in body
    assert "cellBg(vt,vc)" in body, "each cell must consider BOTH fields"
    assert "212,164,20" in body and "70,130,230" in body, "thief gold vs cop blue"
    assert "instead of" not in body
    # deep-linkable toggle state so screenshot review can capture each mode
    assert "get('scent')" in body


def test_hub_keeps_replay_inside_the_tabs():
    body = client.get("/").text
    assert 'id="nav-replay"' in body and 'id="replay-frame"' in body
    # the history g01..g06 links must call openReplay (stay in the tab), never
    # carry a plain href that navigates the whole dashboard to /replay
    assert "onclick=\"openReplay('${l}')\"" in body
    assert 'href="/replay?log=' not in body


def test_standalone_replay_offers_a_way_back_to_the_dashboard():
    body = live_client.get("/replay").text
    assert 'id="backlink"' in body and 'href="/#replay"' in body
    assert "window.self===window.top" in body, "the link shows only when not embedded"
