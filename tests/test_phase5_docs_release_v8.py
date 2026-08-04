"""Phase 5 v8 tests: documentation truthfulness, version consistency, CLI correctness."""

from __future__ import annotations

from pathlib import Path


class TestVersionConsistency:
    def test_pyproject_and_agent_version_match(self):
        """pyproject.toml version must match agent/version.py."""
        import tomllib

        with open("pyproject.toml", "rb") as f:
            pyproject = tomllib.load(f)
        pyproject_version = pyproject["project"]["version"]

        from agent.version import __version__

        assert pyproject_version == __version__, (
            f"pyproject.toml version {pyproject_version!r} != agent/version.py {__version__!r}"
        )

    def test_version_is_3_0_0(self):
        """Package version should be 3.0.0 for this submission."""
        from agent.version import __version__

        assert __version__ == "3.0.0", f"Expected 3.0.0, got {__version__!r}"


class TestReadmeCliAccuracy:
    def test_readme_uses_thief_url_not_cop_url(self):
        """README must not contain the incorrect --cop-url option name."""
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "--cop-url" not in readme, (
            "README still contains --cop-url; should be --thief-url (cop drives the game "
            "and connects TO the thief's MCP endpoint)"
        )

    def test_readme_mentions_thief_url(self):
        """README must document --thief-url as the CLI option."""
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "--thief-url" in readme, "README should document --thief-url option"

    def test_run_series_has_thief_url_argument(self):
        """scripts/run_series.py must define --thief-url argument."""
        script = Path("scripts/run_series.py").read_text(encoding="utf-8")
        assert "--thief-url" in script, "run_series.py must expose --thief-url argument"
        assert "--cop-url" not in script, (
            "run_series.py must not have --cop-url (the cop IS the active driver)"
        )

    def test_readme_mentions_runtime_modes(self):
        """README must document all three RuntimeMode values."""
        readme = Path("README.md").read_text(encoding="utf-8")
        for mode in ("counted", "warmup", "development"):
            assert mode.lower() in readme.lower(), f"README must mention RuntimeMode.{mode.upper()}"


class TestProductionArchitectureDocs:
    def test_readme_mentions_composition_root(self):
        """README must describe AgentOrchestrator as the single composition root."""
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "AgentOrchestrator" in readme

    def test_readme_mentions_dec_pomdp(self):
        """README must describe the Dec-POMDP information model."""
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "Dec-POMDP" in readme or "POMDP" in readme

    def test_readme_mentions_local_observation(self):
        """README must state that opponent true position is hidden."""
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "hidden" in readme.lower() or "local_observation" in readme.lower()

    def test_readme_acknowledges_external_pending(self):
        """README must honestly acknowledge EXTERNAL_PENDING items."""
        readme = Path("README.md").read_text(encoding="utf-8")
        assert "EXTERNAL_PENDING" in readme or "pending" in readme.lower()

    def test_known_deviations_exists(self):
        """docs/KNOWN_DEVIATIONS.md must exist for honest reporting."""
        assert Path("docs/KNOWN_DEVIATIONS.md").exists()

    def test_requirements_traceability_exists(self):
        """docs/REQUIREMENTS_TRACEABILITY.md must exist."""
        assert Path("docs/REQUIREMENTS_TRACEABILITY.md").exists()


class TestVerificationManifest:
    def test_manifest_exists_and_valid_json(self):
        """results/verification_manifest.json must be valid JSON."""
        import json

        manifest_path = Path("results/verification_manifest.json")
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert "cop_sha" in data
        assert "cop_tests" in data
        assert isinstance(data["cop_tests"], int)
        assert data["cop_tests"] > 1000

    def test_manifest_version_is_current(self):
        """Manifest package_version must match pyproject.toml."""
        import json
        import tomllib

        manifest = json.loads(Path("results/verification_manifest.json").read_text())
        with open("pyproject.toml", "rb") as f:
            pyproject = tomllib.load(f)
        assert manifest.get("package_version") == pyproject["project"]["version"]


class TestSafetyNoHiddenCoordInSafeLiveView:
    def test_safe_live_view_has_no_opponent_position_field(self):
        """SafeLiveView must not expose opponent_position."""
        import dataclasses

        from agent.observation import SafeLiveView

        fields = {f.name for f in dataclasses.fields(SafeLiveView)}
        forbidden = {"opponent_position", "cop_position", "thief_position"}
        leaked = forbidden & fields
        assert not leaked, f"SafeLiveView leaks hidden fields: {leaked}"

    def test_local_observation_has_no_opponent_position_field(self):
        """LocalObservation must not expose opponent_position."""
        import dataclasses

        from agent.observation import LocalObservation

        fields = {f.name for f in dataclasses.fields(LocalObservation)}
        forbidden = {"opponent_position", "cop_position", "thief_position"}
        leaked = forbidden & fields
        assert not leaked, f"LocalObservation leaks hidden fields: {leaked}"
