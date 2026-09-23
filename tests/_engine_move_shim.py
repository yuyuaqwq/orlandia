# -*- coding: utf-8 -*-
"""测试侧垫片：让「引擎搬迁前的历史快照」在搬迁后仍能 exec。

为什么存在
----------
2026-09-23 的包栈重构把一批游戏原语从 `saintess_engine/` 搬进了 `extends/ext_*/`
（`battle` · `gauge` · `formation` · `panel` · `quest` · `space` · `run` · `loot` ·
`dialogue` · `presence` …）。有几份**冻结门禁**保存了搬迁前实现的**文本快照**，
用 `exec` 跑它们再和活实现逐格比对 —— 那是它们的核心证明力。

问题：那些历史文本里写着 `from saintess_engine.battle import …`，而该模块现在
不存在了 ⇒ `ModuleNotFoundError`。**门禁没错，缺的只是执行环境。**

本垫片把旧名字指到新家（`sys.modules` 别名），只为了让历史文本跑得起来。

边界（重要）
------------
* **只给测试用**。`editor/` 与 `saintess_engine/` 都不许 import 本模块
  （引擎侧留兼容名 = 把刚搬出去的东西又拉回来，正是重构要消灭的东西）。
* 不写任何产品代码路径。产品侧只有 `ext_*` 一个真源。
* 用 `setdefault`：真模块在场时绝不覆盖。
"""
from __future__ import annotations

import importlib
import sys

#: 搬走的模块 → 新家（扩展包）。只放**确实搬走**的，别自作主张加。
MOVED = {
    "battle": "ext_combat",
    "gauge": "ext_combat",
    "formation": "ext_combat",
    "panel": "ext_combat",
    "quest": "ext_quest",
    "space": "ext_world",
    "run": "ext_world",
    "loot": "ext_loot",
    "dialogue": "ext_dialogue",
    "presence": "ext_social",
    "membership": "ext_social",
    "collect": "ext_life",
    "periodic": "ext_life",
    "timers": "ext_life",
    "unlock": "ext_life",
    "trade": "ext_economy",
    "shelf": "ext_economy",
    "produce": "ext_economy",
}


def install(*, extra: dict | None = None) -> dict:
    """把 `saintess_engine.<旧名>` 指到新家；返回「旧名 → 新模块」的映射。

    取不到的新家直接跳过（不是每个扩展包都在当前包栈里）—— 垫片要能容忍缺席，
    否则测试会因为「没装某个包」而炸，那是另一件事。
    """
    done = {}
    pairs = dict(MOVED)
    pairs.update(extra or {})
    for old, pkg in pairs.items():
        alias = "saintess_engine.%s" % old
        if alias in sys.modules:
            done[old] = sys.modules[alias]
            continue
        for cand in ("%s.%s" % (pkg, old), pkg):
            try:
                mod = importlib.import_module(cand)
            except ImportError:
                continue
            sys.modules[alias] = mod
            done[old] = mod
            break
    return done


#: import 本模块即生效（门禁顶部一句 `import _engine_move_shim  # noqa: F401` 就够）。
DONE = install()
