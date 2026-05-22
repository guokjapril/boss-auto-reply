import asyncio

from playwright.async_api import Page

from src.logger import setup_logger


class LoginHandler:
    """处理 BOSS 直聘登录流程。"""

    BOSS_URL = "https://www.zhipin.com"
    CHAT_URL = "https://www.zhipin.com/web/chat/index"
    LOGIN_TIMEOUT = 120  # 扫码超时（秒）

    def __init__(self, config: dict):
        self.logger = setup_logger()

    async def ensure_logged_in(self, page: Page) -> bool:
        """确保已登录，返回是否成功。"""
        self.logger.info("正在检查登录状态…")

        # 先到首页检查
        await page.goto(self.BOSS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        if await self._is_logged_in(page):
            self.logger.info("已登录，跳过扫码流程")
            return True

        return await self._qr_login(page)

    async def _is_logged_in(self, page: Page) -> bool:
        """检测页面是否已登录。"""
        try:
            # 检查是否有登录按钮（未登录状态的特征）
            login_btn = page.locator('text=登录').first
            if await login_btn.count() > 0:
                return False

            # 检查是否有用户头像/昵称（已登录特征）
            user_menu = page.locator('[class*="user"], .user-nav, .header-login, [class*="avatar"]').first
            if await user_menu.count() > 0:
                return True

            # 通过 cookie 辅助判断
            cookies = await page.context.cookies()
            for c in cookies:
                if c.get("name") in ("token", "wt", "utoken") and c.get("value"):
                    return True
        except Exception:
            pass
        return False

    async def _qr_login(self, page: Page) -> bool:
        """等待用户扫码登录。"""
        self.logger.info("=" * 50)
        self.logger.info("请使用 BOSS直聘 APP 扫码登录")
        self.logger.info("等待扫码中（超时 %d 秒）…", self.LOGIN_TIMEOUT)
        self.logger.info("=" * 50)

        # BOSS 直聘首页通常有微信扫码 / APP扫码入口
        # 先尝试找到并点击"登录"按钮
        try:
            login_btn = page.locator('text=登录').first
            if await login_btn.count() > 0:
                await login_btn.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # 尝试切换到扫码登录 tab（BOSS 有时默认是密码登录）
        try:
            qr_tab = page.locator('text=扫码登录').first
            if await qr_tab.count() > 0:
                await qr_tab.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        # 等待登录完成
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.LOGIN_TIMEOUT:
                self.logger.error("扫码登录超时")
                return False

            if await self._is_logged_in(page):
                self.logger.info("扫码登录成功！")
                await asyncio.sleep(2)
                return True

            # 每5秒输出一次等待提示
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                remaining = self.LOGIN_TIMEOUT - int(elapsed)
                self.logger.info("仍在等待扫码… 剩余 %d 秒", remaining)

            await asyncio.sleep(1)
