# -*- coding: utf-8 -*-
"""包内尾部长尾名门面（`content/catalog_rules.py`）—— 宿主尾部长尾名的**包内读口**。

本文件只做三件事：**读**包内域表、由域表现算**派生**量、再导出**既有读口**的结果。
数据表本体一律在 `content/{data,rules}/*.json`（编辑器可改）—— 逐名台账见 `out/DIFF_NOTES.md`。

读口纪律（与 `catalog_b143.py` / `catalog_life.py` 同款）
--------------------------------------------------------
* **只读包内数据**（`content/rules/*.json` · `content/data/*.json`）；**零宿主 import**、
  不用 `_host_attr`/`_HostMod`（宿主 `game/data` 删掉后本模块照样活）。
* 域读不到（缺文件/坏 JSON）→ 返回 `{}` / `[]` **不抛**（空表会在门禁上以「不等」现形）。
* **不改形状**：不设默认值、不改数值、不重排键（判等连键序一起比）。

三个来源
--------
① **包内域 JSON**（这是真域，编辑器可改）——
   `EFFECT_RULES`(`rules/effect_rules.json`) · `BAR_STATE_PREFIX`(`rules/game_config.json`
   `battle_rules` 组) · `FORMULA_SKELETON`(同文件 `formula_skeleton` 组) ·
   `FIELD_TIER_MULT`(同文件 `stat_templates` 组) · `DROP_POOLS`(`data/drop_pools.json`) ·
   `PLAYER_BASE_GROWTH`(`rules/panel_rules.json` 的 `base_growth` 组，**tuple 还原**) ·
   `equipment` / `gems` / `enchant` / `factions` / `chapters`（常量组域）·
   `game_config` 的 `events`/`sets`/`equip_roster`/`set_bonus_data`/`affixes`/`fishing`/
   `pets`/`props`/`races`/`daily_events`/`wild_king_data`/`instances` 组。

② **派生**——`EVENT_WEIGHT_SUM` / `EXPLORE_EGG_SUM`：真源就是
   `sum(e["weight"] for e in EXPLORE_EVENTS / EXPLORE_EGG_EVENTS)`，此处按
   `events` 域的 `source` 字段现算（`explore`=100 · `egg`=46，与真源池同源）。

③ **既有读口的结果**——`CRAFT_RECIPES` / `CRAFT_RECIPE_ALIASES` ← `catalog_life`
   （`craft` 域；条目里的 `aliases` 是导出期注入字段，真源插入序由该模块的 `_ORDER_CRAFT_RECIPES`
   声明并带集合守卫）；`FISH_COLLECT` ← `catalog_b143`（`game_config.fishing` 组）。
   同一份数据不在本模块再造一份。

⚠️ 类型还原（不做 = 静默错值/门禁报红）
--------------------------------------
* `GEM_DROP_TIER` 的值、`SUBAREA_PROPS` 的行、`WILD_KING_SPAWN_HOURS`：真源是 **tuple**，
  JSON 只有 array ⇒ 读回时还原。
* `FISH_QUALITY_WEIGHTS` 的键：真源是 **int**，JSON 只有字符串键 ⇒ 读回时还原（`_int_keys`）。
* `FORMULA_SKELETON["boss_atk_legacy"]["seg"]` / `FIELD_TIER_MULT` / `PLAYER_BASE_GROWTH
  ["linear_stats"]` / 五张 `*_STAGE_MULT`：同款 tuple 行还原（`_tupled_rows`）。
* `EXPLORE_EGG_CHANCE` 是 float：JSON 按 repr 落盘，往返精确（0.005）。
"""
from __future__ import annotations

import os

from saintess_engine.records import orders_of, set_from_domains

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

#: 域读表口（引擎 records 形状）；在 `_ORDER_*` 序声明之后建（`order=` 要用它们）
_R = None


def _read_group(domain: str, sub: str, group: str, key: str, default=None):
    """取某域里一个 **常量组** 里的某个键（域/组/键缺 → default）。

    `sub` 已由 `_R` 的域声明给 —— 读文件/缺表留痕那层机制归形状，本函数只做组内取键。
    """
    dom = getattr(_R, domain).all()
    if not isinstance(dom, dict):
        return default
    grp = dom.get(group)
    return grp.get(key, default) if isinstance(grp, dict) else default


# ============================================================
# 类型/序还原（不做 = 静默错值 or 门禁报红；与 `catalog_b143.py` 同款）
# ============================================================

def _tupled_rows(rows):
    """`list[list]` → **`tuple[tuple]`**：真源侧是 **tuple 行表**（如 `BOSS_ATK_LEGACY["seg"]` 的
    `((上限, 每级增量), …)`、`FIELD_TIER_MULT['elite']` 的 `((等级上限, 倍率), …)`），
    JSON 只有 array ⇒ 不还原 = 与真源 `type` 不等（`b14_catalog_gate.cmp_val` 报「类型不同
    list vs tuple」）。

    消费端 `for _lv, _v in seg` 对两种都成立，但**判等/入集合/切片语义**要求 tuple。
    """
    if not isinstance(rows, (list, tuple)):
        return rows
    return tuple(tuple(x) if isinstance(x, list) else x for x in rows)

def _int_keys(tbl) -> dict:
    """字符串键 → **int 键**（JSON 只有 str 键；还原不了的键**原样保留**，不静默丢）。

    `FISH_QUALITY_WEIGHTS` 的真源键是 `1/3/5/7/9`（int）—— 不还原 = `.get(3)` 恒 None。
    """
    out: dict = {}
    for k, v in (tbl or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            out[k] = v
    return out


# ============================================================
# 序声明（真源**插入序**）——**唯一源** = `content/data/key_order.json`（`key_order` 域）
# S2 ①：本文件原先内嵌的 85 行序字面量已搬进该域，「值 + 类型 + 序」与搬前逐元素对拍相等。
# 读不到即 raise（**不静默空序 / 不静默改序**）。
# ============================================================


def _order(name: str) -> list:
    """按名取包内序声明（引擎装载口 `orders_of`，落点由包内域声明派生）。"""
    return orders_of(_PKG_ROOT, name, domain="key_order")


_ORDER_EFFECT_RULES = _order("effect_rules")

# ============================================================
# 域读表口（引擎 records 形状）—— 序声明齐了才建（`order=` 要用它）
# **域元数据唯一源 = 包内 `editor/domains.json`**（S2 ②：这里只声明「我要哪些域」，
# 落点由声明的 `kind` 派生；声明缺项 / 文件缺 / 声明与磁盘不符 → 装载期报错，不静默）。
# ============================================================
_R = set_from_domains(_PKG_ROOT, (
    "game_config", "effect_rules", "drop_pools", "panel_rules",
    "events", "equipment", "gems", "enchant", "factions", "chapters",
), overrides={
    "effect_rules": {"order": _ORDER_EFFECT_RULES},   # 85 条声明序（key_order 域 effect_rules）
})


# ============================================================
# ① 包内域（真域；改数值 = 改这些 JSON）
# ============================================================
# rules/effect_rules.json（85 条，与 content/mech/params.py 读的是**同一份文件**）
# 序 = 真源插入序（域落盘是字典序 ⇒ 序不可逆，只能在此显式声明；声明与域键集不符即 raise）
EFFECT_RULES: dict = _R.effect_rules.all()

# rules/game_config.json -> battle_rules 组
BAR_STATE_PREFIX = _read_group("game_config", "rules", "battle_rules", "BAR_STATE_PREFIX")

# rules/game_config.json -> formula_skeleton 组（**全量 9 段**；宿主 game/bootstrap.py 的
# `_skeleton()` hook 供体读它。⚠️ 与 content/mech/params.py 的 FORMULA_SKELETON **不同物** ——
# 后者是引擎切片用的 2 段子集，别拿它替这个）
FORMULA_SKELETON: dict = _read_group("game_config", "rules", "formula_skeleton", "FORMULA_SKELETON", {}) or {}
if isinstance(FORMULA_SKELETON.get("boss_atk_legacy"), dict):     # ← tuple 行还原
    FORMULA_SKELETON["boss_atk_legacy"]["seg"] = _tupled_rows(
        FORMULA_SKELETON["boss_atk_legacy"].get("seg"))

# rules/game_config.json -> stat_templates 组（每档值 = tuple 行列表 → 还原）
FIELD_TIER_MULT: dict = {k: _tupled_rows(v) for k, v in (
    _read_group("game_config", "rules", "stat_templates", "FIELD_TIER_MULT", {}) or {}).items()}

# data/drop_pools.json（596 池）
DROP_POOLS: dict = _R.drop_pools.all()

# rules/panel_rules.json -> base_growth 组（+ **linear_stats 还原 tuple**）
_BASE_GROWTH: dict = _R.panel_rules.all().get("base_growth") or {}
PLAYER_BASE_GROWTH: dict = dict(_BASE_GROWTH)
if "linear_stats" in PLAYER_BASE_GROWTH:
    PLAYER_BASE_GROWTH["linear_stats"] = tuple(PLAYER_BASE_GROWTH["linear_stats"] or ())

# ============================================================
# ② 派生（由包内 events 域现算；真源 = 宿主 `game/data/events.py` 的两条 sum）
# ============================================================
_EVENTS: dict = _R.events.all()


def _weight_sum(source: str) -> int:
    """某池的权重和（域条目自带 `weight`；非 dict 条目跳过 —— 同真源只 sum 池条）。"""
    return sum(v["weight"] for v in _EVENTS.values()
               if isinstance(v, dict) and v.get("source") == source and "weight" in v)


EVENT_WEIGHT_SUM = _weight_sum("explore")   # ← sum(e["weight"] for e in EXPLORE_EVENTS)
EXPLORE_EGG_SUM = _weight_sum("egg")        # ← sum(e["weight"] for e in EXPLORE_EGG_EVENTS)


# ============================================================
# ③ 域常量（值原样；`game_config` 的组名 = 宿主源模块名）
# ============================================================
# ---- equipment 域（content/data/equipment.json · `equipment` 组 ← 宿主 game/data/equipment.py）----
# WEAPON_TYPES ← equipment.py:49（武器类型 → 可用职业）
WEAPON_TYPES: dict = _read_group("equipment", "data", "equipment", "WEAPON_TYPES", {}) or {}
# WEAPON_NAME_SUFFIX ← equipment.py:76（武器类型 → 名后缀词）
WEAPON_NAME_SUFFIX: dict = _read_group("equipment", "data", "equipment", "WEAPON_NAME_SUFFIX", {}) or {}
# EQUIP_NAME_PREFIX ← equipment.py:166（品质 → 名前缀词）
EQUIP_NAME_PREFIX: dict = _read_group("equipment", "data", "equipment", "EQUIP_NAME_PREFIX", {}) or {}
# EQUIP_PREFIX_FLAVOR ← equipment.py:207（前缀词 → 数值加成）
EQUIP_PREFIX_FLAVOR: dict = _read_group("equipment", "data", "equipment", "EQUIP_PREFIX_FLAVOR", {}) or {}
# EQUIP_NAME_SUFFIX ← equipment.py:232（部位 → 名后缀词）
EQUIP_NAME_SUFFIX: dict = _read_group("equipment", "data", "equipment", "EQUIP_NAME_SUFFIX", {}) or {}
# AFFIX_FALLBACK ← equipment.py:293（词条 → 兜底数值区间）
AFFIX_FALLBACK: dict = _read_group("equipment", "data", "equipment", "AFFIX_FALLBACK", {}) or {}
# AFFIX_COUNT ← equipment.py:280（品质 → 词条条数；orange 是区间）
AFFIX_COUNT: dict = _read_group("equipment", "data", "equipment", "AFFIX_COUNT", {}) or {}

# ---- gems 域（content/data/gems.json · `gems` 组 ← 宿主 game/data/gems.py）----
# GEM_STATS ← gems.py:23（可镶嵌属性池）
GEM_STATS: list = _read_group("gems", "data", "gems", "GEM_STATS", []) or []
# GEM_ITEM_TYPE ← gems.py:21（宝石物品类型名）
GEM_ITEM_TYPE = _read_group("gems", "data", "gems", "GEM_ITEM_TYPE")
# GEM_REMOVE_COST ← gems.py:39（拆卸手续费）
GEM_REMOVE_COST = _read_group("gems", "data", "gems", "GEM_REMOVE_COST")
# GEM_DROP_RATE ← gems.py:47（怪档 → 掉落率）
GEM_DROP_RATE: dict = _read_group("gems", "data", "gems", "GEM_DROP_RATE", {}) or {}
# GEM_DROP_TIER ← gems.py:54（怪档 → 掉落阶区间）—— 值是 **tuple** ⇒ 还原
GEM_DROP_TIER: dict = {k: tuple(v) for k, v in (
    _read_group("gems", "data", "gems", "GEM_DROP_TIER", {}) or {}).items()}
# GEM_BOSS_FIXED ← gems.py:62（指定 Boss → 必掉宝石属性）
GEM_BOSS_FIXED: dict = _read_group("gems", "data", "gems", "GEM_BOSS_FIXED", {}) or {}

# ---- enchant 域（content/data/enchant.json · `enchant` 组 ← 宿主 game/data/enchant.py）----
# ENCHANT_MAX_VALUE ← enchant.py:138（词条 → 单次附魔上限）
ENCHANT_MAX_VALUE: dict = _read_group("enchant", "data", "enchant", "ENCHANT_MAX_VALUE", {}) or {}

# ---- factions 域（content/data/factions.json · `factions` 组 ← 宿主 game/data/factions.py）----
# FACTION_SHOP ← factions.py:34（阵营 → 声望商店货单）
FACTION_SHOP: dict = _read_group("factions", "data", "factions", "FACTION_SHOP", {}) or {}
# FACTION_CAMPS ← factions.py:76（阵营营地：名 / 图标 / 说明）
FACTION_CAMPS: dict = _read_group("factions", "data", "factions", "FACTION_CAMPS", {}) or {}
# FACTION_CAMP_OPEN_LV ← factions.py:88（营地解锁等级）
FACTION_CAMP_OPEN_LV = _read_group("factions", "data", "factions", "FACTION_CAMP_OPEN_LV")
# FACTION_CAMP_SWITCH_COOLDOWN ← factions.py:95（换阵营冷却秒）
FACTION_CAMP_SWITCH_COOLDOWN = _read_group("factions", "data", "factions", "FACTION_CAMP_SWITCH_COOLDOWN")
# FACTION_CAMP_DAILY_TASKS ← factions.py:116（营地日常任务）
FACTION_CAMP_DAILY_TASKS: list = _read_group("factions", "data", "factions", "FACTION_CAMP_DAILY_TASKS", []) or []
# FACTION_CAMP_DAILY_LIMIT ← factions.py:92（每日日常上限）
FACTION_CAMP_DAILY_LIMIT = _read_group("factions", "data", "factions", "FACTION_CAMP_DAILY_LIMIT")
# FACTION_CAMP_SHOP ← factions.py:101（营地商店货单）
FACTION_CAMP_SHOP: list = _read_group("factions", "data", "factions", "FACTION_CAMP_SHOP", []) or []

# ---- chapters 域（content/data/chapters.json · `quest_add_v140` 组）----
# SUPPLY_BOX ← 宿主 game/data/quest_add_v140.py:121（每日补给箱 3 档）
SUPPLY_BOX: list = _read_group("chapters", "data", "quest_add_v140", "SUPPLY_BOX", []) or []

# ---- game_config 域 · events 组（宿主 game/data/events.py）----
# EXPLORE_EGG_CHANCE ← events.py:1458（探索彩蛋 0.5% 独立触发闸门）
EXPLORE_EGG_CHANCE = _read_group("game_config", "rules", "events", "EXPLORE_EGG_CHANCE")

# ---- game_config 域 · sets 组（宿主 game/data/sets.py）----
# SET_THEMES ← sets.py:3（品质 → 套装主题词）
SET_THEMES: dict = _read_group("game_config", "rules", "sets", "SET_THEMES", {}) or {}
# SET_CHANCE ← sets.py:24（品质 → 套装出现概率）
SET_CHANCE: dict = _read_group("game_config", "rules", "sets", "SET_CHANCE", {}) or {}

# ---- game_config 域 · equip_roster 组（宿主 game/data/equip_roster.py）----
# SERIES_SETS ← equip_roster.py:510（系列 → 系列套名）
SERIES_SETS: dict = _read_group("game_config", "rules", "equip_roster", "SERIES_SETS", {}) or {}

# ---- game_config 域 · pois 组（宿主 game/data/pois.py）----
# NOTE_POOL ← pois.py:352（note POI 线索文案池）
NOTE_POOL: list = _read_group("game_config", "rules", "pois", "NOTE_POOL", []) or []
# RUNE_POOL ← pois.py:359（rune POI 图鉴线索文案池）
RUNE_POOL: list = _read_group("game_config", "rules", "pois", "RUNE_POOL", []) or []
# SIGHT_POOL ← pois.py:367（sight POI 风景文案池）
SIGHT_POOL: list = _read_group("game_config", "rules", "pois", "SIGHT_POOL", []) or []

# ---- game_config 域 · set_bonus_data 组（宿主 game/data/set_bonus_data.py）----
# SERIES_SET_BONUS ← set_bonus_data.py:35（系列 → 套装件数 → 加成）
SERIES_SET_BONUS: dict = _read_group("game_config", "rules", "set_bonus_data", "SERIES_SET_BONUS", {}) or {}

# ---- game_config 域 · affixes 组（宿主 game/data/affixes.py）----
# AFFIX_AFFINITY_POOLS ← affixes.py:529（锻造倾向 → 词条池）
AFFIX_AFFINITY_POOLS: dict = _read_group("game_config", "rules", "affixes", "AFFIX_AFFINITY_POOLS", {}) or {}
# SERIES_FIXED_AFFIX ← affixes.py:1028（系列 / 装备名 → 固定词条）
SERIES_FIXED_AFFIX: dict = _read_group("game_config", "rules", "affixes", "SERIES_FIXED_AFFIX", {}) or {}

# ---- game_config 域 · fishing 组（宿主 game/data/fishing.py）----
# FISH_QUALITY_WEIGHTS ← fishing.py:73（钓点等级 → 品质权重）—— 键是 **int** ⇒ 还原
FISH_QUALITY_WEIGHTS: dict = _int_keys(
    _read_group("game_config", "rules", "fishing", "FISH_QUALITY_WEIGHTS", {}) or {})

# ---- game_config 域 · pets 组（宿主 game/data/pets.py）----
# _PET_EGG_PRICE ← pets.py:133（品质 → 宠物蛋价）
_PET_EGG_PRICE: dict = _read_group("game_config", "rules", "pets", "_PET_EGG_PRICE", {}) or {}
# PET_EXP_GRADE ← pets.py:194（品质 → 经验加成曲线）
PET_EXP_GRADE: dict = _read_group("game_config", "rules", "pets", "PET_EXP_GRADE", {}) or {}

# ---- game_config 域 · props 组（宿主 game/data/props.py）----
# SUBAREA_PROPS ← props.py:606（`地图:子区域` → 落点道具行）—— 行内是 **tuple** ⇒ 还原
SUBAREA_PROPS: dict = {
    k: [tuple(x) if isinstance(x, list) else x for x in (v or [])]
    for k, v in (_read_group("game_config", "rules", "props", "SUBAREA_PROPS", {}) or {}).items()}

# ---- game_config 域 · races 组（宿主 game/data/races.py）----
# RACE_ATTACK_MULT ← races.py:115（性格 → 攻击系数）
RACE_ATTACK_MULT: dict = _read_group("game_config", "rules", "races", "RACE_ATTACK_MULT", {}) or {}

# ---- game_config 域 · daily_events 组（宿主 game/data/daily_events.py）----
# DAILY_MAP_EVENTS ← daily_events.py:18（野外图 → 今日奇遇变体）
DAILY_MAP_EVENTS: dict = _read_group("game_config", "rules", "daily_events", "DAILY_MAP_EVENTS", {}) or {}

# ---- game_config 域 · wild_king_data 组（宿主 game/data/wild_king_data.py）----
# WILD_KING_CHEST_TIERS ← wild_king_data.py:145（档位 → 宝箱奖励）
WILD_KING_CHEST_TIERS: dict = _read_group(
    "game_config", "rules", "wild_king_data", "WILD_KING_CHEST_TIERS", {}) or {}
# WILD_KING_GLOBAL_LIMIT ← wild_king_data.py:34（全局同时存在上限）
WILD_KING_GLOBAL_LIMIT = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_GLOBAL_LIMIT")
# WILD_KING_LIFETIME_SEC ← wild_king_data.py:36（存活秒）
WILD_KING_LIFETIME_SEC = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_LIFETIME_SEC")
# WILD_KING_LOOT_PRIORITY_SEC ← wild_king_data.py:38（发现者优先拾取秒）
WILD_KING_LOOT_PRIORITY_SEC = _read_group(
    "game_config", "rules", "wild_king_data", "WILD_KING_LOOT_PRIORITY_SEC")
# WILD_KING_MAPS ← wild_king_data.py:130（候选野外图）
WILD_KING_MAPS: list = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_MAPS", []) or []
# WILD_KING_NO_KILL_EXTRA ← wild_king_data.py:45（未击杀者的额外惩罚）
WILD_KING_NO_KILL_EXTRA = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_NO_KILL_EXTRA")
# WILD_KING_PERIODS ← wild_king_data.py:26（时段表）
WILD_KING_PERIODS: list = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_PERIODS", []) or []
# WILD_KING_PER_DAY_LIMIT ← wild_king_data.py:41（每日上限）
WILD_KING_PER_DAY_LIMIT = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_PER_DAY_LIMIT")
# WILD_KING_PER_PERIOD_LIMIT ← wild_king_data.py:40（每时段上限）
WILD_KING_PER_PERIOD_LIMIT = _read_group(
    "game_config", "rules", "wild_king_data", "WILD_KING_PER_PERIOD_LIMIT")
# WILD_KING_PITY_PERIODS ← wild_king_data.py:43（保底时段数）
WILD_KING_PITY_PERIODS = _read_group("game_config", "rules", "wild_king_data", "WILD_KING_PITY_PERIODS")
# WILD_KING_SPAWN_HOURS ← wild_king_data.py:47（刷新小时）—— 值是 **tuple** ⇒ 还原
WILD_KING_SPAWN_HOURS: tuple = tuple(
    _read_group("game_config", "rules", "wild_king_data", "WILD_KING_SPAWN_HOURS", ()) or ())
# WILD_KING_PITY_VOUCHER_NAME ← wild_king_data.py:184（保底券名）
WILD_KING_PITY_VOUCHER_NAME = _read_group(
    "game_config", "rules", "wild_king_data", "WILD_KING_PITY_VOUCHER_NAME")

# ---- game_config 域 · instances 组（宿主 game/data/instances.py）----
# INSTANCE_BOSS_EQUIP_DROP ← instances.py:3686（副本 → Boss 装备掉落规则）
INSTANCE_BOSS_EQUIP_DROP: dict = _read_group(
    "game_config", "rules", "instances", "INSTANCE_BOSS_EQUIP_DROP", {}) or {}

# ---- game_config 域 · battle_config 组（宿主 game/data/battle_config.py）----
# ENEMY_BAR_CFG ← battle_config.py（敌方架势条配置；消费点 tests/test_numeric_bar_decay.py）
ENEMY_BAR_CFG: dict = _read_group("game_config", "rules", "battle_config", "ENEMY_BAR_CFG")

# ---- 既有读口的结果（同一份数据不在本模块再造一份）----
# `craft` 域（content/data/craft.json）：条目带导出期注入的 `aliases`；真源插入序由
# `catalog_life` 的 `_ORDER_CRAFT_RECIPES` 声明并带集合守卫 ⇒ 直接取那份结果。
from .catalog_life import CRAFT_RECIPES, CRAFT_RECIPE_ALIASES      # noqa: E402
# `game_config.fishing` 组（content/rules/game_config.json）
from .catalog_b143 import FISH_COLLECT                             # noqa: E402


# ============================================================
# ④ 遗留登记 —— 本模块的数据名全部有域（本格为空 = 无需登记）
# ============================================================
NOT_YET_DOMAINED: tuple = ()


# =============================================================================
# B14 收口追加（主 agent 2026-09-14）：`game_config.stat_templates` 13 键
#   ← `content/stats.py:89-105` 的模块级取件（真源 `game/data/stat_templates.py`）
#   删宿主 `game/data` 的**唯一 import 期阻塞**就是这一组；`FIELD_TIER_MULT` 本模块已有。
# =============================================================================
EQUIP_SLOT_BASE: dict = _read_group("game_config", "rules", "stat_templates", "EQUIP_SLOT_BASE", {}) or {}
EQUIP_SLOT_SCALING: dict = _read_group("game_config", "rules", "stat_templates", "EQUIP_SLOT_SCALING", {}) or {}
MONSTER_EXP_BASE: dict = _read_group("game_config", "rules", "stat_templates", "MONSTER_EXP_BASE", {}) or {}
MONSTER_GOLD_BASE: dict = _read_group("game_config", "rules", "stat_templates", "MONSTER_GOLD_BASE", {}) or {}
MONSTER_ROLE_BASE: dict = _read_group("game_config", "rules", "stat_templates", "MONSTER_ROLE_BASE", {}) or {}
MONSTER_ROLE_GROWTH: dict = _read_group("game_config", "rules", "stat_templates", "MONSTER_ROLE_GROWTH", {}) or {}
# ⚠️ 真源是 list[tuple]（JSON 落盘只剩 list）→ 必须 `_tupled_rows` 还原，否则类型不等
NORMAL_HP_STAGE_MULT = _tupled_rows(_read_group("game_config", "rules", "stat_templates", "NORMAL_HP_STAGE_MULT", {}) or {})
# ⚠️ 真源是 list[tuple]（JSON 落盘只剩 list）→ 必须 `_tupled_rows` 还原，否则类型不等
BOSS_ATK_STAGE_MULT = _tupled_rows(_read_group("game_config", "rules", "stat_templates", "BOSS_ATK_STAGE_MULT", {}) or {})
# ⚠️ 真源是 list[tuple]（JSON 落盘只剩 list）→ 必须 `_tupled_rows` 还原，否则类型不等
INSTANCE_BOSS_ATK_STAGE_MULT = _tupled_rows(_read_group("game_config", "rules", "stat_templates", "INSTANCE_BOSS_ATK_STAGE_MULT", {}) or {})
# ⚠️ 真源是 list[tuple]（JSON 落盘只剩 list）→ 必须 `_tupled_rows` 还原，否则类型不等
HP_STAGE_MULT = _tupled_rows(_read_group("game_config", "rules", "stat_templates", "HP_STAGE_MULT", {}) or {})
# ⚠️ 真源是 list[tuple]（JSON 落盘只剩 list）→ 必须 `_tupled_rows` 还原，否则类型不等
ATK_STAGE_MULT = _tupled_rows(_read_group("game_config", "rules", "stat_templates", "ATK_STAGE_MULT", {}) or {})
MONSTER_ROLE_MODS: dict = _read_group("game_config", "rules", "stat_templates", "MONSTER_ROLE_MODS", {}) or {}


__all__ = [
    "EFFECT_RULES", "BAR_STATE_PREFIX", "FORMULA_SKELETON", "FIELD_TIER_MULT",
    "DROP_POOLS", "PLAYER_BASE_GROWTH",
    "EVENT_WEIGHT_SUM", "EXPLORE_EGG_SUM",
    "EXPLORE_EGG_CHANCE",
    "WEAPON_TYPES",
    "WEAPON_NAME_SUFFIX",
    "EQUIP_NAME_PREFIX",
    "EQUIP_PREFIX_FLAVOR",
    "EQUIP_NAME_SUFFIX",
    "SET_THEMES",
    "SET_CHANCE",
    "SERIES_SETS",
    "NOTE_POOL",
    "RUNE_POOL",
    "SIGHT_POOL",
    "DAILY_MAP_EVENTS",
    "SUPPLY_BOX",
    "NOT_YET_DOMAINED", "missing_domains",
    # ---- B14 收口追加（主 agent 2026-09-14）----
    "EQUIP_SLOT_BASE",
    "EQUIP_SLOT_SCALING",
    "MONSTER_EXP_BASE",
    "MONSTER_GOLD_BASE",
    "MONSTER_ROLE_BASE",
    "MONSTER_ROLE_GROWTH",
    "NORMAL_HP_STAGE_MULT",
    "BOSS_ATK_STAGE_MULT",
    "INSTANCE_BOSS_ATK_STAGE_MULT",
    "HP_STAGE_MULT",
    "ATK_STAGE_MULT",
    "MONSTER_ROLE_MODS",
    # ---- B16-W11 追加（2026-09-14）----
    "GEM_STATS",
    "GEM_ITEM_TYPE",
    "GEM_REMOVE_COST",
    "GEM_DROP_RATE",
    "GEM_DROP_TIER",
    "GEM_BOSS_FIXED",
    "ENCHANT_MAX_VALUE",
    "AFFIX_FALLBACK",
    "AFFIX_COUNT",
    "SERIES_FIXED_AFFIX",
    "FISH_QUALITY_WEIGHTS",
    "SERIES_SET_BONUS",
    "RACE_ATTACK_MULT",
    "SUBAREA_PROPS",
    "FACTION_SHOP",
    "FACTION_CAMPS",
    "FACTION_CAMP_OPEN_LV",
    "FACTION_CAMP_SWITCH_COOLDOWN",
    "FACTION_CAMP_DAILY_TASKS",
    "FACTION_CAMP_DAILY_LIMIT",
    "FACTION_CAMP_SHOP",
    "WILD_KING_CHEST_TIERS",
    "WILD_KING_GLOBAL_LIMIT",
    "WILD_KING_LIFETIME_SEC",
    "WILD_KING_LOOT_PRIORITY_SEC",
    "WILD_KING_MAPS",
    "WILD_KING_NO_KILL_EXTRA",
    "WILD_KING_PERIODS",
    "WILD_KING_PER_DAY_LIMIT",
    "WILD_KING_PER_PERIOD_LIMIT",
    "WILD_KING_PITY_PERIODS",
    # ---- B15b 追加（2026-09-14）：副业/重锻**宿主函数**进包 ----
    #   真源 `game/data/prof_config.py:86/:108` · `refine_exclusive.py:160`（宿主 data 层已删）。
    #   函数本体在 `content/prof_config.py` / `content/refine_exclusive.py`（逐字端口），
    #   此处只**再导出** → 宿主 `game/content.py` 的 `catalog_*` 聚合循环收回 `C.<名>`（零宿主改动）。
    #   ⚠️ 函数名不是数据名 → **不进** `NOT_YET_DOMAINED`（那格只登记数据名）。
    "price_band",
    "gather_map_min_lv",
    "merge_into",
]


def missing_domains() -> list:
    """本模块里**包内无域**（值只能随代码走、编辑器改不到）的名字 —— 供报告登记。"""
    return [n for n in NOT_YET_DOMAINED if globals().get(n) in (None, {}, [], ())]


# =============================================================================
# B15b 追加（2026-09-14）：副业/重锻**宿主函数**进包 —— 只做**再导出**
#   背景：宿主 `game/data/*.py` 删除后，`game/data/prof_config.py` 的 `price_band()` /
#   `gather_map_min_lv()` 与 `game/data/refine_exclusive.py` 的 `merge_into()` 在宿主聚合层
#   `C.<名>` 上**没有对象**了（`C.gather_map_min_lv` 实测 AttributeError，红测试
#   `tests/test_v87_14_spatial_links.py`）。函数本体**逐字端口**在：
#       content/prof_config.py:48      price_band        ← 真源 game/data/prof_config.py:86
#       content/prof_config.py:54      gather_map_min_lv ← 真源 game/data/prof_config.py:108
#       content/refine_exclusive.py:29 merge_into        ← 真源 game/data/refine_exclusive.py:160
#   本文件把三个名字放进 `dir()` 面 ⇒ 宿主 `game/content.py` 的 `catalog_*` 聚合循环
#   （`globals().setdefault(名, getattr(模块, 名))`，callable 即收）自动收回 `C.<名>`
#   → **宿主侧零改动**（原「缺名」红项清零；等价性见 `overnight/W-B15b.md`）。
#   依赖常量不重抄：`PRICE_BAND` ← `content/config.py:const("prof_config", …)`（域 game_config）；
#   `REFINE_EXCLUSIVE_RECIPES` ← `catalog_items`（域 game_config·**新组** refine_exclusive）。
# =============================================================================
from .prof_config import gather_map_min_lv, price_band  # noqa: F401
from .refine_exclusive import merge_into  # noqa: F401
