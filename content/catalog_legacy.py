# -*- coding: utf-8 -*-
"""B14 收口·W13：**legacy 再导出 / 读口**（`content/catalog_legacy.py`）。

背景
----
`game/content.py` 由 `from .data import *` 改成「包内门面再导出」后，`C` 公开面（基线 578 名）
会丢名。本模块专治「改后丢名里**有人在读**的那批」——逐个把名字从**包内已有的家**显式再导出：

    门面/模块属性 → 域读口（`content/{data,rules}/*.json`）→ 序/类型还原读口

铁律：**数值/文案/顺序/类型逐字不变，只换「取值来源」**。不造数据、不编值：
* 每个名字都由 `overnight/_w13_gen_legacy.py` 与宿主现表（旧 `game.content` = `game/data/*` 聚合）
  逐名深比较（值 / 类型 / dict 键序 / list-tuple 长度 / float repr）后**才**写入本文件；
* `_ORDER_*` 序声明由生成器从**宿主真源**机械导出（与 `overnight/b143_gen_facade.py` 同法），不手抄；
* 逐名台账（名 → 家 → 手段）见 `overnight/_w13_catalog_legacy.md`。

形状约定（与 `content/catalog_b143.py` 一致）
--------------------------------------------
* 域读不到（缺文件 / 坏 JSON / 空表）→ 容器回 `{}`/`[]`、标量回 `None`，**不抛**；
* 域在、但键集与 `_ORDER_*` 声明不符 → `raise`（防「源改了、门面静默改序」）；
* `missing_domains()` / `missing_names()` 供报告与门禁列出没解析到的名字。

缺口（本模块**不覆盖**，需建域或改读点）
----------------------------------------
见 `GAPS` / `overnight/_w13_catalog_legacy.md`
"""
from __future__ import annotations

import os

from saintess_engine.records import apply_replacements, orders_of, placeholder, register_view, set_from_domains, update_in_place

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读域文件 / 缺表留痕（`missing`）收进引擎 records 形状的域声明。
# **域元数据唯一源 = 包内 `editor/domains.json`**（S2 ②：这里只声明「我要哪些域」，
# 落点由声明的 `kind` 派生；声明缺项 / 文件缺 / 声明与磁盘不符 → 装载期报错，不静默）。
# `_ordered` 作用在**派生表 / 合表**上（`_MAPS_DOM` 的 `links`、`content.shop_stock` 再导出、…），
# 形状的 `order` 覆盖的是域顶层键集 ⇒ 按铁律 4 原样保留（见 out/DIFF_NOTES.md §C）。
_R = set_from_domains(_PKG_ROOT, ("game_config", "maps", "pois"))


def _missing(tbl) -> bool:
    return not isinstance(tbl, dict) or not tbl


def _ordered(tbl, order, where):
    """按**声明序**排外层键（域是字典序，真源是插入序）。域读不到 → `{}` 不抛；
    域在但键集与声明不一致 → `raise`（防「源改了、门面静默改序」）。"""
    if _missing(tbl):
        return {}
    keys = list(order)
    if len(set(keys)) != len(keys):
        raise ValueError("catalog_legacy：%s 的序声明有重复键 —— 拒绝静默取首个" % where)
    have = set(tbl)
    miss = [k for k in keys if k not in have]
    extra = [k for k in have if k not in set(keys)]
    if miss or extra:
        raise ValueError(
            "catalog_legacy：%s 与序声明不一致（表缺 %d / 声明缺 %d）—— 请重跑 "
            "overnight/_w13_gen_legacy.py 同步序声明。表缺 %s … 未声明 %s …"
            % (where, len(miss), len(extra), miss[:5], sorted(extra)[:5]))
    return {k: tbl[k] for k in keys}


# ---- 序声明读口：**唯一源** = `content/data/key_order.json`（`key_order` 域）----
# S2 ①：本文件原先内嵌的 6 张序字面量（1,072 行清尾的一部分）已搬进该域，
# 「值 + 类型 + 序」与搬前逐元素对拍相等；读不到即 raise（**不静默空序 / 不静默改序**）。
def _order(name: str) -> list:
    """按名取包内序声明（引擎装载口 `orders_of`，落点由包内域声明派生）。"""
    return orders_of(_PKG_ROOT, name, domain="key_order")


# ============================================================
# ① 包内模块家（直取再导出；对拍全等）
# ============================================================
from content.mech.element_data import ELEMENT_REACTIONS as ELEMENT_REACTIONS  # noqa: F401
from content.mech.class_data import MECH_CFG as MECH_CFG  # noqa: F401
from content.mech.we_data import WEAPON_EFFECT_DATA as WEAPON_EFFECT_DATA  # noqa: F401
from content.skills import SKILL_UP as SKILL_UP  # noqa: F401
from content.item_templates import TIPS as TIPS  # noqa: F401
from content.config import TRIAL_MIN_LV as TRIAL_MIN_LV  # noqa: F401
from content.config import WEEKLY_MIN_LV as WEEKLY_MIN_LV  # noqa: F401
from content.config import WEEKLY_PICK as WEEKLY_PICK  # noqa: F401
from content.instance_cmds import INVESTIGATE_BP_CHANCE as INVESTIGATE_BP_CHANCE  # noqa: F401
from content.instance_cmds import INVESTIGATE_COLLECT_CHANCE as INVESTIGATE_COLLECT_CHANCE  # noqa: F401
from content.instance_cmds import INVESTIGATE_RUNE_CHANCE as INVESTIGATE_RUNE_CHANCE  # noqa: F401
from content.mech.params import mech_cfg as mech_cfg  # noqa: F401  包内模块家（函数）
from content.tables import resolve_job as resolve_job  # noqa: F401  包内模块家（函数）

# ============================================================
# ② 包内域读口（content/rules/game_config.json 各组；对拍全等）
# ============================================================
# ---- game_config.battle_config（14 名）
from content.tables import JOB_GUIDE as _JOB_GUIDE_RAW  # noqa: E402
from content.tables import JOB_ORDER as BASE_ORDER  # noqa: E402

# 宝石名基底（真源 game/data/gems.py `GEM_BASE_NAME`；与包内 `GEM_ITEM_TYPE` 同值）
from content.catalog_rules import GEM_ITEM_TYPE as GEM_BASE_NAME  # noqa: E402

# 垂钓档位序（真源 game/data/__init__.py:30：`FISH_QUALITY_ORDER = QUALITY_ORDER`）
from content.catalog_b143 import QUALITY_ORDER as _QUALITY_ORDER  # noqa: E402
from content.collection import books as _collection_books  # noqa: E402
from content.wild_king import WILD_KINGS as _WILD_KINGS_RAW  # noqa: E402
BOSS_ATTACK_MULTS = placeholder("BOSS_ATTACK_MULTS")
CONTROL_MECHS = placeholder("CONTROL_MECHS")
DOT_ADAPT_DECAY_STEP = placeholder("DOT_ADAPT_DECAY_STEP")
DOT_BLEED_DOUBLE_HP_PCT = placeholder("DOT_BLEED_DOUBLE_HP_PCT")
DOT_DEFS = placeholder("DOT_DEFS")
DOT_RESIST_CAP = placeholder("DOT_RESIST_CAP")
MECH_COMBO_STACKS = placeholder("MECH_COMBO_STACKS")
MECH_FROZEN_MULT = placeholder("MECH_FROZEN_MULT")
MECH_FULL_HP_CRIT = placeholder("MECH_FULL_HP_CRIT")
MECH_PROC_GROUPS = placeholder("MECH_PROC_GROUPS")
MECH_STACK_BONUS = placeholder("MECH_STACK_BONUS")
MECH_STACK_WHITELIST = placeholder("MECH_STACK_WHITELIST")
MECH_STAT_PASSIVES = placeholder("MECH_STAT_PASSIVES")
SKILL_CC_WHITELIST = placeholder("SKILL_CC_WHITELIST")
GATHER_MAP_POOLS = placeholder("GATHER_MAP_POOLS")
GATHER_COND_POOLS = placeholder("GATHER_COND_POOLS")
MINING_DEEP_POOLS = placeholder("MINING_DEEP_POOLS")
PRICE_BAND = placeholder("PRICE_BAND")
GATHER_MAP_MIN_LV = placeholder("GATHER_MAP_MIN_LV")
ITEM_TAG_DISPLAY = placeholder("ITEM_TAG_DISPLAY")
MOUNT_DROP_BOSS = placeholder("MOUNT_DROP_BOSS")
MOUNT_DROP_ELITE = placeholder("MOUNT_DROP_ELITE")
SIGNIN_CONFIG = placeholder("SIGNIN_CONFIG")
SHOP_LIMIT = placeholder("SHOP_LIMIT")
_ORDER_JOB_GUIDE = placeholder("_ORDER_JOB_GUIDE")
_JOB_GUIDE_STRIPPED = placeholder("_JOB_GUIDE_STRIPPED")
JOB_GUIDE = placeholder("JOB_GUIDE")
_ORDER_JOB_ALIASES = placeholder("_ORDER_JOB_ALIASES")
_JOB_ALIASES_FOLDED = placeholder("_JOB_ALIASES_FOLDED")
JOB_ALIASES = placeholder("JOB_ALIASES")
EXTRA_RESOURCES = placeholder("EXTRA_RESOURCES")
EXTRA_RESOURCE_GUIDE = placeholder("EXTRA_RESOURCE_GUIDE")
FISH_QUALITY_ORDER = placeholder("FISH_QUALITY_ORDER")
COLLECTION_BOOKS = placeholder("COLLECTION_BOOKS")
_ORDER_WILD_KINGS = placeholder("_ORDER_WILD_KINGS")
WILD_KINGS = placeholder("WILD_KINGS")
_ORDER_SUBAREA_LINKS_INDEX = placeholder("_ORDER_SUBAREA_LINKS_INDEX")
_MAPS_DOM = placeholder("_MAPS_DOM")
_LINKS_BUILT = placeholder("_LINKS_BUILT")
SUBAREA_LINKS_INDEX = placeholder("SUBAREA_LINKS_INDEX")
_ORDER_SUBAREA_POIS = placeholder("_ORDER_SUBAREA_POIS")
_POIS_DOM = placeholder("_POIS_DOM")
SUBAREA_POIS = placeholder("SUBAREA_POIS")
_a = placeholder("_a")
_cid = placeholder("_cid")
_e = placeholder("_e")
_e2 = placeholder("_e2")

_ORDER_SHOP_LIMIT = _order("shop_limit")
from content.shop_stock import SHOP_LIMIT as _SHOP_LIMIT_RAW  # noqa: E402
from content.tables import JOB_GUIDE as _JOB_GUIDE_RAW  # noqa: E402
from content.tables import JOB_ORDER as BASE_ORDER  # noqa: E402

# 宝石名基底（真源 game/data/gems.py `GEM_BASE_NAME`；与包内 `GEM_ITEM_TYPE` 同值）
from content.catalog_rules import GEM_ITEM_TYPE as GEM_BASE_NAME  # noqa: E402

# 垂钓档位序（真源 game/data/__init__.py:30：`FISH_QUALITY_ORDER = QUALITY_ORDER`）
from content.catalog_b143 import QUALITY_ORDER as _QUALITY_ORDER  # noqa: E402
from content.collection import books as _collection_books  # noqa: E402
from content.wild_king import WILD_KINGS as _WILD_KINGS_RAW  # noqa: E402
BOSS_ATTACK_MULTS = placeholder("BOSS_ATTACK_MULTS")
CONTROL_MECHS = placeholder("CONTROL_MECHS")
DOT_ADAPT_DECAY_STEP = placeholder("DOT_ADAPT_DECAY_STEP")
DOT_BLEED_DOUBLE_HP_PCT = placeholder("DOT_BLEED_DOUBLE_HP_PCT")
DOT_DEFS = placeholder("DOT_DEFS")
DOT_RESIST_CAP = placeholder("DOT_RESIST_CAP")
MECH_COMBO_STACKS = placeholder("MECH_COMBO_STACKS")
MECH_FROZEN_MULT = placeholder("MECH_FROZEN_MULT")
MECH_FULL_HP_CRIT = placeholder("MECH_FULL_HP_CRIT")
MECH_PROC_GROUPS = placeholder("MECH_PROC_GROUPS")
MECH_STACK_BONUS = placeholder("MECH_STACK_BONUS")
MECH_STACK_WHITELIST = placeholder("MECH_STACK_WHITELIST")
MECH_STAT_PASSIVES = placeholder("MECH_STAT_PASSIVES")
SKILL_CC_WHITELIST = placeholder("SKILL_CC_WHITELIST")
GATHER_MAP_POOLS = placeholder("GATHER_MAP_POOLS")
GATHER_COND_POOLS = placeholder("GATHER_COND_POOLS")
MINING_DEEP_POOLS = placeholder("MINING_DEEP_POOLS")
PRICE_BAND = placeholder("PRICE_BAND")
GATHER_MAP_MIN_LV = placeholder("GATHER_MAP_MIN_LV")
ITEM_TAG_DISPLAY = placeholder("ITEM_TAG_DISPLAY")
MOUNT_DROP_BOSS = placeholder("MOUNT_DROP_BOSS")
MOUNT_DROP_ELITE = placeholder("MOUNT_DROP_ELITE")
SIGNIN_CONFIG = placeholder("SIGNIN_CONFIG")
SHOP_LIMIT = placeholder("SHOP_LIMIT")
_ORDER_JOB_GUIDE = placeholder("_ORDER_JOB_GUIDE")
_JOB_GUIDE_STRIPPED = placeholder("_JOB_GUIDE_STRIPPED")
JOB_GUIDE = placeholder("JOB_GUIDE")
_ORDER_JOB_ALIASES = placeholder("_ORDER_JOB_ALIASES")
_JOB_ALIASES_FOLDED = placeholder("_JOB_ALIASES_FOLDED")
JOB_ALIASES = placeholder("JOB_ALIASES")
EXTRA_RESOURCES = placeholder("EXTRA_RESOURCES")
EXTRA_RESOURCE_GUIDE = placeholder("EXTRA_RESOURCE_GUIDE")
FISH_QUALITY_ORDER = placeholder("FISH_QUALITY_ORDER")
COLLECTION_BOOKS = placeholder("COLLECTION_BOOKS")
_ORDER_WILD_KINGS = placeholder("_ORDER_WILD_KINGS")
WILD_KINGS = placeholder("WILD_KINGS")
_ORDER_SUBAREA_LINKS_INDEX = placeholder("_ORDER_SUBAREA_LINKS_INDEX")
_MAPS_DOM = placeholder("_MAPS_DOM")
_LINKS_BUILT = placeholder("_LINKS_BUILT")
SUBAREA_LINKS_INDEX = placeholder("SUBAREA_LINKS_INDEX")
_ORDER_SUBAREA_POIS = placeholder("_ORDER_SUBAREA_POIS")
_POIS_DOM = placeholder("_POIS_DOM")
SUBAREA_POIS = placeholder("SUBAREA_POIS")
_a = placeholder("_a")
_cid = placeholder("_cid")
_e = placeholder("_e")
_e2 = placeholder("_e2")

COVERED: tuple = ("BASE_ORDER", "BOSS_ATTACK_MULTS", "COLLECTION_BOOKS", "CONTROL_MECHS", "DOT_ADAPT_DECAY_STEP", "DOT_BLEED_DOUBLE_HP_PCT", "DOT_DEFS", "DOT_RESIST_CAP", "ELEMENT_REACTIONS", "EXTRA_RESOURCES", "EXTRA_RESOURCE_GUIDE", "FISH_QUALITY_ORDER", "GATHER_COND_POOLS", "GATHER_MAP_MIN_LV", "GATHER_MAP_POOLS", "GEM_BASE_NAME", "INVESTIGATE_BP_CHANCE", "INVESTIGATE_COLLECT_CHANCE", "INVESTIGATE_RUNE_CHANCE", "ITEM_TAG_DISPLAY", "JOB_ALIASES", "JOB_GUIDE", "MECH_CFG", "MECH_COMBO_STACKS", "MECH_FROZEN_MULT", "MECH_FULL_HP_CRIT", "MECH_PROC_GROUPS", "MECH_STACK_BONUS", "MECH_STACK_WHITELIST", "MECH_STAT_PASSIVES", "MINING_DEEP_POOLS", "MOUNT_DROP_BOSS", "MOUNT_DROP_ELITE", "PRICE_BAND", "SHOP_LIMIT", "SIGNIN_CONFIG", "SKILL_CC_WHITELIST", "SKILL_UP", "SUBAREA_LINKS_INDEX", "SUBAREA_POIS", "TIPS", "TRIAL_MIN_LV", "WEAPON_EFFECT_DATA", "WEEKLY_MIN_LV", "WEEKLY_PICK", "WILD_KINGS", "mech_cfg", "resolve_job")

#: 本模块**不覆盖**的丢名（包内无源 → 需建域或改读点；见报告「缺口」逐条）
GAPS: tuple = ("AFFIX_AFFINITY_POOLS", "AFFIX_KIND", "BRANCH_KEY_DISPLAY", "CLASS_SET_STAGES", "CLASS_SET_THEMES", "CORE_RESOURCE_GUIDE", "EXTRA_ALIASES", "FACTION_SHOP", "HIDDEN_ORDER", "HIDDEN_SUCCESSORS", "INSTANCE_BOSS_EQUIP_DROP", "QUEST_ADD", "QUEST_MAT", "REFINE_EXCLUSIVE_RECIPES", "SUBAREA_BY_MAP", "SUBAREA_INDEX", "SUBAREA_PROPS", "WILD_KING_CHEST_TIERS", "WILD_KING_GLOBAL_LIMIT", "WILD_KING_LIFETIME_SEC", "WILD_KING_LOOT_PRIORITY_SEC", "WILD_KING_MAPS", "WILD_KING_NO_KILL_EXTRA", "WILD_KING_PERIODS", "WILD_KING_PER_DAY_LIMIT", "WILD_KING_PER_PERIOD_LIMIT", "WILD_KING_PITY_PERIODS", "WILD_KING_SPAWN_HOURS", "affixes", "alchemy", "base_growth", "battle_config", "battle_rules", "builds", "calamity", "classes", "collection_book", "cooking", "dialogues", "dungeon_links", "dungeon_pois", "econ_config", "enhance", "equip_roster", "equipment", "formula_skeleton", "gather", "gather_map_min_lv", "gather_pools", "guild", "hidden_monsters", "honor_shop", "housing", "instance_investigation", "instance_stage_maps", "instances", "item_tag_display", "items", "job_guide", "merge_into", "mesh_rooms_east_abyss", "mesh_rooms_south", "mesh_rooms_west_north", "monster_mods", "monsters", "npcs", "poi_pools", "price_band", "prof_config", "props", "quest_add_v140", "quests", "races", "refine", "refine_exclusive", "set_bonus_data", "sets", "shop", "shop_limit", "signin_config", "skill_up", "skills", "stat_templates", "subareas", "tips", "titles", "trial_tower", "upgrade", "weapon_effect_data", "weekly_quests", "wild_king_data", "wild_npcs", "world")

#: 真源在宿主 `game/data/*`、包内既无门面也无域的名字（缺域 / 缺实现）
GAP_REASON: dict = {
    '宿主函数（包内无实现）': ['price_band', 'gather_map_min_lv', 'merge_into'],
    '宿主 data 子模块句柄（随 data 消失；实测无真读点）': ['affixes', 'alchemy', 'base_growth', 'battle_config', 'battle_rules', 'builds', 'calamity', 'classes', 'collection_book', 'cooking', 'dialogues', 'dungeon_links', 'dungeon_pois', 'econ_config', 'enhance', 'equip_roster', 'equipment', 'formula_skeleton', 'gather', 'gather_pools', 'guild', 'hidden_monsters', 'honor_shop', 'housing', 'instance_investigation', 'instance_stage_maps', 'instances', 'item_tag_display', 'items', 'job_guide', 'mesh_rooms_east_abyss', 'mesh_rooms_south', 'mesh_rooms_west_north', 'monster_mods', 'monsters', 'npcs', 'poi_pools', 'prof_config', 'props', 'quest_add_v140', 'quests', 'races', 'refine', 'refine_exclusive', 'set_bonus_data', 'sets', 'shop', 'shop_limit', 'signin_config', 'skill_up', 'skills', 'stat_templates', 'subareas', 'tips', 'titles', 'trial_tower', 'upgrade', 'weapon_effect_data', 'weekly_quests', 'wild_king_data', 'wild_npcs', 'world'],
    # ---- B15b 追加（2026-09-14 · 只追加，不改上面两格的既有取值）----
    # 上面『宿主函数（包内无实现）』那三个名 + `GAPS` 里的 `REFINE_EXCLUSIVE_RECIPES` **已进包**：
    #   price_band / gather_map_min_lv → `content/prof_config.py`（逐字端口；常量走 content/config.py）
    #   merge_into                     → `content/refine_exclusive.py`（逐字端口；常量走 catalog_items）
    #   三门面再导出由 `content/catalog_rules.py` 尾部长尾门面负责 ⇒ 宿主 `C.<名>` 自动收回，宿主零改动。
    #   `REFINE_EXCLUSIVE_RECIPES` 的域 = `content/rules/game_config.json` 新组 `refine_exclusive`
    #   （由 `overnight/b15b_port_domain.py` 从备份真源 dump，非手抄）。
    # 故 `GAPS` / 上面那格是**历史台账**，勿再按「缺口」派活；等价性证据见 `overnight/W-B15b.md`。
    'B15b 已进包（历史名，勿再按缺口处理）': ['price_band', 'gather_map_min_lv', 'merge_into', 'REFINE_EXCLUSIVE_RECIPES'],
}


def missing_domains() -> list:
    """本模块**读不到**的域（缺文件 / 坏 JSON / 空表）—— 空 = 全部读通。"""
    out = []
    for grp in ("battle_config", "gather_pools", "prof_config", "item_tag_display",
                "mounts", "signin_config"):
        if not _R.game_config.get(grp):
            out.append("rules/game_config.json:%s" % grp)
    for sub, dom in (("data", "maps"), ("data", "pois")):
        if not getattr(_R, dom).all():
            out.append("%s/%s.json" % (sub, dom))
    return out


def missing_names() -> list:
    """本模块**声明要导出、但取值解析不到**的名字（容器空 / 标量为 None）。"""
    out = []
    for n in __all__:
        v = globals().get(n)
        if v is None or (isinstance(v, (dict, list, tuple)) and not v):
            out.append(n)
    return out


__all__ = [
    "BASE_ORDER",
    "BOSS_ATTACK_MULTS",
    "COLLECTION_BOOKS",
    "CONTROL_MECHS",
    "DOT_ADAPT_DECAY_STEP",
    "DOT_BLEED_DOUBLE_HP_PCT",
    "DOT_DEFS",
    "DOT_RESIST_CAP",
    "ELEMENT_REACTIONS",
    "EXTRA_RESOURCES",
    "EXTRA_RESOURCE_GUIDE",
    "FISH_QUALITY_ORDER",
    "GATHER_COND_POOLS",
    "GATHER_MAP_MIN_LV",
    "GATHER_MAP_POOLS",
    "GEM_BASE_NAME",
    "INVESTIGATE_BP_CHANCE",
    "INVESTIGATE_COLLECT_CHANCE",
    "INVESTIGATE_RUNE_CHANCE",
    "ITEM_TAG_DISPLAY",
    "JOB_ALIASES",
    "JOB_GUIDE",
    "MECH_CFG",
    "MECH_COMBO_STACKS",
    "MECH_FROZEN_MULT",
    "MECH_FULL_HP_CRIT",
    "MECH_PROC_GROUPS",
    "MECH_STACK_BONUS",
    "MECH_STACK_WHITELIST",
    "MECH_STAT_PASSIVES",
    "MINING_DEEP_POOLS",
    "MOUNT_DROP_BOSS",
    "MOUNT_DROP_ELITE",
    "PRICE_BAND",
    "SHOP_LIMIT",
    "SIGNIN_CONFIG",
    "SKILL_CC_WHITELIST",
    "SKILL_UP",
    "SUBAREA_LINKS_INDEX",
    "SUBAREA_POIS",
    "TIPS",
    "TRIAL_MIN_LV",
    "WEAPON_EFFECT_DATA",
    "WEEKLY_MIN_LV",
    "WEEKLY_PICK",
    "WILD_KINGS",
    "mech_cfg",
    "resolve_job",
    "COVERED",
    "GAPS",
    "GAP_REASON",
    "missing_domains",
    "missing_names",
]



def _rebuild_view() -> list:
    """重读本模块声明的域 → 重建模块级派生状态；返回非容器替换序列（见文件头 ★ 视图）。

    容器（dict / list / set）就地更新（身份不变、内容已新）；非容器（tuple / frozenset /
    数字 / 字符串）本模块换引用，并把 `(旧对象, 新对象)` 序列交引擎做别名回填。
    import 期（见文件尾）与每次重载走**同一条路径**：本函数是唯一构建处。
    """
    global BOSS_ATTACK_MULTS, CONTROL_MECHS, DOT_ADAPT_DECAY_STEP, DOT_BLEED_DOUBLE_HP_PCT
    global DOT_DEFS, DOT_RESIST_CAP, MECH_COMBO_STACKS, MECH_FROZEN_MULT
    global MECH_FULL_HP_CRIT, MECH_PROC_GROUPS, MECH_STACK_BONUS, MECH_STACK_WHITELIST
    global MECH_STAT_PASSIVES, SKILL_CC_WHITELIST, GATHER_MAP_POOLS, GATHER_COND_POOLS
    global MINING_DEEP_POOLS, PRICE_BAND, GATHER_MAP_MIN_LV, ITEM_TAG_DISPLAY
    global MOUNT_DROP_BOSS, MOUNT_DROP_ELITE, SIGNIN_CONFIG, SHOP_LIMIT
    global _ORDER_JOB_GUIDE, _JOB_GUIDE_STRIPPED, JOB_GUIDE, _ORDER_JOB_ALIASES
    global _JOB_ALIASES_FOLDED, JOB_ALIASES, EXTRA_RESOURCES, EXTRA_RESOURCE_GUIDE
    global FISH_QUALITY_ORDER, COLLECTION_BOOKS, _ORDER_WILD_KINGS, WILD_KINGS
    global _ORDER_SUBAREA_LINKS_INDEX, _MAPS_DOM, _LINKS_BUILT, SUBAREA_LINKS_INDEX
    global _ORDER_SUBAREA_POIS, _POIS_DOM, SUBAREA_POIS, _a
    global _cid, _e, _e2

    # 旧对象：容器要就地更新、非容器要交代给引擎（全部先抓一遍，再重建）
    old = {
        'BOSS_ATTACK_MULTS': None, 'CONTROL_MECHS': None, 'DOT_ADAPT_DECAY_STEP': None, 'DOT_BLEED_DOUBLE_HP_PCT': None,
        'DOT_DEFS': None, 'DOT_RESIST_CAP': None, 'MECH_COMBO_STACKS': None, 'MECH_FROZEN_MULT': None,
        'MECH_FULL_HP_CRIT': None, 'MECH_PROC_GROUPS': None, 'MECH_STACK_BONUS': None, 'MECH_STACK_WHITELIST': None,
        'MECH_STAT_PASSIVES': None, 'SKILL_CC_WHITELIST': None, 'GATHER_MAP_POOLS': None, 'GATHER_COND_POOLS': None,
        'MINING_DEEP_POOLS': None, 'PRICE_BAND': None, 'GATHER_MAP_MIN_LV': None, 'ITEM_TAG_DISPLAY': None,
        'MOUNT_DROP_BOSS': None, 'MOUNT_DROP_ELITE': None, 'SIGNIN_CONFIG': None, 'SHOP_LIMIT': None,
        '_ORDER_JOB_GUIDE': None, '_JOB_GUIDE_STRIPPED': None, 'JOB_GUIDE': None, '_ORDER_JOB_ALIASES': None,
        '_JOB_ALIASES_FOLDED': None, 'JOB_ALIASES': None, 'EXTRA_RESOURCES': None, 'EXTRA_RESOURCE_GUIDE': None,
        'FISH_QUALITY_ORDER': None, 'COLLECTION_BOOKS': None, '_ORDER_WILD_KINGS': None, 'WILD_KINGS': None,
        '_ORDER_SUBAREA_LINKS_INDEX': None, '_MAPS_DOM': None, '_LINKS_BUILT': None, 'SUBAREA_LINKS_INDEX': None,
        '_ORDER_SUBAREA_POIS': None, '_POIS_DOM': None, 'SUBAREA_POIS': None, '_a': None,
        '_cid': None, '_e': None, '_e2': None,
    }
    for _n in list(old):
        old[_n] = globals()[_n]

    BOSS_ATTACK_MULTS = _R.game_config.get("battle_config", {}).get("BOSS_ATTACK_MULTS") or {}
    CONTROL_MECHS = _R.game_config.get("battle_config", {}).get("CONTROL_MECHS") or ()
    DOT_ADAPT_DECAY_STEP = _R.game_config.get("battle_config", {}).get("DOT_ADAPT_DECAY_STEP")
    DOT_BLEED_DOUBLE_HP_PCT = _R.game_config.get("battle_config", {}).get("DOT_BLEED_DOUBLE_HP_PCT")
    DOT_DEFS = _R.game_config.get("battle_config", {}).get("DOT_DEFS") or {}
    DOT_RESIST_CAP = _R.game_config.get("battle_config", {}).get("DOT_RESIST_CAP")
    MECH_COMBO_STACKS = _R.game_config.get("battle_config", {}).get("MECH_COMBO_STACKS") or ()
    MECH_FROZEN_MULT = _R.game_config.get("battle_config", {}).get("MECH_FROZEN_MULT") or {}
    MECH_FULL_HP_CRIT = _R.game_config.get("battle_config", {}).get("MECH_FULL_HP_CRIT") or ()
    MECH_PROC_GROUPS = _R.game_config.get("battle_config", {}).get("MECH_PROC_GROUPS") or {}
    MECH_STACK_BONUS = _R.game_config.get("battle_config", {}).get("MECH_STACK_BONUS") or {}
    MECH_STACK_WHITELIST = _R.game_config.get("battle_config", {}).get("MECH_STACK_WHITELIST") or ()
    MECH_STAT_PASSIVES = _R.game_config.get("battle_config", {}).get("MECH_STAT_PASSIVES") or {}
    SKILL_CC_WHITELIST = _R.game_config.get("battle_config", {}).get("SKILL_CC_WHITELIST") or ()

    # ---- game_config.gather_pools（3 名）
    GATHER_MAP_POOLS = _R.game_config.get("gather_pools", {}).get("GATHER_MAP_POOLS") or {}
    GATHER_COND_POOLS = _R.game_config.get("gather_pools", {}).get("GATHER_COND_POOLS") or {}
    MINING_DEEP_POOLS = _R.game_config.get("gather_pools", {}).get("MINING_DEEP_POOLS") or {}

    # ---- game_config.prof_config（2 名）
    PRICE_BAND = _R.game_config.get("prof_config", {}).get("PRICE_BAND") or {}
    GATHER_MAP_MIN_LV = _R.game_config.get("prof_config", {}).get("GATHER_MAP_MIN_LV") or []

    # ---- game_config.item_tag_display（1 名）
    ITEM_TAG_DISPLAY = _R.game_config.get("item_tag_display", {}).get("ITEM_TAG_DISPLAY") or {}

    # ---- game_config.mounts（2 名）
    MOUNT_DROP_BOSS = _R.game_config.get("mounts", {}).get("MOUNT_DROP_BOSS") or {}
    MOUNT_DROP_ELITE = _R.game_config.get("mounts", {}).get("MOUNT_DROP_ELITE") or {}

    # ---- game_config.signin_config（1 名）
    SIGNIN_CONFIG = _R.game_config.get("signin_config", {}).get("SIGNIN_CONFIG") or {}

    # ============================================================
    # ③ 序/类型还原读口（域落盘字典序 → 真源插入序；注入键剥离/反折叠）
    # ============================================================
    # 商店限购配置 35 条（真源 game/data/shop_limit.py:39；域落盘是字典序 → 按真源插入序还原）
    SHOP_LIMIT = _ordered(_SHOP_LIMIT_RAW, _ORDER_SHOP_LIMIT, "shop_stock.SHOP_LIMIT")

    # 职业速查 7 条（真源 game/data/job_guide.py:172；域落盘字典序 + 导出器注入 `aliases`/`extra_resources`
    # → 剥注入键后按真源插入序还原）
    _ORDER_JOB_GUIDE = _order("job_guide")
    _JOB_GUIDE_STRIPPED = {_cid: {_k: _v for _k, _v in _e.items()
                           if _k not in ("aliases", "extra_resources")}
                           for _cid, _e in _JOB_GUIDE_RAW.items()}
    JOB_GUIDE = _ordered(_JOB_GUIDE_STRIPPED, _ORDER_JOB_GUIDE, "content.tables.JOB_GUIDE")

    # 职业查询别名 44 条（真源 game/data/job_guide.py:180 JOB_ALIASES；导出器把它折叠进
    # 每职业的 `aliases` 列表 → 反折叠回 `{查询名: 职业 id}` 并按真源插入序还原）
    _ORDER_JOB_ALIASES = _order("job_aliases")
    _JOB_ALIASES_FOLDED = {}
    for _cid, _e in _JOB_GUIDE_RAW.items():
        for _a in (_e.get("aliases") or []):
            _JOB_ALIASES_FOLDED.setdefault(_a, _cid)
    JOB_ALIASES = _ordered(_JOB_ALIASES_FOLDED, _ORDER_JOB_ALIASES, "game/data/job_guide.py:JOB_ALIASES")

    # 次要资源（真源 game/data/job_guide.py:58 EXTRA_RESOURCES；导出器把 EXTRA_RESOURCES +
    # EXTRA_RESOURCE_GUIDE 合并成每职业的 `extra_resources` 列表 → 反折叠回 `{职业: [资源 key]}`）
    EXTRA_RESOURCES = {_cid: [_e2["key"] for _e2 in (_e.get("extra_resources") or [])]
                       for _cid, _e in _JOB_GUIDE_RAW.items() if _e.get("extra_resources")}

    # 次要资源展示元数据（真源 game/data/job_guide.py:99 EXTRA_RESOURCE_GUIDE；被导出器并进
    # 每职业 `extra_resources` 的每条（多了 `key`）→ 反折叠回 `{资源 key: {name,max,desc}}`）
    EXTRA_RESOURCE_GUIDE = {}
    for _cid, _e in _JOB_GUIDE_RAW.items():
        for _e2 in (_e.get("extra_resources") or []):
            EXTRA_RESOURCE_GUIDE[_e2["key"]] = {_k: _v for _k, _v in _e2.items()
                                                if _k != "key"}

    # 基础七职业顺序（真源 game/data/job_guide.py `BASE_ORDER`；与包内 `tables.JOB_ORDER` 同值）
    FISH_QUALITY_ORDER = _QUALITY_ORDER

    # 冒险者收藏册 5 册（真源 game/data/collection_book.py:20；域每册被注入 `order`（列表序）
    # → 剥掉后逐册全等，册序由 `books()` 按源列表序给出）
    COLLECTION_BOOKS = [dict((_k, _v) for _k, _v in _b.items() if _k != "order")
                        for _b in _collection_books()]

    # 野外王 8 条（真源 game/data/wild_king_data.py；域落盘字典序 → 按真源插入序还原）
    _ORDER_WILD_KINGS = _order("wild_kings")
    WILD_KINGS = _ordered(_WILD_KINGS_RAW, _ORDER_WILD_KINGS, "content/wild_king.WILD_KINGS")

    # 网状连通表 97 图（真源 game/data/_assembly.py 装配；= maps 域每图的 `links`，
    # 无 links 的图不在真源表里；域按字典序落盘 → 按真源插入序还原）
    _ORDER_SUBAREA_LINKS_INDEX = _order("subarea_links_index")
    _MAPS_DOM = _R.maps.all()
    _LINKS_BUILT = {_mid: _e["links"] for _mid, _e in _MAPS_DOM.items()
                    if isinstance(_e, dict) and isinstance(_e.get("links"), dict)}
    SUBAREA_LINKS_INDEX = _ordered(_LINKS_BUILT, _ORDER_SUBAREA_LINKS_INDEX,
                                   "data/maps.json:links")

    # POI 挂载表 457 行（真源 game/data/pois.py；dungeon 行的自带定义 dict → 只留 id，
    # 与 content/pois.py 的 `_MOUNTED` 同款归一；域按字典序落盘 → 按真源插入序还原）
    _ORDER_SUBAREA_POIS = _order("subarea_pois")
    _POIS_DOM = _R.pois.all()
    SUBAREA_POIS = _ordered(
        {_k: [(_x["id"] if isinstance(_x, dict) else _x) for _x in (_r.get("pois") or [])]
         for _k, _r in _POIS_DOM.items()},
        _ORDER_SUBAREA_POIS, "data/pois.json")

    # ============================================================
    # ④ 台账（供报告 / 门禁）
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


register_view(_rebuild_view, order=90)
apply_replacements(_rebuild_view(), __package__)
