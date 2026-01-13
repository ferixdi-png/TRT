-- Migration 007: Processed updates deduplication table (CRITICAL FIX)
-- Purpose: Persistent dedup of Telegram update_id to prevent duplicate processing
-- Created: 2026-01-13 (Emergency fix for worker deadlock)

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id BIGINT PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    worker_instance_id TEXT,
    update_type TEXT
);

-- Index for cleanup (remove old updates)
CREATE INDEX IF NOT EXISTS idx_processed_updates_processed_at 
ON processed_updates(processed_at);

COMMENT ON TABLE processed_updates IS 'Deduplication: tracks processed Telegram update_id to prevent duplicate message sending';
COMMENT ON COLUMN processed_updates.update_id IS 'Telegram update_id (unique globally)';
COMMENT ON COLUMN processed_updates.processed_at IS 'When this update was first processed';
COMMENT ON COLUMN processed_updates.worker_instance_id IS 'Which instance/worker processed it';
