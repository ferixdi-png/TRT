from app.observability.no_silence_guard import NoSilenceGuard


def test_set_trace_context_keyword_only():
    guard = NoSilenceGuard()
    guard.set_trace_context(
        user_id=11,
        chat_id=22,
        update_id=33,
        message_id=44,
        update_type="callback",
        correlation_id="corr-11-22",
        action="TEST",
        stage="UI_ROUTER",
    )

    trace_context = guard.trace_contexts[33]
    assert trace_context["correlation_id"] == "corr-11-22"
    assert trace_context["user_id"] == 11
