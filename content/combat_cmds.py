# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— combat 命令域实现（B10 L5 薄壳化，2026-09-13）。

真源：游戏仓 `game/commands/combat.py`（3203 行）的 `class CombatCmds`。本模块 = 那个类的
**实现本体**（74 个方法逐字搬成模块级函数，只去 4 空格缩进）。宿主 `game/commands/combat.py`
现在只剩：命令注册（@declared）+ 守卫 + 取玩家/取参 + 一行转发调包 + yield 渲染。

搬的边界
--------
* **搬**：除「命令入口的取玩家/取参行」之外的全部方法（探索/野王宝箱/许愿/商人/复活确认/
  攻击/技能面板族/防御/逃跑/讨伐世界Boss/PVP 族/荣誉商店/战前指令），含 `_handle_victory`、
  `_handle_defeat` 两个**已是薄壳**的编排器（B10_BRIEF：本线不动其行为，只搬位置）。
* **不搬**：命令入口的装饰器/守卫（注册动作必须在宿主：正则来自 `game/data/command_specs.json`，
  框架注册表 + `_registry` 都从它派生）；**常量表**（`_MECH_CN` / `_EFFECT_CN` /
  `_P_BUFF_NAMES` / `_E_BUFF_NAMES` / `_STACK_NAMES` / `_ENEMY_MECH_STACKS` / `_DEBUFF_NAMES` /
  `_RAIN_WINDOW` / `_EXPLORE_RECENT_KEY` / `_EXPLORE_RECENT_MAX` / `_DF139_CLASS_FORMS` /
  `_FINISHER139_OPTIONS` / `_ARCANE_FIELD_OPTIONS`）**B10-L5 期原样留宿主类** —— ★ L7（2026-09-15）
  已**正位回本模块级**：类属性在宿主壳上取不到（`self` = 壳）⇒ 事故 `EngineShell has no attribute
  '_EXPLORE_RECENT_KEY'`；现为模块级常量、实现体直接量名读（值一字不改）。

正文改动面（**三类，全部登记**；差异面自检 `overnight/b10_l5_check.py`）
---------------------------------------------------------------------
1. 模块级/函数体内**宿主 import** → 同位置惰性替身（B10-L5 期写法；**B2-C1 已整段收口**，见下）。
2. 命令入口的 4 行取玩家/取参（`self._uid` / `self._player` / `self._strip_cmd`）**上提**到宿主
   薄壳 → 包内删除同名行、改成形参。`self._strip_cmd` 是纯函数（读 `event.get_message_str()`
   + 纯字符串处理，见 `saintess_engine/command/base.py:114`），上提零副作用；`wish` 的 `opt`
   唯一差别是求值点提前（值相同）。
3. `battle_prefs_*` 三命令的 `text`/`arg` 两行派生上提（同 2：纯函数）。

★ 全部 4 处 `self._strip_cmd`（wish/attack/skill/honor_shop）都在宿主薄壳里 —— B10_BRIEF §L5
  「取参保留在宿主」逐条落实。

★ **B2-C1（2026-09-14）收口：宿主替身口整段 → 包内直取**
--------------------------------------------------------
九个 B2 单元在本模块的全部读点已由「宿主壳惰性解析」改为**包内直取**
（逐读点对照表 = `dsh-work/b2c1/out/W-B2C1.md`；身份实测 = `out/evidence/identity_probe.txt`）：

| 原读点（宿主壳） | 现取用（包内家） |
|---|---|
| `game.commands.combat` 的野王四函数 | `content/wild_king.py`（宿主 `core.wild_king` **is** 本模块）+ 猴补覆写面 |
| `game.services.battle_bridge`（构造 + 回写） | `content/bridge.py`（`_EventStateView` 等价件也在本文件） |
| `game.services.battle_settlement` 7 名 | `content/settlement.py` + 本文件结算句柄（注入名 `db`/`content`） |
| `game.services.battle_worldboss_procs` | `content/mech/worldboss.py` |
| `game.core.event_templates` | `content/event_templates.py` |
| `game.core.poi_effects` | `content/effects/poi_effects.py` |
| `game.log_setup.LOG` | `content/obs.py`（包内唯一日志口，fail-closed） |
| `game.content` 的函数读口（11 名） | 各自包内家（12/13 与宿主聚合层**同一对象**）；3 个 drops 名见下 |

仍留在**宿主边界**的只有 3 处（逐条登记在 W-B2C1 §6）：（a）`content/drops.py` 的 3 个构造器
—— 接口表第 5 行冻结的落点属 **C2**，本波未落地 ⇒ `_drops()` 过渡口回退宿主聚合层；
（b）野王四函数的 **monkeypatch 覆写面**（`tests/test_v1307_zone_risk.py:65` /
`test_v1308_lv_jitter.py:70` 改绑 `game.commands.combat.<名>`，`b2_impact.md:100` 要求保住）；
（c）`attach_tlog`（接口表第 11 行冻结注入名，平台件，波2 由宿主壳注入）。

时序不变式（**原样保留**）：早先「只注入 3 个句柄、其余在调用点惰性解析」的理由是
提前 import **宿主服务模块**会改变 rule/action 注册顺序；本批改成包内直取后 import 的是
**包内模块**（`content/bridge.py` / `content/settlement.py` …），而它们本就是宿主壳 `_pkg()`/
`_lib()` 首次调用时 import 的那一份 ⇒ 注册顺序与改造前逐点相同。

包内直取（**不是**宿主）：`player_final_stats` / `passive_skills_learned` / `skill_learn_cost_for`
（`content/panel.py`，D3 批逐字端口）· `_sk_table` / `is_skill_learned` / `skill_info` /
`skill_level_of` / `branch_skill_owner`（`content/skills.py`，D3 批逐字端口）· `K_PHYS…K_TAUNT`
（`content/mech/kinds.py`）· `skill_*` 纯公式 / `Battle` / `formation_view` / `alive_units` /
`state_effects` / `gauge`（引擎公开 API）。

★ B14-2（L4）+ W5（2026-09-14）读点现状 —— 22 个数据名已切**包内门面**（宿主 `game/data` 删掉后仍能取值）
----------------------------------------------------------------------------------
门禁 `overnight/b14_catalog_gate.py --names …` → **不等 0（含键序）**（真实输出见
`overnight/W-B14-2-L4.md` / `overnight/_w5_cut_combat_instance.md`）。本模块切掉的名字（正文 `C.<名>` → 门面别名）：

| 门面别名 | 名字（本模块已切） |
|---|---|
| `_cc` = `content/catalog_core.py` | `CLASSES` · `PLAYER_SKILLS` · `BRANCH_SKILLS` · `TUTOR_SKILLS` · `MAP_TYPE_TOWN` · `MAP_TYPE_INSTANCE` · `ENCOUNTER_EVENT_CHANCE` · `SA_BOSS_CHANCE` · `PVP_TIMEOUT_SEC` |
| `_ci` = `content/catalog_items.py` | `MATERIALS` |
| `_cl` = `content/catalog_life.py` | `MOUNT_BY_KEY` |
| `_cq` = `content/catalog_quests.py` | `MAIN_QUESTS` · `SIDE_QUESTS` · `NPCS` · `MONSTER_SKILLS` |
| `_cs` = `content/catalog_space.py` | `MAP_BY_ID` |
| `_b143` = `content/catalog_b143.py`（W5） | `QUALITY` · `WISH_POOL` · `HONOR_SHOP` · `HIDDEN_MONSTERS` · `PET_SKILL_UNLOCK_LV` |
| `_wild` = `content/wild.py`（W5，PEP 562 惰性） | `ALL_WILD` |

★ W5（2026-09-14）收口：上列原「缺口 6 表」**已全部切包内门面**（门禁逐名深比较含键序 → 不等 0，
  取值来源换门面，数值/顺序/默认值一字未动）：
* **表**：`QUALITY`（`game/data/equipment.py` → `equipment` 域）· `WISH_POOL`
  （`game/data/poi_pools.py` → `poi_pools` 域）· `HONOR_SHOP`（`game/data/honor_shop.py` →
  `shop.honor_shop.ranks`，int 键已还原）· `HIDDEN_MONSTERS`（`game/data/hidden_monsters.py` →
  `game_config.hidden_monsters`）· `ALL_WILD`（真源 `game/core/wild.py:26` 在 import 期求值 →
  `content/wild.py` 惰性快照，宿主薄壳本就 `is` 同一模块）· `PET_SKILL_UNLOCK_LV`
  （`game/data/pets.py:192` 常量段 → `game_config.pets`）。
* **函数名**（原「保留宿主句柄」那批）：**B2-C1 已一并收口** —— 11 个函数名改为包内直取
  （实测与宿主聚合层 `C.<名>` **同一对象**：`out/evidence/identity_probe.txt`）；只剩
  3 个 `game.core.drops` 构造器（`build_monster` / `build_monster_group` / `roll_blueprint`）
  走 `_drops()` 过渡口（包内家 = C2 的 `content/drops.py`，接口表第 5 行；本波该文件未落地）。
"""
from __future__ import annotations

import importlib
import json
import random
import re
import sys
import time

from saintess_engine.battle.formulas import skill_buff_turns, skill_cond_mult, skill_lifesteal_pct, skill_max_level, skill_mech_val, skill_mp_pay_of, skill_power_mult
from saintess_engine.formation import formation_view

from . import texts as _T          # 文案表（B 批 B-1：效果名等）
from .mech.kinds import K_PHYS, K_MAGI, K_HEAL, K_BUFF, K_PASSIVE, K_TAUNT  # v176 去魔法字符串
from .panel import passive_skills_learned, player_final_stats, skill_learn_cost_for
from .skills import _sk_table, branch_skill_owner, is_skill_learned, skill_info, skill_level_of

# ---- 包内门面（B14-2 L4：宿主聚合层 `C` 的包内等价物；宿主 `game/data` 删掉后仍可取值）----
# 16 个数据名切门面（门禁逐名 OK · 不等 0，含键序）；余下 = 缺口名 + `C` 的函数名句柄。
# ⚠️ 纯包内 import（不碰宿主）⇒ 不改本模块「时序不变式」（rule/action 注册顺序）那一条。
from . import catalog_core as _cc        # CLASSES / PLAYER_SKILLS / BRANCH_SKILLS / TUTOR_SKILLS / MAP_TYPE_* / *_CHANCE / PVP_TIMEOUT_SEC
from . import catalog_items as _ci       # MATERIALS
from . import catalog_life as _cl        # MOUNT_BY_KEY
from . import catalog_quests as _cq      # MAIN_QUESTS / SIDE_QUESTS / NPCS / MONSTER_SKILLS
from . import catalog_space as _cs       # MAP_BY_ID
from . import catalog_b143 as _b143      # QUALITY / WISH_POOL / HONOR_SHOP / HIDDEN_MONSTERS / PET_SKILL_UNLOCK_LV（W5）
from . import wild as _wild              # ALL_WILD（W5；宿主薄壳 game/core/wild.py `is content.wild`，同对象）


# ============================================================
# ① 包内直取 + 宿主边界（B2-C1 收口）
# ------------------------------------------------------------
# 旧「宿主替身口」整段（通用惰性句柄 + 动态属性解析 + 野王惰性包装）已删除：
# 九个单元的读点全部改成包内直取。仍留在**宿主边界**的只有 3 处（逐条见 W-B2C1 §6）：
#   1) `content/drops.py` 的 3 个构造器 —— 接口表第 5 行冻结的 C2 落点，本波未落地；
#   2) 野王四函数的 monkeypatch 覆写面（b2_impact.md:100 要求保住）；
#   3) `attach_tlog` —— 接口表第 11 行冻结注入名（平台件，波2 由宿主壳注入）。
# ============================================================

from . import obs as _obs                     # log_setup 的包内唯一取用口（fail-closed）
from . import bridge as _BR                   # services.battle_bridge（构造 + 回写两半）
from . import settlement as _ST               # services.battle_settlement（唯一实现）
from . import event_templates as _ET          # core.event_templates（唯一实现）
from .effects import poi_effects as _POI      # core.poi_effects（唯一实现）
from .mech import worldboss as _WBP           # services.battle_worldboss_procs（唯一实现）
from . import wild_king as _WK                # core.wild_king（宿主 core.wild_king is 本模块）
from .index import resolve as _resolve, display as _display
from .achievements import check_achievements as _check_achievements
from .mounts import mount_effects as _mount_effects
from .events import roll_explore_event as _roll_explore_event, roll_explore_egg as _roll_explore_egg
from .pois import roll_poi as _roll_poi
from .stats import exp_to_next as _exp_to_next
from .panel import race_stats                          # 结算句柄用（真源 content_rules.panel）
from .gameplay_rules import resolve_drop as _resolve_drop
from .gameplay_rules import check_player_level_up as check_player_level_up   # 真源 `..content_rules.gameplay`
from .rule_engine import fire as _rule_fire
from .stat_bonus import stat_bonus as _stat_bonus
# ⚠️ 这 4 名在测试里被**宿主聚合层属性改写**（`tests/test_v83_explore_egg.py:42-44` /
#    `test_v97_03_event_templates.py:129` / `test_v1307_zone_risk.py:90-91` /
#    `test_v1308_lv_jitter.py:109-110`）⇒ 经 `_overlay()` 包一层（见下），不裸绑。
from .wild import roll_wild_encounter as _pkg_roll_wild_encounter
from .events import roll_explore_event as _pkg_roll_explore_event, roll_explore_egg as _pkg_roll_explore_egg
from .pois import roll_poi as _pkg_roll_poi
from .daily_events import today_event_effects as _pkg_today_event_effects
from .maps import bump_explore_count as _bump_explore_count              # 真源：宿主聚合层同名（同对象）
from . import catalog_rules as _cr                     # poi `dom` 替身：RUNE_POOL/NOTE_POOL/SIGHT_POOL
from .flow import instance_run as _IR                  # poi `dom` 替身：living_members/set_alive

from ._pkgref import DB as db
from .constants import ACT_TICK

HOST_PKG = "data.plugins.dragonfall.game"
HOST_PKG_FALLBACK = "game"
from saintess_engine.wire import Wire
_WIRE = Wire()


def bind_host(**objs):
    """宿主薄壳 import 期注入（幂等）——键 = 真源相对模块路径 / 接口表冻结注入名。

    仍在用的键：`db` / `content` / `commands.combat`（宿主壳 `game/commands/combat.py:65`）；
    接口表冻结、波2 才注入的键：`attach_tlog`（接口表第 11 行）。
    """
    _WIRE.bind(**objs)


# ---- 宿主边界 ①：`game.core.drops` 的 3 个构造器（跨簇缺口，W-B2C1 §6 登记）----

def _drops(name):
    """`game.core.drops` 的构造器（`build_monster` / `build_monster_group` / `roll_blueprint`）。

    包内家 = ☆`content/drops.py`（接口表第 5 行冻结的 **C2** 落点）。⚠️ 跨簇缺口：该文件属 C2 的
    落地清单，本波（C1）尚未存在 ⇒ 过渡期回退「宿主内容聚合层属性」（= 旧 `C.<名>` 的同一取法；
    再回落 `game.core.drops`）。C2 落地后回退分支即死，**本文件无需再改**。
    """
    try:
        _mod = importlib.import_module("content.drops")
    except ImportError:
        _mod = None
    if _mod is not None:
        return getattr(_mod, name)
    _cands = (HOST_PKG + ".content", HOST_PKG_FALLBACK + ".content",
              HOST_PKG + ".core.drops", HOST_PKG_FALLBACK + ".core.drops")
    for _full in _cands:
        _m = sys.modules.get(_full)
        if _m is not None and hasattr(_m, name):
            return getattr(_m, name)
    _last = None
    for _full in _cands:
        try:
            return getattr(importlib.import_module(_full), name)
        except Exception as _exc:                       # noqa: BLE001
            _last = _exc
    raise RuntimeError("content.combat_cmds：core.drops.%s 取不到（%s）——拒绝静默空跑"
                       % (name, _last))


def build_monster(*args, **kwargs):
    """真源 `from ..core.drops import build_monster`（包内家 = `content/drops.py`，见 `_drops`）。"""
    return _drops("build_monster")(*args, **kwargs)


def build_monster_group(*args, **kwargs):
    """真源 `from ..core.drops import build_monster_group`（包内家 = `content/drops.py`）。"""
    return _drops("build_monster_group")(*args, **kwargs)


# ---- 宿主边界 ②：野王四函数的 monkeypatch 覆写面 + 聚合层 5 名的覆写面 ----

def _overlay(name, pkg_obj):
    """宿主聚合层 `game.content.<name>` 的 **monkeypatch 覆写面**（与 `_wild_king` 同款口径）。

    生产上宿主聚合层同名属性 **is** 包内同名对象（实测 `out/evidence/content_homes.txt`）⇒
    本函数零动作（包内直取优先）；只有被测试改绑时用宿主那份：
    `tests/test_v83_explore_egg.py:42-44`（`roll_wild_encounter` / `roll_poi` / `roll_explore_egg`）·
    `test_v97_03_event_templates.py:129`（`roll_explore_event`）·
    `test_v1307_zone_risk.py:90-91` / `test_v1308_lv_jitter.py:109-110`（`today_event_effects`）。
    `b2_impact.md:100` 对 `explore_king` 的要求同样适用于聚合层：宿主模块属性是测试的替换点。
    只查**已加载**模块，**绝不 import 宿主模块树**。
    """
    for _full in (HOST_PKG + ".content", HOST_PKG_FALLBACK + ".content"):
        _m = sys.modules.get(_full)
        if _m is None:
            continue
        _cur = getattr(_m, name, None)
        if _cur is not None and _cur is not pkg_obj:
            return _cur
    return pkg_obj


def today_event_effects(*args, **kwargs):
    """真源 `..daily_events.today_event_effects`（+ 聚合层覆写面，见 `_overlay`）。"""
    return _overlay("today_event_effects", _pkg_today_event_effects)(*args, **kwargs)


def roll_poi(*args, **kwargs):
    """真源 `..pois.roll_poi`（+ 聚合层覆写面，见 `_overlay`）。"""
    return _overlay("roll_poi", _pkg_roll_poi)(*args, **kwargs)


def roll_explore_egg(*args, **kwargs):
    """真源 `..events.roll_explore_egg`（+ 聚合层覆写面，见 `_overlay`）。"""
    return _overlay("roll_explore_egg", _pkg_roll_explore_egg)(*args, **kwargs)


def roll_explore_event(*args, **kwargs):
    """真源 `..events.roll_explore_event`（+ 聚合层覆写面，见 `_overlay`）。"""
    return _overlay("roll_explore_event", _pkg_roll_explore_event)(*args, **kwargs)


def roll_wild_encounter(*args, **kwargs):
    """真源 `..wild.roll_wild_encounter`（+ 聚合层覆写面，见 `_overlay`）。"""
    return _overlay("roll_wild_encounter", _pkg_roll_wild_encounter)(*args, **kwargs)


def _wild_king(name):
    """野王四函数（真源 `..core.wild_king`）：**包内直取优先** + 宿主命令模块属性覆写。

    `game/core/wild_king.py` 是纯壳（`sys.modules[__name__] = content.wild_king`）⇒ 生产上
    `game.commands.combat.<名>` **is** `content.wild_king.<名>`；仅当被测试改绑
    （`tests/test_v1307_zone_risk.py:65` / `tests/test_v1308_lv_jitter.py:70`）时两者不同 →
    用宿主那份（`b2_impact.md:100` 明确要求保住该 monkeypatch 点）。只查**已加载**模块，
    **绝不 import 宿主模块树**。
    """
    _fn = getattr(_WK, name)
    for _full in (HOST_PKG + ".commands.combat", HOST_PKG_FALLBACK + ".commands.combat"):
        _m = sys.modules.get(_full)
        if _m is None:
            continue
        _cur = getattr(_m, name, None)
        if _cur is not None and _cur is not _fn:
            return _cur
    return _fn


def explore_king(*args, **kwargs):
    return _wild_king("explore_king")(*args, **kwargs)


def build_king_monster(*args, **kwargs):
    return _wild_king("build_king_monster")(*args, **kwargs)


def open_chest(*args, **kwargs):
    return _wild_king("open_chest")(*args, **kwargs)


def wild_king_summary(*args, **kwargs):
    return _wild_king("wild_king_summary")(*args, **kwargs)


# ---- 宿主边界 ③：attach_tlog（接口表第 11 行冻结注入名）+ 结算句柄（第 12 行注入名 db/content）----

def _attach_tlog(b, *, btype="monster", player=None, enemies=None, seed=None):
    """流水挂载（接口表第 11 行：宿主壳 `game/services/battle_bridge.py:203` 注入名 = `attach_tlog`）。

    · 注入优先（波2 宿主壳 `bind_host(attach_tlog=…)`）；
    · 过渡期（宿主冻结）取**已加载**的宿主 `services.battle_bridge.attach_tlog`（只查 sys.modules，
      **不 import 宿主模块树**）；
    · 都没有 → **抛**（fail-closed：开战流水静默不挂 = 平台缺陷被吞）；句柄在但流水未启用 →
      宿主契约自返回 `b`（零行为，`game/tlog_setup.py:98-124`）。
    """
    _fn = _WIRE.handles().get("attach_tlog")
    if _fn is None:
        for _full in (HOST_PKG + ".services.battle_bridge",
                      HOST_PKG_FALLBACK + ".services.battle_bridge"):
            _m = sys.modules.get(_full)
            if _m is not None:
                _fn = getattr(_m, "attach_tlog", None)
                if _fn is not None:
                    break
    if _fn is None:
        raise RuntimeError(
            "content.combat_cmds：attach_tlog 取不到（波2 宿主壳未注入且宿主模块未加载）"
            "——拒绝静默不挂流水")
    return _fn(b, btype=btype, player=player, enemies=enemies, seed=seed)


class _EventStateView(dict):
    """宿主 db → 包内 `event_state` 协议替身（逐字等价宿主壳 `game/services/battle_bridge.py:122`）。

    接口表第 11 行把 `_EventStateView` 记为宿主独有 ⇒ 等价实现落在本文件。三动词转发宿主 db；
    `dict` 子类只为满足包内 `isinstance(event_state, dict)` 守卫（键值不落本对象）。
    """

    __slots__ = ("_db",)

    def __init__(self, db):
        super().__init__()
        self._db = db

    def get(self, key, default=None):
        v = self._db.get_event_state(key)
        return default if v is None else v

    def __setitem__(self, key, value):
        self._db.set_event_state(key, value)

    def pop(self, key, default=None):
        v = self._db.get_event_state(key)
        if v is None:
            return default
        self._db.delete_event_state(key)
        return v


def _es_arg(db):
    """宿主第三参 `db` → 包内 `event_state` 替身（宿主壳 `_es_arg` 逐字等价）。"""
    return _EventStateView(db or _settle_db())


class _SettleHost:
    """`content/settlement.py` 的服务句柄（真源 = 宿主壳 `_Host`；接口表第 12 行冻结注入名 db/content）。

    · `db` / `content` = 宿主壳 `game/commands/combat.py:65` 注入的句柄（本文件 `bind_host` 唯一注入口）；
      `content` 是**宿主内容聚合层** —— 该单元的设计如此（材料/物品/符文/宠物/公会/世界事件表
      未进包，见 `content/settlement.py` 头注）；
    · 其余 5 名 = 包内同源物（真源宿主壳 `_Host` 里那 5 个也只是薄壳转发，实测**同一对象**：
      `out/evidence/identity_probe.txt`）。
    """

    __slots__ = ()

    @property
    def db(self):
        return _WIRE.handles().get("db") or db

    @property
    def C(self):                                        # noqa: N802（沿用真源 `_Host.C` 名）
        _mod = _WIRE.handles().get("content")
        if _mod is None:
            for _full in (HOST_PKG + ".content", HOST_PKG_FALLBACK + ".content"):
                _mod = sys.modules.get(_full)
                if _mod is not None:
                    break
        if _mod is None:
            raise RuntimeError("content.combat_cmds：结算句柄 content（宿主内容聚合层）取不到"
                               "——拒绝静默空跑")
        return _mod

    resolve_drop = staticmethod(_resolve_drop)
    player_final_stats = staticmethod(player_final_stats)
    race_stats = staticmethod(race_stats)
    rule_fire = staticmethod(_rule_fire)
    stat_bonus = staticmethod(_stat_bonus)


def _settle_db():
    """结算/开战句柄的存储层（宿主注入优先 → 包内存储句柄）。"""
    return _WIRE.handles().get("db") or db


def _settle_host():
    """取结算句柄（每次调用现取，与真源 `_host()` 同刻同义）。"""
    return _SettleHost()


# ============================================================================
# 模块级常量表（L7 正位：13 张表的**所有者 = 本模块**，不再挂 `class CombatCmds`）
# ----------------------------------------------------------------------------
# 背景（线上 2026-09-15 事故）：这 13 张表原为 `class CombatCmds` 的类属性；但本模块的
# 74 个实现体是**模块级函数**，被宿主壳按名绑定后 `self` = 宿主壳
# （`host/shell.py::_package_helper` → `functools.partial(fn, shell)`），壳上只有转发、
# **零包内词汇** ⇒ `self._X` 当场 `AttributeError: EngineShell has no attribute
# '_EXPLORE_RECENT_KEY'`（快捷指令整条挂）。修法 = 把表放回**本模块**（唯一所有者），
# 实现体直接读模块全局名 —— 归属正确，且壳一行不用改。
# 值逐字节取自原类属性（只改归属不改值；改前/改后逐表 sha256 对拍见 out/CONST_SHA.md）。
# 跨模块读者经 `combat_cmds._EFFECT_CN` 取同一份（`content/player_cmds.py`）。
# ============================================================================

_RAIN_WINDOW = 1800  # 30 分钟

_EXPLORE_RECENT_KEY = "explore_recent_{gid}_{qq_id}"

_EXPLORE_RECENT_MAX = 3

_MECH_KEYS = {   # ★ B-1：id → 文案键（文案真源 = text_specs.json 的 mech_name.*）
    "arcane": "mech_name.arcane", "arcane_burst": "mech_name.arcane_burst", "bleed": "mech_name.bleed",
    "bless": "mech_name.bless", "bone_rush": "mech_name.bone_rush", "burn": "mech_name.burn",
    "chi": "mech_name.chi", "cleanse": "mech_name.cleanse", "corros": "mech_name.corros",
    "curse": "mech_name.curse", "curse_refresh": "mech_name.curse_refresh", "element_burst": "mech_name.element_burst",
    "element_burst_3": "mech_name.element_burst_3", "element_burst_all": "mech_name.element_burst_all", "element_multi_mark": "mech_name.element_multi_mark",
    "faith_unload": "mech_name.faith_unload", "finisher": "mech_name.finisher", "fire_mark": "mech_name.fire_mark",
    "freeze": "mech_name.freeze", "guard_core_burst": "mech_name.guard_core_burst", "hunt_mark": "mech_name.hunt_mark",
    "ice_mark": "mech_name.ice_mark", "iron": "mech_name.iron", "judge": "mech_name.judge",
    "lian_duan": "mech_name.lian_duan", "mark": "mech_name.mark", "mark_burst": "mech_name.mark_burst",
    "melody": "mech_name.melody", "melody_chant": "mech_name.melody_chant", "poison": "mech_name.poison",
    "poison_burst": "mech_name.poison_burst", "poison_burst_finisher": "mech_name.poison_burst_finisher", "rage": "mech_name.rage",
    "sacrifice": "mech_name.sacrifice", "shadow": "mech_name.shadow", "shield": "mech_name.shield",
    "silence": "mech_name.silence", "soul_mark": "mech_name.soul_mark", "spd_down": "mech_name.spd_down",
    "stun": "mech_name.stun", "thunder_mark": "mech_name.thunder_mark", "wind": "mech_name.wind",
    "zhan_yi": "mech_name.zhan_yi", "zhan_yi_cash": "mech_name.zhan_yi_cash", "zhan_yi_fury": "mech_name.zhan_yi_fury",
}
_MECH_CN = _T.names(_MECH_KEYS, prefix="mech_name")

# ★ B 批 B-1（2026-09-17）：本表已搬进**文案真源**（`content/data/text_specs.json` 的
#   `effect_name.*`，分类「效果名」）。代码侧只留读口 —— 值与搬前逐字相等（47 键等价性见
#   `tests/` 与本批 LANDING）；未登记 → 原样返回 id（= 搬前 `.get(id, id)` 同义）。
_EFFECT_KEYS = {   # ★ B-1：效果 id → 文案键（文案真源 = text_specs.json 的 effect_name.*）
    "all_stat_cc": "effect_name.all_stat_cc", "arcane_field": "effect_name.arcane_field", "arcane_matrix": "effect_name.arcane_matrix",
    "arcane_shield": "effect_name.arcane_shield", "atk_all": "effect_name.atk_all", "atk_matk_all": "effect_name.atk_matk_all",
    "atk_up": "effect_name.atk_up", "atk_up_strong": "effect_name.atk_up_strong", "bless_shield": "effect_name.bless_shield",
    "block_reflect": "effect_name.block_reflect", "burn_burst": "effect_name.burn_burst", "cc_immune": "effect_name.cc_immune",
    "cleanse": "effect_name.cleanse", "cleanse_all": "effect_name.cleanse_all", "counter": "effect_name.counter",
    "crit_all": "effect_name.crit_all", "crit_hit_buff": "effect_name.crit_hit_buff", "crit_up": "effect_name.crit_up",
    "def_up": "effect_name.def_up", "disengage_dodge": "effect_name.disengage_dodge", "dodge_buff": "effect_name.dodge_buff",
    "dodge_reduce_all": "effect_name.dodge_reduce_all", "element_switch": "effect_name.element_switch", "hunt_team_dmg": "effect_name.hunt_team_dmg",
    "lifesteal": "effect_name.lifesteal", "matk_all": "effect_name.matk_all", "matk_up": "effect_name.matk_up",
    "matk_up_strong": "effect_name.matk_up_strong", "mon_atk_down": "effect_name.mon_atk_down", "protect": "effect_name.protect",
    "rage_burst": "effect_name.rage_burst", "reduce": "effect_name.reduce", "reduce_all": "effect_name.reduce_all",
    "reduce_shield_all": "effect_name.reduce_shield_all", "shadow_dance": "effect_name.shadow_dance", "shield_all": "effect_name.shield_all",
    "shield_all_reduce": "effect_name.shield_all_reduce", "shield_block": "effect_name.shield_block", "shield_self": "effect_name.shield_self",
    "spd_all": "effect_name.spd_all", "spd_buff": "effect_name.spd_buff", "spd_up": "effect_name.spd_up",
    "star_lock": "effect_name.star_lock", "stealth": "effect_name.stealth", "stealth_cc": "effect_name.stealth_cc",
    "taunt": "effect_name.taunt", "vuln": "effect_name.vuln",
}


def _effect_cn(eid) -> str:
    """效果名（真源 = 文案表 `effect_name.*`）；未登记 → 原样返回 id（= 搬前 `.get(id, id)` 同义）。"""
    key = _EFFECT_KEYS.get(str(eid))
    return _T.static(key) if key else str(eid)


_P_BUFF_KEYS = {   # ★ B-1：id → 文案键（文案真源 = text_specs.json 的 pbuff_name.*）
    "atk_down": "pbuff_name.atk_down", "atk_up": "pbuff_name.atk_up", "atk_up_big": "pbuff_name.atk_up_big",
    "atk_up_small": "pbuff_name.atk_up_small", "atk_up_strong": "pbuff_name.atk_up_strong", "block_pot": "pbuff_name.block_pot",
    "cc_immune": "pbuff_name.cc_immune", "counter": "pbuff_name.counter", "crit_dmg_pot": "pbuff_name.crit_dmg_pot",
    "crit_up": "pbuff_name.crit_up", "crit_up_big": "pbuff_name.crit_up_big", "crit_up_small": "pbuff_name.crit_up_small",
    "def_up": "pbuff_name.def_up", "dodge_pot": "pbuff_name.dodge_pot", "dodge_up": "pbuff_name.dodge_up",
    "echo_bless": "pbuff_name.echo_bless", "execute_pot": "pbuff_name.execute_pot", "food_atk_up": "pbuff_name.food_atk_up",
    "food_crit_up": "pbuff_name.food_crit_up", "food_def_up": "pbuff_name.food_def_up", "food_matk_up": "pbuff_name.food_matk_up",
    "food_spd_up": "pbuff_name.food_spd_up", "food_spd_up_small": "pbuff_name.food_spd_up_small", "freeze": "pbuff_name.freeze",
    "heal_up": "pbuff_name.heal_up", "lifesteal_pot": "pbuff_name.lifesteal_pot", "magic_resist": "pbuff_name.magic_resist",
    "matk_up": "pbuff_name.matk_up", "matk_up_pot": "pbuff_name.matk_up_pot", "matk_up_strong": "pbuff_name.matk_up_strong",
    "mon_atk_down": "pbuff_name.mon_atk_down", "mortal_wound": "pbuff_name.mortal_wound", "next_atk_up": "pbuff_name.next_atk_up",
    "pene_magi_pot": "pbuff_name.pene_magi_pot", "pene_pot": "pbuff_name.pene_pot", "revenge_atk": "pbuff_name.revenge_atk",
    "silence": "pbuff_name.silence", "spd_down": "pbuff_name.spd_down", "spd_up": "pbuff_name.spd_up",
    "spd_up_small": "pbuff_name.spd_up_small", "spellblade_surge": "pbuff_name.spellblade_surge", "stealth": "pbuff_name.stealth",
    "stun": "pbuff_name.stun", "thorns_pot": "pbuff_name.thorns_pot",
}
_P_BUFF_NAMES = _T.names(_P_BUFF_KEYS, prefix="pbuff_name")

_E_BUFF_KEYS = {   # ★ B-1：id → 文案键（文案真源 = text_specs.json 的 ebuff_name.*）
    "burn": "ebuff_name.burn", "def_down": "ebuff_name.def_down", "fire_mark": "ebuff_name.fire_mark",
    "freeze": "ebuff_name.freeze", "ice_mark": "ebuff_name.ice_mark", "mark": "ebuff_name.mark",
    "mon_atk_down": "ebuff_name.mon_atk_down", "mon_atk_up": "ebuff_name.mon_atk_up", "mon_atk_up_strong": "ebuff_name.mon_atk_up_strong",
    "mon_def_up": "ebuff_name.mon_def_up", "mon_spd_down": "ebuff_name.mon_spd_down", "mortal_wound": "ebuff_name.mortal_wound",
    "poison": "ebuff_name.poison", "shield": "ebuff_name.shield", "silence": "ebuff_name.silence",
    "sleep": "ebuff_name.sleep", "spd_down": "ebuff_name.spd_down", "spd_up": "ebuff_name.spd_up",
    "stun": "ebuff_name.stun", "summon": "ebuff_name.summon", "thunder_mark": "ebuff_name.thunder_mark",
}
_E_BUFF_NAMES = _T.names(_E_BUFF_KEYS, prefix="ebuff_name")

_STACK_KEYS = {   # ★ B-1：id → 文案键（文案真源 = text_specs.json 的 stack_name.*）
    "bless": "stack_name.bless", "burn": "stack_name.burn", "chi": "stack_name.chi",
    "iron": "stack_name.iron", "judge": "stack_name.judge", "mark": "stack_name.mark",
    "poison": "stack_name.poison", "rage": "stack_name.rage", "shadow": "stack_name.shadow",
    "shield": "stack_name.shield", "wind": "stack_name.wind",
}
_STACK_NAMES = _T.names(_STACK_KEYS, prefix="stack_name")

_ENEMY_MECH_STACKS = ("burn", "poison", "mark", "bleed")

_DEBUFF_NAMES = {
    "poison": "☠️毒", "burn": "🔥灼烧", "mark": "🎯标记", "bleed": "🩸流血",
}

_DF139_CLASS_FORMS = {
    "cls_zhan_shi": ("狂暴", "fury"),
}

_FINISHER139_OPTIONS = ("快刀", "满刃", "残血", "满段")

_ARCANE_FIELD_OPTIONS = ("盾", "刃")


class CombatCmds:
    """`game.commands.combat.CombatCmds` 的**类入口包内等价面**（B2-C1；接口表第 2 行「公开名」）。

    ⚠️ 常量表已**正位**（L7，2026-09-15）：13 张表是本模块的**模块级常量**（见本文件上方
    `_RAIN_WINDOW` …），**不是**本类的类属性 —— 本模块实现体是模块级函数、绑定后 `self` = 宿主壳，
    只有「模块级归属」才不依赖壳。本类只保留「名字」这一层（按名取件的等价面）；跨模块读者经
    `content.combat_cmds._EFFECT_CN` 取同一份（`content/player_cmds.py`）。值一字不改，
    改前/改后逐表 sha256 对拍见 `out/CONST_SHA.md`。

    命令方法本体不在这里 —— 它们是本模块的 **74 个模块级函数**（宿主壳逐个转发调它们）。
    """

    # 13 张常量表已下移为**模块级常量**（见本文件上方 `_RAIN_WINDOW` …）：L7 正位，本类不再持有、壳侧零痕迹。


class _PoiDom:
    """`content/effects/poi_effects.py` 的 `dom` 替身（该文件头 §② 契约：内容域访问）。

    真源 = 宿主薄聚合层 `C`；本文件按调用方契约给**包内等价物**（逐名到包内家，名字集由
    `out/evidence/poi_contract.txt` 的 AST 扫描定全 —— 漏名即 AttributeError）：
    `pools`（文案池）· `living_members` / `set_alive`（副本名单视图）·
    `resolve` / `display` / `roll_blueprint` / `generate_equip`（函数读口）。
    """

    @staticmethod
    def pools(name):
        return getattr(_cr, name)

    living_members = staticmethod(_IR.living_members)
    set_alive = staticmethod(_IR.set_alive)
    resolve = staticmethod(_resolve)
    display = staticmethod(_display)

    @staticmethod
    def roll_blueprint(*args, **kwargs):
        return _drops("roll_blueprint")(*args, **kwargs)

    @staticmethod
    def generate_equip(*args, **kwargs):
        return _drops("generate_equip")(*args, **kwargs)



# ============================================================
# ② 模块级常量 / 纯函数（逐字搬自宿主 combat.py 顶层；原文顺序）
# ============================================================


_battle_locks = set()


WORLD_BOSS_DOT_INTERVAL = 4


def _curve_vals(fn, cur: int, mx: int) -> list:
    """按 Lv.1→满级逐级取值；折线级数(满级>5)按『当前级/满级』压缩（鱼鱼偏好显示宁砍不堆）。"""
    mx = min(max(mx, 1), 5)
    if mx <= 1 or cur < 1:
        return []
    if mx <= 5:
        return [fn(lv) for lv in range(1, mx + 1)]
    return [fn(1), fn(max(cur, 1)), fn(mx)]


def _fmt_mult(v) -> str:
    """条件倍率紧凑格式：×1.2 / ×1.15（去尾零）"""
    s = f"{v:g}"
    return s


def pet_battle_status_note(pet: dict | None) -> str:
    """v110 P0（#119 宠物不动）：宠物战斗可用性提示（显示层）。

    宠物 Lv≥10 才解锁战斗技能、饱食度 =0 时技能失效（设计 24 章四/五）——
    此前玩家只看到『宠物不出手』没有任何解释（意见 #119 宠物不动了 +
    #21/#117 喂养匹配不上/列表看不见的连锁）。返回一行提示，无则空串。"""
    if not pet:
        return ""
    try:
        lv = int(pet.get("level", 0) or 0)
        sat = int(pet.get("satiety", 0) or 0)
        name = pet.get("name") or "宠物"
        if lv >= int(_b143.PET_SKILL_UNLOCK_LV) and sat <= 0:
            return (f"🐾 {name} 饿得没力气战斗了……『喂养 <食物>』（肉/鱼/草药）恢复饱食度！")
        if lv < int(_b143.PET_SKILL_UNLOCK_LV):
            return f"🐾 {name} 还小（Lv.{lv}），Lv.{int(_b143.PET_SKILL_UNLOCK_LV)} 解锁战斗技能！"
    except Exception:
        pass
    return ""


WORLD_BOSS_DROPS = {
    "巨史莱姆王·咕噜咕噜": ["mat_zhan_hun_zhi_chen", "mount_steed"],
    "百族战魂·奥德里克残影": ["mat_xing_lang_pi", "mat_mu_ying_long_hun", "mount_steed", "mount_wolf",
                            "mat_bai_zu_hui_zhang"],  # v104 M08 P1-7：百族徽章（策划案 7.3"国战参与"——世界 Boss 讨伐=国战玩法）
    "海蛇王·深渊之鳞": ["mat_ao_lan_zhi_zhu", "mat_mo_luo_zhi_guan", "mount_wolf", "mount_ghost"],
    "地底恶魔·黑炎": ["mat_ao_lan_zhi_zhu", "mat_mo_luo_zhi_guan", "mount_ghost", "mount_warhorse"],
    "风暴龙王·裂空": ["mat_ao_lan_zhi_zhu", "mat_mo_luo_zhi_guan", "mount_warhorse", "mount_griffin"],
    "古龙·奥姆之影": ["mat_ao_lan_zhi_zhu", "mat_mo_luo_zhi_guan", "mat_chen_xi_zhi_guan", "mount_warhorse", "mount_griffin"],
}


_RESOURCE_KEYS = {   # ★ B-1：id → 文案键（文案真源 = text_specs.json 的 resource_name.*）
    "arcane": "resource_name.arcane", "chi": "resource_name.chi", "cp": "resource_name.cp",
    "energy": "resource_name.energy", "faith": "resource_name.faith", "lian_duan": "resource_name.lian_duan",
    "melody": "resource_name.melody", "rage": "resource_name.rage", "zhan_yi": "resource_name.zhan_yi",
}
RESOURCE_STACK_CN = _T.names(_RESOURCE_KEYS, prefix="resource_name")


def resource_stack_text(effects) -> str:
    """effects 容器 → 职业资源叠层文本（'战意 5/10层 连段 3/10层'；无/空 → ''）。

    v181.M-R3：野外/副本/世界 Boss 面板的资源条统一入口——白名单 key 取 stacks，
    cap 查 EFFECT_RULES[key].cap（config 未挂载时容错空表；未声明 cap 只显 'N层'）。
    纯读函数，不依赖 battle 类型/self，副本 footer（snap.effects）与战斗 footer
    （actor.effects）共用。
    """
    if not isinstance(effects, dict) or not effects:
        return ""
    rules = {}
    try:
        from saintess_engine import config as _b2c
        rules = _b2c.get_effect_rules() or {}
    except Exception:
        rules = {}
    parts = []
    for k, cn in RESOURCE_STACK_CN.items():
        ent = effects.get(k)
        if not isinstance(ent, dict):
            continue
        try:
            n = int(ent.get("stacks", 0) or 0)
        except Exception:
            n = 0
        if n <= 0:
            continue
        cap = (rules.get(k) or {}).get("cap")
        parts.append(f"{cn} {n}/{int(cap)}层" if cap else f"{cn} {n}层")
    return " ".join(parts)


def _res_display_name(key: str) -> str:
    """资源/效果 key → 展示中文名（v181.M-R2b 单源：EFFECT_RULES[key].name，无条目兜底 key）。

    旧数据源 core_resources.py（按职业主资源取名 + engine.core_resource_def 按 class 查）已退役删除——
    （M-R2b 函数退役，M-R2c 文件本体删除；现网名单源 = EFFECT_RULES）
    res_cost/res_gain 的 key 直查 EFFECT_RULES（energy→精力 / zhan_yi→战意 / faith→信仰值…，
    cap 亦同表）。读数据表本体而非 config 挂载，保证脱战/技能列表等命令上下文不依赖挂载时机。
    """
    try:
        from .catalog_rules import EFFECT_RULES as _ER   # ★ B16-W11b：包内门面（真源 rules/effect_rules.json，85 条逐值+键序同）
        _n = (_ER.get(key) or {}).get("name")
        return _n or key
    except Exception:
        return key



# ============================================================
# ③ 类方法（65 个：命令 15 / 私有 50）—— 逐字搬自宿主 `class CombatCmds`
# ============================================================


def _target_by_label(b, raw: str):
    """站位图编号 → actor（`a2`/`A2`/`2` = 敌方第 2 个；`b1` = 我方第 1 个）。

    编号与站位图**同源**：`saintess_engine.formation.numbered_units`（存活单位、rank 升序 + 层内原序）。
    """
    from saintess_engine.formation import numbered_units
    s = (raw or "").strip()
    if not s:
        return None
    m = re.match(r"^([abAB])\s*(\d+)$", s)
    if m:
        side = "enemy" if m.group(1).lower() == "a" else "player"
        n = int(m.group(2))
    elif s.isdigit():
        side, n = "enemy", int(s)            # 纯数字 = 敌方第 n 个（与面板引导「打2号(纯数字同义)」一致）
    else:
        return None
    for num, u in numbered_units(_sides_of_x(b).get(side) or []):
        if num == n:
            return u
    return None


def _sides_of_x(b) -> dict:
    """战斗对象或 battle_state dict 都取到 sides（命令层两条路径都用得到）。"""
    if isinstance(b, dict):
        return b.get("sides") or {}
    return getattr(b, "sides", None) or {}


def _resolve_target_arg(b, raw):
    """『攻击 <名字>』/『技能1 a2』的目标串 → **actor dict**（引擎 `ActCtx.target` 只认 actor）。

    ★ 2026-09-13 P1 修复（B10 收口批 L5 线发现；**改前既有**）：命令层原来把 `target_arg`
    字符串直传 `human_act(target=...)`，而 v181 引擎在伤害/治疗落地时做 `target.get("hp")`
    → `AttributeError: 'str' object has no attribute 'get'`；而站位图面板一直教玩家
    『技能1 a2』（`_battle_footer` 的引导行）—— 玩家照做即报错。

    解析顺序（只认**存活**单位，与站位图编号同源）：
      ① 编号 `a1/a2…`（敌）/`b1/b2…`（己） ② 纯数字 = 敌方第 n 个
      ③ 名字：精确 → 前缀 → 包含（先敌后己）
    解析不到 → `None` = 自动选敌（与无参写法一致；**不再把字符串丢给引擎**）。
    `b` 可以是 Battle 对象或 battle_state dict。
    """
    s = (raw or "").strip()
    if not s:
        return None
    u = _target_by_label(b, s)
    if u is not None:
        return u
    _sd = _sides_of_x(b)
    cands = list(_sd.get("enemy") or []) + list(_sd.get("player") or [])
    alive = [x for x in cands if isinstance(x, dict) and (x.get("hp", 0) or 0) > 0]
    for pick in (lambda n: n == s, lambda n: n.startswith(s), lambda n: s in n):
        for x in alive:
            if pick(str(x.get("name") or "")):
                return x
    return None


def _b_enemy(self, b) -> dict:
    """命令层读当前敌方 actor（显示/结算用；sides['enemy'] 首个存活，无 → {}）。

    v181.P4：Battle 不再暴露 enemy 主怪代理——命令层自己从 actor 组读。"""
    try:
        acts = (getattr(b, "sides", None) or {}).get("enemy") or []
        for _u in acts:
            if _u.get("hp", 0) > 0:
                return _u
        return acts[0] if acts else {}
    except Exception:
        return {}

async def explore(self, event: AstrMessageEvent, group_id, qq_id, player):
    # v87.2 副本地图化：副本地图模式（mode=map）→ 副本内探索
    inst_row = self._instance_battle_for(group_id, qq_id)
    if inst_row and (inst_row["state"].get("mode") == "map" or inst_row["state"].get("rooms")):
        async for _r in self._instance_explore(event, group_id, qq_id, inst_row):
            yield _r
        return
    # v104 M24 P2：战斗中禁止探索。_in_battle 内部查 db.get_battle（battle_state 按 qq 全局，
    # 跨群/私聊同样命中）+ 内存锁 + 副本队员锁（_instance_battle_for，批次1 M04 加固）；
    # 上方副本 map 模式分支先行放行属 v87.2 设计（副本内探索），普通/副本刻制战斗在此拦截。
    if self._in_battle(group_id, qq_id):
        # O121 Boss 战不提示『逃跑』（无法逃跑，防误导）
        _bt = db.get_battle(group_id, qq_id) or {}
        _is_boss = bool((_bt.get("state") or {}).get("enemy", {}).get("is_boss"))
        yield event.plain_result(_T.static("ex.in_battle") + ("" if _is_boss else _T.static("ex.battle_hint")))
        return
    cur = player["cur_map"]
    if cur.startswith("home_"):
        yield event.plain_result(_T.static("ex.at_home"))
        return
    cur_map = _cs.MAP_BY_ID[cur]
    # 城镇区域（安全区）：可触发 POI，无怪
    if cur_map.get("type") == _cc.MAP_TYPE_TOWN:
        # v105 M23 P2-1：冷却 key 去掉 group_id——玩家数据全局化（battle 按 qq 全局），
        # 原 key 含群号可跨群绕过：A 群刷完 B 群立刻再刷，城镇 POI 每小时可白嫖约 60 次（60s 冷却）
        _town_cd_key = f"town_explore_cd_{qq_id}"
        try:
            _last_town = float(db.get_event_state(_town_cd_key) or 0)
        except Exception:
            _last_town = 0
        if time.time() - _last_town < 60:
            yield event.plain_result(_T.static("ex.town_quiet"))
            return
        db.set_event_state(_town_cd_key, str(time.time()))
        cur_sa_id_poi = player.get("cur_subarea") or ""
        poi_hit = roll_poi(group_id, qq_id, cur, cur_sa_id_poi, chance=0.15)
        if poi_hit:
            poi_id, poi = poi_hit
            # v105 M23 P2-3：POI 每日重置（策划案 02 章 7.6 阶段 D）——本日已触发则本次不再触发
            if self._poi_daily_used(group_id, qq_id, cur, cur_sa_id_poi, poi_id):
                poi_hit = None
            else:
                poi_text = self._handle_poi(group_id, qq_id, player, cur_map, poi_id, poi)
                yield event.plain_result(poi_text)
                return
        yield event.plain_result(
            _T.text("ex.town_walk", map=cur_map['name'])
        )
        return
    # v95.26 #265：副本区域探索不触发普通战斗——副本怪按组队强度设计（如海蚀洞窟
    # 入口子区域怪物池含 Lv.26 海盗精锐），单人遭遇必死；且探索打赢也不计入副本进度
    # （#247 只修了 Boss 混池/精英判定，普通怪池仍会单人遭遇副本怪）。
    # 副本入口应引导玩家走『副本 <名字>』开本流程（等级/人数校验 + 组队轮流 + 通关结算）。
    # v105 M19 P0：主线击杀目标只挂载在副本类地图（q3_3/q6_2/q9_4/q10_1/q12_1/q12_2）
    # 时，探索放行——主线目标 Boss/精英走下方 SA_BOSS_CHANCE 独立判定，保证主线可单人推进
    # （否则第 3 章 q3_3 起主线击杀任务永远卡死）。
    if cur_map.get("type") == _cc.MAP_TYPE_INSTANCE and not self._main_kill_target_on_map(group_id, qq_id, cur_map):
        inst_name = cur_map.get("name", "这个副本")
        yield event.plain_result(
            _T.text("ex.inst_party", name=inst_name, name2=inst_name)
        )
        return
    # 9.4：野外 NPC 偶遇（满足条件 → 偶遇提示，不消耗探索；30 分钟冷却防刷）
    # v140 波2：野王看守宝箱——探索优先命中当前图野王（在场则进入战斗，优先级最高）
    _king = explore_king(group_id, qq_id, cur)
    if _king:
        if _king.get("killed"):
            # 已被击杀：宝箱在原地，提示摸箱
            yield event.plain_result(wild_king_summary(cur))
            return
        # 野王在场：构造野王战斗（血量弹性按参战人数）→ 保存战斗状态
        monster = build_king_monster(_king, cur_map, player)
        group = build_monster_group(monster, cur_map, player, scale_main=False)
        b = self._open_battle(player, group, "monster", group_id=group_id, qq_id=qq_id)
        db.save_battle(group_id, qq_id, b.to_state())
        self._lock_battle(group_id, qq_id)
        _acts = _T.static("ex.act_hint")  # 野王=Boss 战，不可逃跑
        yield event.plain_result(
            _T.text("ex.wildking", name=monster['name'], killer=_king.get('icon', '👑'), lv=monster['lv'],
                hp=monster['hp'], panel=self._battle_formation_panel(player, b))
            + (f"{self._resource_line(player, b)}\n" if self._resource_line(player, b) else "")
            + _T.text("ex.chest_tip", tail=_acts)
        )
        return
    wild = roll_wild_encounter(group_id, qq_id, player, cur)
    if wild:
        nid, wnpc = wild
        _ta = "她" if wnpc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别
        _dur = int(wnpc.get("duration", 60) or 60)  # v127.5 限时NPC：在场分钟数
        yield event.plain_result(
            _T.text("ex.wildnpc", where=cur_map['name'], name=wnpc['icon'], desc=wnpc['name'],
                line=wnpc.get('desc', ''), npc=wnpc.get('dialogue', '……'), who=wnpc['name'],
                when=_ta, min=_ta, tail=_dur)
        )
        return
    # v87 02 章 7.6：POI 探索点独立判定（15%）
    # v87.9 修复：放在随机事件之前——事件命中直接 return 会吞掉 POI 判定，导致挂载了却探索不到
    # v94 体力：野外探索消耗 1 体力（偶遇 NPC 不消耗）；v101.13 坐骑 stamina_reduce 概率免费（流程照常，只免体力）
    _stam_cost = 0 if random.random() < float(_mount_effects(player).get("stamina_reduce", 0) or 0) else 1
    if _stam_cost > 0:
        _ok, _st = self._spend_stamina(group_id, qq_id, _stam_cost, player, "探索")
        if not _ok:
            yield event.plain_result(_st)
            return
    # v115 今日奇遇：取当前野外图的当日效果（无奇遇返回 {}，A/C 未就绪时 getattr 兜底）
    _fx = today_event_effects(cur)
    # v115 隐藏房间探索计数：每次野外探索成功扣体力后累加（A 提供的 bump_explore_count）
    _bump_fx = _bump_explore_count
    if _bump_fx is not None:
        try:
            _bump_fx(group_id, qq_id, cur)
        except Exception:
            pass
    cur_sa_id_poi = player.get("cur_subarea") or ""
    poi_hit = roll_poi(group_id, qq_id, cur, cur_sa_id_poi, chance=0.15)
    if poi_hit:
        poi_id, poi = poi_hit
        # v105 M23 P2-3：POI 每日重置——本日已触发则该 POI 本次不触发，继续后续事件/遇怪流程
        if self._poi_daily_used(group_id, qq_id, cur, cur_sa_id_poi, poi_id):
            poi_hit = None
        else:
            poi_text = self._handle_poi(group_id, qq_id, player, cur_map, poi_id, poi)
            yield event.plain_result(poi_text)
            return
    # v105 M23 P1-1：探索彩蛋独立判定（02 章 7.5『总概率 0.5%』）——原实现嵌在
    # _handle_explore_event 的 35% 事件窗口内（实际 0.35×0.005=0.175%），移出到
    # 遇怪/事件/彩蛋三路并列，命中直接返回，恢复策划案 ~0.5% 总概率
    egg = roll_explore_egg(cur_map.get("id"))
    if egg:
        EventContext, execute_event_template = _ET.EventContext, _ET.execute_event_template
        egg_ctx = EventContext(group_id, qq_id, player, cur_map,
                               params=egg.get("params", {}), name=cur_map.get("name", "此地"),
                               hooks={"title_bonus": lambda q: self._title_bonus(group_id, q)})
        egg_text = execute_event_template(egg["template"], egg_ctx)
        if egg_text:
            yield event.plain_result(egg_text)
            return
    # 探索随机事件（野外/外郊/核心区 35% 概率，事件优先于遇怪）
    _ev_chance = _cc.ENCOUNTER_EVENT_CHANCE
    if self._rain_boost(group_id, qq_id):
        # v104 M23：『突如其来的雨』30 分钟窗口内探索遇怪率 +15%（事件概率让渡给遇怪）
        _ev_chance = max(0.0, _ev_chance - 0.15)
    # v115 今日奇遇：事件率叠加 event_chance（clamp 到 [0, 0.6]，在 rain_boost 调整后叠加）
    _ev_chance += _fx.get("event_chance", 0)
    # v130.7 意见#28 越级风险增强：地图等级高于玩家时，探索事件率随等级差叠加
    # （每高 1 级 +5%，最高 +25%；0.35+0.25=0.60 刚好顶格下方 clamp）
    _lv_gap = (cur_map.get("lv") or 1) - (player.get("level") or 1)
    if _lv_gap > 0:
        _ev_chance += min(_lv_gap * 0.05, 0.25)
    _ev_chance = min(0.6, max(0.0, _ev_chance))
    if random.random() < _ev_chance:
        handled, ev_text = self._handle_explore_event(group_id, qq_id, player, cur_map, _fx=_fx)
        if handled:
            yield event.plain_result(ev_text)
            return
    # v105 M23 P1-3：空探索作为独立结果类型进入流程——事件窗口未命中后 25% 空手而归并
    # fire explore_done 规则。原 4 条 explore_done 规则（luck/ghost/scenery/coin）挂在
    # 下方『无 events 且无 elite/boss』死分支（v95r38 空池保护接管后 203 个野外子区域
    # 全有怪 → 分支不可达，规则 100% 死规则），现经此路径复活。
    if random.random() < max(0.05, 0.25 - _fx.get("encounter_rate", 0)):
        _rule_txt = self._rule_fire('explore_done', group_id, qq_id, player, cur_map, {'event': 'empty'})
        yield event.plain_result(_T.static("ex.nothing")
                                 + (f"\n{_rule_txt}" if _rule_txt else ""))
        return
    # 探索事件池（v86 子区域：用当前子区域的怪物，无则回退地图级）
    cur_sa = None
    cur_sa_id = player.get("cur_subarea") or ""
    for _sa in (cur_map.get("subareas") or []):
        if _sa["id"] == cur_sa_id:
            cur_sa = _sa
            break
    events = []
    mon_src = (cur_sa.get("monsters") if cur_sa else None)
    if mon_src is None:
        mon_src = cur_map.get("monsters", [])
    # v105 M19 P0：副本类地图若挂载当前主线击杀目标（Boss/精英），放行其遭遇判定
    # v110 审计修复：放宽到全部图型——q11_3 击杀目标「枢机主教·奥古斯都」只挂载于
    # 野外图 dawn_cathedral_3 的 monsters 池（role=boss），原仅 INSTANCE 图计算
    # main_target → 该 Boss 被普通池排除后无任何遭遇路径，主线第 11 章卡死
    #（实测 400 次探索 0 遭遇；v104 记录的"被 Lv94 秒杀"为旧版行为，v105 M19 后反转为永不出）
    main_target = None
    boss_target = None
    main_target = self._main_kill_target_on_map(group_id, qq_id, cur_map)
    for mid, name, role, lv, skills, drops in mon_src:
        # v95.23 #247：role=boss 条目不进普通怪池（boss 字段有独立判定 SA_BOSS_CHANCE），
        # 否则副本入口等区域探索 random.choice 会抽中 Boss → 无法逃跑被秒杀
        if role == "boss":
            # v105 M19 P0：主线目标 Boss（如 q3_3 海盗王·独眼杰克）单独走
            # SA_BOSS_CHANCE 判定，不混普通池
            if main_target and name == main_target[1]:
                boss_target = (mid, name, role, lv, skills, drops)
            continue
        events.append(("monster", (mid, name, role, lv, skills, drops)))
    # 精英/Boss：子区域优先，回退地图级
    sa_elite = (cur_sa.get("elite") if cur_sa else None) or cur_map.get("elite")
    sa_boss = (cur_sa.get("boss") if cur_sa else None) or cur_map.get("boss")
    # v95.23 #247：副本区域探索不触发精英/Boss 独立判定——副本 Boss 只能走『副本 <名字>』
    # 开本流程（有等级/人数校验和通关结算），探索撞 Boss 打赢也不计入副本进度，纯坑玩家
    # v105 M19 P0：但主线击杀目标只挂副本时放行——否则主线 q3_3 起 6 个击杀任务永远卡死
    if cur_map.get("type") == _cc.MAP_TYPE_INSTANCE:
        if main_target:
            if main_target[2] == "boss":
                sa_boss = boss_target or sa_boss
            elif main_target[2] == "elite":
                sa_elite = main_target
        else:
            sa_elite = None
            sa_boss = None
    # v102.1 移除：'城镇外郊' 类型不存在于数据（maps.py 仅 城镇区域/副本/野外/隐藏区域），
    # 该分支恒 False 从未执行（历史遗留自 82abbde 红名系统，数据层重写后成孤儿）
    # v95r38 空池保护：纯精英/Boss 房（如野猪王巢）探索不报"什么也没发现"，由下方必遇逻辑接管
    if not events and not sa_elite and not sa_boss:
        _rule_txt = self._rule_fire('explore_done', group_id, qq_id, player, cur_map, {'event': 'empty'})
        yield event.plain_result(_T.static("ex.nothing")
                                 + (f"\n{_rule_txt}" if _rule_txt else ""))
        return
    # v87 04 章十六节：隐藏怪物独立判定（低概率彩蛋怪，优先级最高）
    hm = self._roll_hidden_monster(group_id, qq_id, player, cur_map)
    if hm:
        monster, tag, flavor = hm
        # v2 多对多：隐藏怪经 build_monster_group 生成敌方阵列（精英带爪牙）后传入 Battle
        group = build_monster_group(monster, cur_map, player)
        b = self._open_battle(player, group, "monster", group_id=group_id, qq_id=qq_id)
        db.save_battle(group_id, qq_id, b.to_state())
        self._lock_battle(group_id, qq_id)
        _boons = player.get("_battle_boons") or {}
        _bl = _boons.get("echo_bless")
        bless_note = ""
        if _bl and _bl.get("mult"):
            _pct = int(round((float(_bl["mult"]) - 1.0) * 100))
            bless_note += _T.text("ex.echo_bless", pct=_pct)
        _pb = player.get("poi_buff")
        if _pb:
            _pct_pb = int(round((float(_pb.get("mult", 1.10)) - 1.0) * 100))
            bless_note += _T.text("ex.shrine_bless", text=_pb.get('name', _pb['stat']), pct=_pct_pb)
        # O121 Boss 战隐藏『逃跑』选项（引擎/命令层均禁逃，防误导）
        _acts = _T.static("ex.act_hint") + ("" if monster.get("is_boss") else _T.static("ex.act_hint2"))
        yield event.plain_result(
            _T.text("ex.hidden", mark=tag, name=monster['name'], lv=monster['lv'], desc=flavor,
                tail=self._battle_formation_panel(player, b))
            + (f"{self._resource_line(player, b)}\n" if self._resource_line(player, b) else "")
            + f"{bless_note}━━━━━━━━━━━━\n"
            f"你的行动：{_acts}"
        )
        return
    # 随机遇怪：精英/首领独立保底判定（不混进普通怪池子玄学抽）
    monster = None
    tag = ""
    stam_warn = ""
    double = False
    eb = self._mount_explore_bonus(player)
    # v115 今日奇遇：精英遭遇率叠加 elite_chance
    if sa_elite and (random.random() < (0.08 + eb + _fx.get("elite_chance", 0)) or not events):
        monster = build_monster(sa_elite, cur_map)
        tag = _T.static("ex.elite_tag")
    elif sa_boss and (random.random() < _cc.SA_BOSS_CHANCE or not events):
        monster = build_monster(sa_boss, cur_map)
        tag = "👑 BOSS"
        # v95.20 #101：Boss 战无法逃跑且每刻耗体力，体力低时预警，避免中途耗尽被困
        if (player.get("stamina") or 0) < 20:
            stam_warn = _T.text("ex.boss_stamina", stamina=player.get('stamina'))
    elif events:
        # v101.25c 怪物等级波动：普通怪 ±1 级（精英/Boss 固定）——同图练级不单调
        # v130.8 意见#32：±1 感知弱 → 增强为 ±2；v132 鱼鱼拍板改回 ±1（"随机等级大概在正负1就行了"，
        # 面板已明示 Lv.X±1 → 波动感知由展示层承担，数值层收敛防等级飘移）
        monster = build_monster(random.choice(events)[1], cur_map, lv_jitter=1)
        # v2 多对多：普通怪 60% 单只 / 40% 双只——用确定性哈希决定（v103 铁律：不新增 random
        # 调用点；monster_id+lv 唯一确定同一只怪是否双只，不改变既有 random 调用顺序/结果）
        _double = hash(monster.get("id", "") + "_" + str(monster.get("lv", 0))) % 100 < 40
        double = _double
    # v105 M23 P3-9：删除原 else 兜底死代码——空池+无 elite/boss 已在上方提前 return；
    # 纯精英/Boss 房（events 空）由上方 sa_elite/sa_boss 的 `or not events` 保底必命中，else 理论不可达
    # 遇普通怪但此地有精英/Boss → 提示气息（刷精英的方向感）
    hint = ""
    if not tag:
        if sa_elite:
            # #242: 精英气息提示 10 分钟冷却——迷雾沼泽等地图此前连续 6 次探索全刷提示
            _hint_key = f"elite_hint_{group_id}_{qq_id}"
            _last_hint = 0
            try:
                _last_hint = int(db.get_event_state(_hint_key) or 0)
            except Exception:
                pass
            if time.time() - _last_hint > 600:
                hint = _T.text("ex.elite_near", name=sa_elite[1])
                try:
                    db.set_event_state(_hint_key, str(int(time.time())))
                except Exception:
                    pass
        elif sa_boss:
            hint = _T.text("ex.boss_near", name=sa_boss[1])
    # 保存战斗状态（v9 统一引擎）
    # v2 多对多：经 build_monster_group 生成敌方阵列（普通怪 single/double；精英带爪牙；
    # Boss 带 2 爪牙）后传入 Battle 构造（enemies 参数）
    group = build_monster_group(monster, cur_map, player, double=double)
    b = self._open_battle(player, group, "monster", group_id=group_id, qq_id=qq_id)
    db.save_battle(group_id, qq_id, b.to_state())
    self._lock_battle(group_id, qq_id)
    _boons = player.get("_battle_boons") or {}
    _bl = _boons.get("echo_bless")
    bless_note = ""
    if _bl and _bl.get("mult"):
        _pct = int(round((float(_bl["mult"]) - 1.0) * 100))
        bless_note += _T.text("ex.echo_bless", pct=_pct)
    _pb = player.get("poi_buff")
    if _pb:
        _pct_pb = int(round((float(_pb.get("mult", 1.10)) - 1.0) * 100))
        bless_note += _T.text("ex.shrine_bless", text=_pb.get('name', _pb['stat']), pct=_pct_pb)
    role_mark = tag or ("👑 BOSS" if monster["is_boss"] else (_T.static("ex.elite_tag") if monster["is_elite"] else "🐾"))
    # v104 修复（M06 P2-2）：展示 MONSTER_MODS 个体特色文案（此前只有数值生效，玩家看不到）
    mod_line = f"📜 {monster['mod']}\n" if monster.get("mod") else ""
    # O121 Boss 战隐藏『逃跑』选项（引擎/命令层均禁逃，防误导）
    _acts = _T.static("ex.act_hint") + ("" if monster.get("is_boss") else _T.static("ex.act_hint2"))
    # v110 P0（#119 宠物不动）：遭遇瞬间就提示宠物为何无法出手（饿肚子/Lv 不足），
    # 不必等进战斗页脚——第一眼就消除『宠物怎么不动了』的困惑。
    _pet_note = pet_battle_status_note(getattr(b, "pet", None))
    yield event.plain_result(
        _T.text("ex.battle", mark=role_mark, name=monster['name'], lv=monster['lv'], tail=mod_line,
            tail2=self._battle_formation_panel(player, b))
        + (f"{self._resource_line(player, b)}\n" if self._resource_line(player, b) else "")
        + f"{bless_note}━━━━━━━━━━━━\n"
        + (f"{_pet_note}\n" if _pet_note else "")
        + _T.text("ex.turn", tail=_acts)
        + f"{hint}{stam_warn}"
    )

async def wild_king_chest(self, event: AstrMessageEvent, group_id, qq_id, player):
    """v140 波2：野王看守宝箱——『摸宝箱』/『摸战利箱』开箱。

    前置：当前地图野王已被击杀（宝箱解锁）。击杀者（队伍）优先 15 分钟战利箱，
    之后转公共箱（同图每人 1 次）；每人每时段最多 1 次、每日最多 2 次；
    个人连续 3 时段参与未开箱 → 第 4 时段保底券（不占次数）。
    """
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("chest.in_battle"))
        return
    cur = player.get("cur_map") or ""
    if cur.startswith("home_"):
        yield event.plain_result(_T.static("chest.at_home"))
        return
    try:
        text, need_bc = open_chest(group_id, qq_id, cur)
    except Exception:
        text = _T.static("chest.locked")
        need_bc = False
    yield event.plain_result(text)
    if need_bc:
        try:
            await self._broadcast(text.split("\n")[0] + "\n" + "\n".join(text.split("\n")[1:3]))
        except Exception:
            pass

def _main_kill_target_on_map(self, group_id, qq_id, cur_map):
    """v105 M19 P0：当前 active 主线击杀目标怪是否挂载于本副本地图。

    副本类地图『探索』默认拦截、移动撞怪默认跳过（组队强度设计，v95.23/26），
    但主线击杀目标（q3_3 海盗王·独眼杰克 / q6_2 古王·奥德里克 / q9_4 恶魔祭司·赫尔加 /
    q10_1 封印守卫(腐蚀) / q12_1 深渊猎犬 / q12_2 蚀夜(真相形态)）只挂载在
    type=副本 的地图上——不放行则主线第 3 章即断。命中返回怪物条目（扁平 6 元组），
    未命中返回 None（维持原有拦截/跳过）。
    """
    try:
        quests = db.get_quests(group_id, qq_id)
    except Exception:
        return None
    if not quests or quests.get("main_status") != "active":
        return None
    mid = quests.get("main_quest")
    mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mid), None) if mid else None
    if not mq:
        return None
    target = (mq.get("objective") or {}).get("kill")
    if not target:
        return None
    for sa in (cur_map.get("subareas") or []):
        for ent in (sa.get("monsters") or []):
            if ent and len(ent) >= 2 and ent[1] == target:
                return ent
        for _f in ("elite", "boss"):
            ent = sa.get(_f)
            if not ent:
                continue
            # elite/boss 字段为扁平 6 元组；兼容历史嵌套写法
            _e = ent[0] if isinstance(ent[0], (list, tuple)) else ent
            if _e and len(_e) >= 2 and _e[1] == target:
                return _e
    return None

def _in_battle(self, group_id, qq_id):
    # v28：锁按 qq_id 全局维度（玩家数据已全局化，群/临时会话共用同一角色）。
    # 自愈：db 无战斗记录但内存锁残留时自动清除（跨群打完/异常中断导致）。
    # v87.2：副本撤退后（retreated）保留进度但不算战斗中
    db_battle = db.get_battle(group_id, qq_id)
    db_in_battle = db_battle is not None
    if db_battle and db_battle["state"].get("type") == "instance" and db_battle["state"].get("retreated"):
        db_in_battle = False
    key = str(qq_id)
    if not db_in_battle and key in _battle_locks:
        # v104 修复 M04：副本 battle 只存队长名下（队员 db 无记录是正常态），
        # 直接自愈清锁会让队员探索一次锁即消失，可双线野外战斗而 Boss 仍打他。
        # 自愈前检查是否在副本队伍战斗中（_instance_battle_for 内部查
        # db.party_members 找队长 + 队长有 type=instance 且未撤退的 battle）→ 保留锁。
        if self._instance_battle_for(group_id, qq_id):
            return True
        _battle_locks.discard(key)
        return False
    return key in _battle_locks or db_in_battle

def _lock_battle(self, group_id, qq_id):
    _battle_locks.add(str(qq_id))

def _unlock_battle(self, group_id, qq_id):
    _battle_locks.discard(str(qq_id))

def _open_battle(self, player: dict, enemies: list, btype: str = "monster",
                  group_id=None, qq_id=None, pet=None) -> "object":
    """开战构造（saintess_engine 四步仪式，N5b4-2 起探索/野王/普通遇怪/约战/塔统一走）。

    ① 开战仪式（player dict 侧：字段播种/max 重算/echo_bless/poi_buff 消费）
    ② 组 sides（player + 怪组）
    ③ 装备装配（weapon_effect + affix → actor.triggers，N9/N9.7 已支持）
    ④ 构造 Battle
    """
    tb = self._title_bonus(group_id, qq_id) if (group_id is not None and qq_id is not None) else {}
    _BR.prepare_player_for_battle(player, tb, _es_arg(db))
    sides = _BR.build_sides(player=player, enemies=enemies)
    # 装备词条 + 职业机制 + 外部增幅容器（序列收敛于 BR.apply_battle_loadout，
    # 与数值门禁 tests/numeric_sim.py 同源）
    for _a in sides.get("player", []):
        _BR.apply_battle_loadout(_a, tb)
    from saintess_engine import Battle as B2
    b = B2(btype, sides=sides, title_bonus=tb,
           pet=pet if pet is not None else db.pet_get(qq_id))
    # 流水采集（可拔插：未启用 DRAGONFALL_TLOG / 未 enable 时为 no-op，见 game/tlog_setup.py）
    return _attach_tlog(b, btype=btype, player=player, enemies=enemies)

def _restore_battle(self, state: dict) -> "object":
    """恢复 saintess_engine 战斗（from_state）。旧格式（无 sides）→ None（命令层清档重开）。"""
    if not isinstance(state, dict) or not state.get("sides"):
        return None
    from saintess_engine import Battle as B2
    return B2.from_state(state)

def _sync_battle_player(self, player: dict, b) -> None:
    """saintess_engine 行动后回写：actor（副本）→ player dict（命令层读它做 db/展示）。"""
    try:
        _f = b.focus() if hasattr(b, "focus") else None
        if _f:
            _BR.sync_player_from_actor(player, _f)
    except Exception:
        pass  # 回写异常不阻断（player 可能为空/半构造）

def _mount_explore_bonus(self, player) -> float:
    """v39 坐骑：骑乘中探索精英率提升"""
    mounts = player.get("mounts") or {}
    active_mk = mounts.get("active")
    if active_mk and active_mk in _cl.MOUNT_BY_KEY:
        return _cl.MOUNT_BY_KEY[active_mk].get("elite_bonus", 0)
    return 0.0

def _roll_hidden_monster(self, group_id, qq_id, player, cur_map):
    """v87 04 章十六节：隐藏怪物独立判定。

    按 HIDDEN_MONSTERS 表的 cond 匹配当前地图环境，chance 概率触发。
    返回 (monster, tag, flavor) 或 None。
    """
    mid = cur_map.get("id", "")
    # 时间系统时段（night 判定：用 time_weather.current_period）
    # v105 M23 P3-1：time_weather 只返回 morning/day/evening/night，原 ("night","深夜","夜晚")
    # 中后两个值永不可能（死代码），收敛为 == "night"
    is_night = False
    try:
        from .time_weather import current_period
        is_night = current_period() == "night"
    except Exception:
        pass
    # 地图环境分类（v98.3：数据化 → core/hidden_cond.py ENV_KEYWORDS）
    from .hidden_cond import envs_of, check_cond, HiddenCtx
    envs = envs_of(mid)
    if cur_map.get("type") == _cc.MAP_TYPE_TOWN:
        return None  # 城镇不出隐藏怪
    hctx = HiddenCtx(mid, cur_map, is_night, envs)
    for hid, hdef in _b143.HIDDEN_MONSTERS.items():
        # v97.6 区域限定：maps 字段指定地图 id 列表，当前图不在其中则跳过
        if hdef.get("maps") and mid not in hdef["maps"]:
            continue
        cond = hdef.get("cond", "any")
        if not check_cond(cond, hctx):
            continue
        # any / 未知：无限制
        if random.random() >= hdef.get("chance", 0.004):
            continue
        # 命中：构造怪物（等级 = 地图等级 + 偏移，clamp ≥1）
        base_lv = cur_map.get("lv", 1)
        lv = max(1, base_lv + hdef.get("lv_off", 0))
        monster_def = (hid, hdef["name"], hdef.get("role", "elite"), lv,
                       hdef.get("skills", []), hdef.get("drops", []))
        monster = build_monster(monster_def, cur_map)
        # 隐藏怪金币加成（gold_mult 倍）
        gold_extra = monster.get("gold", 0) * hdef.get("gold_mult", 1)
        monster["gold"] = gold_extra
        return monster, hdef.get("tag", "✨ 隐藏"), hdef.get("flavor", "")
    return None

async def wish(self, event: AstrMessageEvent, group_id, qq_id, player, opt):
    """流星许愿(02 章 7.5 探索彩蛋)：三选一祝福"""
    import json as _json, time as _time
    raw = db.get_event_state(f"wish_{group_id}_{qq_id}")
    if not raw:
        yield event.plain_result(_T.static("ws.no_meteor"))
        return
    try:
        st = _json.loads(raw)
    except Exception:
        st = {"ts": 0}
    if not isinstance(st, dict):
        # v95.39 #216：v83 曾把 value 写成 "wish_ts" 字符串（set_state 只认 "ts"），
        # 旧状态残留字符串会在这里崩 AttributeError——统一按过期处理
        st = {"ts": 0}
    if _time.time() - st.get("ts", 0) > 120:
        db.set_event_state(f"wish_{group_id}_{qq_id}", "")
        yield event.plain_result(_T.static("ws.gone"))
        return
    if opt not in ("经验", "金币", "材料"):
        yield event.plain_result(_T.static("ws.usage"))
        return
    db.set_event_state(f"wish_{group_id}_{qq_id}", "")
    if opt == "经验":
        need = _exp_to_next(player["level"]) - player["exp"]
        gain = max(20, int(need * 0.2))
        db.update_player(group_id, qq_id, exp=player["exp"] + gain)
        player = self._player(group_id, qq_id)
        player["_title_bonus"] = self._title_bonus(group_id, qq_id)
        lv_logs, _ = check_player_level_up(group_id, qq_id, player)
        tail = ("\n" + "\n".join(lv_logs)) if lv_logs else ""
        msg = _T.text("ws.exp", v=gain, tail=tail)
    elif opt == "金币":
        gain = 80 + player["level"] * 8
        db.update_player(group_id, qq_id, gold=player["gold"] + gain)
        msg = _T.text("ws.gold", v=gain)
    else:
        # v101.4：流星愿望材料池数据化 → data/poi_pools.py WISH_POOL
        mat = random.choice(_b143.WISH_POOL)
        mid = _resolve("materials", mat)
        if mid in _ci.MATERIALS:
            db.add_item(group_id, qq_id, mid,
                        {"name": _display("materials", mid), "type": "材料",
                         "stackable": True, "price": _ci.MATERIALS[mid]["price"]})
        msg = _T.text("ws.mat", v=_display('materials', mid))
    _check_achievements(group_id, qq_id, player, {"wish_met": True})
    yield event.plain_result(_T.text("ws.real", msg=msg))

async def trader_confirm(self, event: AstrMessageEvent, group_id, qq_id):
    """v113.5 O71：流浪商人强卖确认/拒绝——探索遇商人挂起报价
    （event_templates.tpl_merchant 写 trader_{gid}_{qid}）后，
    回复『确认购买』成交（扣金币+装备入包）或『拒绝』离开。"""
    import json as _json, time as _time, uuid
    raw = db.get_event_state(f"trader_{group_id}_{qq_id}")
    if not raw:
        yield event.plain_result(_T.static("tr.none"))
        return
    try:
        st = _json.loads(raw)
    except Exception:
        st = {"ts": 0}
    if not isinstance(st, dict):
        # 对齐 wish 的旧值兜底：非 dict 一律按过期处理
        st = {"ts": 0}
    if _time.time() - st.get("ts", 0) > 120:
        db.set_event_state(f"trader_{group_id}_{qq_id}", "")
        yield event.plain_result(_T.static("tr.gone"))
        return
    # v113.5 O71 实测修正：『确认购买』剥离指令后为空串，不能用剥离结果判分支——
    # 直接看原始消息（正则已限定只有 确认购买/拒绝 两种输入）
    opt = "确认购买" if "确认购买" in (event.get_message_str() or "") else "拒绝"
    db.set_event_state(f"trader_{group_id}_{qq_id}", "")
    if opt == "拒绝":
        yield event.plain_result(_T.static("tr.decline"))
        return
    equip = st.get("equip") or {}
    price = int(st.get("price", 0))
    player = self._player(group_id, qq_id)
    if player["gold"] < price:
        yield event.plain_result(_T.text("tr.poor", gold=player['gold']))
        return
    db.update_player(group_id, qq_id, gold=player["gold"] - price)
    db.add_item(group_id, qq_id, f"eq_{uuid.uuid4().hex[:8]}", equip)
    q = _b143.QUALITY.get(equip.get("quality", "white"), {})
    qtxt = q.get("color", "")
    yield event.plain_result(_T.text("tr.buy", gold=price, name=qtxt, x=equip.get('name', '装备')))

async def revive_confirm(self, event: AstrMessageEvent, group_id, qq_id):
    """O119 战败结算二段回复：消耗复活羽毛免扣金币 / 放弃复活损失金币。

    _handle_defeat 检测到背包有复活羽毛时，写 revive_choice_{gid}_{qid}
    （挂起金币扣款，先回城满血），玩家回复『使用复活羽毛』消耗 1 根免扣，
    『放弃复活』按原损失结算；超时 5 分钟按损失金币兜底（防白嫖免罚）。"""
    import json as _json
    import time as _time
    key = f"revive_choice_{group_id}_{qq_id}"
    raw = db.get_event_state(key)
    if not raw:
        yield event.plain_result(_T.static("rv.none"))
        return
    try:
        st = _json.loads(raw) if isinstance(raw, str) and raw else {}
    except Exception:
        st = {}
    if not isinstance(st, dict) or not st:
        db.set_event_state(key, "")
        yield event.plain_result(_T.static("rv.stale"))
        return
    lost = int(st.get("lost", 0) or 0)
    extra = int(st.get("extra", 0) or 0)
    if _time.time() - st.get("ts", 0) > 300:
        # 超时未答复：按损失金币兜底结算（不能白嫖免罚）
        db.set_event_state(key, "")
        player = self._player(group_id, qq_id)
        db.update_player(group_id, qq_id, gold=max(0, player["gold"] - lost - extra))
        yield event.plain_result(_T.text("rv.fade", gold=lost + extra))
        return
    # 直接看原始消息（正则已限定只有 使用复活羽毛/放弃复活 两种输入）
    opt = "使用复活羽毛" if "复活羽毛" in (event.get_message_str() or "") else "放弃复活"
    db.set_event_state(key, "")
    player = self._player(group_id, qq_id)
    if opt == "使用复活羽毛":
        try:
            cnt = int(db.count_item(group_id, qq_id, "i_fu_huo_yu_mao") or 0)
        except Exception:
            cnt = 0
        if cnt <= 0:
            # 背包里已没有羽毛（可能被其他途径消耗）→ 按损失金币兜底
            db.update_player(group_id, qq_id, gold=max(0, player["gold"] - lost - extra))
            yield event.plain_result(_T.text("rv.lost", gold=lost + extra))
            return
        db.remove_item(group_id, qq_id, "i_fu_huo_yu_mao", 1)
        yield event.plain_result(_T.text("rv.ok", gold=lost + extra))
        return
    db.update_player(group_id, qq_id, gold=max(0, player["gold"] - lost - extra))
    yield event.plain_result(_T.text("rv.give", gold=lost + extra))

def _roll_find_quest_events(self, group_id, qq_id, player, cur_map):
    """v97.1 条件探索事件：进行中的 find 型任务，在指定地图探索按 chance 触发。
    返回触发文案(列表)或 None。机制：告示委托→探索概率遇到目标(鱼鱼示例：找猫)。"""
    import json as _json
    cur_id = cur_map.get("id", "")
    quests = db.get_quests(group_id, qq_id)
    side = quests.get("side", {}) or {}
    for sid, sq in list(side.items()):
        if sq.get("status") != "active":
            continue
        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
        if not sqd:
            continue
        obj = sqd.get("objective") or {}
        if not obj.get("find"):
            continue
        # v124：find 目标未显式指定 map 时 fallback 任务自身 map（s18 猎手的救赎 find 白桦）
        if (obj.get("map") or sqd.get("map")) != cur_id:
            continue
        chance = float(obj.get("chance", 0.1))
        if random.random() >= chance:
            continue
        # 命中：任务推进到 ready(交付阶段)
        sq["status"] = "ready"
        side[sid] = sq
        quests["side"] = side
        db.save_quests(group_id, qq_id, quests)
        target = obj["find"]
        mname = cur_map.get("name", "此地")
        giver = _cq.NPCS.get(sqd["giver"]) or _wild.ALL_WILD.get(sqd["giver"]) or {}
        gname = giver.get("name", "发布人")
        return (
            f"🐱【找到目标】你在{mname}的灌木丛里听到一声细弱的『喵——』！\n"
            f"一只{target}怯生生地探出头，你小心翼翼地靠近，用食物引诱，一把将它抱了起来！\n"
            f"━━━━━━━━━━━━\n"
            f"📜 『{sqd['name']}』目标达成！回去找 {gname} {self._deliver_hint(sqd['giver'])}吧～"
        )
    return None

def _rain_boost(self, group_id, qq_id) -> bool:
    """读取『突如其来的雨』set_state 写入的 rain_{gid}_{qid}({"ts": float})，
    30 分钟窗口内返回 True → 探索遇怪率 +15%（combat.py 探索分支消费）。"""
    try:
        raw = db.get_event_state(f"rain_{group_id}_{qq_id}")
        if not raw:
            return False
        try:
            ts = float(json.loads(raw).get("ts", 0))
        except Exception:
            ts = float(raw)  # 兼容裸时间戳旧值
        return 0 <= time.time() - ts <= _RAIN_WINDOW
    except Exception:
        return False

def _handle_explore_event(self, group_id, qq_id, player, cur_map, _fx=None):
    """处理探索随机事件；返回 (handled, 文本)
    v97.3：事件全部走模板引擎（core/event_templates.py），数据在 data/events.py。
    v115：当日奇遇 effects（loot_mult/pref_mats，取 _fx["mats"]）注入 EventContext，
          由模板层落地倍率/材料倾向（S3）。"""
    # v97.1 条件探索事件优先：find 型任务(告示委托)命中则不再 roll 常规事件
    find_lines = self._roll_find_quest_events(group_id, qq_id, player, cur_map)
    if find_lines:
        return True, find_lines
    name = cur_map.get("name", "此地")
    EventContext, execute_event_template = _ET.EventContext, _ET.execute_event_template
    # v105 M23 P1-1：探索彩蛋已移出本函数（explore() 事件窗口外独立判定，见 combat.py 探索入口），
    # 此处不再 roll 彩蛋——避免彩蛋再次被 35% 事件窗口吞掉导致实际概率只剩 0.175%
    ev = roll_explore_event(exclude=self._recent_explore_events(group_id, qq_id))
    ctx_kw = {"params": ev.get("params", {}), "name": name,
              "hooks": {"title_bonus": lambda q: self._title_bonus(group_id, q)}}
    _fx = _fx or {}
    _lm = _fx.get("loot_mult")
    _pm = _fx.get("mats")
    # v115 今日奇遇：EventContext 已支持 loot_mult/pref_mats（S3 落地），直接注入
    if _lm is not None:
        ctx_kw["loot_mult"] = _lm
    if _pm:
        ctx_kw["pref_mats"] = _pm
    ctx = EventContext(group_id, qq_id, player, cur_map, **ctx_kw)
    text = execute_event_template(ev["template"], ctx)
    if text:
        self._remember_explore_event(group_id, qq_id, ev["id"])
        return True, text
    return False, ""

def _recent_explore_events(self, group_id, qq_id):
    raw = db.get_event_state(_EXPLORE_RECENT_KEY.format(gid=group_id, qq_id=qq_id))
    if not raw:
        return []
    try:
        lst = json.loads(raw)
        return [x for x in lst if isinstance(x, str)][-_EXPLORE_RECENT_MAX:]
    except Exception:
        return []

def _remember_explore_event(self, group_id, qq_id, eid):
    recent = self._recent_explore_events(group_id, qq_id)
    recent = [x for x in recent if x != eid] + [eid]
    db.set_event_state(_EXPLORE_RECENT_KEY.format(gid=group_id, qq_id=qq_id),
                       json.dumps(recent[-_EXPLORE_RECENT_MAX:]))

def _poi_daily_used(self, group_id, qq_id, cur, sa_id, poi_id) -> bool:
    """v105 M23 P2-3：POI 每日重置（策划案 02 章 7.6 阶段 D『探索 15% 触发 POI + 每日重置』）。

    同一 POI 实例（地图:子区域:poi_id）同一天只触发一次：本日已用过返回 True（本次不触发）；
    首次触发则登记后返回 False（放行）。篝火 30% 回血/草药/鱼群等无法再高频重复刷。

    F1 审计修复（A3）：原实现为 读(get_props_use)→判→写(mark_props_use) 两段非原子，并发
    双请求可能同时读到"未用"都发放奖励造成重复。改为原子 API props_use_claim_atomic 单事务
    内 读-判-写，只有首个占坑者返回 True。布尔语义与旧函数相反：props_use_claim_atomic 返回
    True=本次占坑（放行发放），故此处取反返回（True=今日已用跳过）。"""
    import datetime as _dt
    key = f"{cur}:{sa_id}:{poi_id}"
    return not db.props_use_claim_atomic(qq_id, key, _dt.date.today().isoformat())

def _handle_poi(self, group_id, qq_id, player, cur_map, poi_id, poi, st=None):
    """v87 02 章 7.6：处理 POI 探索点交互；返回展示文本。

    v125.2 注册表化：世界 POI 按 effect 键、副本内联 POI 按 inst:<type> 键
    查 POI_EFFECTS（game/core/poi_effects.py，原 9+5 分支 if-chain 全量迁入）；
    未知效果显式告警（不再静默 fallback 吞掉数据拼写错误）。
    st 为副本战斗上下文（副本内联 POI 时传入）。
    """
    PoiContext, execute_poi = _POI.PoiContext, _POI.execute_poi
    eff = f"inst:{poi.get('type')}" if poi.get("type") else poi.get("effect", "")
    ctx = PoiContext(group_id, qq_id, player, cur_map, poi_id, poi, st=st,
                     hooks={"mark_used": self._mark_poi_used, "player": self._player},
                     host=db, dom=_PoiDom)
    text = execute_poi(eff, ctx)
    if text is not None:
        return text
    # 未知 effect：显式告警（防数据拼写错误被静默吞掉）
    _obs.log().warning(
        "[dragonfall] 未知 POI effect %r（poi_id=%s），效果未结算——"
        "请检查 data/pois.py 或 instance_stage_maps.py", eff, poi_id)
    if poi.get("type"):
        return f"你检查了{poi.get('name', '')}，没发现特别之处。"
    icon = poi.get("icon", "🌿")
    pname = poi.get("name", "探索点")
    return f"{icon} 【{pname}】你打量了一下{ctx.loc}的{poi.get('desc', '这处探索点')}，似乎没什么特别的。"

async def attack(self, event: AstrMessageEvent, group_id, qq_id, player, target_arg):
    battle = db.get_battle(group_id, qq_id)
    if not battle:
        inst_row = self._instance_battle_for(group_id, qq_id)
        if inst_row:
            battle = inst_row
    # 目标解析（v2 多对多 §8.1）：『攻击 @QQ』/『攻击 QQ 号』(数字/@ 开头)→ 恒走 PVP；
    # 其余带参 → 若当前在怪/世界Boss战斗中则解析为指定目标名（非 PVP），否则维持 PVP 发起。
    if target_arg:
        _is_pvp_target = target_arg[0].isdigit() or target_arg.startswith("@")
        # 『攻击 <名字>』：当前已处于任意战斗（含副本/PVP）且非数字/@ → 视为本次战斗行动
        # （不在战斗中 → 维持 PVP 发起）。数字/@ 开头恒走 PVP（『攻击 @QQ』/『攻击 QQ 号』）。
        _in_any_cbt = bool(battle)
        if _is_pvp_target or not _in_any_cbt:
            async for _r in self._pvp_start(event, group_id, qq_id, player, target_arg):
                yield _r
            return
    if not battle:
        yield event.plain_result(_T.static("bt.no_enemy"))
        return
    if battle["state"].get("type") == "instance":
        # N5b4-5a R2：接线点 attack → 新 Router（saintess_engine 原生；老 _instance_act R3 删除）
        async for _r in self._instance_router(event, group_id, qq_id, player, battle["state"], "attack", None):
            yield _r
        return
    if battle["state"].get("type") == "pvp":
        if self._pvp_handle_timeout(battle, group_id, qq_id):
            yield event.plain_result(_T.static("bt.pvp_timeout"))
            return
        async for _r in self._pvp_act(event, group_id, qq_id, player, battle["state"], "attack", None):
            yield _r
        return
    _stype = battle["state"].get("type")
    # worldboss 战斗（N5b4-3：saintess_engine 恢复）
    if _stype == "worldboss":
        b = self._restore_battle(battle["state"])
        if b is None:
            db.clear_battle(group_id, qq_id)
            self._unlock_battle(group_id, qq_id)
            yield event.plain_result(_T.static("bt.stale_boss"))
            return
        async for _r in self._worldboss_act(event, group_id, qq_id, player, b, "attack", None, target=_resolve_target_arg(b, target_arg)):
            yield _r
        return
    b = self._restore_battle(battle["state"])
    if b is None:
        # 旧格式存档作废：清档重开（N5b 约定不迁移）
        db.clear_battle(group_id, qq_id)
        self._unlock_battle(group_id, qq_id)
        yield event.plain_result(_T.static("bt.stale_explore"))
        return
    # v2 指定目标：『攻击 <名字>』解析为目标名传给引擎（引擎会校验射程/存活）；无参→None 自动
    # ★ P1 修复：解析成 **actor**（`_resolve_target_arg`）—— v181 引擎 `ActCtx.target` 只认 actor，
    #   传字符串会在落地段 `target.get("hp")` 崩。
    _target = _resolve_target_arg(b, target_arg)
    # v94.2 体力：每次攻击扣 1（普通/世界Boss通用；instance/pvp 已在上方分流）
    _ok, _st = self._spend_stamina(group_id, qq_id, 1, player, "攻击")
    if not _ok:
        if self._b_enemy(b).get("is_boss"):
            # v95.20 #101：Boss 战无法逃跑，体力耗尽=被困战斗——提示必须说清出路
            yield event.plain_result(_st + _T.static("bt.boss_noflee"))
        else:
            yield event.plain_result(_st + _T.static("bt.food_tip"))
        return
    logs, ended, _who = b.human_act("attack", None, b.focus(), target=_target)
    self._sync_battle_player(player, b)
    db.update_player(group_id, qq_id, hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"])
    if ended:
        # v130.3 意见#9 体验增强：胜利/结束时若残存潜行（技能/防御击杀场景潜行未被攻击消费），
        # 显式提示消散，避免玩家误解"战斗结束了暴击还在"
        # V 系列：saintess_engine 效果在 player.effects；旧引擎引用同步 buffs——双引擎判型
        _stealth_left = bool((player.get("effects") or {}).get("stealth")) \
            if isinstance(player.get("effects"), dict) else False
        if _stealth_left:
            logs.append(_T.static("bt.shadow_gone"))
        if b.result == "victory":
            # N5b4-2：胜利结算用原主怪引用（sides["enemy"][0]——死亡不移除，读存活首怪或引用）
            _mon = self._b_enemy(b)
            if not _mon:
                _acts = b.sides_of("enemy")
                _mon = _acts[0] if _acts else {}
            # N5b4-2：同场全部击杀单位（含副怪）交胜利结算——掉落/经验只按主怪一次
            _kills = list(getattr(b, "killed_actors", None) or [])
            for _r in self._handle_victory(event, group_id, qq_id, player, _mon, "\n".join(logs), extra_kills=_kills):
                yield _r
            return
        if b.result == "defeat":
            for _r in self._handle_defeat(event, group_id, qq_id, player, self._b_enemy(b), "\n".join(logs)):
                yield _r
            return
        if b.result == "fled":
            self._unlock_battle(group_id, qq_id)
            db.clear_battle(group_id, qq_id)
            yield event.plain_result("\n".join(logs))
            return
    # 保存战斗状态（v9）
    db.save_battle(group_id, qq_id, b.to_state())
    monster = self._b_enemy(b)
    result = "\n".join(logs)
    yield event.plain_result(
        f"{result}\n━━━━━━━━━━━━\n"
        f"{self._battle_footer(player, b, monster)}"
    )

async def skill(self, event: AstrMessageEvent, group_id, qq_id, player, skill_name):
    # v2 目标指定：『技能 <名> <目标名>』——原始命令行 token 保留，战斗施放时取首个之后的
    # token 为指定目标（技能名本身是单 token，无空格）；槽位施放『技能 <槽位> <目标名>』同理。
    raw_tokens = skill_name.split()
    if raw_tokens and raw_tokens[0].isdigit():
        _skill_target = " ".join(raw_tokens[1:]) if len(raw_tokens) >= 2 else None
    elif len(raw_tokens) >= 2:
        _skill_target = " ".join(raw_tokens[1:])
    else:
        _skill_target = None
    # v52 Build 懒迁移：技能栏全空的老玩家，自动把已学技能装进前几格
    # v157 修复：技能栏含无效 ID（如 v153 重置残留的 "***" 占位符）也触发迁移——
    # 否则输入『技能 1』查不到技能、战斗只触发被动不行动 → 玩家"无限回合"（实抓）。
    bar = db.get_skill_bar(qq_id)
    _valid_bar = [s for s in (bar or []) if s and skill_info(player["class_name"], s)]
    if not _valid_bar:
        learned = [_display("skills", s) for s in (player.get("learned_skills") or []) if s]
        if learned:
            new_bar = list(learned[:6])
            while len(new_bar) < 6:
                new_bar.append(None)
            db.set_skill_bar(qq_id, new_bar)
            bar = new_bar
    elif len(_valid_bar) != len(bar or []):
        # 部分无效：保留有效项，缺口用已学技能补（不整体重置）
        learned = [_display("skills", s) for s in (player.get("learned_skills") or []) if s]
        _fill = [s for s in learned if s not in _valid_bar]
        new_bar = list(_valid_bar)
        for _s in _fill:
            if len(new_bar) >= 6:
                break
            new_bar.append(_s)
        while len(new_bar) < 6:
            new_bar.append(None)
        db.set_skill_bar(qq_id, new_bar)
        bar = new_bar
    skill_name = skill_name.strip()
    parts = skill_name.split()
    first = parts[0] if parts else ""
    # 无参 → 技能系统面板
    if not skill_name:
        yield event.plain_result(self._skill_panel(player))
        return
    # 『技能 学习 <名称>』委托给学习逻辑
    if first == "学习" and len(parts) >= 2:
        yield event.plain_result(self._skill_learn_msg(group_id, player, "".join(parts[1:])))
        return
    # 『技能 列表 <页>』→ 技能列表（翻页，每页5带序号），支持免空格『技能列表2』
    if first.startswith("列表") or first.startswith("list"):
        rest = first[2:] if first.startswith("列表") else first[4:]
        page = 1
        if rest.isdigit():
            page = int(rest)
        elif len(parts) >= 2 and parts[1].isdigit():
            page = int(parts[1])
        yield event.plain_result(self._skill_list_page(player, page))
        return
    # 『技能 <数字>』→ 技能栏槽位（v52：必须已设置，不再 fallback 全列表）
    if skill_name.isdigit():
        idx = int(skill_name)
        bar = db.get_skill_bar(qq_id)
        if 1 <= idx <= 6 and bar and idx <= len(bar) and bar[idx - 1]:
            skill_name = bar[idx - 1]
        else:
            yield event.plain_result(
                _T.text("sk.bar_empty", idx=idx, idx2=idx)
            )
            return
    # 其他 → 战斗中施放
    battle = db.get_battle(group_id, qq_id)
    if not battle:
        inst_row = self._instance_battle_for(group_id, qq_id)
        if inst_row:
            battle = inst_row
    if not battle:
        # v101.25 #300：治疗类技能脱战可直接施放（回复生命），不再误导"找敌人"。
        # 战斗外治疗不要求技能栏配置（技能栏是战斗配置），但必须已学会。
        info = skill_info(player["class_name"], skill_name)
        if info and info.get("kind") == K_HEAL and is_skill_learned(
            player["class_name"], player["level"], skill_name, player.get("learned_skills", [])
        ):
            # v104 R3 P1-3 修复：脱战治疗必须校验核心资源——res_cost 技能（神恩降临 faith10/
            # 大治愈术 faith3）此前脱战 0 信仰可无限刷，改拦截（核心资源仅战斗内存在，脱战无法攒取）；
            # CD 为战斗内状态，脱战无 battle 实例无法校验，带 cd 的无资源技能保持可脱战施放
            if info.get("res_cost"):
                # v181.M-R2b：资源名单源 EFFECT_RULES[key].name（旧按职业主资源
                # core_resource_def 已退役）——res_cost 键直查：energy→精力、zhan_yi→战意
                _rc_list = []
                for _k, _v in info["res_cost"].items():
                    _rc_list.append(f"{_v} {_res_display_name(_k)}")
                yield event.plain_result(
                    _T.text("sk.res_off", res=info.get('name', skill_name), cost=' + '.join(_rc_list))
                )
                return
            # v164.3 修复：技能数据 v161 起支持 res_cost（精力/怒气等核心资源），无 mp 字段——
            # 原 info["mp"] 直接下标对 res_cost 技能 KeyError 崩（玩家报"放不出技能"）。
            # 对齐引擎 battle.py:2455：mp 用 .get 兜底；res_cost 技能资源校验由引擎施放时执行。
            # v181.M-smallfix：mp 预检改与引擎 actions._skill_pay_of 同源折算（bonus.cost
            # 折扣后 floor+保底 1，= 引擎实际扣费值）——脱战 player 无 bonus 容器（词条
            # 装配只在战斗 actor 上）→ 折算直通声明费（行为零变化），口径与战斗内一致。
            _mp_need = skill_mp_pay_of(player, info)
            if _mp_need > 0 and player["mp"] < _mp_need:
                yield event.plain_result(_T.static("sk.no_mp"))
                return
            if player.get("hp", 0) >= player.get("max_hp", 1):
                yield event.plain_result(_T.text("sk.heal_full", cur=player['hp'], cap=player['max_hp']))
                return
            st = player_final_stats(player["class_name"], player["level"],
                                      player.get("equipment", {}), player.get("class_tier", 0),
                                      player.get("attributes"), player.get("evolve_path", 0),
                                      self._title_bonus(group_id, qq_id), player.get("race"))
            # 与 battle.py _skill_heal 同款结算：power<1 按 max_hp 百分比，power>=1 按魔攻×power
            # v104 R3 P2-2：倍率按技能等级（skill_level_of）而非玩家等级——此前 Lv.30 玩家
            # 技能 Lv.1 脱战治疗 +60%（1.60x vs 战斗内 1.00x），数值口径分裂
            _slv = skill_level_of(player, skill_name)
            if info.get("power", 0) < 1:
                heal = int(player.get("max_hp", 0) * info["power"] * skill_power_mult(_slv, info))
            else:
                heal = int(st["matk"] * info["power"] * skill_power_mult(_slv, info))
            pv = passive_skills_learned(player["class_name"], player.get("learned_skills", []))
            if "神恩" in pv:
                heal = int(heal * 1.10)
            new_hp = min(player.get("max_hp", 1), player.get("hp", 0) + heal)
            db.update_player(group_id, qq_id, hp=new_hp, mp=player["mp"] - info["mp"])
            yield event.plain_result(
                _T.text("sk.heal_ok", name=skill_name, hp=heal, cur=new_hp, cap=player['max_hp'])
            )
            return
        yield event.plain_result(_T.static("sk.no_enemy"))
        return
    skill_name = skill_name.strip()
    # v2 技能带目标解析：『技能 <名> <目标名>』——当前位于"施放"分支（学习/列表/详情/
    # 升级/槽位等关键字已在上方 return），parts[0] 是技能名 token。先尝试用 parts[0] 查技能，
    # 查到 → 技能名取 parts[0]、剩余 token 拼接为目标传战斗层；查不到 → 用完整串（保持旧逻辑）。
    _skill_resolve_keys = {"学习", "列表", "list", "详情", "升级", "洗点", "栏"}
    if (len(parts) >= 2 and not skill_name.isdigit() and first not in _skill_resolve_keys):
        if skill_info(player["class_name"], first):
            skill_name = first
            _skill_target = " ".join(parts[1:])
    info = skill_info(player["class_name"], skill_name)
    if not info:
        # v95.25 #145：报错读 learned_skills（v52 后 skills 列不再更新），并引流『技能列表』
        learned = [_display("skills", s) for s in (player.get("learned_skills") or [])]
        learned_str = "、".join(learned) if learned else _T.static("sk.none")
        yield event.plain_result(
            _T.text("sk.unknown", name=skill_name, list=learned_str)
        )
        return
    if not is_skill_learned(player["class_name"], player["level"], skill_name, player.get("learned_skills", [])):
        need_lv = info["lv"]
        if player["level"] < need_lv:
            yield event.plain_result(
                _T.text("sk.lv_short", name=skill_name, need=need_lv, have=player['level'])
            )
        else:
            cost = skill_learn_cost_for(player, need_lv)
            yield event.plain_result(
                _T.text("sk.not_learned", name=skill_name, name2=skill_name, cost=cost)
            )
        return
    # v64 被动技能：无需施放，学习后战斗自动生效
    if info.get("kind") == K_PASSIVE:
        yield event.plain_result(
            _T.text("sk.passive", name=skill_name, name2=skill_name)
        )
        return
    # v52 Build 系统：战斗中只能使用技能栏里设置的技能
    bar = db.get_skill_bar(qq_id)
    if skill_name not in (bar or []):
        yield event.plain_result(
            _T.text("sk.not_in_bar", name=skill_name, slot=skill_name, name2=self._tip('build'))
        )
        return
    # v164.3 修复：技能数据 v161 起支持 res_cost（精力/怒气等核心资源），无 mp 字段——
    # 原 info["mp"] 直接下标对 res_cost 技能 KeyError 崩（玩家报"放不出技能"）。
    # 对齐引擎 battle.py:2455：mp 用 .get 兜底；res_cost 技能资源校验由引擎施放时执行。
    # v181.M-smallfix：mp 预检改与引擎 actions._skill_pay_of 同源折算——折扣词条
    # （arcane_focus 等 bonus.cost）下 mp ∈ [实际pay, 声明费) 边界放行施放（丢边界
    # 收益修复，无白嫖：pay = 引擎实际扣费，floor+保底 1 同语义）。折算容器取战斗
    # state 我方 actor（开战装配 bonus.cost 随档落盘/恢复）；异常/找不到 → 回落
    # player dict（无容器 → 声明费直通，历史行为不变）。
    _mp_need = skill_mp_pay_of(player, info)
    _mp_cur = int(player.get("mp", 0) or 0)
    try:
        _me_actor = None
        for _acts in (battle.get("state") or {}).get("sides", {}).values():
            for _a in (_acts or []):
                if not isinstance(_a, dict):
                    continue
                if str(_a.get("qq_id") or _a.get("uid") or "") == str(qq_id):
                    _me_actor = _a
                    break
            if _me_actor is not None:
                break
        if _me_actor is not None:
            _mp_need = skill_mp_pay_of(_me_actor, info)
            if _me_actor.get("mp") is not None:
                _mp_cur = int(_me_actor.get("mp") or 0)
    except Exception:
        pass  # 取 actor 异常 → 保留 player dict 口径（兜底铁律）
    if _mp_need > 0 and _mp_cur < _mp_need:
        yield event.plain_result(_T.static("sk.no_mp"))
        return
    # 2026-09-11 ★P0 冷却预检（与引擎 actions._cd_left_of 同源：绝对时刻制
    # `actor.cooldown[name] = 施放时刻 + cd`，与战斗 state["now"] 比较）。
    # 拦截在命令层 → 不扣体力、不耗回合（对齐上方 mp 预检的处理方式）。
    # 引擎侧 do_skill 也会拦（双保险：脚本/AI 等非命令路径直调引擎时不白放）。
    if info.get("cd"):
        try:
            _cd_tbl = _me_actor.get("cooldown") or {}
        except Exception:
            _cd_tbl = {}  # 取 actor 异常 → 无冷却表（引擎侧仍会拦）
        try:
            _cd_due = float(_cd_tbl.get(info.get("name") or skill_name) or 0)
            _cd_now = float((battle.get("state") or {}).get("now") or 0)
            _cd_left = _cd_due - _cd_now
        except Exception:
            _cd_left = 0.0
        if _cd_left > 0:
            yield event.plain_result(
                _T.text("sk.cd", name=info.get('name', skill_name), ticks=_cd_left)
            )
            return
    if battle["state"].get("type") == "instance":
        # N5b4-5a R2：接线点 skill → 新 Router（saintess_engine 原生；老 _instance_act R3 删除）
        async for _r in self._instance_router(event, group_id, qq_id, player, battle["state"], "skill", skill_name, target=_resolve_target_arg(battle["state"], _skill_target)):
            yield _r
        return
    if battle["state"].get("type") == "pvp":
        if self._pvp_handle_timeout(battle, group_id, qq_id):
            yield event.plain_result(_T.static("bt.pvp_timeout"))
            return
        async for _r in self._pvp_act(event, group_id, qq_id, player, battle["state"], "skill", skill_name):
            yield _r
        return
    # worldboss 战斗（N5b4-3：saintess_engine 恢复）
    if battle["state"].get("type") == "worldboss":
        b = self._restore_battle(battle["state"])
        if b is None:
            db.clear_battle(group_id, qq_id)
            self._unlock_battle(group_id, qq_id)
            yield event.plain_result(_T.static("bt.stale_boss"))
            return
        async for _r in self._worldboss_act(event, group_id, qq_id, player, b, "skill", skill_name, target=_resolve_target_arg(b, _skill_target)):
            yield _r
        return
    b = self._restore_battle(battle["state"])
    if b is None:
        # 旧格式存档作废：清档重开（N5b 约定不迁移）
        db.clear_battle(group_id, qq_id)
        self._unlock_battle(group_id, qq_id)
        yield event.plain_result(_T.static("bt.stale_explore"))
        return
    # v94.2 体力：施放技能扣 1（instance/pvp/worldboss 已在上方分流）
    _ok, _st = self._spend_stamina(group_id, qq_id, 1, player, "施放技能")
    if not _ok:
        if self._b_enemy(b).get("is_boss"):
            # v95.20 #101：Boss 战无法逃跑，体力耗尽=被困战斗——提示必须说清出路
            yield event.plain_result(_st + _T.static("bt.boss_noflee"))
        else:
            yield event.plain_result(_st + _T.static("bt.food_tip"))
        return
    logs, ended, _who = b.human_act("skill", skill_name, b.focus(), target=_resolve_target_arg(b, _skill_target))
    self._sync_battle_player(player, b)
    db.update_player(group_id, qq_id, hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"])
    if ended:
        if b.result == "victory":
            # N5b4-2：胜利结算用原主怪引用（sides["enemy"][0]——死亡不移除，读存活首怪或引用）
            _mon = self._b_enemy(b)
            if not _mon:
                _acts = b.sides_of("enemy")
                _mon = _acts[0] if _acts else {}
            # N5b4-2：同场全部击杀单位（含副怪）交胜利结算——掉落/经验只按主怪一次
            _kills = list(getattr(b, "killed_actors", None) or [])
            for _r in self._handle_victory(event, group_id, qq_id, player, _mon, "\n".join(logs), extra_kills=_kills):
                yield _r
            return
        if b.result == "defeat":
            for _r in self._handle_defeat(event, group_id, qq_id, player, self._b_enemy(b), "\n".join(logs)):
                yield _r
            return
    db.save_battle(group_id, qq_id, b.to_state())
    monster = self._b_enemy(b)
    result = "\n".join(logs)
    yield event.plain_result(
        f"{result}\n━━━━━━━━━━━━\n"
        f"{self._battle_footer(player, b, monster)}"
    )

def _skill_panel(self, player: dict) -> str:
    """技能系统面板(无参『技能』)"""
    cls = player["class_name"]
    cls_info = _cc.CLASSES.get(cls, {})
    total = len(_sk_table(cls))
    learned = player.get("learned_skills", [])
    # v101.20：已学导师专属技能计入总数（避免"已学>总数"怪相）
    _tutor = (_cc.TUTOR_SKILLS or {}).get(cls, {}) or {}
    _tutor_learned = sum(1 for _sid in _tutor if _sid in [_resolve("skills", s) for s in learned if s])
    total += _tutor_learned
    have = len(learned)
    pts = player.get("skill_points", 0)
    lines = [
        _T.text("skill_panel.title", icon=cls_info.get('icon',''), cls=_display('classes', cls),
            level=player['level']),
        "━━━━━━━━━━━━",
        _T.text("skill_panel.points", pts=pts),
        _T.text("skill_panel.learned", have=have, total=total, left=total - have),
        "━━━━━━━━━━━━",
        _T.static("skill_panel.hint_list"),
        _T.static("skill_panel.hint_detail"),
        _T.static("skill_panel.hint_learn"),
        _T.static("skill_panel.hint_upgrade"),
        _T.static("skill_panel.hint_bar"),
        _T.static("skill_panel.hint_reset"),
        _T.static("skill_panel.hint_cast"),
        _T.static("skill_panel.hint_passive"),
    ]
    return "\n".join(lines)

def _branch_skills_for(self, player: dict) -> dict:
    """玩家已解锁分支的专属技能表 {技能名: info}(v26：按 tier 升序合并，只含已转职分支)"""
    cls = _cc.BRANCH_SKILLS.get(player["class_name"], {})
    if isinstance(cls, dict) and "branches" in cls:
        cls = cls["branches"]
    tier = player.get("class_tier", 0)
    path = player.get("evolve_path", 0)
    out = {}
    if not path or tier <= 0:
        return out
    for t in sorted(cls.keys()):
        if t > tier:
            continue
        branches = cls[t]
        names = list(branches.keys())
        # v112：多分支索引通用化（攻/守 path=1/2；隐藏流派 path=1/2/3）
        idx = max(0, int(path or 0) - 1)
        if idx < len(names):
            out.update(branches[names[idx]])
    return out

def _player_skill_table(self, player: dict) -> dict:
    """玩家完整技能表：基础职业技能 + 已解锁分支专属技能（基础在前，序号稳定）

    v48：PLAYER_SKILLS[cls] 结构为 {"name": 中文名, "skills": {技能表}}
    """
    cls_skills = _cc.PLAYER_SKILLS.get(player["class_name"], {})
    if isinstance(cls_skills, dict) and "skills" in cls_skills:
        table = dict(cls_skills["skills"])
    else:
        table = dict(cls_skills)
    table.update(self._branch_skills_for(player))
    # v101.20 职业导师专属技能：未学会不进列表（保持神秘感），学会后追加（序号稳定在尾部）
    learned = player.get("learned_skills", [])
    _tutor = (_cc.TUTOR_SKILLS or {}).get(player["class_name"], {}) or {}
    for _sid, _info in _tutor.items():
        if _sid in [_resolve("skills", s) for s in learned if s]:
            table[_sid] = _info
    return table

def _skill_tag(self, info: dict) -> str:
    _T.static("sk.tag_passive")
    if info.get("kind") == K_PASSIVE:
        return _T.static("sk.tag_passive")
    if info.get("effect"):
        return _effect_cn(info["effect"])
    if info.get("mech"):
        return _MECH_CN.get(info["mech"], info["mech"])
    if info.get("cond"):
        label = info["cond"].get("label", "")
        return label[:2] if label else ""
    return ""

def _skill_range_label(self, info: dict) -> str:
    _T.static("sk.range_multi")
    if str(info.get("team") or "").endswith("_all"):
        return _T.static("sk.range_multi")
    r = info.get("range")
    if r and r != "single":
        return _T.static("sk.range_multi")
    aoe = info.get("aoe")
    if isinstance(aoe, str) and aoe:
        return _T.static("sk.range_multi")
    return ""

def _skill_list_gains(self, info: dict, lv: int) -> list:
    """v134 意见#38：技能列表当前等级数值维度——与 player.py _skill_upgrade_gains 同逻辑
    （CombatCmds 与 PlayerCmds 是不同 Mixin 不能跨类调用，本地复制；列表只展示已学技能数值）"""
    parts = []
    kind = info.get("kind", "")
    if info.get("power"):
        label = "治疗" if kind == K_HEAL else "伤害"
        parts.append(f"{label} {int(info['power'] * skill_power_mult(lv, info) * 100)}%")
    if kind in (K_BUFF, K_TAUNT):
        parts.append(_T.text("sk.gain_dur", v=skill_buff_turns(lv)))
    if info.get("cond"):
        parts.append(_T.text("sk.gain_cond", v=skill_cond_mult(info['cond'], lv, info)))
    if info.get("mech_val"):
        parts.append(_T.text("sk.gain_stack", v=skill_mech_val(info, lv)))
    if info.get("lifesteal"):
        parts.append(_T.text("sk.gain_leech", v=int(skill_lifesteal_pct(info, lv) * 100)))
    return parts

def _skill_gains_curve(self, info: dict, cur: int, mx: int) -> str:
    """v134.1 意见#47：英雄联盟式多等级效果曲线（Lv.1→满级逐级数值，最高到 Lv.5）。
    维度与 _skill_list_gains 同源（伤害/治疗/持续刻/条件×/叠层/吸血）：
    - 折线级数（Lv.5）按『当前级/满级』压缩：跳级只保留当前级+满级；
    - 数值全等无成长 → 返回空串（passive/无成长维度，不占行）。"""
    parts = []
    kind = info.get("kind", "")
    if info.get("power"):
        label = "治疗" if kind == K_HEAL else "伤害"
        vals = _curve_vals(
            lambda lv: int(info["power"] * skill_power_mult(lv, info) * 100), cur, mx)
        if len(vals) > 1:
            parts.append(f"{label} {'/'.join(f'{v}%' for v in vals)}")
    if kind in (K_BUFF, K_TAUNT):
        vals = _curve_vals(lambda lv: skill_buff_turns(lv), cur, mx)
        if len(vals) > 1:
            parts.append(_T.text("sk.curve_dur", v='/'.join(f'{v}刻' for v in vals)))
    if info.get("cond"):
        vals = _curve_vals(
            lambda lv: round(skill_cond_mult(info["cond"], lv, info), 2), cur, mx)
        if len(vals) > 1:
            parts.append(_T.text("sk.curve_cond", v='/×'.join(_fmt_mult(v) for v in vals)))
    if info.get("mech_val"):
        vals = _curve_vals(lambda lv: skill_mech_val(info, lv), cur, mx)
        if len(vals) > 1:
            parts.append(_T.text("sk.curve_stack", v='/'.join(str(v) for v in vals)))
    if info.get("lifesteal"):
        vals = _curve_vals(
            lambda lv: int(skill_lifesteal_pct(info, lv) * 100), cur, mx)
        if len(vals) > 1:
            parts.append(_T.text("sk.curve_leech", v='/'.join(f'{v}%' for v in vals)))
    return " · ".join(parts)

def _skill_list_page(self, player: dict, page: int = 1) -> str:
    """技能列表翻页(每页 5 条带序号，未学显示 Lv.0)。
    v104 R3 P2-22：序号仅用于『技能详情/学习/升级 <序号>』定位列表项；
    战斗中『技能 <槽位>』按技能栏槽位(1-6)施放，两者语义不同，不再混称一致。"""
    skills = self._player_skill_table(player)
    skill_items = list(skills.items())
    learned = player.get("learned_skills", [])
    # 分支技能名 → 分支名标记（v130.2f.2：苦修档位展示名映射，分支 key 不动）
    _BRANCH_DISPLAY = {"武僧": "淬势者", "大地武僧": "锻势行者"}
    branch_tags = {}
    for sname in skills:
        owner = branch_skill_owner(player["class_name"], sname)
        if owner:
            branch_tags[sname] = _BRANCH_DISPLAY.get(owner[1], owner[1])
    page_items, pages, page = self._page_items(skill_items, page, per_page=5)
    lines = ["技能列表"]
    lines.append("━━━━━━━━━━━━")
    for i, (sname, info) in enumerate(page_items, (page - 1) * 5 + 1):
        # v49：key 是技能 ID（sk_xxx），显示用中文名
        disp_name = info.get("name", sname) if isinstance(info, dict) else sname
        learned_now = is_skill_learned(player["class_name"], player["level"], sname, learned)
        if learned_now:
            slv = skill_level_of(player, sname)  # #259：兼容 skill_levels key 为中文名（store 读库转换）
            lv_str = f"Lv.{slv}/{skill_max_level(info)}"  # v56.4：每技能独立满级
        else:
            slv = 0  # v56.3：未学显示 0 级
            need_lv = info.get("lv", 99)
            if player["level"] >= need_lv:
                # v95.7 #36：已达解锁等级 → 显示"可学(X技能点)"而非静态"未学(Lv.X解锁)"
                # v95.7 修复：cost 用 skill_learn_cost_for（含种族折扣），与『技能学习』实际扣点一致
                cost = skill_learn_cost_for(player, need_lv)
                lv_str = _T.text("skl.learnable", cost=cost)
            else:
                lv_str = _T.text("skl.locked", lv=need_lv)  # v95.4：标注解锁等级
        tags = [info.get("kind", "")]
        tags.append(self._skill_range_label(info))  # v122 范围标签：kind 后、机制前
        ftag = self._skill_tag(info)
        if ftag and ftag != info.get("kind", ""):
            tags.append(ftag)
        if info.get("team"):
            tags.append(_T.static("skl.team"))  # v56.4：团队标记放标签，不进描述
        if sname in branch_tags:
            tags.append(branch_tags[sname])
        tag_str = "".join(f"<{t}>" for t in tags if t)  # v122c：过滤空标签（单体无范围标签）
        # v101.25d 技能列表排版（鱼鱼拍板模板）：编号行 / 标签行 / 描述行 / 消耗行，
        # 每条之间 ━━ 分隔线，参考属性面板四维的分区感
        lines.append(f"{i}.{disp_name} [{lv_str}]")
        if tag_str:
            lines.append(f"  · {tag_str}")
        # v134.4 意见#57 落地：技能列表不再显示技能描述（desc/等级曲线），只保留
        # 编号/名称/等级/标签/消耗/射程/冷却——一眼扫完；想看效果用『技能详情
        # <名称/序号>』（已支持序号，如『技能详情 6』）
        _cost = []
        _mp = info.get("mp", 0)
        # v126.5 资源消耗并入魔力求（鱼鱼问"信仰-3 是不是要消耗"→原格式 `信仰值 -3`
        # 像属性值 -3 有歧义；改为 `30 魔力 + 3 信仰值` 直白表达消耗）
        _rc = info.get("res_cost") or {}
        # v181.M-R2b：资源名单源 EFFECT_RULES[key].name（旧 core_resource_def 按职业
        # 主资源取名已退役）——res_cost/res_gain 键直查（energy→精力、zhan_yi→战意…）
        _rc_parts = []
        for _k, _v in _rc.items():
            # v126.6c 鱼鱼终版拍板：消耗项数字后缀用 `-`（消耗=扣减，与 res_gain
            # 获得的 `+` 区分；`消耗：` 前缀后带上下文，无属性值歧义）
            _rc_parts.append(f"{_res_display_name(_k)} -{_v}")
        if _mp or _rc_parts:
            _cost_parts = []
            if _mp:
                _cost_parts.append(_T.text("skl.mp", v=_mp))
            _cost_parts.extend(_rc_parts)
            _cost.append(" ｜ ".join(_cost_parts))
        else:
            _cost.append("无")
        # v122d 攻击距离（鱼鱼拍板用「射程」：技能自带 reach 覆盖职业 reach）
        _cls_reach = int((_cc.CLASSES.get(player.get("class_name", ""), {}) or {}).get("reach", 2) or 2)
        _cost.append(_T.text("skl.range", v=int(info.get('reach') or _cls_reach)))
        _rg = info.get("res_gain") or 0
        if _rg:
            # res_gain 可为 int（常规）或 dict（按资源名取值，如林语印记 {"energy": 10}）
            if isinstance(_rg, dict):
                for _k, _v in _rg.items():
                    _cost.append(f"{_res_display_name(_k)} +{_v}")
            else:
                # int res_gain 无 key（旧「职业主资源隐含」口径随 core_resource_def 退役；
                # 现网技能表无 int res_gain 条目 → 此分支不可达，固定 '资源' 标签兜底）
                _cost.append(_T.text("skl.res", v=_rg))
        _cd = info.get("cd") or 0
        if _cd:
            _cost.append(_T.text("skl.cd", v=_cd))
        if _cost:
            lines.append(_T.text("skl.cost", v=' ｜ '.join(_cost)))
        else:
            lines.append(_T.static("skl.cost_none"))  # v104 R3 P3-1：零消耗技能如实显示"无"（原"免费"易误解为有价免费）
    lines.append("━━━━━━━━━━━━")  # v114.6：页数上方分隔线加回（v114.5 删每条间隔线时误伤）
    lines.append(_T.text("skl.pages", cur=page, tot=pages))
    if pages > 1 and page < pages:
        lines.append(_T.text("skl.next", page=page+1))
    # v130.5 意见#8 落地：固定长引导 → TIPS.skill 随机提示池(带 emoji，≤20字)，
    # 与背包/炼金等面板风格统一；操作要点(战斗施放/学习/副本指定队友)已拆入提示池
    lines.append(self._tip("skill"))
    self._record_list_state(player.get("qq_id"), "技能列表", page, pages)
    return "\n".join(lines)

async def defend(self, event: AstrMessageEvent, group_id, qq_id, player):
    battle = db.get_battle(group_id, qq_id)
    if not battle:
        inst_row = self._instance_battle_for(group_id, qq_id)
        if inst_row:
            battle = inst_row
    if battle["state"].get("type") == "instance":
        # N5b4-5a R2：接线点 defend → 新 Router（saintess_engine 原生；老 _instance_act R3 删除）
        async for _r in self._instance_router(event, group_id, qq_id, player, battle["state"], "defend", None):
            yield _r
        return
    if battle["state"].get("type") == "pvp":
        if self._pvp_handle_timeout(battle, group_id, qq_id):
            yield event.plain_result(_T.static("bt.pvp_timeout"))
            return
        async for _r in self._pvp_act(event, group_id, qq_id, player, battle["state"], "defend", None):
            yield _r
        return
    # worldboss 战斗（N5b4-3：saintess_engine 恢复）
    if battle["state"].get("type") == "worldboss":
        b = self._restore_battle(battle["state"])
        if b is None:
            db.clear_battle(group_id, qq_id)
            self._unlock_battle(group_id, qq_id)
            yield event.plain_result(_T.static("bt.stale_boss"))
            return
        async for _r in self._worldboss_act(event, group_id, qq_id, player, b, "defend", None):
            yield _r
        return
    b = self._restore_battle(battle["state"])
    if b is None:
        db.clear_battle(group_id, qq_id)
        self._unlock_battle(group_id, qq_id)
        yield event.plain_result(_T.static("bt.stale_explore"))
        return
    logs, ended, _who = b.human_act("defend", None, b.focus())
    self._sync_battle_player(player, b)
    db.update_player(group_id, qq_id, hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"])
    if ended and b.result == "defeat":
        for _r in self._handle_defeat(event, group_id, qq_id, player, self._b_enemy(b), "\n".join(logs)):
            yield _r
        return
    db.save_battle(group_id, qq_id, b.to_state())
    monster = self._b_enemy(b)
    result = "\n".join(logs)
    yield event.plain_result(
        f"{result}\n━━━━━━━━━━━━\n"
        f"{self._battle_footer(player, b, monster)}"
    )

async def flee(self, event: AstrMessageEvent, group_id, qq_id, player):
    battle = db.get_battle(group_id, qq_id)
    if not battle:
        inst_row = self._instance_battle_for(group_id, qq_id)
        if inst_row:
            battle = inst_row
    if battle["state"].get("type") == "instance":
        yield event.plain_result(_T.static("fl.inst_locked"))
        return
    if battle["state"].get("type") == "pvp":
        # PVP 逃跑 = 脱离战斗（双方解除，互不追究），避免被锁死/被骚扰
        st = battle["state"]
        # N5b4-4（saintess_engine）：双方 qq 从 meta/sides 读（旧格式快照键兜底兼容）
        _att_qq, _def_qq = self._pvp_meta_qqs(st)
        _my = str(qq_id)
        opp_qq = _def_qq if _my == _att_qq else _att_qq
        # 攻击方获得袭击 CD（无论谁逃跑，防反复骚扰）
        self._set_pvp_cd(_att_qq or _my)
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        if opp_qq:
            self._unlock_battle(group_id, opp_qq)
            db.clear_battle(group_id, opp_qq)
        yield event.plain_result(_T.static("fl.pvp_out"))
        return
    # Boss 锁场检查：saintess_engine 格式读 sides["enemy"] 存活怪 is_boss；旧格式读 state.enemy
    _is_boss = False
    if battle["state"].get("sides"):
        _eacts = battle["state"].get("sides", {}).get("enemy") or []
        _is_boss = any((_u or {}).get("is_boss") for _u in _eacts)
    else:
        _is_boss = bool((battle["state"].get("enemy") or {}).get("is_boss"))
    if _is_boss:
        yield event.plain_result(_T.static("fl.boss_locked"))
        return
    # worldboss 战斗（N5b4-3：saintess_engine 恢复；世界Boss 通常被 is_boss 拦截不可逃，兜底）
    if battle["state"].get("type") == "worldboss":
        b = self._restore_battle(battle["state"])
        if b is None:
            db.clear_battle(group_id, qq_id)
            self._unlock_battle(group_id, qq_id)
            yield event.plain_result(_T.static("bt.stale_boss"))
            return
        logs, ended, _who = b.human_act("flee", None, b.focus())
        self._sync_battle_player(player, b)
        db.update_player(group_id, qq_id, hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"])
        if ended and b.result == "fled":
            self._unlock_battle(group_id, qq_id)
            db.clear_battle(group_id, qq_id)
            yield event.plain_result("\n".join(logs))
            return
        db.save_battle(group_id, qq_id, b.to_state())
        monster = self._b_enemy(b)
        result = "\n".join(logs)
        yield event.plain_result(
            _T.text("bt.hp_mp_log", log=result, hp=player['hp'], hpmax=player['max_hp'], mp=player['mp'],
                mpmax=player['max_mp'])
        )
        return
    b = self._restore_battle(battle["state"])
    if b is None:
        db.clear_battle(group_id, qq_id)
        self._unlock_battle(group_id, qq_id)
        yield event.plain_result(_T.static("bt.stale_explore"))
        return
    logs, ended, _who = b.human_act("flee", None, b.focus())
    self._sync_battle_player(player, b)
    db.update_player(group_id, qq_id, hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"])
    if ended:
        if b.result == "fled":
            self._unlock_battle(group_id, qq_id)
            db.clear_battle(group_id, qq_id)
            yield event.plain_result("\n".join(logs))
            return
        if b.result == "defeat":
            for _r in self._handle_defeat(event, group_id, qq_id, player, self._b_enemy(b), "\n".join(logs)):
                yield _r
            return
    db.save_battle(group_id, qq_id, b.to_state())
    monster = self._b_enemy(b)
    result = "\n".join(logs)
    yield event.plain_result(
        _T.text("bt.hp_mp_log", log=result, hp=player['hp'], hpmax=player['max_hp'], mp=player['mp'],
            mpmax=player['max_mp'])
    )

def _buff_left_ticks(k, v, now_t) -> "tuple[str | None, str]":
    """buff 条目 → (剩余刻标签 or None, 值格式)。

    N5b4-1 双形态折算（纯读层兼容，N10 删旧后只留 dict 分支）：
    - dict（saintess_engine N7.1 定稿 / 旧复杂值）：{expire: 绝对秒} → 剩刻 = expire - now；
      无 expire（bar 状态/复杂值）→ 只显名无刻数
    - int/float（旧引擎绝对到期刻号）：值 × ACT_TICK - now 折算剩刻
    - 特殊键（控制/印记/一次性）saintess_engine 也走 dict.expire；旧 int 特殊键原样显刻
    """
    _SPECIAL_NO_DECAY = {"stun", "freeze", "fire_mark", "ice_mark", "thunder_mark",
                         "next_atk_up", "buff_phys_next", "stealth", "arcane_echo",
                         "oath_blade_next", "we_oath", "reduce_all", "reduce", "shield"}
    if isinstance(v, dict):
        exp = v.get("expire")
        if isinstance(exp, (int, float)) and exp is not None:
            _left = float(exp) - now_t
            if _left > 0:
                return _T.text("st.left_ticks", n=max(1, int(round(_left / (ACT_TICK or 1.0))))), None
            return None, None  # 已到期将清 → 只显名
        return None, None  # 无到期语义（bar 状态/永久）→ 只显名
    # int/float 形态（旧引擎）
    if k in _SPECIAL_NO_DECAY:
        return _T.text("st.left_ticks", n=int(v)), None
    _left = float(v) * (ACT_TICK or 1.0) - now_t
    if _left > 0:
        return _T.text("st.left_ticks", n=max(1, int(round(_left / (ACT_TICK or 1.0))))), None
    return None, None

def _status_line(self, player: dict, b) -> str:
    """战斗状态行：玩家 buff/叠层 + 敌方状态。无状态返回空串。

    N5b4-1：玩家侧改读 player dict（命令层已 sync_player_from_actor 回写；
    旧引擎引用同步同效）——展示纯读不依赖引擎 battle 类型，先切安全。
    敌方读 b.sides（旧 v180F / saintess_engine 双引擎通用，_b_enemy 已 sides 化）。
    """
    parts = []
    _now_t = float(getattr(b, "_now", 0.0) or 0.0)
    pbuf = []
    # 玩家效果源 = effects 单容器（V 系列四容器已合并；旧 buffs 分支随 N10 删除）
    _pb_src = (player.get("effects") or {}) if isinstance(player.get("effects"), dict) else {}
    for k, v in _pb_src.items():
        if k not in _P_BUFF_NAMES:
            continue
        # dict 条目（saintess_engine {expire,stat,...}/bar 状态）或旧 int 刻号；
        # 无效值（0/空）由 helper 过滤，这里只查名字表避免 dict 比较 TypeError
        if isinstance(v, dict):
            if "expire" not in (v or {}) and not v.get("stat") and not v.get("mode") and not v.get("period"):
                continue  # 空/纯状态残留
        elif not v or not (v > 0):
            continue
        left_tag, _ = self._buff_left_ticks(k, v, _now_t)
        pbuf.append(f"{_P_BUFF_NAMES[k]}{('(' + left_tag + ')') if left_tag else ''}")
    # 玩家叠层（V 系列：effects 条目 stacks——rage/战意等 stat_scale 声明 key；
    # O96：burn/poison/mark 是敌方减益叠层，不在玩家栏显示）
    stacks = {}
    if isinstance(player.get("effects"), dict):
        from saintess_engine.battle.state_effects import all_state_effects as _ase
        _stk_table = _ase()
        for _k, _ent in (player.get("effects") or {}).items():
            if isinstance(_ent, dict) and (_k in _stk_table or _k in _STACK_NAMES):
                _sv = int(_ent.get("stacks", 0) or 0)
                if _sv > 0:
                    stacks[_k] = _sv
    for k, v in stacks.items():
        if v and v > 0 and k in _STACK_NAMES and k not in _ENEMY_MECH_STACKS:
            pbuf.append(f"{_STACK_NAMES[k]}×{v}")
    # 玩家护盾（读 player dict shields；expire_at 绝对秒折算，同旧逻辑）
    shields = player.get("shields") or {}
    for sname, s in shields.items():
        if (s or {}).get("value", 0) > 0:
            _exp = (s or {}).get("expire_at")
            _left_sec = None
            if isinstance(_exp, (int, float)):
                _left_sec = float(_exp) - _now_t
            # 旧档 {turns} 兼容：无 expire_at 时按 turns 折算
            if _left_sec is None and (s or {}).get("turns") is not None:
                _left_sec = max(0.0, float(s.get("turns", 0) or 0)) * (ACT_TICK or 1.0)
            if _left_sec is not None and _left_sec > 0:
                _turns = max(1, int(round(_left_sec / (ACT_TICK or 1.0))))
                pbuf.append(_T.text("st.shield_ticks", tail=s['value'], ticks=_turns))
            else:
                pbuf.append(_T.text("st.shield", tail=s['value']))
    if pbuf:
        parts.append(_T.text("st.self_buffs", buffs=' '.join(pbuf)))
    # 敌方状态（当前主目标怪；saintess_engine 效果容器 effects）
    ebuf = []
    _eb = self._b_enemy(b) or {}
    _eb_disp = _eb.get("effects") or {}
    if not isinstance(_eb_disp, dict):
        _eb_disp = {}
    for k, v in _eb_disp.items():
        if k not in _E_BUFF_NAMES:
            continue
        # bar 状态/复杂值（shaken/curse = {val, threshold, ...}）非刻 buff，跳过；
        # dict 有 expire（saintess_engine 控制/buff 形态）参与折算，不做 dict>int 比较
        if isinstance(v, dict):
            if "expire" not in (v or {}) and not v.get("mode"):
                continue
            # V 系列叠层条目（effects[key].stacks）：标/stacks>0 显示
            _vsv = int(v.get("stacks", 0) or 0) if v.get("stacks") is not None else 0
            if _vsv > 0 and "expire" not in (v or {}) and not v.get("mode"):
                v = _vsv
            elif _vsv > 0 and k in ("fire_mark", "ice_mark", "thunder_mark", "hunt_mark", "soul_mark"):
                ebuf.append(f"{_E_BUFF_NAMES[k]}×{_vsv}")
                continue
        elif not v or not (v > 0):
            continue
        # shield 存护盾值（HP 量）、元素印记存层数——非刻语义，按各自格式显示
        if k == "shield":
            ebuf.append(f"{_E_BUFF_NAMES[k]}{v}")
            continue
        if k in ("fire_mark", "ice_mark", "thunder_mark"):
            ebuf.append(f"{_E_BUFF_NAMES[k]}×{v}")
            continue
        left_tag, _ = self._buff_left_ticks(k, v, _now_t)
        ebuf.append(f"{_E_BUFF_NAMES[k]}{('(' + left_tag + ')') if left_tag else ''}")
    # 挂敌身条（破绽/诅咒等）：effects[BAR_STATE_PREFIX+key] → 显示当刻积蓄/阈值
    # （结算到当前刻再读；阈值随触发递增，玩家据此决策「继续推还是换目标」）
    try:
        from saintess_engine.gauge import bar_settle, bar_def, _state_prefix
        _pfx = _state_prefix()
        _now_b = float(getattr(b, "_now", 0.0) or 0.0)
        for _k, _v in list(_eb_disp.items()):
            if not (isinstance(_k, str) and _k.startswith(_pfx)
                    and isinstance(_v, dict)):
                continue
            _bk = _k[len(_pfx):]
            _bd = bar_def(_bk)
            if not _bd:
                continue
            bar_settle(_eb, _bk, _now_b)
            ebuf.append(f"💥{_bd.get('name') or _bk} {int(_v.get('val', 0) or 0)}"
                        f"/{int(_v.get('threshold', 0) or 0)}")
    except Exception:
        pass  # 条显示异常不影响战报
    # 敌方狂暴（v58 mech）
    if _eb.get("enraged"):
        ebuf.append(_T.static("st.enrage"))
    # v114：敌方援军（真召唤实体）——独立行『👥 援军：爪牙×2（HP 320/320、300/300）』
    mins = getattr(b, "e_minions", []) or []
    if mins:
        _grp = {}
        for _m in mins:
            _grp.setdefault(_m.get("name", _T.static("st.minion")), []).append(_m)
        for _nm, _ms in _grp.items():
            parts.append(_T.text("st.reinforce", name=_nm, n=len(_ms)) + "、".join(
                f"{_m.get('hp', 0)}/{_m.get('max_hp', 1)}" for _m in _ms) + "）")
    # DOT/减益重构（契约 §7）：敌方持续减益（毒/灼烧/标记/流血）读 enemy["debuffs"]
    deb = _eb.get("debuffs") or {}
    for k, d in deb.items():
        if k in _DEBUFF_NAMES:
            _n = int((d or {}).get("n", 0) or 0)
            if _n > 0:
                ebuf.append(f"{_DEBUFF_NAMES[k]}×{_n}")
    # 异常抗性（dot_res>0 才显示——普通怪不设键=0）
    _dres = float(_eb.get("dot_res", 0) or 0)
    if _dres > 0:
        ebuf.append(_T.text("st.anti", pct=int(_dres * 100)))
    if ebuf:
        parts.append(_T.text("st.enemy_buffs", buffs=' '.join(ebuf)))
    return "\n".join(parts)

def _resource_line(self, player: dict, b) -> str:
    """职业资源条（v181.M-R3：读当前战斗玩家 actor 的 effects 叠层）。

    v95.4/v181.M 前实现读 player["resources"] + core_resource_def——该键已无
    生产写入（死字段，R3 清理）；saintess_engine 战斗内职业资源 = actor.effects 叠层
    （技能 mech/装配层 apply op=add，cap 见 EFFECT_RULES）。本行从 b 的玩家
    actor（sides_of("player") 按 qq_id 匹配，无 qq_id/未命中回落
    human_controlled 焦点）读 effects，经 resource_stack_text 白名单展示；
    无战斗/无 actor/无白名单资源 → ""（调用方已判空拼接，兼容安全）。
    """
    if b is None:
        return ""
    p_acts = []
    try:
        _sof = getattr(b, "sides_of", None)
        if callable(_sof):
            p_acts = list(_sof("player"))
        else:
            p_acts = list((getattr(b, "sides", None) or {}).get("player") or [])
    except Exception:
        p_acts = []
    if not p_acts:
        return ""
    me = None
    _qq = str(player.get("qq_id") or "")
    if _qq:
        for _a in p_acts:
            if str(_a.get("qq_id") or "") == _qq:
                me = _a
                break
    if me is None:
        # 兜底：无 qq_id 的 actor（旧测试/简构 actor）→ human_controlled/玩家 kind
        for _a in p_acts:
            if _a.get("human_controlled") or _a.get("kind") == "player":
                me = _a
                break
    if me is None:
        return ""
    try:
        _txt = resource_stack_text(me.get("effects") or {})
    except Exception:
        _txt = ""
    return f"⚡ {_txt}" if _txt else ""

def _player_unit_for_formation(self, player: dict) -> dict:
    """v2 多对多站位图：把玩家单机单位表示为站位单位 dict（并入我方阵列展示用）。
    只读 player，不改动原 dict；rank/reach 按职业 default_rank/reach（数据层已落地）。"""
    cls = player.get("class_name", "")
    cls_info = _cc.CLASSES.get(cls, {}) or {}
    cls_cn = cls_info.get("name") or cls
    return {
        "uid": "p_self",
        "side": "ally",
        "rank": int(cls_info.get("default_rank", 2) or 2),
        "reach": int(cls_info.get("reach", 2) or 2),
        "name": f"{player.get('name', '你')}({cls_cn})",
        "hp": player.get("hp", 0), "max_hp": player.get("max_hp", 0),
        "defending": False, "charging": None,
    }

def _battle_formation_panel(self, player: dict, b) -> str:
    """v2 多对多站位图面板（§4.4）：双方各一层行（formation_view），含蓄力标记。
    敌方= b.sides 存活阵列（N5b4-1：旧引擎 .enemies 与 saintess_engine sides 统一走
    b.sides——旧 v180F 已播种 sides，展示层不依赖引擎类型）；我方= 单机 [玩家]。
    阵亡（敌全灭）面板不输出敌方行。

    v127.3 目标编号：敌方 a1/a2…（A{n}层），我方 b1（B{n}层）——『技能1 a2』指定目标。
    """
    from saintess_engine.formation import alive_units
    allies = [self._player_unit_for_formation(player)]
    ally_rows = formation_view(alive_units(allies), side="ally")
    _enemies = (getattr(b, "sides", None) or {}).get("enemy") or []
    _alive_enemies = alive_units(_enemies)
    enemy_rows = formation_view(_alive_enemies, side="enemy") if _alive_enemies else []
    panel = ((_T.static("bf.enemy_head") + "\n".join(enemy_rows) + "\n") if enemy_rows else "") \
        + _T.static("bf.self_head") + "\n".join(ally_rows)
    return panel.rstrip("\n")

def _battle_footer(self, player: dict, b, monster: dict) -> str:
    """战斗底部：双方站位图 + 血蓝 + 资源 + 状态行(v61)。

    v164.1：站位图已逐只带血量（❤️当前/最大）——删除原下方重复的敌方血量汇总行
    （单怪行 / 多怪列表），与副本 _instance_battle_footer 观感统一。
    """
    status = self._status_line(player, b)
    lines = [
        self._battle_formation_panel(player, b),
    ]
    # v163 全局时刻显示（野外/世界Boss）：b._now = 战斗绝对时刻（1 刻 = 1 游戏秒）
    try:
        _bnow = float(getattr(b, "_now", 0.0) or 0.0)
        lines.insert(1, _T.text("bf.clock", s=_bnow))
    except Exception:
        pass
    lines.append(_T.text("bt.hp_mp", hp=player['hp'], hpmax=player['max_hp'], mp=player['mp'],
                     mpmax=player['max_mp']))
    rl = self._resource_line(player, b)
    if rl:
        lines.append(rl)
    if status:
        lines.append(status)
    # v110 P0（#119 宠物不动）：战斗中显示宠物可用性（饿肚子/Lv 不足），防止玩家
    # 困惑『宠物怎么不出手』——饱食度 =0 技能失效是设计，但此前无任何提示。
    _pnote = pet_battle_status_note(getattr(b, "pet", None))
    if _pnote:
        lines.append(_pnote)
    # v127.3 选敌引导：站位图编号 a1/a2(敌) b1/b2(友)，『技能 <槽位> <编号>』指定目标
    lines.append(_T.static("bf.select_tip"))
    return "\n".join(lines)

def _handle_victory(self, event, group_id, qq_id, player, monster, result, extra_kills=None):
    """击败怪物：经验/金币/掉落/任务进度（P4-9 壳，async generator 语义保留）

    v181.P4-9（方案 A）：1803–2201 段纯同步结算已随迁 services.battle_settlement.victory_settle
    （等级差曲线/组队/公会/宠物/坐骑/世界事件/运势/统计声望/图纸/装备/蛋/缰绳/符文/原石/
    符文收益/护符/材料/求知/exp 落库重读/rule_fire(battle_win,win)/进度条面板行骨架）；
    命令层保留 async generator yield 流（v3.4 铁律）+ 战斗锁解锁/清战斗 + 2202–2297 段
    （公会任务推进/升级/quest 进度/野王广播/塔卫/成就/rule 公告/下一步指引/收尾行）。
    行为零变化（快照测试逐字段全等）。

    v130.7 意见#17：extra_kills=同场其余击杀单位快照（多目标战副怪）——经验/金币/
    掉落仍只按主怪 monster 结算一次，任务进度按全部击杀逐个计数。"""
    self._unlock_battle(group_id, qq_id)
    db.clear_battle(group_id, qq_id)
    victory_settle = _ST.victory_settle
    _r = victory_settle(_settle_host(), group_id, qq_id, player, monster, result, extra_kills=extra_kills)
    lines = _r["lines_pre"]
    player = _r["player"]
    _rule_txt = _r["rule_txt"]
    # ---- L3 玩家级反应总线（v181 L3-P2：原 L2034-2118 手动段 公会每日/升级/
    #   任务/周常/野王/塔卫/成就 收敛为 battle_victory 订阅——行序与空行规则由
    #   总线 blank 参数保证，文案零变化；升级订阅方重绑 player 供后续使用）----
    killed = [dict(k) for k in (extra_kills or [])]
    if monster and not any(k.get("name") == monster.get("name") for k in killed):
        killed.insert(0, monster)
    from .player_events import fire as _pe_fire
    from .player_events import ensure_registered as _pe_ensure   # 触发注册（幂等）
    _pe_ensure()
    _vctx = {
        "kind": "field",
        "group_id": group_id, "qq_id": qq_id,
        "player": player, "monster": monster, "killed": killed,
        "side_effects": [],
    }
    lines += _pe_fire("battle_victory", _vctx)
    player = _vctx["player"]  # levelup 订阅方可能重绑（升级后最新 dict）
    # 野王广播副作用（原 self._broadcast 位点；订阅方行组已进 lines）
    for _se in _vctx.get("side_effects") or []:
        if _se.get("type") == "broadcast":
            try:
                self._broadcast(_se.get("text", ""))
            except Exception:
                pass
    # v97.5 行为彩蛋规则：战斗胜利后（#262：触发已提前到进度条生成前，这里只保留公告行位置）
    if _rule_txt:
        lines.append(_rule_txt)
    # v138.3 结算卡·下一步（借鉴《云海猎团》M8.4 峰终定律——终值=结算接养成指引）：
    # 把爽感直接接到养成循环上，玩家打完知道"接下来干嘛"
    _next = self._next_step_hint(group_id, qq_id, player, monster)
    if _next:
        lines.append(_next)
    lines.append("━━━━━━━━━━━━")
    lines.append(_T.text("bt.hp_mp", hp=player['hp'], hpmax=player['max_hp'], mp=player['mp'],
                     mpmax=player['max_mp']))
    yield event.plain_result("\n".join(lines))

def _next_step_hint(self, group_id, qq_id, player, monster) -> str:
    """v138.3 结算卡·下一步指引（P4-9 转发壳：实现随迁 services.battle_settlement.next_step_hint）"""
    next_step_hint = _ST.next_step_hint
    return next_step_hint(_settle_host(), group_id, qq_id, player, monster)

def _nearest_town(self, cur_map: str) -> str:
    """BFS 找离当前地图最近的城镇（P4-9 转发壳：实现随迁 services.battle_settlement.nearest_town，
    与回城卷轴 economy._nearest_town 同逻辑，M22 P3）。"""
    nearest_town = _ST.nearest_town
    return nearest_town(_settle_host(), cur_map)

def _handle_defeat(self, event, group_id, qq_id, player, monster, result):
    """战败：扣金币/回城（不扣宠物饱食度——宽容设计，见胜利路径 1475 注释）

    v181.P4-9（方案 A）：全同步编排（stats/扣金/红名/nearest_town/复活羽毛挂起/落库/
    rule_fire(battle_win, lose)）已随迁 services.battle_settlement.defeat_settle；
    命令层保留 async generator yield 流（v3.4 铁律）+ 战斗锁解锁/清战斗。
    行为零变化（快照测试逐字段全等）。"""
    self._unlock_battle(group_id, qq_id)
    db.clear_battle(group_id, qq_id)
    defeat_settle = _ST.defeat_settle
    _r = defeat_settle(_settle_host(), group_id, qq_id, player, monster, result)
    yield event.plain_result("\n".join(_r["lines"]))

async def hunt_boss(self, event: AstrMessageEvent, group_id, qq_id, player):
    cur = db.get_world_event()
    now = int(time.time())
    if not cur:
        # 是否有过期的 Boss 事件待清除
        expired = db.get_world_event(include_expired=True)
        if expired and expired["etype"] == "boss" and now >= expired["ends_at"]:
            db.clear_world_event()
            yield event.plain_result(_T.static("wb.gone"))
            return
        yield event.plain_result(_T.static("wb.none"))
        return
    if cur["etype"] != "boss":
        yield event.plain_result(_T.static("wb.none"))
        return
    b = cur["data"].get("boss", {})
    # v49 意见#5：世界 Boss 指定地点，必须到达该地图才能讨伐
    boss_map = b.get("map", "")
    if boss_map and player["cur_map"] != boss_map:
        cur_map_name = _cs.MAP_BY_ID.get(player["cur_map"], {}).get("name", player["cur_map"])
        yield event.plain_result(
            _T.text("wb.other_map", name=b.get('name', '?'), map=b.get('map_name', '未知之地'),
                cur=cur_map_name)
        )
        return
    # 已有世界BOSS战斗状态 → 显示当前状态（N5b4-3：saintess_engine state 存 sides）
    battle = db.get_battle(group_id, qq_id)
    if battle and battle["state"].get("type") == "worldboss":
        _st = battle["state"]
        if _st.get("sides"):
            _enemies = [u for u in (_st.get("sides", {}).get("enemy") or [])
                        if (u.get("hp") or 0) > 0]
            _sum_hp = sum(max(0, u.get("hp", 0)) for u in _enemies)
            _sum_max = sum(max(0, u.get("max_hp", u.get("hp", 1))) for u in _enemies)
            _pct = max(0, int(_sum_hp / max(1, _sum_max) * 100))
            yield event.plain_result(
                _T.text("wb.joined_arr", name=_enemies[0].get('name', '?') if _enemies else b.get('name', '?'),
                    left=len(_enemies), total=_sum_hp, killed=_sum_max, pct=_pct) + "\n  ".join([f"{u.get('name','?')} ❤️{max(0,u.get('hp',0))}" for u in _enemies]) + _T.text("wb.you_hp", hp=player['hp'], hpmax=player['max_hp'], mp=player['mp'],
                                                                                                                   mpmax=player['max_mp'])
            )
        elif _st.get("enemies"):
            _enemies = [u for u in _st.get("enemies") if (u.get("hp") or 0) > 0]
            _sum_hp = sum(max(0, u.get("hp", 0)) for u in _enemies)
            _sum_max = sum(max(0, u.get("max_hp", u.get("hp", 1))) for u in _enemies)
            _pct = max(0, int(_sum_hp / max(1, _sum_max) * 100))
            yield event.plain_result(
                _T.text("wb.joined_arr", name=b.get('name', '?'), left=len(_enemies), total=_sum_hp,
                    killed=_sum_max, pct=_pct) + "\n  ".join([f"{u.get('name','?')} ❤️{max(0,u.get('hp',0))}" for u in _enemies]) + _T.text("wb.you_hp", hp=player['hp'], hpmax=player['max_hp'], mp=player['mp'],
                                                                                                                   mpmax=player['max_mp'])
            )
        else:
            b2 = battle["state"].get("enemy", {})
            pct = max(0, int(b2.get("hp", 0) / max(1, b2.get("max_hp", 1)) * 100))
            yield event.plain_result(
                _T.text("wb.joined_solo", name=b2.get('name', '?'), hp=max(0, b2.get('hp', 0)),
                    hpmax=b2.get('max_hp', 0), pct=pct, hp2=player['hp'],
                    hpmax2=player['max_hp'], mp=player['mp'], mpmax=player['max_mp'])
            )
        return
    # 第一次进入：创建世界BOSS战斗（Boss 没技能则按等级配 2 个攻击技能）
    import random as _rnd
    if not b.get("skills"):
        cand = [s for s, si in _cq.MONSTER_SKILLS.items() if si.get("kind") in (K_PHYS, K_MAGI)]
        b["skills"] = _rnd.sample(cand, min(2, len(cand)))
    # v2 多对多：世界 Boss 经 build_monster_group 生成敌方阵列（Boss+2 爪牙）。
    # 全局数据升级为 {"enemies": [...]}（首元素=主目标），旧 hp/max_hp/name 保留作主目标汇总兼容。
    # 判定 is_boss=True 触发 build_monster_group 的分支；阵列为 [Boss(rank1) + 爪牙(rank1)]——
    # 世界 Boss 保持 rank1 让所有玩家（含近战 reach1）都能打到主目标（全局讨伐设计，避免爪牙当肉盾挡住近战贡献）。
    wmap = {"id": b.get("map", ""), "name": b.get("map_name", ""),
            "area": b.get("map", "")}
    _old_hp = b.get("hp")
    was_hp_missing = "enemies" not in b
    b["uid"] = "wb_0"
    b["rank"] = 1
    b["reach"] = 1
    b["is_boss"] = True
    b["is_elite"] = False
    b.setdefault("effects", {})
    b["defending"] = False; b["charging"] = None
    # DOT/减益重构（契约 §6）：世界 Boss 全局共享减益层/dot 结算计数/抗性（事件数据可覆写）。
    # 老世界 Boss 存档无这些键 → setdefault 兜底，保证向前兼容。
    b.setdefault("debuffs", {})
    b.setdefault("dot_act", 0)
    b.setdefault("dot_res", 0.9)
    b.setdefault("immune_dots", [])
    # v1.2（契约 §11）：减益适应（毒/灼烧叠加抗性）全局共享；老存档无键 → setdefault 兜底。
    b.setdefault("adapt", {"poison": 0.0, "burn": 0.0})
    # 世界 Boss：scale_main=False（数值由事件配置，不把主怪 ×0.7；多对多才缩主怪）
    _boss_grp = build_monster_group(b, wmap, player, scale_main=False)
    # DOT/减益重构（契约 §6/§11）：确保敌方阵列每个单位带 debuffs/dot_res/immune_dots/adapt。
    # 主目标从全局 b 拷入；爪牙经 _scale_monster=dict(m) 浅拷贝已带上 b 的键，这里再逐个兜底。
    _gdebuff = {k: dict(v) for k, v in (b.get("debuffs") or {}).items()}
    for _u in _boss_grp:
        _u.setdefault("debuffs", {k: dict(v) for k, v in _gdebuff.items()})
        _u.setdefault("dot_res", b.get("dot_res", 0.9))
        _u.setdefault("immune_dots", list(b.get("immune_dots") or []))
        _u.setdefault("adapt", dict(b.get("adapt") or {"poison": 0.0, "burn": 0.0}))
    _main = _boss_grp[0]
    # 已有全局 enemies（他人已打过）：新构建的爪牙按 uid 从既有全局阵列同步 hp，避免重置
    _existing = b.get("enemies")
    if _existing:
        _ex_by_uid = {u.get("uid"): u for u in _existing}
        for _ug in _boss_grp:
            _eu = _ex_by_uid.get(_ug.get("uid"))
            if _eu is not None and _eu.get("hp") is not None:
                _ug["hp"] = _eu.get("hp", _ug.get("hp", 0))
    # 存量单一 Boss 数据（无 enemies 键）：把旧全局 hp 同步进主目标，保证不重置
    if was_hp_missing and _old_hp and _main.get("hp"):
        _main["hp"] = _old_hp
    b["enemies"] = [dict(u) for u in _boss_grp]  # 拷贝：避免 b["enemies"][0] is b 全局自引用（P3 序列化递归）
    b["name"] = _main.get("name", b.get("name", "?"))
    b["hp"], b["max_hp"] = _main.get("hp", 0), _main.get("max_hp", _main.get("hp", 1))
    # N5b4-3：世界Boss 切 saintess_engine（Boss 自动行动 + CTB 时间轴；dmg_mult 构造参数）
    _tb = self._title_bonus(group_id, qq_id)
    _BR.prepare_player_for_battle(player, _tb, _es_arg(db))
    _sides = _BR.build_sides(player=player, enemies=[dict(u) for u in _boss_grp])
    # 玩家侧 actor 塞 bonus.panel（v181.M-bonus 统一容器；Boss 敌侧不塞——回落
    # battle.title_bonus 保持 N5b4-3 行为）
    try:
        for _a in _sides.get("player", []):
            _a["bonus"] = {"panel": dict(_tb or {}), "cap": {}, "cost": {}}
    except Exception:
        pass
    # 敌 actor 装配（weapon/affix 是玩家侧；敌侧只需 auto_act 行动配置）
    for _a in _sides.get("enemy", []):
        if not _a.get("auto_act"):
            _a["auto_act"] = {"act": {"type": "attack"}}
    from saintess_engine import Battle as B2
    # v2026-09-11：GM 世界 Boss 伤害倍率接回**承伤乘区**（taken_calc 事件）。
    #   引擎 Battle 的 dmg_mult 构造参数只存不读（旧引擎 _boss_dmg_filter 那段没迁过来）
    #   → gm_伤害 曾静默失效；现走内容装配层 battle_worldboss_procs 挂 Boss actor。
    #   pet=db.pet_get() 同属「传了但引擎不读」——宠物参战归随从 actor 工厂（随从线），
    #   本处不再静默传参（传了会让人误以为宠物已参战）。
    _wb_mult = float(db.get_boss_dmg_mult(qq_id) or 1.0)
    if _wb_mult != 1.0:
        for _a in _sides.get("enemy", []):
            _WBP.apply_gm_dmg_mult(_a, _wb_mult)
    nb = B2("worldboss", sides=_sides, title_bonus=_tb)
    # 敌 actor 技能索引已由 B2 构造建立；给 Boss 配首个技能自动行动（AI 轮换属上层怪 AI 模块）
    try:
        _boss_a = next((u for u in nb.sides_of("enemy") if u.get("is_boss")), None)
        if _boss_a:
            _idx = _boss_a.get("_skill_index") or {}
            _sk_names = [_k for _k, _inf in _idx.items()
                         if _inf and _inf.get("name") == _k]  # 中文名键 = 技能显示名
            if _sk_names:
                _boss_a["auto_act"] = {"act": {"type": "skill", "skill": _sk_names[0]}}
    except Exception:
        pass
    # 同步回全局事件（含 enemies 阵列，供其他玩家响应共享血量）
    db.save_world_event(cur["etype"], cur["ends_at"], cur["data"])
    db.save_battle(group_id, qq_id, nb.to_state())
    self._lock_battle(group_id, qq_id)
    pct = max(0, int(_main.get("hp", 0) / max(1, _main.get("max_hp", 1)) * 100))
    yield event.plain_result(
        _T.text("wb.start", name=_main['name'], lv=_main.get('lv', 30), hp=_main.get('hp', 0),
            hpmax=_main.get('max_hp', 1), pct=pct,
            panel=self._battle_formation_panel(player, nb))
    )

def _grant_worldboss_drop(self, group_id, qq_id, key):
    """v104 M06 P2-3：发放世界 Boss 特殊掉落（P4-9 转发壳：实现随迁
    services.battle_settlement.grant_worldboss_drop）。返回物品中文名或 None"""
    grant_worldboss_drop = _ST.grant_worldboss_drop
    return grant_worldboss_drop(_settle_host(), group_id, qq_id, key)

async def _worldboss_act(self, event, group_id, qq_id, player, b, action, skill_name=None, target=None):
    """世界BOSS战斗行动（attack/skill/defend 共用）
    1. 同步全局 Boss 阵列血量到本地 b.sides_of("enemy")（其他玩家可能也打了，逐 uid）
    2. 玩家行动（target 指定目标）→ 贡献累积（全阵列伤害合计）→ 本地写回全局阵列
    3. 全阵列无存活（saintess_engine result=victory）→ Boss 死亡结算；玩家死亡 → 走死亡结算

    N5b4-3（saintess_engine）：玩家 action 走 human_act（actor 副本）+ sync 回写；
    DOT 由 saintess_engine schedule 自动结算（actor.state dot 规则），退役旧全局
    debuffs/adapt 共享 + 每4次强制结算补丁（鱼鱼拍板按新引擎语义）。
    """
    cur_evt = db.get_world_event()
    if not cur_evt or cur_evt["etype"] != "boss":
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        yield event.plain_result(_T.static("wb.gone"))
        return
    gboss = cur_evt["data"]["boss"]
    genemies = gboss.get("enemies")
    # N5b4-3（saintess_engine）：本地敌 actor = b.sides_of("enemy")（死亡不移除 → 读存活过滤）；
    # 行动前全局阵列血量 → 本地（逐 uid；旧单怪数据回落主目标 hp）。
    _l_enemies = [u for u in b.sides_of("enemy") if (u.get("hp") or 0) > 0] or b.sides_of("enemy")
    if genemies:
        _g_by_uid = {u.get("uid"): u for u in genemies}
        for u in _l_enemies:
            _gu = _g_by_uid.get(u.get("uid"))
            if _gu is not None:
                u["hp"] = _gu.get("hp", u.get("hp", 0))
    else:
        _me0 = _l_enemies[0] if _l_enemies else self._b_enemy(b)
        _me0["hp"] = gboss.get("hp", _me0.get("hp", 0))
    before = sum(max(0, u.get("hp", 0)) for u in b.sides_of("enemy"))
    # N5b4-3：saintess_engine 行动入口 human_act（副本 actor）+ 回写 player dict。
    # DOT 由 saintess_engine schedule 在行动推进中自动结算（actor.state dot 规则，
    # 本地副本语义——旧"全局共享 debuffs + 每4次强制结算"补丁按鱼鱼拍板退役）。
    logs, ended, _who = b.human_act(action, skill_name, b.focus(), target=target)
    self._sync_battle_player(player, b)
    db.update_player(group_id, qq_id, hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"])
    after = sum(max(0, u.get("hp", 0)) for u in b.sides_of("enemy"))
    dealt = max(0, before - after)  # 全阵列伤害合计（含 schedule 自动 DOT）
    contrib = gboss.setdefault("contrib", {})
    contrib[str(qq_id)] = contrib.get(str(qq_id), 0) + dealt
    # 保留"你击败了"过滤（胜利文案由结算逻辑输出）；saintess_engine 击杀日志文案可能含目标名
    lines = [x for x in logs if "你击败了" not in x]

    # 行动后：本地 b.sides_of("enemy") → 全局阵列（逐 uid 同步 hp）+ 主目标汇总
    _l_all = b.sides_of("enemy")
    if genemies:
        _l_by_uid = {u.get("uid"): u for u in _l_all}
        for _gu in genemies:
            _lu = _l_by_uid.get(_gu.get("uid"))
            if _lu is not None:
                _gu["hp"] = _lu.get("hp", _gu.get("hp", 0))
        _main_now = next((u for u in _l_all if (u.get("hp") or 0) > 0), None) or (_l_all[0] if _l_all else None)
        if _main_now:
            gboss["name"] = _main_now.get("name", gboss.get("name", "?"))
            gboss["hp"] = _main_now.get("hp", 0)
            gboss["max_hp"] = _main_now.get("max_hp", _main_now.get("hp", 1))
    else:
        _me0 = _l_all[0] if _l_all else {}
        gboss["hp"] = _me0.get("hp", gboss.get("hp", 0))

    if ended and b.result == "victory":
        # Boss 死亡结算（全阵列无存活；先于玩家死亡判断）
        lines.append("")
        lines.append(_T.text("wb.killed", name=gboss['name']))
        total = sum(contrib.values())
        top_qq = max(contrib, key=contrib.get) if contrib else None
        boss_pool = WORLD_BOSS_DROPS.get(gboss.get("name"), [])
        for qq2, d in sorted(contrib.items(), key=lambda x: -x[1]):
            p2 = self._player(group_id, qq2)
            if not p2:
                continue
            ratio = d / max(1, total)
            g = int(gboss["reward"]["gold"] * ratio * 3)
            e = int(gboss["reward"]["exp"] * ratio * 3)
            db.update_player(group_id, qq2, gold=p2["gold"] + g, exp=p2["exp"] + e)
            # v104 M06 P2-3：世界 Boss 特殊物品掉落——参与 1 件，首功再加 1 件
            item_txt = ""
            if boss_pool:
                _cnt = 2 if qq2 == top_qq else 1
                for _ in range(_cnt):
                    _it = self._grant_worldboss_drop(group_id, qq2, random.choice(boss_pool))
                    if _it:
                        item_txt += f" 🎁{_it}"
            lines.append(_T.text("wb.contrib_row", name=p2['name'], pct=d, gold=int(ratio*100), exp=g, x=e, y=item_txt))
            # L3-P3：玩家级反应总线——任何击杀都算数（鱼鱼 09-09 语义决策）。
            # 世界Boss 死亡对每个 contrib>0 玩家 fire：quests 按 boss 名/属性推进
            # （主线/每日/支线/周常，现状不推=漏接）、公会每场胜利+1、成就
            # kind=worldboss extra(worldboss:1，原 L2432 手动调用收敛)。
            # levelup 订阅方 kind 守卫仅 field（参与奖励现状不升级）。
            from .player_events import fire as _pe_fire
            from .player_events import ensure_registered as _pe_ensure   # 触发注册（幂等）
            _pe_ensure()
            _wb_monster = {"name": gboss.get("name", "世界Boss"),
                           "lv": gboss.get("lv", 30) or 30,
                           "is_boss": True}
            _wbctx = {
                "kind": "worldboss",
                "group_id": group_id, "qq_id": qq2,
                "player": p2, "monster": _wb_monster,
                "killed": [_wb_monster],
                "side_effects": [],
                "meta": {},
            }
            lines += _pe_fire("battle_victory", _wbctx)
        tp = self._player(group_id, top_qq) if top_qq else None
        if tp:
            lines.append(_T.text("wb.first", name=tp['name']))
        db.clear_world_event()
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        try:
            await self._broadcast("\n".join(lines))
        except Exception:
            pass
        if player["hp"] <= 0:
            # 同归于尽：奖励已发，玩家仍走死亡结算
            player["hp"] = 0
            for _r in self._handle_defeat(event, group_id, qq_id, player,
                                          {"name": gboss["name"], "lv": gboss.get("lv", 30)},
                                          "\n".join(lines)):
                yield _r
            return
        yield event.plain_result("\n".join(lines))
        return

    if ended and b.result == "defeat":
        # 玩家阵亡（Boss 未死）：贡献已记，同步血量，走死亡结算
        if not genemies:
            _me0 = b.sides_of("enemy")
            gboss["hp"] = (_me0[0] if _me0 else {}).get("hp", gboss.get("hp", 0))
        db.save_world_event(cur_evt["etype"], cur_evt["ends_at"], cur_evt["data"])
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        player["hp"] = 0
        for _r in self._handle_defeat(event, group_id, qq_id, player,
                                      {"name": gboss["name"], "lv": gboss.get("lv", 30)},
                                      "\n".join(lines)):
            yield _r
        return

    # Boss 未死：更新贡献 + 全局血量/阵列 + 战斗状态
    db.save_world_event(cur_evt["etype"], cur_evt["ends_at"], cur_evt["data"])
    db.save_battle(group_id, qq_id, b.to_state())
    _enemies_alive = [u for u in b.sides_of("enemy") if (u.get("hp") or 0) > 0]
    _sum_hp = sum(max(0, u.get("hp", 0)) for u in _enemies_alive or [])
    _sum_max = sum(max(0, u.get("max_hp", u.get("hp", 1))) for u in _enemies_alive or [])
    pct = max(0, int(_sum_hp / max(1, _sum_max) * 100))
    body = "\n".join(lines)
    status = self._status_line(player, b)
    rl_wb = self._resource_line(player, b)
    _enemy_line = (_T.text("wb.enemy_left", name=gboss['name'], left=len(_enemies_alive), total=_sum_hp,
                       n=_sum_max, pct=pct)
                   if len(_enemies_alive) > 1 else
                   f"👹【{gboss['name']}】❤️ {gboss['hp']:,} / {gboss['max_hp']:,}({pct}%)")
    yield event.plain_result(
        _T.text("wb.turn_panel", name=body, contrib=_enemy_line, hp=contrib[str(qq_id)],
            hpmax=player['hp'], mp=player['max_hp'], mpmax=player['mp'], tail=player['max_mp'])
        + (f"\n{rl_wb}" if rl_wb else "")
        + (f"\n{status}" if status else "")
    )

def _parse_target_qq(self, target_arg: str):
    """解析攻击目标参数：@QQ / [At:QQ] / QQ / @名字(QQ) / 名字(QQ) / 名字。返回 (qq_id, name) 或 None"""
    t = target_arg.strip()
    # [At:123]
    m = re.match(r"^\[At:(\d+)\]$", t)
    if m:
        return m.group(1), None
    # @123 或 123
    m = re.match(r"^@?(\d+)$", t)
    if m:
        return m.group(1), None
    # @名字(123) 或 名字(123) —— QQ @ 消息的文本格式（括号内是 QQ 号）
    # F1 审计修复（B7）：去掉冗余字符类 [()()]/[((]/[))]（等价于 [()]/(/)，仅符号噪声），
    # 正规化为 @名字(123)：名字内不含括号即可命中。
    m = re.match(r"^@?[^()]*\((\d+)\)$", t)
    if m:
        return m.group(1), None
    # 纯 @昵称：剥掉前导 @ 后按名字查玩家（B7：原实现含 @ 前缀无法命中 find_player_by_name）
    tp = db.find_player_by_name(t.lstrip("@"))
    if tp:
        return str(tp["qq_id"]), tp["name"]
    return None

def _red_until(self, qq_id) -> int:
    """红名截止时间（P4-9 转发壳：实现随迁 services.battle_settlement.red_until）"""
    red_until = _ST.red_until
    return red_until(_settle_host(), qq_id)

def _is_redname(self, qq_id) -> bool:
    """P4-9 转发壳：实现随迁 services.battle_settlement.is_redname"""
    is_redname = _ST.is_redname
    return is_redname(_settle_host(), qq_id)

def _get_honor(self, qq_id) -> int:
    try:
        return int(db.get_event_state(f"honor_{qq_id}") or 0)
    except (ValueError, TypeError):
        return 0

def _pvp_meta_qqs(self, state: dict):
    """PVP state → (attacker_qq, defender_qq)。

    N5b4-4（saintess_engine）：state = saintess_engine to_state + meta{attacker_qq, actor}，
    sides.player 固定 = 攻击者(发起方)、sides.enemy = 防守方（双方 actor 都透传
    qq_id）。旧格式（attacker/defender 快照键）兜底兼容（存量旧档超时清理用）。
    """
    meta = state.get("meta") or {}
    att = str(meta.get("attacker_qq", "") or "")
    if not att and isinstance(state.get("attacker"), dict):
        att = str(state["attacker"].get("qq_id", "") or "")
    deff = ""
    if isinstance(state.get("defender"), dict):
        deff = str(state["defender"].get("qq_id", "") or "")
    if not deff:
        for _sn, _acts in (state.get("sides") or {}).items():
            for _a in _acts or []:
                _q = str((_a or {}).get("qq_id", "") or "")
                if _q and _q != att:
                    deff = _q
    return att, deff

def _pvp_snapshot(self, p: dict, group_id: str = "", qq_id: str = "") -> dict:
    """玩家快照(PVP 战斗状态用)
    v109.2 P0 修复：补全战斗结算属性（此前缺 atk/def/mdef/tenacity 等 → PVP 中防御/韧性全失效，
    玩家攻击打敌方 0 防御、暴击不受敌方韧性削减——审计 P1-7 快照不消费根源）。"""
    st = player_final_stats(p["class_name"], p["level"], p.get("equipment", {}), p.get("class_tier", 0), p.get("attributes"), p.get("evolve_path", 0), self._title_bonus(group_id, qq_id), p.get("race"))
    cls_info = _cc.CLASSES.get(p["class_name"], {}) or {}
    return {
        "qq_id": str(p["qq_id"]), "name": p["name"],
        "class_name": p["class_name"], "level": p["level"],
        "hp": p["hp"], "mp": p["mp"], "max_hp": st["max_hp"], "max_mp": st["max_mp"],
        "equipment": p.get("equipment", {}), "class_tier": p.get("class_tier", 0),
        "attributes": p.get("attributes", {}),
        "evolve_path": p.get("evolve_path", 0), "race": p.get("race"),
        # v2 多对多站位：PVP 1v1 双方均为 rank1（无队友分层），reach 按职业（§8.1/9.1）
        "uid": f"p_{str(p['qq_id'])}",
        "side": "enemy",
        "rank": 1,
        "reach": int(cls_info.get("reach", 2) or 2),
        "defending": False, "charging": None,
        # v109.2 战斗结算属性（_enemy_stats/_pvp_enemy_turn 消费）
        "atk": st.get("atk", 0), "def": st.get("def", 0),
        "matk": st.get("matk", 0), "mdef": st.get("mdef", 0),
        "spd": st.get("spd", 0), "crit": st.get("crit", 0.05),
        "tenacity": st.get("tenacity", 0) or 0, "luck": st.get("luck", 0) or 0,
        "pene_phys": st.get("pene_phys", 0) or 0, "pene_magi": st.get("pene_magi", 0) or 0,
        "pene_flat": st.get("pene_flat", 0) or 0, "pene_mflat": st.get("pene_mflat", 0) or 0,
        "phys_reduce": st.get("phys_reduce", 0) or 0, "magic_reduce": st.get("magic_reduce", 0) or 0,
        "block": st.get("block", 0) or 0, "dodge": st.get("dodge", 0) or 0,
        "elem_res": st.get("elem_res", 0) or 0, "abyss_res": st.get("abyss_res", 0) or 0,
        "precise": st.get("precise", 0) or 0,  # v110 P1-3：快照补导出（防守方精准/攻击端读 _enemy_stats）
    }

def _pvp_handle_timeout(self, battle, group_id, qq_id) -> bool:
    """PVP 超时检查：5 分钟无行动自动解除(防对方离线卡死)。返回 True=已解除"""
    if time.time() - battle.get("updated_at", 0) > _cc.PVP_TIMEOUT_SEC:
        st = battle["state"]
        # N5b4-4（saintess_engine）：双方 qq 从 meta/sides 读（旧格式快照键兜底兼容）
        _att_qq, _def_qq = self._pvp_meta_qqs(st)
        _my = str(qq_id)
        # 对方 = 两方里非我的那个（都不匹配时取防守方——能走到超时的多半是防守方离线）
        opp_qq = _def_qq if _my == _att_qq else _att_qq
        # 攻击方获得袭击 CD，防脱离后立刻再骚扰
        self._set_pvp_cd(_att_qq or _my)
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        if opp_qq:
            self._unlock_battle(group_id, opp_qq)
            db.clear_battle(group_id, opp_qq)
        return True
    return False

def _set_pvp_cd(self, qq_id):
    """PVP 结束后主动攻击方 2 分钟袭击冷却(防打一下逃跑反复骚扰)"""
    db.set_event_state(f"pvp_cd_{qq_id}", str(int(time.time()) + 120))

def _pvp_cd_left(self, qq_id) -> int:
    try:
        return max(0, int(db.get_event_state(f"pvp_cd_{qq_id}") or 0) - int(time.time()))
    except (ValueError, TypeError):
        return 0

async def honor_shop(self, event: AstrMessageEvent, group_id, qq_id, player, raw):
    """荣誉商店：『荣誉』查看，『荣誉 兑换 <编号>』兑换"""
    if raw.startswith("兑换"):
        num = raw[2:].strip()
        if not num.isdigit():
            yield event.plain_result(_T.static("hn.usage"))
            return
        async for _r in self._honor_buy(event, group_id, qq_id, player, int(num)):
            yield _r
        return
    honor = self._get_honor(qq_id)
    lines = [_T.text("hn.title", honor=honor), "━━━━━━━━━━━━"]
    for i, item in _b143.HONOR_SHOP.items():
        lines.append(f"{i}. {item['name']} ｜ {item['cost']} 荣誉")
        lines.append(f"   {item['desc']}")
    lines.append("━━━━━━━━━━━━")
    lines.append(self._tip("honor"))
    if self._is_redname(qq_id):
        lines.append(_T.text("hn.red", min=max(0, self._red_until(qq_id) - int(time.time())) // 60))
    yield event.plain_result("\n".join(lines))

async def _honor_buy(self, event, group_id, qq_id, player, num):
    """荣誉兑换：扣荣誉 → 按 reward 类型发放（v99.4 数据化 → data/honor_shop.py）"""
    item = _b143.HONOR_SHOP.get(num)
    if not item:
        yield event.plain_result(_T.text("hn.no_item", idx=num))
        return
    honor = self._get_honor(qq_id)
    if honor < item["cost"]:
        yield event.plain_result(_T.text("hn.short", name=item['name'], need=item['cost'], have=honor))
        return
    reward = item.get("reward") or {}
    # v104 M09 修复：item 类防重复兑换——背包已有同名物品则拦截（title 类保持可重复）
    # v105 M09 P2-1：消耗品用完(count=0)可再次兑换，拦截文案按类型区分——
    #   消耗品提示"用完再来"，外观珍品保留"每人限兑一件"（原文案与可再兑行为矛盾）
    if reward.get("type") == "item":
        _iname = (reward.get("item") or {}).get("name") or item["name"]
        if db.count_item(group_id, qq_id, _iname) > 0:
            _ritem = reward.get("item") or {}
            if _ritem.get("stackable") or _ritem.get("type") == "消耗品":
                yield event.plain_result(_T.text("hn.has_bag", name=item['name']))
            else:
                yield event.plain_result(_T.text("hn.has", name=item['name']))
            return
    # v104 M09 P2 修复：title 类重复兑换拦截（此前无 honor_{title_id}_{qq} 检查，连兑 2 次白扣荣誉）
    if reward.get("type") == "title" and db.get_event_state(f"honor_{reward['title_id']}_{qq_id}"):
        yield event.plain_result(_T.text("hn.has_title", name=reward['label']))
        return
    db.set_event_state(f"honor_{qq_id}", str(honor - item["cost"]))
    import uuid as _uuid
    if reward.get("type") == "title":
        db.set_event_state(f"honor_{reward['title_id']}_{qq_id}", "1")
        yield event.plain_result(
            _T.text("hn.ok_title", name=reward['label'], cost=item['cost'], x=reward.get('msg', '')))
    elif reward.get("type") == "item":
        db.add_item(group_id, qq_id, f"{reward.get('item_prefix', 'h_')}{_uuid.uuid4().hex[:8]}", reward["item"])
        yield event.plain_result(f"⚜️ 你兑换了【{item['name']}】！(花费 {item['cost']} 荣誉)\n{reward.get('msg', '')}")
    else:
        yield event.plain_result(_T.text("hn.bad", ))

async def _pvp_start(self, event, group_id, qq_id, player, target_arg):
    """PVP 发起：『攻击 @目标』(安全区/等级保护/灰名/袭击CD)"""
    cd = self._pvp_cd_left(qq_id)
    if cd > 0:
        yield event.plain_result(_T.text("pv.cd", sec=cd))
        return
    parsed = self._parse_target_qq(target_arg)
    if not parsed:
        yield event.plain_result(_T.text("pv.no_user", arg=target_arg))
        return
    target_qq, _tname = parsed
    if str(target_qq) == str(qq_id):
        yield event.plain_result(_T.static("pv.self"))
        return
    target_player = db.get_player(group_id, target_qq)
    if not target_player:
        yield event.plain_result(_T.static("pv.no_char"))
        return
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("pv.busy_self"))
        return
    if self._in_battle(group_id, target_qq):
        yield event.plain_result(_T.text("pv.busy_target", name=target_player['name']))
        return
    # v84 新手保护（26 章二）：Lv.<10 不能被攻击
    if target_player["level"] < 10:
        yield event.plain_result(_T.text("pv.newbie_t", name=target_player['name'], lv=target_player['level']))
        return
    if player["level"] < 10:
        yield event.plain_result(_T.text("pv.newbie_self", lv=player['level']))
        return
    # 安全区检查（城镇区域不可 PK；'城镇外郊' 类型数据不存在，v102.1 清理）
    cur_map = _cs.MAP_BY_ID.get(player["cur_map"], {})
    tgt_map = _cs.MAP_BY_ID.get(target_player["cur_map"], {})
    if cur_map.get("type") == _cc.MAP_TYPE_TOWN or tgt_map.get("type") == _cc.MAP_TYPE_TOWN:
        yield event.plain_result(_T.static("pv.safe"))
        return
    # v110 审计修复：26 章 §二「发起：野外同地图」——原实现可跨任意地图按名远程袭击
    if player["cur_map"] != target_player["cur_map"]:
        yield event.plain_result(_T.text("pv.diff_map", name=target_player['name']))
        return
    # 等级保护：等级差 > 10 不能主动攻击
    if abs(player["level"] - target_player["level"]) > 10:
        yield event.plain_result(_T.text("pv.gap", mine=player['level'], theirs=target_player['level']))
        return
    # N5b4-4：创建 PVP 战斗状态（saintess_engine）——sides 双 actor 持久化 + meta 外壳。
    #   sides.player 固定 = 攻击者(发起方)、sides.enemy = 防守方；双方 human_controlled
    #   （PVP 轮流制由命令层 meta.actor 驱动，enemy 侧真人 actor 不自动行动）。
    #   bonus.panel（v181.M-bonus 统一数值容器；N5b4-4 起 per-actor 增幅）：Battle.
    #   title_bonus 战斗级单份无法区分双人——各自外部增幅（core/stat_bonus.py 聚合）
    #   塞 actor["bonus"]["panel"]，stats 读 actor 优先，双方面板各自精确；
    #   battle 级传 {} 仅兜底。
    from saintess_engine import Battle as B2
    # 0. 双方各自外部增幅聚合（core 直调 + 已 load 的 player dict，避免 _title_bonus
    #    内部再读档；失败降级空 dict）
    from .stat_bonus import stat_bonus as _core_tb
    _tb_me = {}
    _tb_opp = {}
    try:
        _tb_me = _core_tb(group_id, qq_id, player) or {}
        _tb_opp = _core_tb(group_id, target_qq, target_player) or {}
    except Exception:
        pass
    # ① 开战仪式（仅攻击方：echo_bless/神龛祝福是发起者消耗自己的祝福；max_hp/max_mp
    #    重算带自己增幅 → 与 actor_stats 面板口径一致）
    _BR.prepare_player_for_battle(player, _tb_me, _es_arg(db))
    # ② 防守方：拷贝 + 只实时化 max_hp/max_mp（不跑仪式——防消费对方 event_state；
    #    外部增幅用防守方自己的）
    _def_p = dict(target_player)
    try:
        _dst = player_final_stats(
            _def_p.get("class_name", "战士"), int(_def_p.get("level", 1) or 1),
            _def_p.get("equipment") or {}, int(_def_p.get("class_tier", 0) or 0),
            _def_p.get("attributes"), int(_def_p.get("evolve_path", 0) or 0),
            _tb_opp, _def_p.get("race"))
        if _dst.get("max_hp"):
            _def_p["max_hp"] = int(_dst["max_hp"])
        if _dst.get("max_mp") is not None:
            _def_p["max_mp"] = int(_dst["max_mp"])
    except Exception:
        pass
    # ③ 组 sides + 双方装备装配（PVP 双方都是真人 actor，武器/词条一视同仁）
    _my_actor = _BR.player_to_actor(player)
    _opp_actor = _BR.player_to_actor(_def_p)
    _opp_actor["side"] = "enemy"  # 防守方入敌侧（human_controlled=True 保持 → 不自动）
    # 双方装备装配（PVP 双方都是真人 actor，武器/词条一视同仁）+ 各自外部增幅容器
    #（v181.M-bonus 统一数值容器；序列收敛于 BR.apply_battle_loadout，随 actor 落盘/恢复）
    _BR.apply_battle_loadout(_my_actor, _tb_me)
    _BR.apply_battle_loadout(_opp_actor, _tb_opp)
    _b2 = B2("pvp", sides={"player": [_my_actor], "enemy": [_opp_actor]},
             title_bonus={}, pet=db.pet_get(qq_id))
    state = _b2.to_state()
    # meta 外壳（saintess_engine from_state 忽略未知键 → 只给命令层读）
    state["meta"] = {"pvp": True, "attacker_qq": str(qq_id), "actor": "attacker"}
    db.save_battle(group_id, qq_id, state)
    db.save_battle(group_id, target_qq, state)
    self._lock_battle(group_id, qq_id)
    self._lock_battle(group_id, target_qq)
    # 主动攻击 → 灰名 10 分钟
    db.set_event_state(f"grey_{qq_id}", str(int(time.time()) + 600))
    a, d = _my_actor, _opp_actor
    yield event.plain_result(
        _T.text("pv.engage", name=target_player['name'], hp=a['hp'], hpmax=a['max_hp'], mp=a['mp'],
            mpmax=a['max_mp'], lv=a['level'], ohp=d['hp'], ohpmax=d['max_hp'], omp=d['mp'],
            ompmax=d['max_mp'], olv=d['level'])
    )

async def _pvp_act(self, event, group_id, qq_id, player, state, action, skill_name=None):
    """PVP 行动：轮流操作，胜者结算（N5b4-4 saintess_engine 版）。

    state = saintess_engine to_state + meta{attacker_qq, actor}；sides.player = 攻击者(发起方)、
    sides.enemy = 防守方，双方 human_controlled。轮流制由命令层 meta.actor 驱动：
    当前行动者可能是 player side（攻击者）或 enemy side（防守方）——按 side 显式定位
    actor（saintess_engine focus() 只认 sides.player 首个 human_controlled，PVP 不依赖）。
    胜负判定 = 自己 actor 是否存活（saintess_engine result 视角固定 player side，防守方视角
    要翻转——不直接用 result 判自己输赢）。
    """
    # 旧格式（无 sides/meta）→ 作废清档重开（N5b 约定不迁移）
    meta = state.get("meta") or {}
    if not isinstance(state.get("sides"), dict) or not state["sides"] or not meta.get("attacker_qq"):
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        yield event.plain_result(_T.static("pv.stale1"))
        return
    from saintess_engine import Battle as B2
    b = B2.from_state(state)
    if b is None:
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        yield event.plain_result(_T.static("pv.stale2"))
        return
    attacker_qq = str(meta.get("attacker_qq", ""))
    my_key = "attacker" if str(qq_id) == attacker_qq else "defender"
    if meta.get("actor") != my_key:
        yield event.plain_result(_T.static("pv.wait"))
        return
    opp_key = "defender" if my_key == "attacker" else "attacker"
    # 我的 actor 在 my_side（攻击者=player 侧/防守者=enemy 侧），对方在 opp_side
    my_side = "player" if my_key == "attacker" else "enemy"
    opp_side = "enemy" if my_key == "attacker" else "player"
    my_actor = next((_a for _a in b.sides_of(my_side) if _a.get("human_controlled")), None)
    opp_actor = next((_a for _a in b.sides_of(opp_side) if _a.get("human_controlled")), None)
    if my_actor is None:
        yield event.plain_result(_T.static("pv.gone_self"))
        return
    if opp_actor is None:
        # 对方记录异常（正常该在）→ 保险清场
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        yield event.plain_result(_T.static("pv.gone_other"))
        return
    opp_qq = str(opp_actor.get("qq_id", "") or "")
    # PVP 战斗中血量/蓝量以战斗 state 为准（actor 副本；不写回 db，避免被重置）
    _BR.sync_player_from_actor(player, my_actor)
    if action == "skill":
        info = skill_info(player["class_name"], skill_name)
        if not info:
            yield event.plain_result(_T.text("pv.no_skill", name=skill_name))
            return
        if not is_skill_learned(player["class_name"], player["level"], skill_name, player.get("learned_skills", [])):
            yield event.plain_result(_T.text("pv.lv_short", need=info['lv'], have=player['level']))
            return
        # v181.M-smallfix：PVP mp 预检与引擎 actions._skill_pay_of 同源折算——my_actor
        # 为 restore 后战斗 actor（bonus.cost 词条装配随档在），pay = 引擎实际扣费值
        # （floor+保底 1）→ 折扣词条下 mp ∈ [pay, 声明费) 边界放行（不再被声明费先拦）。
        if info.get("mp", 0) or 0:
            _pvp_mp_need = skill_mp_pay_of(my_actor or player, info)
            if _pvp_mp_need > 0 and int(my_actor.get("mp") or 0) < _pvp_mp_need:
                yield event.plain_result(_T.static("pv.no_mp"))
                return
    # PVP『防御』（saintess_engine：目标 actor defending=True → landing deal_damage 减半统一消费）。
    # 防御姿态随 actor dict 持久化（to_state 带 defending）——上一击 defend 的人恢复后
    # 自动在 defending 状态，无需命令层再搬运。这里只做"覆盖/消耗"语义：
    # - defend 行动：己方由引擎 _do_defend 置 True；对方旧防御被覆盖清掉
    # - 攻击/技能行动：对方防御在本次伤害结算中生效（引擎）→ 行动后双方防御都被消耗
    if action == "defend":
        opp_actor["defending"] = False
    # 目标：攻击类技能打对方；治疗/增益类作用自己（PVP 无友方——传敌方 actor
    # 会让 heal 奶对手 / buff 挂敌人）
    _tgt = opp_actor if (opp_actor.get("hp") or 0) > 0 else None
    if action == "skill":
        _info = skill_info(player["class_name"], skill_name) or {}
        if _info.get("kind") in (K_HEAL, K_BUFF):
            _tgt = None
    logs, ended, _who = b.human_act(action, skill_name, actor=my_actor, target=_tgt)
    if action != "defend":
        my_actor["defending"] = False
        opp_actor["defending"] = False
    # 回写 player dict（展示/后续结算读 player 时拿到最新值；db 不写——PVP 快照制）
    _BR.sync_player_from_actor(player, my_actor)
    my_alive = (my_actor.get("hp") or 0) > 0
    opp_alive = (opp_actor.get("hp") or 0) > 0
    # 结果展示体（双方面板）
    _opp_hp = max(0, int(opp_actor.get("hp", 0) or 0))
    _my_hp = max(0, int(my_actor.get("hp", 0) or 0))
    _opp_mp = max(0, int(opp_actor.get("mp", 0) or 0))
    _my_mp = max(0, int(my_actor.get("mp", 0) or 0))
    if not my_alive:
        # 行动者败（反伤/荆棘/毒跳类）→ 双方解除（对齐旧 defeat 保险分支，不做掉落惩罚）
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        if opp_qq:
            self._unlock_battle(group_id, opp_qq)
            db.clear_battle(group_id, opp_qq)
        yield event.plain_result("\n".join(logs))
        return
    if not opp_alive:
        # 行动者胜：受伤状态写回 db → 结算（掉金/荣誉/回城）
        db.update_player(group_id, qq_id, hp=_my_hp, mp=_my_mp,
                         max_hp=my_actor.get("max_hp"), max_mp=my_actor.get("max_mp"))
        self._unlock_battle(group_id, qq_id)
        db.clear_battle(group_id, qq_id)
        if opp_qq:
            self._unlock_battle(group_id, opp_qq)
            db.clear_battle(group_id, opp_qq)
        async for _r in self._pvp_finish(event, group_id, qq_id, opp_qq,
                                         attacker_qq or str(qq_id), "\n".join(logs)):
            yield _r
        return
    # 未分胜负：meta.actor 翻给对手，存双方（同一 st）
    meta["actor"] = opp_key
    st = b.to_state()
    st["meta"] = meta
    db.save_battle(group_id, qq_id, st)
    if opp_qq:
        db.save_battle(group_id, opp_qq, st)
    body = "\n".join(logs)
    yield event.plain_result(
        _T.text("pv.turn", name=body, hp=opp_actor.get('name', '对方'), hpmax=_opp_hp,
            mp=max(0, int(opp_actor.get('max_hp', 1) or 1)), mpmax=_opp_mp,
            hp2=max(0, int(opp_actor.get('max_mp', 1) or 1)), hpmax2=_my_hp,
            mp2=max(0, int(my_actor.get('max_hp', 1) or 1)), mpmax2=_my_mp,
            tail=max(0, int(my_actor.get('max_mp', 1) or 1)))
    )

async def _pvp_finish(self, event, group_id, winner_qq, loser_qq, attacker_qq, log_body):
    """PVP 结算：败者掉 10% 金币给胜者 + 回城 HP=1；红名/荣誉"""
    loser = db.get_player(group_id, loser_qq)
    winner = db.get_player(group_id, winner_qq)
    # v110 审计修复：战败掉金对齐 26 章 §3.2 第二档——10% 上限 2000；
    # 红名者战败额外再掉 10%（上限 2000，惩罚消失不入胜者）
    lost = min(int(loser["gold"] * 0.1), 2000)
    extra = 0
    if self._is_redname(loser_qq):
        extra = min(int(loser["gold"] * 0.1), 2000)
    db.update_player(group_id, winner_qq, gold=winner["gold"] + lost)
    # v104 P2(M22)：PVP 战败与打怪战败(_handle_defeat)一致——回最近城镇（原固定回橡木镇
    # START_MAP，Lv.60+ 败者也回 Lv.1 新手图），落该城中心广场 subareas[0]；HP=1 惩罚保留
    _town_id = self._nearest_town(loser.get("cur_map", ""))
    _town_sas = _cs.MAP_BY_ID.get(_town_id, {}).get("subareas") or []
    _town_sa = _town_sas[0]["id"] if _town_sas else ""
    db.update_player(group_id, loser_qq, gold=max(0, loser["gold"] - lost - extra), hp=1,
                     cur_map=_town_id, cur_subarea=_town_sa)
    db.init_stats(group_id, loser_qq)
    db.bump_stats(group_id, loser_qq, deaths=1)
    # 攻击方袭击 CD（防击杀后立刻蹲尸再打）
    self._set_pvp_cd(str(attacker_qq))
    # F1 审计修复（H0-S1）：败方也进入 PVP 袭击 CD（同机制同时长）——否则两账号可交替
    # 互杀无限对刷荣誉（胜者 +50）；现在胜负双方 2 分钟内都无法立即再次袭击，阻断荣誉对刷。
    self._set_pvp_cd(str(loser_qq))
    now = int(time.time())
    # F1 P1-5（report_09）：灰名只写不读修复——结算处消费灰名标记。
    # 查证：26 章策划案(design/new_world/26_PVP与红名系统.md)无灰名设计、v110.14 提交说明
    # 无灰名惩罚 → 惩罚数值不明确，按 FIX-F1 ⚠️ 保守默认：灰名期间主动袭击者被反杀
    # 不掉额外惩罚（与普通战败同规则 10% 上限 2000），仅提示灰名状态；
    # 掉金翻倍/荣誉惩罚候选方案待鱼鱼拍板。
    _grey_st = db.get_event_state(f"grey_{loser_qq}")
    try:
        grey_active = bool(_grey_st) and int(_grey_st) > now
    except Exception:
        grey_active = False
    lines = [log_body, "", _T.text("pv.dead", name=loser['name'])]
    if lost > 0:
        lines.append(_T.text("pv.loot", gold=lost))
    if extra > 0:
        lines.append(_T.text("pv.red_lose", gold=extra))
    if grey_active:
        lines.append(_T.text("pv.gray", name=loser['name']))
    _town_name = _cs.MAP_BY_ID.get(_town_id, {}).get("name", "城镇")
    lines.append(_T.text("pv.hospital", where=_town_name))
    if self._is_redname(loser_qq):
        honor = self._get_honor(winner_qq) + 50
        db.set_event_state(f"honor_{winner_qq}", str(honor))
        lines.append(_T.text("pv.honor_red", honor=honor))
    else:
        # v110 审计修复：26 章 §3.3「PVP 胜利 +10」补全（原仅击杀红名 +50）
        honor = self._get_honor(winner_qq) + 10
        db.set_event_state(f"honor_{winner_qq}", str(honor))
        lines.append(_T.text("pv.honor_win", honor=honor))
        if str(winner_qq) == str(attacker_qq):
            red_until = self._red_until(winner_qq)
            # v110 审计修复：26 章 §3.1——击杀红名 30 分钟基础，红名期间每多击杀
            # 叠加 10 分钟，上限 120 分钟（原固定 +30 分钟无叠加无上限）
            if red_until > now:
                new_red = min(red_until + 600, now + 7200)
                lines.append(_T.static("pv.red_stack"))
            else:
                new_red = now + 1800
                lines.append(_T.static("pv.red_new"))
            db.set_event_state(f"red_{winner_qq}", str(new_red))
    yield event.plain_result("\n".join(lines))

async def battle_prefs_form(self, event: AstrMessageEvent, group_id, qq_id, player, arg):
    lines = []
    cls_id = _resolve("classes", player.get("class_name", ""))
    forms = _DF139_CLASS_FORMS.get(cls_id)
    if not forms:
        lines.append(_T.static("bp.form_na"))
        yield event.plain_result("\n".join(lines))
        return
    fname, fkey = forms
    if not arg:
        cur = (player.get("battle_prefs") or {}).get("dual_form", "")
        lines.append(_T.text("bp.form_cur", v='【' + cur + '】' if cur else '未设置（默认按资源自动入形态）'))
        lines.append(f"可用：{fname}（当前职业仅此一种双形态）")
        yield event.plain_result("\n".join(lines))
        return
    if arg not in (fname, fkey):
        lines.append(_T.text("bp.form_unknown", arg=arg, name=fname))
        yield event.plain_result("\n".join(lines))
        return
    prefs = dict(player.get("battle_prefs") or {})
    prefs["dual_form"] = fname
    db.update_player(group_id, qq_id, battle_prefs=prefs)
    lines.append(_T.text("bp.form_ok", name=fname))
    lines.append(_T.static("bp.form_tip"))
    yield event.plain_result("\n".join(lines))

async def battle_prefs_finisher(self, event: AstrMessageEvent, group_id, qq_id, player, arg):
    lines = []
    if _resolve("classes", player.get("class_name", "")) != "cls_ci_ke":
        lines.append(_T.static("bp.fin_na"))
        yield event.plain_result("\n".join(lines))
        return
    if not arg:
        cur = (player.get("battle_prefs") or {}).get("finisher", "满刃")
        lines.append(_T.text("bp.fin_cur", v='【' + cur + '】'))
        lines.append(_T.static("bp.fin_usage"))
        yield event.plain_result("\n".join(lines))
        return
    if arg not in _FINISHER139_OPTIONS:
        lines.append(_T.text("bp.fin_unknown", arg=arg, avail='/'.join(_FINISHER139_OPTIONS)))
        yield event.plain_result("\n".join(lines))
        return
    prefs = dict(player.get("battle_prefs") or {})
    prefs["finisher"] = arg
    db.update_player(group_id, qq_id, battle_prefs=prefs)
    lines.append(_T.text("bp.fin_ok", name=arg))
    lines.append(_T.static("bp.fin_tip"))
    yield event.plain_result("\n".join(lines))

async def battle_prefs_arcane_field(self, event: AstrMessageEvent, group_id, qq_id, player, arg):
    lines = []
    if _resolve("classes", player.get("class_name", "")) != "cls_fa_shi":
        lines.append(_T.static("bp.af_na"))
        yield event.plain_result("\n".join(lines))
        return
    if not arg:
        cur = (player.get("battle_prefs") or {}).get("arcane_field", "盾")
        lines.append(_T.text("bp.af_cur", v='【' + cur + '】'))
        lines.append(_T.static("bp.af_usage"))
        yield event.plain_result("\n".join(lines))
        return
    if arg not in _ARCANE_FIELD_OPTIONS:
        lines.append(_T.text("bp.af_unknown", arg=arg, avail='/'.join(_ARCANE_FIELD_OPTIONS)))
        yield event.plain_result("\n".join(lines))
        return
    prefs = dict(player.get("battle_prefs") or {})
    prefs["arcane_field"] = arg
    db.update_player(group_id, qq_id, battle_prefs=prefs)
    lines.append(_T.text("bp.af_ok", name=arg))
    lines.append(_T.static("bp.af_tip"))
    yield event.plain_result("\n".join(lines))

async def battle_prefs_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    prefs = player.get("battle_prefs") or {}
    lines = [_T.static("bp.view_title")]
    if not prefs:
        lines.append(_T.static("bp.view_empty"))
    else:
        if prefs.get("dual_form"):
            lines.append(_T.text("bp.view_form", v=prefs['dual_form']))
        if prefs.get("finisher"):
            lines.append(_T.text("bp.view_fin", v=prefs['finisher']))
    lines.append(_T.static("bp.view_usage"))
    yield event.plain_result("\n".join(lines))


__all__ = ["_battle_locks", "WORLD_BOSS_DOT_INTERVAL", "_curve_vals", "_fmt_mult", "pet_battle_status_note", "WORLD_BOSS_DROPS", "RESOURCE_STACK_CN", "resource_stack_text", "_res_display_name", "_b_enemy", "explore", "wild_king_chest", "_main_kill_target_on_map", "_in_battle", "_lock_battle", "_unlock_battle", "_open_battle", "_restore_battle", "_sync_battle_player", "_mount_explore_bonus", "_roll_hidden_monster", "wish", "trader_confirm", "revive_confirm", "_roll_find_quest_events", "_rain_boost", "_handle_explore_event", "_recent_explore_events", "_remember_explore_event", "_poi_daily_used", "_handle_poi", "attack", "skill", "_skill_panel", "_branch_skills_for", "_player_skill_table", "_skill_tag", "_skill_range_label", "_skill_list_gains", "_skill_gains_curve", "_skill_list_page", "defend", "flee", "_buff_left_ticks", "_status_line", "_resource_line", "_player_unit_for_formation", "_battle_formation_panel", "_battle_footer", "_handle_victory", "_next_step_hint", "_nearest_town", "_handle_defeat", "hunt_boss", "_grant_worldboss_drop", "_worldboss_act", "_parse_target_qq", "_red_until", "_is_redname", "_get_honor", "_pvp_meta_qqs", "_pvp_snapshot", "_pvp_handle_timeout", "_set_pvp_cd", "_pvp_cd_left", "honor_shop", "_honor_buy", "_pvp_start", "_pvp_act", "_pvp_finish", "battle_prefs_form", "battle_prefs_finisher", "battle_prefs_arcane_field", "battle_prefs_view"]
