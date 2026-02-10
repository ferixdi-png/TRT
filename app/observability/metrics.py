"""
Prometheus-compatible metrics export for observability.

Provides /metrics endpoint with key application metrics:
- Request counts and latencies
- Generation job stats
- Circuit breaker states
- Database and Redis health
"""

import asyncio
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Global metrics storage
_metrics: Dict[str, float] = defaultdict(float)
_metric_labels: Dict[str, Dict[str, str]] = {}
_start_time: float = time.time()


@dataclass
class MetricValue:
    """Single metric value with optional labels."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    metric_type: str = "gauge"  # gauge, counter, histogram
    help_text: str = ""


def increment_counter(name: str, value: float = 1.0, **labels) -> None:
    """Increment a counter metric."""
    key = _build_key(name, labels)
    _metrics[key] += value
    _metric_labels[key] = {"name": name, "type": "counter", "labels": labels}


def set_gauge(name: str, value: float, **labels) -> None:
    """Set a gauge metric value."""
    key = _build_key(name, labels)
    _metrics[key] = value
    _metric_labels[key] = {"name": name, "type": "gauge", "labels": labels}


def _build_key(name: str, labels: Dict[str, str]) -> str:
    """Build unique key from name and labels."""
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_str}}}"


async def collect_metrics() -> Dict[str, MetricValue]:
    """Collect all current metrics."""
    metrics = {}
    
    # Uptime
    uptime = time.time() - _start_time
    metrics["trt_uptime_seconds"] = MetricValue(
        name="trt_uptime_seconds",
        value=uptime,
        metric_type="gauge",
        help_text="Time since application start in seconds",
    )
    
    # Collect storage metrics
    try:
        from app.storage.factory import get_storage
        storage = get_storage()
        
        # Circuit breaker state
        if hasattr(storage, "_circuit_open_until"):
            cb_open = 1.0 if storage._circuit_open_until and time.time() < storage._circuit_open_until else 0.0
            metrics["trt_circuit_breaker_open"] = MetricValue(
                name="trt_circuit_breaker_open",
                value=cb_open,
                labels={"component": "postgres"},
                metric_type="gauge",
                help_text="Circuit breaker state (1=open, 0=closed)",
            )
        
        # Pool stats
        if hasattr(storage, "_get_pool"):
            try:
                pool = await storage._get_pool()
                if pool:
                    pool_size = pool.get_size() if hasattr(pool, "get_size") else 0
                    pool_idle = pool.get_idle_size() if hasattr(pool, "get_idle_size") else 0
                    pool_max = pool.get_max_size() if hasattr(pool, "get_max_size") else 0
                    
                    metrics["trt_db_pool_size"] = MetricValue(
                        name="trt_db_pool_size",
                        value=float(pool_size),
                        metric_type="gauge",
                        help_text="Current database connection pool size",
                    )
                    metrics["trt_db_pool_idle"] = MetricValue(
                        name="trt_db_pool_idle",
                        value=float(pool_idle),
                        metric_type="gauge",
                        help_text="Idle connections in pool",
                    )
                    metrics["trt_db_pool_max"] = MetricValue(
                        name="trt_db_pool_max",
                        value=float(pool_max),
                        metric_type="gauge",
                        help_text="Max pool size",
                    )
                    metrics["trt_db_pool_in_use"] = MetricValue(
                        name="trt_db_pool_in_use",
                        value=float(pool_size - pool_idle),
                        metric_type="gauge",
                        help_text="Connections currently in use",
                    )
            except Exception as e:
                logger.debug("Failed to collect pool metrics: %s", e)
    except Exception as e:
        logger.debug("Failed to collect storage metrics: %s", e)
    
    # Collect Redis metrics
    try:
        from app.utils.distributed_lock import get_redis_client
        redis_client = await get_redis_client()
        redis_available = 1.0 if redis_client else 0.0
        metrics["trt_redis_available"] = MetricValue(
            name="trt_redis_available",
            value=redis_available,
            metric_type="gauge",
            help_text="Redis availability (1=available, 0=unavailable)",
        )
    except Exception as e:
        logger.debug("Failed to collect Redis metrics: %s", e)
    
    # Add stored counters/gauges
    for key, value in _metrics.items():
        meta = _metric_labels.get(key, {})
        name = meta.get("name", key)
        labels = meta.get("labels", {})
        metric_type = meta.get("type", "gauge")
        
        metrics[key] = MetricValue(
            name=name,
            value=value,
            labels=labels,
            metric_type=metric_type,
        )
    
    return metrics


def format_prometheus(metrics: Dict[str, MetricValue]) -> str:
    """Format metrics in Prometheus text format."""
    lines = []
    
    # Group by metric name for HELP and TYPE
    seen_names = set()
    
    for key, metric in sorted(metrics.items()):
        name = metric.name
        
        # Add HELP and TYPE once per metric name
        if name not in seen_names:
            seen_names.add(name)
            if metric.help_text:
                lines.append(f"# HELP {name} {metric.help_text}")
            lines.append(f"# TYPE {name} {metric.metric_type}")
        
        # Format metric line
        if metric.labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(metric.labels.items()))
            lines.append(f"{name}{{{label_str}}} {metric.value}")
        else:
            lines.append(f"{name} {metric.value}")
    
    return "\n".join(lines) + "\n"


async def metrics_handler(request) -> "web.Response":
    """aiohttp handler for /metrics endpoint."""
    from aiohttp import web
    
    try:
        metrics = await collect_metrics()
        body = format_prometheus(metrics)
        return web.Response(
            text=body,
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )
    except Exception as e:
        logger.error("Failed to collect metrics: %s", e)
        return web.Response(
            text=f"# Error collecting metrics: {e}\n",
            content_type="text/plain",
            status=500,
        )
