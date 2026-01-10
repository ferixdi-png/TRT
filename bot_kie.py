#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tempfile
from app.utils.validation import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_AUDIO_SIZE,
    MAX_IMAGE_SIZE,
)

    from app.config import get_settings

    settings = get_settings(validate=False)
    BOT_TOKEN = settings.telegram_bot_token
    CONFIG_DATABASE_URL = settings.database_url
    BOT_MODE = settings.bot_mode
    WEBHOOK_BASE_URL = settings.webhook_base_url
    WEBHOOK_URL = settings.webhook_url
    from app.utils.webhook import build_webhook_url, get_webhook_base_url, get_webhook_secret_path
    WEBHOOK_BASE_URL = get_webhook_base_url()
    WEBHOOK_URL = build_webhook_url(WEBHOOK_BASE_URL, get_webhook_secret_path())
            if os.getenv("PORT") and get_webhook_base_url():
def _normalize_extension(ext: str, fallback: str) -> str:
    if not ext:
        return fallback
    if not ext.startswith("."):
        return f".{ext.lower()}"
    return ext.lower()


def _is_extension_allowed(ext: str, allowed: set[str]) -> bool:
    return ext in allowed


def _write_temp_file(data: bytes, suffix: str) -> str:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(data)
    temp_file.flush()
    temp_file.close()
    return temp_file.name


def _cleanup_temp_file(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.unlink(path)
    except Exception as e:
        logger.warning(f"Failed to remove temp file {path}: {e}")


async def upload_image_to_hosting(
    image_data: bytes,
    filename: str = "image.jpg",
    file_path: Optional[str] = None
) -> str:
    if file_path:
        try:
            with open(file_path, "rb") as handle:
                image_data = handle.read()
        except Exception as e:
            logger.error(f"Failed to read temp file {file_path}: {e}")
            return None

                if audio_file.file_size and audio_file.file_size > MAX_AUDIO_SIZE:
                    if loading_msg:
                        try:
                            await loading_msg.delete()
                        except:
                            pass
                    await update.message.reply_text(
                        "❌ <b>Файл слишком большой</b>\n\n"
                        f"Максимальный размер: {MAX_AUDIO_SIZE // (1024 * 1024)} MB.\n"
                        "Попробуйте другой файл.",
                        parse_mode='HTML'
                    )
                    return INPUTTING_PARAMS
            # Check file size
            if len(audio_data) > MAX_AUDIO_SIZE:
                    f"Максимальный размер: {MAX_AUDIO_SIZE // (1024 * 1024)} MB.\n"
            file_ext = _normalize_extension(file_extension, ".mp3")
            if not _is_extension_allowed(file_ext, ALLOWED_AUDIO_EXTENSIONS):
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Неподдерживаемый формат</b>\n\n"
                    f"Допустимые форматы: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}\n"
                    "Попробуйте другой файл.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS
            filename = f"audio_{user_id}_{audio_file.file_id[:8]}{file_ext}"
            temp_path = _write_temp_file(audio_data, file_ext)
            try:
                public_url = await upload_image_to_hosting(audio_data, filename=filename, file_path=temp_path)
            finally:
                _cleanup_temp_file(temp_path)
                if photo.file_size and photo.file_size > MAX_IMAGE_SIZE:
                    if loading_msg:
                        try:
                            await loading_msg.delete()
                        except:
                            pass
                    await update.message.reply_text(
                        "❌ <b>Файл слишком большой</b>\n\n"
                        f"Максимальный размер: {MAX_IMAGE_SIZE // (1024 * 1024)} MB.\n"
                        "Попробуйте другое изображение или пропустите этот шаг.",
                        parse_mode='HTML'
                    )
                    return INPUTTING_PARAMS
            # Check file size
            if len(image_data) > MAX_IMAGE_SIZE:
                    f"Максимальный размер: {MAX_IMAGE_SIZE // (1024 * 1024)} MB.\n"
            file_ext = _normalize_extension(os.path.splitext(file.file_path or "")[1], ".jpg")
            if not _is_extension_allowed(file_ext, ALLOWED_IMAGE_EXTENSIONS):
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                await update.message.reply_text(
                    "❌ <b>Неподдерживаемый формат</b>\n\n"
                    f"Допустимые форматы: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}\n"
                    "Попробуйте другое изображение или пропустите этот шаг.",
                    parse_mode='HTML'
                )
                return INPUTTING_PARAMS

            logger.info(f"🔥🔥🔥 UPLOADING TO HOSTING: user_id={user_id}, filename=image_{user_id}_{photo.file_id[:8]}{file_ext}")
                temp_path = _write_temp_file(image_data, file_ext)
                try:
                    public_url = await upload_image_to_hosting(
                        image_data,
                        filename=f"image_{user_id}_{photo.file_id[:8]}{file_ext}",
                        file_path=temp_path
                    )
                finally:
                    _cleanup_temp_file(temp_path)
        webhook_base_url = WEBHOOK_BASE_URL or get_webhook_base_url()
        webhook_url = WEBHOOK_URL or build_webhook_url(
            webhook_base_url,
            get_webhook_secret_path()
        )
            logger.error("❌ WEBHOOK_BASE_URL not set for webhook mode!")
            logger.error("   Set WEBHOOK_BASE_URL environment variable or use BOT_MODE=polling")
