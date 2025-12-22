import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from playwright.sync_api import sync_playwright

MARKET_URL = "https://kie.ai/market"
STATE_PATH = Path(".cache/kie_storage_state.json")
PRICING_YAML = Path("pricing/config.yaml")
CATALOG_YAML = Path("models/catalog.yaml")
CATALOG_JSON = Path("models/catalog.json")

def die(msg: str):
    raise SystemExit(msg)

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def dump_yaml(path: Path, data: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    path.write_text(text, encoding="utf-8")

def dump_json(path: Path, data: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def normalize_price_matrix(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """If raw already has matrix format, return it"""
    if isinstance(raw, dict) and raw.get("type") == "matrix" and "table" in raw:
        return raw
    return None

def make_unsupported(raw: Any, reason: str) -> Dict[str, Any]:
    return {"unsupported": True, "reason": reason, "raw_pricing": raw}

def safe_model_id(s: str) -> str:
    return s.strip()

def guess_model_id_from_url(url: str) -> Optional[str]:
    """Извлекаем model_id из URL"""
    m = re.search(r"/market/([^/?#]+)", url)
    if m:
        slug = m.group(1)
        # wan-2-6-text-to-video -> wan/2-6-text-to-video
        if slug.startswith("wan-") and "-" in slug[4:]:
            slug = slug.replace("-", "/", 1)
        return slug
    return None

def extract_next_data(page) -> Optional[Dict[str, Any]]:
    try:
        nd = page.evaluate("() => window.__NEXT_DATA__ || null")
        if isinstance(nd, dict):
            return nd
    except Exception:
        pass
    return None

def extract_json_candidates(network_json: List[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
    """Find JSON responses that might contain model data"""
    candidates = []
    for url, payload in network_json:
        if not isinstance(payload, dict):
            continue
        # Простая проверка: есть ли ключевые слова
        payload_str = json.dumps(payload).lower()[:1000]
        if any(word in payload_str for word in ["model", "prompt", "schema", "fields"]):
            candidates.append((url, payload))
    return candidates

def extract_schema_and_pricing(payload: Any) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """Extract schema and pricing from JSON payload. Returns: (schema, pricing, title, meta)"""
    if not isinstance(payload, dict):
        return None, None, None, {}
    
    schema = None
    pricing = None
    title = None
    model_id = None
    
    # Простой поиск по ключам (без рекурсии)
    if "fields" in payload and isinstance(payload["fields"], list):
        schema = {}
        for f in payload["fields"]:
            if not isinstance(f, dict):
                continue
            fname = f.get("name") or f.get("key")
            if not fname:
                continue
            schema[fname] = {
                "type": str(f.get("type", "string")),
                "required": bool(f.get("required", False))
            }
            if "enum" in f:
                schema[fname]["values"] = [str(x) for x in f["enum"]]
            if "maxLength" in f:
                schema[fname]["max_len"] = int(f["maxLength"])
            if "max_length" in f:
                schema[fname]["max_len"] = int(f["max_length"])
    
    # Ищем в типичных местах
    for key in ["inputSchema", "schema", "input_schema"]:
        if key in payload and isinstance(payload[key], dict):
            schema = payload[key]
            break
    
    # Title
    for key in ["title", "name", "modelName"]:
        if key in payload and isinstance(payload[key], str):
            title = payload[key]
            break
    
    # Model ID
    for key in ["model", "model_id", "modelId", "id"]:
        if key in payload and isinstance(payload[key], str):
            model_id = payload[key]
            break
    
    # Pricing
    for key in ["pricing", "prices"]:
        if key in payload:
            pricing = payload[key]
            break
    
    return schema, pricing, title, {"model_id": model_id}

def click_api_tab(page):
    # The UI has a tab called API
    selectors = [
        "text=API",
        "role=tab[name='API']",
        "a:has-text('API')",
        "button:has-text('API')",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1200):
                loc.click()
                page.wait_for_timeout(800)
                return
        except Exception:
            continue

def collect_model_links(page) -> List[str]:
    """Собираем ссылки на модели со страницы market"""
    links = set()
    # Скроллим страницу чтобы загрузить все модели
    for _ in range(10):
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(500)
    
    # Ищем все ссылки с /market/
    for link in page.locator('a[href*="/market/"]').all():
        try:
            href = link.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://kie.ai" + href
            if "/market/" in href and href != MARKET_URL:
                links.add(href.split("#")[0].split("?")[0])
        except:
            pass
    return sorted(links)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--only", type=str, default=None, help="Prefix filter like 'wan/'")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not STATE_PATH.exists():
        die(f"Missing {STATE_PATH}. Run: python tools/kie_sync/login_kie.py")

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
        ctx = browser.new_context(storage_state=str(STATE_PATH))
        page = ctx.new_page()

        # Capture JSON responses
        network_json: List[Tuple[str, Any]] = []

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
        # Filter out duplicates and generic market pages
        links = [u for u in links if u != MARKET_URL and "/market" in u]

        if args.only:
            links = [u for u in links if args.only in u]

        if args.limit and args.limit > 0:
            links = links[: args.limit]

        print(f"Found candidate links: {len(links)}")

        # Process each model page
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

            # Prefer candidates first; fallback to next_data
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

            # Pricing update (best-effort: if we already manually added wan* keep as-is unless we detect a matrix block)
            # For now: if model already exists in pricing and is not empty -> don't overwrite unless we can normalize matrix cleanly.
            existing = pricing_cfg["models"].get(model_id)
            new_pricing_block = None

            # If the page text contains the "Pricing: ... $0.xx ..." we can attempt regex extraction as LAST resort.
            # But do NOT do regex by default (unstable). Only mark unsupported.
            if isinstance(raw_pricing, dict):
                maybe = normalize_price_matrix(raw_pricing)
                if maybe:
                    new_pricing_block = maybe

            if new_pricing_block is None:
                # Keep existing, else create unsupported placeholder
                if existing is None:
                    pricing_cfg["models"][model_id] = make_unsupported(raw_pricing, "pricing_not_extracted")
                    changed_pricing.append(model_id)
            else:
                if existing != new_pricing_block:
                    pricing_cfg["models"][model_id] = new_pricing_block
                    changed_pricing.append(model_id)

            print(f"[{processed}/{len(links)}] OK: {model_id} (json={best_url})")

        browser.close()

    # Update meta timestamps
    catalog_cfg.setdefault("meta", {})
    catalog_cfg["meta"]["source"] = "kie.ai/market"
    catalog_cfg["meta"]["synced_at"] = int(time.time() * 1000)

    print("\n=== SUMMARY ===")
    print(f"catalog changed: {len(changed_catalog)}")
    print(f"pricing changed: {len(changed_pricing)}")

    if args.dry_run and not args.sync:
        print("\nDRY RUN: no files written.")
        if changed_catalog:
            print("Catalog updates:", ", ".join(changed_catalog[:50]))
        if changed_pricing:
            print("Pricing updates:", ", ".join(changed_pricing[:50]))
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
