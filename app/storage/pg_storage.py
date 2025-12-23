"""
PostgreSQL storage implementation - хранение данных в PostgreSQL
Использует asyncpg для async операций
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import json

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

from app.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class PostgresStorage(BaseStorage):
    """PostgreSQL storage implementation с asyncpg"""
    
    def __init__(self, database_url: str):
        if not ASYNCPG_AVAILABLE:
            raise ImportError("asyncpg is required for PostgreSQL storage")
        
        self.database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None
    
    async def _get_pool(self) -> asyncpg.Pool:
        """Получить или создать connection pool"""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
        return self._pool
    
    async def async_test_connection(self) -> bool:
        """
        Проверить подключение (async-friendly).
        
        ВАЖНО: Используется в runtime когда event loop уже запущен.
        НЕ использует asyncio.run() или run_until_complete().
        """
        if not ASYNCPG_AVAILABLE:
            return False
        
        try:
            # Пробуем создать временный pool для проверки
            pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=1,
                command_timeout=5  # Короткий таймаут для проверки
            )
            if pool:
                await pool.close()
                return True
        except Exception as e:
            logger.debug(f"PostgreSQL async connection test failed: {e}")
            return False
        return False
    
    def test_connection(self) -> bool:
        """
        Проверить подключение (синхронно, для CLI/тестов).
        
        ВАЖНО: НЕ использовать в runtime когда event loop уже запущен!
        Используйте async_test_connection() вместо этого.
        """
        if not ASYNCPG_AVAILABLE:
            return False
        
        try:
            import asyncio
            # Проверяем есть ли уже запущенный loop
            try:
                loop = asyncio.get_running_loop()
                # Если loop уже запущен - это ошибка, нужно использовать async версию
                logger.warning(
                    "[WARN] test_connection() called while event loop is running. "
                    "Use async_test_connection() instead."
                )
                return False
            except RuntimeError:
                # Нет запущенного loop - можно создать новый
                pass
            
            # Создаем новый loop только если его нет
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                pool = loop.run_until_complete(
                    asyncpg.create_pool(self.database_url, min_size=1, max_size=1, command_timeout=5)
                )
                if pool:
                    loop.run_until_complete(pool.close())
                    return True
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"PostgreSQL connection test failed: {e}")
            return False
        return False
    
    # ==================== USER OPERATIONS ====================
    
    async def get_user(self, user_id: int, upsert: bool = True) -> Dict[str, Any]:
        """Получить данные пользователя"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                user_id
            )
            
            if row is None and upsert:
                # Создаем пользователя
                await conn.execute(
                    "INSERT INTO users (id, balance) VALUES ($1, 0.00) ON CONFLICT (id) DO NOTHING",
                    user_id
                )
                row = await conn.fetchrow(
                    "SELECT * FROM users WHERE id = $1",
                    user_id
                )
            
            if row is None:
                return {
                    'user_id': user_id,
                    'balance': 0.0,
                    'language': 'ru',
                    'gift_claimed': False,
                    'referrer_id': None,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
            
            # Получаем дополнительные данные
            language = await self.get_user_language(user_id)
            gift_claimed = await self.has_claimed_gift(user_id)
            referrer_id = await self.get_referrer(user_id)
            
            return {
                'user_id': user_id,
                'balance': float(row['balance']),
                'language': language,
                'gift_claimed': gift_claimed,
                'referrer_id': referrer_id,
                'created_at': row['created_at'].isoformat() if row['created_at'] else datetime.now().isoformat(),
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else datetime.now().isoformat()
            }
    
    async def get_user_balance(self, user_id: int) -> float:
        """Получить баланс пользователя"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT balance FROM users WHERE id = $1",
                user_id
            )
            if row is None:
                # Создаем пользователя с балансом 0
                await conn.execute(
                    "INSERT INTO users (id, balance) VALUES ($1, 0.00) ON CONFLICT (id) DO NOTHING",
                    user_id
                )
                return 0.0
            return float(row['balance'])
    
    async def set_user_balance(self, user_id: int, amount: float) -> None:
        """Установить баланс пользователя"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, balance) VALUES ($1, $2)
                ON CONFLICT (id) DO UPDATE SET balance = $2
                """,
                user_id, amount
            )
    
    async def add_user_balance(self, user_id: int, amount: float) -> float:
        """Добавить к балансу"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, balance) VALUES ($1, $2)
                ON CONFLICT (id) DO UPDATE SET balance = users.balance + $2
                """,
                user_id, amount
            )
            return await self.get_user_balance(user_id)
    
    async def subtract_user_balance(self, user_id: int, amount: float) -> bool:
        """Вычесть из баланса"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                current = await self.get_user_balance(user_id)
                if current >= amount:
                    await conn.execute(
                        "UPDATE users SET balance = balance - $1 WHERE id = $2",
                        amount, user_id
                    )
                    return True
                return False
    
    async def get_user_language(self, user_id: int) -> str:
        """Получить язык пользователя"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT language FROM user_settings WHERE user_id = $1",
                user_id
            )
            if row:
                return row['language'] or 'ru'
            
            # Создаем запись с дефолтным языком
            await conn.execute(
                "INSERT INTO user_settings (user_id, language) VALUES ($1, 'ru') ON CONFLICT (user_id) DO NOTHING",
                user_id
            )
            return 'ru'
    
    async def set_user_language(self, user_id: int, language: str) -> None:
        """Установить язык пользователя"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, language) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET language = $2
                """,
                user_id, language
            )
    
    async def has_claimed_gift(self, user_id: int) -> bool:
        """Проверить получение подарка"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT gift_claimed FROM user_settings WHERE user_id = $1",
                user_id
            )
            return bool(row['gift_claimed']) if row else False
    
    async def set_gift_claimed(self, user_id: int) -> None:
        """Отметить получение подарка"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, gift_claimed) VALUES ($1, TRUE)
                ON CONFLICT (user_id) DO UPDATE SET gift_claimed = TRUE
                """,
                user_id
            )
    
    async def get_user_free_generations_today(self, user_id: int) -> int:
        """Получить количество бесплатных генераций сегодня"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            today = datetime.now().date()
            row = await conn.fetchrow(
                """
                SELECT count FROM daily_free_generations
                WHERE user_id = $1 AND date = $2
                """,
                user_id, today
            )
            return row['count'] if row else 0
    
    async def get_user_free_generations_remaining(self, user_id: int) -> int:
        """Получить оставшиеся бесплатные генерации"""
        from app.config import get_settings
        settings = get_settings()
        free_per_day = 5  # TODO: добавить в settings
        
        used = await self.get_user_free_generations_today(user_id)
        bonus = await self._get_free_generations_bonus(user_id)
        total_available = free_per_day + bonus
        return max(0, total_available - used)
    
    async def _get_free_generations_bonus(self, user_id: int) -> int:
        """Получить бонусные генерации"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT bonus FROM daily_free_generations WHERE user_id = $1",
                user_id
            )
            return row['bonus'] if row else 0
    
    async def increment_free_generations(self, user_id: int) -> None:
        """Увеличить счетчик бесплатных генераций"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            today = datetime.now().date()
            await conn.execute(
                """
                INSERT INTO daily_free_generations (user_id, date, count, bonus)
                VALUES ($1, $2, 1, 0)
                ON CONFLICT (user_id, date) DO UPDATE SET count = daily_free_generations.count + 1
                """,
                user_id, today
            )
    
    async def get_admin_limit(self, user_id: int) -> float:
        """Получить лимит админа"""
        from app.config import get_settings
        settings = get_settings()
        
        if user_id == settings.admin_id:
            return float('inf')
        
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT limit_amount FROM admin_limits WHERE user_id = $1",
                user_id
            )
            return float(row['limit_amount']) if row else 100.0
    
    async def get_admin_spent(self, user_id: int) -> float:
        """Получить потраченную сумму админа"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(amount), 0) as spent FROM operations WHERE user_id = $1 AND type = 'generation'",
                user_id
            )
            return float(row['spent']) if row else 0.0
    
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
        status: str = "pending"
    ) -> str:
        """Добавить задачу генерации"""
        job_id = task_id or str(uuid.uuid4())
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Сохраняем task_id как external_task_id
            await conn.execute(
                """
                INSERT INTO generation_jobs (job_id, user_id, model_id, model_name, params, price, status, external_task_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                job_id, user_id, model_id, model_name, json.dumps(params), price, status, task_id
            )
        return job_id
    
    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result_urls: Optional[List[str]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Обновить статус задачи"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            updates = ["status = $2"]
            params = [job_id, status]
            
            if result_urls is not None:
                updates.append("result_urls = $3")
                params.append(json.dumps(result_urls))
            if error_message is not None:
                updates.append("error_message = $4")
                params.append(error_message[:500])  # Ограничиваем длину
            
            await conn.execute(
                f"UPDATE generation_jobs SET {', '.join(updates)} WHERE job_id = $1",
                *params
            )
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Получить задачу по ID"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM generation_jobs WHERE job_id = $1",
                job_id
            )
            if row:
                return dict(row)
            return None
    
    async def list_jobs(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Получить список задач"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM generation_jobs WHERE 1=1"
            params = []
            
            if user_id is not None:
                query += " AND user_id = $" + str(len(params) + 1)
                params.append(user_id)
            if status is not None:
                query += " AND status = $" + str(len(params) + 1)
                params.append(status)
            
            query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
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
        gen_id = operation_id or str(uuid.uuid4())
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO operations (user_id, type, amount, model, result_url, prompt)
                VALUES ($1, 'generation', $2, $3, $4, $5)
                """,
                user_id, price, model_name, json.dumps(result_urls), json.dumps(params)[:1000]
            )
        return gen_id
    
    async def get_user_generations_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить историю генераций"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM operations
                WHERE user_id = $1 AND type = 'generation'
                ORDER BY created_at DESC LIMIT $2
                """,
                user_id, limit
            )
            return [dict(row) for row in rows]
    
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
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO payments (payment_id, user_id, amount, payment_method, screenshot_file_id, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                pay_id, user_id, amount, payment_method, screenshot_file_id, status
            )
        return pay_id
    
    async def mark_payment_status(
        self,
        payment_id: str,
        status: str,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> None:
        """Обновить статус платежа"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Обновляем статус
                await conn.execute(
                    "UPDATE payments SET status = $1, admin_id = $2, notes = $3 WHERE payment_id = $4",
                    status, admin_id, notes, payment_id
                )
                
                # Если платеж одобрен, добавляем баланс
                if status == "approved":
                    payment = await conn.fetchrow(
                        "SELECT user_id, amount FROM payments WHERE payment_id = $1",
                        payment_id
                    )
                    if payment:
                        await self.add_user_balance(payment['user_id'], float(payment['amount']))
    
    async def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получить платеж по ID"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM payments WHERE payment_id = $1",
                payment_id
            )
            return dict(row) if row else None
    
    async def list_payments(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Получить список платежей"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM payments WHERE 1=1"
            params = []
            
            if user_id is not None:
                query += " AND user_id = $" + str(len(params) + 1)
                params.append(user_id)
            if status is not None:
                query += " AND status = $" + str(len(params) + 1)
                params.append(status)
            
            query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    # ==================== REFERRALS ====================
    
    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        """Установить реферера"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO referrals (user_id, referrer_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET referrer_id = $2
                """,
                user_id, referrer_id
            )
    
    async def get_referrer(self, user_id: int) -> Optional[int]:
        """Получить ID реферера"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT referrer_id FROM referrals WHERE user_id = $1",
                user_id
            )
            return int(row['referrer_id']) if row and row['referrer_id'] else None
    
    async def get_referrals(self, referrer_id: int) -> List[int]:
        """Получить список рефералов"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id FROM referrals WHERE referrer_id = $1",
                referrer_id
            )
            return [int(row['user_id']) for row in rows]
    
    async def add_referral_bonus(self, referrer_id: int, bonus_generations: int = 5) -> None:
        """Добавить бонусные генерации рефереру"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            today = datetime.now().date()
            await conn.execute(
                """
                INSERT INTO daily_free_generations (user_id, date, count, bonus)
                VALUES ($1, $2, 0, $3)
                ON CONFLICT (user_id, date) DO UPDATE SET bonus = daily_free_generations.bonus + $3
                """,
                referrer_id, today, bonus_generations
            )
    
    # ==================== UTILITY ====================
    
    async def close(self) -> None:
        """Закрыть соединения"""
        if self._pool:
            await self._pool.close()
            self._pool = None


# Алиас для обратной совместимости
PGStorage = PostgresStorage
