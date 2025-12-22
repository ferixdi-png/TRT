"""
CLI tool for testing pricing calculations
Usage: python -m pricing.cli --model "wan/2-6-text-to-video" --params "{\"duration\":\"5\",\"resolution\":\"1080p\"}"
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pricing.engine import calc_model_price_rub, get_model_credits


def main():
    parser = argparse.ArgumentParser(description="Calculate model price in RUB")
    parser.add_argument("--model", required=True, help="Model ID (e.g., wan/2-6-text-to-video)")
    parser.add_argument("--params", required=True, help="JSON string with parameters (e.g., {\"duration\":\"5\",\"resolution\":\"1080p\"})")
    parser.add_argument("--admin", action="store_true", help="Calculate admin price (no markup)")
    parser.add_argument("--credits", action="store_true", help="Show credits reference value")
    
    args = parser.parse_args()
    
    # Parse parameters
    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(f"Error parsing params JSON: {e}")
        sys.exit(1)
    
    # Calculate price
    try:
        price_rub = calc_model_price_rub(
            model_id=args.model,
            params=params,
            is_admin=args.admin
        )
        
        print(f"Model: {args.model}")
        print(f"Params: {params}")
        print(f"Price: {price_rub:.2f} RUB")
        if args.admin:
            print("(Admin price - no markup)")
        else:
            print("(Regular user price - with markup x2)")
        
        # Show credits if requested
        if args.credits:
            credits = get_model_credits(args.model, params)
            if credits is not None:
                print(f"Credits (reference): {credits}")
            else:
                print("Credits (reference): N/A")
        
    except Exception as e:
        print(f"Error calculating price: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
