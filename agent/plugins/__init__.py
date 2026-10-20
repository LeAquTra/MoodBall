"""Python 插件自动发现：目录中的 *.py，只要暴露 TOOLS 列表即可。

示例：
    from langchain_core.tools import tool

    @tool
    def get_disk_free() -> str:
        \"\"\"返回磁盘剩余空间。\"\"\"
        ...

    TOOLS = [get_disk_free]
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from langchain_core.tools import BaseTool

logger = logging.getLogger("moodball.plugins")

PLUGIN_DIR = Path(__file__).resolve().parent
_SKIP = {"__init__", "builtin_tools"}


def discover_plugin_tools() -> list[BaseTool]:
    tools: list[BaseTool] = []
    for path in sorted(PLUGIN_DIR.glob("*.py")):
        if path.stem.startswith("_") or path.stem in _SKIP:
            continue
        module_name = f"moodball_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            # 允许直接编辑插件文件后「刷新工具」即可生效，而不是命中旧模块缓存。
            sys.modules.pop(module_name, None)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            candidates = getattr(module, "TOOLS", [])
            for tool in candidates:
                if isinstance(tool, BaseTool) and tool.name:
                    tools.append(tool)
            logger.debug("plugin %s loaded: %s", path.name, len(candidates))
        except Exception:
            logger.exception("plugin load failed: %s", path)
    return tools
