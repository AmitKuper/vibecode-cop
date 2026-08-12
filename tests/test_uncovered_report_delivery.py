"""Tests for reports/delivery_store.py and reports/gatekeeper.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""

import asyncio


class TestDeliveryStore:
    def test_load_history_missing(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        assert store.load_history("game_01") == []

    def test_get_delivery_path(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        p = store.get_delivery_path("game_01")
        assert "game_01" in str(p)

    def test_record_and_load(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        record = {"plugin": "gmail", "status": "sent", "timestamp": "now"}
        asyncio.run(store.record_delivery("game_01", record))
        history = store.load_history("game_01")
        assert len(history) == 1
        assert history[0]["status"] == "sent"

    def test_has_successful_delivery_no(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        result = asyncio.run(store.has_successful_delivery("game_01", "gmail"))
        assert result is False

    def test_has_successful_delivery_yes(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        record = {"plugin": "gmail", "status": "sent", "game_id": "game_01"}
        asyncio.run(store.record_delivery("game_01", record))
        result = asyncio.run(store.has_successful_delivery("game_01", "gmail"))
        assert result is True

    def test_load_history_corrupted(self, tmp_path):
        from league_manager.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        path = store.get_delivery_path("bad_game")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("NOT JSON", encoding="utf-8")
        assert store.load_history("bad_game") == []  # should not raise


class TestReportGatekeeper:
    def test_dry_run_always_allowed(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        result = asyncio.run(g.can_send("g1", "gmail", [], mode="dry_run"))
        ok, reason = result
        assert ok is True

    def test_draft_always_allowed(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        ok, reason = asyncio.run(g.can_send("g1", "gmail", [], mode="draft"))
        assert ok is True

    def test_already_sent_blocks(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        history = [{"plugin": "gmail", "status": "sent", "game_id": "g1"}]
        ok, reason = asyncio.run(g.can_send("g1", "gmail", history, mode="send"))
        assert ok is False
        assert "Already" in reason

    def test_daily_limit_blocks(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper(max_sends_per_day=2)
        history = [
            {"status": "sent", "timestamp": "9999-01-01T00:00:00"},
            {"status": "sent", "timestamp": "9999-01-01T00:01:00"},
        ]
        ok, reason = asyncio.run(g.can_send("g2", "gmail", history, mode="send"))
        assert ok is False

    def test_max_retries_blocks(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper(max_retries=2)
        history = [
            {"plugin": "gmail", "status": "failed", "game_id": "g3"},
            {"plugin": "gmail", "status": "failed", "game_id": "g3"},
        ]
        ok, reason = asyncio.run(g.can_send("g3", "gmail", history, mode="send"))
        assert ok is False

    def test_record_send(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        rec = g.record_send(
            "g1", "gmail", "send", "sent", destination="test@x.com", message_id="msg-01"
        )
        assert rec["status"] == "sent"
        assert rec["destination"] == "test@x.com"
        assert rec["message_id"] == "msg-01"

    def test_record_send_failed(self):
        from league_manager.reports.gatekeeper import ReportGatekeeper

        g = ReportGatekeeper()
        rec = g.record_send("g1", "gmail", "send", "failed", error="SMTP error")
        assert rec["error"] == "SMTP error"
