"""示例 Python 插件：放到本目录即被发现（无需重启进程，下次刷新生效）。"""

from __future__ import annotations

import shutil

from langchain_core.tools import tool


@tool
def get_disk_free() -> str:
    """返回项目所在磁盘的剩余空间。"""
    try:
        usage = shutil.disk_usage(".")
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        return f"磁盘剩余 {free_gb:.1f} GB / 共 {total_gb:.1f} GB"
    except Exception as exc:  # pragma: no cover
        return f"读取磁盘信息失败：{exc}"


TOOLS = [get_disk_free]
