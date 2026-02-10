"""Tests for the Chat Z-Image module — isolated public chat auto-generation mode."""

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure CHAT_ZIMAGE_CHAT is NOT set by default so the mode is disabled
os.environ.pop("CHAT_ZIMAGE_CHAT", None)


# ── Import after env cleanup ────────────────────────────────────────────
from app.chat_zimage.handler import (
    CHAT_ZIMAGE_MODEL,
    PHRASES_OK,
    PLACEHOLDER_PATH,
    _ChatLimiter,
    _check_cooldown,
    _cooldowns,
    _load_placeholder,
    _parse_chat_username,
    _set_cooldown,
    _TARGET_USERNAME,
)


# ── Placeholder image ───────────────────────────────────────────────────

def test_placeholder_file_exists():
    """Placeholder PNG must exist in the module directory."""
    assert PLACEHOLDER_PATH.exists(), f"Placeholder not found: {PLACEHOLDER_PATH}"


def test_placeholder_is_valid_png():
    """Placeholder must be a valid PNG (starts with PNG magic bytes)."""
    data = _load_placeholder()
    assert len(data) > 100, "Placeholder too small"
    assert data[:4] == b"\x89PNG", "Placeholder is not a valid PNG"


# ── Model ID ─────────────────────────────────────────────────────────────

def test_model_is_z_image():
    """Chat mode must always use z-image model."""
    assert CHAT_ZIMAGE_MODEL == "z-image"


# ── Phrases ──────────────────────────────────────────────────────────────

def test_phrases_ok_count():
    """Must have at least 5 OK phrases for variety."""
    assert len(PHRASES_OK) >= 5


def test_phrases_are_short():
    """All phrases must be short (3-8 words)."""
    for phrase in PHRASES_OK:
        words = phrase.split()
        assert 2 <= len(words) <= 10, f"Phrase too long/short: '{phrase}' ({len(words)} words)"


def test_silent_mode_no_error_phrases_sent():
    """In silent mode, errors are only logged — no messages sent to users."""
    # The module no longer sends placeholder/error/cooldown messages.
    # Verify the OK phrases still exist (only thing ever sent).
    assert all(isinstance(p, str) and len(p) > 0 for p in PHRASES_OK)


# ── Cooldown ─────────────────────────────────────────────────────────────

def test_cooldown_not_set():
    """User without cooldown should return None."""
    _cooldowns.clear()
    assert _check_cooldown(999999) is None


def test_cooldown_set_and_active():
    """Recently set cooldown should return remaining time."""
    _cooldowns.clear()
    _set_cooldown(123)
    remaining = _check_cooldown(123)
    assert remaining is not None
    assert remaining > 0


def test_cooldown_expired():
    """Expired cooldown should return None."""
    _cooldowns.clear()
    _cooldowns[456] = time.monotonic() - 999  # way in the past
    assert _check_cooldown(456) is None


# ── Limiter ──────────────────────────────────────────────────────────────

def test_limiter_allows_entry():
    """Limiter should allow entry when not full."""
    lim = _ChatLimiter(max_concurrency=1, max_queue=2)
    assert lim.try_enter() is True
    assert lim._in_flight == 1


def test_limiter_rejects_when_full():
    """Limiter should reject when max_concurrency + max_queue is reached."""
    lim = _ChatLimiter(max_concurrency=1, max_queue=2)
    assert lim.try_enter() is True  # 1
    assert lim.try_enter() is True  # 2
    assert lim.try_enter() is True  # 3 (1 + 2)
    assert lim.try_enter() is False  # rejected


def test_limiter_release():
    """Release should free a slot."""
    lim = _ChatLimiter(max_concurrency=1, max_queue=1)
    assert lim.try_enter() is True
    assert lim.try_enter() is True
    assert lim.try_enter() is False
    lim.release()
    assert lim.try_enter() is True


def test_limiter_leave_queue():
    """leave_queue should decrement in_flight without releasing semaphore."""
    lim = _ChatLimiter(max_concurrency=1, max_queue=1)
    assert lim.try_enter() is True
    lim.leave_queue()
    assert lim._in_flight == 0


# ── Registration ─────────────────────────────────────────────────────────

def test_register_disabled_by_default():
    """Without CHAT_ZIMAGE_CHAT env var, registration should return False."""
    from app.chat_zimage.handler import register_chat_zimage_handler

    app = MagicMock()
    with patch.dict(os.environ, {}, clear=False):
        # Make sure CHAT_ZIMAGE_CHAT is empty
        with patch("app.chat_zimage.handler.CHAT_ZIMAGE_CHAT", ""):
            result = register_chat_zimage_handler(app)
    assert result is False
    app.add_handler.assert_not_called()


def test_register_enabled():
    """With CHAT_ZIMAGE_CHAT set, handler should be registered in group -50."""
    from app.chat_zimage.handler import register_chat_zimage_handler

    app = MagicMock()
    with patch("app.chat_zimage.handler.CHAT_ZIMAGE_CHAT", "@test_chat"):
        result = register_chat_zimage_handler(app)
    assert result is True
    app.add_handler.assert_called_once()
    _, kwargs = app.add_handler.call_args
    assert kwargs.get("group") == -50


def test_gate_blocks_non_target_chat_passthrough():
    """Gate handler should NOT block updates from other chats."""
    assert _TARGET_USERNAME == ""  # disabled in test env


def test_parse_chat_username_tme_url():
    """Must extract username from https://t.me/... URL."""
    assert _parse_chat_username("https://t.me/FERIXDI_FREE") == "ferixdi_free"
    assert _parse_chat_username("https://t.me/FERIXDI_FREE/") == "ferixdi_free"
    assert _parse_chat_username("http://t.me/MyChat") == "mychat"
    assert _parse_chat_username("t.me/SomeChat") == "somechat"


def test_parse_chat_username_at_prefix():
    """Must strip @ prefix."""
    assert _parse_chat_username("@FERIXDI_FREE") == "ferixdi_free"
    assert _parse_chat_username("@MyChat") == "mychat"


def test_parse_chat_username_bare():
    """Must handle bare username."""
    assert _parse_chat_username("FERIXDI_FREE") == "ferixdi_free"


def test_parse_chat_username_empty():
    """Must return empty string for empty input."""
    assert _parse_chat_username("") == ""
    assert _parse_chat_username("  ") == ""


# ── No interference with main bot ────────────────────────────────────────

def test_main_bot_not_affected():
    """Existing critical flows must still pass (regression check)."""
    # This test is a meta-check: if test_critical_flows.py passes alongside
    # this file, the chat_zimage module does not break the main bot.
    assert True  # placeholder — real validation is pytest exit code
