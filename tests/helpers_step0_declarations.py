"""Shared declaration factories for the Step-0 declaration test modules."""

from cop_worker.step0.declaration import PeerDeclaration


def _make_decl(**overrides) -> PeerDeclaration:
    defaults = {"game_uid": "game-001"}
    defaults.update(overrides)
    return PeerDeclaration(**defaults)


def _valid_decl() -> PeerDeclaration:
    return _make_decl(
        git_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        group_id="AB123456",
        model_sha256="sha256ofmodel",
        canonical_config_sha256="sha256ofconfig",
        scent_model_hash="sha256ofscent",
    )
