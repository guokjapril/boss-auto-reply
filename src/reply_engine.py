import asyncio
import random
import time
from typing import Optional

from playwright.async_api import Page

from src.logger import setup_logger
from src.ai_client import AIClient


class ReplyEngine:
    """回复引擎：模板匹配 + AI 生成（预留）。"""

    def __init__(self, config: dict):
        self.cfg = config.get("reply", {})
        self.logger = setup_logger()
        self._mode = self.cfg.get("mode", "template")
        self._send_count = 0
        self._hour_start = time.time()
        self._ai_client: Optional[AIClient] = None

        if self._mode == "ai":
            self._ai_client = AIClient(config)
            self.logger.info("回复引擎: AI 模式")
        else:
            self.logger.info("回复引擎: 模板模式（已加载 %d 条模板）",
                              len(self.cfg.get("templates", [])))

    async def reply(self, msg: dict, page: Page) -> bool:
        """处理单条消息的回复流程。"""
        # 速率限制
        if not self._check_rate_limit():
            self.logger.warning("已达每小时回复上限，跳过本次回复")
            return False

        name = msg.get("name", "候选人")
        text = msg.get("text", "")

        # 生成回复内容
        reply_text = await self._generate_reply(name, text)
        if not reply_text:
            return False

        # 点击对应会话进入聊天
        success = await self._open_chat(page, name)
        if not success:
            self.logger.warning("无法打开与 %s 的聊天窗口", name)
            return False

        # 发送消息
        sent = await self._send_message(page, reply_text)
        if sent:
            self._send_count += 1
            self.logger.info("已回复 %s: %s", name, reply_text)
        return sent

    async def _generate_reply(self, name: str, message: str) -> Optional[str]:
        if self._mode == "ai" and self._ai_client:
            return await self._ai_client.generate_reply(name, message)

        return self._match_template(message)

    def _match_template(self, message: str) -> str:
        """智能匹配：负面检测 + 多关键词打分 + 长度权重。"""
        templates = self.cfg.get("templates", [])
        # 检测负面词
        negative_words = ["不", "没", "别", "无", "算了", "免了", "不考虑了"]
        has_negative = any(w in message for w in negative_words)

        scored = []
        for idx, tpl in enumerate(templates):
            score = 0
            best_kw_len = 0
            is_negative_tpl = tpl.get("negative", False)

            for kw in tpl.get("keywords", []):
                if kw in message:
                    score += len(kw)  # 关键词越长权重越高
                    best_kw_len = max(best_kw_len, len(kw))

            if score == 0:
                continue

            # 负面场景：负面模板加分，非负面模板扣分
            if has_negative:
                if is_negative_tpl:
                    score *= 3  # 负面消息优先匹配负面场景
                else:
                    score //= 2  # 降低正面场景匹配度

            # 配置中越靠前的模板有微小优先级加成
            score += max(0, 10 - idx) // 3

            scored.append((score, best_kw_len, tpl["reply"]))

        if scored:
            # 按总分配降序，同分按关键词长度降序
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return scored[0][2]

        return self.cfg.get("default_reply", "您好，看到您的消息了～")

    def _check_rate_limit(self) -> bool:
        now = time.time()
        if now - self._hour_start > 3600:
            self._hour_start = now
            self._send_count = 0
        limit = self.cfg.get("rate_limit_per_hour", 50)
        return self._send_count < limit

    async def _open_chat(self, page: Page, name: str) -> bool:
        """在消息列表中找到并点击指定候选人的会话。"""
        try:
            # 尝试点击包含候选人名字的元素
            target = page.locator(f'text={name}').first
            if await target.count() > 0:
                await target.click()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                return True

            # 备用：遍历列表项
            items = page.locator('[class*="chat-item"], [class*="chat-list-item"], li').first
            if await items.count() > 0:
                # 尝试匹配名字
                item_with_name = page.locator(f'[class*="chat"]:has-text("{name}")').first
                if await item_with_name.count() > 0:
                    await item_with_name.click()
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    return True

        except Exception as e:
            self.logger.error("打开聊天失败: %s", e)
        return False

    async def _send_message(self, page: Page, text: str) -> bool:
        """在聊天输入框输入并发送消息。"""
        try:
            min_d = self.cfg.get("min_delay", 1.0)
            max_d = self.cfg.get("max_delay", 3.0)

            # 定位输入框
            input_selectors = [
                'textarea',
                '[contenteditable="true"]',
                '[class*="input"]',
                '[placeholder*="输入"]',
                '[placeholder*="回复"]',
            ]
            input_box = None
            for sel in input_selectors:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    input_box = el
                    break

            if not input_box:
                self.logger.error("找不到消息输入框")
                return False

            await input_box.click()
            await asyncio.sleep(random.uniform(0.1, 0.3))

            # 清空并输入
            await input_box.fill("")
            await input_box.type(text, delay=random.randint(30, 80))
            await asyncio.sleep(random.uniform(min_d, max_d))

            # 找到并点击发送按钮
            send_selectors = [
                'button:has-text("发送")',
                '[class*="send"]',
                'button:last-of-type',
            ]
            for sel in send_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    return True

            # 如果没找到发送按钮，尝试 Enter 键
            await page.keyboard.press("Enter")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return True

        except Exception as e:
            self.logger.error("发送消息失败: %s", e)
            return False
