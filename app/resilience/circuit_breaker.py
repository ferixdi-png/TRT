"""
Circuit Breaker pattern implementation for external services.

Prevents cascade failures by tracking error rates and opening circuit
when failure threshold is exceeded.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures exceeded threshold, fast-fail all requests
- HALF_OPEN: Recovery testing, allow limited requests

PR-3: Circuit Breaker для KIE API (HIGH priority)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Fast-fail mode (failure threshold exceeded)
    HALF_OPEN = "half_open"  # Recovery testing mode


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5  # Open circuit after N consecutive failures
    success_threshold: int = 2  # Close circuit after N consecutive successes in HALF_OPEN
    timeout: float = 60.0  # Seconds to wait before attempting HALF_OPEN
    name: str = "default"  # Circuit breaker name for logging


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.monotonic)
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_rejected: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit breaker rejects request."""
    def __init__(self, name: str, state: CircuitState, until: Optional[float] = None):
        self.name = name
        self.state = state
        self.until = until
        if until:
            wait_seconds = int(until - time.monotonic())
            super().__init__(
                f"Circuit breaker '{name}' is {state.value}. "
                f"Retry after {wait_seconds}s."
            )
        else:
            super().__init__(f"Circuit breaker '{name}' is {state.value}.")


class CircuitBreaker:
    """
    Circuit breaker implementation for protecting external service calls.
    
    Usage:
        breaker = CircuitBreaker(config=CircuitBreakerConfig(
            failure_threshold=5,
            timeout=60.0,
            name="kie_api"
        ))
        
        try:
            result = await breaker.call(kie_client.create_task, model_id, input_data)
        except CircuitBreakerError as e:
            logger.warning("Circuit open: %s", e)
            # Return cached result or show error to user
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async callable to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            CircuitBreakerError: If circuit is OPEN
            Any exception from func if circuit is CLOSED/HALF_OPEN
        """
        async with self._lock:
            self.stats.total_requests += 1
            
            # Check if circuit should transition to HALF_OPEN
            if self.stats.state == CircuitState.OPEN:
                if self.stats.last_failure_time:
                    elapsed = time.monotonic() - self.stats.last_failure_time
                    if elapsed >= self.config.timeout:
                        self._transition_to(CircuitState.HALF_OPEN)
                        logger.info(
                            "CIRCUIT_BREAKER_HALF_OPEN name=%s timeout_elapsed=%.1fs",
                            self.config.name,
                            elapsed,
                        )
            
            # Reject request if circuit is OPEN
            if self.stats.state == CircuitState.OPEN:
                self.stats.total_rejected += 1
                retry_after = self.stats.last_failure_time + self.config.timeout if self.stats.last_failure_time else None
                logger.warning(
                    "CIRCUIT_BREAKER_REJECT name=%s state=%s failures=%s rejected=%s",
                    self.config.name,
                    self.stats.state.value,
                    self.stats.total_failures,
                    self.stats.total_rejected,
                )
                raise CircuitBreakerError(
                    name=self.config.name,
                    state=self.stats.state,
                    until=retry_after,
                )
        
        # Execute request (outside lock to allow concurrent requests in CLOSED state)
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as exc:
            await self._on_failure(exc)
            raise

    async def _on_success(self) -> None:
        """Handle successful request."""
        async with self._lock:
            self.stats.total_successes += 1
            self.stats.failure_count = 0  # Reset failure counter
            
            if self.stats.state == CircuitState.HALF_OPEN:
                self.stats.success_count += 1
                if self.stats.success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        "CIRCUIT_BREAKER_CLOSED name=%s successes=%s/%s",
                        self.config.name,
                        self.stats.success_count,
                        self.config.success_threshold,
                    )

    async def _on_failure(self, exc: Exception) -> None:
        """Handle failed request."""
        async with self._lock:
            self.stats.total_failures += 1
            self.stats.failure_count += 1
            self.stats.last_failure_time = time.monotonic()
            
            if self.stats.state == CircuitState.HALF_OPEN:
                # Immediately open circuit on failure in HALF_OPEN
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    "CIRCUIT_BREAKER_OPEN name=%s reason=half_open_failure error=%s",
                    self.config.name,
                    type(exc).__name__,
                )
            elif self.stats.state == CircuitState.CLOSED:
                if self.stats.failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.error(
                        "CIRCUIT_BREAKER_OPEN name=%s failures=%s/%s error=%s",
                        self.config.name,
                        self.stats.failure_count,
                        self.config.failure_threshold,
                        type(exc).__name__,
                    )

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition circuit to new state (must be called under lock)."""
        old_state = self.stats.state
        self.stats.state = new_state
        self.stats.last_state_change = time.monotonic()
        
        if new_state == CircuitState.HALF_OPEN:
            self.stats.success_count = 0  # Reset success counter for HALF_OPEN test
        elif new_state == CircuitState.CLOSED:
            self.stats.failure_count = 0
            self.stats.success_count = 0
        
        logger.info(
            "CIRCUIT_BREAKER_TRANSITION name=%s from=%s to=%s total_failures=%s total_successes=%s",
            self.config.name,
            old_state.value,
            new_state.value,
            self.stats.total_failures,
            self.stats.total_successes,
        )

    def get_stats(self) -> dict:
        """Get current circuit breaker statistics."""
        return {
            "name": self.config.name,
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_requests": self.stats.total_requests,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "total_rejected": self.stats.total_rejected,
            "last_failure_time": self.stats.last_failure_time,
            "last_state_change": self.stats.last_state_change,
        }

    async def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        async with self._lock:
            logger.info(
                "CIRCUIT_BREAKER_RESET name=%s old_state=%s",
                self.config.name,
                self.stats.state.value,
            )
            self.stats = CircuitBreakerStats()
