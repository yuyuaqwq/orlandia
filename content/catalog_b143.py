# -*- coding: utf-8 -*-
"""B14-3 收口门面（`content/catalog_b143.py`）—— 42 个「缺口名」的**包内等价物**。

背景
----
B14-3_BRIEF §1 列的 46 个缺口名（42 个数据名 + 派生名 `ALL_WILD` + `PERIOD_CN` + 文档占位
`X`/`XXX`）过去「包内既无门面也无域可依」＝ 删 `game/data` 的前置阻塞项。本线把它们逐个安家：

* 新域 6 个：`equipment` · `factions` · `enchant` · `poi_pools` · `chapters` · `gems`
  （`scripts/export_domains/b14_3_gaps.py`，表组形状「一条 = 一个源模块的常量组」）；
* 扩既有域 2 个：`guild` 加一行 `config`（`GUILD_CONFIG`）· `shop` 加一行 `honor_shop`
  （`HONOR_SHOP`，行内 `ranks` 装编号表）；
* 扩既有域 `game_config` 9 组常量：pets / maps / world / runes / affixes / fishing / pois /
  hidden_monsters / instance_investigation（判据见 `schemas/game_config.schema.json` 逐组说明）。
* 剩下 4 个不是数据缺口：`ALL_WILD`（派生式，真源 `game/core/wild.py:26`，包内已有
  `content/wild.py:_ALL_WILD()`）· `PERIOD_CN`（真源就是**包内** `content/time_weather.py:27`）·
  `X` / `XXX`（`content/economy_host.py:65` / `quests_flow.py:14` / `travel.py:15` 的**文档占位**，
  不是读点）。

本模块的纪律
------------
* 只读包内域文件（`content/{data,rules}/*.json`），**不 import 宿主**、不用 `_HostMod`。
* 域读不到（缺文件/坏 JSON/空表）→ 返回 `{}` **不抛**（空表会在门禁上以「不等」现形）；
  域在、但键集与序声明不符 → `raise`（防「源改了、门面静默改序」）。
* **两处类型还原**（不做 = 静默错值）：
  ① **外层键序**：域 JSON 是字典序，真源是插入序 —— 逐张声明在 `content/data/key_order.json`
     （形状见该域 schema），本文件按名取用（`_order()`）；
  ② **int 键**：`GEM_TIERS` / `GEM_TIER_NAMES` / `RUNE_LEVEL_ROMAN` / `HONOR_SHOP` 的键源侧是
     int，JSON 只有字符串键 → 不还原 = `.get(3)` 恒 None、`sorted()` 乱序、`tier + 1` 取不到。

逐名台账（名 → 域 → 宿主真源）
------------------------------
| 名字 | 域（落点） | 宿主真源 |
|---|---|---|
| `QUALITY` `EQUIP_SLOTS` `WEAPON_FLAVOR` `QUALITY_ORDER` | `equipment`（data） | `game/data/equipment.py:13/3/127/41` |
| `FACTIONS` `FACTION_ORDER` `AREA_FACTION` `CHRONICLES` `REPUTATION_TIERS` | `factions`（data） | `game/data/factions.py:8/18/123/165/20` |
| `ENCHANT_RECIPES` `ENCHANT_SLOTS` `ENCHANT_CRIT_CHANCE` | `enchant`（data） | `game/data/enchant.py:9/3/134` |
| `WISH_POOL` `CAMPFIRE_FOOD_POOL` `HERB_POOL` | `poi_pools`（data） | `game/data/poi_pools.py:10/15/18` |
| `CHAPTER_PACK` | `chapters`（data） | `game/data/quest_add_v140.py:106` |
| `GEM_TIERS` `GEM_TIER_NAMES` `GEM_SOCKETS` `GEM_DRILL` `GEM_LEGENDARY_EFFECTS` `RUNE_REMOVE_COST` | `gems`（data） | `game/data/gems.py:7/19/25/33/42/40` |
| `PET_MAX_LEVEL` `PET_SKILL_UNLOCK_LV` | `game_config.pets` | `game/data/pets.py:190/192` |
| `MAP_CONNECTIONS` `LEGACY_MAP_ALIAS` `HIDDEN_MAP_UNLOCK` | `game_config.maps` | `game/data/maps.py:4224/4352/4343` |
| `WORLD_EVENT_POOL` `AUCTION_POOL` `WORLD_BOSS_POOL` | `game_config.world` | `game/data/world.py:8/110/123` |
| `RUNE_CRAFT_SHARDS` `RUNE_DROP` `RUNE_LEVEL_ROMAN` | `game_config.runes` | `game/data/runes.py:304/247/272` |
| `AFFIX_AFFINITY_CN` `AFFIX_POOL_BY_QUALITY` | `game_config.affixes` | `game/data/affixes.py:540/487` |
| `FISH_COLLECT` `FISH_EXP` | `game_config.fishing` | `game/data/fishing.py:193/83` |
| `POIS` | `game_config.pois` | `game/data/pois.py:9`（83 条**定义**；落点表在 `pois` 域） |
| `HIDDEN_MONSTERS` | `game_config.hidden_monsters` | `game/data/hidden_monsters.py:18` |
| `INVESTIGATE_COLLECT_SAMPLES` | `game_config.instance_investigation` | `game/data/instance_investigation.py:47` |
| `GUILD_CONFIG` | `guild.config` | `game/data/guild.py:3` |
| `HONOR_SHOP` | `shop.honor_shop.ranks` | `game/data/honor_shop.py:11`（**int 键**） |

**本文件是新增文件**（既有 `catalog_{space,items,quests,life,core}.py` 一行未改）—— 并行期
把「42 个名字」的交付面收在一个文件里，避免与 B14-2 八条线抢共享文件。谁切读点谁 import：
`from . import catalog_b143 as _b143`（或 `from .catalog_b143 import QUALITY, EQUIP_SLOTS`）。
"""
from __future__ import annotations

import os

from saintess_engine.records import RecordsSet

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读域文件 / 缺表留痕（`missing`）收进引擎 records 形状的域声明。
# 本文件的 `_int_keys` / `_ordered` 作用在**嵌套常量组**上（`_R.<域>.get("<组>")` 之后）：
# 形状的 `key_type` / `order` 只作用于域顶层键，组内键型与组内键序覆盖不到 ⇒ 仍由本文件还原
# （序声明按名取 `key_order` 域，见 out/DIFF_NOTES.md §C）。
_R = RecordsSet(_PKG_ROOT, {
    "game_config": {"sub": "content/rules"},
    "equipment":   {"sub": "content/data"},
    "factions":    {"sub": "content/data"},
    "enchant":     {"sub": "content/data"},
    "poi_pools":   {"sub": "content/data"},
    "chapters":    {"sub": "content/data"},
    "gems":        {"sub": "content/data"},
    "guild":       {"sub": "content/data"},
    "shop":        {"sub": "content/data"},
    "key_order":   {"sub": "content/data"},
})


def _missing(table) -> bool:
    return not isinstance(table, dict) or not table


def _int_keys(tbl) -> dict:
    """字符串键 → int 键（非整数键**原样保留**，不静默丢）。"""
    out: dict = {}
    for k, v in (tbl or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            out[k] = v
    return out


def _num_sorted(tbl) -> dict:
    """int 键表 → 按**数值升序**（JSON 是字典序：`"10" < "2"` ⇒ 不排序 = 阶位/等级乱序）。"""
    ints = {k: v for k, v in (tbl or {}).items() if isinstance(k, int) and not isinstance(k, bool)}
    rest = {k: v for k, v in (tbl or {}).items() if k not in ints}
    return {**{k: ints[k] for k in sorted(ints)}, **rest}


def _ordered(tbl, order, where: str):
    """按**声明序**排外层键（域是字典序，真源是插入序）。域读不到 → `{}` 不抛；
    域在但键集与声明不一致 → `raise`（防「源改了、门面静默改序」）。"""
    if _missing(tbl):
        return {}
    keys = list(order)
    if len(set(keys)) != len(keys):
        raise ValueError(f"catalog_b143：{where} 的序声明有重复键 —— 拒绝静默取首个")
    have = set(tbl)
    miss = [k for k in keys if k not in have]
    extra = [k for k in have if k not in set(keys)]
    if miss or extra:
        raise ValueError(
            "catalog_b143：%s 域与序声明不一致（域缺 %d / 声明缺 %d）—— 请同步 "
            "content/data/key_order.json 的对应条目。域缺 %s … 未声明 %s …"
            % (where, len(miss), len(extra), miss[:5], sorted(extra)[:5]))
    return {k: tbl[k] for k in keys}


def missing_domains() -> list:
    """本模块要用的域里，哪几张读不到（缺文件 / 坏 JSON / 空表）。"""
    out = []
    for name, sub, path in _REQUIRED:
        if not getattr(_R, name).get(path):
            out.append(f"{sub}/{name}:{path}")
    return out


def _tupled_rows(rows):
    """`list[tuple]` 还原：源侧是 **tuple 的行**（如 `REPUTATION_TIERS` 的 `(下限, 档名)`），
    JSON 只有 array ⇒ 不还原 = 与真源 `type` 不等（B14 门禁 `cmp_val` 报「类型不同 list vs tuple」）。
    消费端 `for _t, _n in …` 对两种都成立，但**判等/入集合**需要 tuple。"""
    if not isinstance(rows, list):
        return rows
    return [tuple(x) if isinstance(x, list) else x for x in rows]


# ============================================================
# ① 序声明（`content/data/key_order.json`：本模块 26 条 / 443 键，按名取用）
# ============================================================
_ORDERS: dict = _R.key_order.all()


def _order(name: str):
    """按名取键序声明（`key_order` 域）—— 缺条目 / 形状不对 → raise（不静默当空序）。"""
    ent = _ORDERS.get(name)
    keys = ent.get("keys") if isinstance(ent, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ValueError(
            "key_order：读不到 %r 的键序声明（域缺该条目，或形状不是 {keys: [...]}）"
            "—— 序读不到就不许静默改成空表" % (name,))
    return keys


# ============================================================
# ② 42 个名字（域 → 值；含两处类型还原）
# ============================================================
_CFG = _R.game_config.all()


def _grp(group: str) -> dict:
    """`game_config` 的一组常量（缺组 → `{}`）。"""
    g = _CFG.get(group)
    return g if isinstance(g, dict) else {}

PET_MAX_LEVEL = _grp("pets").get("PET_MAX_LEVEL")
PET_SKILL_UNLOCK_LV = _grp("pets").get("PET_SKILL_UNLOCK_LV")
MAP_CONNECTIONS = _ordered((_grp("maps").get("MAP_CONNECTIONS") if isinstance(_grp("maps").get("MAP_CONNECTIONS"), dict) else {}), _order("map_connections"), "game_config.maps")
LEGACY_MAP_ALIAS = _ordered((_grp("maps").get("LEGACY_MAP_ALIAS") if isinstance(_grp("maps").get("LEGACY_MAP_ALIAS"), dict) else {}), _order("legacy_map_alias"), "game_config.maps")
HIDDEN_MAP_UNLOCK = _ordered((_grp("maps").get("HIDDEN_MAP_UNLOCK") if isinstance(_grp("maps").get("HIDDEN_MAP_UNLOCK"), dict) else {}), _order("hidden_map_unlock"), "game_config.maps")
WORLD_EVENT_POOL = _grp("world").get("WORLD_EVENT_POOL")
AUCTION_POOL = _grp("world").get("AUCTION_POOL")
WORLD_BOSS_POOL = _grp("world").get("WORLD_BOSS_POOL")
RUNE_CRAFT_SHARDS = _ordered((_grp("runes").get("RUNE_CRAFT_SHARDS") if isinstance(_grp("runes").get("RUNE_CRAFT_SHARDS"), dict) else {}), _order("rune_craft_shards"), "game_config.runes")
RUNE_DROP = _ordered((_grp("runes").get("RUNE_DROP") if isinstance(_grp("runes").get("RUNE_DROP"), dict) else {}), _order("rune_drop"), "game_config.runes")
RUNE_LEVEL_ROMAN = _num_sorted(_ordered(_int_keys((_grp("runes").get("RUNE_LEVEL_ROMAN") if isinstance(_grp("runes").get("RUNE_LEVEL_ROMAN"), dict) else {})), _order("rune_level_roman"), "game_config.runes"))
AFFIX_AFFINITY_CN = _ordered((_grp("affixes").get("AFFIX_AFFINITY_CN") if isinstance(_grp("affixes").get("AFFIX_AFFINITY_CN"), dict) else {}), _order("affix_affinity_cn"), "game_config.affixes")
AFFIX_POOL_BY_QUALITY = _ordered((_grp("affixes").get("AFFIX_POOL_BY_QUALITY") if isinstance(_grp("affixes").get("AFFIX_POOL_BY_QUALITY"), dict) else {}), _order("affix_pool_by_quality"), "game_config.affixes")
FISH_COLLECT = _grp("fishing").get("FISH_COLLECT")
FISH_EXP = _ordered((_grp("fishing").get("FISH_EXP") if isinstance(_grp("fishing").get("FISH_EXP"), dict) else {}), _order("fish_exp"), "game_config.fishing")
POIS = _ordered((_grp("pois").get("POIS") if isinstance(_grp("pois").get("POIS"), dict) else {}), _order("pois"), "game_config.pois")
HIDDEN_MONSTERS = _ordered((_grp("hidden_monsters").get("HIDDEN_MONSTERS") if isinstance(_grp("hidden_monsters").get("HIDDEN_MONSTERS"), dict) else {}), _order("hidden_monsters"), "game_config.hidden_monsters")
INVESTIGATE_COLLECT_SAMPLES = _grp("instance_investigation").get("INVESTIGATE_COLLECT_SAMPLES")
QUALITY = _ordered((_R.equipment.get("equipment", {}).get("QUALITY") if isinstance(_R.equipment.get("equipment", {}).get("QUALITY"), dict) else {}), _order("quality"), "equipment")
EQUIP_SLOTS = _ordered((_R.equipment.get("equipment", {}).get("EQUIP_SLOTS") if isinstance(_R.equipment.get("equipment", {}).get("EQUIP_SLOTS"), dict) else {}), _order("equip_slots"), "equipment")
WEAPON_FLAVOR = _ordered((_R.equipment.get("equipment", {}).get("WEAPON_FLAVOR") if isinstance(_R.equipment.get("equipment", {}).get("WEAPON_FLAVOR"), dict) else {}), _order("weapon_flavor"), "equipment")
QUALITY_ORDER = _R.equipment.get("equipment", {}).get("QUALITY_ORDER")
FACTIONS = _ordered((_R.factions.get("factions", {}).get("FACTIONS") if isinstance(_R.factions.get("factions", {}).get("FACTIONS"), dict) else {}), _order("factions"), "factions")
FACTION_ORDER = _R.factions.get("factions", {}).get("FACTION_ORDER")
AREA_FACTION = _ordered((_R.factions.get("factions", {}).get("AREA_FACTION") if isinstance(_R.factions.get("factions", {}).get("AREA_FACTION"), dict) else {}), _order("area_faction"), "factions")
CHRONICLES = _R.factions.get("factions", {}).get("CHRONICLES")
REPUTATION_TIERS = _tupled_rows(_R.factions.get("factions", {}).get("REPUTATION_TIERS"))
ENCHANT_RECIPES = _ordered((_R.enchant.get("enchant", {}).get("ENCHANT_RECIPES") if isinstance(_R.enchant.get("enchant", {}).get("ENCHANT_RECIPES"), dict) else {}), _order("enchant_recipes"), "enchant")
ENCHANT_SLOTS = _ordered((_R.enchant.get("enchant", {}).get("ENCHANT_SLOTS") if isinstance(_R.enchant.get("enchant", {}).get("ENCHANT_SLOTS"), dict) else {}), _order("enchant_slots"), "enchant")
ENCHANT_CRIT_CHANCE = _R.enchant.get("enchant", {}).get("ENCHANT_CRIT_CHANCE")
WISH_POOL = _R.poi_pools.get("poi_pools", {}).get("WISH_POOL")
CAMPFIRE_FOOD_POOL = _R.poi_pools.get("poi_pools", {}).get("CAMPFIRE_FOOD_POOL")
HERB_POOL = _R.poi_pools.get("poi_pools", {}).get("HERB_POOL")
CHAPTER_PACK = _R.chapters.get("quest_add_v140", {}).get("CHAPTER_PACK")
GEM_TIERS = _num_sorted(_ordered(_int_keys((_R.gems.get("gems", {}).get("GEM_TIERS") if isinstance(_R.gems.get("gems", {}).get("GEM_TIERS"), dict) else {})), _order("gem_tiers"), "gems"))
GEM_TIER_NAMES = _num_sorted(_ordered(_int_keys((_R.gems.get("gems", {}).get("GEM_TIER_NAMES") if isinstance(_R.gems.get("gems", {}).get("GEM_TIER_NAMES"), dict) else {})), _order("gem_tier_names"), "gems"))
GEM_SOCKETS = _ordered((_R.gems.get("gems", {}).get("GEM_SOCKETS") if isinstance(_R.gems.get("gems", {}).get("GEM_SOCKETS"), dict) else {}), _order("gem_sockets"), "gems")
GEM_DRILL = _ordered((_R.gems.get("gems", {}).get("GEM_DRILL") if isinstance(_R.gems.get("gems", {}).get("GEM_DRILL"), dict) else {}), _order("gem_drill"), "gems")
GEM_LEGENDARY_EFFECTS = _R.gems.get("gems", {}).get("GEM_LEGENDARY_EFFECTS")
RUNE_REMOVE_COST = _R.gems.get("gems", {}).get("RUNE_REMOVE_COST")
GUILD_CONFIG = _ordered((_R.guild.get("config", {}) if isinstance(_R.guild.get("config", {}), dict) else {}), _order("guild_config"), "guild")
HONOR_SHOP = _num_sorted(_ordered(_int_keys((_R.shop.get("honor_shop", {}).get("ranks", {}) if isinstance(_R.shop.get("honor_shop", {}).get("ranks", {}), dict) else {})), _order("honor_shop"), "shop"))


_REQUIRED = (
    ("game_config", "rules", "pets"), ("game_config", "rules", "maps"),
    ("game_config", "rules", "world"), ("game_config", "rules", "runes"),
    ("game_config", "rules", "affixes"), ("game_config", "rules", "fishing"),
    ("game_config", "rules", "pois"), ("game_config", "rules", "hidden_monsters"),
    ("game_config", "rules", "instance_investigation"),
    ("equipment", "data", "equipment"), ("factions", "data", "factions"),
    ("enchant", "data", "enchant"), ("poi_pools", "data", "poi_pools"),
    ("chapters", "data", "quest_add_v140"), ("gems", "data", "gems"),
    ("guild", "data", "config"), ("shop", "data", "honor_shop"),
)

# =============================================================================
# B14 收口追加（主 agent 2026-09-14）：equipment 域 5 键
#   `WT_CN`/`QUALITY_CN` → `content/index_build.py` 的 `weapon_types`/`quality` 索引表
#   `WEAPON_DIST`/`ARMOR_FAMILY`/`ARMOR_FAMILY_ALIAS` → `content/stats.py:103-105` 模块级取件
# =============================================================================
WT_CN = (_R.equipment.get("equipment", {}).get("WT_CN") or {})
QUALITY_CN = (_R.equipment.get("equipment", {}).get("QUALITY_CN") or {})
WEAPON_DIST = (_R.equipment.get("equipment", {}).get("WEAPON_DIST") or {})
ARMOR_FAMILY = (_R.equipment.get("equipment", {}).get("ARMOR_FAMILY") or {})
ARMOR_FAMILY_ALIAS = (_R.equipment.get("equipment", {}).get("ARMOR_FAMILY_ALIAS") or {})


# =============================================================================
# B14 收口追加（W12 世界/杂项线 2026-09-14）：`game_config` 的 `rules` / `mounts` 两组
#   `RULES` ← 真源 `game/data/rules.py:8`（20 条；list ⇒ JSON 数组自带序，不需要序声明）
#   `MOUNT_DROP_BOSS` / `MOUNT_DROP_ELITE` ← 真源 `game/data/mounts.py:71/70`
#     └ **序有行为**：`content/mounts.py:roll_mount_drop` 按 `.items()` 累计区间抽签 ⇒ 序声明 + 守卫
#   消费点：`content/rule_engine.py:_rules()` · `content/mounts.py:_tables()`
#   逐值 + 键序对拍（对**真源模块**，非 `C`：宿主聚合层未导出这两个名，
#   `b14_catalog_gate.py` 判「门面缺」）→ `overnight/_w12_precheck_sources.py` A/B/C/D 全 OK。
# =============================================================================
RULES = _grp("rules").get("RULES")
MOUNT_DROP_BOSS = _ordered((_grp("mounts").get("MOUNT_DROP_BOSS") if isinstance(_grp("mounts").get("MOUNT_DROP_BOSS"), dict) else {}), _order("mount_drop_boss"), "game_config.mounts")
MOUNT_DROP_ELITE = _ordered((_grp("mounts").get("MOUNT_DROP_ELITE") if isinstance(_grp("mounts").get("MOUNT_DROP_ELITE"), dict) else {}), _order("mount_drop_elite"), "game_config.mounts")


__all__ = [
    "QUALITY", "EQUIP_SLOTS", "WEAPON_FLAVOR", "QUALITY_ORDER",
    "FACTIONS", "FACTION_ORDER", "AREA_FACTION", "CHRONICLES", "REPUTATION_TIERS",
    "ENCHANT_RECIPES", "ENCHANT_SLOTS", "ENCHANT_CRIT_CHANCE",
    "WISH_POOL", "CAMPFIRE_FOOD_POOL", "HERB_POOL",
    "CHAPTER_PACK",
    "GEM_TIERS", "GEM_TIER_NAMES", "GEM_SOCKETS", "GEM_DRILL",
    "GEM_LEGENDARY_EFFECTS", "RUNE_REMOVE_COST",
    "PET_MAX_LEVEL", "PET_SKILL_UNLOCK_LV",
    "MAP_CONNECTIONS", "LEGACY_MAP_ALIAS", "HIDDEN_MAP_UNLOCK",
    "WORLD_EVENT_POOL", "AUCTION_POOL", "WORLD_BOSS_POOL",
    "RUNE_CRAFT_SHARDS", "RUNE_DROP", "RUNE_LEVEL_ROMAN",
    "AFFIX_AFFINITY_CN", "AFFIX_POOL_BY_QUALITY",
    "FISH_COLLECT", "FISH_EXP", "POIS", "HIDDEN_MONSTERS",
    "INVESTIGATE_COLLECT_SAMPLES",
    "GUILD_CONFIG", "HONOR_SHOP",
    "missing_domains",
    # ---- B14 收口追加（主 agent 2026-09-14）----
    "WT_CN",
    "QUALITY_CN",
    "WEAPON_DIST",
    "ARMOR_FAMILY",
    "ARMOR_FAMILY_ALIAS",
    # ---- B14 收口追加（W12 世界/杂项线 2026-09-14）----
    "RULES",
    "MOUNT_DROP_BOSS",
    "MOUNT_DROP_ELITE",
]

