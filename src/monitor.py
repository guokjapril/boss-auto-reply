import asyncio
import hashlib
import json
from typing import Callable

from playwright.async_api import Page

from src.paths import data_path
from src.logger import setup_logger


class MessageMonitor:
    """轮询 BOSS 直聘消息列表，检测新消息。"""

    CHAT_URL = "https://www.zhipin.com/web/chat/index"

    def __init__(self, config: dict):
        self.cfg = config.get("monitor", {})
        self.logger = setup_logger()
        self._processed: set[str] = set()
        self._processed_file = data_path("data/processed_messages.json")
        self._load_processed()

    def _load_processed(self):
        if self._processed_file.exists():
            try:
                data = json.loads(self._processed_file.read_text())
                self._processed = set(data)
                self.logger.info("已加载 %d 条历史回复记录", len(self._processed))
            except Exception:
                pass

    def _save_processed(self):
        self._processed_file.parent.mkdir(parents=True, exist_ok=True)
        self._processed_file.write_text(json.dumps(list(self._processed), ensure_ascii=False))

    def _make_msg_id(self, name: str, text: str) -> str:
        raw = f"{name}|{text}"
        return hashlib.md5(raw.encode()).hexdigest()

    async def navigate_to_chat(self, page: Page):
        self.logger.info("正在进入消息列表…")

        for attempt in range(3):
            await page.goto(self.CHAT_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            current_url = page.url
            self.logger.info("当前页面: %s (第%d次)", current_url, attempt + 1)

            if "chat" in current_url:
                self.logger.info("已进入消息列表")
                return

            # 如果被重定向，尝试点击跳过引导
            if "guide" in current_url:
                self.logger.info("检测到引导页，尝试跳过…")
                for sel in ['text=跳过', 'text=我知道了', 'text=完成', 'text=好的',
                            '.guide-skip', '.skip-btn', 'button:has-text("跳过")']:
                    try:
                        btn = page.locator(sel).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(1)
                    except Exception:
                        continue

            self.logger.info("未进入聊天页，重试…")

        self.logger.warning("多次尝试后仍在: %s，继续轮询", page.url)

    async def poll(self, page: Page, on_new_message: Callable, reply_engine) -> None:
        poll_interval = self.cfg.get("poll_interval", 10)
        max_pages = self.cfg.get("max_pages", 5)
        self.logger.info("开始轮询消息，间隔 %d 秒", poll_interval)

        while True:
            try:
                # 检查页面健康状态
                if not await self._check_page_health(page):
                    self.logger.warning("页面异常，尝试恢复到聊天页…")
                    await page.goto(self.CHAT_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    continue

                new_messages = await self._scan_messages(page, max_pages)
                for msg in new_messages:
                    msg_id = self._make_msg_id(msg["name"], msg["text"])
                    if msg_id in self._processed:
                        continue

                    self.logger.info("新消息: %s — %s", msg["name"], msg["text"])
                    await on_new_message(msg, reply_engine, page)
                    self._processed.add(msg_id)
                    self._save_processed()

            except Exception as e:
                self.logger.error("轮询异常: %s", e)

            await asyncio.sleep(poll_interval)

    async def _check_page_health(self, page: Page) -> bool:
        try:
            url = page.url
            if not url or "about:blank" in url:
                return False
            if "zhipin.com" not in url:
                return False
            if "chat" not in url:
                return False
            return True
        except Exception:
            return False

    async def _scan_messages(self, page: Page, max_pages: int) -> list[dict]:
        messages = []

        try:
            await page.wait_for_selector(
                '[class*="chat"], [class*="message"], [class*="dialog"], [class*="conversation"]',
                timeout=5000
            )
        except Exception:
            pass

        for _ in range(max_pages):
            cards = await self._extract_cards(page)
            messages.extend(cards)

            has_next = await self._scroll_or_next(page)
            if not has_next:
                break

        return messages

    async def _extract_cards(self, page: Page) -> list[dict]:
        messages = []

        selectors = [
            '.chat-list-item',
            '[class*="chat-item"]',
            '[class*="conversation-item"]',
            '.message-item',
            'li[class*="chat"]',
        ]

        for selector in selectors:
            items = page.locator(selector)
            count = await items.count()
            if count > 0:
                for i in range(count):
                    try:
                        item = items.nth(i)
                        name_el = item.locator('[class*="name"], .user-name, [class*="title"]').first
                        msg_el = item.locator('[class*="last-msg"], [class*="summary"], [class*="content"], p').first
                        unread_el = item.locator('[class*="unread"], [class*="badge"], .red-dot').first

                        name = (await name_el.text_content() or "").strip() if await name_el.count() > 0 else "未知"
                        text = (await msg_el.text_content() or "").strip() if await msg_el.count() > 0 else ""
                        has_unread = await unread_el.count() > 0

                        if name and text:
                            messages.append({"name": name, "text": text, "unread": has_unread})
                    except Exception:
                        continue
                break

        return messages

    async def _scroll_or_next(self, page: Page) -> bool:
        try:
            prev_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
            new_height = await page.evaluate("document.body.scrollHeight")
            return new_height > prev_height
        except Exception:
            return False
