"""
Login to KIE.ai and save storage state for authenticated requests.
"""

import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path(".cache/kie_storage_state.json")
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

KIE_URL = "https://kie.ai"
LOGIN_URL = "https://kie.ai/login"


def main():
    email = os.getenv("KIE_EMAIL")
    password = os.getenv("KIE_PASSWORD")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"Navigating to {LOGIN_URL}...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        if email and password:
            print("Using KIE_EMAIL and KIE_PASSWORD from environment...")
            # Try to find email and password fields
            try:
                email_input = page.locator('input[type="email"], input[name="email"], input[id*="email"]').first
                password_input = page.locator('input[type="password"], input[name="password"], input[id*="password"]').first
                
                if email_input.is_visible(timeout=3000):
                    email_input.fill(email)
                    password_input.fill(password)
                    
                    # Try to find and click submit button
                    submit_button = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Login")').first
                    if submit_button.is_visible(timeout=2000):
                        submit_button.click()
                        page.wait_for_timeout(3000)
                    else:
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Auto-login failed: {e}")
                print("Please login manually in the browser window...")
        else:
            print("KIE_EMAIL/KIE_PASSWORD not set. Please login manually in the browser window...")

        # Wait for user to login manually
        print("\nWaiting for login...")
        print("Please complete the login in the browser window.")
        print("After successful login, press Enter here to save the session...")
        input()

        # Check if we're logged in by trying to access a protected page
        page.goto(KIE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Save storage state
        storage_state = context.storage_state()
        STATE_PATH.write_text(
            storage_state, encoding="utf-8"
        )

        # Verify login worked
        current_url = page.url
        if "login" not in current_url.lower():
            print(f"\n✅ Storage state saved to {STATE_PATH}")
        else:
            print(f"\n⚠️ Still on login page. Please login manually and press Enter again.")
            input()
            storage_state = context.storage_state()
            STATE_PATH.write_text(
                json.dumps(storage_state, indent=2), encoding="utf-8"
            )
            print(f"✅ Storage state saved to {STATE_PATH}")
        browser.close()


if __name__ == "__main__":
    main()
