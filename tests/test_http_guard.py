"""Egress allowlist tests."""
import pytest
from jarvis.security.http_guard import check_url, EgressDeniedError, _is_allowed


def test_allowed_hosts():
    # Anthropic
    check_url("https://api.anthropic.com/v1/messages")
    # Google
    check_url("https://generativelanguage.googleapis.com/v1/models")
    # Groq
    check_url("https://api.groq.com/openai/v1/audio/transcriptions")
    # ElevenLabs
    check_url("https://api.elevenlabs.io/v1/text-to-speech/xyz")


def test_localhost_always_allowed():
    check_url("http://127.0.0.1:9000/health")
    check_url("http://localhost:8000/api")


def test_disallowed_hosts():
    with pytest.raises(EgressDeniedError):
        check_url("https://evil.com/exfiltrate")
    with pytest.raises(EgressDeniedError):
        check_url("https://facebook.com/api")
    with pytest.raises(EgressDeniedError):
        check_url("https://random-tracker.io/beacon")


def test_subdomain_matching():
    # api.anthropic.com should be allowed via anthropic.com entry
    assert _is_allowed("api.anthropic.com")
    assert _is_allowed("foo.bar.anthropic.com")
    # But evil-anthropic.com should NOT match
    assert not _is_allowed("evil-anthropic.com")
    assert not _is_allowed("anthropic.com.evil.io")


def test_egress_denied_exception_carries_host():
    try:
        check_url("https://bad-host.example/x")
    except EgressDeniedError as e:
        assert e.host == "bad-host.example"
        assert "not in allowlist" in e.reason
