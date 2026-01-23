from types import SimpleNamespace

from app.session_store import SessionStore, ensure_session_cached, get_session_cached, get_session_get_count


def test_session_cache_single_fetch_per_update():
    store = SessionStore({123: {"model_id": "z-image"}})
    context = SimpleNamespace(user_data={})

    session_first = get_session_cached(context, store, 123, update_id=99, default=None)
    session_second = get_session_cached(context, store, 123, update_id=99, default=None)

    assert session_first is session_second
    assert get_session_get_count(context, 99) == 1


def test_session_cache_counts_ensure_after_miss():
    store = SessionStore({})
    context = SimpleNamespace(user_data={})

    session_first = get_session_cached(context, store, 999, update_id=101, default=None)
    assert session_first is None

    session_ensured = ensure_session_cached(context, store, 999, update_id=101)
    assert session_ensured == {}
    assert get_session_get_count(context, 101) == 2


def test_session_cache_out_of_order_update_does_not_override_cache():
    store = SessionStore({123: {"model_id": "z-image"}})
    context = SimpleNamespace(user_data={})

    session_first = get_session_cached(context, store, 123, update_id=200, default=None)
    assert session_first["model_id"] == "z-image"

    store.set(123, {"model_id": "new"})

    session_out_of_order = get_session_cached(context, store, 123, update_id=150, default=None)
    assert session_out_of_order["model_id"] == "new"
    cache = context.user_data.get("_session_cache")
    assert cache["update_id"] == 200
    assert context.user_data.get("_session_last_update_id") == 200
