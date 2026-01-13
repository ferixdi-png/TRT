-- Migration 008: Processed updates deduplication table
-- Purpose: Persistent dedup of Telegram update_id to prevent duplicate processing

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id BIGINT PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    worker_instance_id TEXT,
    update_type TEXT,
    CONSTRAINT processed_updates_update_id_unique UNIQUE (update_id)
);

-- Index for cleanup (remove old updates)
CREATE INDEX IF NOT EXISTS idx_processed_updates_processed_at 
ON processed_updates(processed_at);

-- Auto-cleanup: remove updates older than 7 days
-- (Telegram keeps updates for ~24h, but we keep longer for safety)
CREATE OR REPLACE FUNCTION cleanup_old_processed_updates()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM processed_updates
    WHERE processed_at < NOW() - INTERVAL '7 days';
END;
$$;

COMMENT ON TABLE processed_updates IS 'Deduplication: tracks processed Telegram update_id to prevent duplicate message sending';
COMMENT ON COLUMN processed_updates.update_id IS 'Telegram update_id (unique globally)';
COMMENT ON COLUMN processed_updates.processed_at IS 'When this update was first processed';
COMMENT ON COLUMN processed_updates.worker_instance_id IS 'Which instance/worker processed it';
