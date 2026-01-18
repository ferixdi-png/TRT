# Audit Delta

## Current counts
- registry_count: 72 (models/kie_models.yaml)
- pricing_count: 72 (app/kie_catalog/models_pricing.yaml)

## Orphans
- pricing - registry: none
- registry - pricing: none

## Free models derivation
- Free models are derived from the pricing catalog only via `get_free_model_ids()` which scans `app/kie_catalog/models_pricing.yaml` and marks a model free if `free: true` or any mode has `free: true` or zero credits/price. This prevents orphaned free-model mismatches because it uses the catalog as the source. See `app/kie_catalog/catalog.py`.
- free models list size: 1 (based on current catalog data, `free: true` entry).
