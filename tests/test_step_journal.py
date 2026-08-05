"""Basic StepJournal unit tests."""

from __future__ import annotations

from agent.audit.step_journal import StepEvidence, StepJournal


def _ev(step: int, role: str = "cop") -> StepEvidence:
    return StepEvidence(
        game_uid="g-001",
        gamelet=1,
        step=step,
        role=role,
        local_commitment=f"c{step}",
        local_nonce=f"n{step}",
        local_move=f"m{step}",
    )


def test_empty_journal_transcript_root(tmp_path):
    """Empty journal transcript root equals genesis hash."""
    j = StepJournal(str(tmp_path / "j.json"))
    assert j.transcript_root() == j._genesis_hash


def test_append_and_read(tmp_path):
    """Append entries and read them back."""
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    j.append(_ev(2))
    j.append(_ev(3))
    assert len(j.entries) == 3
    assert j.entries[0].step == 1
    assert j.entries[2].local_move == "m3"


def test_transcript_root_changes_on_append(tmp_path):
    """Transcript root should change with each append."""
    j = StepJournal(str(tmp_path / "j.json"))
    root0 = j.transcript_root()
    j.append(_ev(1))
    root1 = j.transcript_root()
    j.append(_ev(2))
    root2 = j.transcript_root()

    assert root0 != root1
    assert root1 != root2
    assert root0 != root2


def test_load_from_file_round_trip(tmp_path):
    """Write to file, load back, chain verifies and data matches."""
    p = tmp_path / "journal.json"

    # Write
    j1 = StepJournal(str(p))
    j1.append(_ev(1))
    j1.append(_ev(2))
    saved_root = j1.transcript_root()

    # Load
    j2 = StepJournal(str(p))
    ok, msg = j2.verify_chain()
    assert ok, f"Reloaded chain should verify: {msg}"
    assert j2.transcript_root() == saved_root
    assert j2.entries[0].local_nonce == "n1"
    assert j2.entries[1].local_nonce == "n2"


def test_append_returns_hash(tmp_path):
    """append() should return the hash for the new entry."""
    j = StepJournal(str(tmp_path / "j.json"))
    h = j.append(_ev(1))
    assert isinstance(h, str)
    assert len(h) == 64  # SHA-256 hex
    assert h == j.transcript_root()


def test_entries_is_a_copy(tmp_path):
    """entries property returns a copy, not the internal list."""
    j = StepJournal(str(tmp_path / "j.json"))
    j.append(_ev(1))
    entries = j.entries
    entries.clear()  # modifying the returned list
    assert len(j.entries) == 1  # internal list unchanged


def test_journal_creates_parent_dirs(tmp_path):
    """StepJournal creates parent directories on first write."""
    nested = tmp_path / "a" / "b" / "c" / "journal.json"
    j = StepJournal(str(nested))
    j.append(_ev(1))
    assert nested.exists()
