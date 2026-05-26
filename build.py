#!/usr/bin/env python3
"""PyInstaller 打包脚本。

用法：
    python build.py          # 打包当前平台
    python build.py windows  # 交叉打包 Windows（需要 Wine）
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# 修复 Windows CI 中文编码问题
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def clean():
    for d in (DIST, BUILD):
        if d.exists():
            shutil.rmtree(d)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()


def ensure_pyinstaller():
    try:
        import PyInstaller
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build(target: str = None):
    clean()
    ensure_pyinstaller()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "BossAutoReply",
        "--add-data", f"config.yaml{os.pathsep}.",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "yaml",
        "--hidden-import", "aiohttp",
        "--hidden-import", "playwright.async_api",
        "--clean",
        "--noconfirm",
    ]

    if sys.platform == "win32" or target == "windows":
        # Windows 控制台程序（方便看日志）
        pass
    else:
        # macOS: 不弹 Dock 图标，纯后台控制台
        cmd += ["--noconsole"]

    # 入口文件
    cmd.append(str(ROOT / "main.py"))

    print(f"[BUILD] {' '.join(cmd)}")
    subprocess.check_call(cmd)

    # PyInstaller --onefile 产物在 dist/
    exe_name = "BossAutoReply.exe" if sys.platform == "win32" else "BossAutoReply"
    exe_path = DIST / exe_name
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n[DONE] 打包完成: {exe_path} ({size_mb:.1f} MB)")
        print(f"[NOTE] 首次运行会自动下载 Firefox 浏览器内核（约 120MB），请耐心等待。")
    else:
        print("[ERROR] 打包失败，产物未找到")
        sys.exit(1)

    # 生成 Windows 启动脚本
    _create_run_bat()
    # 复制配置文件到 dist/
    _copy_config()


def _create_run_bat():
    bat_path = DIST / "run.bat"
    content = (
        "@echo off\r\n"
        'title BOSS直聘自动复聊\r\n'
        'cd /d "%~dp0"\r\n'
        'set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/\r\n'
        '"%~dp0BossAutoReply.exe"\r\n'
        "pause\r\n"
    )
    bat_path.write_text(content, encoding="gbk")
    print(f"[DONE] run.bat 已生成: {bat_path}")


def _copy_config():
    cfg_src = ROOT / "config.yaml"
    cfg_dst = DIST / "config.yaml"
    shutil.copy2(cfg_src, cfg_dst)
    print(f"[DONE] config.yaml 已复制: {cfg_dst}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    build(target)
