import pytest

from app.oauth import base as oauth_base


def test_round_trip(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "shhh")
    state = oauth_base.sign_state("node-1", "owner-1")
    node_id, owner_id = oauth_base.verify_state(state)
    assert node_id == "node-1"
    assert owner_id == "owner-1"


def test_tampered_state_fails(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "shhh")
    state = oauth_base.sign_state("node-1", "owner-1")
    payload_b64, sig = state.split(".", 1)
    tampered = f"{payload_b64}x.{sig}"
    with pytest.raises(oauth_base.InvalidStateError):
        oauth_base.verify_state(tampered)


def test_expired_state_fails(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "shhh")
    monkeypatch.setattr(oauth_base, "STATE_TTL_SECONDS", -1)
    state = oauth_base.sign_state("node-1", "owner-1")
    with pytest.raises(oauth_base.InvalidStateError):
        oauth_base.verify_state(state)


def test_wrong_secret_fails(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "shhh")
    state = oauth_base.sign_state("node-1", "owner-1")
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "different")
    with pytest.raises(oauth_base.InvalidStateError):
        oauth_base.verify_state(state)


def test_verify_requires_secret(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "")
    with pytest.raises(RuntimeError, match="OAUTH_STATE_SECRET"):
        oauth_base.verify_state("whatever.whatever")


def test_sign_requires_secret(monkeypatch):
    monkeypatch.setattr(oauth_base.settings, "oauth_state_secret", "")
    with pytest.raises(RuntimeError, match="OAUTH_STATE_SECRET"):
        oauth_base.sign_state("node-1", "owner-1")
