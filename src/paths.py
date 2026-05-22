"""PyInstaller 打包路径兼容工具。

Dev 环境：资源在项目根目录，数据在 ./data/
打包后：资源在 sys._MEIPASS，数据在 .exe 同级目录
"""

import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否在 PyInstaller 打包环境中运行。"""
    return getattr(sys, "frozen", False)


def base_dir() -> Path:
    """可执行文件 / 项目根目录。"""
    if is_frozen():
        return Path(sys.executable).parent
    # 相对于 main.py 的项目根目录
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """获取资源文件路径（config.yaml 等只读资源）。

    打包后资源在 sys._MEIPASS 中。
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", ".")) / relative
    return base_dir() / relative


def data_path(relative: str) -> Path:
    """获取可写数据文件路径（日志、状态文件等）。

    打包后数据始终在 .exe 同级目录下。
    """
    p = base_dir() / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def resolve_dir(config_path: str) -> str:
    """将配置文件中的相对路径转为绝对路径。

    数据类目录（如 user_data_dir）需指向可写位置。
    """
    p = Path(config_path)
    if p.is_absolute():
        return str(p)
    # 判断是数据路径还是资源路径
    if "data" in p.parts or p.parts[0] in ("data",):
        return str(data_path(config_path))
    return str(resource_path(config_path))
