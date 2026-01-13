# Product Roadmap

**Last Updated**: 2026-01-13  
**Current Cycle**: 9 (Telemetry Integration)  
**Status**: Phase 1 Complete, Phase 2 In Progress

---

## Completed Cycles

### Cycle 1-7: Foundation & Stabilization
- ✅ Core infrastructure (database, storage, KIE client)
- ✅ Payment integration (Telegram Stars)
- ✅ Model registry (KIE_SOURCE_OF_TRUTH.json)
- ✅ FSM flow (categories → models → params → generation)
- ✅ Singleton lock (PostgreSQL advisory lock)
- ✅ ACTIVE/PASSIVE mode (graceful degradation)

### Cycle 8: Emergency Hotfix (2026-01-12)
- ✅ Fixed heartbeat function type signature
- ✅ Fixed lock takeover loops
- ✅ Added comprehensive documentation
- ✅ Schema versioning (migration 007 → 008)
- ✅ Production verification

### Cycle 9: Telemetry Integration (2026-01-13)
**Phase 1 Complete**:
- ✅ Telemetry infrastructure (logging_contract, ui_registry, helpers)
- ✅ TelemetryMiddleware integration
- ✅ /debug admin command
- ✅ Core handlers instrumented (start, main_menu, category, model)
- ✅ Event chain logging (cid-based correlation)
- ✅ Reason codes (semantic failure classification)
- ✅ Documentation (telemetry.md, integration examples, implementation guide)

---

## Current Cycle: Cycle 9 (Telemetry) - Phase 2

**Goal**: Complete handler integration + production verification

### Remaining Tasks

#### P0: Handler Integration (This Week)
- [ ] z_image.py - integrate telemetry
- [ ] balance.py - integrate telemetry
- [ ] history.py - integrate telemetry
- [ ] admin.py - integrate telemetry
- [ ] quick_actions.py - integrate telemetry
- [ ] gallery.py - integrate telemetry
- [ ] marketing.py - integrate telemetry
- [ ] error_handler.py - integrate telemetry

#### P0: Testing & Verification
- [ ] Run smoke_buttons_instrumentation.py
- [ ] Fix any failures
- [ ] Verify event chains in Render logs
- [ ] Test /debug command end-to-end
- [ ] 60-second diagnosis walkthrough

#### P1: Documentation
- [ ] Update kb/patterns.md with telemetry examples
- [ ] Update kb/features.md with observability status
- [ ] Add troubleshooting guide (common issues + solutions)

---

## Cycle 10: Unified Model Pipeline (Next 2 Weeks)

**Goal**: All models работают через единый пайплайн (как z-image)

### Architecture Vision

**Current** (problematic):
- z-image: dedicated handler (works well)
- Other models: mixed approaches (some through flow.py, some broken)
- Inconsistent parameter collection
- No standardized confirmation/pricing display
- Duplicate code for task creation/polling

**Target** (unified):
```
User clicks model
  ↓
Common pipeline detects flow_type (text2image, image2image, etc.)
  ↓
Parameter collection (contract-driven, from SSOT)
  ↓
Confirmation screen (model info + pricing + params summary)
  ↓
Task creation (unified kie_client.create_task)
  ↓
Polling + delivery (unified queue handler)
  ↓
Storage (generation record)
```

### Tasks

#### P0: Pipeline Core
- [ ] Create `app/pipeline/universal_handler.py`
- [ ] Contract-driven parameter collection
- [ ] Standardized confirmation screen
- [ ] Unified task creation/polling
- [ ] Error handling + retry logic

#### P0: SSOT Enhancement
- [ ] Validate all models have correct flow_type
- [ ] Add parameter constraints (min/max, options)
- [ ] Add examples for each parameter
- [ ] Add validation rules

#### P1: UX Improvements
- [ ] Parameter help text (hints for users)
- [ ] Progress indicators (step 1/3, etc.)
- [ ] Better error messages (actionable)
- [ ] Example prompts (inspiration)

#### P1: Testing
- [ ] Unit tests for pipeline
- [ ] Integration tests (end-to-end flows)
- [ ] Smoke tests for each flow_type

---

## Cycle 11: Parameters UX (Week of Jan 20)

**Goal**: Параметры понятны и легко заполняются

### Tasks

- [ ] Label + help for each parameter
- [ ] Buttons for constrained fields (aspect_ratio, style, etc.)
- [ ] Examples in prompts ("например: sunset beach")
- [ ] Validation with clear error messages
- [ ] Smart defaults (pre-fill common values)

---

## Cycle 12: Architecture Cleanup (Week of Jan 27)

**Goal**: Убрать мусор, один источник правды

### Tasks

- [ ] Remove legacy handlers (move to /legacy)
- [ ] Remove shadow packages (./aiogram stubs)
- [ ] Consolidate configuration (one ENV source)
- [ ] Remove duplicate services
- [ ] Validate startup (guards for missing deps)

---

## Future Cycles (Feb 2026+)

### Metrics & Monitoring
- [ ] Grafana dashboard (metrics export)
- [ ] Alerting (error rate, response time)
- [ ] Session replay (reconstruct user journey from logs)
- [ ] Model performance tracking

### Advanced Features
- [ ] Batch generation (multiple images at once)
- [ ] Generation history search
- [ ] Favorites (save/reuse prompts)
- [ ] Model recommendations (based on usage)
- [ ] Cost optimization (cheaper alternatives suggestions)

### Scaling
- [ ] Multi-instance mode (beyond singleton)
- [ ] Redis cache (model registry, pricing)
- [ ] CDN integration (result delivery)
- [ ] Rate limiting (per-user quotas)

---

## Success Metrics (Overall Product)

### Reliability
- **Target**: 99.5% uptime
- **Current**: TBD (need monitoring setup)

### Performance
- **Target**: P95 response < 800ms
- **Current**: ~300ms (webhook fast-ack works)

### Observability
- **Target**: 60-second diagnosis for any issue
- **Current**: ✅ ACHIEVED (Cycle 9 Phase 1)

### Model Coverage
- **Target**: 100% of enabled models работают
- **Current**: ~50% (z-image works, others partial)

### UX Quality
- **Target**: No silent failures, clear error messages
- **Current**: 70% (telemetry helps, but UX needs polish)

---

## Backlog (Future Ideas)

### Nice-to-Have Features
- Web dashboard (admin panel for stats)
- A/B testing (different UX flows)
- User preferences (language, default params)
- Multi-language support (English, Chinese)
- API for third-party integrations

### Technical Debt
- Migrate from MemoryStorage to RedisStorage (FSM persistence)
- Database connection pooling optimization
- Async queue processing (beyond in-memory)
- Image optimization (compression before delivery)

---

**PRIORITY FOCUS**: Finish Cycle 9 Phase 2 (handler integration) → then Cycle 10 (unified pipeline)
