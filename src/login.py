import asyncio

from playwright.async_api import Page

from src.logger import setup_logger


class LoginHandler:
    """处理 BOSS 直聘登录流程。"""

    BOSS_URL = "https://www.zhipin.com"
    LOGIN_URL = "https://www.zhipin.com/web/user/"
    CHAT_URL = "https://www.zhipin.com/web/chat/index"
    LOGIN_TIMEOUT = 120

    def __init__(self, config: dict):
        self.logger = setup_logger()

    async def ensure_logged_in(self, page: Page) -> bool:
        self.logger.info("正在检查登录状态…")

        await self._setup_about_blank_guard(page)

        await page.goto(self.BOSS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        await self._check_page_health(page)

        if await self._is_logged_in(page):
            self.logger.info("已登录，跳过扫码流程")
            return True

        return await self._qr_login(page)

    async def _setup_about_blank_guard(self, page: Page):
        """只拦截主页面导航到 about:blank，子资源请求直接放行。"""
        async def handle_route(route):
            if not route.request.is_navigation_request():
                await route.continue_()
                return
            try:
                response = await route.fetch()
                loc = (response.headers.get("location") or "").lower()
                if response.status in (301, 302, 303, 307, 308) and "about:blank" in loc:
                    self.logger.debug("拦截到 about:blank 重定向，已阻止")
                    await route.abort()
                    return
                await route.fulfill(response=response)
            except Exception:
                await route.continue_()

        await page.route("**/*", handle_route)

    async def _check_page_health(self, page: Page, fallback_url: str = None) -> bool:
        if fallback_url is None:
            fallback_url = self.BOSS_URL
        url = page.url
        if not url or "about:blank" in url or "zhipin.com" not in url:
            self.logger.warning("页面异常: %s，正在重新导航…", url)
            await page.goto(fallback_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            return False
        return True

    async def _is_logged_in(self, page: Page) -> bool:
        """检测页面是否已登录。优先通过 cookie 判断。"""
        try:
            # 1. 优先检查 BOSS 专用 cookie（扫码后服务端设置的可靠信号）
            cookies = await page.context.cookies()
            cookie_names = [c.get("name") for c in cookies if c.get("value")]
            self.logger.debug("当前 cookies (%d个): %s", len(cookie_names), cookie_names)

            for c in cookies:
                if c.get("name") in ("wt", "wt2", "zp_at", "wbg", "bst", "utoken", "wtsso") and c.get("value"):
                    self.logger.warning("检测到 BOSS 认证 cookie: %s=%s...", c.get("name"), c.get("value")[:20])
                    # 二次确认：cookie 存在后检查页面确认没有登录按钮
                    try:
                        login_btn = page.locator('text=登录').first
                        if await login_btn.count() > 0:
                            self.logger.debug("cookie 存在但页面仍有登录按钮，继续等待…")
                            return False
                    except Exception:
                        pass
                    return True

            # 2. 检查页面 UI
            login_btn = page.locator('text=登录').first
            if await login_btn.count() > 0:
                return False

            # 3. 检查用户菜单（已登录的视觉特征）
            user_menu = page.locator('[class*="user"], .user-nav, .header-login, [class*="avatar"], [class*="nickname"]').first
            if await user_menu.count() > 0:
                return True

        except Exception as e:
            self.logger.debug("登录检测异常: %s", e)
        return False

    async def _qr_login(self, page: Page) -> bool:
        self.logger.info("=" * 50)
        self.logger.info("请使用 BOSS直聘 APP 扫码登录")
        self.logger.info("等待扫码中（超时 %d 秒）…", self.LOGIN_TIMEOUT)
        self.logger.info("=" * 50)

        await page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self._check_page_health(page, fallback_url=self.LOGIN_URL)

        try:
            qr_tab = page.locator('text=扫码登录').first
            if await qr_tab.count() > 0:
                await qr_tab.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        start_time = asyncio.get_event_loop().time()
        last_log_time = 0
        recover_count = 0
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.LOGIN_TIMEOUT:
                self.logger.error("扫码登录超时")
                return False

            if not await self._check_page_health(page, fallback_url=self.LOGIN_URL):
                recover_count += 1
                delay = min(recover_count * 2, 15)
                await asyncio.sleep(delay)
                continue

            recover_count = 0

            if await self._is_logged_in(page):
                self.logger.info("扫码登录成功！")
                await asyncio.sleep(2)
                return True

            if int(elapsed) - last_log_time >= 10:
                last_log_time = int(elapsed)
                remaining = self.LOGIN_TIMEOUT - int(elapsed)
                self.logger.info("仍在等待扫码… 剩余 %d 秒", remaining)

            await asyncio.sleep(1)
