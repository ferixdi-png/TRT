"""Full system audit script — checks consistency across all data sources."""
import yaml
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

print("=" * 60)
print("FULL SYSTEM AUDIT")
print("=" * 60)

# 1. Pricing catalog vs Registry
pricing = load_yaml('app/kie_catalog/models_pricing.yaml')
registry = load_yaml('models/kie_models.yaml')
pricing_rub = load_yaml('data/kie_pricing_rub.yaml')

pricing_ids = set(m['id'] for m in pricing['models'])
registry_ids = set(registry['models'].keys())
rub_ids = set(m['id'] for m in pricing_rub['models'])

print(f"\n[1] PRICING CATALOG vs REGISTRY")
print(f"   Pricing catalog: {len(pricing_ids)} models")
print(f"   Registry YAML:   {len(registry_ids)} models")
print(f"   Pricing RUB:     {len(rub_ids)} models")
diff1 = pricing_ids - registry_ids
diff2 = registry_ids - pricing_ids
diff3 = pricing_ids - rub_ids
diff4 = rub_ids - pricing_ids
if diff1: print(f"   ❌ In pricing but NOT in registry: {sorted(diff1)}")
if diff2: print(f"   ❌ In registry but NOT in pricing: {sorted(diff2)}")
if diff3: print(f"   ❌ In pricing but NOT in RUB:      {sorted(diff3)}")
if diff4: print(f"   ❌ In RUB but NOT in pricing:      {sorted(diff4)}")
if not (diff1 or diff2 or diff3 or diff4):
    print("   ✅ All 3 sources perfectly aligned")

# 2. KIE_MODELS (kie_models.py) vs pricing
# Parse KIE_MODELS ids from kie_models.py without importing it
kie_model_ids = set()
gen_type_model_ids = set()
with open('kie_models.py', 'r', encoding='utf-8') as f:
    content = f.read()
    # Find all 'id': '...' patterns
    import re
    for match in re.finditer(r"'id'\s*:\s*'([^']+)'", content):
        kie_model_ids.add(match.group(1))
    for match in re.finditer(r'"id"\s*:\s*"([^"]+)"', content):
        kie_model_ids.add(match.group(1))
    # Find models in GENERATION_TYPES
    for match in re.finditer(r"'models'\s*:\s*\[(.*?)\]", content, re.DOTALL):
        block = match.group(1)
        for m in re.finditer(r"'([^']+)'", block):
            gen_type_model_ids.add(m.group(1))
        for m in re.finditer(r'"([^"]+)"', block):
            gen_type_model_ids.add(m.group(1))

print(f"\n[2] KIE_MODELS.py")
print(f"   KIE_MODELS entries: {len(kie_model_ids)}")
print(f"   GENERATION_TYPES model refs: {len(gen_type_model_ids)}")
orphans = kie_model_ids - gen_type_model_ids
if orphans: print(f"   ⚠️  Orphans (in KIE_MODELS, not in GENERATION_TYPES): {sorted(orphans)}")
missing = gen_type_model_ids - kie_model_ids
if missing: print(f"   ❌ In GENERATION_TYPES but NOT in KIE_MODELS: {sorted(missing)}")
no_pricing = gen_type_model_ids - pricing_ids
if no_pricing: print(f"   ❌ In GENERATION_TYPES but NO pricing: {sorted(no_pricing)}")
if not (orphans or missing or no_pricing):
    print("   ✅ All aligned")

# 3. Check pricing RUB has valid prices
print(f"\n[3] PRICING RUB VALIDATION")
zero_price = []
negative_price = []
no_skus = []
for m in pricing_rub['models']:
    mid = m['id']
    skus = m.get('skus', [])
    if not skus:
        no_skus.append(mid)
        continue
    for sku in skus:
        price = sku.get('price_rub', 0)
        if price == 0 and not sku.get('free') and not sku.get('is_free'):
            zero_price.append(f"{mid} ({sku.get('notes','')})")
        if price < 0:
            negative_price.append(f"{mid} ({price})")
if zero_price: print(f"   ⚠️  Zero price SKUs: {zero_price[:5]}...")
if negative_price: print(f"   ❌ Negative prices: {negative_price}")
if no_skus: print(f"   ❌ Models without SKUs: {no_skus}")
if not (zero_price or negative_price or no_skus):
    print("   ✅ All prices valid")

# 4. model_copy.yaml coverage
model_copy = load_yaml('app/models/model_copy.yaml')
copy_ids = set(model_copy.keys()) if isinstance(model_copy, dict) else set()
missing_copy = pricing_ids - copy_ids
print(f"\n[4] MODEL COPY COVERAGE")
print(f"   model_copy.yaml entries: {len(copy_ids)}")
if missing_copy:
    print(f"   ⚠️  Models without copy: {sorted(missing_copy)[:10]}")
else:
    print("   ✅ All models have copy")

# 5. Registry schema validation
print(f"\n[5] REGISTRY SCHEMA VALIDATION")
schema_issues = []
for mid, mdata in registry['models'].items():
    if 'model_type' not in mdata:
        schema_issues.append(f"{mid}: missing model_type")
    if 'input' not in mdata:
        schema_issues.append(f"{mid}: missing input")
    inp = mdata.get('input', {})
    has_required = any(v.get('required') for v in inp.values() if isinstance(v, dict))
    if not has_required:
        schema_issues.append(f"{mid}: no required inputs")
if schema_issues:
    for issue in schema_issues[:10]:
        print(f"   ⚠️  {issue}")
else:
    print("   ✅ All models have valid schema")

# 6. Pricing catalog modes vs RUB SKUs count
print(f"\n[6] PRICING MODES vs RUB SKUs COUNT")
mode_mismatches = []
pricing_map = {m['id']: m for m in pricing['models']}
rub_map = {m['id']: m for m in pricing_rub['models']}
for mid in pricing_ids & rub_ids:
    n_modes = len(pricing_map[mid].get('modes', []))
    n_skus = len(rub_map[mid].get('skus', []))
    if n_modes != n_skus:
        mode_mismatches.append(f"{mid}: {n_modes} modes vs {n_skus} SKUs")
if mode_mismatches:
    for mm in mode_mismatches[:10]:
        print(f"   ⚠️  {mm}")
else:
    print("   ✅ All modes/SKUs counts match")

# 7. USD_TO_RUB consistency
print(f"\n[7] USD_TO_RUB CONSISTENCY")
pricing_config = load_yaml('pricing/config.yaml')
ssot_rate = pricing_config.get('settings', {}).get('usd_to_rub')
print(f"   SSOT rate (pricing/config.yaml): {ssot_rate}")
# Check other files
import ast
files_to_check = {
    'config.py': None,
    'pricing_transparency.py': None,
    'pricing/engine.py': None,
}
for fpath in files_to_check:
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            for line in f:
                if 'USD_TO_RUB' in line and '=' in line and '#' not in line.split('=')[0]:
                    # Extract number
                    nums = re.findall(r'[\d.]+', line.split('=')[1].split('#')[0])
                    if nums:
                        files_to_check[fpath] = float(nums[0])
                        break
    except Exception:
        pass
all_ok = True
for fpath, rate in files_to_check.items():
    if rate and rate != ssot_rate:
        print(f"   ❌ {fpath}: {rate} (should be {ssot_rate})")
        all_ok = False
    elif rate:
        print(f"   ✅ {fpath}: {rate}")
if all_ok:
    print("   ✅ All rates consistent")

print(f"\n{'=' * 60}")
print("AUDIT COMPLETE")
print("=" * 60)
