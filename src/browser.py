import asyncio
import os
import random
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page

from src.paths import base_dir, is_frozen
from src.logger import setup_logger


class BrowserManager:
    def __init__(self, config: dict):
        self.cfg = config
        self.logger = setup_logger()
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def start(self) -> Page:
        self._setup_browser_path()
        await self._ensure_browser_installed()

        self._playwright = await async_playwright().start()

        user_data_dir = self.cfg["browser"]["user_data_dir"]
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)

        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self.cfg["browser"].get("headless", False),
            viewport=self.cfg["browser"].get("viewport", {"width": 1280, "height": 800}),
            locale=self.cfg["browser"].get("locale", "zh-CN"),
            timezone_id=self.cfg["browser"].get("timezone_id", "Asia/Shanghai"),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        await self._browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            window.chrome = { runtime: {} };
        """)

        pages = self._browser.pages
        self._page = pages[0] if pages else await self._browser.new_page()

        self.logger.info("浏览器已启动")
        return self._page

    def _setup_browser_path(self):
        """优先使用打包在 exe 同目录的 Chromium。"""
        bundled = base_dir() / "ms-playwright"
        if bundled.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)
            self.logger.info("使用捆绑的 Chromium: %s", bundled)

    async def _ensure_browser_installed(self):
        """确保 Chromium 浏览器已安装。"""
        p = await async_playwright().start()
        installed = False
        try:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
            installed = True
            self.logger.info("Chromium 浏览器已就绪")
            return
        except Exception:
            pass
        finally:
            if not installed:
                await p.stop()

        # 尝试自动安装
        self.logger.info("Chromium 未安装，正在自动下载（首次约 150MB）…")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                self.logger.info("Chromium 安装完成")
                return
        except Exception:
            pass

        # 最终 fallback：提供清晰指引
        raise RuntimeError(
            "\n".join([
                "=" * 50,
                "Chromium 浏览器未安装，自动安装失败。",
                "",
                "请手动安装（任选一种）：",
                "  1. pip install playwright && playwright install chromium",
                "  2. 从发布页面下载 BossAutoReply-Windows.zip（包含浏览器）",
                "=" * 50,
            ])
        )

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.logger.info("浏览器已关闭")

    @staticmethod
    async def random_delay(min_s: float = 0.2, max_s: float = 2.0):
        await asyncio.sleep(random.uniform(min_s, max_s))
