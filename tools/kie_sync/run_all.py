"""
Run KIE Market sync with cookie-based auth (for CI/CD)
"""

import argparse
import os
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.kie_sync.export_market import (
    MARKET_URL, PRICING_YAML, CATALOG_YAML, CATALOG_JSON,
    die, load_yaml, dump_yaml, dump_json, make_unsupported,
    normalize_price_matrix, safe_model_id, guess_model_id_from_url,
    extract_next_data, extract_json_candidates, extract_schema_and_pricing,
    click_api_tab, collect_model_links
)

def create_context_with_cookie(browser, cookie_header: str):
    """Create browser context with cookie header (for CI)"""
    # Parse cookie header (format: "name1=value1; name2=value2")
    cookies = []
    for part in cookie_header.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".kie.ai",
                "path": "/"
            })
    
    context = browser.new_context()
    if cookies:
        # Set cookies for main domain and subdomains
        for cookie in cookies:
            try:
                context.add_cookies([cookie])
            except:
                # Try with different domain variations
                for domain in [".kie.ai", "kie.ai", "www.kie.ai"]:
                    try:
                        cookie["domain"] = domain
                        context.add_cookies([cookie])
                        break
                    except:
                        pass
    return context

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    # Check auth method
    cookie_header = os.getenv("KIE_COOKIE_HEADER")
    state_path = Path(".cache/kie_storage_state.json")
    
    if not cookie_header and not state_path.exists():
        die("Need either KIE_COOKIE_HEADER env var or .cache/kie_storage_state.json")

    pricing_cfg = load_yaml(PRICING_YAML)
    if "models" not in pricing_cfg:
        pricing_cfg["models"] = {}

    catalog_cfg = load_yaml(CATALOG_YAML)
    if "models" not in catalog_cfg:
        catalog_cfg["meta"] = {"source": "kie.ai/market", "synced_at": None}
        catalog_cfg["models"] = {}

    changed_pricing = []
    changed_catalog = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Use cookie header if available, otherwise storage state
        if cookie_header:
            # Don't log the cookie header (security)
            context = create_context_with_cookie(browser, cookie_header)
        else:
            context = browser.new_context(storage_state=str(state_path))
        
        page = context.new_page()

        # Capture JSON responses
        network_json = []

        def on_response(resp):
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    url = resp.url
                    data = resp.json()
                    network_json.append((url, data))
            except Exception:
                pass

        page.on("response", on_response)

        page.goto(MARKET_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        links = collect_model_links(page)
        links = [u for u in links if u != MARKET_URL and "/market" in u]

        if args.only:
            links = [u for u in links if args.only in u]

        if args.limit and args.limit > 0:
            links = links[:args.limit]

        print(f"Found {len(links)} model links")

        processed = 0
        for url in links:
            processed += 1
            network_json.clear()

            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            click_api_tab(page)
            page.wait_for_timeout(1200)

            nd = extract_next_data(page)
            candidates = extract_json_candidates(network_json)

            best_payload = candidates[0][1] if candidates else nd
            best_url = candidates[0][0] if candidates else "next_data"

            if not best_payload:
                print(f"SKIP (no JSON): {url}")
                continue

            schema, raw_pricing, title, meta = extract_schema_and_pricing(best_payload)
            model_id = meta.get("model_id") or guess_model_id_from_url(url) or guess_model_id_from_url(best_url)
            if not model_id:
                print(f"SKIP (no model_id): {url}")
                continue
            model_id = safe_model_id(model_id)

            # Catalog update
            catalog_entry = {
                "title": title or model_id,
                "source_url": url,
                "endpoint": {
                    "create_task": "/api/v1/jobs/createTask",
                    "query_task": "/api/v1/jobs/recordInfo",
                },
                "input_schema": schema or {"unsupported": True, "reason": "schema_not_extracted"},
            }

            old_cat = catalog_cfg["models"].get(model_id)
            if old_cat != catalog_entry:
                catalog_cfg["models"][model_id] = catalog_entry
                changed_catalog.append(model_id)

            # Pricing update
            existing = pricing_cfg["models"].get(model_id)
            new_pricing_block = None

            if isinstance(raw_pricing, dict):
                maybe = normalize_price_matrix(raw_pricing)
                if maybe:
                    new_pricing_block = maybe

            if new_pricing_block is None:
                if existing is None:
                    pricing_cfg["models"][model_id] = make_unsupported(raw_pricing, "pricing_not_extracted")
                    changed_pricing.append(model_id)
            else:
                if existing != new_pricing_block:
                    pricing_cfg["models"][model_id] = new_pricing_block
                    changed_pricing.append(model_id)

            print(f"[{processed}/{len(links)}] OK: {model_id}")

        browser.close()

    # Update meta
    import time
    catalog_cfg.setdefault("meta", {})
    catalog_cfg["meta"]["source"] = "kie.ai/market"
    catalog_cfg["meta"]["synced_at"] = int(time.time() * 1000)

    print("\n=== SUMMARY ===")
    print(f"catalog changed: {len(changed_catalog)}")
    print(f"pricing changed: {len(changed_pricing)}")

    if args.dry_run and not args.sync:
        print("\nDRY RUN: no files written.")
        return

    if not args.sync and not args.dry_run:
        print("No action. Use --sync to write files or --dry-run to preview.")
        return

    # Write outputs
    dump_yaml(CATALOG_YAML, catalog_cfg)
    dump_json(CATALOG_JSON, catalog_cfg)
    dump_yaml(PRICING_YAML, pricing_cfg)

    print(f"✅ Wrote: {CATALOG_YAML}, {CATALOG_JSON}, {PRICING_YAML}")

if __name__ == "__main__":
    main()



