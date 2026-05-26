#!/usr/bin/env python3
"""BOSS 直聘自动复聊脚本 —— 入口文件。"""

import asyncio
import signal
import sys

import yaml

from src.paths import resource_path, resolve_dir, base_dir
from src.browser import BrowserManager
from src.login import LoginHandler
from src.monitor import MessageMonitor
from src.reply_engine import ReplyEngine
from src.logger import setup_logger


def load_config() -> dict:
    # 优先读取 exe 同目录的 config.yaml（用户可编辑），否则用内置默认配置
    external_cfg = base_dir() / "config.yaml"
    cfg_path = external_cfg if external_cfg.exists() else resource_path("config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["browser"]["user_data_dir"] = resolve_dir(config["browser"]["user_data_dir"])
    config["logging"]["file"] = resolve_dir(config["logging"]["file"])
    return config


async def on_new_message(msg: dict, reply_engine: ReplyEngine, page):
    await reply_engine.reply(msg, page)


async def main():
    config = load_config()
    logger = setup_logger(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("file", "./data/bot.log"),
    )

    logger.info("=" * 40)
    logger.info("BOSS 直聘自动复聊脚本 启动")
    logger.info("资源目录: %s", resource_path("."))
    logger.info("数据目录: %s", resolve_dir("data"))
    logger.info("=" * 40)

    browser = BrowserManager(config)
    login_handler = LoginHandler(config)
    monitor = MessageMonitor(config)
    reply_engine = ReplyEngine(config)

    shutdown_event = asyncio.Event()

    def handle_shutdown():
        logger.info("收到退出信号，正在关闭…")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda s, f: handle_shutdown())
        except Exception:
            pass

    page = None
    try:
        page = await browser.start()
        logged_in = await login_handler.ensure_logged_in(page)
        if not logged_in:
            logger.error("登录失败，退出")
            return

        await monitor.navigate_to_chat(page)

        poll_task = asyncio.create_task(
            monitor.poll(page, on_new_message, reply_engine)
        )

        await shutdown_event.wait()
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error("运行异常: %s", e, exc_info=True)
    finally:
        if page:
            await browser.close()
        logger.info("脚本已退出")


if __name__ == "__main__":
    asyncio.run(main())
