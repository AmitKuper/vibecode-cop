"""Tests for reliability/durable_io.py.

Split from test_uncovered_modules_coverage.py; no LLM, no network.
"""


class TestDurableIO:
    def test_atomic_write_bytes_success(self, tmp_path):
        from cop_worker.reliability.durable_io import atomic_write_bytes

        dest = tmp_path / "out.bin"
        atomic_write_bytes(dest, b"hello world")
        assert dest.read_bytes() == b"hello world"

    def test_atomic_write_bytes_invalid_attempts(self, tmp_path):
        import pytest

        from cop_worker.reliability.durable_io import atomic_write_bytes

        dest = tmp_path / "x.bin"
        with pytest.raises(ValueError):
            atomic_write_bytes(dest, b"data", attempts=0)

    def test_atomic_write_bytes_retry_on_failure(self, tmp_path):
        """Force first attempt to fail via read-only directory trick."""
        from unittest.mock import patch

        from cop_worker.reliability.durable_io import atomic_write_bytes

        dest = tmp_path / "sub" / "out.bin"
        call_count = [0]
        orig_replace = __import__("os").replace

        def failing_replace(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("simulated failure")
            return orig_replace(src, dst)

        with patch("os.replace", side_effect=failing_replace):
            # Should succeed on second attempt
            atomic_write_bytes(dest, b"retry", attempts=2, retry_delay_s=0)

    def test_atomic_write_bytes_all_attempts_fail(self, tmp_path):
        from unittest.mock import patch

        import pytest

        from cop_worker.reliability.durable_io import PersistenceError, atomic_write_bytes

        dest = tmp_path / "fail.bin"

        with patch("os.replace", side_effect=OSError("always fails")):
            with pytest.raises(PersistenceError):
                atomic_write_bytes(dest, b"data", attempts=2, retry_delay_s=0)

    def test_atomic_write_json_success(self, tmp_path):
        import json

        from cop_worker.reliability.durable_io import atomic_write_json

        dest = tmp_path / "data.json"
        atomic_write_json(dest, {"key": "value", "num": 42})
        result = json.loads(dest.read_text())
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_sync_directory_windows_noop(self):
        """On Windows (os.name=='nt'), _sync_directory should be a no-op."""
        import os
        from pathlib import Path

        from cop_worker.reliability.durable_io import _sync_directory

        # This test just verifies it doesn't raise on Windows
        if os.name == "nt":
            _sync_directory(Path("."))  # should return without error

    def test_persistence_error_is_oserror(self):
        from cop_worker.reliability.durable_io import PersistenceError

        err = PersistenceError("test error")
        assert isinstance(err, OSError)
