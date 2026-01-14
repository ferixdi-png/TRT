# Database Schema & Operations

## Connection Pool

```python
# app/database/services.py
pool = ThreadedConnectionPool(
    minconn=2,
    maxconn=20,
    dsn=DATABASE_URL
)
```

**Timeouts**:
- Connection timeout: 10 seconds
- Query timeout: 30 seconds
- Idle timeout: 600 seconds (10 minutes)

## Schema (Migrations in /migrations)

### user_balances
```sql
CREATE TABLE IF NOT EXISTS user_balances (
    user_id BIGINT PRIMARY KEY,
    balance NUMERIC(10, 2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'RUB',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_balances_user_id ON user_balances(user_id);
```

### transactions
```sql
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RUB',
    type VARCHAR(20) NOT NULL,  -- 'topup', 'deduction', 'refund'
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);
```

### jobs
```sql
CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    model_id VARCHAR(100) NOT NULL,
    prompt TEXT,
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    result_url TEXT,
    error_message TEXT,
    cost NUMERIC(10, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
```

### lock_heartbeat
```sql
CREATE TABLE IF NOT EXISTS lock_heartbeat (
    lock_key BIGINT PRIMARY KEY,
    instance_id VARCHAR(100) NOT NULL,
    last_heartbeat TIMESTAMP DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_lock_heartbeat(
    p_lock_key BIGINT,
    p_instance_id VARCHAR(100)
) RETURNS VOID AS $$
BEGIN
    INSERT INTO lock_heartbeat (lock_key, instance_id, last_heartbeat)
    VALUES (p_lock_key, p_instance_id, NOW())
    ON CONFLICT (lock_key) DO UPDATE
    SET instance_id = EXCLUDED.instance_id,
        last_heartbeat = NOW();
END;
$$ LANGUAGE plpgsql;
```

## Common Operations

### Get user balance
```python
async def get_user_balance(user_id: int) -> float:
    async with db.connection() as conn:
        result = await conn.fetchone(
            "SELECT balance FROM user_balances WHERE user_id = %s",
            (user_id,)
        )
        return float(result[0]) if result else 0.0
```

### Deduct balance (with transaction)
```python
async def deduct_balance(user_id: int, amount: float, description: str):
    async with db.transaction() as txn:
        # Check balance
        balance = await txn.fetchone(
            "SELECT balance FROM user_balances WHERE user_id = %s FOR UPDATE",
            (user_id,)
        )
        
        if not balance or balance[0] < amount:
            raise InsufficientBalanceError()
        
        # Deduct
        await txn.execute(
            "UPDATE user_balances SET balance = balance - %s, updated_at = NOW() WHERE user_id = %s",
            (amount, user_id)
        )
        
        # Log transaction
        await txn.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (%s, %s, 'deduction', %s)",
            (user_id, -amount, description)
        )
```

### Create job
```python
async def create_job(user_id: int, model_id: str, prompt: str, parameters: dict, cost: float) -> int:
    async with db.connection() as conn:
        result = await conn.fetchone(
            """
            INSERT INTO jobs (user_id, model_id, prompt, parameters, cost, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (user_id, model_id, prompt, json.dumps(parameters), cost)
        )
        return result[0]
```

### Update job status
```python
async def update_job_status(job_id: int, status: str, result_url: str = None, error_message: str = None):
    async with db.connection() as conn:
        await conn.execute(
            """
            UPDATE jobs
            SET status = %s,
                result_url = %s,
                error_message = %s,
                completed_at = NOW()
            WHERE id = %s
            """,
            (status, result_url, error_message, job_id)
        )
```

## Migration Strategy

1. All migrations use `IF NOT EXISTS` (idempotent)
2. No `DROP` statements in production migrations
3. Schema changes via new migration files (never edit old ones)
4. Test migrations on staging before production

## Backup Policy

- Daily automated backups (Render managed)
- Retention: 7 days
- Manual backup before major schema changes

## Performance Considerations

- Use `EXPLAIN ANALYZE` for slow queries
- Add indexes for frequently filtered columns
- Use `LIMIT` in admin queries (avoid full table scans)
- Partitioning for transactions table (if > 1M rows)

## Forbidden Operations

❌ No `SELECT *` in production code (specify columns)  
❌ No N+1 queries (use joins or batch fetches)  
❌ No `DELETE FROM table` without WHERE (data loss risk)  
❌ No long-running transactions (> 10 seconds)  
❌ No raw SQL concatenation (always use parameterized queries)
