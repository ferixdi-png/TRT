# Schema Version Tracking

**Status**: Implemented in Migration 012 (2026-01-13)  
**Purpose**: Track which migrations have been applied, enable smarter migration logic

---

## Why It Matters

### Before (Pre-Migration 012)
- Migrations applied on every startup (idempotent via `IF NOT EXISTS`)
- No visibility into which migrations were actually applied
- Difficult to debug schema consistency issues
- Slow startup if many migrations exist (future-proofing)

### After (Migration 012+)
- Migration application tracked in `migration_history` table
- Startup can verify expected migrations were applied
- Audit trail of schema changes (when, which migration, status)
- Foundation for selective migration application (skip already-applied)

---

## Implementation

### Table: `migration_history`

```sql
CREATE TABLE migration_history (
    id BIGSERIAL PRIMARY KEY,
    migration_name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status TEXT DEFAULT 'success',  -- 'success', 'failure', 'rollback'
    error_message TEXT
);
```

**Columns**:
- `id` - Sequential identifier
- `migration_name` - Filename of migration (e.g., `011_fix_heartbeat_type.sql`)
- `applied_at` - Timestamp when migration was applied
- `status` - Outcome ('success' = applied, 'failure' = error, 'rollback' = reverted)
- `error_message` - If status='failure', contains error details

**Indexes**:
- `(migration_name)` - Fast lookup by filename
- `(applied_at DESC)` - Recent migrations first

### Helper Functions

#### `migration_already_applied(p_migration_name TEXT) → BOOLEAN`
```sql
SELECT migration_already_applied('011_fix_heartbeat_type.sql');  -- true if applied
```

**Usage**: Check if migration was already applied before attempting to run it.

#### `record_migration(p_migration_name TEXT, p_status TEXT, p_error_message TEXT)`
```sql
SELECT record_migration('013_future_migration.sql', 'success', NULL);
```

**Usage**: Record migration attempt (creates or updates history entry).

---

## Python Integration

### `app/storage/migrations.py`

#### `get_applied_migrations(database_url) → Optional[List[str]]`
```python
applied = await get_applied_migrations(DATABASE_URL)
# Returns: ['001_initial_schema.sql', '002_balance_reserves.sql', ...]
# Or None if migration_history table doesn't exist yet
```

#### Updated: `apply_migrations_safe(database_url) → bool`
- Applies migrations as before (idempotent)
- **NEW**: Also records each application in `migration_history`
- Handles case where `migration_history` table doesn't exist yet (migration 012 not applied)

#### Enhanced: `check_migrations_status() → tuple[bool, int]`
- **OLD**: Simple connectivity check + assume all applied
- **NEW**: If `migration_history` exists, counts applied migrations vs. expected
- Provides accurate verification of schema consistency

---

## Initialization

When migration 012 is first applied:

1. **Table created**: `migration_history` table initialized
2. **Backfill**: All existing migrations (001-011) inserted as 'success'
3. **Helper functions**: `migration_already_applied()` and `record_migration()` created

This is **idempotent**: re-applying migration 012 updates existing records harmlessly.

---

## Usage Example

### At Startup (future enhancement)

```python
# After migrations applied, verify consistency
applied = await get_applied_migrations(DATABASE_URL)
expected = ['001_initial_schema.sql', '002_balance_reserves.sql', ..., '012_schema_version_tracking.sql']

missing = set(expected) - set(applied or [])
if missing:
    logger.error(f"Missing migrations: {missing}")
    # Could selectively apply missing ones instead of all
```

### Monitoring

```sql
-- What migrations have been applied?
SELECT migration_name, applied_at, status 
FROM migration_history 
ORDER BY applied_at DESC 
LIMIT 10;

-- Any failures?
SELECT migration_name, error_message 
FROM migration_history 
WHERE status = 'failure';
```

### Dashboard (future)

Health endpoint could expose:
```json
{
  "migrations": {
    "total": 12,
    "applied": 12,
    "last_applied": "2026-01-13T16:42:00Z",
    "failures": 0
  }
}
```

---

## Future Enhancements

### 1. Selective Migration Application
```python
# Only apply migrations not yet in history
applied = await get_applied_migrations(db_url)
for sql_file in sql_files:
    if sql_file.name not in (applied or []):
        await apply_migration(sql_file)
        await record_migration(sql_file.name, 'success')
```

### 2. Migration Rollback Support
```sql
INSERT INTO migration_history (migration_name, status)
VALUES ('011_fix_heartbeat_type.sql', 'rollback')
ON CONFLICT DO UPDATE;
```

### 3. Schema Versioning
```python
# Get schema version from latest success
schema_version = await conn.fetchval(
    "SELECT migration_name FROM migration_history WHERE status='success' ORDER BY applied_at DESC LIMIT 1"
)
# Output: '012_schema_version_tracking.sql'
```

### 4. Health Check
```python
# Verify schema consistency on startup
async def verify_schema_consistency():
    applied = await get_applied_migrations(db_url)
    expected = get_expected_migrations()
    if not applied or len(applied) != len(expected):
        logger.error("Schema inconsistency detected")
        return False
    return True
```

---

## References

- Migration file: [migrations/012_schema_version_tracking.sql](../../migrations/012_schema_version_tracking.sql)
- Migration runner: [app/storage/migrations.py](../../app/storage/migrations.py)
- Deployment guide: [docs/deployment.md#migrations](deployment.md#migrations)
- SSOT definition: [docs/architecture/SSOT.md](architecture/SSOT.md)
