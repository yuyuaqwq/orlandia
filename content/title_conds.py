# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— 称号获得条件注册表（B13-L4，2026-09-14）。

真源：游戏仓 `game/core/title_conds.py`（350 行 / v98.3 起）。本模块 = 那份文件的
**实现本体**（逐字搬：50 个称号条件注册 + `TitleCtx` + `check_pro_title` + 两个辅助
`_side_done` / `_has_flag`）。宿主 `game/core/title_conds.py` 现在只剩「加载包 + 同名单
re-export」（`CONDITIONS` / `register` / `TitleCtx` / `check_pro_title` / 各 `_t_*`），
消费者 `game/commands/economy.py:26` 与 `game/core/stat_bonus.py:87` 的 import 点零改动。

正文改动面（只有两类，替换表见 `overnight/w1213_b13l4_port.py`，每条断言出现次数）
--------------------------------------------------------------------------------------
1. 宿主取件 → 惰性替身：`TitleCtx._db()` 里函数内 `from .. import db` → 模块级
   `db = _HostMod("db")`（`_db()` 仍返回该句柄，调用点 `ctx._db().xxx()` 一行未改）；
   函数内 `from .. import content as C`（rep_honor / rep_legend / hidden 三处）删除；
   `_has_flag` 的 `from .. import content as _C` → ★ W4 切包内读口 `content/wild.py`（原 `_C = C`）。
2. 读点（B14-2，L7 线已切三名包内门面）：`C.MAPS` → `content/catalog_space.py:MAPS` ·
   `C.NPCS` / `C.HIDDEN_NPCS` → `content/catalog_quests.py`（门禁逐名 OK · 不等 0，含键序；
   MAPS 实测保留 `hidden`/`type`，NPCS=362 / HIDDEN_NPCS=22 与宿主同值同序 —— B13-L4 时期
   「maps 域是投影 / npcs 域是超集」的判断已随 B14-A/C 重造失效）。
   ★ W4（2026-09-14）：原「仍走宿主句柄」的两名已切门面 —— `C.HIDDEN_MAP_UNLOCK` →
   `content/catalog_b143.py`（B14-3 建 `game_config.maps` 组，门禁含键序不等 0）；
   `C.ALL_WILD` → 包内读口 `content/wild.py`（B13-L2 已落地；派生口径与宿主 `C.ALL_WILD`
   一致）。仍走宿主句柄的只剩**函数**：`C.faction_reputation_tier`（`core/factions.py`）。

真源原文头注（逐字保留）
------------------------
    奥兰迪亚·余烬纪年核心层 - title_conds.py（v98.3：称号获得条件注册表）
    
    消灭 commands/economy.py _earned_titles() 里的 if-elif 硬编码：
    称号数据只声明 id，判定统一走本模块注册表。
    
    扩展方式：
    - 加称号：data/titles.py 加一条 dict（id 唯一）+ 本文件 register 一个条件函数
    - 函数签名：fn(ctx) -> bool
    - ctx 为 TitleCtx（group_id/qq_id/player/stats/rep/quests/hooks）"""

from __future__ import annotations

import importlib
import sys


# ============================================================
# 宿主替身口（**惰性**：属性访问时才解析宿主模块；绝不 import 宿主模块树、绝不静默空跑）
# 真源写法 → 包内替身：`from .. import content as C` → `C = _HostMod("content")`；
# `from .. import db` → `db = _HostMod("db")`。函数内那几行 import 已按原位置删除，
# 所有调用点 `C.xxx` / `db.xxx` **一行未改**（与 `content/world_cmds.py` / `talk_actions.py` 同款）。
# ============================================================
_HOST_PKG = "data.plugins.dragonfall.game"      # 运行时（main.py 的模块路径）
_HOST_PKG_FALLBACK = "game"                     # 测试/工具按 `game.xxx` 直接 import 时
_INJECTED = {}


def bind_host(**objs):
    """宿主薄壳 import 期注入（幂等）——键 = `_HostMod` 的模块名（`content` / `db`）。"""
    for k, v in (objs or {}).items():
        if v is not None:
            _INJECTED[k] = v


def _host_module(name: str):
    """取宿主子模块（`name` 为空 = 宿主 `game` 包本身，真源 `from .. import X` 那一类）。"""
    if name in _INJECTED:
        return _INJECTED[name]
    for prefix in (_HOST_PKG, _HOST_PKG_FALLBACK):
        full = prefix if not name else "%s.%s" % (prefix, name)
        m = sys.modules.get(full)
        if m is not None:
            return m
    last = None
    for prefix in (_HOST_PKG, _HOST_PKG_FALLBACK):
        try:
            return importlib.import_module(prefix if not name else "%s.%s" % (prefix, name))
        except Exception as exc:                # noqa: BLE001
            last = exc
    raise RuntimeError("%s：宿主模块 %s 取不到（%s）——拒绝静默空跑" % (__name__, name, last))


def _host_attr(mod: str, attr: str):
    """宿主模块属性 —— 真源「函数内 `from ..<mod> import <attr>`」的同义替身（调用时解析）。"""
    m = _host_module(mod)
    try:
        return getattr(m, attr)
    except AttributeError:
        for prefix in (_HOST_PKG, _HOST_PKG_FALLBACK):
            try:
                return importlib.import_module("%s.%s" % (
                    prefix if not mod else "%s.%s" % (prefix, mod), attr))
            except Exception:                   # noqa: BLE001
                continue
        raise


class _HostMod:
    """宿主模块替身（`C` / `db`）——`C.xxx` / `db.xxx` 正文一字未改，属性访问时解析。"""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        return getattr(_host_module(self._name), attr)


from ._pkgref import DB as db, PkgModule
# ★ P4′-W1 A 组：`C.faction_reputation_tier` 实测 `__module__ == "content.factions"`
C = PkgModule("content.factions")

# B14-2（L7 线）：数据名读点切包内门面 —— 原 `C.<名>` / `_C.<名>` 直取换成门面同名绑定
from .catalog_quests import HIDDEN_NPCS, NPCS   # 真源 `C.HIDDEN_NPCS` / `C.NPCS`
from .catalog_space import MAPS                 # 真源 `C.MAPS`
# ★ W4（2026-09-14）：缺口两名切包内 —— `HIDDEN_MAP_UNLOCK` → `catalog_b143`；`ALL_WILD` → `wild`
from . import catalog_b143 as _cb143            # 真源 `C.HIDDEN_MAP_UNLOCK`（`game/data/maps.py:4343`）
from . import wild as _wild                     # 真源 `C.ALL_WILD`（`core/wild.py:26` 派生式）

import re

from saintess_engine.conditions import Conditions
from saintess_engine.conditions.declarative import register_specs
from .cond_specs import load as _load_specs

CONDITIONS = Conditions()

# 条件注册装饰器（引擎同名方法；判定函数签名 fn(ctx) 与引擎调用约定一致）
register = CONDITIONS.register

# ★ S4 数据化：下面这些条目的判定形状固定（常量比较 / 步链取值 / 布尔组合 /
#   计数阈值），正文已搬进 `content/data/cond_specs.json`（引擎侧只用
#   `saintess_engine.conditions.declarative` 的通用算子装配）。
#   保留在下方代码里的条目都带真逻辑（跨域联查 / 运行期取数 / 引擎没有的算子）。
register_specs(CONDITIONS.register, _load_specs("title"))


class TitleCtx:
    """称号条件判定上下文。hooks 注入命令层专属能力（has_enhanced/visited_maps）。"""

    def __init__(self, group_id, qq_id, player, stats, rep, quests, hooks=None):
        self.group_id = group_id
        self.qq_id = qq_id
        self._focus = player or {}
        self.stats = stats or {}
        self.rep = rep or {}
        self.quests = quests or {}
        self.hooks = hooks or {}

    def _db(self):
        # B13-L4：真源「函数内 from .. import db」→ 宿主 db 模块本体
        # （`_host_module("db")` 返回的**就是宿主 db 模块对象**：类型/身份与真源一致；
        #   调用点 `ctx._db().xxx()` 一字未改）
        return db    # B1：包内直取（`content.persistence`；原 `_host_module("db")`）

    def hook(self, name, *args, **kwargs):
        fn = self.hooks.get(name)
        if fn:
            return fn(*args, **kwargs)
        return None


# ================= 条件实现 =================

@register("novice")
def _t_novice(ctx):
    return True


@register("rep_honor")
def _t_rep_honor(ctx):
    return any(C.faction_reputation_tier(v) in ("崇敬", "崇拜") for v in ctx.rep.values())


@register("rep_legend")
def _t_rep_legend(ctx):
    return any(C.faction_reputation_tier(v) == "崇拜" for v in ctx.rep.values())


@register("explorer")
def _t_explorer(ctx):
    return ctx._db().get_visited_count(ctx.group_id, ctx.qq_id) >= 10


@register("fish10")
def _t_fish10(ctx):
    return ctx._db().get_fishing_total(ctx.group_id, ctx.qq_id) >= 10


@register("enhance5")
def _t_enhance5(ctx):
    return bool(ctx.hook("has_enhanced", ctx.group_id, ctx.qq_id, 5))


@register("enhance9")
def _t_enhance9(ctx):
    return bool(ctx.hook("has_enhanced", ctx.group_id, ctx.qq_id, 9))


@register("hidden")
def _t_hidden(ctx):
    # v124 修复：mithril_hall 已删除（v104 P2 清理死条目）→ 改判真实隐藏区域，
    # 与成就 ach_mythril（hidden_area≥1，achievement_conds.py 已修复）同语义：
    # 到访任一隐藏区域即达成（lost_library / ember_corridor，或 hidden=True 地图）
    visited = ctx.hook("visited_maps", ctx.group_id, ctx.qq_id) or []
    hidden = set(_cb143.HIDDEN_MAP_UNLOCK or {})
    for m in (MAPS or []):
        if m.get("hidden") or m.get("type") == "隐藏区域":
            hidden.add(m["id"])
    if not hidden:
        return False
    return any(v in hidden for v in visited)


@register("fish_king")
def _t_fish_king(ctx):
    return ctx._db().get_fish_king(ctx.group_id, ctx.qq_id) >= 1


@register("pvp_hero")
def _t_pvp_hero(ctx):
    # 数据源：荣誉商店兑换勋章（26 章 3.3，combat.py _honor_buy 写
    # event_state key = f"honor_{reward['title_id']}_{qq}"，honor_shop.py
    # 第 1 件商品 title_id="medal" → 键 honor_medal_{qq}，与本行读取键一致）
    return int(ctx._db().get_event_state(f"honor_medal_{ctx.qq_id}") or 0) >= 1


# ================= v124 剧情线称号（side 完成判定）=================
def _side_done(ctx, sid):
    """支线完成 = quests.side[sid].status == done"""
    return (ctx.quests.get("side") or {}).get(sid, {}).get("status") == "done"


def _has_flag(ctx, flag):
    """任意 NPC flag 桶含指定 flag（扫描全桶，同 wild.py unlock_met flag: 先例）"""
    _AW = _wild.ALL_WILD                # 真源 `from .. import content as _C` 的 `_C.ALL_WILD`（★ W4 切包内读口）
    db = ctx._db()
    for nid in list(NPCS.keys()) + list(_AW.keys()) + list(HIDDEN_NPCS.keys()):
        if flag in db.get_talk_flags(ctx.group_id, ctx.qq_id, nid):
            return True
    return False


@register("north_benefactor")
def _t_north_benefactor(ctx):
    return _side_done(ctx, "s18") and _has_flag(ctx, "s18_branch_light")


@register("nightwalker")
def _t_nightwalker(ctx):
    return _side_done(ctx, "s18") and _has_flag(ctx, "s18_branch_dark")


@register("just_enforcer")
def _t_just_enforcer(ctx):
    return _side_done(ctx, "s78") and _has_flag(ctx, "s78_branch_justice")


@register("shadow_friend")
def _t_shadow_friend(ctx):
    return _side_done(ctx, "s78") and _has_flag(ctx, "s78_branch_mercy")


def check_pro_title(tid: str, ctx) -> bool:
    """副业称号：pro_<prof><lv>（如 pro_gather3）→ 副业等级达标。"""
    m = re.match(r"^pro_([a-z]+)(\d+)$", tid)
    if not m:
        return False
    prof_key, need_lv = m.group(1), int(m.group(2))
    if prof_key in ("gather", "mining", "fishing", "alchemy", "craft", "cooking"):
        return ctx._db().get_prof_level(ctx.group_id, ctx.qq_id, prof_key) >= need_lv
    return False


# ================= v140 波3.6：资源向称号条件（方案 3.9，6 个） =================
# 条件口径与 achievements.py prof_count 一致（stats 计数），效果消费点见 titles.py effect 字段

