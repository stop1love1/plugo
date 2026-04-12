"""Browser-based authenticated crawling using Playwright.

Handles login via browser automation, extracts session cookies,
and passes them to the standard httpx WebCrawler for actual crawling.
"""

import asyncio

from logging_config import logger

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserLoginError(Exception):
    pass


async def browser_login_and_extract_cookies(
    login_url: str,
    username: str,
    password: str,
    username_selector: str = "input[name='email'], input[name='username'], input[type='email']",
    password_selector: str = "input[name='password'], input[type='password']",
    submit_selector: str = "button[type='submit'], input[type='submit']",
    success_url: str | None = None,
    timeout_ms: int = 30000,
) -> dict[str, str]:
    """Login via Playwright browser and return extracted cookies as a dict.

    Args:
        login_url: The login page URL
        username: Username/email to fill
        password: Password to fill
        username_selector: CSS selector(s) for username field (comma-separated for fallback)
        password_selector: CSS selector(s) for password field (comma-separated for fallback)
        submit_selector: CSS selector(s) for submit button (comma-separated for fallback)
        success_url: URL pattern to wait for after login (optional)
        timeout_ms: Max time to wait for login to complete

    Returns:
        Dict of cookie name -> cookie value
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise BrowserLoginError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Navigate to login page
            logger.info("Browser crawl: navigating to login page", url=login_url)
            await page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_load_state("networkidle", timeout=10000)

            # Fill username — try each selector in the comma-separated list
            username_filled = False
            for sel in username_selector.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible(timeout=2000):
                        await locator.fill(username)
                        username_filled = True
                        logger.info("Browser crawl: filled username", selector=sel)
                        break
                except Exception:
                    continue

            if not username_filled:
                raise BrowserLoginError(
                    f"Could not find username field. Tried selectors: {username_selector}"
                )

            # Fill password
            password_filled = False
            for sel in password_selector.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible(timeout=2000):
                        await locator.fill(password)
                        password_filled = True
                        logger.info("Browser crawl: filled password", selector=sel)
                        break
                except Exception:
                    continue

            if not password_filled:
                raise BrowserLoginError(
                    f"Could not find password field. Tried selectors: {password_selector}"
                )

            # Click submit
            submit_clicked = False
            for sel in submit_selector.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible(timeout=2000):
                        await locator.click()
                        submit_clicked = True
                        logger.info("Browser crawl: clicked submit", selector=sel)
                        break
                except Exception:
                    continue

            if not submit_clicked:
                raise BrowserLoginError(
                    f"Could not find submit button. Tried selectors: {submit_selector}"
                )

            # Wait for login to complete
            if success_url:
                try:
                    await page.wait_for_url(f"**{success_url}**", timeout=timeout_ms)
                    logger.info("Browser crawl: login success — matched URL pattern", pattern=success_url)
                except Exception:
                    # Check if we navigated away from login page at least
                    current = page.url
                    if current == login_url:
                        raise BrowserLoginError(
                            f"Login failed — still on login page. Expected redirect to: {success_url}"
                        ) from None
                    logger.info("Browser crawl: navigated away from login page", current_url=current)
            else:
                # No success URL specified — wait for navigation away from login page
                try:
                    await page.wait_for_url(
                        lambda url: url != login_url,
                        timeout=timeout_ms,
                    )
                    logger.info("Browser crawl: navigated away from login page", current_url=page.url)
                except Exception:
                    raise BrowserLoginError(
                        "Login may have failed — page did not navigate away from login URL"
                    ) from None

            # Wait a bit for any post-login redirects/cookie setting
            await asyncio.sleep(1)
            await page.wait_for_load_state("networkidle", timeout=5000)

            # Extract cookies
            cookies = await context.cookies()
            cookie_dict = {}
            for cookie in cookies:
                cookie_dict[cookie["name"]] = cookie["value"]

            logger.info(
                "Browser crawl: extracted cookies",
                count=len(cookie_dict),
                domains=list({c.get("domain", "") for c in cookies}),
            )

            if not cookie_dict:
                raise BrowserLoginError("Login completed but no cookies were set")

            return cookie_dict

        except BrowserLoginError:
            raise
        except Exception as e:
            raise BrowserLoginError(f"Browser login failed: {e!s}") from e
        finally:
            await browser.close()


async def test_browser_login(
    login_url: str,
    username: str,
    password: str,
    username_selector: str = "input[name='email'], input[name='username'], input[type='email']",
    password_selector: str = "input[name='password'], input[type='password']",
    submit_selector: str = "button[type='submit'], input[type='submit']",
    success_url: str | None = None,
) -> dict:
    """Test login configuration and return result (success/failure + details)."""
    try:
        cookies = await browser_login_and_extract_cookies(
            login_url=login_url,
            username=username,
            password=password,
            username_selector=username_selector,
            password_selector=password_selector,
            submit_selector=submit_selector,
            success_url=success_url,
        )
        return {
            "success": True,
            "message": f"Login successful — {len(cookies)} cookies extracted",
            "cookie_count": len(cookies),
        }
    except BrowserLoginError as e:
        return {
            "success": False,
            "message": str(e),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Unexpected error: {e!s}",
        }
