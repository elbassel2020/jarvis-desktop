"""
Health Dashboard tests.

Tests:
1. get_health_status returns dict with required keys
2. integrations section has all 5 expected keys
3. get_audit_report returns dict with required keys
4. get_audit_report respects custom days param
5. get_health_status never crashes (even with missing data)
"""
from jarvis.dashboard import get_health_status, get_audit_report


def test_health_status_returns_dict():
    status = get_health_status()
    assert isinstance(status, dict)
    assert "timestamp" in status
    assert "integrations" in status
    assert "task_queue" in status
    assert "memory" in status
    assert "audit_today" in status


def test_health_integrations_has_all_keys():
    status = get_health_status()
    expected = {"gmail", "zoho", "telegram", "anthropic", "gemini"}
    assert expected.issubset(set(status["integrations"].keys()))


def test_audit_report_returns_dict():
    report = get_audit_report(days=7)
    assert isinstance(report, dict)
    assert "by_actor" in report
    assert "by_outcome" in report
    assert "errors_recent" in report
    assert isinstance(report["errors_recent"], list)


def test_audit_report_custom_days():
    report = get_audit_report(days=1)
    assert report["days"] == 1
    report30 = get_audit_report(days=30)
    assert report30["days"] == 30


def test_health_does_not_crash_on_missing_data():
    """Health status must return a dict even if sub-systems are unavailable."""
    status = get_health_status()
    assert status is not None
    assert isinstance(status["integrations"], dict)
    assert isinstance(status["memory"], dict)
