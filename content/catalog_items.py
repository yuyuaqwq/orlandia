# -*- coding: utf-8 -*-
"""包内物品装备族门面（`content/catalog_items.py`）—— 宿主聚合层 `C` 的「B-物品装备族」等价物。

为什么需要它
------------
宿主 `game/content.py`（19 行）= `from .data import *` + `from .core import *`，包内模块过去靠
宿主句柄读它的名字。宿主 `game/data`（74,707 行 / 87 文件）要删 ⇒ 这些名字必须先在包内由**域 JSON**
重建。本模块 = B 单元（物品装备族 40 个数据名里可从域重建的 23 个）的那一层。

读口纪律（B14_BRIEF §3 / 计划 §9 I1·I2）
----------------------------------------
* 只读包内域数据：`content/data/<域>.json` · `content/rules/<域>.json`（缺文件/坏 JSON → 空，不抛，
  与 `content/tables.py:48 _read_json` 同款）。
* **不 import 宿主任何模块**、**不用 `_HostMod`/`_host_attr`** —— 宿主表删掉之后本模块仍能活。

域来源（真源 = 游戏仓；单向导出器 = 游戏仓 `scripts/export_game_package.py`）
--------------------------------------------------------------------------
    content/data/items.json             ← derive_items        ITEMS 全量 900（材料 598 是它的前缀段）
    content/data/equip_roster.json      ← derive_equip_roster 687 装备（导出期注入 series_set/fixed_affixes）
    content/data/runes.json             ← derive_runes        16 符文（导出期注入 craft/conflicts）
    content/data/affixes.json           ← derive_affixes      76 词条
    content/data/sets.json              ← derive_sets         92 套装
    content/data/props.json             ← derive_props         59 道具（导出期注入 mounts）
    content/data/legendary_effects.json ← derive_legendary_effects 93 传说特效
    content/data/enhance_table.json     ← derive_enhance_table 10 行强化阶梯（键 = int 还原）
    content/rules/game_config.json      ← derive_game_config  enhance / upgrade / refine 三组常量

三处「类型还原」（JSON 只有 str 键 / 只有 array，不做还原 = 静默错值）
--------------------------------------------------------------------
  ① **int 键**：`ENHANCE_TABLE` / `UPGRADE_TABLE` / `ENHANCE_FAIL_DROP` / `RUNES[*]["lvl"]`
     —— 源里是 int 键，不还原 = `.get(3)` 恒 None = 强化/升级/符文数值静默归零（与
     `content/tables.py:ENHANCE_TABLE` 同族坑，B13-L1 头注也点过符文这一条）。
  ② **导出期注入字段要剥**：`equip_roster.json` 的 `series_set` / `fixed_affixes`、
     `runes.json` 的 `craft` / `conflicts`、`props.json` 的 `mounts` —— 它们是真源**别的表**
     （`SERIES_SETS` / `SERIES_FIXED_AFFIX` / `RUNE_CRAFT` / `RUNE_CONFLICTS` / `MOUNT_POOL` 挂点）
     折进条目的产物，留在表里会让 `EQUIP_ROSTER` / `RUNES` / `PROPS` 三条**逐条不等**。
     本模块剥掉后，其中三张（`RUNE_CRAFT` / `RUNE_CONFLICTS` / 道具挂点）由剥出来的值重建。
  ③ **衍生索引**：`MATERIALS_BY_NAME`（名字 → 材料条目，`MATERIALS` 值序）、
     `EQUIP_ROSTER_BY_NAME`（名字 → [装备 id]，`EQUIP_ROSTER` 值序、重名收全 —— 实测 686 键/687 id）。

⚠ 键序（迭代序）：域落盘走导出契约 `sort_table`（字典序），真源是**手写插入序** ⇒ 序不可逆
--------------------------------------------------------------------------------------
本模块按 `content/quests_flow.py:SIDE_QUEST_ORDER` / `content/event_menu.py:MAP_ORDER` /
`content/tables.py:JOB_ORDER` 同一手法**显式声明真源插入序**（`_ORDER_*`，见「① 顺序声明」段），
带集合守卫：域里多一条/少一条就 `raise`（防「加了内容忘了改这里」= 静默改序）。
顺序字面量由 `overnight/_b14b_gen_orders.py` 从真源生成（本文件不手抄）。
更彻底的做法是**在域里补 `seq`/`order` 字段**（I3 反向可逆性）—— 已登记给主 agent 裁。

⚠ 无域可依的名字（17 个）：本模块**不提供**（不许编数据），逐名缺口见 `overnight/W-B14-B.md`：
    EQUIP_SLOTS · QUALITY_ORDER · WEAPON_FLAVOR        —— 宿主 `game/data/equipment.py`（无域）
    GEM_TIERS · GEM_TIER_NAMES · GEM_SOCKETS · GEM_DRILL · GEM_LEGENDARY_EFFECTS · RUNE_REMOVE_COST
                                                        —— 宿主 `game/data/gems.py`（无域）
    ENCHANT_SLOTS · ENCHANT_RECIPES · ENCHANT_CRIT_CHANCE —— 宿主 `game/data/enchant.py`（无域）
    RUNE_DROP · RUNE_LEVEL_ROMAN · RUNE_CRAFT_SHARDS    —— 宿主 `game/data/runes.py`（常量段，无域）
    AFFIX_POOL_BY_QUALITY · AFFIX_AFFINITY_CN           —— 宿主 `game/data/affixes.py`（配套索引，无域）
"""
from __future__ import annotations

import os

from saintess_engine.records import apply_replacements, placeholder, records_from_domain, register_view, set_from_domains, update_in_place

from ._domainio import int_keys as _int_keys, order_of as _order   # P0-4 域读口单源

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# `_R`（域读表口 = 引擎 records 形状）在下面的 `_ORDER_*` 序声明**之后**才建（`order=` 要用它们）。
_R = None
#: `runes` 域的**未剥**视图（`RUNE_CRAFT` / `_rune_conflicts` 要读 `craft` / `conflicts`）
_RUNES_RAW: dict = {}


# ---- 序声明读口：**唯一源** = `content/data/key_order.json`（`key_order` 域）----
# S2 ①：本文件原先内嵌的 10 张序字面量（`__B14B_ORDERS_BEGIN__` 段）已搬进该域，
# 「值 + 类型 + 序」与搬前逐元素对拍相等；读不到即 raise（**不静默空序**）。


# __B14B_ORDERS_BEGIN__
_ORDER_MATERIALS = _order("items_materials")
_ORDER_ITEMS_REST = _order("items_rest")
_ORDER_EQUIP_ROSTER = _order("equip_roster")
_ORDER_AFFIXES = _order("affixes")
_ORDER_SETS = _order("sets")
_ORDER_PROPS = _order("props")
_ORDER_LEGENDARY_EFFECTS = _order("legendary_effects")
_ORDER_RUNES = _order("runes")
_ORDER_RUNE_CRAFT = _order("rune_craft")
_ORDER_RUNE_EFFECT_NAMES = _order("rune_effect_names")
# __B14B_ORDERS_END__


# ============================================================
# ③ 域读表口（引擎 records 形状）+ 两个键型小工具
# ------------------------------------------------------------
# **域元数据唯一源 = 包内 `editor/domains.json`**（S2 ②：这里只声明「我要哪些域」+
# 自己的派生参数 `order` / `drop` / `key_type`，落点由声明的 `kind` 派生；
# 声明缺项 / 文件缺 / 声明与磁盘不符 → 装载期报错，不静默给空表）。
# 下面只留形状覆盖不到的两件**键型**变换：
#   `_int_keys`   —— 嵌套子表（符文条目 `lvl`、`game_config` 的 `ENHANCE_FAIL_DROP`/`UPGRADE_TABLE`）
#   `_num_sorted` —— int 键按数值升序（域文件是字典序）
# ============================================================
_EQUIP_ROSTER_INJECTED = ("series_set", "fixed_affixes")
_RUNES_INJECTED = ("craft", "conflicts")

_R = set_from_domains(_PKG_ROOT, (
    "items", "equip_roster", "runes", "affixes", "sets", "props",
    "legendary_effects", "enhance_table", "game_config",
), overrides={
    # items 的序分两段声明（材料段 + 非材料段）；形状要求一条 `order` 覆盖全域 ⇒ 拼起来
    "items":             {"order": _ORDER_MATERIALS + _ORDER_ITEMS_REST},
    "equip_roster":      {"order": _ORDER_EQUIP_ROSTER, "drop": _EQUIP_ROSTER_INJECTED},
    "runes":             {"order": _ORDER_RUNES, "drop": _RUNES_INJECTED},
    "affixes":           {"order": _ORDER_AFFIXES},
    "sets":              {"order": _ORDER_SETS},
    "props":             {"order": _ORDER_PROPS, "drop": ("mounts",)},
    "legendary_effects": {"order": _ORDER_LEGENDARY_EFFECTS},
    "enhance_table":     {"key_type": int},          # int 键还原（JSON 只有字符串键）
})

# 未剥视图：`RUNE_CRAFT` / `_rune_conflicts` 要读条目里的 `craft` / `conflicts`
def _runes_build() -> dict:
    out: dict = {}
    for rid, ent in _R.runes.all().items():
        e = dict(ent)                                       # 副本（形状的表只读，不得就地改）
        if e.get("lvl") is not None:                        # int 键还原（不做 = 符文数值恒 0）
            e["lvl"] = _int_keys(e["lvl"])
        out[rid] = e
    return out


def _rune_conflicts() -> list:
    """真源 `RUNE_CONFLICTS`（3 对，**无向对**）← 域里每条符文的 `conflicts` 字段。

    规则：按真源符文插入序遍历，每遇到一条「未被收过的无向对」收一次，方向取遍历时那条符文
    的 effect（实测与真源逐位相同：`[[burn,freeze],[barrier,thorns],[scavenger,exp_bless]]`）。
    域侧是对称标注（互相都写），所以「首见即收」正好等价于真源的声明序。
    """
    out: list = []
    seen: set = set()
    for rid in _ORDER_RUNES:
        ent = _RUNES_RAW.get(rid) or {}
        eff = (RUNES.get(rid) or {}).get("effect")
        for other in (ent.get("conflicts") or []):
            pair = frozenset((eff, other))
            if pair in seen:
                continue
            seen.add(pair)
            out.append([eff, other])
    return out


_RUNES_RAW = placeholder("_RUNES_RAW")
_GAME_CONFIG = placeholder("_GAME_CONFIG")
_CFG_ENHANCE = placeholder("_CFG_ENHANCE")
_CFG_UPGRADE = placeholder("_CFG_UPGRADE")
_CFG_REFINE = placeholder("_CFG_REFINE")
MATERIALS = placeholder("MATERIALS")
ITEMS = placeholder("ITEMS")
MATERIALS_BY_NAME = placeholder("MATERIALS_BY_NAME")
EQUIP_ROSTER = placeholder("EQUIP_ROSTER")
EQUIP_ROSTER_BY_NAME = placeholder("EQUIP_ROSTER_BY_NAME")
RUNES = placeholder("RUNES")
RUNE_CRAFT = placeholder("RUNE_CRAFT")
_EFFECT_NAMES_BY_KEY = placeholder("_EFFECT_NAMES_BY_KEY")
RUNE_EFFECT_NAMES = placeholder("RUNE_EFFECT_NAMES")
RUNE_CONFLICTS = placeholder("RUNE_CONFLICTS")
_RUNE_SHARD_NAME = placeholder("_RUNE_SHARD_NAME")
_RUNE_SHARD_HITS = placeholder("_RUNE_SHARD_HITS")
RUNE_SHARD_KEY = placeholder("RUNE_SHARD_KEY")
AFFIXES = placeholder("AFFIXES")
SETS = placeholder("SETS")
LEGENDARY_EFFECTS = placeholder("LEGENDARY_EFFECTS")
PROPS = placeholder("PROPS")
ENHANCE_TABLE = placeholder("ENHANCE_TABLE")
MAX_ENHANCE = placeholder("MAX_ENHANCE")
ENHANCE_FAIL_DROP = placeholder("ENHANCE_FAIL_DROP")
ENHANCE_SMITH_MAPS = placeholder("ENHANCE_SMITH_MAPS")
UPGRADE_TABLE = placeholder("UPGRADE_TABLE")
UPGRADE_STONE = placeholder("UPGRADE_STONE")
UPGRADE_STAMINA = placeholder("UPGRADE_STAMINA")
UPGRADE_MATERIAL_CN = placeholder("UPGRADE_MATERIAL_CN")
REFINE_RECIPES = placeholder("REFINE_RECIPES")
_CFG_REFINE_EXCLUSIVE = placeholder("_CFG_REFINE_EXCLUSIVE")
REFINE_EXCLUSIVE_RECIPES = placeholder("REFINE_EXCLUSIVE_RECIPES")


def _num_sorted(tbl) -> dict:
    """int 键表 → 按**数值升序**（真源是 `for lv in range(...)`/字面量升序；JSON 是字典序，
    `\"10\" < \"2\"` ⇒ 不排序 = 升级表第 2 行漂到第 10 行后）。非整数键排在后面并保持相对序。"""
    ints = {k: v for k, v in (tbl or {}).items() if isinstance(k, int) and not isinstance(k, bool)}
    rest = {k: v for k, v in (tbl or {}).items() if k not in ints}
    return {**{k: ints[k] for k in sorted(ints)}, **rest}


def missing_domains() -> list:
    """本模块要用的域里，哪几张读不到（缺文件 / 坏 JSON / 空表）。"""
    out = []
    for name, sub in (("items", "data"), ("equip_roster", "data"),
                      ("runes", "data"), ("affixes", "data"),
                      ("sets", "data"), ("props", "data"),
                      ("legendary_effects", "data"),
                      ("enhance_table", "data"),
                      ("game_config", "rules")):
        if getattr(_R, name).missing:
            out.append(f"{sub}/{name}")
    return out


# ============================================================
# ④ 物品（`ITEMS` / `MATERIALS` / `MATERIALS_BY_NAME`）
# ------------------------------------------------------------
# 真源 `game/data/items.py`：`MATERIALS`（598，含 591 个 `mat_*` + 7 个白名单 id）先声明，
# 再若干 `ITEMS.update(...)` 追加消耗品/技能书等 → `ITEMS = dict(MATERIALS) + 追加段`（900）。
# 导出域 `items.json` = `ITEMS` 全量（逐键逐值相等，实测 900/900）。材料段与非材料段的**切法**
# 不靠前缀猜（`i_stone_*` / `item_*` 7 个不是 `mat_` 开头）—— 由 `_ORDER_MATERIALS` /
# `_ORDER_ITEMS_REST` 两段声明给出（生成自真源插入序，带集合守卫）。
# ============================================================
def _runes_build() -> dict:
    out: dict = {}
    for rid, ent in _R.runes.all().items():
        e = dict(ent)                                       # 副本（形状的表只读，不得就地改）
        if e.get("lvl") is not None:                        # int 键还原（不做 = 符文数值恒 0）
            e["lvl"] = _int_keys(e["lvl"])
        out[rid] = e
    return out


def _rune_conflicts() -> list:
    """真源 `RUNE_CONFLICTS`（3 对，**无向对**）← 域里每条符文的 `conflicts` 字段。

    规则：按真源符文插入序遍历，每遇到一条「未被收过的无向对」收一次，方向取遍历时那条符文
    的 effect（实测与真源逐位相同：`[[burn,freeze],[barrier,thorns],[scavenger,exp_bless]]`）。
    域侧是对称标注（互相都写），所以「首见即收」正好等价于真源的声明序。
    """
    out: list = []
    seen: set = set()
    for rid in _ORDER_RUNES:
        ent = _RUNES_RAW.get(rid) or {}
        eff = (RUNES.get(rid) or {}).get("effect")
        for other in (ent.get("conflicts") or []):
            pair = frozenset((eff, other))
            if pair in seen:
                continue
            seen.add(pair)
            out.append([eff, other])
    return out


_RUNES_RAW = placeholder("_RUNES_RAW")
_GAME_CONFIG = placeholder("_GAME_CONFIG")
_CFG_ENHANCE = placeholder("_CFG_ENHANCE")
_CFG_UPGRADE = placeholder("_CFG_UPGRADE")
_CFG_REFINE = placeholder("_CFG_REFINE")
MATERIALS = placeholder("MATERIALS")
ITEMS = placeholder("ITEMS")
MATERIALS_BY_NAME = placeholder("MATERIALS_BY_NAME")
EQUIP_ROSTER = placeholder("EQUIP_ROSTER")
EQUIP_ROSTER_BY_NAME = placeholder("EQUIP_ROSTER_BY_NAME")
RUNES = placeholder("RUNES")
RUNE_CRAFT = placeholder("RUNE_CRAFT")
_EFFECT_NAMES_BY_KEY = placeholder("_EFFECT_NAMES_BY_KEY")
RUNE_EFFECT_NAMES = placeholder("RUNE_EFFECT_NAMES")
RUNE_CONFLICTS = placeholder("RUNE_CONFLICTS")
_RUNE_SHARD_NAME = placeholder("_RUNE_SHARD_NAME")
_RUNE_SHARD_HITS = placeholder("_RUNE_SHARD_HITS")
RUNE_SHARD_KEY = placeholder("RUNE_SHARD_KEY")
AFFIXES = placeholder("AFFIXES")
SETS = placeholder("SETS")
LEGENDARY_EFFECTS = placeholder("LEGENDARY_EFFECTS")
PROPS = placeholder("PROPS")
ENHANCE_TABLE = placeholder("ENHANCE_TABLE")
MAX_ENHANCE = placeholder("MAX_ENHANCE")
ENHANCE_FAIL_DROP = placeholder("ENHANCE_FAIL_DROP")
ENHANCE_SMITH_MAPS = placeholder("ENHANCE_SMITH_MAPS")
UPGRADE_TABLE = placeholder("UPGRADE_TABLE")
UPGRADE_STONE = placeholder("UPGRADE_STONE")
UPGRADE_STAMINA = placeholder("UPGRADE_STAMINA")
UPGRADE_MATERIAL_CN = placeholder("UPGRADE_MATERIAL_CN")
REFINE_RECIPES = placeholder("REFINE_RECIPES")
_CFG_REFINE_EXCLUSIVE = placeholder("_CFG_REFINE_EXCLUSIVE")
REFINE_EXCLUSIVE_RECIPES = placeholder("REFINE_EXCLUSIVE_RECIPES")



__all__ = [
    "MATERIALS", "MATERIALS_BY_NAME", "ITEMS",
    "EQUIP_ROSTER", "EQUIP_ROSTER_BY_NAME",
    "RUNES", "RUNE_CRAFT", "RUNE_EFFECT_NAMES", "RUNE_CONFLICTS", "RUNE_SHARD_KEY",
    "AFFIXES", "SETS", "PROPS", "LEGENDARY_EFFECTS",
    "ENHANCE_TABLE", "MAX_ENHANCE", "ENHANCE_FAIL_DROP", "ENHANCE_SMITH_MAPS",
    "UPGRADE_TABLE", "UPGRADE_STONE", "UPGRADE_STAMINA", "UPGRADE_MATERIAL_CN",
    "REFINE_RECIPES", "REFINE_EXCLUSIVE_RECIPES", "missing_domains",
]



def _rebuild_view() -> list:
    """重读本模块声明的域 → 重建模块级派生状态；返回非容器替换序列（见文件头 ★ 视图）。

    容器（dict / list / set）就地更新（身份不变、内容已新）；非容器（tuple / frozenset /
    数字 / 字符串）本模块换引用，并把 `(旧对象, 新对象)` 序列交引擎做别名回填。
    import 期（见文件尾）与每次重载走**同一条路径**：本函数是唯一构建处。
    """
    global _RUNES_RAW, _GAME_CONFIG, _CFG_ENHANCE, _CFG_UPGRADE
    global _CFG_REFINE, MATERIALS, ITEMS, MATERIALS_BY_NAME
    global EQUIP_ROSTER, EQUIP_ROSTER_BY_NAME, RUNES, RUNE_CRAFT
    global _EFFECT_NAMES_BY_KEY, RUNE_EFFECT_NAMES, RUNE_CONFLICTS, _RUNE_SHARD_NAME
    global _RUNE_SHARD_HITS, RUNE_SHARD_KEY, AFFIXES, SETS
    global LEGENDARY_EFFECTS, PROPS, ENHANCE_TABLE, MAX_ENHANCE
    global ENHANCE_FAIL_DROP, ENHANCE_SMITH_MAPS, UPGRADE_TABLE, UPGRADE_STONE
    global UPGRADE_STAMINA, UPGRADE_MATERIAL_CN, REFINE_RECIPES, _CFG_REFINE_EXCLUSIVE
    global REFINE_EXCLUSIVE_RECIPES

    # 旧对象：容器要就地更新、非容器要交代给引擎（全部先抓一遍，再重建）
    old = {
        '_RUNES_RAW': None, '_GAME_CONFIG': None, '_CFG_ENHANCE': None, '_CFG_UPGRADE': None,
        '_CFG_REFINE': None, 'MATERIALS': None, 'ITEMS': None, 'MATERIALS_BY_NAME': None,
        'EQUIP_ROSTER': None, 'EQUIP_ROSTER_BY_NAME': None, 'RUNES': None, 'RUNE_CRAFT': None,
        '_EFFECT_NAMES_BY_KEY': None, 'RUNE_EFFECT_NAMES': None, 'RUNE_CONFLICTS': None, '_RUNE_SHARD_NAME': None,
        '_RUNE_SHARD_HITS': None, 'RUNE_SHARD_KEY': None, 'AFFIXES': None, 'SETS': None,
        'LEGENDARY_EFFECTS': None, 'PROPS': None, 'ENHANCE_TABLE': None, 'MAX_ENHANCE': None,
        'ENHANCE_FAIL_DROP': None, 'ENHANCE_SMITH_MAPS': None, 'UPGRADE_TABLE': None, 'UPGRADE_STONE': None,
        'UPGRADE_STAMINA': None, 'UPGRADE_MATERIAL_CN': None, 'REFINE_RECIPES': None, '_CFG_REFINE_EXCLUSIVE': None,
        'REFINE_EXCLUSIVE_RECIPES': None,
    }
    for _n in list(old):
        old[_n] = globals()[_n]

    _RUNES_RAW = records_from_domain(_PKG_ROOT, "runes").all()

    _GAME_CONFIG = _R.game_config.all()
    _CFG_ENHANCE = dict(_GAME_CONFIG.get("enhance") or {})
    _CFG_UPGRADE = dict(_GAME_CONFIG.get("upgrade") or {})
    _CFG_REFINE = dict(_GAME_CONFIG.get("refine") or {})

    # ============================================================
    # ③b 两个键型小工具（形状覆盖不到的嵌套/数值序变换）
    # ============================================================
    MATERIALS = {k: _R.items.all()[k] for k in _ORDER_MATERIALS}   # 已按声明序排好 + 集合守卫
    ITEMS = dict(_R.items.all())

    # 名字 → 材料条目（真源 `items.py:3054 {_m["name"]: _m for _m in MATERIALS.values()}`；值序 = MATERIALS 序）
    MATERIALS_BY_NAME = {v["name"]: v for v in MATERIALS.values() if isinstance(v, dict) and v.get("name")}

    # ============================================================
    # ⑤ 装备名册（`EQUIP_ROSTER` / `EQUIP_ROSTER_BY_NAME`）
    # ------------------------------------------------------------
    # 真源 `game/data/equip_roster.py:15 EQUIP_ROSTER`（687）。域条目多两个**导出期注入**字段
    # （`series_set` ← `SERIES_SETS`、`fixed_affixes` ← `SERIES_FIXED_AFFIX`）→ 必须剥，否则逐条不等。
    # `EQUIP_ROSTER_BY_NAME`（:1048 `setdefault(name, []).append(id)`）= 名字 → [id]（686 键 / 687 id，
    # 重名 1 处「精铁短杖」）—— S2 ③：**索引本体改由引擎 records 建**（`Records.index_of`：
    # 重名收全、值序 = 表序、缺字段/None/非映射不参与并留痕），本模块不再手写一遍
    # `setdefault(...).append(...)`（同一件事两处实现 = 改一处漏一处）。
    # ============================================================
    EQUIP_ROSTER = _R.equip_roster.all()

    EQUIP_ROSTER_BY_NAME = _R.equip_roster.index_of("name")

    # ============================================================
    # ⑥ 符文（`RUNES` / `RUNE_CRAFT` / `RUNE_EFFECT_NAMES` / `RUNE_CONFLICTS` / `RUNE_SHARD_KEY`）
    # ------------------------------------------------------------
    # 真源 `game/data/runes.py`：`RUNES`（16，`lvl` 是 **int 键**）+ 常量段 `RUNE_CONFLICTS`（3 对）/
    # `RUNE_DROP` / `RUNE_EFFECT_NAMES` / `RUNE_LEVEL_ROMAN` / `RUNE_CRAFT` / `RUNE_CRAFT_SHARDS` /
    # `RUNE_SHARD_KEY`。域 `runes.json` 把 `RUNE_CRAFT` 折成条目 `craft` 字段、`RUNE_CONFLICTS`
    # 折成对称的条目 `conflicts` 字段 → 两张表都由剥出来的值重建（序由真源插入序声明给出）。
    # `RUNE_DROP` / `RUNE_LEVEL_ROMAN` / `RUNE_CRAFT_SHARDS` **无域** → 缺口，不提供。
    # ============================================================
    RUNES = _runes_build()

    # 符文制作配方（真源 `RUNE_CRAFT`，序 = 真源插入序）
    RUNE_CRAFT = {
        rid: dict(_RUNES_RAW[rid]["craft"])
        for rid in _ORDER_RUNE_CRAFT if rid in _RUNES_RAW and "craft" in _RUNES_RAW[rid]
    }

    # 效果 key → 中文名（真源 `RUNE_EFFECT_NAMES`；值 = `RUNES[*]["name"]`，实测 16/16 逐条相等）
    _EFFECT_NAMES_BY_KEY = {v["effect"]: v.get("name") for v in RUNES.values() if isinstance(v, dict)}
    RUNE_EFFECT_NAMES = {
        eff: _EFFECT_NAMES_BY_KEY[eff]
        for eff in _ORDER_RUNE_EFFECT_NAMES if eff in _EFFECT_NAMES_BY_KEY
    }

    RUNE_CONFLICTS = _rune_conflicts()

    # 符文碎片材料 key（真源常量 `RUNE_SHARD_KEY = "mat_fu_wen_sui_pian"`，注释写明「items.py 已定义
    # 名字『符文碎片』」）→ 按**名字唯一命中**从 items 域取 key（命中 ≠ 1 就 raise，不猜）。
    _RUNE_SHARD_NAME = "符文碎片"
    _RUNE_SHARD_HITS = [k for k, v in ITEMS.items() if isinstance(v, dict) and v.get("name") == _RUNE_SHARD_NAME]
    if len(_RUNE_SHARD_HITS) != 1:
        raise ValueError(
            "catalog_items：items 域里名字 %r 的条目有 %d 条（要求恰好 1 条）—— RUNE_SHARD_KEY "
            "无法唯一确定，拒绝猜。" % (_RUNE_SHARD_NAME, len(_RUNE_SHARD_HITS)))
    RUNE_SHARD_KEY = _RUNE_SHARD_HITS[0]

    # ============================================================
    # ⑦ 词条 / 套装 / 道具 / 传说特效（域直读，仅还原序）
    # ============================================================
    AFFIXES = _R.affixes.all()
    SETS = _R.sets.all()
    LEGENDARY_EFFECTS = _R.legendary_effects.all()

    # 道具（真源 `game/data/props.py:12 PROPS`）；域条目多一个导出期注入的 `mounts`（← `MOUNT_POOL`
    # 挂点）→ 剥掉（道具本体条目没有它）。
    PROPS = _R.props.all()

    # ============================================================
    # ⑧ 强化 / 升级 / 精炼（数值键表 + `game_config` 三组常量）
    # ------------------------------------------------------------
    # 真源 `game/data/enhance.py` / `upgrade.py` / `refine.py`；常量组在 `content/rules/game_config.json`
    # 的 `enhance` / `upgrade` / `refine`（导出器「每个模块级常量都有家」硬闸的产物）。
    # 三张数值键表（`ENHANCE_TABLE` / `UPGRADE_TABLE` / `ENHANCE_FAIL_DROP`）都按数值升序还原键型。
    # ============================================================
    ENHANCE_TABLE = _num_sorted(_R.enhance_table.all())
    MAX_ENHANCE = _CFG_ENHANCE.get("MAX_ENHANCE")
    ENHANCE_FAIL_DROP = _num_sorted(_int_keys(_CFG_ENHANCE.get("ENHANCE_FAIL_DROP")))
    ENHANCE_SMITH_MAPS = list(_CFG_ENHANCE.get("ENHANCE_SMITH_MAPS") or [])

    UPGRADE_TABLE = _num_sorted(_int_keys(_CFG_UPGRADE.get("UPGRADE_TABLE")))
    UPGRADE_STONE = _CFG_UPGRADE.get("UPGRADE_STONE")
    UPGRADE_STAMINA = _CFG_UPGRADE.get("UPGRADE_STAMINA")
    UPGRADE_MATERIAL_CN = _CFG_UPGRADE.get("UPGRADE_MATERIAL_CN")

    REFINE_RECIPES = dict(_CFG_REFINE.get("REFINE_RECIPES") or {})

    # ---- B15b 追加（只加新名，既有名与取值不动）----
    # `REFINE_EXCLUSIVE_RECIPES`：真源 `game/data/refine_exclusive.py:18`（v172 路 B 重锻专属 12 条，
    # 键 = 旧装备中文名，值 = {target(名册 rid), mats, gold, inherit, desc}）。域 = `content/rules/game_config.json`
    # 的**新组** `refine_exclusive`（组名 = 真源模块名，与 `refine` 组同款口径；数据由
    # `overnight/b15b_port_domain.py` 从备份真源 import 后 dump，非手抄）。
    # 为什么必须有这个门面名：宿主聚合层 `C.REFINE_EXCLUSIVE_RECIPES` 开关后**没有对象**了，
    # 而 `content/economy_cmds.py` 的 4 处 `getattr(C, "REFINE_EXCLUSIVE_RECIPES", None) or {}`
    # 会静默退成 `{}`（= v172 路 B 的重锻专属配方在『装备重锻』列表/获取提示里**整块消失**）。
    # 本名由 `game/content.py` 的 `catalog_*` 聚合循环自动收回 ⇒ `C.<名>` 恢复（宿主侧零改动）。
    _CFG_REFINE_EXCLUSIVE = dict(_GAME_CONFIG.get("refine_exclusive") or {})
    REFINE_EXCLUSIVE_RECIPES = dict(_CFG_REFINE_EXCLUSIVE.get("REFINE_EXCLUSIVE_RECIPES") or {})

    # 收敛：容器就地更新（身份不变）；非容器交引擎按身份回填
    out = []
    for name in old:
        before, new = old[name], globals()[name]
        if before is new:
            continue
        if isinstance(new, (dict, list, set)):
            if _same_container(before, new):
                update_in_place(before, new)   # 就地更新：消费方手头引用身份不变
                globals()[name] = before
            continue                           # 首次构建：全局已是新对象
        out.append((before, new))
    return out


def _same_container(a, b) -> bool:
    """同型可变容器（dict / list / set）—— 就地更新只对同型成立。"""
    return ((isinstance(a, dict) and isinstance(b, dict))
            or (isinstance(a, list) and isinstance(b, list))
            or (isinstance(a, set) and isinstance(b, set)))


register_view(_rebuild_view, order=30)
apply_replacements(_rebuild_view(), __package__)
