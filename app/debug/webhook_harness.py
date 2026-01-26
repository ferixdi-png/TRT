from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web
from telegram import Message

import main_render
from app.config import Settings, reset_settings
from app.session_store import get_session_store
from bot_kie import create_bot_application


@dataclass
class WebhookOutbox:
    messages: List[Dict[str, Any]] = field(default_factory=list)
    edited_messages: List[Dict[str, Any]] = field(default_factory=list)
    callback_answers: List[Dict[str, Any]] = field(default_factory=list)


class WebhookHarness:
    def __init__(self) -> None:
        self.application = None
        self.handler = None
        self.outbox = WebhookOutbox()
        self.session_store = None
        self._message_id_counter = 1000
        self.settings = None

    def _next_message_id(self) -> int:
        self._message_id_counter += 1
        return self._message_id_counter

    async def setup(self) -> None:
        reset_settings()
        self.settings = Settings()
        self.application = await create_bot_application(self.settings)
        await self.application.initialize()

        main_render._app_ready_event.set()
        object.__setattr__(self.application.bot, "_initialized", True)
        object.__setattr__(self.application.bot, "_bot_user", MagicMock(username="test_bot"))

        async def mock_send_message(chat_id, text, **kwargs):
            message_id = self._next_message_id()
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": kwargs.get("parse_mode"),
                "reply_markup": kwargs.get("reply_markup"),
            }
            self.outbox.messages.append(payload)
            mock_msg = MagicMock(spec=Message)
            mock_msg.chat_id = chat_id
            mock_msg.message_id = message_id
            mock_msg.text = text
            mock_msg.reply_markup = kwargs.get("reply_markup")
            return mock_msg

        async def mock_edit_message_text(chat_id=None, message_id=None, text=None, **kwargs):
            resolved_message_id = message_id or self._next_message_id()
            payload = {
                "chat_id": chat_id,
                "message_id": resolved_message_id,
                "text": text,
                "parse_mode": kwargs.get("parse_mode"),
                "reply_markup": kwargs.get("reply_markup"),
            }
            self.outbox.edited_messages.append(payload)
            mock_msg = MagicMock(spec=Message)
            mock_msg.chat_id = chat_id
            mock_msg.message_id = resolved_message_id
            mock_msg.text = text
            mock_msg.reply_markup = kwargs.get("reply_markup")
            return mock_msg

        async def mock_answer_callback_query(callback_query_id, text=None, show_alert=False, **kwargs):
            self.outbox.callback_answers.append(
                {
                    "callback_query_id": callback_query_id,
                    "text": text,
                    "show_alert": show_alert,
                }
            )
            return True

        for name, fn in {
            "send_message": mock_send_message,
            "edit_message_text": mock_edit_message_text,
            "answer_callback_query": mock_answer_callback_query,
            "send_photo": mock_send_message,
            "send_video": mock_send_message,
            "send_audio": mock_send_message,
            "send_document": mock_send_message,
        }.items():
            object.__setattr__(self.application.bot, name, AsyncMock(side_effect=fn))

        main_render._seen_update_ids.clear()
        self.handler = main_render.build_webhook_handler(self.application, self.settings)
        self.session_store = get_session_store(application=self.application)
        import bot_kie

        bot_kie.user_sessions = self.session_store
        bot_kie.generation_submit_locks.clear()

    async def teardown(self) -> None:
        if self.application:
            await self.application.shutdown()
        self.outbox = WebhookOutbox()
        main_render._app_ready_event.clear()
        self.application = None
        self.handler = None
        try:
            import bot_kie

            bot_kie.generation_submit_locks.clear()
        except Exception:
            pass

    async def _send_payload(self, payload: Dict[str, Any], *, request_id: str) -> web.StreamResponse:
        self.handler = main_render.build_webhook_handler(self.application, self.settings)
        request = MagicMock(spec=web.Request)
        request.headers = {"X-Request-ID": request_id}
        request.method = "POST"
        request.path = "/webhook"
        request.content_length = len(json.dumps(payload))
        request.json = AsyncMock(return_value=payload)
        response = await self.handler(request)
        await asyncio.sleep(0)
        return response

    async def send_message(
        self,
        *,
        user_id: int,
        text: str,
        update_id: int,
        chat_id: Optional[int] = None,
        message_id: int = 1,
        request_id: str = "corr-webhook-test",
    ) -> web.StreamResponse:
        payload = {
            "update_id": update_id,
            "message": {
                "message_id": message_id,
                "date": 0,
                "chat": {"id": chat_id or user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
                "text": text,
            },
        }
        return await self._send_payload(payload, request_id=request_id)

    async def send_callback(
        self,
        *,
        user_id: int,
        callback_data: str,
        update_id: int,
        message_id: int = 1,
        chat_id: Optional[int] = None,
        request_id: str = "corr-webhook-test",
    ) -> web.StreamResponse:
        payload = {
            "update_id": update_id,
            "callback_query": {
                "id": f"cbq-{update_id}",
                "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
                "message": {
                    "message_id": message_id,
                    "date": 0,
                    "chat": {"id": chat_id or user_id, "type": "private"},
                    "text": "callback",
                },
                "data": callback_data,
                "chat_instance": "test-instance",
            },
        }
        return await self._send_payload(payload, request_id=request_id)
