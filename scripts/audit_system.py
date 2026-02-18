#!/usr/bin/env python3
"""Full system audit script - checks all critical components."""
import yaml
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
issues = []
warnings = []

# 1. Pricing YAML
print("=" * 60)
print("1. PRICING YAML AUDIT")
print("=" * 60)
with open(os.path.join(ROOT, "app/kie_catalog/models_pricing.yaml"), "r", encoding="utf-8") as f:
    pricing = yaml.safe_load(f)
p_models = pricing.get("models", [])
p_ids = set()
for m in p_models:
    mid = m.get("id", "?")
    p_ids.add(mid)
    if not m.get("type"):
        issues.append(f"PRICING: {mid} missing type")
    if not m.get("modes"):
        issues.append(f"PRICING: {mid} missing modes")
    for mode in m.get("modes", []):
        if mode.get("credits") is None:
            issues.append(f"PRICING: {mid} mode missing credits")
print(f"  Models: {len(p_ids)}")
print(f"  All have type: {all(m.get('type') for m in p_models)}")
print(f"  All have modes: {all(m.get('modes') for m in p_models)}")

# 2. Registry YAML
print("\n" + "=" * 60)
print("2. REGISTRY YAML AUDIT")
print("=" * 60)
with open(os.path.join(ROOT, "models/kie_models.yaml"), "r", encoding="utf-8") as f:
    registry = yaml.safe_load(f)
r_models = registry if isinstance(registry, list) else registry.get("models", [])
r_ids = set()
for m in r_models:
    if isinstance(m, dict):
        r_ids.add(m.get("id", ""))
    elif isinstance(m, str):
        r_ids.add(m)
print(f"  Models: {len(r_ids)}")

# 3. RUB Pricing
print("\n" + "=" * 60)
print("3. RUB PRICING AUDIT")
print("=" * 60)
with open(os.path.join(ROOT, "data/kie_pricing_rub.yaml"), "r", encoding="utf-8") as f:
    rub = yaml.safe_load(f)
rub_models = rub.get("models", [])
rub_ids = {m.get("id") for m in rub_models}
print(f"  Models: {len(rub_ids)}")
zero_price = [m["id"] for m in rub_models if all(s.get("price_rub", 0) == 0 for s in m.get("skus", []))]
if zero_price:
    warnings.append(f"RUB: {len(zero_price)} models with 0 price: {zero_price[:5]}")

# 4. Cross-check
print("\n" + "=" * 60)
print("4. CROSS-CHECK")
print("=" * 60)
diff_pr = p_ids - r_ids
diff_rp = r_ids - p_ids
diff_prub = p_ids - rub_ids
diff_rubp = rub_ids - p_ids
if diff_pr: issues.append(f"In pricing but not registry: {diff_pr}")
if diff_rp: issues.append(f"In registry but not pricing: {diff_rp}")
if diff_prub: issues.append(f"In pricing but not rub: {diff_prub}")
if diff_rubp: issues.append(f"In rub but not pricing: {diff_rubp}")
print(f"  Pricing vs Registry: {'OK' if not diff_pr and not diff_rp else 'MISMATCH'}")
print(f"  Pricing vs RUB: {'OK' if not diff_prub and not diff_rubp else 'MISMATCH'}")

# 5. Top Models
print("\n" + "=" * 60)
print("5. TOP MODELS AUDIT")
print("=" * 60)
try:
    from app.top_models import get_top_models, get_categories, get_sku_price_rub
    top = get_top_models()
    cats = get_categories()
    no_price = []
    for m in top:
        for sku in m.get("skus", []):
            pr = get_sku_price_rub(sku.get("price_ref", ""), sku.get("mode_key", ""))
            if not pr:
                no_price.append(f"{m.get('id')}/{sku.get('sku_id')}")
    print(f"  Top models: {len(top)}")
    print(f"  Categories: {len(cats)}")
    if no_price:
        warnings.append(f"TOP: {len(no_price)} SKUs without price: {no_price[:5]}")
    else:
        print("  All SKUs priced: YES")
except Exception as e:
    issues.append(f"TOP MODELS: {e}")

# 6. KIE_MODELS enrichment
print("\n" + "=" * 60)
print("6. KIE_MODELS ENRICHMENT")
print("=" * 60)
try:
    from kie_models import KIE_MODELS, GENERATION_TYPES
    print(f"  KIE_MODELS entries: {len(KIE_MODELS)}")
    gen_model_ids = set()
    for gt, gdata in GENERATION_TYPES.items():
        for mid in gdata.get("models", []):
            gen_model_ids.add(mid)
    print(f"  GENERATION_TYPES total model refs: {len(gen_model_ids)}")
    not_in_gen = p_ids - gen_model_ids
    if not_in_gen:
        warnings.append(f"KIE: {len(not_in_gen)} pricing models not in GENERATION_TYPES: {list(not_in_gen)[:5]}")
except Exception as e:
    issues.append(f"KIE_MODELS: {e}")

# 7. Model Copy
print("\n" + "=" * 60)
print("7. MODEL COPY AUDIT")
print("=" * 60)
try:
    with open(os.path.join(ROOT, "app/models/model_copy.yaml"), "r", encoding="utf-8") as f:
        copy_data = yaml.safe_load(f)
    copy_ids = set(copy_data.keys()) if isinstance(copy_data, dict) else set()
    missing_copy = p_ids - copy_ids
    print(f"  Model copy entries: {len(copy_ids)}")
    if missing_copy:
        warnings.append(f"COPY: {len(missing_copy)} models without copy (will use fallback): {list(missing_copy)[:5]}")
    else:
        print(f"  All models have copy: YES")
except FileNotFoundError:
    warnings.append("MODEL_COPY: app/models/model_copy.yaml not found")
except Exception as e:
    warnings.append(f"MODEL_COPY: {e}")

# 8. WebApp handlers
print("\n" + "=" * 60)
print("8. WEBAPP HANDLERS")
print("=" * 60)
try:
    import ast
    with open(os.path.join(ROOT, "webapp/aiohttp_handlers.py"), "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    required = ["webapp_generate", "webapp_job_status", "webapp_models", "webapp_top_models", "webapp_model_info", "webapp_user_history"]
    for r in required:
        if r not in funcs:
            issues.append(f"WEBAPP: missing handler {r}")
    print(f"  Handler functions: {len(funcs)}")
    print(f"  Required handlers present: {all(r in funcs for r in required)}")
except Exception as e:
    issues.append(f"WEBAPP: {e}")

# 9. Universal Engine
print("\n" + "=" * 60)
print("9. UNIVERSAL ENGINE")
print("=" * 60)
try:
    import ast
    with open(os.path.join(ROOT, "app/generations/universal_engine.py"), "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    print(f"  Classes: {classes[:10]}")
    print(f"  JobResult present: {'JobResult' in classes}")
    print(f"  run_generation present: {'run_generation' in funcs}")
except Exception as e:
    issues.append(f"ENGINE: {e}")

# 10. Delivery / Reconciler
print("\n" + "=" * 60)
print("10. DELIVERY RECONCILER")
print("=" * 60)
try:
    import ast
    with open(os.path.join(ROOT, "app/delivery/reconciler.py"), "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    print(f"  Functions: {len(funcs)}")
except Exception as e:
    issues.append(f"RECONCILER: {e}")

# Summary
print("\n" + "=" * 60)
print("AUDIT SUMMARY")
print("=" * 60)
if issues:
    print(f"\n[FAIL] ISSUES ({len(issues)}):")
    for i in issues:
        print(f"  - {i}")
else:
    print("\n[OK] NO ISSUES FOUND")

if warnings:
    print(f"\n[WARN] WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  - {w}")
else:
    print("\n[OK] NO WARNINGS")

print(f"\nTotal: {len(issues)} issues, {len(warnings)} warnings")
sys.exit(1 if issues else 0)
