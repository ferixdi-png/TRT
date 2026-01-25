"""DB health check helpers shared between diagnostics and billing preflight."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import asyncpg

from app.observability.structured_logs import log_structured_event
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DbHealthResult:
    ok: bool
    status: str
    latency_ms: Optional[float]
    correlation_id: str
    error_class: Optional[str] = None
    error_message: Optional[str] = None


async def check_db_health(
    database_url: str,
    *,
    db_pool: Optional[asyncpg.Pool] = None,
    timeout_s: float = 1.5,
    correlation_id: Optional[str] = None,
) -> DbHealthResult:
    corr_id = correlation_id or f"corr-db-{uuid.uuid4().hex[:10]}"
    if not database_url and db_pool is None:
        return DbHealthResult(
            ok=False,
            status="FAIL",
            latency_ms=None,
            correlation_id=corr_id,
            error_class="ConfigError",
            error_message="DATABASE_URL missing",
        )

    start = time.perf_counter()
    try:
        if db_pool is None:
            conn = await asyncio.wait_for(asyncpg.connect(database_url), timeout=timeout_s)
            try:
                value = await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=timeout_s)
            finally:
                await conn.close()
        else:
            async with db_pool.acquire() as conn:
                value = await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=timeout_s)
        latency_ms = (time.perf_counter() - start) * 1000
        if value != 1:
            return DbHealthResult(
                ok=False,
                status="FAIL",
                latency_ms=latency_ms,
                correlation_id=corr_id,
                error_class="InvalidResponse",
                error_message=f"SELECT 1 returned {value}",
            )
        return DbHealthResult(
            ok=True,
            status="OK",
            latency_ms=latency_ms,
            correlation_id=corr_id,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("DB_HEALTH_CHECK_FAILED corr_id=%s error=%s", corr_id, exc, exc_info=True)
        log_structured_event(
            correlation_id=corr_id,
            action="DB_FAIL",
            action_path="db:healthcheck",
            stage="DB",
            outcome="failed",
            error_code=type(exc).__name__,
            fix_hint=str(exc)[:120],
            param={"latency_ms": latency_ms},
        )
        return DbHealthResult(
            ok=False,
            status="FAIL",
            latency_ms=latency_ms,
            correlation_id=corr_id,
            error_class=type(exc).__name__,
            error_message=str(exc)[:120],
        )
