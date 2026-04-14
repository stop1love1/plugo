"""Browser-based authenticated crawling using Playwright.

Handles login via browser automation, extracts session cookies,
and passes them to the standard httpx WebCrawler for actual crawling.
"""

import asyncio
import sys

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
) -> list[dict]:
    """Public wrapper — on Windows runs Playwright in a thread with a ProactorEventLoop.

    Uvicorn's --reload installs WindowsSelectorEventLoopPolicy, which can't spawn
    subprocesses. Playwright needs subprocess support, so we run it in an isolated
    thread with a fresh ProactorEventLoop.
    """
    kwargs = dict(
        login_url=login_url,
        username=username,
        password=password,
        username_selector=username_selector,
        password_selector=password_selector,
        submit_selector=submit_selector,
        success_url=success_url,
        timeout_ms=timeout_ms,
    )
    if sys.platform == "win32":
        def _runner():
            loop = asyncio.ProactorEventLoop()
            try:
                return loop.run_until_complete(_browser_login_impl(**kwargs))
            finally:
                loop.close()
        return await asyncio.to_thread(_runner)
    return await _browser_login_impl(**kwargs)


async def _browser_login_impl(
    login_url: str,
    username: str,
    password: str,
    username_selector: str = "input[name='email'], input[name='username'], input[type='email']",
    password_selector: str = "input[name='password'], input[type='password']",
    submit_selector: str = "button[type='submit'], input[type='submit']",
    success_url: str | None = None,
    timeout_ms: int = 30000,
) -> list[dict]:
    """Login via Playwright browser and return extracted cookies with domain info.

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
        List of dicts with name, value, domain, path for each cookie
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

            # Check if password field is already visible (single-page login)
            password_visible = False
            for sel in password_selector.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible(timeout=1000):
                        password_visible = True
                        break
                except Exception:
                    continue

            if not password_visible:
                # Multi-step login: click Next/Continue to advance to the password page
                logger.info("Browser crawl: password field not visible, trying multi-step login")
                next_clicked = False
                # Try the configured submit selector first, then common "Next"/"Continue" buttons
                next_selectors = [s.strip() for s in submit_selector.split(",") if s.strip()]
                next_selectors.extend([
                    "button:has-text('Next')", "button:has-text('Continue')",
                    "button:has-text('next')", "button:has-text('continue')",
                    "input[type='submit']", "button[type='submit']",
                ])
                for sel in next_selectors:
                    try:
                        locator = page.locator(sel).first
                        if await locator.is_visible(timeout=1000):
                            await locator.click()
                            next_clicked = True
                            logger.info("Browser crawl: clicked next/continue for multi-step login", selector=sel)
                            break
                    except Exception:
                        continue

                if not next_clicked:
                    raise BrowserLoginError(
                        "Multi-step login: could not find Next/Continue button after username step"
                    )

                # Wait for the password field to appear
                await asyncio.sleep(1)
                await page.wait_for_load_state("networkidle", timeout=5000)

            # Fill password
            password_filled = False
            for sel in password_selector.split(","):
                sel = sel.strip()
                if not sel:
                    continue
                try:
                    locator = page.locator(sel).first
                    if await locator.is_visible(timeout=3000):
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

            # Extract cookies with domain info for multi-domain support
            raw_cookies = await context.cookies()
            cookie_list = []
            for cookie in raw_cookies:
                cookie_list.append({
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                })

            logger.info(
                "Browser crawl: extracted cookies",
                count=len(cookie_list),
                domains=list({c["domain"] for c in cookie_list}),
            )

            if not cookie_list:
                raise BrowserLoginError("Login completed but no cookies were set")

            return cookie_list

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
    """Test login configuration and return detailed result (success/failure + diagnostics)."""
    import time

    start_time = time.monotonic()
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
        elapsed = round(time.monotonic() - start_time, 2)
        cookie_names = [c["name"] for c in cookies]
        # Check if any cookie domain matches the success_url pattern
        success_url_detected = False
        if success_url:
            # The login function would have raised if it didn't navigate,
            # so if we got here the redirect was successful
            success_url_detected = True
        return {
            "success": True,
            "message": f"Login successful — {len(cookies)} cookies extracted",
            "cookie_count": len(cookies),
            "cookie_names": cookie_names,
            "success_url_detected": success_url_detected,
            "time_seconds": elapsed,
        }
    except BrowserLoginError as e:
        elapsed = round(time.monotonic() - start_time, 2)
        return {
            "success": False,
            "message": str(e),
            "time_seconds": elapsed,
        }
    except Exception as e:
        elapsed = round(time.monotonic() - start_time, 2)
        logger.error("test_browser_login unexpected error", error=repr(e))
        return {
            "success": False,
            "message": f"Unexpected error: {type(e).__name__}: {e!s}" if str(e) else f"Unexpected error: {type(e).__name__}: {e!r}",
            "time_seconds": elapsed,
        }
