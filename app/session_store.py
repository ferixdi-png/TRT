"""
SessionStore: единый источник правды для runtime session state.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_SESSION_DATA: Dict[int, Dict[str, Any]] = {}


class SessionStore:
    """Thin wrapper around session dict with structured logging."""

    def __init__(self, store: Dict[int, Dict[str, Any]]):
        self._store = store

    @property
    def data(self) -> Dict[int, Dict[str, Any]]:
        return self._store

    def __contains__(self, user_id: int) -> bool:
        return user_id in self._store

    def __getitem__(self, user_id: int) -> Dict[str, Any]:
        if user_id in self._store:
            session = self._store[user_id]
            self._log("SESSION_GET", user_id, session)
            return session
        self._log("SESSION_MISS", user_id, None)
        raise KeyError(user_id)

    def __setitem__(self, user_id: int, session: Dict[str, Any]) -> None:
        self._store[user_id] = session
        self._log("SESSION_SET", user_id, session)

    def __delitem__(self, user_id: int) -> None:
        self.clear(user_id)

    def __len__(self) -> int:
        return len(self._store)

    def __iter__(self):
        return iter(self._store)

    def get(self, user_id: int, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        session = self._store.get(user_id, default)
        if session is None or session is default:
            self._log("SESSION_MISS", user_id, None)
        else:
            self._log("SESSION_GET", user_id, session)
        return session

    def set(self, user_id: int, session: Dict[str, Any]) -> Dict[str, Any]:
        self._store[user_id] = session
        self._log("SESSION_SET", user_id, session)
        return session

    def ensure(self, user_id: int) -> Dict[str, Any]:
        session = self._store.get(user_id)
        if session is None:
            session = {}
            self._store[user_id] = session
            self._log("SESSION_SET", user_id, session)
        else:
            self._log("SESSION_GET", user_id, session)
        return session

    def clear(self, user_id: int) -> None:
        if user_id in self._store:
            self._store.pop(user_id, None)
            self._log("SESSION_SET", user_id, {})
        else:
            self._log("SESSION_MISS", user_id, None)

    def pop(self, user_id: int, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        session = self._store.pop(user_id, default)
        if session is default or session is None:
            self._log("SESSION_MISS", user_id, None)
        else:
            self._log("SESSION_SET", user_id, {})
        return session

    def setdefault(self, user_id: int, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if user_id in self._store:
            session = self._store[user_id]
            self._log("SESSION_GET", user_id, session)
            return session
        session = default if isinstance(default, dict) else {}
        self._store[user_id] = session
        self._log("SESSION_SET", user_id, session)
        return session

    def keys(self):
        return self._store.keys()

    def items(self):
        return self._store.items()

    def values(self):
        return self._store.values()

    def snapshot(self, user_id: Optional[int]) -> Dict[str, Any]:
        if user_id is None:
            return {}
        session = self._store.get(user_id)
        if not isinstance(session, dict):
            return {}
        return {
            "keys": list(session.keys()),
            "waiting_for": session.get("waiting_for"),
            "current_param": session.get("current_param"),
            "model_id": session.get("model_id"),
        }

    def _log(self, action: str, user_id: int, session: Optional[Dict[str, Any]]) -> None:
        keys = list(session.keys()) if isinstance(session, dict) else None
        waiting_for = session.get("waiting_for") if isinstance(session, dict) else None
        current_param = session.get("current_param") if isinstance(session, dict) else None
        model_id = session.get("model_id") if isinstance(session, dict) else None
        logger.info(
            "%s user_id=%s keys=%s waiting_for=%s current_param=%s model_id=%s",
            action,
            user_id,
            keys,
            waiting_for,
            current_param,
            model_id,
        )


_SESSION_STORE = SessionStore(_DEFAULT_SESSION_DATA)

_SESSION_CACHE_KEY = "_session_cache"


def get_session_store(context: Any | None = None, application: Any | None = None) -> SessionStore:
    """Return SessionStore from deps if available, otherwise fallback to module store."""
    app = application or getattr(context, "application", None)
    deps = None
    if app is not None:
        deps = getattr(app, "bot_data", {}).get("deps")
    store = getattr(deps, "user_sessions", None) if deps is not None else None
    if isinstance(store, dict):
        return SessionStore(store)
    return _SESSION_STORE


def get_session_cached(
    context: Any | None,
    store: SessionStore,
    user_id: int,
    update_id: int | None,
    default: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch session once per update and cache in context.user_data."""
    if context is None or getattr(context, "user_data", None) is None or update_id is None:
        return store.get(user_id, default)
    cache = context.user_data.get(_SESSION_CACHE_KEY)
    if cache and cache.get("update_id") == update_id and cache.get("user_id") == user_id:
        return cache.get("session", default)
    sentinel = object()
    session = store.get(user_id, sentinel)
    from_store = session is not sentinel
    if not from_store:
        session = default
    context.user_data[_SESSION_CACHE_KEY] = {
        "update_id": update_id,
        "user_id": user_id,
        "session": session,
        "store_gets": 1,
        "from_store": from_store,
    }
    return session


def ensure_session_cached(
    context: Any | None,
    store: SessionStore,
    user_id: int,
    update_id: int | None,
) -> Dict[str, Any]:
    """Ensure session exists, reusing per-update cache."""
    if context is None or getattr(context, "user_data", None) is None or update_id is None:
        return store.ensure(user_id)
    cache = context.user_data.get(_SESSION_CACHE_KEY)
    if cache and cache.get("update_id") == update_id and cache.get("user_id") == user_id:
        session = cache.get("session")
        if isinstance(session, dict) and cache.get("from_store", False):
            return session
    session = store.ensure(user_id)
    store_gets = int(cache.get("store_gets", 0) if cache else 0) + 1
    context.user_data[_SESSION_CACHE_KEY] = {
        "update_id": update_id,
        "user_id": user_id,
        "session": session,
        "store_gets": store_gets,
        "from_store": True,
    }
    return session


def get_session_get_count(context: Any | None, update_id: int | None) -> int:
    """Return number of store gets for the cached update."""
    if context is None or getattr(context, "user_data", None) is None or update_id is None:
        return 0
    cache = context.user_data.get(_SESSION_CACHE_KEY)
    if not cache or cache.get("update_id") != update_id:
        return 0
    return int(cache.get("store_gets", 0))
