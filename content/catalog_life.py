# -*- coding: utf-8 -*-
"""包内生活经济门面（`content/catalog_life.py`）—— 游戏仓聚合层 `C` 的「D-生活经济族」等价物。

为什么需要它
------------
宿主 `game/content.py` 是 19 行薄聚合层（`from .data import *` + `from .core import *`），
包内模块过去用宿主句柄（`_HostMod("content")` / `bind_host(content=C)`）读它的名字。
宿主 `game/data`（74,707 行 / 87 文件）要删，所以这些名字必须先在包内**由域 JSON 重建**——
本模块就是 D 单元（生活经济族，53 个数据名里可从域重建的 42 个）的那一层。

读口纪律（B14_BRIEF §3 / 计划 §9 I1·I2）
----------------------------------------
* 只读包内域数据：`content/data/<域>.json` · `content/rules/<域>.json`（缺文件/坏 JSON → 空，不抛，
  与 `content/tables.py:48 _read_json` 同款）。
* **不 import 宿主任何模块**、**不用 `_HostMod`/`_host_attr`** —— 宿主表删掉之后本模块仍能活。

域来源（真源 = 游戏仓；单向导出器 = 游戏仓 `scripts/export_*`）
--------------------------------------------------------------
    content/data/craft.json             ← derive_craft       426 条配方（含导出期注入的 `aliases`）
    content/data/alchemy.json           ← derive_alchemy      91 条炼金配方
    content/data/cooking.json           ← derive_cooking      59 条烹饪配方
    content/data/fishing_spots.json     ← derive_fishing_spots 11 个钓点
    content/data/fishing_pool.json      ← derive_fishing_pool  30 条渔获（带 `seq` = 源插入序）
    content/data/shop.json              ← derive_shop        89 条店铺合表（六张源表并集）
    content/data/pets.json              ← derive_pets        16 个品种（每品种挂 `egg_roll` 规则行）
    content/rules/game_config.json      ← derive_game_config 配置/常量归口（一条 = 一个源模块）

三处「类型还原」（JSON 只有 str 键 / 只有 array，不做还原就是静默错值）
----------------------------------------------------------------------
  ① **int 键**：`HOUSE_LEVELS` / `HOUSE_REFUND` / `RUNE_LEVEL_GATE` —— 源里是 int 键
     （`HOUSE_LEVELS[lv]`、`RUNE_LEVEL_GATE[gem_lv]`），不还原 = 查表恒空（与 `tables.py:ENHANCE_TABLE` 同族坑）。
  ② **tuple 值**：`PROF_TUTORS` / `PROF_WAIT_BASE` / `DAILY_PROF_TASKS` —— 源里是元组
     （消费端按 `(导师, 城市)` / `(低, 高, 名)` 解包），JSON 落成 array → 必须还原成 tuple，
     否则门禁深比较报「类型不同（tuple vs list）」。
  ③ **导出期注入字段要剥**：`craft.json` 条目的 `aliases`（= 真源 `CRAFT_RECIPE_ALIASES` 折进条目）
     → `CRAFT_RECIPES` 必须剥掉它、`CRAFT_RECIPE_ALIASES` 由它重建；
     `fishing_pool.json` 的 `seq`、`pets.json` 的 `egg_roll` 同理（`FISH_POOL` 剥 `seq`、`PET_POOL` 剥 `egg_roll`）。

键序（迭代序）：域落盘走导出契约 `sort_table`（字典序），真源是**手写插入序** ⇒ 序不可逆
--------------------------------------------------------------------------------------
本模块按 `content/quests_flow.py:SIDE_QUEST_ORDER` / `content/event_menu.py:MAP_ORDER` /
`content/tables.py:JOB_ORDER` 同一手法**显式声明真源插入序**（`_ORDER_*`，见「① 顺序声明」段），
带集合守卫：域里多一条/少一条就 `raise`（防「加了内容忘了改这里」= 静默改序）。
顺序字面量由 `overnight/_b14d_gen_orders.py` 从真源生成（本文件不手抄）。
更彻底的做法是**在域里补 `seq`/`order` 字段**（I3 反向可逆性）—— 已在 `overnight/W-B14-D.md` 登记给主 agent 裁。

⚠ 无域可依的名字（11 个）：本模块**不提供**（不许编数据），逐名缺口见 `overnight/W-B14-D.md`：
    PET_MAX_LEVEL · PET_SKILL_UNLOCK_LV                —— 宿主 `game/data/pets.py`（常量段，无域）
    FISH_COLLECT · FISH_EXP                            —— 宿主 `game/data/fishing.py`（导出器只导了 FISH_POOL）
    FACTIONS · FACTION_ORDER · REPUTATION_TIERS ·
    AREA_FACTION · CHRONICLES                          —— 宿主 `game/data/factions.py`（无域）
    HONOR_SHOP                                         —— 宿主 `game/data/honor_shop.py`（无域）
    GUILD_CONFIG                                       —— 宿主 `game/data/guild.py`（guild 域只导了 roles/shop_items/skills）
"""
from __future__ import annotations

import os

from saintess_engine.records import apply_replacements, placeholder, register_view, set_from_domains, update_in_place

from ._domainio import int_keys as _int_keys, order_of as _order, seq_rows   # P0-4 域读口单源

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读域文件 / 缺表留痕（`missing`）收进引擎 records 形状的域声明（本文件的域顶层键无声明序）。
# **域元数据唯一源 = 包内 `editor/domains.json`**（S2 ②：这里只声明「我要哪些域」，
# 落点由声明的 `kind` 派生；声明缺项 / 文件缺 / 声明与磁盘不符 → 装载期报错，不静默）。
_R = set_from_domains(_PKG_ROOT, (
    "game_config", "craft", "alchemy", "cooking",
    "fishing_spots", "fishing_pool", "shop", "pets",
))


def _tupled(tbl) -> dict:
    """值是 array 的条目 → tuple（源侧是元组，消费端按位解包）。**键序原样**。"""
    return {k: tuple(v) for k, v in (tbl or {}).items()}


def _pick(tbl, field: str) -> dict:
    """从「合表」里取某一列：`{键: 条目[field]}`（条目没这列 → 该键不出现，不补空）。"""
    return {k: v[field] for k, v in (tbl or {}).items() if field in v}


# ---- 序声明读口：**唯一源** = `content/data/key_order.json`（`key_order` 域）----
# S2 ①：本文件原先内嵌的 12 张序字面量（`__B14D_ORDERS_BEGIN__` 段）已搬进该域，
# 「值 + 类型 + 序」与搬前逐元素对拍相等；读不到即 raise（**不静默空序**）。


# ============================================================
# ① 顺序声明 —— 真源插入序（域落盘是字典序，序只能显式带出）
#    字面量由 `overnight/_b14d_gen_orders.py` 从真源生成；本文件不手抄。
# ============================================================
# __B14D_ORDERS_BEGIN__
_ORDER_CRAFT_RECIPES = _order("craft")
_ORDER_CRAFT_RECIPE_ALIASES = _order("craft_aliases")
_ORDER_ALCHEMY_RECIPES = _order("alchemy")
_ORDER_COOKING_RECIPES = _order("cooking")
_ORDER_FISHING_SPOTS = _order("fishing_spots")
_ORDER_SHOP_WEAPONS = _order("shop_weapons")
_ORDER_SHOP_EQUIP = _order("shop_equip")
_ORDER_SHOP_SMITH_MATERIALS = _order("shop_smith_materials")
_ORDER_SHOP_SUBAREA_ITEMS = _order("shop_subarea_items")
_ORDER_SUBAREA_KIND = _order("subarea_kind")
_ORDER_PET_POOL = _order("pet_pool")
_ORDER_PET_EGG_ROLL = _order("pet_egg_roll")
# __B14D_ORDERS_END__


def _order_list(block) -> list:
    """顺序声明 → 键列表。

    S2 ① 起声明来自 `key_order` 域（已经是 list）；旧的「空白分隔三引号块」写法仍收
    （`#` 起头到行尾为注释），两种形态给出同一份键列表。
    """
    if isinstance(block, (list, tuple)):
        return list(block)
    out: list = []
    for line in (block or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.extend(line.split())
    return out


def _ordered(raw: dict, block: str, where: str) -> dict:
    """按声明序重排 `{键: 条目}`；域/声明键集不一致 → `raise`（静默漏条目的防线）。

    与 `content/catalog_items.py:_ordered` 同款（带重复键守卫与差集报错）。
    """
    keys = _order_list(block)
    if not keys:
        return dict(raw or {})
    if len(set(keys)) != len(keys):
        raise ValueError(f"catalog_life：{where} 的序声明有重复键 —— 拒绝静默取首个")
    if set(raw or {}) != set(keys):
        miss = sorted(set(raw or {}) - set(keys))
        extra = sorted(set(keys) - set(raw or {}))
        raise ValueError(
            f"catalog_life：{where} 域与序声明不一致（域多 {len(miss)} / 声明多 {len(extra)}）"
            f"—— 请重跑 overnight/_b14d_gen_orders.py 同步序声明。域多 {miss[:5]} … 声明多 {extra[:5]} …")
    return {k: raw[k] for k in keys}


# ============================================================
# ② 配置归口域 `game_config`（rules）—— 一个组 = 一个宿主源模块的常量组
# ============================================================
def _cfg(group: str) -> dict:
    """取 `game_config` 的一个组（缺组 → 空 dict；键序原样，导出期未排序）。"""
    g = _GAME_CONFIG.get(group)
    return dict(g) if isinstance(g, dict) else {}


# ---- econ_config 组（真源 game/data/econ_config.py）----
_GAME_CONFIG = placeholder("_GAME_CONFIG")
ECON_CONFIG = placeholder("ECON_CONFIG")
_PROF = placeholder("_PROF")
PROF_TUTORS = placeholder("PROF_TUTORS")
PROF_WAIT_BASE = placeholder("PROF_WAIT_BASE")
DAILY_PROF_TASKS = placeholder("DAILY_PROF_TASKS")
BAG_FILTER_TYPES = placeholder("BAG_FILTER_TYPES")
PROF_STAMINA_COST = placeholder("PROF_STAMINA_COST")
PROF_WAIT_DECAY = placeholder("PROF_WAIT_DECAY")
PROF_WAIT_FLOOR = placeholder("PROF_WAIT_FLOOR")
MINING_KEYWORDS = placeholder("MINING_KEYWORDS")
PAWN_RATES = placeholder("PAWN_RATES")
ENCHANT_SLOT_UNLOCK = placeholder("ENCHANT_SLOT_UNLOCK")
RUNE_LEVEL_GATE = placeholder("RUNE_LEVEL_GATE")
DAILY_PROF_EXP = placeholder("DAILY_PROF_EXP")
RARE_MATERIAL_PRICE = placeholder("RARE_MATERIAL_PRICE")
_HOUSING = placeholder("_HOUSING")
PROPERTIES = placeholder("PROPERTIES")
HOUSE_LEVELS = placeholder("HOUSE_LEVELS")
HOUSE_MAX_LEVEL = placeholder("HOUSE_MAX_LEVEL")
HOUSE_REFUND = placeholder("HOUSE_REFUND")
_GATHER = placeholder("_GATHER")
CAMP_SPOTS = placeholder("CAMP_SPOTS")
MINE_SPOTS = placeholder("MINE_SPOTS")
_CALAMITY = placeholder("_CALAMITY")
CALAMITY_MAX = placeholder("CALAMITY_MAX")
CALAMITY_COST = placeholder("CALAMITY_COST")
CALAMITY_STATS = placeholder("CALAMITY_STATS")
CALAMITY_BONUS = placeholder("CALAMITY_BONUS")
CALAMITY_MALUS = placeholder("CALAMITY_MALUS")
CALAMITY_POSITIVE_CHANCE = placeholder("CALAMITY_POSITIVE_CHANCE")
MOUNT_POOL = placeholder("MOUNT_POOL")
MOUNT_BY_KEY = placeholder("MOUNT_BY_KEY")
_CRAFT = placeholder("_CRAFT")
_CRAFT_STRIPPED = placeholder("_CRAFT_STRIPPED")
CRAFT_RECIPES = placeholder("CRAFT_RECIPES")
CRAFT_RECIPE_ALIASES = placeholder("CRAFT_RECIPE_ALIASES")
ALCHEMY_RECIPES = placeholder("ALCHEMY_RECIPES")
COOKING_RECIPES = placeholder("COOKING_RECIPES")
FISHING_SPOTS = placeholder("FISHING_SPOTS")
FISH_POOL = placeholder("FISH_POOL")
_SHOP = placeholder("_SHOP")
SHOP_WEAPONS = placeholder("SHOP_WEAPONS")
SHOP_EQUIP = placeholder("SHOP_EQUIP")
SHOP_SMITH_MATERIALS = placeholder("SHOP_SMITH_MATERIALS")
SHOP_SUBAREA_ITEMS = placeholder("SHOP_SUBAREA_ITEMS")
SHOP_WILD_TRADE = placeholder("SHOP_WILD_TRADE")
SUBAREA_KIND = placeholder("SUBAREA_KIND")
_PETS = placeholder("_PETS")
_PET_POOL_BY_KEY = placeholder("_PET_POOL_BY_KEY")
PET_POOL = placeholder("PET_POOL")
PET_EGG_ROLL = placeholder("PET_EGG_ROLL")

REQUIRED_DOMAINS = ("game_config", "craft", "alchemy", "cooking",
                    "fishing_spots", "fishing_pool", "shop", "pets")


def missing_domains() -> list:
    """缺哪张源域（文件不在 / 坏 JSON / 空表）→ 域名清单（空 = 全在）。"""
    return [d for d in REQUIRED_DOMAINS if getattr(_R, d).missing]


# 本模块**不做**的名字（无域可依，禁编数据；详见报告「缺口」表）：
#   PET_MAX_LEVEL · PET_SKILL_UNLOCK_LV · FISH_COLLECT · FISH_EXP · FACTIONS · FACTION_ORDER ·
#   REPUTATION_TIERS · AREA_FACTION · CHRONICLES · HONOR_SHOP · GUILD_CONFIG
__all__ = [
    "ECON_CONFIG", "PROF_TUTORS", "PROF_WAIT_BASE", "DAILY_PROF_TASKS", "BAG_FILTER_TYPES",
    "PROF_STAMINA_COST", "PROF_WAIT_DECAY", "PROF_WAIT_FLOOR", "MINING_KEYWORDS", "PAWN_RATES",
    "ENCHANT_SLOT_UNLOCK", "RUNE_LEVEL_GATE", "DAILY_PROF_EXP", "RARE_MATERIAL_PRICE",
    "PROPERTIES", "HOUSE_LEVELS", "HOUSE_MAX_LEVEL", "HOUSE_REFUND",
    "CAMP_SPOTS", "MINE_SPOTS",
    "CALAMITY_MAX", "CALAMITY_COST", "CALAMITY_STATS", "CALAMITY_BONUS", "CALAMITY_MALUS",
    "CALAMITY_POSITIVE_CHANCE",
    "MOUNT_POOL", "MOUNT_BY_KEY",
    "CRAFT_RECIPES", "CRAFT_RECIPE_ALIASES", "ALCHEMY_RECIPES", "COOKING_RECIPES",
    "FISHING_SPOTS", "FISH_POOL",
    "SHOP_WEAPONS", "SHOP_EQUIP", "SHOP_SMITH_MATERIALS", "SHOP_SUBAREA_ITEMS",
    "SHOP_WILD_TRADE", "SUBAREA_KIND",
    "PET_POOL", "PET_EGG_ROLL",
    "REQUIRED_DOMAINS", "missing_domains",
]



def _rebuild_view() -> list:
    """重读本模块声明的域 → 重建模块级派生状态；返回非容器替换序列（见文件头 ★ 视图）。

    容器（dict / list / set）就地更新（身份不变、内容已新）；非容器（tuple / frozenset /
    数字 / 字符串）本模块换引用，并把 `(旧对象, 新对象)` 序列交引擎做别名回填。
    import 期（见文件尾）与每次重载走**同一条路径**：本函数是唯一构建处。
    """
    global _GAME_CONFIG, ECON_CONFIG, _PROF, PROF_TUTORS
    global PROF_WAIT_BASE, DAILY_PROF_TASKS, BAG_FILTER_TYPES, PROF_STAMINA_COST
    global PROF_WAIT_DECAY, PROF_WAIT_FLOOR, MINING_KEYWORDS, PAWN_RATES
    global ENCHANT_SLOT_UNLOCK, RUNE_LEVEL_GATE, DAILY_PROF_EXP, RARE_MATERIAL_PRICE
    global _HOUSING, PROPERTIES, HOUSE_LEVELS, HOUSE_MAX_LEVEL
    global HOUSE_REFUND, _GATHER, CAMP_SPOTS, MINE_SPOTS
    global _CALAMITY, CALAMITY_MAX, CALAMITY_COST, CALAMITY_STATS
    global CALAMITY_BONUS, CALAMITY_MALUS, CALAMITY_POSITIVE_CHANCE, MOUNT_POOL
    global MOUNT_BY_KEY, _CRAFT, _CRAFT_STRIPPED, CRAFT_RECIPES
    global CRAFT_RECIPE_ALIASES, ALCHEMY_RECIPES, COOKING_RECIPES, FISHING_SPOTS
    global FISH_POOL, _SHOP, SHOP_WEAPONS, SHOP_EQUIP
    global SHOP_SMITH_MATERIALS, SHOP_SUBAREA_ITEMS, SHOP_WILD_TRADE, SUBAREA_KIND
    global _PETS, _PET_POOL_BY_KEY, PET_POOL, PET_EGG_ROLL

    # 旧对象：容器要就地更新、非容器要交代给引擎（全部先抓一遍，再重建）
    old = {
        '_GAME_CONFIG': None, 'ECON_CONFIG': None, '_PROF': None, 'PROF_TUTORS': None,
        'PROF_WAIT_BASE': None, 'DAILY_PROF_TASKS': None, 'BAG_FILTER_TYPES': None, 'PROF_STAMINA_COST': None,
        'PROF_WAIT_DECAY': None, 'PROF_WAIT_FLOOR': None, 'MINING_KEYWORDS': None, 'PAWN_RATES': None,
        'ENCHANT_SLOT_UNLOCK': None, 'RUNE_LEVEL_GATE': None, 'DAILY_PROF_EXP': None, 'RARE_MATERIAL_PRICE': None,
        '_HOUSING': None, 'PROPERTIES': None, 'HOUSE_LEVELS': None, 'HOUSE_MAX_LEVEL': None,
        'HOUSE_REFUND': None, '_GATHER': None, 'CAMP_SPOTS': None, 'MINE_SPOTS': None,
        '_CALAMITY': None, 'CALAMITY_MAX': None, 'CALAMITY_COST': None, 'CALAMITY_STATS': None,
        'CALAMITY_BONUS': None, 'CALAMITY_MALUS': None, 'CALAMITY_POSITIVE_CHANCE': None, 'MOUNT_POOL': None,
        'MOUNT_BY_KEY': None, '_CRAFT': None, '_CRAFT_STRIPPED': None, 'CRAFT_RECIPES': None,
        'CRAFT_RECIPE_ALIASES': None, 'ALCHEMY_RECIPES': None, 'COOKING_RECIPES': None, 'FISHING_SPOTS': None,
        'FISH_POOL': None, '_SHOP': None, 'SHOP_WEAPONS': None, 'SHOP_EQUIP': None,
        'SHOP_SMITH_MATERIALS': None, 'SHOP_SUBAREA_ITEMS': None, 'SHOP_WILD_TRADE': None, 'SUBAREA_KIND': None,
        '_PETS': None, '_PET_POOL_BY_KEY': None, 'PET_POOL': None, 'PET_EGG_ROLL': None,
    }
    for _n in list(old):
        old[_n] = globals()[_n]

    _GAME_CONFIG = _R.game_config.all()

    ECON_CONFIG = _cfg("econ_config").get("ECON_CONFIG") or {}

    # ---- prof_config 组（真源 game/data/prof_config.py，15 个常量）----
    _PROF = _cfg("prof_config")
    PROF_TUTORS = _tupled(_PROF.get("PROF_TUTORS"))              # {副业: (导师, 城市)}
    PROF_WAIT_BASE = _tupled(_PROF.get("PROF_WAIT_BASE"))        # {副业: (低秒, 高秒, 名)}
    DAILY_PROF_TASKS = _tupled(_PROF.get("DAILY_PROF_TASKS"))    # {副业: (任务名, 次数, 金币)}
    BAG_FILTER_TYPES = list(_PROF.get("BAG_FILTER_TYPES") or [])
    PROF_STAMINA_COST = dict(_PROF.get("PROF_STAMINA_COST") or {})
    PROF_WAIT_DECAY = _PROF.get("PROF_WAIT_DECAY", 0.0)
    PROF_WAIT_FLOOR = _PROF.get("PROF_WAIT_FLOOR", 0)
    MINING_KEYWORDS = list(_PROF.get("MINING_KEYWORDS") or [])
    PAWN_RATES = dict(_PROF.get("PAWN_RATES") or {})
    ENCHANT_SLOT_UNLOCK = dict(_PROF.get("ENCHANT_SLOT_UNLOCK") or {})
    RUNE_LEVEL_GATE = _int_keys(_PROF.get("RUNE_LEVEL_GATE"))     # {符文等级: 附魔副业等级}
    DAILY_PROF_EXP = _PROF.get("DAILY_PROF_EXP", 0)
    RARE_MATERIAL_PRICE = _PROF.get("RARE_MATERIAL_PRICE", 0)
    # （同组的 PRICE_BAND / GATHER_MAP_MIN_LV 属函数侧常量，E 单元与 `content/profession.py` 各自消费）

    # ---- housing 组（真源 game/data/housing.py）----
    _HOUSING = _cfg("housing")
    PROPERTIES = dict(_HOUSING.get("PROPERTIES") or {})
    HOUSE_LEVELS = {k: dict(v) for k, v in _int_keys(_HOUSING.get("HOUSE_LEVELS")).items()}
    HOUSE_MAX_LEVEL = _HOUSING.get("HOUSE_MAX_LEVEL", 0)
    HOUSE_REFUND = _int_keys(_HOUSING.get("HOUSE_REFUND"))

    # ---- gather 组（真源 game/data/gather.py；采集/挖掘点池在 gather_pools/子域别处）----
    _GATHER = _cfg("gather")
    CAMP_SPOTS = dict(_GATHER.get("CAMP_SPOTS") or {})
    MINE_SPOTS = {k: dict(v) for k, v in (_GATHER.get("MINE_SPOTS") or {}).items()}

    # ---- calamity 组（真源 game/data/calamity.py，v136 怪异炼成）----
    _CALAMITY = _cfg("calamity")
    CALAMITY_MAX = _CALAMITY.get("CALAMITY_MAX", 0)
    CALAMITY_COST = dict(_CALAMITY.get("CALAMITY_COST") or {})
    CALAMITY_STATS = list(_CALAMITY.get("CALAMITY_STATS") or [])
    CALAMITY_BONUS = _CALAMITY.get("CALAMITY_BONUS", 0.0)
    CALAMITY_MALUS = _CALAMITY.get("CALAMITY_MALUS", 0.0)
    CALAMITY_POSITIVE_CHANCE = _CALAMITY.get("CALAMITY_POSITIVE_CHANCE", 0.0)

    # ---- mounts 组（真源 game/data/mounts.py；`MOUNT_BY_KEY` 是派生索引）----
    MOUNT_POOL = list(_cfg("mounts").get("MOUNT_POOL") or [])
    # 真源 `mounts.py:70 MOUNT_BY_KEY = {m["key"]: m for m in MOUNT_POOL}` —— 键序 = MOUNT_POOL 序
    MOUNT_BY_KEY = {m["key"]: m for m in MOUNT_POOL}

    # ============================================================
    # ③ 副业配方域 `craft` / `alchemy` / `cooking`（data）
    # ============================================================
    _CRAFT = _R.craft.all()

    # 配方条目剥掉导出期注入的 `aliases`（= 真源 CRAFT_RECIPE_ALIASES 折进条目）
    _CRAFT_STRIPPED = {
        rid: {k: v for k, v in ent.items() if k != "aliases"}
        for rid, ent in _CRAFT.items()
    }
    CRAFT_RECIPES = _ordered(_CRAFT_STRIPPED, _ORDER_CRAFT_RECIPES, "craft 配方")

    # 别名表：真源 `CRAFT_RECIPE_ALIASES`={配方 id: [名字…]}，导出期折进条目 `aliases`
    CRAFT_RECIPE_ALIASES = _ordered(
        {rid: list(ent["aliases"]) for rid, ent in _CRAFT.items() if ent.get("aliases")},
        _ORDER_CRAFT_RECIPE_ALIASES, "craft 配方别名")

    ALCHEMY_RECIPES = _ordered(
        {k: dict(v) for k, v in _R.alchemy.all().items()},
        _ORDER_ALCHEMY_RECIPES, "alchemy 配方")
    COOKING_RECIPES = _ordered(
        {k: dict(v) for k, v in _R.cooking.all().items()},
        _ORDER_COOKING_RECIPES, "cooking 配方")

    # ============================================================
    # ④ 垂钓域 `fishing_spots` / `fishing_pool`（data）
    # ============================================================
    FISHING_SPOTS = _ordered(
        {k: dict(v) for k, v in _R.fishing_spots.all().items()},
        _ORDER_FISHING_SPOTS, "fishing_spots")

    # 渔获池 = 源 list 的等价物：域 = {鱼名: 条目 + seq}，按 `seq` 还原成 list 并剥掉 `seq`
    # （源 `FISH_POOL` 是 list、插入序参与 `random.choices` 抽样 → 必须保序；域里已有 `seq`，不需要序声明）
    FISH_POOL = seq_rows(_R.fishing_pool.all().values())

    # ============================================================
    # ⑤ 商店域 `shop`（data）—— 89 条「六张源表并集」合表，按列拆回各表
    #    ⚠ 合表里五列是**五张源表**，各有各的插入序 → 每列一个序声明
    # ============================================================
    _SHOP = _R.shop.all()

    SHOP_WEAPONS = _ordered(_pick(_SHOP, "weapons"), _ORDER_SHOP_WEAPONS,
                                  "shop.weapons")               # 真源 game/data/shop.py:83
    SHOP_EQUIP = _ordered(_pick(_SHOP, "equip"), _ORDER_SHOP_EQUIP,
                                "shop.equip")                   # 真源 game/data/shop.py:293
    SHOP_SMITH_MATERIALS = _ordered(_pick(_SHOP, "materials"), _ORDER_SHOP_SMITH_MATERIALS,
                                          "shop.materials")     # 真源 game/data/shop.py:232
    # 子区域配货：合表里唯一非店铺条目是保留键 `wild_trade`（行商货单），要从本表排除
    SHOP_SUBAREA_ITEMS = _ordered(
        {k: v["items"] for k, v in _SHOP.items() if "items" in v and k != "wild_trade"},
        _ORDER_SHOP_SUBAREA_ITEMS, "shop.items")                # 真源 shop.py:22
    SHOP_WILD_TRADE = list((_SHOP.get("wild_trade") or {}).get("items") or [])  # 真源 shop.py:13
    # 设施类别表（真源 game/data/shop.py:417）
    SUBAREA_KIND = _ordered(_pick(_SHOP, "kind"), _ORDER_SUBAREA_KIND, "shop.kind")

    # ============================================================
    # ⑥ 宠物域 `pets`（data）—— 一条 = 一个品种，规则行挂在条目 `egg_roll`
    # ============================================================
    _PETS = _R.pets.all()
    # 品种池：剥掉导出期注入的 `egg_roll`（= 该品种的掷蛋规则行）
    _PET_POOL_BY_KEY = _ordered(
        {k: {kk: vv for kk, vv in ent.items() if kk != "egg_roll"} for k, ent in _PETS.items()},
        _ORDER_PET_POOL, "pets 品种")
    PET_POOL = list(_PET_POOL_BY_KEY.values())
    # 掷蛋规则表：源 `PET_EGG_ROLL` 是 list，导出期按 `key` 连接进品种条目 → 这里按键取回（序由声明给出）
    PET_EGG_ROLL = list(_ordered(
        {k: dict(ent["egg_roll"]) for k, ent in _PETS.items() if ent.get("egg_roll")},
        _ORDER_PET_EGG_ROLL, "pets 掷蛋规则").values())

    # ============================================================
    # ⑦ 缺域检出 —— 「静默变空洞」比报错难查得多（同 tables.py:missing_domains 口径）
    # ============================================================

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


register_view(_rebuild_view, order=40)
apply_replacements(_rebuild_view(), __package__)
