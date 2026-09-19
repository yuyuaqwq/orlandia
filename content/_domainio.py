# -*- coding: utf-8 -*-
"""包内域读口单点（`content/_domainio.py`）—— 键型还原 / 序声明 / JSON 域读取。

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

**P0-4b（2026-09-19 续批）** —— 读口的余族同样收在这里：

* `_read_json` ×11（`mounts` / `player_cmds` / `mech/cond_procs` / `persistence/professions` /
  `flow/boss_script` / `flow/instance_gate` / `apply` / `loot` / `exploration` / `misc_cmds` /
  `mech/params`）—— **逐字同体**，只差「包内 `content/data/<name>` 拼接」还是「调用方给绝对路径」，
  ⇒ 拆成 `read_data_json(name, default, sub)`（8 处）与 `read_json(path, default)`（3 处）。
* `_read_domain` ×9（`talk_actions` / `shop_stock` / `smith_stock` / `instance_cmds` /
  `wild_king` / `world_cmds` / `achievements`）—— 全部同体（`_HERE/<sub>/<domain>.json`，坏则 `{}`）
  ⇒ `read_domain(domain, sub, default)`。
* `_read_domain` ×2 **fail-closed 变体**（`social_guild.py` 的 `guild.json` / `flow/weekly_progress.py`
  的 `weekly_quests.json`：硬编码单域 + 空表抛 `RuntimeError`）⇒ `read_data_json_strict()`。
* **未收的两处**：`content/dialogue.py` / `content/dialogue_conds.py` 的 `_read_domain` ——
  `tests/test_u1i4_dialogue_frozen.py` 把这两段源码逐段冻结（E 栏断言 `frozen == live`，
  缺符号直接 `KeyError`）且门禁自哈希 pinned ⇒ 该线收口后才能随冻结基准重采一并并入。

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

import json
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


# ───────────────────────────────────────────────────────── 域读口（P0-4b：读 JSON / 读域文件）
_DATA_DIR = os.path.join(_HERE, "data")


def read_json(path: str, default):
    """读一个 JSON 文件（缺文件 / 坏 JSON / 权限 → `default`，不抛）。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                        # noqa: BLE001
        return default


def read_data_json(name: str, default=None, sub: str = "data"):
    """读包内 `content/<sub>/<name>`（`name` 带扩展名）—— 缺文件 / 坏 JSON → `default`，不抛。"""
    return read_json(os.path.join(_HERE, sub, name), default)


def read_domain(domain: str, sub: str = "data", default=None):
    """读包内 `content/<sub>/<domain>.json`（缺文件 / 坏 JSON → `default`，不抛）。

    缺省 `default=None` ⇒ 交回 `{}`（包内各原地读口的历史口径，逐字保留）。
    """
    return read_json(os.path.join(_HERE, sub, "%s.json" % domain),
                     {} if default is None else default)


def read_data_json_strict(name: str, label: str, hint: str) -> dict:
    """读包内 `content/data/<name>`，**fail-closed**：文件缺 → `OSError`；空表 / 顶层不是映射 → `RuntimeError`。

    给「空表 = 静默无内容」的单域读点用（`guild` / `weekly_quests`）：
    读不到就点名抛，绝不给空表。
    """
    path = os.path.join(_DATA_DIR, name)
    with open(path, encoding="utf-8") as f:
        tbl = json.load(f)
    if not isinstance(tbl, dict) or not tbl:
        raise RuntimeError("%s 域文件不可用（%s）—— 空表 = %s" % (label, path, hint))
    return tbl
