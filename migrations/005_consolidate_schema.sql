-- Migration 005: Consolidate Schema (IDEMPOTENT VERSION)
-- Унификация generation_jobs → jobs (из app/database/schema.py)
-- Добавление недостающих полей и индексов для production-ready состояния

-- PHASE 1: Add missing columns to existing users table (if needed)
DO $$
BEGIN
    -- Add role column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='role') THEN
        ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user';
        ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('user', 'admin', 'banned'));
    END IF;
    
    -- Add locale column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='locale') THEN
        ALTER TABLE users ADD COLUMN locale TEXT DEFAULT 'ru';
    END IF;
    
    -- Add metadata column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='metadata') THEN
        ALTER TABLE users ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
    END IF;
    
    -- Add username column if it doesn't exist (может быть уже из 003)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='username') THEN
        ALTER TABLE users ADD COLUMN username TEXT;
    END IF;
    
    -- Add first_name column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='first_name') THEN
        ALTER TABLE users ADD COLUMN first_name TEXT;
    END IF;
END $$;

-- Create indexes on users
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- PHASE 3: Ensure wallets table exists
CREATE TABLE IF NOT EXISTS wallets (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    balance_rub NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (balance_rub >= 0),
    hold_rub NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (hold_rub >= 0),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT balance_plus_hold_positive CHECK (balance_rub + hold_rub >= 0)
);

CREATE INDEX IF NOT EXISTS idx_wallets_updated ON wallets(updated_at);

-- PHASE 4: Migrate generation_jobs → jobs (if generation_jobs exists)
DO $$
BEGIN
    -- Check if generation_jobs exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generation_jobs') THEN
        -- Create jobs table with data from generation_jobs
        CREATE TABLE IF NOT EXISTS jobs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            model_id TEXT NOT NULL,
            category TEXT NOT NULL,
            input_json JSONB NOT NULL,
            price_rub NUMERIC(12, 2) NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
                'draft', 'await_confirm', 'queued', 'running',
                'done', 'failed', 'canceled'
            )),
            kie_task_id TEXT,
            kie_status TEXT,
            result_json JSONB,
            error_text TEXT,
            idempotency_key TEXT NOT NULL,
            chat_id BIGINT,
            delivered_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMP
        );
        
        -- Migrate data
        INSERT INTO jobs (
            user_id, model_id, category, input_json, price_rub,
            status, kie_task_id, result_json, error_text,
            idempotency_key, created_at, updated_at
        )
        SELECT
            user_id,
            model_id,
            COALESCE(
                (params->>'category')::TEXT,
                CASE 
                    WHEN model_id LIKE '%video%' THEN 'video'
                    WHEN model_id LIKE '%image%' THEN 'image'
                    WHEN model_id LIKE '%audio%' THEN 'audio'
                    ELSE 'other'
                END
            ) as category,
            params as input_json,
            price as price_rub,
            CASE status
                WHEN 'queued' THEN 'queued'
                WHEN 'running' THEN 'running'
                WHEN 'done' THEN 'done'
                WHEN 'failed' THEN 'failed'
                WHEN 'canceled' THEN 'canceled'
                ELSE 'draft'
            END as status,
            external_task_id as kie_task_id,
            result_urls::jsonb as result_json,
            error_message as error_text,
            CONCAT('migrated:', job_id) as idempotency_key,
            created_at,
            updated_at
        FROM generation_jobs
        ON CONFLICT (idempotency_key) DO NOTHING;
        
        -- Drop old table after successful migration
        DROP TABLE generation_jobs CASCADE;
        
        RAISE NOTICE 'Migrated generation_jobs to jobs';
    ELSE
        -- Just create jobs table if generation_jobs doesn't exist
        CREATE TABLE IF NOT EXISTS jobs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            model_id TEXT NOT NULL,
            category TEXT NOT NULL,
            input_json JSONB NOT NULL,
            price_rub NUMERIC(12, 2) NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
                'draft', 'await_confirm', 'queued', 'running',
                'done', 'failed', 'canceled'
            )),
            kie_task_id TEXT,
            kie_status TEXT,
            result_json JSONB,
            error_text TEXT,
            idempotency_key TEXT NOT NULL,
            chat_id BIGINT,
            delivered_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMP
        );
    END IF;
END $$;

-- CRITICAL: Enforce idempotency
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs(idempotency_key);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_kie_task ON jobs(kie_task_id);
CREATE INDEX IF NOT EXISTS idx_jobs_chat_id ON jobs(chat_id);

-- PHASE 5: (removed - migration handled in PHASE 4)

-- PHASE 6: Ledger (if not exists)
CREATE TABLE IF NOT EXISTS ledger (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('topup', 'charge', 'refund', 'hold', 'release', 'adjust')),
    amount_rub NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'done' CHECK (status IN ('pending', 'done', 'failed', 'cancelled')),
    ref TEXT,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_ref ON ledger(ref) WHERE ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ledger_status ON ledger(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_idempotency ON ledger(ref) WHERE ref IS NOT NULL AND status = 'done';

-- PHASE 7: UI State
CREATE TABLE IF NOT EXISTS ui_state (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ui_state_expires ON ui_state(expires_at);

-- PHASE 8: Orphan callbacks (from migration 004)
CREATE TABLE IF NOT EXISTS orphan_callbacks (
    task_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT NOW(),
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMP,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_processed ON orphan_callbacks(processed);
CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_received_at ON orphan_callbacks(received_at);
CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_cleanup ON orphan_callbacks(processed, received_at);

-- PHASE 9: Add foreign key from orphan_callbacks to jobs (soft link)
-- Not enforced FK because orphan can exist before job
CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_task_id ON orphan_callbacks(task_id);

-- PHASE 10: Admin actions log
CREATE TABLE IF NOT EXISTS admin_actions (
    id BIGSERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK (action_type IN (
        'model_enable', 'model_disable', 'model_price', 'model_free', 
        'user_topup', 'user_charge', 'user_ban', 'user_unban',
        'config_change', 'other'
    )),
    target_type TEXT NOT NULL CHECK (target_type IN ('model', 'user', 'config', 'system')),
    target_id TEXT,
    old_value JSONB,
    new_value JSONB,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_actions_admin ON admin_actions(admin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_actions_type ON admin_actions(action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_actions_target ON admin_actions(target_type, target_id);

-- PHASE 11: Free models config
CREATE TABLE IF NOT EXISTS free_models (
    model_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    daily_limit INT NOT NULL DEFAULT 5,
    hourly_limit INT DEFAULT 2,
    meta JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_free_models_enabled ON free_models(enabled);

-- PHASE 12: Free usage tracking
CREATE TABLE IF NOT EXISTS free_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    job_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_free_usage_user_model ON free_usage(user_id, model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_free_usage_created ON free_usage(created_at);

-- PHASE 13: Verification
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_name IN ('users', 'wallets', 'jobs', 'ledger', 'ui_state', 'orphan_callbacks');
    
    IF table_count < 6 THEN
        RAISE EXCEPTION 'Migration 005 failed: expected 6 core tables, found %', table_count;
    END IF;
    
    RAISE NOTICE 'Migration 005 complete: Consolidated schema with % core tables', table_count;
END $$;
