-- SQL Diagnostics Queries for TRT Observability
-- Safe to run in production (all queries have LIMIT and use indexes)

-- ============================================================================
-- 1. Errors by Hour (Last 24 Hours)
-- ============================================================================
SELECT 
    DATE_TRUNC('hour', ts) as hour,
    level,
    COUNT(*) as error_count
FROM app_events
WHERE level IN ('ERROR', 'CRITICAL')
    AND ts >= NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', ts), level
ORDER BY hour DESC, level;

-- ============================================================================
-- 2. Top Events (Last 24 Hours)
-- ============================================================================
SELECT 
    event,
    COUNT(*) as count,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT cid) as unique_cids
FROM app_events
WHERE ts >= NOW() - INTERVAL '24 hours'
GROUP BY event
ORDER BY count DESC
LIMIT 20;

-- ============================================================================
-- 3. Top Failure Reasons (Last 24 Hours)
-- ============================================================================
SELECT 
    payload_json->>'failCode' as fail_code,
    payload_json->>'failMsg' as fail_msg,
    COUNT(*) as count,
    MIN(ts) as first_seen,
    MAX(ts) as last_seen
FROM app_events
WHERE event = 'KIE_JOB_COMPLETED'
    AND level = 'ERROR'
    AND ts >= NOW() - INTERVAL '24 hours'
    AND payload_json IS NOT NULL
GROUP BY payload_json->>'failCode', payload_json->>'failMsg'
ORDER BY count DESC
LIMIT 10;

-- ============================================================================
-- 4. Recent Failed Jobs (Last 50)
-- ============================================================================
SELECT 
    j.id,
    j.user_id,
    j.model_id,
    j.status,
    j.error_text,
    j.created_at,
    j.updated_at,
    j.finished_at,
    EXTRACT(EPOCH FROM (j.finished_at - j.created_at)) as duration_seconds
FROM jobs j
WHERE j.status != 'done'
    AND j.status != 'draft'
    AND j.created_at >= NOW() - INTERVAL '7 days'
ORDER BY j.created_at DESC
LIMIT 50;

-- ============================================================================
-- 5. Users with Most Errors (Last 24 Hours)
-- ============================================================================
SELECT 
    user_id,
    COUNT(*) as error_count,
    COUNT(DISTINCT event) as unique_events,
    MIN(ts) as first_error,
    MAX(ts) as last_error
FROM app_events
WHERE level IN ('ERROR', 'CRITICAL')
    AND ts >= NOW() - INTERVAL '24 hours'
    AND user_id IS NOT NULL
GROUP BY user_id
ORDER BY error_count DESC
LIMIT 20;

-- ============================================================================
-- 6. Stuck Jobs (Running > 10 Minutes)
-- ============================================================================
SELECT 
    j.id,
    j.user_id,
    j.model_id,
    j.status,
    j.kie_task_id,
    j.created_at,
    j.updated_at,
    EXTRACT(EPOCH FROM (NOW() - j.updated_at)) / 60.0 as minutes_stuck
FROM jobs j
WHERE j.status = 'running'
    AND j.updated_at < NOW() - INTERVAL '10 minutes'
ORDER BY j.updated_at ASC
LIMIT 50;

-- ============================================================================
-- 7. PASSIVE_REJECT Events (Last 24 Hours, Grouped by Hour)
-- ============================================================================
SELECT 
    DATE_TRUNC('hour', ts) as hour,
    COUNT(*) as reject_count,
    COUNT(DISTINCT user_id) as affected_users
FROM app_events
WHERE event = 'PASSIVE_REJECT'
    AND ts >= NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', ts)
ORDER BY hour DESC;

-- ============================================================================
-- 8. Model Usage Statistics (Last 24 Hours)
-- ============================================================================
SELECT 
    model,
    COUNT(*) as job_count,
    COUNT(DISTINCT user_id) as unique_users,
    SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) as error_count,
    ROUND(
        100.0 * SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) / COUNT(*),
        2
    ) as error_rate_percent
FROM app_events
WHERE event = 'KIE_JOB_CREATED'
    AND ts >= NOW() - INTERVAL '24 hours'
    AND model IS NOT NULL
GROUP BY model
ORDER BY job_count DESC
LIMIT 20;

-- ============================================================================
-- 9. Correlation ID Chains (Debug Specific CID)
-- ============================================================================
-- Replace 'YOUR_CID_HERE' with actual correlation ID
SELECT 
    ts,
    level,
    event,
    user_id,
    task_id,
    model,
    payload_json,
    err_stack
FROM app_events
WHERE cid = 'YOUR_CID_HERE'
ORDER BY ts ASC;

-- ============================================================================
-- 10. Event Rate by Minute (Last Hour) - for Load Monitoring
-- ============================================================================
SELECT 
    DATE_TRUNC('minute', ts) as minute,
    COUNT(*) as event_count,
    COUNT(DISTINCT event) as unique_events,
    COUNT(DISTINCT user_id) as active_users
FROM app_events
WHERE ts >= NOW() - INTERVAL '1 hour'
GROUP BY DATE_TRUNC('minute', ts)
ORDER BY minute DESC
LIMIT 60;

-- ============================================================================
-- NOTES:
-- ============================================================================
-- - All queries use indexes (ts DESC, event, user_id, task_id, cid)
-- - All queries have LIMIT to prevent long-running queries
-- - Replace 'YOUR_CID_HERE' in query #9 with actual correlation ID
-- - Adjust time intervals as needed (24 hours, 7 days, etc.)
-- - Run during low-traffic periods for large time ranges

