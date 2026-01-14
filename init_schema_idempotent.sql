-- Idempotent schema initialization для TRT bot
-- Создает только необходимые таблицы для minimal happy path
-- Безопасно для повторного выполнения (IF NOT EXISTS)

-- Table: users (для FK в generation_jobs)
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance DECIMAL(10, 2) DEFAULT 0.00,
    language VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- Table: generation_jobs (для отслеживания задач)
CREATE TABLE IF NOT EXISTS generation_jobs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    input_params JSONB,
    result_url TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_id ON generation_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_task_id ON generation_jobs(task_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_created_at ON generation_jobs(created_at);

-- Table: orphan_callbacks (для reconciliation)
CREATE TABLE IF NOT EXISTS orphan_callbacks (
    id SERIAL PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_task_id ON orphan_callbacks(task_id);
CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_processed ON orphan_callbacks(processed);
CREATE INDEX IF NOT EXISTS idx_orphan_callbacks_received_at ON orphan_callbacks(received_at);

-- Function: ensure_user (helper для вставки/обновления)
CREATE OR REPLACE FUNCTION ensure_user(
    p_user_id BIGINT,
    p_username TEXT DEFAULT NULL,
    p_first_name TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO users (user_id, username, first_name)
    VALUES (p_user_id, p_username, p_first_name)
    ON CONFLICT (user_id) DO UPDATE SET
        username = COALESCE(EXCLUDED.username, users.username),
        first_name = COALESCE(EXCLUDED.first_name, users.first_name),
        updated_at = CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Trigger: update updated_at on generation_jobs
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_generation_jobs_updated_at ON generation_jobs;
CREATE TRIGGER update_generation_jobs_updated_at
    BEFORE UPDATE ON generation_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
