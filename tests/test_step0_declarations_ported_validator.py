"""Tests for the Step-0 counted-mode declaration validator."""

from cop_worker.step0.validator import validate_for_counted_mode
from tests.helpers_step0_declarations import _valid_decl

# ---------------------------------------------------------------------------
# validate_for_counted_mode
# ---------------------------------------------------------------------------


def test_validate_counted_mode_valid():
    errors = validate_for_counted_mode(_valid_decl())
    assert errors == []


def test_validate_counted_mode_rejects_empty_git_sha():
    decl = _valid_decl()
    decl.git_sha = ""
    errors = validate_for_counted_mode(decl)
    assert any("git_sha" in e for e in errors)


def test_validate_counted_mode_rejects_placeholder_git_sha():
    decl = _valid_decl()
    decl.git_sha = "placeholder"
    errors = validate_for_counted_mode(decl)
    assert any("git_sha" in e for e in errors)


def test_validate_counted_mode_rejects_unknown_git_sha():
    decl = _valid_decl()
    decl.git_sha = "unknown"
    errors = validate_for_counted_mode(decl)
    assert any("git_sha" in e for e in errors)


def test_validate_counted_mode_rejects_bad_length_group_id():
    decl = _valid_decl()
    decl.group_id = "SHORT"
    errors = validate_for_counted_mode(decl)
    assert any("group_id" in e for e in errors)


def test_validate_counted_mode_rejects_placeholder_group_id():
    decl = _valid_decl()
    decl.group_id = "XXXXXXXX"
    errors = validate_for_counted_mode(decl)
    assert any("placeholder" in e.lower() for e in errors)


def test_validate_counted_mode_rejects_empty_model_sha():
    decl = _valid_decl()
    decl.model_sha256 = ""
    errors = validate_for_counted_mode(decl)
    assert any("model_sha256" in e for e in errors)


def test_validate_counted_mode_rejects_placeholder_model_sha():
    decl = _valid_decl()
    decl.model_sha256 = "placeholder"
    errors = validate_for_counted_mode(decl)
    assert any("model_sha256" in e for e in errors)


def test_validate_counted_mode_rejects_missing_canonical_config():
    decl = _valid_decl()
    decl.canonical_config_sha256 = ""
    errors = validate_for_counted_mode(decl)
    assert any("canonical_config_sha256" in e for e in errors)


def test_validate_counted_mode_rejects_missing_scent_hash():
    decl = _valid_decl()
    decl.scent_model_hash = ""
    errors = validate_for_counted_mode(decl)
    assert any("scent_model_hash" in e for e in errors)
