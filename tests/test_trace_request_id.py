from app.utils.trace import TraceContext, get_request_id


def test_get_request_id_generates_hex_when_missing_context():
    rid = get_request_id()

    assert rid != "-"
    assert len(rid) == 12
    int(rid, 16)

    # Subsequent calls should reuse the same generated id until context changes
    assert get_request_id() == rid


def test_get_request_id_respects_trace_context():
    with TraceContext(request_id="trace-123", user_id=1, model_id="m1"):
        assert get_request_id() == "trace-123"
