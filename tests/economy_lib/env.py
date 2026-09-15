# -*- coding: utf-8 -*-
"""economy_lib 环境引导（随包内测试迁入：`pkg/tests/economy_lib/`）。

口径（与宿主编同义，只换路径装配）：
  把「包根 + tests/」加进 sys.path；引擎根 / 宿主壳根交 `tests/_paths.py` 单点发现
  （`GWEN_FRAMEWORK_DIR` 优先；缺失即**醒目报错**，不静默跳过）；
  GWEN_GAME_DB 默认测试库；stdout UTF-8。import economy_lib 即完成（幂等）。
"""
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))        # tests/economy_lib/
_TESTS_DIR = os.path.dirname(_SCRIPT_DIR)                       # tests/
_PKG_ROOT = os.path.dirname(_TESTS_DIR)                         # 包仓根

for _p in (_PKG_ROOT, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _paths  # noqa: E402,F401  ← 引擎根/宿主壳根发现（GWEN_FRAMEWORK_DIR 优先）

os.environ.setdefault("GWEN_GAME_DB", os.path.join(_TESTS_DIR, "test_game_data.db"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def setup_env():
    """显式调用入口（幂等）。"""
    return True
