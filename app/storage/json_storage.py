"""
JSON storage implementation - хранение данных в JSON файлах
Атомарная запись (temp+rename), filelock для безопасности
"""

import os
import json
import asyncio
import logging
import math
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import uuid
import aiofiles

from app.storage.base import BaseStorage

# Опциональный импорт filelock (мягкая деградация)
try:
    from filelock import FileLock, Timeout
    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False
    pass

logger = logging.getLogger(__name__)


class JsonStorage(BaseStorage):
    """JSON storage implementation"""
    
    def __init__(self, data_dir: str = "./data", bot_instance_id: Optional[str] = None):
        self.bot_instance_id = (bot_instance_id or os.getenv("BOT_INSTANCE_ID") or "").strip()
        if not self.bot_instance_id:
            self.bot_instance_id = "default"
            logger.warning("BOT_INSTANCE_ID missing; JSON storage defaulting to tenant=%s", self.bot_instance_id)
        self.partner_id = self.bot_instance_id
        base_dir = Path(data_dir)
        if self.bot_instance_id:
            if self.bot_instance_id not in base_dir.parts:
                base_dir = base_dir / self.bot_instance_id
        self.data_dir = base_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Файлы
        self.balances_file = self.data_dir / "user_balances.json"
        self.languages_file = self.data_dir / "user_languages.json"
        self.gift_claimed_file = self.data_dir / "gift_claimed.json"
        self.free_generations_file = self.data_dir / "daily_free_generations.json"
        self.free_deductions_file = self.data_dir / "free_deductions.json"
        self.hourly_free_usage_file = self.data_dir / "hourly_free_usage.json"
        self.referral_free_bank_file = self.data_dir / "referral_free_bank.json"
        self.admin_limits_file = self.data_dir / "admin_limits.json"
        self.balance_deductions_file = self.data_dir / "balance_deductions.json"
        self.generations_history_file = self.data_dir / "generations_history.json"
        self.payments_file = self.data_dir / "payments.json"
        self.referrals_file = self.data_dir / "referrals.json"
        self.jobs_file = self.data_dir / "generation_jobs.json"
        
        # Инициализируем файлы если их нет
        self._init_files()
    
    def _init_files(self):
        """Инициализирует JSON файлы если их нет"""
        files = [
            self.balances_file,
            self.languages_file,
            self.gift_claimed_file,
            self.free_generations_file,
            self.hourly_free_usage_file,
            self.referral_free_bank_file,
            self.admin_limits_file,
            self.balance_deductions_file,
            self.free_deductions_file,
            self.generations_history_file,
            self.payments_file,
            self.referrals_file,
            self.jobs_file,
        ]
        for file in files:
            if not file.exists():
                try:
                    file.write_text("{}", encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to create {file}: {e}")
    
    def _get_lock_file(self, file_path: Path) -> Path:
        """Получает путь к lock файлу"""
        return file_path.parent / f".{file_path.name}.lock"
    
    async def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """Загружает JSON файл"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                if not content.strip():
                    return {}
                payload = json.loads(content)
                if isinstance(payload, dict):
                    return payload
                if isinstance(payload, str):
                    try:
                        nested = json.loads(payload)
                    except json.JSONDecodeError:
                        nested = None
                    if isinstance(nested, dict):
                        return nested
                correlation_id = uuid.uuid4().hex[:8]
                logger.warning(
                    "STORAGE_JSON_TYPE_INVALID correlation_id=%s file=%s payload_type=%s",
                    correlation_id,
                    file_path,
                    type(payload).__name__,
                )
                return {}
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in {file_path}, returning empty dict")
            return {}
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return {}
    
    async def _save_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Сохраняет JSON файл атомарно (temp file + rename)"""
        if FILELOCK_AVAILABLE:
            lock_file = self._get_lock_file(file_path)
            lock = FileLock(lock_file, timeout=5)
            
            try:
                with lock:
                    # Создаем временный файл
                    temp_file = file_path.with_suffix('.tmp')
                    async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
                    
                    # Атомарно переименовываем
                    temp_file.replace(file_path)
            except Timeout:
                logger.error(f"Timeout acquiring lock for {file_path}")
                raise
            except Exception as e:
                logger.error(f"Error saving {file_path}: {e}")
                raise
        else:
            # Без filelock - просто сохраняем (риск race conditions, но работает)
            temp_file = file_path.with_suffix('.tmp')
            async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            temp_file.replace(file_path)
    
    # ==================== USER OPERATIONS ====================
    
    async def get_user(self, user_id: int, upsert: bool = True) -> Dict[str, Any]:
        """Получить данные пользователя"""
        balance = await self.get_user_balance(user_id)
        language = await self.get_user_language(user_id)
        gift_claimed = await self.has_claimed_gift(user_id)
        referrer_id = await self.get_referrer(user_id)
        
        return {
            'user_id': user_id,
            'balance': balance,
            'language': language,
            'gift_claimed': gift_claimed,
            'referrer_id': referrer_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
    
    async def get_user_balance(self, user_id: int) -> float:
        """Получить баланс пользователя"""
        data = await self._load_json(self.balances_file)
        return float(data.get(str(user_id), 0.0))
    
    async def set_user_balance(self, user_id: int, amount: float) -> None:
        """Установить баланс пользователя"""
        # PR-4: Get balance before change for audit logging
        balance_before = await self.get_user_balance(user_id)
        
        data = await self._load_json(self.balances_file)
        data[str(user_id)] = amount
        await self._save_json(self.balances_file, data)
        
        # PR-4: Log audit event (caller should provide context)
        # Note: Detailed audit logging happens at service layer
        from app.utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info(
            "BALANCE_SET user_id=%s balance_before=%.2f balance_after=%.2f delta=%.2f",
            user_id,
            balance_before,
            amount,
            amount - balance_before,
        )
    
    async def add_user_balance(self, user_id: int, amount: float) -> float:
        """Добавить к балансу"""
        balance_before = await self.get_user_balance(user_id)
        new_balance = balance_before + amount
        await self.set_user_balance(user_id, new_balance)
        
        # PR-4: Audit logging
        from app.utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info(
            "BALANCE_ADD user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f",
            user_id,
            amount,
            balance_before,
            new_balance,
        )
        return new_balance
    
    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        """Вычесть из баланса"""
        balance_before = await self.get_user_balance(user_id)
        # FIX #5: Strict check - NEVER allow negative balance
        if balance_before < amount:
            logger.warning(
                f"❌ Insufficient balance for subtraction: user_id={user_id}, required={amount}, available={balance_before}"
            )
            return False
        
        new_balance = balance_before - amount
        # FIX #5: Extra safety - ensure result is not negative
        if new_balance < 0:
            logger.error(f"🚨 CRITICAL: Attempted negative balance! user_id={user_id}, new_balance={new_balance}")
            return False
        
        await self.set_user_balance(user_id, new_balance)
        
        # PR-4: Audit logging
        from app.utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info(
            "BALANCE_SUBTRACT user_id=%s amount=%.2f balance_before=%.2f balance_after=%.2f",
            user_id,
            amount,
            balance_before,
            new_balance,
        )
        return True

    async def charge_balance_once(
        self,
        user_id: int,
        amount: float,
        *,
        task_id: str,
        sku_id: str = "",
        model_id: str = "",
    ) -> Dict[str, Any]:
        """Идемпотентное списание по task_id."""
        if not task_id:
            return {"status": "missing_task_id"}
        if not math.isfinite(amount) or amount <= 0:
            balance_before = await self.get_user_balance(user_id)
            logger.warning(
                "INVALID_CHARGE_AMOUNT user_id=%s amount=%.4f task_id=%s",
                user_id,
                amount,
                task_id,
            )
            return {
                "status": "invalid_amount",
                "balance_before": balance_before,
                "balance_after": balance_before,
            }

        deductions = await self._load_json(self.balance_deductions_file)
        if task_id in deductions:
            balance_before = await self.get_user_balance(user_id)
            logger.info(
                "BALANCE_CHARGE_DUPLICATE user_id=%s task_id=%s sku_id=%s model_id=%s balance=%.2f",
                user_id,
                task_id,
                sku_id,
                model_id,
                balance_before,
            )
            return {
                "status": "duplicate",
                "balance_before": balance_before,
                "balance_after": balance_before,
            }

        balance_before = await self.get_user_balance(user_id)
        if balance_before < amount:
            logger.warning(
                "BALANCE_CHARGE_INSUFFICIENT user_id=%s task_id=%s required=%.2f available=%.2f",
                user_id,
                task_id,
                amount,
                balance_before,
            )
            return {
                "status": "insufficient",
                "balance_before": balance_before,
                "balance_after": balance_before,
            }
        balance_after = balance_before - amount
        if balance_after < 0:
            logger.error(
                "BALANCE_CHARGE_NEGATIVE_BLOCKED user_id=%s task_id=%s balance_before=%.2f amount=%.2f",
                user_id,
                task_id,
                balance_before,
                amount,
            )
            return {
                "status": "negative_blocked",
                "balance_before": balance_before,
                "balance_after": balance_before,
            }

        await self.set_user_balance(user_id, balance_after)
        deductions[task_id] = {
            "user_id": user_id,
            "model_id": model_id,
            "sku_id": sku_id,
            "amount": amount,
            "created_at": datetime.utcnow().isoformat(),
        }
        await self._save_json(self.balance_deductions_file, deductions)
        logger.info(
            "BALANCE_CHARGE_OK user_id=%s task_id=%s sku_id=%s model_id=%s amount=%.2f balance_after=%.2f",
            user_id,
            task_id,
            sku_id,
            model_id,
            amount,
            balance_after,
        )
        return {
            "status": "charged",
            "balance_before": balance_before,
            "balance_after": balance_after,
        }
    
    async def get_user_language(self, user_id: int) -> str:
        """Получить язык пользователя"""
        data = await self._load_json(self.languages_file)
        return data.get(str(user_id), 'ru')
    
    async def set_user_language(self, user_id: int, language: str) -> None:
        """Установить язык пользователя"""
        data = await self._load_json(self.languages_file)
        data[str(user_id)] = language
        await self._save_json(self.languages_file, data)
    
    async def has_claimed_gift(self, user_id: int) -> bool:
        """Проверить получение подарка"""
        data = await self._load_json(self.gift_claimed_file)
        return data.get(str(user_id), False)
    
    async def set_gift_claimed(self, user_id: int) -> None:
        """Отметить получение подарка"""
        data = await self._load_json(self.gift_claimed_file)
        data[str(user_id)] = True
        await self._save_json(self.gift_claimed_file, data)
    
    async def get_user_free_generations_today(self, user_id: int) -> int:
        """Получить количество бесплатных генераций сегодня"""
        data = await self._load_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        
        if user_key not in data:
            return 0
        
        user_data = data[user_key]
        if user_data.get('date') == today:
            return user_data.get('count', 0)
        return 0
    
    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        """Получить оставшиеся бесплатные генерации"""
        from app.pricing.free_policy import get_free_daily_limit

        free_per_day = get_free_daily_limit()
        used = await self.get_user_free_generations_today(user_id)
        return max(0, free_per_day - used)
    
    async def increment_free_generations(self, user_id: int) -> None:
        """Увеличить счетчик бесплатных генераций"""
        data = await self._load_json(self.free_generations_file)
        user_key = str(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        
        if user_key not in data:
            data[user_key] = {'date': today, 'count': 0, 'bonus': 0}
        
        user_data = data[user_key]
        if user_data.get('date') != today:
            user_data['date'] = today
            user_data['count'] = 0
        
        # FIX #3: Ensure count doesn't go negative and log safely
        old_count = max(0, int(user_data.get('count', 0)))
        user_data['count'] = old_count + 1
        await self._save_json(self.free_generations_file, data)
        logger.info(f"📊 Free gen incremented: user_id={user_id}, date={today}, count={old_count+1}")

    async def consume_free_generation_once(
        self,
        user_id: int,
        *,
        task_id: str,
        sku_id: str = "",
        source: str = "delivery",
    ) -> Dict[str, Any]:
        """Идемпотентное списание бесплатной генерации по task_id."""
        if not task_id:
            return {"status": "missing_task_id"}

        from app.pricing.free_policy import get_free_daily_limit

        free_data = await self._load_json(self.free_generations_file)
        deductions = await self._load_json(self.free_deductions_file)

        today = datetime.now().strftime('%Y-%m-%d')
        user_key = str(user_id)
        entry = free_data.get(user_key, {})
        if entry.get("date") != today:
            entry = {"date": today, "count": 0, "bonus": 0}
        used_count = max(0, int(entry.get("count", 0)))
        limit = int(get_free_daily_limit())
        remaining = max(0, limit - used_count)

        if task_id in deductions:
            return {
                "status": "duplicate",
                "used_today": used_count,
                "remaining": remaining,
                "limit_per_day": limit,
            }

        if remaining <= 0:
            return {
                "status": "deny",
                "used_today": used_count,
                "remaining": 0,
                "limit_per_day": limit,
            }

        entry["count"] = used_count + 1
        free_data[user_key] = entry
        deductions[task_id] = {
            "user_id": user_id,
            "sku_id": sku_id,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
        }
        await self._save_json(self.free_generations_file, free_data)
        await self._save_json(self.free_deductions_file, deductions)

        remaining_after = max(0, limit - entry["count"])
        return {
            "status": "ok",
            "used_today": entry["count"],
            "remaining": remaining_after,
            "limit_per_day": limit,
        }

    async def get_hourly_free_usage(self, user_id: int) -> Dict[str, Any]:
        data = await self._load_json(self.hourly_free_usage_file)
        return data.get(str(user_id), {})

    async def set_hourly_free_usage(self, user_id: int, window_start_iso: str, used_count: int) -> None:
        data = await self._load_json(self.hourly_free_usage_file)
        data[str(user_id)] = {
            "window_start_iso": window_start_iso,
            "used_count": int(used_count),
        }
        await self._save_json(self.hourly_free_usage_file, data)

    async def get_referral_free_bank(self, user_id: int) -> int:
        data = await self._load_json(self.referral_free_bank_file)
        return int(data.get(str(user_id), 0))

    async def set_referral_free_bank(self, user_id: int, remaining_count: int) -> None:
        data = await self._load_json(self.referral_free_bank_file)
        data[str(user_id)] = int(max(0, remaining_count))
        await self._save_json(self.referral_free_bank_file, data)
    
    async def get_admin_limit(self, user_id: int) -> float:
        """Получить лимит админа"""
        from app.config import get_settings
        settings = get_settings()
        
        if user_id == settings.admin_id:
            return float('inf')
        
        data = await self._load_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get('limit', 100.0))
    
    async def get_admin_spent(self, user_id: int) -> float:
        """Получить потраченную сумму админа"""
        data = await self._load_json(self.admin_limits_file)
        admin_data = data.get(str(user_id), {})
        return float(admin_data.get('spent', 0.0))
    
    async def get_admin_remaining(self, user_id: int) -> float:
        """Получить оставшийся лимит админа"""
        limit = await self.get_admin_limit(user_id)
        if limit == float('inf'):
            return float('inf')
        spent = await self.get_admin_spent(user_id)
        return max(0.0, limit - spent)
    
    # ==================== GENERATION JOBS ====================
    
    async def add_generation_job(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        price: float,
        task_id: Optional[str] = None,
        status: str = "pending",
        *,
        job_id: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        prompt: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        sku_id: Optional[str] = None,
        is_free: bool = False,
        is_admin_user: bool = False,
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None,
        result_url: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> str:
        """Добавить задачу генерации"""
        job_id = job_id or task_id or str(uuid.uuid4())
        data = await self._load_json(self.jobs_file)
        
        job = {
            'job_id': job_id,
            'request_id': request_id,
            'correlation_id': correlation_id or request_id,
            'user_id': user_id,
            'model_id': model_id,
            'model_name': model_name,
            'prompt': prompt,
            'prompt_hash': prompt_hash,
            'sku_id': sku_id,
            'is_free': bool(is_free),
            'is_admin_user': bool(is_admin_user),
            'params': params,
            'price': price,
            'status': status,
            'task_id': task_id,  # external_task_id от KIE
            'external_task_id': task_id,  # alias для совместимости
            'chat_id': chat_id,
            'message_id': message_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'result_urls': [],
            'result_url': result_url,
            'error_message': None,
            'error_code': error_code,
        }
        
        data[job_id] = job
        await self._save_json(self.jobs_file, data)
        return job_id
    
    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result_urls: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        result_url: Optional[str] = None,
    ) -> None:
        """Обновить статус задачи"""
        data = await self._load_json(self.jobs_file)
        if job_id not in data:
            raise ValueError(f"Job {job_id} not found")
        
        job = data[job_id]
        current_status = str(job.get('status') or '').lower()
        new_status = str(status or '').lower()
        if current_status == 'delivered' and new_status != 'delivered':
            logger.warning(
                "Skipping status regression for delivered job: job_id=%s current=%s next=%s",
                job_id,
                current_status,
                new_status,
            )
            return
        job['status'] = status
        job['updated_at'] = datetime.now().isoformat()
        
        if result_urls is not None:
            job['result_urls'] = result_urls
            if result_urls:
                job['result_url'] = result_urls[0]
        if error_message is not None:
            job['error_message'] = error_message
        if error_code is not None:
            job['error_code'] = error_code
        if result_url is not None:
            job['result_url'] = result_url
        
        await self._save_json(self.jobs_file, data)
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Получить задачу по ID"""
        data = await self._load_json(self.jobs_file)
        return data.get(job_id)
    
    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Получить список задач"""
        data = await self._load_json(self.jobs_file)
        jobs = list(data.values())
        
        if user_id is not None:
            jobs = [j for j in jobs if j.get('user_id') == user_id]
        if status is not None:
            jobs = [j for j in jobs if j.get('status') == status]
        
        # Сортируем по created_at (новые первыми)
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return jobs[:limit]

    async def list_jobs_by_status(
        self,
        statuses: List[str],
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        data = await self._load_json(self.jobs_file)
        wanted = {status.lower() for status in statuses}
        jobs = [
            job for job in data.values()
            if (job.get("status") or "").lower() in wanted
        ]
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return jobs[:limit]
    
    async def add_generation_to_history(
        self,
        user_id: int,
        model_id: str,
        model_name: str,
        params: Dict[str, Any],
        result_urls: List[str],
        price: float,
        operation_id: Optional[str] = None
    ) -> str:
        """Добавить генерацию в историю"""
        from app.services.history_service import append_event

        gen_id = operation_id or str(uuid.uuid4())
        data = await self._load_json(self.generations_history_file)
        user_key = str(user_id)
        
        if user_key not in data:
            data[user_key] = []
        
        generation = {
            'id': gen_id,
            'model_id': model_id,
            'model_name': model_name,
            'params': params,
            'result_urls': result_urls,
            'price': price,
            'timestamp': datetime.now().isoformat(),
        }
        
        data[user_key].append(generation)
        # Ограничиваем историю последними 100 генерациями
        data[user_key] = data[user_key][-100:]
        
        await self._save_json(self.generations_history_file, data)
        await append_event(
            self,
            user_id=user_id,
            kind="generation",
            payload={
                "model_id": model_id,
                "model_name": model_name,
                "price": price,
                "result_urls": result_urls,
            },
            event_id=gen_id,
        )
        return gen_id
    
    async def get_user_generations_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить историю генераций"""
        data = await self._load_json(self.generations_history_file)
        user_key = str(user_id)
        history = data.get(user_key, [])
        return history[-limit:]
    
    # ==================== PAYMENTS ====================
    
    async def add_payment(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        payment_id: Optional[str] = None,
        screenshot_file_id: Optional[str] = None,
        status: str = "pending"
    ) -> str:
        """Добавить платеж"""
        pay_id = payment_id or str(uuid.uuid4())
        data = await self._load_json(self.payments_file)
        
        payment = {
            'payment_id': pay_id,
            'user_id': user_id,
            'amount': amount,
            'payment_method': payment_method,
            'screenshot_file_id': screenshot_file_id,
            'status': status,
            'balance_charged': False,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'admin_id': None,
            'notes': None
        }
        
        data[pay_id] = payment
        await self._save_json(self.payments_file, data)
        return pay_id
    
    async def mark_payment_status(
        self,
        payment_id: str,
        status: str,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> None:
        """Обновить статус платежа"""
        data = await self._load_json(self.payments_file)
        if payment_id not in data:
            raise ValueError(f"Payment {payment_id} not found")
        
        payment = data[payment_id]
        prev_status = payment.get("status")
        if prev_status == status:
            logger.info(
                "PAYMENT_STATUS_IDEMPOTENT payment_id=%s status=%s user_id=%s",
                payment_id,
                status,
                payment.get("user_id"),
            )
        success_statuses = {"approved", "completed"}
        credit_balance = status in success_statuses and not payment.get('balance_charged')
        if credit_balance:
            payment['balance_charged'] = True
        payment['status'] = status
        payment['updated_at'] = datetime.now().isoformat()
        
        if admin_id is not None:
            payment['admin_id'] = admin_id
        if notes is not None:
            payment['notes'] = notes
        
        # Если платеж одобрен, добавляем баланс
        if credit_balance:
            await self.add_user_balance(payment['user_id'], payment['amount'])
        
        await self._save_json(self.payments_file, data)
    
    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получить платеж по ID"""
        data = await self._load_json(self.payments_file)
        return data.get(payment_id)
    
    async def list_payments(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Получить список платежей"""
        data = await self._load_json(self.payments_file)
        payments = list(data.values())
        
        if user_id is not None:
            payments = [p for p in payments if p.get('user_id') == user_id]
        if status is not None:
            payments = [p for p in payments if p.get('status') == status]
        
        payments.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return payments[:limit]
    
    # ==================== REFERRALS ====================
    
    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        """Установить реферера"""
        data = await self._load_json(self.referrals_file)
        data[str(user_id)] = referrer_id
        
        # Добавляем в список рефералов реферера
        if 'referrals' not in data:
            data['referrals'] = {}
        if str(referrer_id) not in data['referrals']:
            data['referrals'][str(referrer_id)] = []
        
        if user_id not in data['referrals'][str(referrer_id)]:
            data['referrals'][str(referrer_id)].append(user_id)
        
        await self._save_json(self.referrals_file, data)
    
    async def get_referrer(self, user_id: int) -> Optional[int]:
        """Получить ID реферера"""
        data = await self._load_json(self.referrals_file)
        referrer_id = data.get(str(user_id))
        return int(referrer_id) if referrer_id else None
    
    async def get_referrals(self, referrer_id: int) -> List[int]:
        """Получить список рефералов"""
        data = await self._load_json(self.referrals_file)
        if 'referrals' not in data:
            return []
        return data['referrals'].get(str(referrer_id), [])
    
    async def add_referral_bonus(self, referrer_id: int, bonus_generations: int = 5) -> None:
        """Добавить бонусные генерации рефереру"""
        data = await self._load_json(self.free_generations_file)
        user_key = str(referrer_id)
        
        if user_key not in data:
            data[user_key] = {'date': datetime.now().strftime('%Y-%m-%d'), 'count': 0, 'bonus': 0}
        
        data[user_key]['bonus'] = data[user_key].get('bonus', 0) + bonus_generations
        await self._save_json(self.free_generations_file, data)

    # ==================== GENERIC JSON FILES ====================

    async def read_json_file(self, filename: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", label=f"json_storage.read:{filename}")
        target = self.data_dir / filename
        payload = await self._load_json(target)
        if payload:
            return payload
        return default or {}

    async def write_json_file(self, filename: str, data: Dict[str, Any]) -> None:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", label=f"json_storage.write:{filename}")
        target = self.data_dir / filename
        await self._save_json(target, data)

    async def update_json_file(
        self,
        filename: str,
        update_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        from app.utils.fault_injection import maybe_inject_sleep

        await maybe_inject_sleep("TRT_FAULT_INJECT_STORAGE_SLEEP_MS", label=f"json_storage.update:{filename}")
        target = self.data_dir / filename
        data = await self._load_json(target)
        updated = update_fn(dict(data))
        await self._save_json(target, updated)
        return updated
    
    # ==================== UTILITY ====================
    
    def test_connection(self) -> bool:
        """Проверить подключение"""
        try:
            return self.data_dir.exists() and self.data_dir.is_dir()
        except Exception:
            return False
    
    async def close(self) -> None:
        """Закрыть соединения (для JSON ничего не нужно)"""
        pass
