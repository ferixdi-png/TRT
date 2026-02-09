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
    """Get user balance with free generations info."""
    user_id = int(request.match_info.get("user_id", 0))
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    
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
        catalog = get_model_map()
        
        models = []
        for model_id, spec in catalog.items():
            # Get price info
            price = 0
            is_free = False
            try:
                from app.pricing.price_resolver import resolve_price
                price_info = await resolve_price(model_id, {})
                if price_info:
                    price = price_info.get('price_rub', 0)
                    is_free = price_info.get('free_sku', False) or price == 0
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
                sku_id = sku.get("sku_id", "")
                if sku_id:
                    sku["price_rub"] = get_sku_price_rub(sku_id) or 0
        
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
    model_id = request.match_info.get("model_id", "")
    if not model_id:
        return web.json_response({"error": "model_id required"}, status=400)
    
    try:
        from app.kie_catalog import get_model_map
        catalog = get_model_map()
        spec = catalog.get(model_id)
        
        if not spec:
            return web.json_response({"error": f"Model {model_id} not found"}, status=404)
        
        # Get schema for parameters
        schema = {}
        if hasattr(spec, 'schema_properties') and spec.schema_properties:
            schema = spec.schema_properties
        
        # Get price
        price = 0
        try:
            from app.pricing.price_resolver import resolve_price
            price_info = await resolve_price(model_id, {})
            price = price_info.get('price_rub', 0) if price_info else 0
        except Exception:
            pass
        
        return web.json_response({
            "id": model_id,
            "name": getattr(spec, "name", model_id),
            "type": getattr(spec, "model_mode", "unknown"),
            "emoji": getattr(spec, "emoji", "🎨"),
            "description": getattr(spec, "description", ""),
            "schema": schema,
            "price": price,
            "requires_image": getattr(spec, "model_mode", "") in ["image-to-image", "image-to-video"],
        })
    except Exception as e:
        logger.error("Failed to get model %s: %s", model_id, e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_upload_image(request: web.Request) -> web.Response:
    """Upload an image for generation. Accepts base64 or multipart."""
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user_id = get_user_id_from_init_data(init_data)
    
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        content_type = request.content_type
        image_data = None
        filename = f"{user_id}_{uuid.uuid4().hex[:8]}.jpg"
        
        if "multipart" in content_type:
            # Handle multipart form data
            reader = await request.multipart()
            async for field in reader:
                if field.name == "image":
                    image_data = await field.read()
                    if field.filename:
                        ext = Path(field.filename).suffix or ".jpg"
                        filename = f"{user_id}_{uuid.uuid4().hex[:8]}{ext}"
                    break
        else:
            # Handle JSON with base64
            data = await request.json()
            base64_data = data.get("image", "")
            if base64_data:
                # Remove data URL prefix if present
                if "base64," in base64_data:
                    base64_data = base64_data.split("base64,")[1]
                image_data = base64.b64decode(base64_data)
        
        if not image_data:
            return web.json_response({"error": "No image provided"}, status=400)
        
        # Save to uploads
        file_path = WEBAPP_UPLOADS_DIR / filename
        file_path.write_bytes(image_data)
        
        # Generate URL (relative to webapp)
        image_url = f"/webapp/uploads/{filename}"
        
        logger.info("Image uploaded: %s (%d bytes)", filename, len(image_data))
        
        return web.json_response({
            "ok": True,
            "filename": filename,
            "url": image_url,
            "size": len(image_data),
        })
        
    except Exception as e:
        logger.error("Image upload failed: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_serve_upload(request: web.Request) -> web.Response:
    """Serve uploaded files."""
    filename = request.match_info.get("filename", "")
    file_path = WEBAPP_UPLOADS_DIR / filename
    
    if not file_path.exists() or not file_path.is_file():
        return web.Response(text="Not found", status=404)
    
    # Determine content type
    content_type = "image/jpeg"
    if filename.endswith(".png"):
        content_type = "image/png"
    elif filename.endswith(".gif"):
        content_type = "image/gif"
    elif filename.endswith(".webp"):
        content_type = "image/webp"
    
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
    image_url = data.get("image_url")  # For image-to-image/video models
    
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
        
        # Check if image is required
        model_mode = getattr(spec, "model_mode", "")
        requires_image = model_mode in ["image-to-image", "image-to-video"]
        
        if requires_image and not image_url:
            return web.json_response({"error": "Image required for this model"}, status=400)
        
        # Check balance
        storage = get_storage()
        balance = await storage.get_user_balance(user_id)
        
        # Get price
        price = 0
        try:
            from app.pricing.price_resolver import resolve_price
            price_info = await resolve_price(model_id, params)
            price = price_info.get('price_rub', 0) if price_info else 0
        except Exception:
            pass
        
        if balance < price:
            return web.json_response({
                "error": "Insufficient balance",
                "balance": float(balance),
                "price": price,
            }, status=402)
        
        # Create generation job
        job_id = f"webapp-{uuid.uuid4().hex[:12]}"
        correlation_id = f"corr-webapp-{user_id}-{uuid.uuid4().hex[:8]}"
        
        # Merge prompt and image into params
        session_params = {**params, "prompt": prompt}
        
        # Add image if provided
        if image_url:
            # Convert relative URL to absolute file path or external URL
            if image_url.startswith("/webapp/uploads/"):
                filename = image_url.replace("/webapp/uploads/", "")
                file_path = WEBAPP_UPLOADS_DIR / filename
                if file_path.exists():
                    # Read and encode as base64 for API
                    image_bytes = file_path.read_bytes()
                    image_base64 = base64.b64encode(image_bytes).decode()
                    session_params["image"] = f"data:image/jpeg;base64,{image_base64}"
            else:
                session_params["image_url"] = image_url
        
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
                # Store result for polling
                await storage.write_json_file(
                    f"webapp_jobs/{job_id}.json",
                    {
                        "job_id": job_id,
                        "user_id": user_id,
                        "model_id": model_id,
                        "status": result.state if result else "failed",
                        "result_url": result.result_url if result else None,
                        "error": result.error if result else None,
                    }
                )
            except Exception as e:
                logger.error("Webapp generation failed: %s", e)
                await storage.write_json_file(
                    f"webapp_jobs/{job_id}.json",
                    {
                        "job_id": job_id,
                        "user_id": user_id,
                        "model_id": model_id,
                        "status": "failed",
                        "error": str(e),
                    }
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
    """Get job status."""
    job_id = request.match_info.get("job_id", "")
    if not job_id:
        return web.json_response({"error": "job_id required"}, status=400)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        job_data = await storage.read_json_file(f"webapp_jobs/{job_id}.json", default=None)
        if not job_data:
            return web.json_response({"error": "Job not found"}, status=404)
        
        return web.json_response(job_data)
    except Exception as e:
        logger.error("Failed to get job status: %s", e)
        return web.json_response({"error": str(e)}, status=500)


async def webapp_user_history(request: web.Request) -> web.Response:
    """Get user generation history."""
    user_id = int(request.match_info.get("user_id", 0))
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        # Get all jobs for this user
        jobs = []
        try:
            jobs_data = await storage.read_json_file("generation_jobs.json", default={})
            for job_id, job in jobs_data.items():
                if job.get("user_id") == user_id:
                    jobs.append({
                        "job_id": job_id,
                        "model_id": job.get("model_id"),
                        "status": job.get("status"),
                        "result_url": job.get("result_url"),
                        "created_at": job.get("created_at"),
                    })
        except Exception:
            pass
        
        # Sort by date, newest first
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
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
    app.router.add_get("/webapp/api/models/{model_id}", webapp_model_info)
    app.router.add_post("/webapp/api/upload", webapp_upload_image)
    app.router.add_post("/webapp/api/generate", webapp_generate)
    app.router.add_get("/webapp/api/jobs/{job_id}", webapp_job_status)
    app.router.add_get("/webapp/uploads/{filename}", webapp_serve_upload)
    app.router.add_get("/webapp/static/{filename}", webapp_static)
