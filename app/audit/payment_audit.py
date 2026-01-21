"""
Payment Audit Logger - immutable audit trail for all balance changes.

PR-4: Payment Audit Logging (MEDIUM priority)

This module provides structured logging for all balance-related operations:
- Top-ups (payment, admin manual, referral bonus)
- Deductions (generation costs)
- Refunds

All events are logged with:
- correlation_id for tracing
- user_id and admin_id (if applicable)
- before/after balance
- amount and operation type
- timestamp

Events are written to structured logs for forensic analysis and compliance.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from app.utils.logging_config import get_logger
from app.observability.structured_logs import log_structured_event

logger = get_logger(__name__)


class BalanceOperation(str, Enum):
    """Balance operation types."""
    TOPUP_PAYMENT = "topup_payment"  # User paid via payment gateway
    TOPUP_ADMIN = "topup_admin"  # Admin manual top-up
    TOPUP_REFERRAL = "topup_referral"  # Referral bonus
    TOPUP_PROMO = "topup_promo"  # Promo code
    DEDUCT_GENERATION = "deduct_generation"  # Generation cost
    REFUND_FAILED_TASK = "refund_failed_task"  # Refund for failed task
    REFUND_ADMIN = "refund_admin"  # Admin manual refund
    ADJUSTMENT_ADMIN = "adjustment_admin"  # Admin balance adjustment


def log_payment_audit(
    *,
    user_id: int,
    operation: BalanceOperation,
    amount: float,
    balance_before: float,
    balance_after: float,
    correlation_id: Optional[str] = None,
    admin_id: Optional[int] = None,
    task_id: Optional[str] = None,
    model_id: Optional[str] = None,
    payment_id: Optional[str] = None,
    referrer_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    """
    Log immutable audit event for balance change.
    
    Args:
        user_id: User whose balance changed
        operation: Type of operation (TOPUP_PAYMENT, DEDUCT_GENERATION, etc.)
        amount: Amount changed (positive for top-up, negative for deduction)
        balance_before: Balance before operation
        balance_after: Balance after operation
        correlation_id: Request correlation ID for tracing
        admin_id: Admin who performed operation (if applicable)
        task_id: KIE task ID (for generation deductions)
        model_id: Model used (for generation deductions)
        payment_id: Payment gateway transaction ID
        referrer_id: Referrer user ID (for referral bonuses)
        reason: Human-readable reason for operation
    """
    timestamp = time.time()
    
    # Validate consistency
    expected_balance = balance_before + amount
    if abs(expected_balance - balance_after) > 0.01:
        logger.error(
            "PAYMENT_AUDIT_INCONSISTENCY user_id=%s operation=%s balance_before=%.2f amount=%.2f "
            "balance_after=%.2f expected=%.2f diff=%.4f",
            user_id,
            operation.value,
            balance_before,
            amount,
            balance_after,
            expected_balance,
            balance_after - expected_balance,
        )
    
    # Log structured event for querying and forensics
    log_structured_event(
        correlation_id=correlation_id,
        user_id=user_id,
        action="PAYMENT_AUDIT",
        action_path=f"audit>{operation.value}",
        stage="PAYMENT_AUDIT",
        outcome="logged",
        error_code="PAYMENT_AUDIT_OK",
        fix_hint="Audit event recorded.",
        param={
            "operation": operation.value,
            "amount": amount,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "admin_id": admin_id,
            "task_id": task_id,
            "model_id": model_id,
            "payment_id": payment_id,
            "referrer_id": referrer_id,
            "reason": reason,
            "timestamp": timestamp,
        },
    )
    
    # Also log as structured audit line for easy grepping
    logger.info(
        "PAYMENT_AUDIT operation=%s user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f "
        "admin_id=%s task_id=%s model_id=%s payment_id=%s referrer_id=%s reason=%s corr=%s",
        operation.value,
        user_id,
        amount,
        balance_before,
        balance_after,
        admin_id or "-",
        task_id or "-",
        model_id or "-",
        payment_id or "-",
        referrer_id or "-",
        reason or "-",
        correlation_id or "-",
    )


def log_topup_payment(
    user_id: int,
    amount: float,
    balance_before: float,
    balance_after: float,
    payment_id: str,
    correlation_id: Optional[str] = None,
) -> None:
    """Log payment gateway top-up."""
    log_payment_audit(
        user_id=user_id,
        operation=BalanceOperation.TOPUP_PAYMENT,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        payment_id=payment_id,
        correlation_id=correlation_id,
        reason="Payment gateway top-up",
    )


def log_topup_admin(
    user_id: int,
    amount: float,
    balance_before: float,
    balance_after: float,
    admin_id: int,
    correlation_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Log admin manual top-up."""
    log_payment_audit(
        user_id=user_id,
        operation=BalanceOperation.TOPUP_ADMIN,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        admin_id=admin_id,
        correlation_id=correlation_id,
        reason=reason or "Admin manual top-up",
    )


def log_topup_referral(
    user_id: int,
    amount: float,
    balance_before: float,
    balance_after: float,
    referrer_id: int,
    correlation_id: Optional[str] = None,
) -> None:
    """Log referral bonus top-up."""
    log_payment_audit(
        user_id=user_id,
        operation=BalanceOperation.TOPUP_REFERRAL,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        referrer_id=referrer_id,
        correlation_id=correlation_id,
        reason="Referral bonus",
    )


def log_deduct_generation(
    user_id: int,
    amount: float,
    balance_before: float,
    balance_after: float,
    task_id: str,
    model_id: str,
    correlation_id: Optional[str] = None,
) -> None:
    """Log generation cost deduction."""
    log_payment_audit(
        user_id=user_id,
        operation=BalanceOperation.DEDUCT_GENERATION,
        amount=-abs(amount),  # Ensure negative
        balance_before=balance_before,
        balance_after=balance_after,
        task_id=task_id,
        model_id=model_id,
        correlation_id=correlation_id,
        reason="Generation cost",
    )


def log_refund_failed_task(
    user_id: int,
    amount: float,
    balance_before: float,
    balance_after: float,
    task_id: str,
    model_id: str,
    correlation_id: Optional[str] = None,
) -> None:
    """Log refund for failed task."""
    log_payment_audit(
        user_id=user_id,
        operation=BalanceOperation.REFUND_FAILED_TASK,
        amount=abs(amount),  # Ensure positive
        balance_before=balance_before,
        balance_after=balance_after,
        task_id=task_id,
        model_id=model_id,
        correlation_id=correlation_id,
        reason="Refund for failed task",
    )
