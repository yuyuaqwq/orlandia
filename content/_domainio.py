# -*- coding: utf-8 -*-
"""包内域读口单点（`content/_domainio.py`）—— 键型还原 / 序声明。

为什么要它（`重复实现审计_报告.md` P0-4）
--------------------------------------
包内「读域小工具」按惯例**各自持一份**，其中这两族最整齐：

* `_int_keys` ×6（`tables.py` / `catalog_b143.py` / `catalog_items.py` /
  `catalog_life.py` / `catalog_rules.py` / `social_guild.py`）+ `config.py` 的同口径公共名
  `int_keys`（外部消费点 `crafting.py:29`）——**函数体逐字相同**，只有 docstring 措辞有别。
* `_order` ×4 逐字同体（`catalog_items.py` / `catalog_legacy.py` / `catalog_life.py` /
  `catalog_rules.py`）= 一行转发引擎装载口 `orders_of`。
* `_order` ×2域内变体（`catalog_quests.py` / `catalog_b143.py`）从**可重载全局** `_ORDERS`
  （placeholder 模式，重载后由 `_R.key_order.all()` 刷新）取条目 ——
  **取件源与装载口不是一回事** ⇒ 不并入 `order_of()`，只共用「形状校验」那一段
  （`require_key_order()`）。

落点理由（与 `content/_pkgref.py` / `content/_hostref.py` 同一条纪律：**安全依赖面决定落点**）
----------------------------------------------------------------------------------
`tables.py` 在装配最早期被 import，且它派生的表遍布全包 ⇒ 本模块只允许依赖
**标准库 + `saintess_engine.records`**（`tables.py:38` 已在同一位置 import 它，是这条链上的
既有依赖），**不得** import 任何 `content.*` 子模块。故不并入 `content/index.py`
（那里带 `pypinyin` 与索引构建），也不并入 `config.py`（域读口，语义不同）。

行为口径：**逐字不变** —— 键型还原的「非整数键原样保留」、序声明的 raise 分支与消息措辞
（含 `%r` 与尾部提示）均按原样搬移，不做放宽。
"""
from __future__ import annotations

import os

from saintess_engine.records import orders_of

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>


def int_keys(tbl) -> dict:
    """JSON 字符串键 → int 键（非整数键**原样保留**，不静默丢）。

    用途：`UPGRADE_TABLE` / `HOUSE_LEVELS` / `HOUSE_REFUND` / `ENHANCE_FAIL_DROP` /
    `FISH_QUALITY_WEIGHTS` 这类 `{int 档位: 值}` 的表 —— 不还原 = `.get(3)` 恒 `None`（静默归零）。
    """
    out: dict = {}
    for k, v in (tbl or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            out[k] = v
    return out


def order_of(name: str) -> list:
    """按名取包内序声明（引擎装载口 `orders_of`，落点由包内域声明派生）。"""
    return orders_of(_PKG_ROOT, name, domain="key_order")


def require_key_order(orders, name: str) -> list:
    """从**已加载**的 `key_order` 域条目表里取 `name` 的键序：缺条目 / 形状不对 → `raise`。

    给两处「从可重载全局 `_ORDERS` 取条目」的位点共用（`catalog_quests` / `catalog_b143`）。
    """
    ent = orders.get(name)
    keys = ent.get("keys") if isinstance(ent, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ValueError(
            "key_order：读不到 %r 的键序声明（域缺该条目，或形状不是 {keys: [...]}）"
            "—— 序读不到就不许静默改成空表" % (name,))
    return keys
