"""
Kie.ai registry reconciler.

Safely merges upstream data into local SOURCE_OF_TRUTH without breaking existing contracts.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.kie_sync.config import (
    SOURCE_OF_TRUTH_PATH, UPSTREAM_JSON_PATH,
    USD_TO_RUB, MARKUP_MULTIPLIER
)

logging = None
try:
    import logging
    logger = logging.getLogger(__name__)
except:
    pass


class KieReconciler:
    """
    Reconciles upstream Kie.ai data with local SOURCE_OF_TRUTH.
    
    Rules:
    - NEVER delete existing fields
    - NEVER change required->optional or optional->required automatically
    - Add new fields as experimental=true
    - Add new models as disabled=true
    - Preserve all existing contracts
    """
    
    def __init__(self, ssot_path: Path = SOURCE_OF_TRUTH_PATH):
        self.ssot_path = ssot_path
    
    def load_ssot(self) -> Dict[str, Any]:
        """Load local SOURCE_OF_TRUTH."""
        if not self.ssot_path.exists():
            return {"version": "1.0.0", "models": {}}
        
        with open(self.ssot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_upstream(self) -> Dict[str, Any]:
        """Load upstream JSON."""
        if not UPSTREAM_JSON_PATH.exists():
            return {"models": {}}
        
        with open(UPSTREAM_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def calculate_pricing_rub(self, pricing_usd: float) -> float:
        """
        Calculate RUB price from USD: RUB = USD * 78 * 2
        
        Args:
            pricing_usd: Price in USD from upstream
            
        Returns:
            Price in RUB (Kie.ai cost, without markup)
        """
        # Formula: RUB = USD * FX * markup
        # But we store Kie.ai cost (without markup), so: RUB = USD * FX
        return round(pricing_usd * USD_TO_RUB, 2)
    
    def reconcile_model(
        self,
        model_id: str,
        upstream_data: Dict[str, Any],
        local_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Reconcile single model.
        
        Args:
            model_id: Model identifier
            upstream_data: Data from upstream
            local_data: Existing local data (None if new model)
            
        Returns:
            Reconciled model data
        """
        if local_data:
            # Existing model - preserve contract, add upstream metadata
            reconciled = local_data.copy()
            
            # Add upstream metadata (non-breaking)
            reconciled["_upstream"] = {
                "docs_url": upstream_data.get("docs_url"),
                "checksum": upstream_data.get("checksum"),
                "fetched_at": upstream_data.get("fetched_at"),
                "input_schema_upstream": upstream_data.get("input_schema", {}),
            }
            
            # Check for new fields in upstream
            upstream_schema = upstream_data.get("input_schema", {})
            local_schema = local_data.get("input_schema", {})
            
            # Extract local input properties (support both formats)
            local_properties = {}
            if "input" in local_schema and isinstance(local_schema["input"], dict):
                if "properties" in local_schema["input"]:
                    local_properties = local_schema["input"].get("properties", {})
                else:
                    local_properties = {k: v for k, v in local_schema["input"].items() 
                                      if k not in ("type", "required", "examples")}
            elif "properties" in local_schema:
                local_properties = local_schema.get("properties", {})
            else:
                local_properties = {k: v for k, v in local_schema.items() 
                                  if k not in ("type", "required", "examples")}
            
            # Add new fields as optional with experimental flag
            new_fields = {}
            for field_name, field_spec in upstream_schema.items():
                if field_name not in local_properties:
                    # New field - add as optional with experimental flag
                    new_field = field_spec.copy()
                    new_field["required"] = False  # Always optional for new fields
                    new_field["experimental"] = True
                    new_field["source"] = "kie_upstream"
                    new_fields[field_name] = new_field
            
            if new_fields:
                # Merge new fields into local schema
                if "input" in reconciled["input_schema"] and isinstance(reconciled["input_schema"]["input"], dict):
                    if "properties" in reconciled["input_schema"]["input"]:
                        reconciled["input_schema"]["input"]["properties"].update(new_fields)
                    else:
                        # Direct format in input
                        reconciled["input_schema"]["input"].update(new_fields)
                elif "properties" in reconciled["input_schema"]:
                    reconciled["input_schema"]["properties"].update(new_fields)
                else:
                    # Direct format
                    reconciled["input_schema"].update(new_fields)
            
            # Update pricing if upstream has USD (but don't overwrite if manual)
            upstream_pricing = upstream_data.get("pricing", {})
            if upstream_pricing.get("usd") and "pricing" in reconciled:
                upstream_usd = float(upstream_pricing["usd"])
                upstream_rub = self.calculate_pricing_rub(upstream_usd)
                
                # Only update if pricing source is not manual
                if reconciled["pricing"].get("source") != "manual":
                    reconciled["pricing"]["upstream_usd"] = upstream_usd
                    reconciled["pricing"]["rub_per_gen"] = upstream_rub
                    reconciled["pricing"]["source"] = "kie_upstream"
                    reconciled["pricing"]["markup_multiplier"] = MARKUP_MULTIPLIER
                    reconciled["pricing"]["fx_usd_rub"] = USD_TO_RUB
        
        else:
            # New model - create minimal safe entry
            reconciled = {
                "model_id": model_id,
                "disabled": True,  # Must be manually enabled
                "endpoint": upstream_data.get("endpoints", {}).get("create", "/api/v1/jobs/createTask"),
                "input_schema": {
                    "input": {
                        "type": "dict",
                        "required": True,
                        "properties": {}
                    }
                },
                "pricing": {
                    "source": "unknown",
                    "upstream_missing": True
                },
                "_metadata": {
                    "source": "kie_upstream",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "experimental": True
                }
            }
            
            # Add upstream schema
            upstream_schema = upstream_data.get("input_schema", {})
            if upstream_schema:
                if "input" in reconciled["input_schema"]:
                    reconciled["input_schema"]["input"]["properties"] = upstream_schema
                else:
                    reconciled["input_schema"]["properties"] = upstream_schema
            
            # Add required fields (prompt always required)
            if "input" in reconciled["input_schema"]:
                if "properties" in reconciled["input_schema"]["input"]:
                    props = reconciled["input_schema"]["input"]["properties"]
                    if "prompt" in props:
                        if "required" not in reconciled["input_schema"]["input"]:
                            reconciled["input_schema"]["input"]["required"] = []
                        if "prompt" not in reconciled["input_schema"]["input"]["required"]:
                            reconciled["input_schema"]["input"]["required"].append("prompt")
            
            # Add pricing if available
            upstream_pricing = upstream_data.get("pricing", {})
            if upstream_pricing.get("usd"):
                upstream_usd = float(upstream_pricing["usd"])
                upstream_rub = self.calculate_pricing_rub(upstream_usd)
                reconciled["pricing"] = {
                    "upstream_usd": upstream_usd,
                    "rub_per_gen": upstream_rub,
                    "source": "kie_upstream",
                    "markup_multiplier": MARKUP_MULTIPLIER,
                    "fx_usd_rub": USD_TO_RUB
                }
            
            # Add metadata
            reconciled["docs_url"] = upstream_data.get("docs_url")
            reconciled["_upstream"] = {
                "checksum": upstream_data.get("checksum"),
                "fetched_at": upstream_data.get("fetched_at")
            }
        
        return reconciled
    
    def reconcile(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Reconcile upstream data with local SOURCE_OF_TRUTH.
        
        Args:
            dry_run: If True, don't write files, only return diff
            
        Returns:
            Diff report: {"added_models": [], "changed_models": [], "new_fields": {}, "upstream_changes": {}}
        """
        ssot = self.load_ssot()
        upstream = self.load_upstream()
        
        local_models = ssot.get("models", {})
        upstream_models = upstream.get("models", {})
        
        diff = {
            "added_models": [],
            "changed_models": [],
            "new_fields": {},
            "upstream_changes": {}
        }
        
        # Reconcile each upstream model
        for model_id, upstream_data in upstream_models.items():
            local_data = local_models.get(model_id)
            
            if not local_data:
                # New model
                diff["added_models"].append(model_id)
            else:
                # Existing model - check for changes
                reconciled = self.reconcile_model(model_id, upstream_data, local_data)
                
                # Check if there are new fields
                upstream_schema = upstream_data.get("input_schema", {})
                local_schema = local_data.get("input_schema", {})
                
                # Extract local properties
                local_properties = {}
                if "input" in local_schema and isinstance(local_schema["input"], dict):
                    if "properties" in local_schema["input"]:
                        local_properties = local_schema["input"].get("properties", {})
                    else:
                        local_properties = {k: v for k, v in local_schema["input"].items() 
                                          if k not in ("type", "required", "examples")}
                elif "properties" in local_schema:
                    local_properties = local_schema.get("properties", {})
                else:
                    local_properties = {k: v for k, v in local_schema.items() 
                                      if k not in ("type", "required", "examples")}
                
                new_fields = [f for f in upstream_schema.keys() if f not in local_properties]
                if new_fields:
                    diff["new_fields"][model_id] = new_fields
                    diff["changed_models"].append(model_id)
        
        # Write reconciled SSOT if not dry_run
        if not dry_run:
            # Reconcile all models
            reconciled_models = {}
            for model_id, local_data in local_models.items():
                upstream_data = upstream_models.get(model_id)
                if upstream_data:
                    reconciled_models[model_id] = self.reconcile_model(model_id, upstream_data, local_data)
                else:
                    reconciled_models[model_id] = local_data  # Keep as-is
            
            # Add new models
            for model_id in diff["added_models"]:
                upstream_data = upstream_models[model_id]
                reconciled_models[model_id] = self.reconcile_model(model_id, upstream_data, None)
            
            # Update SSOT
            ssot["models"] = reconciled_models
            ssot["version"] = ssot.get("version", "1.0.0")
            ssot["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            ssot["_sync_metadata"] = {
                "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "upstream_checksum": upstream.get("_metadata", {}).get("checksum"),
                "dry_run": False
            }
            
            # Write to file
            with open(self.ssot_path, 'w', encoding='utf-8') as f:
                json.dump(ssot, f, ensure_ascii=False, indent=2)
        
        return diff

