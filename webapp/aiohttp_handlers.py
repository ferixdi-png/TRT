"""Native aiohttp handlers for Mini App (no ASGI bridge needed)."""
import json
import logging
import os
from pathlib import Path

from aiohttp import web

from webapp.api.auth import validate_webapp_data, get_user_id_from_init_data

logger = logging.getLogger(__name__)

WEBAPP_STATIC_DIR = Path(__file__).parent / "static"


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
    """Get user balance."""
    user_id = int(request.match_info.get("user_id", 0))
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        balance = await storage.get_user_balance(user_id)
        return web.json_response({"user_id": user_id, "balance": float(balance)})
    except Exception as e:
        logger.error("Failed to get balance for user %s: %s", user_id, e)
        return web.json_response({"user_id": user_id, "balance": 0, "error": str(e)})


async def webapp_models(request: web.Request) -> web.Response:
    """Get list of available models."""
    try:
        from app.kie_catalog import get_model_map
        catalog = get_model_map()
        
        models = []
        for model_id, spec in catalog.items():
            models.append({
                "id": model_id,
                "name": getattr(spec, "name", model_id),
                "type": getattr(spec, "model_mode", "unknown"),
                "emoji": getattr(spec, "emoji", "🎨"),
            })
        
        return web.json_response({"models": models, "count": len(models)})
    except Exception as e:
        logger.error("Failed to get models: %s", e)
        return web.json_response({"models": [], "count": 0, "error": str(e)})


async def webapp_model_info(request: web.Request) -> web.Response:
    """Get specific model info."""
    model_id = request.match_info.get("model_id", "")
    if not model_id:
        return web.json_response({"error": "model_id required"}, status=400)
    
    try:
        from app.kie_catalog import get_model_map
        catalog = get_model_map()
        spec = catalog.get(model_id)
        
        if not spec:
            return web.json_response({"error": f"Model {model_id} not found"}, status=404)
        
        return web.json_response({
            "id": model_id,
            "name": getattr(spec, "name", model_id),
            "type": getattr(spec, "model_mode", "unknown"),
            "emoji": getattr(spec, "emoji", "🎨"),
            "description": getattr(spec, "description", ""),
        })
    except Exception as e:
        logger.error("Failed to get model %s: %s", model_id, e)
        return web.json_response({"error": str(e)}, status=500)


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
    app.router.add_get("/webapp/api/models", webapp_models)
    app.router.add_get("/webapp/api/models/{model_id}", webapp_model_info)
    app.router.add_get("/webapp/static/{filename}", webapp_static)
