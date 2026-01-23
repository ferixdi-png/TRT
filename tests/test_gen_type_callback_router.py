import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


@pytest.mark.asyncio
async def test_gen_type_callback_does_not_crash(monkeypatch):
    from bot_kie import button_callback

    update = Mock()
    update.update_id = 123
    update.effective_user = Mock()
    update.effective_user.id = 111
    update.effective_chat = Mock()
    update.effective_chat.id = 222

    query = Mock()
    query.id = "cbq_1"
    query.data = "gen_type:text-to-video"
    query.from_user = Mock()
    query.from_user.id = 111
    query.message = Mock()
    query.message.chat_id = 222
    query.message.message_id = 333
    query.message.reply_text = AsyncMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = Mock()
    context.bot = Mock()
    context.user_data = {}

    async def _stub_render_gen_type_menu(*args, **kwargs):
        return None

    monkeypatch.setattr("bot_kie._render_gen_type_menu", _stub_render_gen_type_menu)

    await button_callback(update, context)
