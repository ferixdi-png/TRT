from app.observability.redaction import redact_payload


def test_recordinfo_redaction():
    payload = {
        "taskId": "123",
        "resultUrls": ["https://example.com/file.png?token=secret"],
        "authorization": "Bearer abc",
        "nested": {"api_key": "secret", "detail": "ok"},
    }

    redacted = redact_payload(payload)

    assert redacted["resultUrls"][0] == "https://example.com/file.png"
    assert redacted["authorization"] == "***"
    assert redacted["nested"]["api_key"] == "***"
