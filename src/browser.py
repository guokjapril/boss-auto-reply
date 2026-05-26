import asyncio
import os
import random
import sys
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from src.paths import base_dir
from src.logger import setup_logger


class BrowserManager:
    def __init__(self, config: dict):
        self.cfg = config
        self.logger = setup_logger()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._firefox_exe: Optional[str] = None

    async def start(self) -> Page:
        self._firefox_exe = self._find_firefox()

        self._playwright = await async_playwright().start()

        user_data_dir = self.cfg["browser"]["user_data_dir"]
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)

        launch_kwargs = {
            "headless": self.cfg["browser"].get("headless", False),
            "args": ["-wait-for-browser"],
        }
        if self._firefox_exe:
            launch_kwargs["executable_path"] = self._firefox_exe

        self._browser = await self._playwright.firefox.launch(**launch_kwargs)

        self._context = await self._browser.new_context(
            viewport=self.cfg["browser"].get("viewport", {"width": 1280, "height": 800}),
            locale=self.cfg["browser"].get("locale", "zh-CN"),
            timezone_id=self.cfg["browser"].get("timezone_id", "Asia/Shanghai"),
        )

        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        self._page = await self._context.new_page()
        self.logger.info("Firefox 浏览器已启动")
        return self._page

    def _find_firefox(self) -> Optional[str]:
        """查找 Firefox 可执行文件，优先使用捆绑的 ms-playwright 目录。"""
        bundled = base_dir() / "ms-playwright"
        if bundled.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)
            for pattern in ["firefox-*/firefox/firefox.exe", "firefox-*/firefox/firefox"]:
                for match in sorted(bundled.glob(pattern)):
                    self.logger.info("使用捆绑的浏览器: %s", match)
                    return str(match)
        return None

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.logger.info("浏览器已关闭")

    @staticmethod
    async def random_delay(min_s: float = 0.2, max_s: float = 2.0):
        await asyncio.sleep(random.uniform(min_s, max_s))
