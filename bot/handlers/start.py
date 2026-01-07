"""Legacy /start handler shim for smoke tests."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import flow

router = Router(name="start_shim")


@router.message(Command("start"))
async def cmd_start(message: Message, state=None):
    await message.answer("AI Studio: выберите формат", reply_markup=flow._main_menu_keyboard())
