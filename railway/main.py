from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uvicorn
import os
import asyncio

app = FastAPI()

class Account(BaseModel):
    email: str
    password: str
    proxy: str = None  # Optional proxy

@app.get("/")
def read_root():
    return {"status": "running", "service": "Gmail Checker (Playwright)"}

@app.post("/check")
async def check_gmail(account: Account):
    async with async_playwright() as p:
        # Launch options
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--mute-audio",
        ]

        proxy_config = None
        if account.proxy:
            # Parse proxy string (e.g., ip:port or user:pass@ip:port)
            parts = account.proxy.replace("http://", "").split("@")
            server = parts[-1] 
            credentials = parts[0] if len(parts) > 1 else None

            proxy_config = {"server": f"http://{server}"}
            if credentials:
                user, password = credentials.split(":", 1)
                proxy_config["username"] = user
                proxy_config["password"] = password

        try:
            browser = await p.chromium.launch(
                headless=True,
                args=launch_args,
                proxy=proxy_config,
                timeout=60000 
            )

            # Create context with anti-detect features
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 720},
            )

            page = await context.new_page()
            
            # Navigate to login
            await page.goto("https://accounts.google.com/", timeout=60000)
            
            # Fill email
            await page.fill('input[type="email"]', account.email)
            await page.keyboard.press("Enter")
            
            # Wait for either password input or error
            try:
                await page.wait_for_selector('input[type="password"], div[aria-atomic="true"][aria-live="assertive"]', timeout=30000)
            except:
                return {"status": "DEAD", "message": "Email not found or timeout"}

            # Check for email invalid
            if await page.locator('text="Couldn\'t find your Google Account"').count() > 0:
                return {"status": "DEAD", "message": "Email does not exist"}

            if await page.locator('input[type="password"]').count() == 0:
                 return {"status": "ERROR", "message": "Password field not found (Captcha?)"}

            # Fill password
            await page.fill('input[type="password"]', account.password)
            await page.keyboard.press("Enter")
            
            # Wait for navigation/result
            # Possible outcomes:
            # 1. URL changes to myaccount.google.com -> LIVE
            # 2. "Wrong password" text -> DEAD
            # 3. Phone verification / recovery email -> LOCKED (but password correct)
            # 4. Captcha -> ERROR
            
            try:
                await page.wait_for_navigation(timeout=30000)
            except:
                pass # Timeout waiting for nav is fine, we check content

            content = await page.content()
            url = page.url

            status = "ERROR"
            message = "Unknown"

            if "myaccount.google.com" in url or "apps.google.com" in url:
                status = "LIVE"
                message = "Login successful"
            elif "Wrong password" in content or "password you entered is incorrect" in content:
                status = "DEAD"
                message = "Wrong password"
            elif "challenge" in url or "disabled" in url or "verify" in url:
                status = "LOCKED"
                message = "2FA / Verification required"
            else:
                # Fallback check
                if await page.locator('text="Wrong password"').count() > 0:
                    status = "DEAD"
                    message = "Wrong password (selector)"
                elif await page.locator('a[href*="myaccount.google.com"]').count() > 0:
                     status = "LIVE"
                     message = "Logged in (selector)"
            
            await browser.close()
            return {"status": status, "message": message}

        except Exception as e:
            return {"status": "ERROR", "message": str(e)[:100]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
