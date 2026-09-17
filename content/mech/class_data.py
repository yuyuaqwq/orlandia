# -*- coding: utf-8 -*-
"""《奥兰迪亚》职业机制兑现族（class_mech）所需参数表 —— **数据已进表，本文件只留读口**。

★ D3（D 批「数据进表」，2026-09-17）：本文件原先内联的 `MECH_CFG`（15 组 / 179 行）与
`MECH_CASH`（9 条 / 67 行）字面量**已原样搬进包内域 JSON**，本文件不再自带任何字面量，
只做「读口 + 类型/序还原 + fail-closed」：

| 表 | 包内域（kind=rules） | 条数 | 读口 |
|---|---|---|---|
| `MECH_CFG` | `content/rules/mech_cfg_core.json`（8 个**通用机制**组）+ `content/rules/mech_cfg_class.json`（7 个**职业族机制**组） | 15 组 | `_mech_cfg()`（两域按 core→class 拼接） |
| `MECH_CASH` | `content/rules/mech_cash.json` | 9 条 | `_domain("mech_cash", …)` |

域登记（域元数据唯一源）= `editor/domains.json`（D3 新增 `mech_cfg_core` / `mech_cfg_class` /
`mech_cash` 三域，声明原文另落 `out/domain_decl.json`，按 D-BATCH §3 交主线合并）；
`game.json` 的 `domains` 清单同步（门禁 `test_export_package_sync.py` 要求清单 == 包声明域）。

三处「JSON 往返不可逆」的还原（不做 = 静默错值；清单由 `out/raw/00_before.json` 的 tuple 清单钉住）：
① **元组键**：`element.reactions` / `element.reaction_table`（`("ice","fire_mark")` → `"ice|fire_mark"`）
   与 `branch_resources`（`("cls_fa_shi", 0)` → `"cls_fa_shi|0"`，第 2 段按 **int** 还原）；
② **元组值**：`mech_stack.whitelist` · `buff.mult[*]` · `crit.full_hp_mechs` · `crit.combo_mechs` ·
   `ctrl.mechs` · `ctrl.skill_cc_whitelist` · `ctrl.proc_groups[*]` · `branch_resources[*]`
   （改前实测 = 45 处（core）+ 4 处（class）= 49 处，见 `out/raw/gen_domains.py` 的 tuple 清单）；
③ **外层键序**：域文件外层键**升序**（落盘规范，`test_export_package_sync.py`【6】）→ 真源插入序
   另立 `content/data/key_order.json` 的 `key_order` 域声明（`mech_cfg_core` / `mech_cfg_class` /
   `mech_cash` 三条），读口按名取回源插入序。**这是包内既有惯例**（`catalog_items.py` /
   `catalog_rules.py` / `catalog_quests.py` 同款：`orders_of(pkg, 名, domain="key_order")`）。

fail-closed（D-BATCH §2.4：域文件缺 / 声明与磁盘不符 / 键型不符 → 报错点名，不许静默空表）：
· 域未声明 / 落点与声明不符 / 文件缺 → 引擎 `records_from_domain` 装载期抛
  `RecordsDeclarationError`（点名域 + 声明路径 + 实际路径）；
· 域键集与序声明不一致（多一条/少一条）→ `RecordsOrderMismatch`（拒绝静默改序/漏项）；
· 序声明缺条目 / 形状不是 `{keys: [...]}` → `orders_of` 点名抛；
· 域读成空表 → 本文件 `_domain()` 再抛一次。
**四道都不静默给空表。**

真源对照（游戏仓 `C:/Users/yuyu/qqbot/data/plugins/dragonfall`；搬迁逐字 dump，值/类型/序未改一字节）
------------------------------------------------------------------------------------------------
| 本文件 | 真源 | 条数（dump 实测） |
|---|---|---|
| `MECH_CASH` | `game/data/battle_rules.py:624` | 9 个兑现条目（顶层键）；嵌套子键合计 65 |
| `MECH_CFG` | `game/data/battle_config.py:455` | 15 个子表（dot/mech_stack/buff/element/crit/ctrl/boss/enemy_bar/assassin_combo/shadow_step/echo/full_tension/blood_debt_gain/branch_resources/chi_hold_dmg） |
| `BAR_INJECT_FIELDS` | `game/data/battle_rules.py:742` | 1 条（shaken_gain → shaken, per_hit）—— **单源在 params.py**，本文件只再导出 |
| `BAR_STATE_PREFIX` | `game/data/battle_rules.py:749` | 标量 `"bar:"` —— **单源在 params.py**，本文件只再导出 |

注：任务书写「`MECH_CASH`(163 键)」——从真源 dump 实测为 **9 个顶层兑现条目 / 65 个嵌套子键**，
163 与真源不符（诚实记录，未按 163 编造任何内容；本次搬迁亦未补任何键）。

本族 39 个动作**没有**任何一个直接 import 这三张表：动作的参数由装配层（`apply.py` 的
mech_cash 段）从 `MECH_CASH` 读出后填进效果 dict/动作 params。故本文件是「域表 → 装配层 →
动作」的数据源，`class_mech.py` 顶部 import 它作为包内单源（见该文件头注 struct-rewrite #3）。
"""
from __future__ import annotations

import copy
import os

from saintess_engine.records import orders_of, records_from_domain

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content/mech
_PKG_ROOT = os.path.dirname(os.path.dirname(_HERE))         # <pkg>

# ============================================================
# 序声明 —— 唯一源 = `content/data/key_order.json` 的 `key_order` 域
# （域文件外层键升序 = 落盘规范；真源插入序在这里声明；缺条目/形状不对 → 点名抛）
# ============================================================
_ORDER_CORE = orders_of(_PKG_ROOT, "mech_cfg_core", domain="key_order")
_ORDER_CLASS = orders_of(_PKG_ROOT, "mech_cfg_class", domain="key_order")
_ORDER_MECH_CFG = _ORDER_CORE + _ORDER_CLASS
_ORDER_MECH_CASH = orders_of(_PKG_ROOT, "mech_cash", domain="key_order")


def _domain(domain: str, order) -> dict:
    """读一个域 → **保序 + 独立副本** 的表；任一不符即抛（**绝不静默空表**）。

    `records_from_domain` 已在装载期挡住「域未声明 / 落点与声明不符 / 文件缺」；
    `order=` 再把「域键集 == 序声明」守一遍（`RecordsOrderMismatch`）。
    返回的是 `copy.deepcopy` 出来的副本 —— 下面的类型还原不得就地改引擎域表。
    """
    rec = records_from_domain(_PKG_ROOT, domain, order=list(order))
    tbl = rec.all()
    if rec.missing or not tbl:
        raise RuntimeError("域 %r 读成空表（%s）—— 空表 = 静默失效，拒绝继续"
                           % (domain, rec.problems[:3]))
    return {k: copy.deepcopy(tbl[k]) for k in order}


def _tuple_keys(raw: dict, int_positions=()) -> dict:
    """元组键还原：`"a|b"` → `("a", "b")`；`int_positions` 指定的段还原成 **int**。"""
    out = {}
    for k, v in raw.items():
        parts = str(k).split("|")
        out[tuple(int(p) if i in int_positions else p for i, p in enumerate(parts))] = v
    return out


def _mech_cfg_core() -> dict:
    """`MECH_CFG` 前 8 组（通用战斗机制）← 域 `mech_cfg_core`；元组逐路径还原。"""
    out = _domain("mech_cfg_core", _ORDER_CORE)
    out["mech_stack"]["whitelist"] = tuple(out["mech_stack"]["whitelist"])
    out["buff"]["mult"] = {k: tuple(v) for k, v in out["buff"]["mult"].items()}
    out["element"]["reactions"] = _tuple_keys(out["element"]["reactions"])
    out["element"]["reaction_table"] = _tuple_keys(out["element"]["reaction_table"])
    out["crit"]["full_hp_mechs"] = tuple(out["crit"]["full_hp_mechs"])
    out["crit"]["combo_mechs"] = tuple(out["crit"]["combo_mechs"])
    out["ctrl"]["mechs"] = tuple(out["ctrl"]["mechs"])
    out["ctrl"]["skill_cc_whitelist"] = tuple(out["ctrl"]["skill_cc_whitelist"])
    out["ctrl"]["proc_groups"] = {k: tuple(v) for k, v in out["ctrl"]["proc_groups"].items()}
    return out


def _mech_cfg_class() -> dict:
    """`MECH_CFG` 后 7 组（职业族机制）← 域 `mech_cfg_class`；元组键（含 int 段）+ 元组值还原。"""
    out = _domain("mech_cfg_class", _ORDER_CLASS)
    out["branch_resources"] = {k: tuple(v) for k, v in
                               _tuple_keys(out["branch_resources"], int_positions=(1,)).items()}
    return out


def _mech_cfg() -> dict:
    """两域拼成全量 15 组；拼接后再守一遍键序（不静默改序）。"""
    out = {**_mech_cfg_core(), **_mech_cfg_class()}
    if tuple(out) != tuple(_ORDER_MECH_CFG):
        raise RuntimeError("MECH_CFG 拼接后的键序与 key_order 声明不符：%s ≠ %s"
                           % (list(out), list(_ORDER_MECH_CFG)))
    return out


# ============================================================
# MECH_CFG —— 机制配置表（全量 15 组，逐键等于真源 `battle_config.py:455`）
# ============================================================
MECH_CFG: dict = _mech_cfg()

# ============================================================
# MECH_CASH —— 兑现声明表（9 条，逐条等于真源 `battle_rules.py:624`；全 JSON 原生类型）
# ============================================================
MECH_CASH: dict = _domain("mech_cash", _ORDER_MECH_CASH)

# ============================================================
# BAR_* —— **单源在 params.py**，本文件只做再导出（消费者 import 路径不变）
# ============================================================
from .params import BAR_INJECT_FIELDS, BAR_STATE_PREFIX   # noqa: F401  再导出（单源）

__all__ = ["MECH_CASH", "MECH_CFG", "BAR_INJECT_FIELDS", "BAR_STATE_PREFIX"]
