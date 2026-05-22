import asyncio
from typing import Optional

from src.logger import setup_logger


class AIClient:
    """AI 回复接口（预留），支持 OpenAI / Anthropic / 自定义端点。"""

    def __init__(self, config: dict):
        self.cfg = config.get("ai", {})
        self.logger = setup_logger()
        self._provider = self.cfg.get("provider", "openai")

    async def generate_reply(self, candidate_name: str, message: str,
                             context: str = "") -> Optional[str]:
        api_key = self.cfg.get("api_key", "")
        if not api_key:
            self.logger.warning("AI API key 未配置，无法使用 AI 模式")
            return None

        system_prompt = self.cfg.get("context", "") % context

        try:
            if self._provider == "openai":
                return await self._call_openai(system_prompt, message)
            elif self._provider == "claude":
                return await self._call_claude(system_prompt, message)
            else:
                return await self._call_custom(system_prompt, message)
        except Exception as e:
            self.logger.error(f"AI 调用失败: {e}")
            return None

    async def _call_openai(self, system_prompt: str, user_message: str) -> Optional[str]:
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type": "application/json",
        }
        base_url = self.cfg.get("base_url", "https://api.openai.com/v1")
        payload = {
            "model": self.cfg.get("model", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.cfg.get("max_tokens", 200),
            "temperature": self.cfg.get("temperature", 0.7),
        }

        timeout = aiohttp.ClientTimeout(total=self.cfg.get("timeout", 15))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                self.logger.error(f"OpenAI API 返回 {resp.status}")
                return None

    async def _call_claude(self, system_prompt: str, user_message: str) -> Optional[str]:
        import aiohttp

        headers = {
            "x-api-key": self.cfg["api_key"],
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.cfg.get("model", "claude-sonnet-4-6"),
            "max_tokens": self.cfg.get("max_tokens", 200),
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }

        timeout = aiohttp.ClientTimeout(total=self.cfg.get("timeout", 15))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["content"][0]["text"].strip()
                self.logger.error(f"Claude API 返回 {resp.status}")
                return None

    async def _call_custom(self, system_prompt: str, user_message: str) -> Optional[str]:
        import aiohttp

        base_url = self.cfg.get("base_url", "")
        if not base_url:
            self.logger.error("自定义 AI 端点未配置 base_url")
            return None

        headers = {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.cfg.get("model", ""),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": self.cfg.get("max_tokens", 200),
        }

        timeout = aiohttp.ClientTimeout(total=self.cfg.get("timeout", 15))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                self.logger.error(f"自定义 AI 端点返回 {resp.status}")
                return None
