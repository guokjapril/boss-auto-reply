import asyncio

from playwright.async_api import Page

from src.logger import setup_logger


class LoginHandler:
    """处理 BOSS 直聘登录流程。"""

    BOSS_URL = "https://www.zhipin.com"
    LOGIN_URL = "https://www.zhipin.com/web/user/"
    LOGIN_TIMEOUT = 120

    def __init__(self, config: dict):
        self.logger = setup_logger()

    async def ensure_logged_in(self, page: Page) -> bool:
        self.logger.info("正在检查登录状态…")

        await page.goto(self.BOSS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await self._is_logged_in(page):
            self.logger.info("已登录，跳过扫码流程")
            return True

        return await self._qr_login(page)

    async def _is_logged_in(self, page: Page) -> bool:
        try:
            cookies = await page.context.cookies()
            for c in cookies:
                if c.get("name") in ("wt", "wt2", "zp_at", "wbg", "bst", "utoken", "wtsso") and c.get("value"):
                    self.logger.warning("检测到 BOSS 认证 cookie: %s=%s...", c.get("name"), c.get("value")[:20])
                    login_btn = page.locator('text=登录').first
                    if await login_btn.count() > 0:
                        return False
                    return True

            login_btn = page.locator('text=登录').first
            if await login_btn.count() > 0:
                return False

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

        try:
            qr_tab = page.locator('text=扫码登录').first
            if await qr_tab.count() > 0:
                await qr_tab.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        start_time = asyncio.get_event_loop().time()
        last_log_time = 0
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.LOGIN_TIMEOUT:
                self.logger.error("扫码登录超时")
                return False

            # 页面健康检查：如果跳到了 about:blank，重新导航
            url = page.url
            if not url or "about:blank" in url:
                self.logger.warning("页面异常: %s，重新导航…", url)
                await page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                continue

            if await self._is_logged_in(page):
                self.logger.info("扫码登录成功！")
                await asyncio.sleep(2)
                return True

            if int(elapsed) - last_log_time >= 10:
                last_log_time = int(elapsed)
                remaining = self.LOGIN_TIMEOUT - int(elapsed)
                self.logger.info("仍在等待扫码… 剩余 %d 秒", remaining)

            await asyncio.sleep(1)
