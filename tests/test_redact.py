import logging

from ai_assistant.redact import RedactFilter, last4, redact


def test_redact_strips_common_secrets() -> None:
    text = "bearer sk-abc123456789 and sk-ant-api03-abcdefghijklmnopqrstuvwxyz and AIzaSyA1234567890123456789012"
    cleaned = redact(text)
    assert "sk-abc" not in cleaned
    assert "sk-ant-" not in cleaned
    assert "AIza" not in cleaned
    assert "[redacted]" in cleaned


def test_redact_filter_scrubs_log_records() -> None:
    record = logging.LogRecord(
        name="ai",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="header Authorization: Bearer %s",
        args=("sk-live-secret-value-1234",),
        exc_info=None,
    )
    assert RedactFilter().filter(record) is True
    rendered = record.getMessage()
    assert "sk-live-secret-value-1234" not in rendered
    assert "Bearer" not in rendered or "[redacted]" in rendered


def test_last4_hides_short_values() -> None:
    assert last4("") == ""
    assert last4("short") == ""
    assert last4("sk-test-1234abcd") == "abcd"
