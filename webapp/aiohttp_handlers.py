"""Native aiohttp handlers for Mini App (no ASGI bridge needed)."""
import base64
import json
import logging
import os
import uuid
from pathlib import Path

from aiohttp import web

from webapp.api.auth import validate_webapp_data, get_user_id_from_init_data

logger = logging.getLogger(__name__)

WEBAPP_STATIC_DIR = Path(__file__).parent / "static"


def _get_job_status_info(status: str) -> dict:
    """Map job status to UX-friendly state, progress, and action hint."""
    status_lower = (status or "pending").lower()
    
    STATUS_MAP = {
        "pending": {"state": "pending", "progress": 0, "action_hint": "Ожидание в очереди..."},
        "queued": {"state": "queued", "progress": 10, "action_hint": "В очереди на обработку"},
        "waiting": {"state": "processing", "progress": 30, "action_hint": "Генерация в процессе..."},
        "success": {"state": "ready", "progress": 90, "action_hint": "Результат готов"},
        "result_validated": {"state": "ready", "progress": 95, "action_hint": "Результат проверен"},
        "tg_deliver": {"state": "delivering", "progress": 98, "action_hint": "Доставка результата..."},
        "delivered": {"state": "done", "progress": 100, "action_hint": "Готово! Откройте результат"},
        "completed": {"state": "done", "progress": 100, "action_hint": "Готово!"},
        "failed": {"state": "error", "progress": 0, "action_hint": "Ошибка. Попробуйте повторить"},
        "canceled": {"state": "canceled", "progress": 0, "action_hint": "Отменено"},
    }
    
    return STATUS_MAP.get(status_lower, {"state": status_lower, "progress": 50, "action_hint": "Обработка..."})


WEBAPP_UPLOADS_DIR = Path(__file__).parent / "uploads"
WEBAPP_UPLOADS_DIR.mkdir(exist_ok=True)


async def webapp_index(request: web.Request) -> web.Response:
    """Serve the main Mini App HTML."""
    index_file = WEBAPP_STATIC_DIR / "index.html"
    if index_file.exists():
        return web.Response(
            text=index_file.read_text(encoding="utf-8"),
            content_type="text/html",
        )
    return web.Response(text="<h1>Mini App</h1><p>Frontend not found</p>", content_type="text/html")


async def webapp_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok", "service": "mini-app"})


async def webapp_user_me(request: web.Request) -> web.Response:
    """Get current user info from Telegram initData."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_data = validate_webapp_data(init_data) if init_data else None
    
    if not user_data:
        return web.json_response({"error": "Invalid or missing Telegram auth"}, status=401)
    
    return web.json_response({
        "user_id": user_data.get("id"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "username": user_data.get("username"),
        "language_code": user_data.get("language_code", "ru"),
    })


async def webapp_user_balance(request: web.Request) -> web.Response:
    """Get user balance. Requires auth and user_id match."""
    # Auth check - require valid init_data
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    auth_user_id = get_user_id_from_init_data(init_data)
    if not auth_user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    user_id = int(request.match_info.get("user_id", 0))
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    
    # Verify user can only access their own balance
    if auth_user_id != user_id:
        return web.json_response({"error": "Forbidden"}, status=403)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        balance = await storage.get_user_balance(user_id)
        
        # Get free generations remaining
        free_remaining = 0
        try:
            from helpers import get_user_free_generations_remaining_async
            free_remaining = await get_user_free_generations_remaining_async(user_id)
        except Exception:
            pass
        
        return web.json_response({
            "user_id": user_id,
            "balance": float(balance),
            "free_remaining": free_remaining,
        })
    except Exception as e:
        logger.error("Failed to get balance for user %s: %s", user_id, e)
        return web.json_response({"user_id": user_id, "balance": 0, "free_remaining": 0, "error": str(e)})


async def webapp_models(request: web.Request) -> web.Response:
    """Get list of available models with pricing info."""
    try:
        from app.kie_catalog import get_model_map
        from app.pricing.price_ssot import model_has_free_sku
        catalog = get_model_map()
        
        models = []
        for model_id, spec in catalog.items():
            # Get price info
            price = 0
            is_free = model_has_free_sku(model_id)  # Check directly from SSOT
            try:
                from app.pricing.price_resolver import resolve_price
                price_info = await resolve_price(model_id, {})
                if price_info:
                    price = price_info.get('price_rub', 0)
                    # Also check from resolve_price
                    if price_info.get('free_sku', False):
                        is_free = True
            except Exception:
                pass
            
            models.append({
                "id": model_id,
                "name": getattr(spec, "name", model_id),
                "type": getattr(spec, "model_mode", "unknown"),
                "emoji": getattr(spec, "emoji", "🎨"),
                "price": price,
                "is_free": is_free,
            })
        
        # Sort: free first, then by name
        models.sort(key=lambda m: (not m['is_free'], m['name'].lower()))
        
        return web.json_response({"models": models, "count": len(models)})
    except Exception as e:
        logger.error("Failed to get models: %s", e)
        return web.json_response({"models": [], "count": 0, "error": str(e)})


async def webapp_top_models(request: web.Request) -> web.Response:
    """Get list of top models with SKUs for Mini App."""
    lang = request.query.get("lang", "ru")
    category = request.query.get("category")
    
    try:
        from app.top_models import get_categories, get_top_models, get_sku_price_rub
        
        categories = get_categories(lang=lang)
        models = get_top_models(lang=lang, category=category)
        
        # Enrich models with prices
        for model in models:
            for sku in model.get("skus", []):
                price_ref = sku.get("price_ref", "")
                mode_key = sku.get("mode_key", "")
                if price_ref:
                    sku["price_rub"] = get_sku_price_rub(price_ref, mode_key) or 0
        
        return web.json_response({
            "models": models,
            "categories": categories,
            "count": len(models),
        })
    except Exception as e:
        logger.error("Failed to get top models: %s", e)
        return web.json_response({"models": [], "categories": [], "count": 0, "error": str(e)})


async def webapp_model_info(request: web.Request) -> web.Response:
    """Get specific model info with parameters schema."""
    from urllib.parse import unquote
    model_id = unquote(request.match_info.get("model_id", ""))
    if not model_id:
        return web.json_response({"error": "model_id required"}, status=400)
    
    lang = request.query.get("lang", "ru")
    
    try:
        from app.kie_catalog import get_model_map
        catalog = get_model_map()
        spec = catalog.get(model_id)
        
        if not spec:
            return web.json_response({"error": f"Model {model_id} not found"}, status=404)
        
        # Get schema from Source of Truth (auto-generated from kie_models.yaml)
        ux_schema = None
        try:
            from app.models.input_schema import get_ux_schema_for_webapp
            ux_schema = get_ux_schema_for_webapp(model_id, lang)
        except Exception as e:
            logger.warning("Failed to get UX schema for %s: %s", model_id, e)
        
        # Fallback to legacy schema
        legacy_schema = {}
        if hasattr(spec, 'schema_properties') and spec.schema_properties:
            legacy_schema = spec.schema_properties
        
        # Get price
        price = 0
        try:
            from app.pricing.price_resolver import resolve_price
            price_info = await resolve_price(model_id, {})
            price = price_info.get('price_rub', 0) if price_info else 0
        except Exception:
            pass
        
        # Determine required input types
        model_mode = getattr(spec, "model_mode", "")
        model_type = getattr(spec, "type", "")
        
        requires_image = (
            model_mode in ["image-to-image", "image-to-video", "i2i", "i2v"] or
            model_type in ["i2i", "i2v"] or
            "image-to" in model_id or
            "edit" in model_id.lower() or
            "remix" in model_id.lower()
        )
        requires_video = model_mode in ["video-to-video", "v2v"] or model_type in ["v2v"]
        requires_audio = model_mode in ["audio", "speech", "a2a"] or model_type in ["a2a", "audio"]
        
        # Determine output type
        output_type = "image"
        if model_mode in ["text-to-video", "image-to-video", "t2v", "i2v"] or model_type in ["t2v", "i2v"]:
            output_type = "video"
        elif model_mode in ["audio", "speech", "t2a", "a2a"] or model_type in ["t2a", "a2a", "audio"]:
            output_type = "audio"
        
        return web.json_response({
            "id": model_id,
            "name": getattr(spec, "name", model_id),
            "type": model_mode or model_type or "unknown",
            "emoji": getattr(spec, "emoji", "🎨"),
            "description": getattr(spec, "description", ""),
            "ux_schema": ux_schema,
            "schema": legacy_schema,
            "price": price,
            "requires_image": requires_image,
            "requires_video": requires_video,
            "requires_audio": requires_audio,
            "output_type": output_type,
        })
    except Exception as e:
        logger.error("Failed to get model %s: %s", model_id, e)
        return web.json_response({"error": str(e)}, status=500)


# Supported media extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}


def _get_media_type(filename: str) -> str:
    """Determine media type from filename extension."""
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in VIDEO_EXTENSIONS:
        return "video"
    elif ext in AUDIO_EXTENSIONS:
        return "audio"
    return "file"


async def webapp_upload_image(request: web.Request) -> web.Response:
    """Upload media file (image, video, audio) for generation. Accepts base64 or multipart."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_id = get_user_id_from_init_data(init_data)
    
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        content_type = request.content_type
        file_data = None
        filename = f"{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        original_filename = None
        
        if "multipart" in content_type:
            # Handle multipart form data
            reader = await request.multipart()
            async for field in reader:
                # Accept 'image', 'video', 'audio', or 'file' field names
                if field.name in ("image", "video", "audio", "file", "media"):
                    file_data = await field.read()
                    if field.filename:
                        original_filename = field.filename
                        ext = Path(field.filename).suffix.lower() or ".jpg"
                        filename = f"{user_id}_{uuid.uuid4().hex[:8]}{ext}"
                    break
        else:
            # Handle JSON with base64
            data = await request.json()
            # Check for image, video, audio, or file field
            base64_data = data.get("image") or data.get("video") or data.get("audio") or data.get("file") or ""
            if base64_data:
                # Remove data URL prefix if present and extract extension
                if "base64," in base64_data:
                    # Try to extract mime type for extension
                    prefix = base64_data.split("base64,")[0]
                    base64_data = base64_data.split("base64,")[1]
                    # Extract extension from data URL (e.g., data:video/mp4;base64,...)
                    if "video/" in prefix:
                        mime_ext = prefix.split("video/")[1].split(";")[0]
                        filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{mime_ext}"
                    elif "audio/" in prefix:
                        mime_ext = prefix.split("audio/")[1].split(";")[0]
                        if mime_ext == "mpeg":
                            mime_ext = "mp3"
                        filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{mime_ext}"
                    elif "image/" in prefix:
                        mime_ext = prefix.split("image/")[1].split(";")[0]
                        filename = f"{user_id}_{uuid.uuid4().hex[:8]}.{mime_ext}"
                file_data = base64.b64decode(base64_data)
        
        if not file_data:
            return web.json_response({"error": "No file provided"}, status=400)
        
        # Save to uploads
        file_path = WEBAPP_UPLOADS_DIR / filename
        file_path.write_bytes(file_data)
        
        # Generate URL (relative to webapp)
        file_url = f"/webapp/uploads/{filename}"
        media_type = _get_media_type(filename)
        
        logger.info("Media uploaded: %s (%d bytes, type=%s)", filename, len(file_data), media_type)
        
        return web.json_response({
            "ok": True,
            "filename": filename,
            "url": file_url,
            "size": len(file_data),
            "type": media_type,
            "original_filename": original_filename,
        })
        
    except Exception as e:
        logger.error("Media upload failed: %s", e)
        return web.json_response({"error": str(e)}, status=500)


# Content-type mapping for all supported formats
CONTENT_TYPE_MAP = {
    # Images
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    # Videos
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".m4v": "video/x-m4v",
    # Audio
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}


async def webapp_serve_upload(request: web.Request) -> web.Response:
    """Serve uploaded files (images, videos, audio)."""
    filename = request.match_info.get("filename", "")
    file_path = WEBAPP_UPLOADS_DIR / filename
    
    if not file_path.exists() or not file_path.is_file():
        return web.Response(text="Not found", status=404)
    
    # Determine content type from extension
    ext = Path(filename).suffix.lower()
    content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")
    
    return web.Response(
        body=file_path.read_bytes(),
        content_type=content_type,
    )


async def webapp_generate(request: web.Request) -> web.Response:
    """Start a generation task."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_id = get_user_id_from_init_data(init_data)
    
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    model_id = data.get("model_id")
    prompt = data.get("prompt", "")
    params = data.get("params", {})
    # Support image, video, and audio inputs
    image_url = data.get("image_url")
    video_url = data.get("video_url")
    audio_url = data.get("audio_url")
    media_url = data.get("media_url")  # Generic media field
    
    if not model_id:
        return web.json_response({"error": "model_id required"}, status=400)
    
    if not prompt:
        return web.json_response({"error": "prompt required"}, status=400)
    
    try:
        from app.kie_catalog import get_model_map
        from app.storage import get_storage
        
        catalog = get_model_map()
        spec = catalog.get(model_id)
        if not spec:
            return web.json_response({"error": f"Model {model_id} not found"}, status=404)
        
        # Check if media input is required based on model mode
        model_mode = getattr(spec, "model_mode", "")
        model_type = getattr(spec, "type", "")
        
        # Determine required input type
        requires_image = model_mode in ["image-to-image", "image-to-video", "i2i", "i2v"] or model_type in ["i2i", "i2v"]
        requires_video = model_mode in ["video-to-video", "v2v"] or model_type in ["v2v"]
        requires_audio = model_mode in ["audio", "speech", "a2a"] or model_type in ["a2a", "audio"]
        
        # Check required inputs
        if requires_image and not (image_url or media_url):
            return web.json_response({
                "error": "Изображение обязательно для этой модели",
                "error_en": "Image required for this model",
                "required_input": "image",
            }, status=400)
        
        if requires_video and not (video_url or media_url):
            return web.json_response({
                "error": "Видео обязательно для этой модели",
                "error_en": "Video required for this model",
                "required_input": "video",
            }, status=400)
        
        if requires_audio and not (audio_url or media_url):
            return web.json_response({
                "error": "Аудио обязательно для этой модели",
                "error_en": "Audio required for this model",
                "required_input": "audio",
            }, status=400)
        
        # Validate parameters using schema
        try:
            from app.models.input_schema import validate_input
            validation_errors = validate_input(model_id, {**params, "prompt": prompt})
            if validation_errors:
                return web.json_response({
                    "error": "Ошибки валидации параметров",
                    "error_en": "Parameter validation errors",
                    "validation_errors": validation_errors,
                }, status=400)
        except Exception:
            pass  # Schema may not exist for all models
        
        # Check balance and free generations
        storage = get_storage()
        balance = await storage.get_user_balance(user_id)
        
        # Get price and check if model is free
        price = 0
        is_free_model = False
        try:
            from app.pricing.price_resolver import resolve_price
            from app.pricing.price_ssot import model_has_free_sku
            price_info = await resolve_price(model_id, params)
            price = price_info.get('price_rub', 0) if price_info else 0
            is_free_model = model_has_free_sku(model_id) or price_info.get('free_sku', False) if price_info else False
        except Exception:
            pass
        
        # Check if user has free generations available
        is_free_generation = False
        if is_free_model:
            try:
                from helpers import get_user_free_generations_remaining_async
                free_remaining = await get_user_free_generations_remaining_async(user_id)
                if free_remaining > 0:
                    is_free_generation = True
                    price = 0  # Free generation costs nothing
            except Exception:
                pass
        
        # Check balance only if not a free generation
        if not is_free_generation and balance < price:
            return web.json_response({
                "error": "Insufficient balance",
                "balance": float(balance),
                "price": price,
            }, status=402)
        
        # Create generation job
        job_id = f"webapp-{uuid.uuid4().hex[:12]}"
        correlation_id = f"corr-webapp-{user_id}-{uuid.uuid4().hex[:8]}"
        
        # Merge prompt into params
        session_params = {**params, "prompt": prompt}
        
        # Helper to process media URL (image, video, audio)
        def _process_media_url(url: str, param_name: str, mime_prefix: str) -> None:
            if not url:
                return
            if url.startswith("/webapp/uploads/"):
                fname = url.replace("/webapp/uploads/", "")
                fpath = WEBAPP_UPLOADS_DIR / fname
                if fpath.exists():
                    media_bytes = fpath.read_bytes()
                    media_base64 = base64.b64encode(media_bytes).decode()
                    # Detect mime type from extension
                    ext = Path(fname).suffix.lower()
                    mime_type = CONTENT_TYPE_MAP.get(ext, f"{mime_prefix}/octet-stream")
                    session_params[param_name] = f"data:{mime_type};base64,{media_base64}"
            else:
                session_params[f"{param_name}_url"] = url
        
        # Add image if provided
        _process_media_url(image_url, "image", "image")
        
        # Add video if provided
        _process_media_url(video_url, "video", "video")
        
        # Add audio if provided
        _process_media_url(audio_url, "audio", "audio")
        
        # Add generic media if provided
        if media_url:
            media_type = _get_media_type(media_url)
            _process_media_url(media_url, media_type, media_type)
        
        # CRITICAL: Save job to unified storage IMMEDIATELY so it can be polled
        model_name = getattr(spec, "name", model_id)
        await storage.add_generation_job(
            job_id=job_id,
            user_id=user_id,
            model_id=model_id,
            model_name=model_name,
            params=session_params,
            price=price,
            correlation_id=correlation_id,
            prompt=prompt,
            status="pending",
            is_free=is_free_generation,
        )
        
        # Start generation in background
        import asyncio
        from app.generations.universal_engine import run_generation
        
        async def run_gen():
            try:
                result = await run_generation(
                    user_id=user_id,
                    model_id=model_id,
                    session_params=session_params,
                    correlation_id=correlation_id,
                    job_id=job_id,
                    price=price,
                )
                # Update job status in unified storage
                if result:
                    await storage.update_job_status(
                        job_id=job_id,
                        status=result.state if result.state else "success",
                        result_url=result.result_url,
                        result_urls=result.result_urls if hasattr(result, 'result_urls') else [],
                    )
                else:
                    await storage.update_job_status(job_id=job_id, status="failed")
            except Exception as e:
                logger.error("Webapp generation failed: %s", e)
                await storage.update_job_status(
                    job_id=job_id,
                    status="failed",
                    error_message=str(e),
                )
        
        asyncio.create_task(run_gen())
        
        return web.json_response({
            "ok": True,
            "job_id": job_id,
            "correlation_id": correlation_id,
            "status": "pending",
            "price": price,
        })
        
    except Exception as e:
        logger.error("Failed to start generation: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_job_status(request: web.Request) -> web.Response:
    """Get job status from unified storage."""
    job_id = request.match_info.get("job_id", "")
    if not job_id:
        return web.json_response({"error": "job_id required"}, status=400)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        # Use unified storage.get_job instead of separate webapp_jobs
        job = await storage.get_job(job_id)
        if not job:
            return web.json_response({"error": "Job not found"}, status=404)
        
        # UX-friendly status mapping
        status = job.get("status", "pending")
        status_info = _get_job_status_info(status)
        
        return web.json_response({
            "job_id": job.get("job_id"),
            "user_id": job.get("user_id"),
            "model_id": job.get("model_id"),
            "status": status,
            "state": status_info["state"],
            "progress": status_info["progress"],
            "action_hint": status_info["action_hint"],
            "result_url": job.get("result_url"),
            "result_urls": job.get("result_urls", []),
            "error": job.get("error_message"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        })
    except Exception as e:
        logger.error("Failed to get job status: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_job_cancel(request: web.Request) -> web.Response:
    """Cancel a job."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_id = get_user_id_from_init_data(init_data)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    job_id = request.match_info.get("job_id", "")
    if not job_id:
        return web.json_response({"error": "job_id required"}, status=400)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        job = await storage.get_job(job_id)
        if not job:
            return web.json_response({"error": "Job not found"}, status=404)
        
        if job.get("user_id") != user_id:
            return web.json_response({"error": "Forbidden"}, status=403)
        
        await storage.update_job_status(job_id, "canceled", error_message="Cancelled by user")
        return web.json_response({"ok": True, "status": "canceled"})
    except Exception as e:
        logger.error("Failed to cancel job: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_job_retry(request: web.Request) -> web.Response:
    """Retry a failed job with same parameters."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_id = get_user_id_from_init_data(init_data)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    job_id = request.match_info.get("job_id", "")
    if not job_id:
        return web.json_response({"error": "job_id required"}, status=400)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        job = await storage.get_job(job_id)
        if not job:
            return web.json_response({"error": "Job not found"}, status=404)
        
        if job.get("user_id") != user_id:
            return web.json_response({"error": "Forbidden"}, status=403)
        
        # Create new job with same params
        new_job_id = f"webapp-retry-{uuid.uuid4().hex[:12]}"
        correlation_id = f"corr-webapp-{user_id}-{uuid.uuid4().hex[:8]}"
        
        model_id = job.get("model_id")
        model_name = job.get("model_name", model_id)
        params = job.get("params", {})
        price = job.get("price", 0)
        prompt = params.get("prompt", "")
        
        # CRITICAL: Save retry job immediately so it can be polled
        await storage.add_generation_job(
            job_id=new_job_id,
            user_id=user_id,
            model_id=model_id,
            model_name=model_name,
            params=params,
            price=price,
            correlation_id=correlation_id,
            prompt=prompt,
            status="pending",
        )
        
        import asyncio
        from app.generations.universal_engine import run_generation
        
        async def run_gen():
            try:
                result = await run_generation(
                    user_id=user_id,
                    model_id=model_id,
                    session_params=params,
                    correlation_id=correlation_id,
                    job_id=new_job_id,
                    price=price,
                )
                # Update job status
                if result:
                    await storage.update_job_status(
                        job_id=new_job_id,
                        status=result.state if result.state else "success",
                        result_url=result.result_url,
                        result_urls=result.result_urls if hasattr(result, 'result_urls') else [],
                    )
                else:
                    await storage.update_job_status(job_id=new_job_id, status="failed")
            except Exception as e:
                logger.error("Webapp retry generation failed: %s", e)
                await storage.update_job_status(
                    job_id=new_job_id,
                    status="failed",
                    error_message=str(e),
                )
        
        asyncio.create_task(run_gen())
        
        return web.json_response({
            "ok": True,
            "job_id": new_job_id,
            "correlation_id": correlation_id,
            "status": "pending",
        })
    except Exception as e:
        logger.error("Failed to retry job: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_user_history(request: web.Request) -> web.Response:
    """Get user generation history from unified storage. Requires auth."""
    # Auth check - require valid init_data
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    auth_user_id = get_user_id_from_init_data(init_data)
    if not auth_user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    user_id = int(request.match_info.get("user_id", 0))
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    
    # Verify user can only access their own history
    if auth_user_id != user_id:
        return web.json_response({"error": "Forbidden"}, status=403)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        # Use unified storage.list_jobs instead of reading json file
        jobs_raw = await storage.list_jobs(user_id=user_id, limit=50)
        
        jobs = []
        for job in jobs_raw:
            jobs.append({
                "job_id": job.get("job_id"),
                "model_id": job.get("model_id"),
                "model_name": job.get("model_name"),
                "status": job.get("status"),
                "result_url": job.get("result_url"),
                "result_urls": job.get("result_urls", []),
                "created_at": job.get("created_at"),
            })
        
        return web.json_response({"history": jobs[:20], "total": len(jobs)})
    except Exception as e:
        logger.error("Failed to get user history: %s", e)
        return web.json_response({"history": [], "total": 0, "error": str(e)})


async def webapp_static(request: web.Request) -> web.Response:
    """Serve static files."""
    filename = request.match_info.get("filename", "")
    file_path = WEBAPP_STATIC_DIR / filename
    
    if not file_path.exists() or not file_path.is_file():
        return web.Response(text="Not found", status=404)
    
    content_type = "text/plain"
    if filename.endswith(".html"):
        content_type = "text/html"
    elif filename.endswith(".css"):
        content_type = "text/css"
    elif filename.endswith(".js"):
        content_type = "application/javascript"
    elif filename.endswith(".json"):
        content_type = "application/json"
    
    return web.Response(
        text=file_path.read_text(encoding="utf-8"),
        content_type=content_type,
    )


def register_webapp_routes(app: web.Application) -> None:
    """Register all webapp routes on the aiohttp app."""
    app.router.add_get("/webapp", webapp_index)
    app.router.add_get("/webapp/", webapp_index)
    app.router.add_get("/webapp/api/health", webapp_health)
    app.router.add_get("/webapp/api/user/me", webapp_user_me)
    app.router.add_get("/webapp/api/user/{user_id}/balance", webapp_user_balance)
    app.router.add_get("/webapp/api/user/{user_id}/history", webapp_user_history)
    app.router.add_get("/webapp/api/models", webapp_models)
    app.router.add_get("/webapp/api/top-models", webapp_top_models)
    app.router.add_get("/webapp/api/models/{model_id:.+}", webapp_model_info)  # .+ allows slashes in model_id
    app.router.add_post("/webapp/api/upload", webapp_upload_image)
    app.router.add_post("/webapp/api/generate", webapp_generate)
    app.router.add_get("/webapp/api/jobs/{job_id}", webapp_job_status)
    app.router.add_post("/webapp/api/jobs/{job_id}/cancel", webapp_job_cancel)
    app.router.add_post("/webapp/api/jobs/{job_id}/retry", webapp_job_retry)
    app.router.add_get("/webapp/uploads/{filename}", webapp_serve_upload)
    app.router.add_get("/webapp/static/{filename}", webapp_static)
