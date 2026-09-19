# -*- coding: utf-8 -*-
"""包内阵营声望（`content/factions.py`）—— 游戏仓 `game/core/factions.py`（14 行）**逐字端口**（B13-L7）。

正文一字未改，只换一处「宿主取件」（W12 收口 2026-09-14 已切包内门面直取）：
    `from ..data import REPUTATION_TIERS`  →  `from .catalog_b143 import REPUTATION_TIERS`
    （域 = `content/data/factions.json` 的 `factions` 组；真源 `game/data/factions.py:20` 装配后
     由 `game/data/__init__.py:56` 挂到 `game.data` 上；**tuple 行形状已还原**
     `_tupled_rows` ⇒ `for th, n in …` 解包与真源同形）。
    对拍：`overnight/b14_catalog_gate.py --names REPUTATION_TIERS` → OK（逐值 + 键序）。
"""
from __future__ import annotations

from saintess_engine.wire import slot as _slot
_WIRE, bind_host = _slot()


# ---- 包内门面读口（W12 收口：真源顶层 `from ..data import REPUTATION_TIERS`）----
from .catalog_b143 import REPUTATION_TIERS   # noqa: E402  （域 data/factions.json · factions 组）


def faction_reputation_tier(points: int) -> str:
    """声望点数 → 等级名"""
    name = "陌生"
    for th, n in REPUTATION_TIERS:
        if points >= th:
            name = n
    return name


__all__ = ["faction_reputation_tier", "bind_host"]
