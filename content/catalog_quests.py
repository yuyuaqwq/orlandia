# -*- coding: utf-8 -*-
"""包内「任务剧情族」内容聚合门面（`content/catalog_quests.py`）。

这是宿主聚合层 `C`（游戏仓 `game/content.py` → `from .data import *`）在本单元 21 个
数据名上的**包内等价物**：宿主 `game/data/` 74.7k 行删掉之后，包内模块照旧能读到这些名字。
只读**包内域数据**（`content/data|rules/<域>.json`），不 import 宿主任何模块（`game.*`）——
本模块的存在意义就是「宿主表删掉之后仍能活」。

覆盖的 21 个名字（== `overnight/B14_单元表.json` 的 `C-任务剧情族`）
------------------------------------------------------------------
    名字                 来源（包内域 / 规则）                                    还原规则
    -------------------  ------------------------------------------------------  ------------------------------------------
    NPCS                 `npcs` 域 `source=='town'`（362）                         去注入字段 `source`（+ 序表）
    WILD_NPCS            `npcs` 域 `source=='wild'`（47）                          去 `source`（+ 序表）
    HIDDEN_NPCS          `npcs` 域 `source=='hidden'`（22）                        去 `source`/`inst_stage`（+ 序表）
    DIALOGUES            `dialogues` 域全量（39 棵对话树）                          原样（+ 序表）
    ACHIEVEMENTS         `achievements` 域全量（119）                              原样，按序表还原成 list
    MAIN_QUESTS          `quests` 域 `source=='main'`（70）                        去 `source`（+ 序表）
    SIDE_QUESTS          `quests` 域 `source=='side'`（144）                       去 `source`（+ 序表）
    DAILY_QUESTS         `quests` 域 `source=='daily'`（24）                       去 `source`（+ 序表；键=name）
    EXPLORE_EVENTS       `events` 域 `source=='explore'`（100）                    去 `source`（+ 序表）
    EXPLORE_EGG_EVENTS   `events` 域 `source=='egg'`（46）                         去 `source`（+ 序表）
    MONSTER_SKILLS       `monsters` 域全量（330，怪技能表）                          原样（+ 序表）
    MONSTER_MODS         `monster_mods` 域全量（140）                              原样（+ 序表）
    ELITE_EQUIP_DROP     `monster_roster` 的 `elite_equip_drop`（20 条 → 18 个名）    {精英中文名: 装备 id}（同名同值去重 + 序表）
    TITLES               `titles` 域全量（68）                                     去注入字段 `seq`，按 `seq` 还原源序
    WEEKLY_QUESTS        `weekly_quests` 域全量（12）                              去 `seq`，按 `seq` 还原源序
    TRIAL_FLOORS         `trial_floors` 域全量（30）                               按 `floor` 1..30 还原源序
    TRIAL_DAILY_LIMIT    `rules/game_config.json` 的 `trial_tower`（3）            原样标量
    TRIAL_MAX_FLOOR      `rules/game_config.json` 的 `trial_tower`（30）           原样标量
    BUILDS               `rules/game_config.json` 的 `builds.BUILDS`（7 职业）      原样（域内层键序 = 源序，未丢）

**缺口（本单元做不到的 2 个名字，详见 `overnight/W-B14-C.md`）**：`HIDDEN_MONSTERS`、
`CHAPTER_PACK` —— 包内 66 域里没有等价数据源，见文件末尾 `PENDING_NAMES`。

⚠️ 为什么带「序表」（`key_order` 域：本模块 13 条 / 1,461 键）
-------------------------------------------------------------
包内域 JSON 的**外层键按字典序落盘**（落盘规范「外层键升序」，幂等优先），源迭代序
（随机取 / 遍历 / 掉落序的语义）在域里没有落点 —— 于是逐张声明在 `content/data/key_order.json`
（形状与来历见该域 schema），本文件按名取用。导入期两道守卫：`_order()` 取不到条目 /
形状不对 → raise；`_ordered()` 断言「域键集 == 序声明键集」，不符 → raise
（不静默改序、不静默漏项）。

域来源与读者（真源 = 游戏仓；单向导出器 = 游戏仓 `scripts/`）
------------------------------------------------------------
    content/data/npcs.json          ← derive_npcs             431 = town 362 + wild 47 + hidden 22
    content/data/quests.json        ← derive_quests           238 = main 70 + side 144 + daily 24
    content/data/events.json        ← derive_events           146 = explore 100 + egg 46
    content/data/dialogues.json     ← derive_dialogues        39 棵对话树（键 = NPC id）
    content/data/achievements.json  ← derive_achievements     119
    content/data/titles.json        ← derive_titles           68（自带 seq）
    content/data/weekly_quests.json ← derive_weekly_quests    12（自带 seq）
    content/data/trial_floors.json  ← derive_trial_floors     30（floor 1..30）
    content/data/monsters.json      ← derive_monsters         330 怪技能（= 宿主 MONSTER_SKILLS）
    content/data/monster_mods.json  ← derive_monster_mods     140
    content/data/monster_roster.json← derive_monster_roster   380（elite_equip_drop 20 条）
    content/rules/game_config.json  ← derive_game_config      builds / trial_tower 两组常量

不改形状：本模块只做「取值 / 去注入字段 / 还原序 / 建表」，零默认值、零数值改写
（数值与文案全在域里）。
"""
from __future__ import annotations

import os

from saintess_engine.records import apply_replacements, placeholder, register_view, set_from_domains, update_in_place

from ._domainio import require_key_order   # P0-4 域读口单源

_HERE = os.path.dirname(os.path.abspath(__file__))          # <pkg>/content
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>

# 读域文件 / 缺表留痕（`missing`）收进引擎 records 形状的域声明；
# **域元数据唯一源 = 包内 `editor/domains.json`**（S2 ②：这里只声明「我要哪些域」，
# 落点由声明的 `kind` 派生；声明缺项 / 文件缺 / 声明与磁盘不符 → 装载期报错，不静默）。
# （域顶层键的声明序见下方 `_ordered(...)`：那几张表还要按**源迭代序**重排，
#   而 `order` 只能整域覆盖，NPCS 三表是先按注入字段 `source` 过滤出的子表 —— 见 DIFF_NOTES §C）
_R = set_from_domains(_PKG_ROOT, (
    "npcs", "quests", "events", "dialogues", "achievements", "titles",
    "weekly_quests", "trial_floors", "monsters", "monster_mods",
    "monster_roster", "game_config", "key_order",
))


def _drop(ent: dict, *keys) -> dict:
    """去掉导出期**注入**的字段（`source` / `inst_stage` / `seq`），其余字段顺序原样。

    注入字段在条目末尾，去掉它 = 还原宿主原条目（字段顺序也随之还原）。
    """
    if not isinstance(ent, dict):
        return ent
    return {k: v for k, v in ent.items() if k not in keys}


def _ordered(tbl: dict, order, where: str) -> dict:
    """域表 → 按**源迭代序**重排的 dict；键集不等 → raise（漂移防线，不许静默漏项）。"""
    got, want = set(tbl), set(order)
    if got != want:
        raise ValueError(
            "%s：域键集与序声明不一致（域多 %s / 序声明多 %s）—— 域或序声明变了，"
            "请同步 content/data/key_order.json 的对应条目"
            % (where, sorted(got - want)[:5], sorted(want - got)[:5]))
    return {k: tbl[k] for k in order}


def _by_source(dom: dict, source: str, drop=("source",)) -> dict:
    """域表按注入字段 `source` 拆表（`derive_npcs` / `derive_quests` / `derive_events` 的逆运算）。"""
    return {k: _drop(v, *drop) for k, v in dom.items() if isinstance(v, dict)
            and v.get("source") == source}


# =============================================================================
# ① 序表（`content/data/key_order.json`：本模块 13 条 / 1,461 键）
# =============================================================================
def _order(name: str) -> list:
    """按名取键序声明（`key_order` 域）—— 缺条目 / 形状不对 → raise（不静默当空序）。"""
    return require_key_order(_ORDERS, name)


# =============================================================================
# ② 域读入（全在包内；缺文件 → {} → 下面 _ordered 立刻 raise，不静默变空表）
# =============================================================================
def _elite_equip_drop() -> dict:
    """从 `monster_roster` 的 `elite_equip_drop` 字段还原（键 = 条目的 `name`）。

    实测名册 20 条落点 ↔ 宿主表 18 键：两个名字（深渊骑士 / 沼泽巨鳄）在名册里各出现
    两次且**值相同**（`derive_monster_roster` 的多行摆放投影），故按「同名同值去重」——
    同名**值不同** → raise（那才是真冲突，不能静默挑一个）。
    """
    m: dict = {}
    for mid, ent in _ROSTER_DOM.items():
        v = ent.get("elite_equip_drop") if isinstance(ent, dict) else None
        if v is None:
            continue
        nm = ent.get("name")
        if nm in m and m[nm] != v:
            raise ValueError("elite_equip_drop：%r 在名册里有两个不同值（%r / %r）—— 拒绝静默挑一个"
                             % (nm, m[nm], v))
        m[nm] = v
    return _ordered(m, _order("elite_equip_drop"), "monster_roster(elite_equip_drop)")


_ORDERS = placeholder("_ORDERS")
_NPCS_DOM = placeholder("_NPCS_DOM")
_QUEST_DOM = placeholder("_QUEST_DOM")
_EVENT_DOM = placeholder("_EVENT_DOM")
_DLG_DOM = placeholder("_DLG_DOM")
_ACH_DOM = placeholder("_ACH_DOM")
_TITLE_DOM = placeholder("_TITLE_DOM")
_WEEKLY_DOM = placeholder("_WEEKLY_DOM")
_TRIAL_DOM = placeholder("_TRIAL_DOM")
_MODS_DOM = placeholder("_MODS_DOM")
_MSKILL_DOM = placeholder("_MSKILL_DOM")
_ROSTER_DOM = placeholder("_ROSTER_DOM")
_CFG = placeholder("_CFG")
NPCS = placeholder("NPCS")
WILD_NPCS = placeholder("WILD_NPCS")
HIDDEN_NPCS = placeholder("HIDDEN_NPCS")
DIALOGUES = placeholder("DIALOGUES")
MAIN_QUESTS = placeholder("MAIN_QUESTS")
SIDE_QUESTS = placeholder("SIDE_QUESTS")
DAILY_QUESTS = placeholder("DAILY_QUESTS")
EXPLORE_EVENTS = placeholder("EXPLORE_EVENTS")
EXPLORE_EGG_EVENTS = placeholder("EXPLORE_EGG_EVENTS")
ACHIEVEMENTS = placeholder("ACHIEVEMENTS")
TITLES = placeholder("TITLES")
WEEKLY_QUESTS = placeholder("WEEKLY_QUESTS")
MONSTER_SKILLS = placeholder("MONSTER_SKILLS")
MONSTER_MODS = placeholder("MONSTER_MODS")
ELITE_EQUIP_DROP = placeholder("ELITE_EQUIP_DROP")
_TRIAL_CFG = placeholder("_TRIAL_CFG")
TRIAL_DAILY_LIMIT = placeholder("TRIAL_DAILY_LIMIT")
TRIAL_MAX_FLOOR = placeholder("TRIAL_MAX_FLOOR")
TRIAL_FLOORS = placeholder("TRIAL_FLOORS")
BUILDS = placeholder("BUILDS")

PENDING_NAMES = ("HIDDEN_MONSTERS", "CHAPTER_PACK")

# 本模块真要用到的包内域（缺一个 = 门面变空/import 期 raise）—— 便于验收脚本点名核对
REQUIRED_DOMAINS = ("npcs", "quests", "events", "dialogues", "achievements", "titles",
                    "weekly_quests", "trial_floors", "monsters", "monster_mods",
                    "monster_roster", "game_config")


def missing_domains() -> list:
    """缺哪张域（文件不在 / 坏 JSON / 空表）—— 「静默变白板」比报错难查。"""
    return [dom for dom in REQUIRED_DOMAINS if getattr(_R, dom).missing]


__all__ = [
    "NPCS", "WILD_NPCS", "HIDDEN_NPCS", "DIALOGUES",
    "MAIN_QUESTS", "SIDE_QUESTS", "DAILY_QUESTS",
    "EXPLORE_EVENTS", "EXPLORE_EGG_EVENTS",
    "ACHIEVEMENTS", "TITLES", "WEEKLY_QUESTS",
    "MONSTER_SKILLS", "MONSTER_MODS", "ELITE_EQUIP_DROP",
    "TRIAL_FLOORS", "TRIAL_DAILY_LIMIT", "TRIAL_MAX_FLOOR", "BUILDS",
    "PENDING_NAMES", "REQUIRED_DOMAINS", "missing_domains",
]



def _rebuild_view() -> list:
    """重读本模块声明的域 → 重建模块级派生状态；返回非容器替换序列（见文件头 ★ 视图）。

    容器（dict / list / set）就地更新（身份不变、内容已新）；非容器（tuple / frozenset /
    数字 / 字符串）本模块换引用，并把 `(旧对象, 新对象)` 序列交引擎做别名回填。
    import 期（见文件尾）与每次重载走**同一条路径**：本函数是唯一构建处。
    """
    global _ORDERS, _NPCS_DOM, _QUEST_DOM, _EVENT_DOM
    global _DLG_DOM, _ACH_DOM, _TITLE_DOM, _WEEKLY_DOM
    global _TRIAL_DOM, _MODS_DOM, _MSKILL_DOM, _ROSTER_DOM
    global _CFG, NPCS, WILD_NPCS, HIDDEN_NPCS
    global DIALOGUES, MAIN_QUESTS, SIDE_QUESTS, DAILY_QUESTS
    global EXPLORE_EVENTS, EXPLORE_EGG_EVENTS, ACHIEVEMENTS, TITLES
    global WEEKLY_QUESTS, MONSTER_SKILLS, MONSTER_MODS, ELITE_EQUIP_DROP
    global _TRIAL_CFG, TRIAL_DAILY_LIMIT, TRIAL_MAX_FLOOR, TRIAL_FLOORS
    global BUILDS

    # 旧对象：容器要就地更新、非容器要交代给引擎（全部先抓一遍，再重建）
    old = {
        '_ORDERS': None, '_NPCS_DOM': None, '_QUEST_DOM': None, '_EVENT_DOM': None,
        '_DLG_DOM': None, '_ACH_DOM': None, '_TITLE_DOM': None, '_WEEKLY_DOM': None,
        '_TRIAL_DOM': None, '_MODS_DOM': None, '_MSKILL_DOM': None, '_ROSTER_DOM': None,
        '_CFG': None, 'NPCS': None, 'WILD_NPCS': None, 'HIDDEN_NPCS': None,
        'DIALOGUES': None, 'MAIN_QUESTS': None, 'SIDE_QUESTS': None, 'DAILY_QUESTS': None,
        'EXPLORE_EVENTS': None, 'EXPLORE_EGG_EVENTS': None, 'ACHIEVEMENTS': None, 'TITLES': None,
        'WEEKLY_QUESTS': None, 'MONSTER_SKILLS': None, 'MONSTER_MODS': None, 'ELITE_EQUIP_DROP': None,
        '_TRIAL_CFG': None, 'TRIAL_DAILY_LIMIT': None, 'TRIAL_MAX_FLOOR': None, 'TRIAL_FLOORS': None,
        'BUILDS': None,
    }
    for _n in list(old):
        old[_n] = globals()[_n]

    _ORDERS = _R.key_order.all()

    _NPCS_DOM = _R.npcs.all()
    _QUEST_DOM = _R.quests.all()
    _EVENT_DOM = _R.events.all()
    _DLG_DOM = _R.dialogues.all()
    _ACH_DOM = _R.achievements.all()
    _TITLE_DOM = _R.titles.all()
    _WEEKLY_DOM = _R.weekly_quests.all()
    _TRIAL_DOM = _R.trial_floors.all()
    _MODS_DOM = _R.monster_mods.all()
    _MSKILL_DOM = _R.monsters.all()
    _ROSTER_DOM = _R.monster_roster.all()
    _CFG = _R.game_config.all()

    # =============================================================================
    # ③ 21 个数据名（宿主 `C.<名>` 的等价物）
    # =============================================================================
    # --- NPC 三表（`derive_npcs` 折了 town/wild/hidden 三张真源表，注入 `source` 表达归属）---
    NPCS = _ordered(_by_source(_NPCS_DOM, "town"), _order("npcs_town"), "npcs(town)")
    WILD_NPCS = _ordered(_by_source(_NPCS_DOM, "wild"), _order("npcs_wild"), "npcs(wild)")
    # hidden 里 6 条副本层内 NPC 多一个注入字段 `inst_stage`（`derive_npcs` 注入），一并去掉
    HIDDEN_NPCS = _ordered(_by_source(_NPCS_DOM, "hidden", ("source", "inst_stage")),
                                 _order("npcs_hidden"), "npcs(hidden)")

    # --- 对话树（键 = NPC id；39 棵，节点/选项顺序是语义，域内已原样）---
    DIALOGUES = _ordered(_DLG_DOM, _order("dialogues"), "dialogues")

    # --- 任务三表（`derive_quests` 合表 + 注入 `source`；DAILY 的键是 name，源侧没有 id）---
    MAIN_QUESTS = [_drop(_QUEST_DOM[k], "source") for k in _order("quests_main")]
    SIDE_QUESTS = [_drop(_QUEST_DOM[k], "source") for k in _order("quests_side")]
    DAILY_QUESTS = [_drop(_QUEST_DOM[k], "source") for k in _order("quests_daily")]

    # --- 探索事件两池（`derive_events` 合表 + 注入 `source`）---
    EXPLORE_EVENTS = [_drop(_EVENT_DOM[k], "source") for k in _order("events_explore")]
    EXPLORE_EGG_EVENTS = [_drop(_EVENT_DOM[k], "source") for k in _order("events_egg")]

    # --- 成就 / 称号 / 周常 ---
    ACHIEVEMENTS = [_ACH_DOM[k] for k in _order("achievements")]
    # 称号 / 周常：域自带 `seq`（导出器注入 1 基源序），按它还原源序、再把 `seq` 去掉
    TITLES = [_drop(v, "seq") for v in
                    sorted(_TITLE_DOM.values(), key=lambda e: e["seq"])]
    WEEKLY_QUESTS = [_drop(v, "seq") for v in
                           sorted(_WEEKLY_DOM.values(), key=lambda e: e["seq"])]

    # --- 怪技能 / 个体改造 ---
    MONSTER_SKILLS = _ordered(_MSKILL_DOM, _order("monsters"), "monsters")
    MONSTER_MODS = _ordered(_MODS_DOM, _order("monster_mods"), "monster_mods")

    # --- 精英专属装备掉落（宿主 `ELITE_EQUIP_DROP`：键 = 精英怪**中文名** → 名册装备 id）---
    ELITE_EQUIP_DROP = _elite_equip_drop()

    # --- 试炼塔：层表 + 两个标量（常量与层表同在 game_config 域，但分属两个子表）---
    _TRIAL_CFG = _CFG.get("trial_tower") or {}
    TRIAL_DAILY_LIMIT = _TRIAL_CFG["TRIAL_DAILY_LIMIT"]
    TRIAL_MAX_FLOOR = _TRIAL_CFG["TRIAL_MAX_FLOOR"]
    # 层表按 floor 1..TRIAL_MAX_FLOOR 还原源序（域键是字符串 "1"/"10"/…，字面序会乱）
    TRIAL_FLOORS = [_TRIAL_DOM[str(i)] for i in range(1, TRIAL_MAX_FLOOR + 1)]

    # --- 职业流派（rules 域的 builds 子表：内层键序 = 源序，未被 sort_table 折叠）---
    BUILDS = dict((_CFG.get("builds") or {}).get("BUILDS") or {})

    # =============================================================================
    # ④ 缺口的两个名字（不在此处定义 —— 定义成空值会让门禁把「缺口」当成「值不等」）
    # =============================================================================
    # 这两个名字在包内 66 域里**没有**等价数据源，故本单元不提供：
    #   HIDDEN_MONSTERS  ← 宿主 game/data/hidden_monsters.py:18（25 条隐藏怪行）
    #                      包内 `monster_roster` 有 `hidden` 子块（lv_off/gold_mult/cond/
    #                      chance/tag/flavor 六字段，25/25 对得上），但它的 `name`/`skills`/
    #                      `drops` 是**五处摆放表求并集**的投影（实测 19/25 与隐藏怪行不同），
    #                      还原不了隐藏怪行原文 → 需新域 `hidden_monsters`（字段见报告）。
    #   CHAPTER_PACK     ← 宿主 game/data/quest_add_v140.py:106（10 档章节礼包 list）
    #                      包内无任何域含这批数据 → 需新域 `chapter_pack`（字段见报告）。

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


register_view(_rebuild_view, order=60)
apply_replacements(_rebuild_view(), __package__)
