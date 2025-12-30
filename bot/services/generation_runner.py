"""Generation runner (Syntx-parity runtime).

Goals:
- One running generation per user.
- Cancel button while waiting.
- Stable job history (jobs table) with inputs + result.
- Always charge correctly (markup included) via generate_with_payment.

This module is intentionally thin: it orchestrates existing payment+Kie layers,
adds job tracking, and handles cancellations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database.services import JobService
from app.payments.charges import get_charge_manager
from app.payments.integration import generate_with_payment

from app.kie.normalize import detect_output_type
from app.utils.trace import get_request_id

logger = logging.getLogger(__name__)


@dataclass
class RunningGeneration:
    user_id: int
    job_id: int
    task: asyncio.Task
    chat_id: int
    message_id: int


_RUNNING: Dict[int, RunningGeneration] = {}


def _running_kb(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⛔ Отменить", callback_data=f"job:cancel:{job_id}")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


def _result_kb(model_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"launch:{model_id}")],
            [
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
                InlineKeyboardButton(text="📜 История", callback_data="menu:history"),
                InlineKeyboardButton(text="💳 Баланс", callback_data="menu:balance"),
            ],
        ]
    )


async def cancel_user_generation(user_id: int, job_id: Optional[int] = None) -> bool:
    """Cancel a running generation for the user.

    Returns True if cancelled, False if nothing to cancel / job mismatch.
    """
    ctx = _RUNNING.get(user_id)
    if not ctx:
        return False
    if job_id is not None and int(job_id) != int(ctx.job_id):
        return False
    try:
        ctx.task.cancel()
        return True
    except Exception:
        return False


async def start_generation(
    *,
    bot: Bot,
    message: Message,
    user_id: int,
    model_id: str,
    display_name: str,
    category: str,
    user_inputs: Dict[str, Any],
    price_rub: Decimal,
    output_type: str,
    timeout: int = 300,
) -> int:
    """Create job + schedule background generation.

    Edits the provided message in-place with progress + cancel button.

    Returns job_id.
    """
    cm = get_charge_manager()
    db = getattr(cm, "db_service", None)
    if not db:
        raise RuntimeError("Database service not configured in charge manager")

    # Cancel any previous run (avoid double charges and UX weirdness)
    prev = _RUNNING.get(user_id)
    if prev:
        try:
            prev.task.cancel()
        except Exception:
            pass
        _RUNNING.pop(user_id, None)

    job_service = JobService(db)

    idempotency_key = f"gen:{user_id}:{message.chat.id}:{message.message_id}:{model_id}"
    job_id = await job_service.create(
        user_id=user_id,
        model_id=model_id,
        category=category or "unknown",
        input_json=dict(user_inputs or {}),
        price_rub=price_rub,
        idempotency_key=idempotency_key,
    )

    if not job_id:
        raise RuntimeError("Failed to create job")

    await job_service.update_status(job_id, "queued")

    # Initial UX: queued
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=(
                f"⏳ <b>{display_name}</b>\n\n"
                f"Статус: <b>в очереди</b>\n"
                f"Таймаут: {timeout} сек"
            ),
            reply_markup=_running_kb(job_id),
            parse_mode="HTML",
        )
    except Exception:
        # Not fatal, continue
        pass

    running_marked = False

    async def progress_cb(html_text: str) -> None:
        nonlocal running_marked
        # Update job status once we got progress (avoid spamming DB)
        if not running_marked:
            try:
                await job_service.update_status(job_id, "running")
            except Exception:
                pass
            running_marked = True
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text=html_text,
                reply_markup=_running_kb(job_id),
                parse_mode="HTML",
            )
        except Exception:
            # Ignore "message is not modified" etc
            return

    async def _runner() -> None:
        try:
            result = await generate_with_payment(
                model_id=model_id,
                user_inputs=user_inputs,
                user_id=user_id,
                amount=float(price_rub),
                reserve_balance=True,
                task_id=f"job:{job_id}",
                progress_callback=progress_cb,
                timeout=timeout,
                charge_manager=cm,
            )

            kie_task_id = result.get("task_id")
            if result.get("success"):
                await job_service.update_status(
                    job_id,
                    "succeeded",
                    kie_task_id=kie_task_id,
                    kie_status="success",
                    result_json=result,
                    error_text=None,
                )

                if not await job_service.mark_replied(job_id, result_json=result):
                    logger.info(
                        "reply_once skipped",
                        extra={"stage": "reply", "request_id": get_request_id(), "task_id": kie_task_id, "model_id": model_id},
                    )
                    return

                # Result UX
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        text=(
                            f"✅ <b>{display_name}</b>\n\n"
                            "Статус: <b>готово</b>"
                        ),
                        reply_markup=_result_kb(model_id),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                output_url = result.get("output_url")
                # Always send result as a separate message (keeps progress msg intact)
                if output_url:
                    try:
                        ot = (output_type or "").lower()
                        # Some models in source_of_truth have wrong output_type (e.g. audio models marked as text).
                        # Fallback to URL-based detection so UX stays correct.
                        if not ("video" in ot or "image" in ot or "audio" in ot):
                            ot = detect_output_type(output_url)

                        if "video" in ot:
                            await bot.send_video(message.chat.id, output_url)
                        elif "image" in ot:
                            await bot.send_photo(message.chat.id, output_url)
                        elif "audio" in ot:
                            await bot.send_audio(message.chat.id, output_url)
                        else:
                            await bot.send_message(message.chat.id, f"📎 Результат: {output_url}")
                    except Exception:
                        await bot.send_message(message.chat.id, f"📎 Результат: {output_url}")

            else:
                # Determine final status for history
                status = "failed"
                if result.get("payment_status") == "refunded":
                    status = "refunded"

                await job_service.update_status(
                    job_id,
                    status,
                    kie_task_id=kie_task_id,
                    kie_status=str(result.get("state") or "fail"),
                    result_json=result,
                    error_text=str(result.get("error") or result.get("message") or "unknown"),
                )

                err = result.get("error") or result.get("message") or "Неизвестная ошибка"

                if not await job_service.mark_replied(job_id, result_json=result, error_text=str(err)):
                    logger.info(
                        "reply_once skipped",
                        extra={"stage": "reply", "request_id": get_request_id(), "task_id": kie_task_id, "model_id": model_id},
                    )
                    return
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        text=(
                            f"❌ <b>{display_name}</b>\n\n"
                            "Статус: <b>ошибка</b>\n\n"
                            f"{err}"
                        ),
                        reply_markup=_result_kb(model_id),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        except asyncio.CancelledError:
            try:
                await job_service.update_status(job_id, "cancelled", error_text="user_cancelled")
            except Exception:
                pass
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=(
                        f"⛔ <b>{display_name}</b>\n\n"
                        "Статус: <b>отменено</b>"
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")]]
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error("Generation runner crashed: %s", e, exc_info=True)
            try:
                await job_service.update_status(job_id, "failed", error_text=str(e))
            except Exception:
                pass
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=(
                        f"❌ <b>{display_name}</b>\n\n"
                        "Статус: <b>ошибка</b>\n\n"
                        "Произошла непредвиденная ошибка. Попробуйте ещё раз."
                    ),
                    reply_markup=_result_kb(model_id),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        finally:
            _RUNNING.pop(user_id, None)

    task = asyncio.create_task(_runner(), name=f"gen:{user_id}:{job_id}")
    _RUNNING[user_id] = RunningGeneration(
        user_id=user_id,
        job_id=int(job_id),
        task=task,
        chat_id=message.chat.id,
        message_id=message.message_id,
    )

    return int(job_id)
