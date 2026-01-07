"""
Integration of payments with generation flow.
Ensures charges are only committed on success.
Handles FREE tier models (no charge).
"""
import logging
from app.utils.trace import TraceContext, get_request_id
import asyncio
import time
from typing import Dict, Any, Optional, Callable
from uuid import uuid4

from app.utils.payload_hash import payload_hash

from app.payments.charges import ChargeManager, get_charge_manager
from app.kie.builder import get_model_config
from app.kie.generator import KieGenerator, KieGenerator as RealKieGenerator

# Legacy alias for tests/old imports
KIEAPIService = KieGenerator
from app.utils.metrics import track_generation
from app.pricing.free_models import is_free_model
from app.database.services import UserService
from app.utils.config import REFERRAL_MAX_RUB
from app.database.generation_events import log_generation_event


async def _add_to_history_safe(charge_manager: ChargeManager, user_id: int, model_id: str, inputs: Dict[str, Any], result: str, success: bool) -> None:
    """Call charge_manager.add_to_history if present; await if coroutine."""
    history_fn = getattr(charge_manager, "add_to_history", None)
    if not history_fn:
        return

    maybe_history = history_fn(user_id, model_id, inputs, result, success)
    if asyncio.iscoroutine(maybe_history):
        await maybe_history

logger = logging.getLogger(__name__)


def _normalize_gen_result(gen_result: dict) -> dict:
    """Backward/forward compatible generation result normalization.

    UI layers historically expect `output_url`, while newer generator returns `result_urls`.
    """
    if not isinstance(gen_result, dict):
        return {"success": False, "message": "Invalid generation result"}
    urls = gen_result.get("result_urls") or []
    if not gen_result.get("output_url") and urls:
        gen_result["output_url"] = urls[0]
    # Keep a stable alias for multi-output
    if not gen_result.get("output_urls") and urls:
        gen_result["output_urls"] = list(urls)
    return gen_result


def _build_generate_kwargs(generator: KieGenerator, model_id: str, user_inputs: Dict[str, Any], progress_callback: Optional[Any], timeout: int) -> Dict[str, Any]:
    """Support mocks expecting `inputs` while real generator uses `user_inputs`."""
    base = {
        "model_id": model_id,
        "progress_callback": progress_callback,
        "timeout": timeout,
    }
    try:
        use_user_inputs = isinstance(generator, RealKieGenerator)
    except TypeError:
        use_user_inputs = False
    if use_user_inputs:
        base["user_inputs"] = user_inputs
    else:
        base["inputs"] = user_inputs
    return base


def _get_generator_instance() -> KieGenerator:
    cls = KieGenerator
    if cls is RealKieGenerator and callable(globals().get("KIEAPIService")):
        cls = globals()["KIEAPIService"]
    if not callable(cls):
        cls = RealKieGenerator
    return cls()


async def generate_with_payment(
    model_id: str,
    user_inputs: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,  # Explicit backward compat arg
    user_id: int = None,
    amount: float = 0.0,
    progress_callback: Optional[Any] = None,
    timeout: int = 300,
    task_id: Optional[str] = None,
    reserve_balance: bool = False,
    charge_manager: Optional[ChargeManager] = None,
    task_id_callback: Optional[Callable[..., Any]] = None,
    **kwargs  # Catch-all for unknown args (never crash)
) -> Dict[str, Any]:
    """
    Generate with payment safety guarantees (BACKWARD COMPATIBLE).
    
    CRITICAL: This function NEVER crashes on unexpected arguments.
    Accepts both user_inputs= and payload= (aliases).
    
    - FREE models: no charge
    - Paid models: charge only on success, auto-refund on fail/timeout
    
    Args:
        model_id: Model identifier
        user_inputs: User inputs (PREFERRED)
        payload: User inputs (backward compat alias - DEPRECATED)
        user_id: User identifier
        amount: Charge amount (ignored for FREE models)
        progress_callback: Progress callback
        timeout: Generation timeout
        **kwargs: Catch-all for unknown args (prevents TypeError)
        
    Returns:
        Result dict with generation and payment info
    """
    # === BACKWARD COMPATIBILITY LAYER ===
    # Priority: user_inputs > payload > empty dict
    if user_inputs is not None and payload is not None:
        # Both provided - log warning and prioritize user_inputs
        logger.warning(
            f"⚠️ Both user_inputs and payload provided - using user_inputs "
            f"(user_inputs keys: {list(user_inputs.keys()) if user_inputs else []}, "
            f"payload keys: {list(payload.keys()) if payload else []})"
        )
    
    if user_inputs is None and payload is not None:
        logger.debug(f"🔄 Backward compat: payload->user_inputs (keys: {list(payload.keys()) if payload else []})")
        user_inputs = payload
    elif user_inputs is None:
        user_inputs = {}

    ph = payload_hash({"model": model_id, "inputs": user_inputs})
    
    # Handle legacy user_id from kwargs
    if user_id is None and "user_id" in kwargs:
        user_id = kwargs["user_id"]
    
    # Log any unknown kwargs (helps debug if old code passes weird params)
    known_kwargs = {'user_id'}
    unknown = set(kwargs.keys()) - known_kwargs
    if unknown:
        logger.debug(f"🔧 Ignored unknown kwargs: {unknown}")
    
    # Request-scoped trace (correlation id for logs)
    with TraceContext(user_id=user_id, model_id=model_id, request_id=(get_request_id() if get_request_id() != '-' else None)) as _trace:
        logger.info(f"▶️ generate_with_payment start amount={amount} reserve_balance={reserve_balance} timeout={timeout}s")
        
        # Resolve db_service for generation event logging
        if charge_manager is None:
            charge_manager = get_charge_manager()
        db_service = getattr(charge_manager, 'db_service', None)

        # AMOUNT_SAFEGUARD: if caller passed 0/None for paid models, compute price from source-of-truth
        if (amount is None or float(amount) <= 0.0) and not is_free_model(model_id):
            try:
                from app.payments.pricing import get_price_breakdown
                from app.kie.builder import get_model_config

                model_cfg = get_model_config(model_id)
                if not isinstance(model_cfg, dict):
                    raise ValueError("model config not found")
                # Ensure model_id exists for pricing module
                model_cfg = dict(model_cfg)
                model_cfg.setdefault("model_id", model_id)

                breakdown = get_price_breakdown(model_cfg, user_inputs)
                amount = float(breakdown.user_price_rub)
                logger.info(f"💰 Amount auto-computed: {amount:.2f} RUB")
            except Exception as e:
                logger.warning(f"Failed to auto-compute amount: {e}")
        
        # Check if model is FREE (TOP-5 cheapest)
        if is_free_model(model_id):
            logger.info(f"🆓 Model {model_id} is FREE - skipping payment")
            
            # Log generation start
            request_id = get_request_id()
            if db_service:
                await log_generation_event(
                    db_service,
                    user_id=user_id,
                    chat_id=None,
                    model_id=model_id,
                    category=None,
                    status='started',
                    is_free_applied=True,
                    price_rub=0.0,
                    request_id=request_id,
                    task_id=None
                )
            else:
                logger.info("db_service not available - skipping generation event log (start)")
            
            generator = _get_generator_instance()
            start_time = time.time()
            kw = _build_generate_kwargs(generator, model_id, user_inputs, progress_callback, timeout)
            if task_id_callback is not None:
                kw["task_id_callback"] = task_id_callback
            gen_result = await generator.generate(**kw)
            gen_result = _normalize_gen_result(gen_result)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log completion
            success = gen_result.get('success', False)
            if db_service:
                await log_generation_event(
                    db_service,
                    user_id=user_id,
                    chat_id=None,
                    model_id=model_id,
                    category=None,
                    status='success' if success else 'failed',
                    is_free_applied=True,
                    price_rub=0.0,
                    request_id=request_id,
                    task_id=gen_result.get('task_id'),
                    error_code=gen_result.get('error_code') if not success else None,
                    error_message=gen_result.get('message') if not success else None,
                    duration_ms=duration_ms
                )
            else:
                logger.info("db_service not available - skipping generation event log (complete)")
            
            return {
                **gen_result,
                'charge_task_id': None,
                'payment_status': 'free_tier',
                'payment_message': '🆓 FREE модель - генерация бесплатна'
            }
        
        # Paid model - proceed with charging (or apply referral-free uses if available)
        generator = _get_generator_instance()
        
        # Referral-free: limited бесплатные генерации за приглашения
        referral_used = False
        referral_uses_left: Optional[int] = None
        try:
            db = getattr(charge_manager, "db_service", None)
            if db is not None and amount <= REFERRAL_MAX_RUB:
                user_service = UserService(db)
                meta = await user_service.get_metadata(user_id)
                referral_uses_left = int(meta.get("referral_free_uses", 0) or 0)
                if referral_uses_left > 0:
                    await user_service.increment_metadata_counter(user_id, "referral_free_uses", -1, min_value=0)
                    referral_used = True
                    referral_uses_left -= 1
                    logger.info(
                        f"🎁 Referral-free used: user={user_id} model={model_id} amount={amount:.2f} cap={REFERRAL_MAX_RUB:.2f} left={referral_uses_left}"
                    )
        except Exception as e:
            logger.warning(f"Referral-free precheck failed (continuing with normal charging): {e}")
        
        if referral_used:
            request_id = get_request_id()
            
            # Log start
            if db_service:
                await log_generation_event(
                    db_service,
                    user_id=user_id,
                    chat_id=None,
                    model_id=model_id,
                    category=None,
                    status='started',
                    is_free_applied=False,  # Paid model, but using referral bonus
                    price_rub=0.0,  # No charge due to referral
                    request_id=request_id,
                    task_id=None
                )
            else:
                logger.info("db_service not available - skipping generation event log (referral start)")
            
            start_time = time.time()
            try:
                kw = _build_generate_kwargs(generator, model_id, user_inputs, progress_callback, timeout)
                if task_id_callback is not None:
                    kw["task_id_callback"] = task_id_callback
                gen_result = await generator.generate(**kw)
            except asyncio.CancelledError:
                # user cancelled — restore referral free use
                try:
                    db = getattr(charge_manager, "db_service", None)
                    if db is not None:
                        await UserService(db).increment_metadata_counter(user_id, "referral_free_uses", +1)
                except Exception as e:
                    logger.warning(f"Failed to restore referral-free use after cancel: {e}")
                raise
            duration_ms = int((time.time() - start_time) * 1000)
        
            success = gen_result.get('success', False)
            
            # Log completion
            if db_service:
                await log_generation_event(
                    db_service,
                    user_id=user_id,
                    chat_id=None,
                    model_id=model_id,
                    category=None,
                    status='success' if success else 'failed',
                    is_free_applied=False,
                    price_rub=0.0,
                    request_id=request_id,
                    task_id=gen_result.get('task_id'),
                    error_code=gen_result.get('error_code') if not success else None,
                    error_message=gen_result.get('message') if not success else None,
                    duration_ms=duration_ms
                )
            else:
                logger.info("db_service not available - skipping generation event log (referral complete)")
            
            await track_generation(
                model_id=model_id,
                success=success,
                duration=duration_ms / 1000.0,
                price_rub=0.0
            )
        
            if success:
                result_urls = gen_result.get('result_urls', [])
                result_text = '\n'.join(result_urls) if result_urls else 'Success'
                await _add_to_history_safe(charge_manager, user_id, model_id, user_inputs, result_text, True)
                return {
                    **gen_result,
                    'charge_task_id': None,
                    'payment_status': 'referral_free',
                    'payment_message': f'🎁 Бесплатная генерация за приглашения (осталось: {referral_uses_left})'
                }
        
            # FAIL/TIMEOUT: return referral use back
            try:
                db = getattr(charge_manager, "db_service", None)
                if db is not None:
                    await UserService(db).increment_metadata_counter(user_id, "referral_free_uses", +1)
            except Exception as e:
                logger.warning(f"Failed to restore referral-free use after failure: {e}")
        
            error_msg = gen_result.get('message', 'Failed')
            await _add_to_history_safe(charge_manager, user_id, model_id, user_inputs, error_msg, False)
            return {
                **gen_result,
                'charge_task_id': None,
                'payment_status': 'referral_free_failed',
                'payment_message': '⚠️ Генерация не удалась, бесплатная попытка возвращена'
            }
        charge_task_id = task_id or f"charge_{user_id}_{model_id}_{uuid4().hex[:8]}"
        
        # Create pending charge
        pending_charge = charge_manager.create_pending_charge(
            task_id=charge_task_id,
            user_id=user_id,
            amount=amount,
            model_id=model_id,
            reserve_balance=reserve_balance
        )
        charge_result = await pending_charge if asyncio.iscoroutine(pending_charge) else pending_charge
        
        if charge_result['status'] == 'already_committed':
            # Already paid, just generate
            try:
                kw = _build_generate_kwargs(generator, model_id, user_inputs, progress_callback, timeout)
                if task_id_callback is not None:
                    kw["task_id_callback"] = task_id_callback
                gen_result = await generator.generate(**kw)
            except asyncio.CancelledError:
                # Charge already committed; treat cancel as stopping the wait only
                raise
            gen_result = _normalize_gen_result(gen_result)
            return {
                **gen_result,
                'charge_task_id': charge_task_id,
                'payment_status': 'already_committed',
                'payment_message': 'Оплата уже подтверждена'
            }
        if charge_result['status'] == 'insufficient_balance':
            return {
                'success': False,
                'message': '❌ Недостаточно средств. Пополните баланс и попробуйте снова.',
                'result_urls': [],
                'result_object': None,
                'error_code': 'INSUFFICIENT_BALANCE',
                'error_message': 'Insufficient balance',
                'task_id': None,
                'charge_task_id': charge_task_id,
                'payment_status': charge_result['status'],
                'payment_message': charge_result['message']
            }
        
        # Generate
        request_id = get_request_id()
        
        # Log generation start
        if db_service:
            await log_generation_event(
                db_service,
                user_id=user_id,
                chat_id=None,
                model_id=model_id,
                category=None,
                status='started',
                is_free_applied=False,
                price_rub=amount,
                request_id=request_id,
                task_id=charge_task_id
            )
        else:
            logger.info("db_service not available - skipping generation event log (paid start)")
        
        start_time = time.time()
        try:
            kw = _build_generate_kwargs(generator, model_id, user_inputs, progress_callback, timeout)
            if task_id_callback is not None:
                kw["task_id_callback"] = task_id_callback
            gen_result = await generator.generate(**kw)
        except asyncio.CancelledError:
            # user cancelled — release reserved/pending charge
            try:
                await charge_manager.release_charge(charge_task_id, reason="cancelled")
            except Exception as e:
                logger.warning(f"Failed to release charge after cancel: {e}")
            raise
        gen_result = _normalize_gen_result(gen_result)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Track metrics
        success = gen_result.get('success', False)
        await track_generation(
            model_id=model_id,
            success=success,
            duration=duration_ms / 1000.0,
            price_rub=amount if success else 0.0
        )
        
        # Determine task_id from generation (if available)
        # Commit or release charge based on generation result
        if gen_result.get('success'):
            # SUCCESS: Commit charge
            commit = charge_manager.commit_charge(charge_task_id)
            commit_result = await commit if asyncio.iscoroutine(commit) else commit
            
            # Log success
            if db_service:
                await log_generation_event(
                    db_service,
                    user_id=user_id,
                    chat_id=None,
                    model_id=model_id,
                    category=None,
                    status='success',
                    is_free_applied=False,
                    price_rub=amount,
                    request_id=request_id,
                    task_id=gen_result.get('task_id') or charge_task_id,
                    duration_ms=duration_ms
                )
            else:
                logger.info("db_service not available - skipping generation event log (paid success)")
            
            # Add to history
            result_urls = gen_result.get('result_urls', [])
            result_text = '\n'.join(result_urls) if result_urls else 'Success'
            await _add_to_history_safe(charge_manager, user_id, model_id, user_inputs, result_text, True)
            return {
                **gen_result,
                'charge_task_id': charge_task_id,
                'payment_status': commit_result['status'],
                'payment_message': commit_result['message']
            }
        else:
            # FAIL/TIMEOUT: Release charge (auto-refund)
            error_code = gen_result.get('error_code', 'generation_failed')
            error_message = gen_result.get('message', 'Failed')
            
            # Log failure
            if db_service:
                await log_generation_event(
                    db_service,
                    user_id=user_id,
                    chat_id=None,
                    model_id=model_id,
                    category=None,
                    status='timeout' if error_code == 'TIMEOUT' else 'failed',
                    is_free_applied=False,
                    price_rub=0.0,  # Not charged due to failure
                    request_id=request_id,
                    task_id=gen_result.get('task_id') or charge_task_id,
                    error_code=error_code,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            else:
                logger.info("db_service not available - skipping generation event log (paid failure)")
            
            release = charge_manager.release_charge(
                charge_task_id,
                reason=error_code
            )
            release_result = await release if asyncio.iscoroutine(release) else release
        # Add to history (sync or async impl)
        await _add_to_history_safe(charge_manager, user_id, model_id, user_inputs, error_message, False)
        return {
            **gen_result,
            'charge_task_id': charge_task_id,
            'payment_status': release_result['status'],
            'payment_message': release_result['message']
            }
