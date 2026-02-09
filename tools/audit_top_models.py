"""Audit top models pricing and data integrity."""
from app.top_models import get_top_models, get_sku_price_rub, get_categories

def audit():
    models = get_top_models()
    categories = get_categories()
    
    print(f"=== TOP MODELS AUDIT ===")
    print(f"Total models: {len(models)}")
    print(f"Categories: {len(categories)}")
    
    no_price = []
    no_maps_to = []
    
    for m in models:
        model_id = m.get('id', 'unknown')
        for sku in m.get('skus', []):
            sku_id = sku.get('sku_id', 'unknown')
            pr = sku.get('price_ref', '')
            mk = sku.get('mode_key', '')
            maps_to = sku.get('maps_to', {})
            
            # Check price
            price = get_sku_price_rub(pr, mk) if pr else None
            if not price or price == 0:
                no_price.append(f"{model_id}/{sku_id}: ref={pr}")
            
            # Check maps_to
            if not maps_to or not maps_to.get('model_id'):
                no_maps_to.append(f"{model_id}/{sku_id}")
    
    print(f"\n=== ISSUES ===")
    print(f"SKUs without price: {len(no_price)}")
    for x in no_price[:5]:
        print(f"  ❌ {x}")
    
    print(f"\nSKUs without maps_to.model_id: {len(no_maps_to)}")
    for x in no_maps_to[:5]:
        print(f"  ⚠️ {x}")
    
    # Check model coverage
    print(f"\n=== MODEL DETAILS ===")
    for m in models:
        skus = m.get('skus', [])
        prices = []
        for sku in skus:
            pr = sku.get('price_ref', '')
            mk = sku.get('mode_key', '')
            p = get_sku_price_rub(pr, mk) if pr else 0
            prices.append(p or 0)
        
        min_p = min(prices) if prices else 0
        print(f"  {m.get('id')}: {len(skus)} SKUs, min price: {min_p:.2f} ₽")
    
    return len(no_price) == 0 and len(no_maps_to) == 0

if __name__ == "__main__":
    ok = audit()
    print(f"\n{'✅ ALL OK' if ok else '❌ ISSUES FOUND'}")
