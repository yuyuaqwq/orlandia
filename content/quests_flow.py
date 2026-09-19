# -*- coding: utf-8 -*-
"""包内任务流域（`content/quests_flow.py`）—— 真源 `game/services/quests_flow.py`（831 行）**逐字端口**。

★ B9 L5（2026-09-13）：宿主 `game/services/quests_flow.py` 薄壳化 = **只留「加载包 + 注入宿主替身 +
同名 re-export」**，命令/战斗/经济三层的调用点与调用签名**一字不变**（`world.py:1935/2289/2295/2301/
2681/2733/3379/3452/3458/3758/3764/3770/3776/3889/3895`、`combat.py`、`economy.py`、
`services/player_event_subscribers.py:25`、`tests/test_commands_world.py:16`、`tests/test_v104_quests.py:21`）。

只改两类东西（与 `content/flow/weekly_progress.py` / `content/talk_actions.py` 同款）
------------------------------------------------------------------------------------------
| 真源写法 | 包内写法 | 说明 |
|---|---|---|
| 函数体内 `from .. import db` + `db.xxx(...)` | 模块级 `db` = **惰性宿主代理** `_HostDB` | 正文里 `db.xxx(...)` **一行未改**；宿主由 `bind_host(db)` 注入，或按 `sys.modules` 找**已加载**的宿主模块（绝不 import，防在包侧另起一份宿主模块树） |
| 函数体内 `from .. import content as C` + `C.<名>` | 模块级 `C = _Dom()`（W6 后**只剩函数名句柄 `resolve`**：`ALL_WILD` → 包内派生式读口 `content/wild.py`；`FACTIONS` / `AREA_FACTION` → 门面 `catalog_b143.py`；其余数据名走 `catalog_*.py`） | 逐符号归属见下表 |
| 函数体内 `from ..content_rules.gameplay import check_player_level_up` | 模块级同名包装 `check_player_level_up(...)` → ★ REPOINT-PKG 起兜底**包内直取** `content/gameplay_rules.py` | 宿主薄壳 `game/content_rules/gameplay.py` 是同名单再导出（同一函数对象）；正文调用点不动 |
| 函数体内 `from ..core.stat_bonus import stat_bonus` | 模块级同名包装 `stat_bonus(...)` → ★ REPOINT-PKG 起兜底**包内直取** `content/stat_bonus.py` | 宿主薄壳 `game/core/stat_bonus.py` 是同名单再导出（同一函数对象）；正文调用点不动 |
| 函数体内 `from ..reward import grant_reward` | 模块级同名包装 `grant_reward(*a, **k)` | 发放实现 = 宿主 `game/reward.py` |
| 函数体内 `from .quests import bump_daily_progress as _bump_daily_progress` | 模块级同名包装 `_bump_daily_progress(...)` | 每日委托计数 = 宿主 `game/services/quests.py`（**同级服务，本批未搬**） |
| 函数体内 `from ..services.quests import DAILY_META_KEYS, settle_daily_quest` | `DAILY_META_KEYS` = `_HostAttr("services.quests", …)`（支持 `in`）；`settle_daily_quest` = 同名包装 | 同上；`DAILY_META_KEYS` 只被 `if dkey in DAILY_META_KEYS` 用 ⇒ 用带 `__contains__` 的惰性对象，正文那一行不动 |

★ 逐符号归属（B14-2：数据名已切到**包内门面**；残余 = 缺口名，逐条见 `overnight/W-B14-2-L4.md` §缺口）
----------------------------------------------------------------------------------
| 符号 | 取值来源（B14-2 切门面后） | 实测口径 |
|---|---|---|
| `_cq.MAIN_QUESTS`（70） | 门面 `content/catalog_quests.py`（`quests` 域 `source=="main"`） | 与宿主聚合层同名表 **深比较相等**（含键序，`overnight/b14_catalog_gate.py`）；**消费端全是按 id 取**（`next(... id == X)`）⇒ 无顺序语义 |
| `_cq.SIDE_QUESTS`（144，**有序**） | 门面 `catalog_quests`（+ 门面 `_ORDER_*` 序表还原**源列表插入序**） | 同上门禁逐条相等；`available_quest_list` / `side_available_list` / `offer_side_quests` 的输出行序 = 遍历序 ⇒ 序不能丢（见下） |
| `_cq.NPCS`（362） | 门面 `catalog_quests`（域 `source=="town"`，去注入 `source`） | 门禁逐条相等；本模块只读 `name` / `map` |
| `ALL_WILD`（63） | 包内**派生式读口** `content/wild.py`（PEP 562 `__getattr__("ALL_WILD")` = `{**WILD_NPCS, **HIDDEN_NPCS[无 inst_stage]}`，首次取值后缓存） | W6 实测与宿主 `C.ALL_WILD` **键集/键序/逐条值深等**（63 条，`overnight/w6_allwild_check.py`）；本模块只 `.get(id)` 后读 `name` / `map` ⇒ 顺序无消费语义（该读口内部两张表仍走宿主句柄，那边已登记缺口：npcs 域待补真源顺序字段） |
| `_cq.DIALOGUES`（39） | 门面 `catalog_quests`（`dialogues` 域全量） | 门禁逐键逐值相等 |
| `_cc.RACES`（6） | 门面 `content/catalog_core.py`（`races.json`） | 门禁逐条相等 |
| `_cc.CLASSES`（8） | 门面 `catalog_core`（`classes.json`） | 门禁相等；**只用到 `name` / `tier_levels` 两个字段** |
| `_cs.MAP_BY_ID`（121） | 门面 `content/catalog_space.py`（`worlds` 域） | 门禁相等；**只用到 `.get(...).get("name")` / `.get("area")` / `.get("type")`**（`obj_text` / `quest_reputation` / `_rule_fire` 的 `cur_map` 参数位） |
| `_cq.TITLES`（68） | 门面 `catalog_quests`（`titles` 域全量） | B14-2 前走宿主 `game/data/titles.py`；门禁实测门面 == 宿主（含键序），消费是「按 id / name 扫表」⇒ 顺序无语义 |
| `FACTIONS` / `AREA_FACTION` | 门面 `content/catalog_b143.py`（B14-3 新建域 `factions`；外层键序由 `key_order` 域的 `factions` / `area_faction` 还原） | 门禁逐条相等（含键序）：`b14_catalog_gate.py --names FACTIONS,AREA_FACTION` → 不等 0 |
| `C.resolve("materials", …)` | **函数名句柄**（宿主 `game/core/index.py:47`，W6 后 `C` 上只剩这一项） | 材料名→id 的**权威索引在宿主**（`materials`(598) ⊊ `items`(900)，且 `build_index` 是装配期产物）——包内 `content/tables.py:resolve` 对 `materials` 是**原样返回**，直接改用它会静默错（`db.count_item` 拿到中文名）⇒ 必须走宿主 |

★ 顺序声明 `SIDE_QUEST_ORDER` —— 为什么必须有
--------------------------------------------
域文件外层键是**字典序**（导出契约 `sort_table`：幂等优先），而真源 `SIDE_QUESTS` 是有序 list：
`available_quest_list`（『接取』无参列表）/ `side_available_list`（对话菜单序号）/ `offer_side_quests`
（逐条接取/拒绝提示）**都按遍历序产出玩家可见行**。少一份顺序声明 → 行序变（逐字节不等）。
B14-2：序表**单点移入门面** `content/catalog_quests.py`（那里带集合守卫：域多/少一条即 `raise`）。
本模块的 `SIDE_QUEST_ORDER` 因此改为由门面 `SIDE_QUESTS` 派生的**只读视图**——宿主薄壳
`game/services/quests_flow.py:66` 仍在 re-export 这个名字，故名字必须保留；**别再往这里加 id**。

用法::

    from content import quests_flow as QF
    QF.bind_host(db, c)                     # 宿主薄壳注入（游戏仓 game/services/quests_flow.py）
    lines = QF.take_main_quest(group_id, qq_id, npc_id, npc)
"""
from __future__ import annotations

from collections.abc import Mapping

# ★ B14-2（2026-09-14）：数据名改从**包内门面**直取 —— 宿主 `game/data` 删掉后本模块仍能活；
#   门面同包、只读包内域、不 import 宿主（`game.*`）。
# ★ W6（2026-09-14）：残余数据读点再切门面 —— `ALL_WILD` → 包内派生式读口 `content/wild.py`
#   （实测与宿主 `C.ALL_WILD` 63 条**键集/键序/逐条值深等**）；`FACTIONS` / `AREA_FACTION` →
#   门面 `content/catalog_b143.py`（B14-3 新建域 `factions`，门禁逐条相等）。切完 `C` 上
#   只剩**函数名句柄** `resolve`（宿主装配期索引，函数名不切）→ 见 docstring 逐符号归属表。
from . import catalog_b143 as _b143        # FACTIONS / AREA_FACTION
from . import catalog_core as _cc          # CLASSES / RACES
from . import catalog_quests as _cq        # MAIN_QUESTS / SIDE_QUESTS / NPCS / DIALOGUES / TITLES
from . import catalog_space as _cs         # MAP_BY_ID
from . import wild as _w                   # ALL_WILD（派生式读口）


# ============================================================
# 顺序声明（真源 `game/data/quests.py:939 SIDE_QUESTS` 的列表插入序）
# ------------------------------------------------------------
# B14-2：真源序表**单点移入门面** `content/catalog_quests.py`（门面里带集合守卫：
# 域多/少一条即 `raise`，且已与宿主聚合层同名表逐条对拍相等）。
# 本名保留只为宿主薄壳 `game/services/quests_flow.py:66` 的 re-export（名单与顺序同门面）。
# ============================================================
SIDE_QUEST_ORDER = [q["id"] for q in _cq.SIDE_QUESTS]


# ============================================================
# 宿主替身口（存储层 / 内容聚合层 / 同级服务 / 发放与结算）—— 引擎 wire 形状
# ============================================================
from saintess_engine.wire import Wire

# ★ U1-D2 L4（2026-09-17）：任务块的**三件形状**（账本状态机 / 目标进度折叠 / 目标行）
#   改走引擎 `saintess_engine/quest/`：`QuestLog`（读口 + 状态迁移）、`Objective`/`Objectives`
#   （有序目标类型注册表 + 折叠 + 行骨架）。**取值一个都没进引擎**：字段名（`main_*`）、
#   状态词（pending/active/ready/done）、目标类型词、需求数两种口径、三份行文模板全部
#   仍在本文件注册（见下面 `_QL_*` / `_OBJECTIVES` 注入面）。
from saintess_engine.quest import Objective, Objectives, QuestLog

#: 注入句柄面（`bind_host()` 写；`None` = 没给）——槽名 = `bind_host` 形参名
_WIRE = Wire()

# 宿主模块名（运行时 `main.py` 的模块路径 = `data.plugins.dragonfall`；测试同样）—— 与
# `content/flow/weekly_progress.py` / `content/talk_actions.py` 同口径（B8.2 线1 立的规矩）
from ._hostref import HOST_PKG, HOST_PKG_FALLBACK, make_bound_host  # 宿主包名常量单源（P0-3）

# `C` 上**未进包**的符号 → 转宿主聚合层：W6 后只剩函数名 `resolve`（见下面 `_Dom`）


def bind_host(db=None, c=None, level_up=None, stat_bonus_fn=None,
              grant_reward_fn=None, quests_svc=None) -> None:
    """宿主替身注入（幂等；宿主薄壳在 import 期调用）——写进引擎 wire 句柄面（`None` = 没给）。"""
    _WIRE.bind(db=db, c=c, level_up=level_up, stat_bonus_fn=stat_bonus_fn,
               grant_reward_fn=grant_reward_fn, quests_svc=quests_svc)


_bound_host = make_bound_host(_WIRE, "quests_flow")


class _HostDB:
    """惰性宿主存储层代理（真源 `from .. import db`）——`db.xxx` 正文不动，属性访问时解析。"""

    def __getattr__(self, name):
        return getattr(_bound_host("db"), name)


db = _HostDB()


def _host_c():
    """宿主内容聚合层（真源 `from .. import content as C`）。"""
    return _bound_host("c", "content")


class _HostAttr:
    """惰性宿主模块属性（正文里当普通常量用；只实现 `in` / 迭代 / 取值）。"""

    def __init__(self, mod: str, attr: str):
        self._mod, self._attr = mod, attr

    def _v(self):
        key = "quests_svc" if self._mod == "services.quests" else self._mod
        return getattr(_bound_host(key, self._mod), self._attr)

    def __contains__(self, item):
        return item in self._v()

    def __iter__(self):
        return iter(self._v())

    def __len__(self):
        return len(self._v())

    def __repr__(self):
        return repr(self._v())


DAILY_META_KEYS = _HostAttr("services.quests", "DAILY_META_KEYS")


def check_player_level_up(group_id, qq_id, player):
    """升级结算（真源 函数体内 `from ..content_rules.gameplay import check_player_level_up`）。

    ★ REPOINT-PKG（2026-09-15，B4R B 组第 2 项）：兜底由「宿主子模块
      `game.content_rules.gameplay`」改为**包内直取** `content/gameplay_rules.py`
      —— 宿主那边是同名单再导出（同一函数对象），包内不再指向宿主薄壳。
      注入槽 `bind_host(level_up=…)` 原样保留（宿主薄壳波2 仍可用它覆盖；取件时机 = 调用时，不变）。
    """
    fn = _WIRE.handles().get("level_up")
    if fn is None:
        from .gameplay_rules import check_player_level_up as fn   # 包内直取（调用时取件，与旧口径同时机）
    return fn(group_id, qq_id, player)


def stat_bonus(group_id, qq_id, player):
    """外部面板增幅聚合（真源 函数体内 `from ..core.stat_bonus import stat_bonus`）。

    ★ REPOINT-PKG（2026-09-15，B4R B 组第 3 项）：兜底由「宿主子模块
      `game.core.stat_bonus`」改为**包内直取** `content/stat_bonus.py` —— 宿主那边是
      同名单再导出（同一函数对象），包内不再指向宿主薄壳。
      注入槽 `bind_host(stat_bonus_fn=…)` 原样保留。
    """
    fn = _WIRE.handles().get("stat_bonus_fn")
    if fn is None:
        from .stat_bonus import stat_bonus as fn                  # 包内直取（调用时取件，与旧口径同时机）
    return fn(group_id, qq_id, player)


def grant_reward(*args, **kwargs):
    """发放（真源 函数体内 `from ..reward import grant_reward`）。"""
    fn = _WIRE.handles().get("grant_reward_fn")
    if fn is None:
        fn = getattr(_bound_host("grant_reward_fn", "reward"), "grant_reward")
    return fn(*args, **kwargs)


def _bump_daily_progress(*args, **kwargs):
    """行会每日委托计数（真源 函数体内 `from .quests import bump_daily_progress`）。"""
    fn = getattr(_bound_host("quests_svc", "services.quests"), "bump_daily_progress")
    return fn(*args, **kwargs)


def settle_daily_quest(*args, **kwargs):
    """每日委托达标结算单点（真源 函数体内 `from ..services.quests import settle_daily_quest`）。"""
    fn = getattr(_bound_host("quests_svc", "services.quests"), "settle_daily_quest")
    return fn(*args, **kwargs)


# ============================================================
# 宿主句柄门面（替身 `C`）—— W6 后只剩**函数名** `resolve`；数据名已切 `catalog_*.py` /
# `content/wild.py`（函数名句柄不切，逐符号归属见模块 docstring）
# ============================================================
class _Dom:
    """`C` 上的宿主替身 —— W6 收窄到**只剩 `resolve`**（函数名）。

    `ALL_WILD` → 派生式读口 `content/wild.py`；`FACTIONS` / `AREA_FACTION` → 门面
    `content/catalog_b143.py`；其余数据名走门面 `catalog_quests` / `catalog_core` /
    `catalog_space`。`resolve` 的权威索引（`materials` 598 条）是宿主**装配期**产物，
    包内 `content/tables.py:resolve` 对它原样返回（会静默错）⇒ 必须委托宿主。
    """

    @staticmethod
    def resolve(table_name: str, name_or_id: str):
        """`game/core/index.py:47 resolve` —— **委托宿主**（materials 的权威索引在装配期的宿主侧）。"""
        return _host_c().resolve(table_name, name_or_id)


C = _Dom()


# ============================================================
# ★ U1-D2 L4：引擎 `quest` 形状的**注入面**（取值全在这里，引擎零默认值）
# ============================================================
# ── 账本：字段名 / 状态词 / 子账本声明 ────────────────────────────────────────
# ⚠ 两套词表（**实测现状，不许顺手统一**）：顶层主线用 `main_quest`/`main_status`/
#   `main_progress`/`completed_main`；子账本（side/daily）**条目**用裸 `status`/`progress`。
#   引擎 `QuestLog` 的一份 `fields` 覆盖不了两套（角色键只有一个 `status`）⇒ 内容侧建
#   **两个外壳**：`_log()` 读主线顶层、`_lane_log()` 读/迁 side·daily 条目。
#   （设计稿 §2.2 假设一套 fields 通吃；这是设计↔实现的**口径出入**，登记在 out/LANDING.md）
_QL_FIELDS = {"current": "main_quest", "status": "main_status",
              "progress": "main_progress", "archive": "completed_main",
              "lanes": "side"}
_QL_ENTRY_FIELDS = {"current": "main_quest", "status": "status",
                    "progress": "progress", "archive": "completed_main",
                    "lanes": "side"}
#: 状态词（`pending`/`active`/`done` 是内容约定；`ready` 是内容侧第四态，按值显式传）
_QL_STATES = {"todo": "pending", "live": "active", "ended": "done"}
#: 子账本声明（口径分歧③：side 的进度是 mapping、daily 的是整格 int）
_QL_LANES = (("side", {"progress": dict}), ("daily", {"progress": int}))


def _log(raw=None):
    """主线账本外壳（顶层 `main_*` 词表）。构造 O(1)，不落库。"""
    return QuestLog(raw, fields=_QL_FIELDS, states=_QL_STATES, lanes=_QL_LANES)


def _lane_log(raw=None):
    """side / daily 子账本外壳（**条目**词表：裸 `status`/`progress`）。"""
    return QuestLog(raw, fields=_QL_ENTRY_FIELDS, states=_QL_STATES, lanes=_QL_LANES)


def _expire_daily(quests):
    """跨天清理（口径分歧⑪：**系统钟**，实现逐字留在 `content.persistence.quests`）。

    单点转调而非直调 `db.expire_daily` —— 让「本模块是否真的依赖跨天清理」可被替身观测。
    """
    return db.expire_daily(quests)


# ── 目标类型注册表：15 键（11 型 + 4 修饰键），四个回调全是取值 ────────────────
def _ml_name(value, ev):
    """击杀名匹配（前缀精确：`==` 或 `「目标」·` 开头 —— v104 M20 P2 口径逐字保留）。"""
    name = ev.get("name")
    if name == value:
        return True
    return isinstance(name, str) and name.startswith(str(value) + "·")


_KILL_KINDS = ("kill", "kill_variant", "kill_any", "kill_elite", "kill_boss")


def _m_kill(value, ev):
    """`kill` 型命中：击杀事件 + 目标名前缀精确。"""
    return ev.get("kind") in _KILL_KINDS and _ml_name(value, ev)


def _m_collect(value, ev):
    """`collect` 型命中：采集事件 + 物品名一致（主线/支线的**达标数**另有专门口径）。"""
    return ev.get("kind") == "collect" and ev.get("collect") == value


def _m_explore(value, ev):
    """`explore` 型命中：到达的地图 = 目标地图。"""
    return bool(value) and ev.get("map") == value


def _m_find(value, ev):
    """`find` 型：告示委托靠探索概率（无事件驱动）⇒ **永不命中**（只出行文）。"""
    return False


def _m_use(value, ev):
    """`use` 型命中：使用物品事件 + 物品名一致。"""
    return ev.get("kind") == "use" and ev.get("use") == value


def _m_talk(value, ev):
    """`talk` 型命中：与目标 NPC 对话。"""
    return ev.get("kind") == "talk" and ev.get("talk") == value


def _m_any(value, ev):
    """`kill_any` 型命中：任意击杀（v95.13 支线 / 每日通用击杀）。"""
    return ev.get("kind") in _KILL_KINDS


def _m_elite(value, ev):
    """`kill_elite` 型命中：精英击杀（每日 lane）。"""
    return bool(ev.get("is_elite"))


def _m_boss(value, ev):
    """`kill_boss` 型命中：首领击杀（每日 lane）。"""
    return bool(ev.get("is_boss"))


def _n_count(objective, engine=None):
    """`kill` 需求数 = `count`（旧写法 `obj['count']` 下标读，缺失照样 KeyError）。"""
    return objective["count"]


def _n_collect(objective, engine=None):
    """`collect` 需求数 = `collect_count or count`（口径分歧④第一种，逐字保留）。"""
    return objective.get("collect_count") or objective.get("count", 1)


def _n_one(objective, engine=None):
    """单键达成型（explore/find/use/talk）：需求数恒 1。"""
    return 1


def _n_any(objective, engine=None):
    """单键计数型（kill_any/kill_elite/kill_boss/complete_side/collect_any）= 首个正整数。

    这就是 `daily_need` 的旧口径（面板/每日同源）；都没有定义 → 0（旧 `daily_need` 回读
    定义表后仍无 → None，那一层由内容侧保留）。
    """
    for _v in objective.values():
        if isinstance(_v, bool) or not isinstance(_v, int):
            continue
        if _v > 0:
            return _v
    return 0


def _f_kill(objective, progress, ev):
    """击杀进度补丁：`{目标名: 旧值 + 1}`（进度键 = **目标名**，口径分歧⑦）。"""
    _key = objective["kill"]
    _base = progress.get(_key, 0) if isinstance(progress, Mapping) else 0
    return {_key: _base + 1}


def _f_any(objective, progress, ev):
    """通用击杀计数补丁（`kill_any` 支线用 `progress["any"]`，v95.13 防卡死）。"""
    _base = progress.get("any", 0) if isinstance(progress, Mapping) else 0
    return {"any": _base + 1}


def _f_use(objective, progress, ev):
    """`use` 进度补丁：`{"use": 物品名}`（旧实现是**覆盖**，调用方用 `accept` 落格）。"""
    return {"use": objective["use"]}


#: 有序目标类型注册表：**声明序 = 判定序 = 展示序**（旧三份渲染口的固定 `if` 序）。
#: `need` 全部自带 ⇒ 不注入 `need_of`（未注册类型走 `unknown` 默认 = 不出行）。
_OBJECTIVES = Objectives(
    Objective("kill", match=_m_kill, need=_n_count, fold=_f_kill,
              modifiers=("count",)),
    Objective("collect", match=_m_collect, need=_n_collect,
              modifiers=("count", "collect_count")),
    Objective("explore", match=_m_explore, need=_n_one, multi=True,
              modifiers=("map",)),
    Objective("find", match=_m_find, need=_n_one, multi=True,
              modifiers=("map", "chance")),
    Objective("use", match=_m_use, need=_n_one, fold=_f_use, multi=True,
              modifiers=("map",)),
    Objective("talk", match=_m_talk, need=_n_one),
    Objective("kill_any", match=_m_any, need=_n_any, fold=_f_any,
              modifiers=("count",)),
    Objective("kill_elite", match=_m_elite, need=_n_any,
              modifiers=("count",)),
    Objective("kill_boss", match=_m_boss, need=_n_any,
              modifiers=("count",)),
    Objective("complete_side", need=_n_any),
    Objective("collect_any", need=_n_any),
)

#: 内容侧**声明序**（行序/取值序都按它；`_obj_in_order` 用它把目标 mapping 还原成声明序）
_OBJ_ORDER = tuple(_OBJECTIVES.keys())


def _need_main_collect(obj):
    """主线 collect 需求数 = **只看 `count`**（口径分歧④第二种，逐字保留；别统一掉）。"""
    return obj.get("count", 1)


def _kill_event(monster):
    """击杀事件（引擎只透传；事件键由内容侧定）—— 本入口只从击杀路径进来，故 kind 恒 `kill`。"""
    return {"kind": "kill", "name": monster.get("name"),
            "is_elite": monster.get("is_elite"), "is_boss": monster.get("is_boss")}


def _obj_in_order(obj):
    """目标 mapping → 按内容侧声明序前置的视图（其余键保持原相对序）。

    旧三份渲染口都是**固定 `if` 序**（kill → collect → explore → find → use → talk），与目标
    mapping 的插入序无关；引擎 `lines()` 按**插入序**出行 ⇒ 交给引擎前先把声明序还原出来。
    """
    order = _OBJ_ORDER
    return {**{k: obj[k] for k in order if k in obj},
            **{k: v for k, v in obj.items() if k not in order}}


def _obj_lines(obj, *, progress=None, state=None, text_of=None):
    """目标行**骨架**：引擎注册表 + 内容侧声明序 + 该出口自己的 `text_of` 模板。"""
    return _OBJECTIVES.lines(_obj_in_order(obj), progress=progress, state=state,
                             text_of=text_of)


def _one_text_of(type_key, obj, prog, st):
    """接取/交付通知的**单行**目标模板（`obj_text` 口径；行文逐字保留，不出的型 → None）。"""
    if not obj.get(type_key):
        return None
    if type_key == "kill":
        return f"击败 {obj['kill']} ×{_OBJECTIVES.need_of(obj, 'kill')}"
    if type_key == "collect":
        # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError
        return f"收集 {obj['collect']} ×{_OBJECTIVES.need_of(obj, 'collect')}"
    if type_key == "explore":
        return f"前往 {_cs.MAP_BY_ID.get(obj['explore'], {}).get('name', '？')}"
    if type_key == "find":
        # v97.1 告示委托：在指定地图探索概率找到目标
        return f"在 {_cs.MAP_BY_ID.get(obj.get('map', ''), {}).get('name', '？')} 寻找 {obj['find']}(探索有概率遇到)"
    if type_key == "use":
        # v124 use 目标：使用指定物品达成
        return f"使用 {obj['use']}"
    if type_key == "talk":
        npc = _cq.NPCS.get(obj["talk"], {})
        return f"与 {npc.get('name', '？')} 交谈"
    return None


def obj_text(obj):
    """目标单行摘要（取接取通知 / 交付面板用；未注册目标 → `"？"`，口径分歧⑤）。"""
    _lines = _obj_lines(obj, text_of=_one_text_of)
    return _lines[0] if _lines else "？"


def sq_unlocked(quests, sq):
    """v124 链式支线：unlock 前置解锁检查。unlock 支持单条或列表（全部满足）。
    格式：{"side": "s5"} 或 {"main": "q2_3"}（兼容 {"type":"side","id":"s5"} 写法）。
    无 unlock=天然解锁。"""
    u = sq.get("unlock")
    if not u:
        return True
    us = u if isinstance(u, list) else [u]
    _lane, _main = _lane_log(quests), _log(quests)
    for x in us:
        if not isinstance(x, dict):
            continue
        _typ = x.get("type") or ("side" if x.get("side") else "main" if x.get("main") else None)
        _tid = x.get("id") or x.get("side") or x.get("main") or ""
        if _typ == "side":
            # 支线完成 = side 条目状态 == ended（引擎读口；**条目缺失 → todo ≠ ended**，
            # 与旧 `(_sq or {}).get("status") != "done"` 同义）
            if _lane.status_of("side", _tid) != _QL_STATES["ended"]:
                return False
        elif _typ == "main":
            # 主线完成 = 在 completed_main 历史里 **或** 正是当前环（引擎读口 done/current）
            if _tid not in (_main.done or []) and _main.current != _tid:
                return False
    return True

def sq_stats_met(player, sq):
    """v124 隐藏线/副业线：require_stats 动作计数门槛。达标才可接取。
    stats 表以 qq_id 为主键，group_id 参数为兼容占位。"""
    rs = sq.get("require_stats")
    if not rs:
        return True
    _qq = player.get("qq_id") or player.get("id", "")
    if not _qq:
        return False
    _st = db.get_stats("", _qq) or {}
    for k, v in rs.items():
        if int(_st.get(k, 0) or 0) < int(v):
            return False
    return True

def available_quest_list(player, quests, mq) -> list:
    """当前地图可接取任务列表（v123d 抽出，供『接取』无参渲染与『接取 <序号>』映射共用）。

    返回 [{"name": 任务名, "line": 渲染行（不含 📜 前缀）}, ...]——主线 pending 在前，
    支线按 _cq.SIDE_QUESTS 顺序；告示委托（board）不在此列（须去告示板指名接取）。
    """
    available = []
    _side = _log(quests).lane()
    if mq and _log(quests).status == _QL_STATES["todo"]:
        giver = _cq.NPCS.get(mq["giver"]) or _w.ALL_WILD.get(mq["giver"]) or {}
        if giver.get("map") == player["cur_map"]:
            available.append({
                "name": mq["name"],
                "line": f"主线『{mq['name']}』（{giver.get('name', '？')}发布）",
            })
    for sq in _cq.SIDE_QUESTS:
        if sq["id"] in _side:
            continue
        # v124 链式支线：unlock 前置未满足不出现在可接列表
        if not sq_unlocked(quests, sq):
            continue
        # v124 隐藏线：require_stats 计数门槛未达不出现在可接列表
        if not sq_stats_met(player, sq):
            continue
        # v104 M20 P2：告示委托（board: true）只在告示板子区域指名接取，
        # 列入普通列表会误导玩家（点名接取被 world.py 告示板拦截逻辑挡下）
        if sq.get("board"):
            continue
        npc = _cq.NPCS.get(sq["giver"]) or _w.ALL_WILD.get(sq["giver"]) or {}
        if npc.get("map") == player["cur_map"]:
            # v104 M19：接取列表显示支线等级门槛
            _lv = f"Lv.{sq['min_level']}+ " if sq.get("min_level") else ""
            available.append({
                "name": sq["name"],
                "line": f"支线『{sq['name']}』{_lv}（{npc.get('name', '？')}发布）",
            })
    return available


# v116 §3.4：放弃进行中的支线/每日任务（释放接取位）。主线不可放弃。

def update_explore_quests(group_id, qq_id, map_id):
    """到达子区域时检查 explore 型任务(主线和支线)"""
    lines = []
    quests = db.get_quests(group_id, qq_id)
    changed = False
    # 主线 explore（v105：仅已接取(active)时触发——pending 未接取到达目标图不得自动完成+发奖）
    main_id = _log(quests).current
    if main_id and _log(quests).status == _QL_STATES["live"]:
        mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)
        if mq and _OBJECTIVES.hits(mq["objective"], {"kind": "explore", "map": map_id}):
            # v124.3：奖励统一走 _grant_quest_rewards（exp/gold/升级 + reward_item 全格式
            # + reward_pet/reward_mount/unlock_class）——此前 explore 自动完成只有
            # reward_item 单值，reward_pet 配了也静默不发
            grant_quest_rewards(group_id, qq_id, mq, lines)
            # 交付四步（历史追加 current / 当前环换 next / 状态回未接取 / 进度清空）走引擎；
            # 旧实现手写这四步（v105 M19 P1 注释里的「与 _take_main_quest 交付分支一致」）。
            quests = _log(quests).deliver(lane=None, next_of=lambda _cur: mq["next"])
            changed = True
            lines.append(f"📜 主线『{mq['name']}』达成！奖励：经验 +{mq['reward_exp']} 金币 +{mq['reward_gold']}")
            # v105 M19 P2：explore 自动完成补发声望（奖励本体已并入 _grant_quest_rewards）
            _rep = quest_reputation(group_id, qq_id, mq["giver"])
            if _rep:
                lines.append(f"  {_rep}")
            if mq["next"]:
                nq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mq["next"]), None)
                if nq:
                    lines.append(f"📜 新主线：『{nq['name']}』{nq['desc']}")
            else:
                lines.append("🎊 恭喜！你完成了全部主线任务，成为奥兰迪亚的传说！")
    # 支线 explore
    _lane = _lane_log(quests)
    for sid, sq in list(_lane.lane("side").items()):
        if _lane.status_of("side", sid) == _QL_STATES["live"]:
            sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
            if sqd and _OBJECTIVES.hits(sqd["objective"], {"kind": "explore", "map": map_id}):
                # 条目置 ready（引擎改状态；进度不动，与旧实现只写 status 同义）
                quests = _lane.set_status("ready", lane="side", key=sid)
                _lane = _lane_log(quests)
                changed = True
                _g = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}
                lines.append(f"📜 支线『{sqd['name']}』目标达成！回去找 {_g.get('name', '？')} {deliver_hint(sqd['giver'])}吧～")
    if changed:
        db.save_quests(group_id, qq_id, quests)
    return lines

def take_main_quest(group_id, qq_id, npc_id, npc):
    """从 NPC 接主线任务；返回通知行列表"""
    lines = []
    player = db.get_player(group_id, qq_id)
    quests = db.get_quests(group_id, qq_id)
    main_id = _log(quests).current
    if not main_id:
        lines.append("🎊 主线任务已全部完成，你已是奥兰迪亚的传说！")
        return lines
    mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)
    # 存档容错：main_quest 指向已不存在的任务（旧存档/主线数据变更）→ 重置回主线起点
    if not mq and main_id:
        # 引擎无「换当前环且不追加历史」的迁移口（`deliver` 是唯一改 current 的动作，但它
        # 会追加 archive）⇒ 用 `accept(entry=…)` 把三格一次性写回（仍走引擎的建条目路径）
        quests = _log(quests).accept(lane=None, key=main_id,
                                     entry={_QL_FIELDS["current"]: "q1_1"},
                                     status=_QL_STATES["todo"], progress={})
        main_id = "q1_1"
        mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)
    if not mq or mq["giver"] != npc_id:
        # 不是这个 NPC 的任务
        need_npc = _cq.NPCS.get(mq["giver"], {}).get("name", "？") if mq else "？"
        lines.append(f"【{npc['name']}】我现在没有任务交给你。镇长/各地首领或许有安排……")
        if mq:
            lines.append(f"📜 当前主线『{mq['name']}』由 {need_npc} 发布。")
        return lines
    st = _log(quests).status
    # v105 P0：collect 型主线（q5_5 圣光百合）——背包材料足够即置 ready
    # （对齐支线逻辑 talk_actions.py:111-113 实时数背包；交付时再扣材料）
    # 放在状态分发前：pending 接取时材料已齐 → 直接可交付；active 回来找 NPC → 置 ready
    obj0 = mq["objective"]
    if obj0.get("collect") and st != "ready" and db.count_item(group_id, qq_id, obj0["collect"]) >= _need_main_collect(obj0):
        # 主线 collect 口径 = 只看 `count`（口径分歧④第二种；与 `collect` 型的
        # `collect_count or count` 故意不同 —— 这一处逐字保留）
        quests = _log(quests).accept(lane=None, key=main_id, status="ready",
                                     progress={obj0["collect"]: _need_main_collect(obj0)})
        db.save_quests(group_id, qq_id, quests)
        st = "ready"
    if st == "pending":
        # v169.1：主线 min_level 硬门槛（高经验主线防跨级接取；suggest_lv 仅软提示保留）
        if mq.get("min_level") and player["level"] < mq["min_level"]:
            return lines + [f"🛡️ 『{mq['name']}』需要 Lv.{mq['min_level']} 才能接取！（你当前 Lv.{player['level']}）先去提升实力吧～"]
        quests = _log(quests).accept(lane=None, key=main_id,
                                     status=_QL_STATES["live"], progress={})
        # talk 型任务：与发布 NPC 交谈即达成目标（对话即完成）
        obj = mq["objective"]
        if obj.get("talk") and obj["talk"] == npc_id:
            quests = _log(quests).accept(lane=None, key=main_id, status="ready",
                                         progress={obj["talk"]: 1})
        # v105 P2：explore 型主线接取时已在目标地图 → 直接置 ready（免出图重进）
        if obj.get("explore") and player.get("cur_map") == obj["explore"]:
            quests = _log(quests).accept(lane=None, key=main_id, status="ready",
                                         progress={obj["explore"]: 1})
        db.save_quests(group_id, qq_id, quests)
        lines.append(f"📜 【接取任务】『{mq['name']}』")
        if mq.get("story"):
            lines.append(f"  📖 {mq['story']}")
        lines.append(f"  🎯 目标：{obj_text(mq['objective'])}")
        lines.append(f"  奖励：经验 +{mq['reward_exp']} 金币 +{mq['reward_gold']}")
        # v95.25 #138：主线等级建议（软提示，不拦截接取）——suggest_lv 在 quests.py 数据里
        if mq.get("suggest_lv") and player["level"] < mq["suggest_lv"]:
            lines.append(f"  ⚠️ 建议等级 Lv.{mq['suggest_lv']}，你才 Lv.{player['level']}——可以先练练级再挑战！")
        if _log(quests).status == "ready":
            lines.append("  ✨ 交谈完成！再与这位 NPC 对话即可交付任务。")
    elif st == "ready":
        # 交任务领奖
        obj = mq.get("objective") or {}
        # v105 P0：collect 型主线交付时扣材料（先复核背包，材料被消耗则回到进行中）
        if obj.get("collect"):
            need = _need_main_collect(obj)
            if db.count_item(group_id, qq_id, obj["collect"]) < need:
                quests = _log(quests).accept(lane=None, key=main_id,
                                             status=_QL_STATES["live"], progress={})
                db.save_quests(group_id, qq_id, quests)
                lines.append(f"📜 交付『{mq['name']}』需要 {obj['collect']} ×{need}，你背包里不够了，先去凑齐吧～")
                return lines
            db.remove_item(group_id, qq_id, obj["collect"], need)
            # v126.2：鱼获个体属性在 item_data.tags，remove_item 自动截断，无需额外同步
            lines.append(f"🎒 交出 {obj['collect']} ×{need}")
        # v124.3：奖励统一走 _grant_quest_rewards（exp/gold/升级 + reward_item 全格式
        # + reward_pet/reward_mount/unlock_class）——此前主线交付只支持 reward_item
        # 单值 + reward_pet，eq:/list 随机/坐骑/隐藏职业配了不发
        grant_quest_rewards(group_id, qq_id, mq, lines)
        # 交付四步走引擎：历史追加 current（**保序不去重**，口径分歧①）→ current 换 next →
        # 状态回 todo → 进度清空。与 `_take_main_quest` / explore 完成三处**同一份语义**。
        quests = _log(quests).deliver(lane=None, next_of=lambda _cur: mq["next"])
        db.save_quests(group_id, qq_id, quests)
        lines.append(f"✅ 【任务完成】『{mq['name']}』！")
        if mq.get("ending"):
            # v105 M19 P1：主线抉择结局变体——q10_5 等任务按对话树选择的 flag 输出不同结尾
            _ending = mq["ending"]
            _endings = mq.get("endings") or {}
            if _endings:
                try:
                    _flags = db.get_talk_flags(group_id, qq_id, mq["giver"]) or []
                except Exception:
                    _flags = []
                for _fk, _fv in _endings.items():
                    if _fk in _flags:
                        _ending = _fv
                        break
            lines.append(f"  📖 {_ending}")
        lines.append(f"  奖励：经验 +{mq['reward_exp']} 金币 +{mq['reward_gold']}")
        rep_line = quest_reputation(group_id, qq_id, mq["giver"])
        if rep_line:
            lines.append(f"  {rep_line}")
        if mq["next"]:
            nq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mq["next"]), None)
            if nq:
                lines.append(f"📜 新主线：『{nq['name']}』{nq['desc']}")
                lines.append(f"  🎯 去找 {_cq.NPCS[nq['giver']]['name']} 接取新任务")
        else:
            lines.append("🎊 恭喜！你完成了全部主线任务，成为奥兰迪亚的传说！")
    else:
        lines.append(f"📜 你已接取『{mq['name']}』：{mq['desc']}")
    return lines

def quest_reputation(group_id, qq_id, npc_id):
    """完成任务时给对应势力加声望，返回提示行(如有)"""
    npc = _cq.NPCS.get(npc_id)
    if not npc:
        return ""
    m = _cs.MAP_BY_ID.get(npc["map"], {})
    area_key = m.get("area", npc["map"])
    faction = _b143.AREA_FACTION.get(area_key)
    if not faction:
        return ""
    db.add_reputation(group_id, qq_id, faction, 10)
    return f"🏛️ {_b143.FACTIONS[faction]['icon']} 声望＋10"

def deliver_hint(npc_id):
    """交付方式提示（v95.16 #75）：有对话树 NPC 走对话交付，无对话树 NPC 用『交付任务』"""
    if _cq.DIALOGUES.get(npc_id):
        return "对话交付"
    return "『交付任务』交付"

def side_available_list(group_id, qq_id, npc_id, npc) -> list:
    """v127.6：该 NPC 名下当前"可接"的支线清单（对话菜单/预告/全接三处同源过滤）。

    过滤条件与旧 _offer_side_quests 全部一致：giver == npc_id、非告示板委托(board)、
    未接取（不在 side）、_sq_unlocked 链式前置、_sq_stats_met 计数门槛、
    min_level 等级门槛、require_race 种族限制。每项返回
    {sid, name, desc, objective_text, reward_exp, reward_gold}，按 SIDE_QUESTS 定义顺序
    （保证对话菜单序号稳定）。npc 参数保留以与 _offer_side_quests 签名一致（此处未用到）。
    """
    player = db.get_player(group_id, qq_id) or {}
    quests = db.get_quests(group_id, qq_id)
    side = _lane_log(quests).lane("side")
    out = []
    for sq in _cq.SIDE_QUESTS:
        if sq["giver"] != npc_id:
            continue
        if sq.get("board"):  # v95r65 #295：告示板委托只能在告示板接取，NPC 不自动发
            continue
        if sq["id"] in side:
            continue
        # v124 链式支线：unlock 前置未满足不自动发（如剧情线第二步等第一步完成）
        if not sq_unlocked(quests, sq):
            continue
        # v124 隐藏线/副业线：require_stats 计数门槛未达不自动发（如 H7 需垂钓 10 次）
        if not sq_stats_met(player, sq):
            continue
        # v101.30d #O52：支线等级门槛（min_level 字段）——等级不够不算可接
        if sq.get("min_level") and (player.get("level") or 0) < sq["min_level"]:
            continue
        # v113 种族限制：require_race 指定血脉（隐藏线试炼）——非该种族不算可接
        if sq.get("require_race"):
            _cur = player.get("race") or "human"
            if _cur != sq["require_race"]:
                continue
        out.append({
            "sid": sq["id"],
            "name": sq["name"],
            "desc": sq.get("desc", ""),
            "objective_text": obj_text(sq.get("objective") or {}),
            "reward_exp": sq.get("reward_exp", 0),
            "reward_gold": sq.get("reward_gold", 0),
        })
    return out

def offer_side_quest(group_id, qq_id, npc_id, sid) -> list:
    """v127.6：单条支线接取（对话 side_menu 子选项 action: side_take_one）。

    校验 sid 必须在 _side_available_list 当前可接清单内才接（防越权/已接/等级不足），
    否则返回 [] 不落地。返回该任务的接取通知行列表。
    """
    item = next((a for a in side_available_list(group_id, qq_id, npc_id, None)
                 if a["sid"] == sid), None)
    if not item:
        return []
    sq = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
    if not sq:
        return []
    quests = db.get_quests(group_id, qq_id)
    # 接取 = 建条目（引擎 `accept`：status=live、进度按 side 的 dict 口径清空）
    quests = _lane_log(quests).accept(lane="side", key=sid, status=_QL_STATES["live"],
                                      progress={})
    db.save_quests(group_id, qq_id, quests)
    return [
        f"📜 【支线】『{sq['name']}』{sq['desc']}",
        f"  奖励：经验 +{sq['reward_exp']} 金币 +{sq['reward_gold']}",
        f"  🎯 目标：{item['objective_text']}",
    ]

def offer_side_quests(group_id, qq_id, npc_id, npc):
    """NPC 有未接的支线任务时自动接取，返回通知行列表

    v127.6 重构：可接清单统一走 _side_available_list（与对话 side_menu 菜单/预告同源过滤），
    逐条复用 _offer_side_quest 接取；不可接（min_level/require_race 被过滤掉）的
    原拒绝提示按 SIDE_QUESTS 顺序保留，全接+完成提示行为不变（旧 side_offer action 兼容，
    单支线 NPC 无感）。
    """
    player = db.get_player(group_id, qq_id) or {}
    lines = []
    quests = db.get_quests(group_id, qq_id)
    side = _lane_log(quests).lane("side")
    available = side_available_list(group_id, qq_id, npc_id, npc)
    av_ids = {a["sid"] for a in available}
    changed = False
    for sq in _cq.SIDE_QUESTS:
        if sq["giver"] != npc_id or sq.get("board"):
            continue
        if sq["id"] in side:
            continue
        if sq["id"] in av_ids:
            quests = _lane_log(quests).accept(lane="side", key=sq["id"],
                                              status=_QL_STATES["live"], progress={})
            changed = True
            lines.append(f"📜 【支线】『{sq['name']}』{sq['desc']}")
            lines.append(f"  奖励：经验 +{sq['reward_exp']} 金币 +{sq['reward_gold']}")
            lines.append(f"  🎯 目标：{obj_text(sq['objective'])}")
            continue
        # 不可接但符合其余条件的拒绝提示（与原始行为文案一致）
        if not sq_unlocked(quests, sq):
            continue
        if not sq_stats_met(player, sq):
            continue
        # v101.30d #O52：支线等级门槛——等级不够不自动接
        if sq.get("min_level") and (player.get("level") or 0) < sq["min_level"]:
            lines.append(
                f"🛡️ {npc.get('name', '对方')}打量了你一眼：这活得有 Lv.{sq['min_level']}+ 的本事，你再去练练吧。"
            )
            continue
        # v113 种族限制：require_race 指定血脉——非该种族导师直接拒绝
        if sq.get("require_race"):
            _rr = sq["require_race"]
            _cur = player.get("race") or "human"
            if _cur != _rr:
                _rcn = (_cc.RACES.get(_rr) or {}).get("name", "对应血脉")
                lines.append(
                    f"⛔ {npc.get('name', '对方')}凝视着你，缓缓摇头：『这份传承只属于{_rcn}的血脉。"
                    f"你体内流淌的{(_cc.RACES.get(_cur) or {}).get('name', '血脉')}之血，与它无缘。』"
                )
                continue
    if changed:
        db.save_quests(group_id, qq_id, quests)
    # v95.4：该 NPC 有已完成支线 → 提示交付入口（反馈：可交任务找不到交付方式）
    # v95.15 #73：代词按 NPC 性别（迷路骑士等男性 NPC 用"他"）
    # v95.16 #75：按是否有对话树区分交付引导（无对话树 NPC 的『对话』没有交付选项）
    _ta = "她" if npc.get("gender") == "女" else "他"
    _lane = _lane_log(quests)
    for sid, sq in list(_lane.lane("side").items()):
        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
        if sqd and sqd["giver"] == npc_id and _lane.status_of("side", sid) == "ready":
            if _cq.DIALOGUES.get(npc_id):
                lines.append(f"✅ 『{sqd['name']}』已完成！与{_ta}对话即可交付～")
            else:
                lines.append(f"✅ 『{sqd['name']}』已完成！输入『交付任务』即可交付～")
            break
    return lines

# v104 M24 P2-2：『交任务』无命中（策划案 23 章:182 主指令）→ 补别名

def grant_quest_rewards(group_id, qq_id, qdef, lines):
    """v124.3 统一任务奖励发放（主线 explore 自动完成 / 主线交付 / 支线交付三处共用）。

    基准：支线 _complete_side_quest 原实现（v104 M20 + v124 全奖励类型）——
    reward_exp/reward_gold 入角色并结算升级；reward_item 支持单值 / 列表随机 /
    eq: 装备名册；reward_pet 宠物蛋 / reward_mount 坐骑缰绳入包；unlock_class
    解锁隐藏职业。声望 / 分支 flag / 每日计数等任务特有处理不入此函数，调用方各自保留。
    返回结算后的 player（调用方后续需要时使用，如 _complete_side_quest 的 _rule_fire）。"""
    import random
    player = db.get_player(group_id, qq_id)
    player["exp"] += qdef.get("reward_exp", 0)
    player["gold"] += qdef.get("reward_gold", 0)
    player["_title_bonus"] = stat_bonus(group_id, qq_id, player)
    lv_logs, player = check_player_level_up(group_id, qq_id, player)
    db.update_player(group_id, qq_id, exp=player["exp"], gold=player["gold"], level=player["level"], hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"], skills=player["skills"], attr_pts=player.get("attr_pts", 0), skill_points=player.get("skill_points", 0), learned_skills=player.get("learned_skills", []))
    if lv_logs:
        if lines:
            lines.append("")
        lines += lv_logs
    # v104 M20 P1：列表型奖励（如 s17 随机符文）→ 随机抽一个发放
    # v174 统一抽象：item/eq/pet/mount/title 发放走 game.reward.grant_reward
    # （只传物品类，exp/gold 已在上方原逻辑结算且要 return 更新后 player）
    ri = qdef.get("reward_item")
    _reward_items = []
    if ri:
        if isinstance(ri, list):
            ri = random.choice(ri)
        # eq: 前缀保留（grant_reward 支持 eq:rid 按名册名解析）
        _reward_items.append({"item": ri, "n": 1})
    _rew = {}
    if _reward_items:
        _rew["items"] = _reward_items
    rp = qdef.get("reward_pet")
    if rp:
        _rew["pets"] = [rp] if isinstance(rp, str) else list(rp)
    rm = qdef.get("reward_mount")
    if rm:
        _rew["mounts"] = [rm] if isinstance(rm, str) else list(rm)
    _tid = qdef.get("title")
    if _tid:
        _rew["title"] = _tid
    if _rew:
        try:
            grant_reward(_rew, group_id, qq_id, player=player, lines=lines)
        except Exception:
            pass
    # v87 隐藏职业：交任务解锁（unlock_class 写入 hidden_class_unlock）
    uc = qdef.get("unlock_class")
    if uc:
        player_now = db.get_player(group_id, qq_id)
        unlocks = list(player_now.get("hidden_class_unlock", []) or [])
        if uc not in unlocks:
            unlocks.append(uc)
            db.update_player(group_id, qq_id, hidden_class_unlock=unlocks)
            lines.append(f"  ⚔️ 传承达成！隐藏职业「{_cc.CLASSES.get(uc, {}).get('name', uc)}」已解锁！")
            # v112：档位门槛统一读 CLASSES["tier_levels"]（缺省 T1=40），删除 60/30 特例
            _need = (_cc.CLASSES.get(uc, {}).get("tier_levels") or {1: 40, 2: 60, 3: 90})[1]
            _cname = _cc.CLASSES.get(uc, {}).get("name", uc)
            lines.append(f"  💡 达到 {_need} 级后输入『转职 {_cname}』接受传承！")
    # v140 波3.6：任务奖励称号（title 字段 = titles.py id 或中文名；称号系统条件判定自动拥有，
    # 这里仅播报解锁——条件满足即生效，不满足也不阻塞任务完成）
    _tid = qdef.get("title")
    if _tid:
        _tinfo = next((t for t in _cq.TITLES if t.get("id") == _tid), None)
        if not _tinfo:
            # 兼容支线旧字段用中文名（如 "北境的恩人" → north_benefactor）
            _tinfo = next((t for t in _cq.TITLES if t.get("name") == _tid), None)
        if _tinfo:
            lines.append(f"  🏅 获得称号：「{_tinfo.get('name', _tid)}」！")
        else:
            print(f"[dragonfall][v140] 任务『{qdef.get('name', '')}』称号 id 缺失：{_tid}（titles.py 未登记），已跳过")
    return player

def complete_side_quest(group_id, qq_id, sid, branch_choice=None, hooks=None):
    """交支线任务，返回通知行列表
    v124：支持 branch 分支交付（第一次输出选项并置 branch_wait，玩家回复数字后执行）+
    deliver_text 交付剧情文本。

    hooks：命令层注入 {"tip": callable(cat)->str, "rule_fire": callable(trigger,...)->str}
    （_tip/_rule_fire 是命令层 I/O 面板能力，P4-2 按 §5.2 以 hooks 回调接入）；
    缺省（None）时 _tip 返回空串、_rule_fire 返回空串——service 直测不依赖命令层。"""
    _tip = (hooks or {}).get("tip")
    _rule_fire = (hooks or {}).get("rule_fire")
    lines = []
    quests = db.get_quests(group_id, qq_id)
    sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
    if not sqd:
        return ["未知支线任务。"]
    sq = _lane_log(quests).entry("side", sid)
    if not sq:
        return ["这个任务还没完成呢。"]
    obj = sqd["objective"]
    # 收集型：实时检查背包材料（不依赖 ready 状态）
    if obj.get("collect"):
        # v87 复合目标：kill+collect（魔剑士试炼），collect_count 独立于 kill count
        need = _OBJECTIVES.need_of(obj, "collect")  # v125.1 P2：s64 等 collect_count 无 count 不再 KeyError
        _ckey = C.resolve("materials", obj["collect"])
        have = db.count_item(group_id, qq_id, _ckey)
        if have < need:
            return [f"材料不够！需要 {obj['collect']} ×{need}，你只有 {have} 个。"]
        # v87 复合目标：同时存在 kill 目标时，击杀进度也要满足
        if obj.get("kill"):
            kp = (sq.get("progress") or {}).get(obj["kill"], 0)
            if kp < obj["count"]:
                return [f"还要击败 {obj['kill']} ×{obj['count'] - kp}(当前 {kp}/{obj['count']})！"]
    elif _lane_log(quests).status_of("side", sid) != "ready":
        return ["这个任务还没完成呢。"]
    # v124 分支任务：第一次交付输出选项，等待玩家回复数字
    br = sqd.get("branch")
    if br and not branch_choice:
        opts = br.get("options") or []
        if sq.get("branch_wait"):
            return [f"{br.get('prompt', '')}\n{_tip('quest_branch')}\n" + "\n".join(
                f"  {o.get('key', str(i + 1))}. {o.get('label', '')}" for i, o in enumerate(opts))]
        # 置「可交 + 分支等待」（分支等待是**存档里的一个布尔键**，改名即改存档）
        quests = _lane_log(quests).accept(lane="side", key=sid,
                                          entry={**sq, "branch_wait": True}, status="ready")
        db.save_quests(group_id, qq_id, quests)
        _o = [f"  {o.get('key', str(i + 1))}. {o.get('label', '')}" for i, o in enumerate(opts)]
        return [f"{br.get('prompt', '')}\n{_tip('quest_branch')}\n" + "\n".join(_o)]
    # v124 分支选择执行
    if br and branch_choice:
        opts = br.get("options") or []
        chosen = None
        if isinstance(branch_choice, str):
            for o in opts:
                if branch_choice in (o.get("key"), o.get("label")):
                    chosen = o
                    break
        if chosen is None:
            return [f"没有这个选项～{br.get('prompt', '')}\n{_tip('quest_branch')}\n" + "\n".join(
                f"  {o.get('key', str(i + 1))}. {o.get('label', '')}" for i, o in enumerate(opts))]
        # 用分支选项覆盖奖励（顶层 reward 为 0 时以选项为准）
        lines.append(f"  📖 {chosen.get('text', '')}")
        sqd = {**sqd,
               "reward_exp": chosen.get("reward_exp", sqd.get("reward_exp", 0)),
               "reward_gold": chosen.get("reward_gold", sqd.get("reward_gold", 0)),
               "reward_item": chosen.get("reward_item", sqd.get("reward_item"))}
        # v124 分支 flag：写入 giver NPC 的 flag 桶（称号/后续任务判定用）
        _cf = chosen.get("flag")
        if _cf:
            db.set_talk_flag(group_id, qq_id, sqd.get("giver", ""), _cf)
    # 收集类：扣除材料
    if obj.get("collect"):
        need = _OBJECTIVES.need_of(obj, "collect")  # v125.1 P2：s64 等 collect_count 无 count 不再 KeyError
        for _ in range(need):
            db.remove_item(group_id, qq_id, _ckey)
        # v126.2：鱼获个体属性在 item_data.tags，remove_item 自动截断，无需额外同步
    # v124 交付剧情文本（无分支时）
    dt = sqd.get("deliver_text")
    if dt and not br:
        lines.append(f"  📖 {dt}")
    # v124.3：奖励统一走 _grant_quest_rewards（exp/gold/升级 + reward_item 全格式 +
    # reward_pet/reward_mount/unlock_class）——逻辑与支线原实现完全一致（列表随机 /
    # eq: 名册 / items→materials 顺序），返回结算后 player 供下方 _rule_fire 使用
    player = grant_quest_rewards(group_id, qq_id, sqd, lines)
    # v95.12：交付后条目标记 done（无 completed_side 列），防止 _offer_side_quests 自动重接
    # 子账本交付 = 条目置**最小终态一格**（引擎 `deliver`；口径分歧①：不追加历史）
    quests = _lane_log(quests).deliver(lane="side", key=sid)
    db.save_quests(group_id, qq_id, quests)
    # v104 M20：行会委托每日（complete_side）——支线交付完成 +1，达标发奖
    _bump_daily_progress(group_id, qq_id, "complete_side", lines)
    lines.append(f"✅ 【支线完成】『{sqd['name']}』！")
    lines.append(f"  奖励：经验 +{sqd['reward_exp']} 金币 +{sqd['reward_gold']}")
    rep_line = quest_reputation(group_id, qq_id, sqd["giver"])
    if rep_line:
        lines.append(f"  {rep_line}")
    # v97.5 行为彩蛋规则：任务交付后
    _rule_txt = _rule_fire("quest_deliver", group_id, qq_id, player,
                           _cs.MAP_BY_ID.get(player.get("cur_map"), {}))
    if _rule_txt:
        lines.append(f"  {_rule_txt}")
    return lines

def talk_quest_progress(group_id, qq_id, npc_id) -> list:
    """v95.11：talk 型主线与目标 NPC 对话即达成（active 空进度遗留态 → ready）。
    覆盖 v95.9 对话化之前接取、或接取瞬间未置 ready 的存量档，返回通知行。
    v105 P0/P2：collect 型主线对话时实时数背包（材料足够 → ready）；
    explore 型主线已在目标地图 → ready（免出图重进）。"""
    quests = db.get_quests(group_id, qq_id)
    if _log(quests).status != _QL_STATES["live"]:
        return []
    mid = _log(quests).current
    if not mid:
        return []
    mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mid), None)
    if not mq:
        return []
    obj = mq.get("objective", {})
    if _OBJECTIVES.hits(obj, {"kind": "talk", "talk": npc_id}):
        quests = _log(quests).accept(lane=None, key=mid, status="ready",
                                     progress={npc_id: 1})
        db.save_quests(group_id, qq_id, quests)
        return ["✨ 交谈完成！再与这位 NPC 对话即可交付任务。"]
    if obj.get("collect") and mq.get("giver") == npc_id:
        need = _need_main_collect(obj)
        if db.count_item(group_id, qq_id, obj["collect"]) >= need:
            quests = _log(quests).accept(lane=None, key=mid, status="ready",
                                         progress={obj["collect"]: need})
            db.save_quests(group_id, qq_id, quests)
            return [f"✨ 材料已齐（{obj['collect']} ×{need}）！再与这位 NPC 对话即可交付任务。"]
    if obj.get("explore") and mq.get("giver") == npc_id:
        player = db.get_player(group_id, qq_id)
        if player.get("cur_map") == obj["explore"]:
            quests = _log(quests).accept(lane=None, key=mid, status="ready",
                                         progress={obj["explore"]: 1})
            db.save_quests(group_id, qq_id, quests)
            return ["✨ 目标地点已到达！再与这位 NPC 对话即可交付任务。"]
    return []

# ---------------- v95.23 职业就职 / 导师转职 ----------------

def update_use_quests(group_id, qq_id, item_name):
    """v124 use 目标支线：使用指定物品后支线置 ready（如 递麦酒/用月鳞/交信物）。
    v124.2 防跨图白嫖：objective.map 或任务自身 map 配置时，须玩家当前地图一致才推进；
    objective 无 map 且任务无 map 的保持原行为（不校验直接推进）。"""
    if not item_name:
        return ""
    quests = db.get_quests(group_id, qq_id)
    _lane = _lane_log(quests)
    lines = []
    changed = False
    for sid, sq in list(_lane.lane("side").items()):
        if _lane.status_of("side", sid) != _QL_STATES["live"]:
            continue
        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
        if not sqd:
            continue
        obj = sqd.get("objective") or {}
        if obj.get("use") and obj["use"] == item_name:
            _need_map = obj.get("map") or sqd.get("map")
            if _need_map:
                _pm = db.get_player(group_id, qq_id) or {}
                if _pm.get("cur_map") != _need_map:
                    continue
            # 进度补丁由注册表给（`use` 型 fold = 覆盖成 `{"use": 物品名}`）
            quests = _lane.accept(lane="side", key=sid, status="ready",
                                  progress=_OBJECTIVES.fold(
                                      obj, {}, {"kind": "use", "use": item_name}))
            _lane = _lane_log(quests)
            changed = True
            giver = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}
            lines.append(f"✨ 『{sqd['name']}』目标达成！回去找 {giver.get('name', '发布人')} 交付吧～")
    if changed:
        db.save_quests(group_id, qq_id, quests)
    return "\n".join(lines)

def branch_wait_sid(group_id, qq_id):
    """v124：查找处于分支等待状态的支线 sid（ready + branch_wait）。"""
    quests = db.get_quests(group_id, qq_id)
    for sid, sq in (quests.get("side") or {}).items():
        if sq.get("status") == "ready" and sq.get("branch_wait"):
            return sid
    return None

def quest_kill_progress(group_id, qq_id, monster):
    """战斗后更新任务进度（主线/支线/每日击杀型），返回通知行——combat._update_quests 击杀段原样随迁。

    v181 P4-2：combat._update_quests 的 quest 段（主线/支线 kill/kill_any + 每日 kill_any/elite/boss）
    收敛本函数，combat 只留调用壳；周常悬赏 weekly_bump_kill 属 weekly 域不随迁（调用方自行追加）。
    匹配规则 v105 M19 P2 前缀精确（== 或 「目标·」开头）；每日结算走 services.quests.settle_daily_quest
    （P4-1 试点已收敛单点）。kill_any 支线用 progress.any（v95.13 防卡死）。
    """
    lines = []
    quests = db.get_quests(group_id, qq_id)
    changed = False
    ev = _kill_event(monster)
    # 主线（仅处理已接且进行中的任务；击杀达到目标则变为可交状态）
    main_id = _log(quests).current
    if main_id:
        mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)
        if mq and _log(quests).status == _QL_STATES["live"]:
            prog = dict(quests.get("main_progress", {}))
            obj = mq["objective"]
            if obj.get("kill"):
                # 命中判定 + 进度补丁都由注册表给（`kill` 型 fold = `{目标名: 旧值 + 1}`）
                patch = _OBJECTIVES.fold(obj, prog, ev)
                if patch:
                    prog.update(patch)
                    quests = _log(quests).bump(patch, lane=None)
                    changed = True
                    if prog.get(obj["kill"], 0) >= _OBJECTIVES.need_of(obj, "kill"):
                        quests = _log(quests).set_status("ready", lane=None)
                        _g = _cq.NPCS.get(mq["giver"]) or _w.ALL_WILD.get(mq["giver"]) or {}
                        lines.append(f"📜 主线『{mq['name']}』目标达成！回去找 {_g.get('name', '？')} {deliver_hint(mq['giver'])}吧～")
                    else:
                        lines.append(f"📜 主线『{mq['name']}』：{prog[obj['kill']]}/{obj['count']}")
    # 每日
    # v94：先清跨天任务（daily 里 _date 不是今天 → 清空），避免旧任务残留
    if _expire_daily(quests):
        changed = True
    daily = dict(_log(quests).lane("daily"))
    # v125.1 P0 修复：跳过全部元数据键（_date/_completed/_repeat）——原只跳过 _date，
    # _completed(int)/_repeat(dict) 被 dq["objective"] 下标 → TypeError 每日首战必崩
    for dkey, dq in list(daily.items()):
        if dkey in DAILY_META_KEYS:  # 跨天/计数元数据，不是任务
            continue
        dobj = dq["objective"]
        prog = dq.get("progress", 0)
        # 命中判定走注册表（每日击杀型 3 键 = kill_any / kill_elite / kill_boss 的 match）
        if _OBJECTIVES.hits(dobj, ev):
            prog += 1
        dq["progress"] = prog
        changed = True
        if prog >= dobj.get("kill_any", dobj.get("kill_elite", dobj.get("kill_boss", 99))):
            # v125.1 P2：发奖结算统一走 settle_daily_quest（与 world 非击杀 bump 同单点；
            # 击杀型每日在此接线，防刷上限/衰减对击杀型同样生效）
            settle_daily_quest(group_id, qq_id, daily, dq, lines)
            del daily[dkey]
    # 无条件写回：即使全部完成（daily 为空）也要清空 quests，否则任务残留会无限重复发奖励
    quests["daily"] = daily
    # 支线（击杀型）
    _lane = _lane_log(quests)
    for sid, sq in list(_lane.lane("side").items()):
        if _lane.status_of("side", sid) != _QL_STATES["live"]:
            continue
        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)
        if not sqd:
            continue
        obj = sqd["objective"]
        prog = dict(sq.get("progress", {}))
        # v95.13 修复：kill_any 支线（护送商货等）此前无计数分支，任务永久卡死
        # v105 M19 P2 / v104 M20 P2：击杀进度键统一记 obj['kill']，名字前缀精确匹配
        patch = _OBJECTIVES.fold(obj, prog, ev)
        if not patch:
            continue
        prog.update(patch)
        quests = _lane.bump(patch, lane="side", key=sid)
        _lane = _lane_log(quests)
        changed = True
        _key = next(iter(patch))
        _need = _OBJECTIVES.need_of(obj, _OBJECTIVES.hits(obj, ev)[0])
        if prog.get(_key, 0) >= _need:
            quests = _lane.set_status("ready", lane="side", key=sid)
            _lane = _lane_log(quests)
            _g = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}
            lines.append(f"📜 支线『{sqd['name']}』目标达成！回去找 {_g.get('name', '？')} {deliver_hint(sqd['giver'])}吧～")
        else:
            lines.append(f"📜 支线『{sqd['name']}』：{prog[_key]}/{_need}")
    if changed:
        db.save_quests(group_id, qq_id, quests)
    return lines
