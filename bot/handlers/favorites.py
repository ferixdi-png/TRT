from __future__ import annotations

from typing import List, Set

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.database.services import ensure_user_exists, get_user_by_id, merge_user_metadata
from app.kie.builder import load_source_of_truth
# (model rendering is done elsewhere; here we keep избранное as a lightweight list)


router = Router()


def _get_favorites(meta: dict | None) -> List[str]:
    if not meta:
        return []
    fav = meta.get("favorites")
    if isinstance(fav, list):
        return [str(x) for x in fav if x]
    return []


async def _set_favorites(user_id: int, favs: List[str]) -> None:
    # Keep deterministic + small
    uniq: List[str] = []
    seen: Set[str] = set()
    for m in favs:
        if m in seen:
            continue
        seen.add(m)
        uniq.append(m)
    await merge_user_metadata(user_id, {"favorites": uniq[:200]})


@router.callback_query(F.data.startswith("fav:add:"))
async def fav_add(callback: CallbackQuery) -> None:
    await callback.answer()
    model_id = callback.data.split(":", 2)[2]
    user_id = callback.from_user.id

    await ensure_user_exists(user_id)
    user = await get_user_by_id(user_id)
    favs = _get_favorites(user.get("metadata") if user else None)
    if model_id not in favs:
        favs.append(model_id)
        await _set_favorites(user_id, favs)

    # Friendly toast
    await callback.answer("⭐ Добавлено в избранное", show_alert=False)


@router.callback_query(F.data.startswith("fav:remove:"))
async def fav_remove(callback: CallbackQuery) -> None:
    await callback.answer()
    model_id = callback.data.split(":", 2)[2]
    user_id = callback.from_user.id

    await ensure_user_exists(user_id)
    user = await get_user_by_id(user_id)
    favs = _get_favorites(user.get("metadata") if user else None)
    favs = [m for m in favs if m != model_id]
    await _set_favorites(user_id, favs)
    await callback.answer("🗑 Убрано из избранного", show_alert=False)


@router.callback_query(F.data == "menu:favorites")
async def favorites_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    await ensure_user_exists(user_id)
    user = await get_user_by_id(user_id)
    favs = _get_favorites(user.get("metadata") if user else None)

    sot = load_source_of_truth()
    models = sot.get("models", {})

    # Filter only existing
    fav_models = [m for m in favs if m in models]

    if not fav_models:
        text = (
            "⭐ <b>Избранное</b>\n\n"
            "Пока пусто. Откройте любую модель и нажмите <b>⭐ В избранное</b>."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]
        ])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        return

    # Render compact list (max 20 per page simple)
    items = fav_models[:20]
    lines = ["⭐ <b>Избранное</b>", ""]
    for mid in items:
        mc = models[mid]
        title = mc.get("title") or mc.get("name") or mid
        lines.append(f"• <b>{title}</b>")
    if len(fav_models) > 20:
        lines.append("")
        lines.append(f"…и ещё {len(fav_models) - 20}")

    kb_rows = []
    for mid in items[:10]:
        mc = models[mid]
        title = mc.get("title") or mc.get("name") or mid
        kb_rows.append([InlineKeyboardButton(text=f"🚀 {title}", callback_data=f"model:{mid}")])

    kb_rows.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main"),
        InlineKeyboardButton(text="🗑 Очистить", callback_data="fav:clear"),
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await callback.message.edit_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "fav:clear")
async def favorites_clear(callback: CallbackQuery) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    await ensure_user_exists(user_id)
    await _set_favorites(user_id, [])
    await callback.answer("✅ Избранное очищено", show_alert=False)
    # Go back to empty state
    await favorites_menu(callback)
