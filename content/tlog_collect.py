# -*- coding: utf-8 -*-
"""**薄适配层**（数据包侧）—— 采集半边的**唯一实现已搬进扩展包 `ext_reward`**。

    真源 = `extends/ext_reward/tlog_collect.py`（扩展包 `ext_reward`；2026-09-24 B4a 搬入）
    本文件 = 只转出名字，**零逻辑**（不许在这里加第二份实现）。

为什么这个壳必须留着
--------------------
引擎与宿主取这半边是按**半边名**、且只认**数据包**那一层：

  · 宿主 `host/tlog_setup.py::attach_tlog` → `pkg.optional_submodule("tlog_collect")`
  · 引擎 `saintess_engine/host/runtime.py::_attach_tlog` → `stack.optional_submodule("tlog_collect")`

而 `Package.optional_submodule(name)` 解析 `<entry 同级>/<name>` ⇒ 数据包里必须有
`content/tlog_collect.py` 这个名字（`PackageStack.optional_submodule` 目前只转发数据包）。
要彻底删掉本壳，得先让「可选半边」**逐层取件**（扩展包也能提供半边）—— 已登记为下一步。
"""
from __future__ import annotations

from ext_reward.tlog_collect import (          # noqa: F401
    EVENT_KINDS,
    REPRO_KEYS,
    BattleTLog,
    _player_input,
    _rounds_of,
    _uid,
)

__all__ = [
    "BattleTLog", "EVENT_KINDS", "REPRO_KEYS",
    "_uid", "_rounds_of", "_player_input",
]
