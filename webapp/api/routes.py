"""Mini App API routes."""
import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from webapp.api.auth import validate_webapp_data, get_user_id_from_init_data

logger = logging.getLogger(__name__)

webapp_api = FastAPI(
    title="TRT Mini App API",
    description="Telegram Mini App for TRT Bot",
    version="1.0.0",
)

webapp_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_user_id_from_header(x_telegram_init_data: Optional[str] = None) -> Optional[int]:
    """Extract and validate user_id from Telegram initData header."""
    if not x_telegram_init_data:
        return None
    return get_user_id_from_init_data(x_telegram_init_data)


@webapp_api.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "mini-app"}


@webapp_api.get("/api/user/me")
async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get current user info from Telegram initData."""
    user_data = validate_webapp_data(x_telegram_init_data) if x_telegram_init_data else None
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or missing Telegram auth")
    
    return {
        "user_id": user_data.get("id"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "username": user_data.get("username"),
        "language_code": user_data.get("language_code", "ru"),
    }


@webapp_api.get("/api/user/{user_id}/balance")
async def get_user_balance(
    user_id: int,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get user balance - uses existing storage."""
    auth_user_id = _get_user_id_from_header(x_telegram_init_data)
    
    if auth_user_id and auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        balance = await storage.get_user_balance(user_id)
        return {"user_id": user_id, "balance": balance}
    except Exception as e:
        logger.error("Failed to get balance for user %s: %s", user_id, e)
        return {"user_id": user_id, "balance": 0, "error": str(e)}


@webapp_api.get("/api/models")
async def get_available_models():
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
        
        return {"models": models, "count": len(models)}
    except Exception as e:
        logger.error("Failed to get models: %s", e)
        return {"models": [], "count": 0, "error": str(e)}


@webapp_api.get("/api/models/{model_id}")
async def get_model_info(model_id: str):
    """Get specific model info."""
    try:
        from app.kie_catalog import get_model_map
        catalog = get_model_map()
        spec = catalog.get(model_id)
        
        if not spec:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        return {
            "id": model_id,
            "name": getattr(spec, "name", model_id),
            "type": getattr(spec, "model_mode", "unknown"),
            "emoji": getattr(spec, "emoji", "🎨"),
            "description": getattr(spec, "description", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get model %s: %s", model_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@webapp_api.get("/api/models/{model_id}/intro")
async def get_model_intro(
    model_id: str,
    lang: str = "ru",
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get Model Intro Card data for Mini App."""
    try:
        from app.model_descriptions import get_intro_card_data
        from app.pricing.price_ssot import list_model_skus
        
        # Get first SKU price if available
        price_rub = None
        unit = None
        skus = list_model_skus(model_id)
        if skus:
            price_rub = float(skus[0].price_rub)
            unit = skus[0].unit
        
        return get_intro_card_data(model_id, lang=lang, price_rub=price_rub, unit=unit)
    except Exception as e:
        logger.error("Failed to get intro for model %s: %s", model_id, e)
        return {
            "model_id": model_id,
            "lang": lang,
            "title": model_id,
            "one_liner": "",
            "best_for": [],
            "you_need": "",
            "you_get": "",
            "price_hint": "Цена уточняется" if lang == "ru" else "Pricing TBD",
        }


@webapp_api.get("/api/top-models")
async def get_top_models_list(
    lang: str = "ru",
    category: Optional[str] = None,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get list of top models with SKUs for Mini App."""
    try:
        from app.top_models import get_categories, get_top_models, get_sku_price_rub
        
        categories = get_categories(lang=lang)
        models = get_top_models(lang=lang, category=category)
        
        # Enrich models with prices
        for model in models:
            for sku in model.get("skus", []):
                price = get_sku_price_rub(sku.get("price_ref", ""), sku.get("mode_key", ""))
                sku["price_rub"] = price if price else None
        
        return {
            "categories": categories,
            "models": models,
            "total": len(models),
        }
    except Exception as e:
        logger.error("Failed to get top models: %s", e)
        return {
            "categories": [],
            "models": [],
            "total": 0,
            "error": str(e),
        }


@webapp_api.get("/api/top-models/{top_model_id}")
async def get_top_model_detail(
    top_model_id: str,
    lang: str = "ru",
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get single top model details with SKUs."""
    try:
        from app.top_models import get_top_model_by_id, get_sku_price_rub
        
        model = get_top_model_by_id(top_model_id, lang=lang)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        # Enrich SKUs with prices
        for sku in model.get("skus", []):
            price = get_sku_price_rub(sku.get("price_ref", ""), sku.get("mode_key", ""))
            sku["price_rub"] = price if price else None
        
        return model
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get top model %s: %s", top_model_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@webapp_api.get("/api/top-models/{top_model_id}/sku/{sku_id}")
async def get_top_model_sku(
    top_model_id: str,
    sku_id: str,
    lang: str = "ru",
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get SKU details for routing to generation."""
    try:
        from app.top_models import get_sku_details, get_sku_price_rub
        
        sku = get_sku_details(top_model_id, sku_id, lang=lang)
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")
        
        price = get_sku_price_rub(sku.get("price_ref", ""), sku.get("mode_key", "") if "mode_key" in sku else "")
        sku["price_rub"] = price if price else None
        
        return sku
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get SKU %s/%s: %s", top_model_id, sku_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@webapp_api.get("/api/user/{user_id}/history")
async def get_user_history(
    user_id: int,
    limit: int = 10,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
):
    """Get user generation history."""
    auth_user_id = _get_user_id_from_header(x_telegram_init_data)
    
    if auth_user_id and auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        from app.storage import get_storage
        storage = get_storage()
        
        jobs_data = await storage.read_json_file("generation_jobs.json", default={})
        user_jobs = []
        
        for job_id, job in jobs_data.items():
            if job.get("user_id") == user_id:
                user_jobs.append({
                    "job_id": job_id,
                    "model_id": job.get("model_id"),
                    "status": job.get("status"),
                    "created_at": job.get("created_at"),
                })
        
        user_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return {"history": user_jobs[:limit], "total": len(user_jobs)}
    except Exception as e:
        logger.error("Failed to get history for user %s: %s", user_id, e)
        return {"history": [], "total": 0, "error": str(e)}


WEBAPP_DIR = Path(__file__).parent.parent / "static"


@webapp_api.get("/", response_class=HTMLResponse)
async def serve_webapp():
    """Serve the main Mini App HTML."""
    index_file = WEBAPP_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Mini App</h1><p>Frontend not found</p>")


if WEBAPP_DIR.exists():
    webapp_api.mount("/static", StaticFiles(directory=str(WEBAPP_DIR)), name="static")
