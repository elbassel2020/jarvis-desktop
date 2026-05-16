"""Credential broker round-trip tests."""
import pytest
import re
from pathlib import Path
from jarvis.security.credential_broker import (
    CredentialBroker, broker, redact_secrets_in_text, CredentialBrokerError
)


@pytest.fixture
def test_broker():
    b = CredentialBroker()
    yield b
    # Cleanup test credentials
    b.delete("test_service", "test_account")
    b.delete("test_service", "long_account")


def test_store_and_resolve(test_broker):
    handle = test_broker.store("test_service", "test_account", "secret_value_123")
    assert handle == "cred://test_service/test_account"
    assert test_broker.resolve(handle) == "secret_value_123"


def test_long_token_wrapped(test_broker):
    long_secret = "x" * 5000  # >2.5KB
    handle = test_broker.store("test_service", "long_account", long_secret)
    resolved = test_broker.resolve(handle)
    assert resolved == long_secret


def test_invalid_handle_format(test_broker):
    with pytest.raises(CredentialBrokerError):
        test_broker.resolve("not_a_valid_handle")
    with pytest.raises(CredentialBrokerError):
        test_broker.resolve("cred://Invalid_Service/account")  # uppercase


def test_missing_credential_raises(test_broker):
    with pytest.raises(CredentialBrokerError):
        test_broker.resolve("cred://nonexistent/account")


def test_redact_secrets_in_text():
    text = "API key sk-abc123def456ghi789jkl012 is here"
    redacted = redact_secrets_in_text(text)
    assert "sk-abc123" not in redacted
    assert "[REDACTED]" in redacted


def test_log_file_no_secrets(test_broker, tmp_path):
    """The credential access log should never contain secret values."""
    test_broker.store("test_service", "test_account", "MY_SUPER_SECRET_VALUE_XYZ")
    test_broker.resolve("cred://test_service/test_account")

    log_path = Path(__file__).parent.parent / "logs" / "credential_access.log"
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        assert "MY_SUPER_SECRET_VALUE_XYZ" not in content


def test_handle_namespace_isolation():
    """Different accounts under same service should not collide."""
    broker.store("test_service", "account_a", "value_a")
    broker.store("test_service", "account_b", "value_b")
    assert broker.resolve("cred://test_service/account_a") == "value_a"
    assert broker.resolve("cred://test_service/account_b") == "value_b"
    broker.delete("test_service", "account_a")
    broker.delete("test_service", "account_b")
