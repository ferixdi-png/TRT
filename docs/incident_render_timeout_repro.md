# Render Incident Reproduction Snapshot

Observed symptoms (from Render Events / logs):

```
Render healthcheck: i/o timeout while dialing tcp 10.16.174.85:10000
PRICING_COVERAGE_OK model_id=... sku_id=... price_rub=... sku_price_rub=... free_sku=... admin_free=...
<no further logs>
```

This snapshot captures the reported hang after pricing preflight and the failed healthcheck probe.
