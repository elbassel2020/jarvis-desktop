"""Test identity invariants are loadable and complete."""
import yaml
from pathlib import Path

IDENTITY_PATH = Path(__file__).parent.parent / "safety" / "identity.yaml"


def test_identity_file_exists():
    assert IDENTITY_PATH.exists(), "safety/identity.yaml must exist"


def test_identity_has_required_keys():
    data = yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8"))
    assert "identity" in data
    assert "invariants" in data
    assert "allowed_third_parties" in data
    assert "risk_levels" in data


def test_identity_user_is_walid():
    data = yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8"))
    assert "Walid" in data["identity"]["user"]


def test_invariants_count():
    data = yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8"))
    assert len(data["invariants"]) >= 5


def test_no_dangerous_third_parties():
    data = yaml.safe_load(IDENTITY_PATH.read_text(encoding="utf-8"))
    dangerous = ["facebook.com", "tiktok.com", "unknown.com"]
    for tp in data["allowed_third_parties"]:
        assert tp not in dangerous, f"Suspicious third party: {tp}"
