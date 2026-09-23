# -*- coding: utf-8 -*-
"""奥兰迪亚·余烬纪年内容包 —— world 命令域实现（B9 线2，2026-09-13）。

真源：游戏仓 `game/commands/world.py`（4452 行）的 `class WorldCmds`。本模块 = 那个类的
**实现本体**（103 个方法逐字搬成模块级函数，只去 4 空格缩进）。宿主 `game/commands/world.py`
现在只剩：命令注册（@declared 装饰器）+ 取玩家 + 一行转发调包 + 渲染（`quest_view` 因一条
**宿主源码级门禁**留在那边，见下；`_instance_gate_block` 已随 P5E「壳去逻辑」批搬回本模块）。

搬的边界
--------
* **搬**：除下面一个之外的全部方法（共 3869 行）。
* **不搬（留宿主，理由 = 宿主源码级门禁，不是偷懒）**：
  - `quest_view` —— `tests/test_texts_table.py:81 WIRED` 对「声明 ↔ 调用点」做 **AST 扫描**，
    每日任务域 `daily.*` 7 条文案的调用点必须在宿主 world.py 里；连带宿主模块级依赖
    `T` / `_OBJ_PROGRESS_LINES` / `_kill_prog_count` / `DAILY_LIMIT` / `_DAILY_META_KEYS` /
    `daily_need` 也留宿主。
* **P5E「壳去逻辑」批搬回（2026-09-15）**：`_instance_gate_block`（副本图门禁：取数 + 组装
  `ctx` → `walk_admission`）与 `_HURRY_ALIAS`（赶路别名表，原宿主类属性）从宿主 `host/shell.py`
  搬回本模块。`tests/test_v185_instance_admission.py`（t7_wiring）要的
  `instance_gate.walk_admission` 调用点现在是本模块里的**真调用**（不再靠注释凑字符串）。

正文改动面（**只有两类**，差异面自检见 `overnight/b9_l2_check.py`）
----------------------------------------------------------------
1. 函数体内**延迟 import 的宿主模块** → 同位置换成**包内直取**（B2-C4 收口；见下表）
   `from ..services.travel import level_warn` → `content/travel.py`（同对象）
2. 命令方法开头那两行「取 (group_id, qq_id) + `self._player(...)`」→ 提到宿主薄壳当参数传进来
   （共 31 处）：宿主薄壳因此真的在做「取玩家」。

宿主面取件口（B2-C4 收口后）
----------------------------
| 真源写法 | 包内替身 | 证据 |
|---|---|---|
| `from .. import content as C` —— 数据名读点 | **包内门面**（B14-2 L2 段，31 名） | 门禁 `overnight/_b14_2_L2.json` |
| 宿主聚合层上的全部**函数名**（小写名） | **包内直取**：`_pois` / `_maps` / `_wild` / `_dlg` / `_timed` / `_tw` / `_worlds` / `_portals` / `_fac` / `_idx` / `_ach` | `out/evidence/identity_map.txt`（逐名「包内同一对象」） |
| `from .. import db`（`db.xxx` 133 处） | 包内 `content/_pkgref.DB`（B1 口径） | 同上 |
| 函数内 `from ..services.battle_bridge import …` | 包内 `content/bridge.py`（同对象） | `probe_c4_faces.py` |
| `from .talk_actions import ACTIONS, check_action_keys` | `ACTIONS` = **包内** `content/talk_actions.py`；`check_action_keys` = **冻结注入名**（宿主独有，留宿主读点） | 接口表第 4 行 |
| 掉落族四个函数名（`build_monster_group` / `generate_roster_equip` 等） | `_drops()`：**包内直取** `content/drops.py`（接口表第 5 行冻结落点，B2-C2 已落地）；宿主 `game.core.drops` 为同对象过渡保险 | 接口表第 5 行 + `identity_map.txt` |
| 兼容面两个旧替身口名（`content/cmds_world.py:49` 的 F401 再导出） | 仅保留**名字**（值 = None，零调用点），使该 import 不炸 | 见下文 ⚠️ |

⚠️ **残留的门禁命中（2 类，逐条说明）**：
* `content/cmds_world.py:49` 的 F401 再导出（**包内不属于 B2-C4 文件集**，不就地改）——
  本文件为此保留两个**旧替身口名**（值 = None，全仓零调用点）：删掉它们本文件的兼容别名段即可整体删除。
  收口建议：`content/cmds_world.py:49` 去掉那两个名字（**一行**）。
* 包内 `content/index.py` / `content/maps.py` 各有一个**惰性宿主模块工厂函数**（名字里的
  `host` 片段撞上本批 grep）= **注入面提供者**（不是读点）：5 个宿主薄壳按名调用它
  （`game/core/{index,maps,mounts,factions,exploration,position,pets}.py`）
  ⇒ 宿主侧一字节不动的前提下**不能删**；它是 B1 批遗留（B1 判据也列了这个名）。
  收口建议：包内改名 + 波2 宿主 5 处改口（一行一处）。

包内直取（**不是**宿主）：`IR`（`content/flow/instance_run.py`，逐字端口）、`TIER_GROWTH`
（`content/tables.py`）、`player_final_stats`（`content/panel.py`）、`skill_info`（`content/skills.py`）、
`formation_view`/`alive_units`（引擎 `ext_combat.formation`）。
"""
from __future__ import annotations

import json
import os
import random
import re
import time

from ext_dialogue.dialogue import Cursor
from ext_combat.formation import alive_units, formation_view
from ext_social.presence import Lookup, Presence, minutes_left
from saintess_engine.records import records_from_domain   # D8：包内域读口（fail-closed 声明派生）

from . import catalog_core as _cat_core
from . import catalog_items as _cat_items
from . import catalog_life as _cat_life
from . import catalog_quests as _cat_quests
from . import catalog_space as _cat_space
# ★ W4（2026-09-14）：残余 9 名数据读点切包内 —— 7 名走 catalog_b143，PERIOD_CN / ALL_WILD 走读口
from . import catalog_b143 as _cat_b143
# ★ B16-W11b（2026-09-14）：势力阵营常量组（真源 `game/data/factions.py`；宿主聚合层未导出）→ 包内门面
from .catalog_rules import (FACTION_SHOP, FACTION_CAMPS, FACTION_CAMP_OPEN_LV, FACTION_CAMP_SWITCH_COOLDOWN,
                            FACTION_CAMP_DAILY_TASKS, FACTION_CAMP_DAILY_LIMIT, FACTION_CAMP_SHOP)
from . import wild as _wild
from . import texts as _T      # ★ C 档 18a（2026-09-18）：文案表读口（本文件首次接入）
from .flow import instance_gate      # 副本图门禁准入链（`_instance_gate_block` 的判定本体）
from .flow import instance_run as IR
from .panel import player_final_stats
from .skills import skill_info
from .tables import TIER_GROWTH
from .time_weather import PERIOD_CN
from .prof_config import gather_map_min_lv  # ★ B15b：宿主函数进包（原 `C.gather_map_min_lv`，宿主已无对象）


# ============================================================
# ① 宿主面取件口（B2-C4 收口）—— 本文件 B2 读点全部包内直取；只剩两件：
#    · `_drops()`：`core.drops` 面（B2-C2 线待落 `content/drops.py`，未落则回退宿主同对象）
#    · 兼容面两个旧替身口名（`content/cmds_world.py:49` 的 F401 再导出用，**零调用点**，见头注 ⚠️）
# ============================================================
from ._hostref import drops_module  # 宿主取件样板单源（P0-3/P0-5）
from saintess_engine.wire import slot as _slot
_WIRE, bind_host = _slot()


_drops = drops_module("world_cmds")


def _check_action_keys(action):
    """对话动作未知键防御（真源 `from .talk_actions import check_action_keys`）——**宿主独有**。

    接口表第 4 行冻结：`check_action_keys` 留宿主（读宿主日志层 + `GWEN_*` 环境变量 = 接人性）。
    取件 = 注入（宿主壳 `game/commands/talk_actions.py` import 期，波2）→ `sys.modules` 过渡兜底
    → **同改造前的 importlib 兜底**（旧替身就是注入→sys.modules→importlib；宿主未加载的测试/工具
    路径靠它，见 `tests/test_numeric_reward_unify.py`）→ 抛（不静默空跑）。
    """
    fn = _WIRE.handles().get("check_action_keys")
    if fn is None:
        # ★ P5E-DELETE（2026-09-15，删壳批）：兜底原来按**旧宿主模块名**
        #   `game.commands.talk_actions` 取件 —— 删壳后该模块不复存在，本口在「未被注入」时
        #   必抛（实测 13 个测试文件红）。该防御的**真源已在包内**：`content/talk_actions.py`
        #   就是旧壳的逐字端口（动作注册表 `ACTIONS` 在本模块；`check_action_keys` 本批按
        #   同一段逻辑补回包内，见那边 docstring）。故兜底改为**包内真源**，
        #   与外层「包内直取」口径一致；仍保留 `_WIRE` 优先（宿主/测试可覆盖）。
        from .talk_actions import check_action_keys as fn      # noqa: PLC0415（同位置惰性取件）
    if fn is None:
        raise RuntimeError("world_cmds：check_action_keys 取不到（未注入且包内真源缺件）——拒绝静默空跑")
    return fn(action)


from ._pkgref import DB as db
from . import achievements as _ach       # 成就函数读点 → 包内直取（同对象）
from . import daily_events as _daily_events   # 动态读点 `today_map_event`（原 getattr 聚合层）
from . import dialogue as _dlg           # 对话树五名（get_dialogue/dialogue_node/node_text/visible_options/is_end）
from . import exploration as _exploration     # 动态读点 `exploration_record_visit`
from . import factions as _fac           # faction_reputation_tier
from . import index as _idx              # resolve / display
from . import maps as _maps              # subarea_links / map_entry_subarea / map_exit_subarea / map_center / map_route
from . import pois as _pois              # subarea_pois / subarea_props / prop_entry
from . import portals as _portals        # portal_cost
from . import texts as _texts           # 文案表（`_instance_gate_block` 给准入链换表）
from . import timed_events as _timed     # list_timed / get_timed
from . import time_weather as _tw        # current_period / time_weather_summary
from . import worlds as _worlds          # get_instance_world

# ★ B2-W2 已收口：`content/cmds_world.py:49` 的两个死 import 名已删，本段（C/宿主面取件 占位）随之删除。

# 真源宿主顶层 `from ..services.quests import DAILY_META_KEYS as _DAILY_META_KEYS`
from .profession_quests import DAILY_META_KEYS as _DAILY_META_KEYS
from ._domainio import read_domain as _read_domain

# v104 M23 许愿井彩蛋概率（真源 world.py:47；唯一常量定义点搬到本模块，宿主薄壳再导出同名）
WISH_WELL_EGG_CHANCE = 0.05


# ============================================================
# ③ 引擎形状装配（U1-I4 L5）—— 多表首命中 / 在场清单编号 / 展示分钟 / 会话游标
# ------------------------------------------------------------
# 本模块的四类「手算 / 多份同义实现」换成 `saintess_engine` 形状；判据实现与全部取值
# 仍在本模块与 `content/wild.py`：
#   · `Lookup`       —— **真值链**多表首命中（与 `A.get(k) or B.get(k)` 同口径，空 mapping 穿透）
#   · `Presence`     —— `slots`：静态清单在前、限时项**续号**；`slot_at`：1-based 取用
#   · `minutes_left` —— `max(1, ceil(remain/60))`（限时展示口径，下限 1）
#   · `Cursor`       —— 会话游标**值**（「跟谁 + 在哪」两个不透明串）
# ⚠ 存档面零改动：游标**存储**仍在 `content/persistence/world.py`（键与 JSON 文本一字不动）。
# ⚠ 三份 NPC 列表实现的**成员集合分歧**（口径分歧 ①）逐字保留 —— `Lookup` 只替「查表」，
#   不替「HIDDEN 豁免 / 地图级短路 / 一律过滤」这三条各自的判据。
# ============================================================
_LOOKUP_TOWN = Lookup(_cat_quests.NPCS)                              # 城镇单表（`_current_npcs`）
_LOOKUP = Lookup(_cat_quests.NPCS, _wild.ALL_WILD)                   # 两表真值链（会话取 NPC）
_LOOKUP_ALL = Lookup(_cat_quests.NPCS, _wild.ALL_WILD, _cat_quests.HIDDEN_NPCS)   # 交付解析
_LOOKUP_HIDDEN = Lookup(_cat_quests.HIDDEN_NPCS)                     # 副本层单表
_LOOKUP_HIDDEN_FIRST = Lookup(_cat_quests.HIDDEN_NPCS, _cat_quests.NPCS)   # 地图面板：HIDDEN 优先
_LOOKUP_WILD = Lookup(_wild.ALL_WILD)                                # 野外/隐藏单表
#: 在场清单（本模块只借它的 `slots` / `slot_at` 两个**纯编号**口；判据仍在 `wild.py`）
_PRESENCE = Presence(_LOOKUP_TOWN,
                     keep=lambda row_id, row: True,
                     place_of=lambda row_id, row, day: None)
#: 对话形状的**注入面**（L3 适配层 `content/dialogue.py` 建的 `Dialogue`；本模块只借不改）
_TALK = _dlg._CFG
_TALK_SUBJECT_KEY = "npc"       # 存档 schema 字段名（`Cursor` 的**注入键名**，schema 不动）
_TALK_NODE_KEY = "node"


# ============================================================
# ② 包内域读口 —— 方碑表（域 `portals`，导出器 `scripts/export_domains/b9_quests_travel.py`
#    → `content/data/portals.json`；**域归属 = L5 线**，本线只做**消费方**）
# ------------------------------------------------------------
# 真源 `game/data/portals.py:4 PORTALS`（11 条 {地图id: {name, icon}}）—— 与宿主聚合层
# `C.PORTALS` **同形**（逐键 deep-equal 探针见 `overnight/b9_l2_verify.py`【D】）；
# 正文里原 `C.PORTALS`（13 处）改读本读口（B9 线2）；B14 第二段 L2 另把 31 个数据名读点
# 切到包内门面 `catalog_{core,items,life,quests,space}`（见头注），正文残余 `C.<名>` 只剩
# 下节缺口那 9 名常量表 + `C.` 上的函数。
# ============================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)                          # <pkg>（D8 域声明派生口用）


PORTALS = _read_domain("portals")


# ============================================================
# 实现本体（103 个函数，逐字搬自宿主 `class WorldCmds`）
# ============================================================


def _map_facilities(self, cur_map: dict, player: dict = None, sa_id_override: str = None) -> list:
    """当前地图功能性设施清单（商店/旅店/铁匠/方碑/垂钓/篝火/矿脉/采集）。

    v87.13 与 _map_scene 拆分：设施 = 干事的功能入口；场景 = 氛围景物。
    v87.13b sa_id_override：移动到达展示时目标子区域还没写进 player，显式传入落点子区域 id。
    """
    lines = []
    mid = cur_map.get("id", "")
    portals = db.get_portals(player["qq_id"]) if player else []
    # v86 子区域：设施/NPC 按当前子区域过滤（无子区域/无标记则地图级）
    sa_obj = None
    sa_id = sa_id_override or (player or {}).get("cur_subarea") or ""
    for _sa in (cur_map.get("subareas") or []):
        if _sa["id"] == sa_id:
            sa_obj = _sa
            break
    sa_shop = sa_obj.get("shop") if sa_obj else None
    sa_healer = sa_obj.get("healer") if sa_obj else None
    # 设施
    if (sa_shop is not None and sa_shop) or (sa_shop is None and cur_map.get("shop")):
        lines.append(_T.static("fac.shop"))
    if (sa_healer is not None and sa_healer) or (sa_healer is None and cur_map.get("healer")):
        lines.append(_T.static("fac.inn"))
    if mid in _cat_items.ENHANCE_SMITH_MAPS:
        _sa_name = sa_obj.get("name", "") if sa_obj else ""
        _sa_funcs = (sa_obj.get("funcs") or []) if sa_obj else []
        # O94 修复：与 base._at_smith 同源——鹿角淬火坊(white_deer_8)补入强化可用区域，
        # 地图设施清单同步显示铁匠铺入口（否则设施显示与『强化』可用性矛盾）
        _smith = "craft" in _sa_funcs or _cat_life.SUBAREA_KIND.get(sa_id) in ("smith", "enhance")
        if _smith:
            lines.append(_T.static("fac.smith"))
    # 旅者方碑（只在中心广场/首个子区域提示）
    if mid in PORTALS:
        p = PORTALS[mid]
        if sa_obj is None or sa_obj is cur_map.get("subareas", [None])[0]:
            if mid in portals:
                lines.append(_T.text("fac.portal_on", icon=p['icon'], name=p['name']))
            else:
                lines.append(_T.text("fac.portal_off", icon=p['icon'], name=p['name']))
    # F2 副本入口设施化：funcs 含 instance 的子区域 = 副本入口设施（消费 F1 标记）
    if sa_obj and "instance" in (sa_obj.get("funcs") or []):
        for _ik, _iv in _cat_space.INSTANCES.items():
            _ie = _iv.get("entry") or {}
            if _ie.get("map") == mid and _ie.get("subarea") == sa_id:
                lines.append(_T.text("fac.instance", name=_iv.get('name', '副本'), cmd=_iv.get('name', '')))
                break
    # 自然互动（9.3：垂钓点显示特色描述；v87.17 子区域绑定：不在对应子区域不显示）
    if mid in _cat_life.FISHING_SPOTS:
        _fi = _cat_life.FISHING_SPOTS[mid]
        _want_sa = _fi.get("subarea", "") if isinstance(_fi, dict) else ""
        if not (_want_sa and (sa_obj is None or sa_obj.get("id") != _want_sa)):
            _fname = _fi["name"] if isinstance(_fi, dict) else _fi
            _fneed = _fi.get("min_lv", 1) if isinstance(_fi, dict) else 1
            _flv = db.get_prof_level(player.get("group_id", "g"), player["qq_id"], "fishing") if player else 1
            _lock = " 🔒" if _flv < _fneed else ""
            _fdesc = _fi.get("desc", "") if isinstance(_fi, dict) else ""
            lines.append(_T.text("fac.fishing", name=_fname, lv=_fneed, mark=_lock,
                             tail=(' · ' + _fdesc) if _fdesc else ''))
    if mid in _cat_life.CAMP_SPOTS:
        _cp = _cat_life.CAMP_SPOTS[mid]
        _cp_sa = _cp.get("subarea", "") if isinstance(_cp, dict) else ""
        if not (_cp_sa and (sa_obj is None or sa_obj.get("id") != _cp_sa)):
            _cp_name = _cp.get("name", "营地") if isinstance(_cp, dict) else str(_cp)
            lines.append(_T.text("fac.camp", name=_cp_name))
    # v105R3 M14 P3-3：城镇地图不显示矿脉（『挖掘』已被城镇拦截，防"⛏️ 矿脉"与"城镇安全区"观感冲突）
    # v173：MINE_SPOTS dict 化（name/min_lv），显示同垂钓点——副业等级不足显示 🔒
    if mid in _cat_life.MINE_SPOTS and cur_map.get("type") != "城镇区域":
        _mi = _cat_life.MINE_SPOTS[mid]
        _mi_sa = _mi.get("subarea", "") if isinstance(_mi, dict) else ""
        if not (_mi_sa and (sa_obj is None or sa_obj.get("id") != _mi_sa)):
            _mi_name = _mi.get("name", "矿脉") if isinstance(_mi, dict) else str(_mi)
            _mneed = int(_mi.get("min_lv", 1)) if isinstance(_mi, dict) else 1
            _mlv = db.get_prof_level(player.get("group_id", "g"), player["qq_id"], "mining") if player else 1
            _lock = " 🔒" if _mlv < _mneed else ""
            lines.append(_T.text("fac.mine", name=_mi_name, lv=_mneed, mark=_lock))
    # v173：野地采集也按副业等级分档显示（同垂钓/矿脉）——等级不足显示 🔒
    if cur_map.get("type") == "野外" and mid not in _cat_life.CAMP_SPOTS:
        _glv = db.get_prof_level(player.get("group_id", "g"), player["qq_id"], "gather") if player else 1
        _gneed = int(gather_map_min_lv(int(cur_map.get("lv") or 0)))
        _lock = " 🔒" if _glv < _gneed else ""
        lines.append(_T.text("fac.gather", lv=_gneed, mark=_lock))
    return lines


def _map_scene(self, cur_map: dict, player: dict = None, sa_id_override: str = None) -> tuple:
    """当前子区域场景元素清单（POI 探索点 + PROPS 场景元素 + 副本内联 POI）。

    v87.13 从 _map_interactions 拆出：氛围/景物类，标题用「✨ 场景」。
    v87.13b sa_id_override：移动到达展示时目标子区域还没写进 player，显式传入落点子区域 id。
    v132 返回拆分：("🔎 可探索触发" POI 行列表, "✨ 可交互场景" PROPS 行列表)——
    鱼鱼拍板新排版：探索触发与直接交互分两区展示（城镇版/野外版同一套区块）。
    v137 副本地图化：副本内（玩家开本且当前房间）时，经 rooms[cur_room].pois_left
    过滤子区域挂载 POI——探索完即空的资源池语义；已消费的 POI 不再显示。
    """
    poi_lines, prop_lines = [], []
    mid = cur_map.get("id", "")
    sa_id = sa_id_override or (player or {}).get("cur_subarea") or ""
    # v87 02 章 7.6：探索点 POI 显示（子区域挂载）
    if player:
        poi_ids = _pois.subarea_pois(mid, sa_id)
        # v137 副本地图化：副本内 POI 显示受 rooms[cur_room].pois_left 过滤（资源池语义）
        _inst_row = None
        try:
            _inst_row = self._instance_battle_for(player.get("group_id", "g"), player.get("qq_id"))
        except Exception:
            _inst_row = None
        if _inst_row and (_inst_row["state"].get("mode") == "map" or _inst_row["state"].get("rooms")):
            _st = _inst_row["state"]
            _rooms = _st.get("rooms") or {}
            _rkey = sa_id or (player or {}).get("cur_subarea") or ""
            _rstate = _rooms.get(_rkey) or {}
            # v185：剩余池读点收口 instance_run；缺失（该房间无资源池）仍不过滤
            # —— rooms_progress 视图无法区分「池不存在」与「池为空」，故保留存在性判定
            if _rstate.get("pois_left") is not None:
                poi_ids = [pid for pid in poi_ids if IR.poi_left(_st, _rkey, pid)]
        for _pid in poi_ids:
            _p = _cat_b143.POIS.get(_pid)
            if _p:
                # v137 副本 POI（dungeon_pois）无 icon 字段——用 type 映射或 ❓ 兜底
                _icon = _p.get("icon")
                if not _icon:
                    _icon = {"chest": "📦", "campfire": "🔥", "rune_stone": "🗿",
                             "mechanism": "⚙️", "trap": "⚠️", "supply": "🎒",
                             "corpse": "💀"}.get(_p.get("type"), "❓")
                poi_lines.append(_T.text("scene.explore", icon=_icon, name=_p['name']))
    # v87.9 场景元素 PROPS 显示（子区域挂载，直接交互）
    # v87.11 支持专属名：挂载条目可为 (prop_id, 专属名) 元组
    if player:
        prop_ids = _pois.subarea_props(mid, sa_id)
        for _entry in prop_ids:
            _ppid, _label = _pois.prop_entry(_entry)
            _pp = _cat_items.PROPS.get(_ppid)
            if _pp:
                _name = _label or _pp['name']
                prop_lines.append(_T.text("scene.prop", icon=_pp['icon'], name=_name, cmd=_name))
    # v87.2 副本地图化：内联 POI（副本层自带 pois → 直接显示，『调查 <名称>』互动）
    for _p in (cur_map.get("pois") or []):
        if isinstance(_p, dict) and _p.get("name"):
            poi_lines.append(_T.text("scene.poi", icon=_p.get('icon', '❓'), name=_p['name'], desc=_p.get('hint', ''),
                                 cmd=_p['name']))
    # v87.4 NPC 不再进场景（由地图面板「👥 这里的 NPC」统一显示，避免重复）
    return poi_lines, prop_lines


def _visible_sas(self, player: dict, cur_map: dict, group_id: str, qq_id: str) -> list:
    """v115 当前位置地图中**可见**的子区域列表（供面板/移动统一使用）——v181 P4-8 已下沉 travel.visible_sas。"""
    from .travel import visible_sas
    return visible_sas(player, cur_map, group_id, qq_id)


def _conn_target(conn) -> tuple:
    """解析可前往连接项 → (目标地图 dict, 指定子区域 id 或 None) ——v181 P4-8 已下沉 travel.conn_target。"""
    from .travel import conn_target
    return conn_target(conn)


def _conn_subarea_name(nm: dict, want_sa) -> str:
    """目标地图的落点子区域显示名(默认入口子区域，可指定) ——v181 P4-8 已下沉 travel.conn_subarea_name。"""
    from .travel import conn_subarea_name
    return conn_subarea_name(nm, want_sa)


def _home_map_id(self, qq_id):
    return f"home_{qq_id}"


async def deed_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    # v84 『地契 升级』→ 房屋升级
    raw_arg = self._strip_cmd(event, "地契").strip()
    if raw_arg.startswith("升级"):
        async for _r in self._deed_upgrade(event, group_id, qq_id, player):
            yield _r
        return
    deed = player.get("deed", "") or ""
    lines = [_T.static("house.head"), "━━━━━━━━━━━━"]
    if deed and deed in _cat_life.PROPERTIES:
        prop = _cat_life.PROPERTIES[deed]
        dlv = int(player.get("deed_lv", 1) or 1)
        hl = _cat_life.HOUSE_LEVELS.get(dlv, _cat_life.HOUSE_LEVELS[1])
        lines.append(_T.text("house.mine", name=prop['name'],
                         map=_cat_space.MAP_BY_ID.get(prop['map'], {}).get('name', '？')))
        lines.append(_T.text("house.row", name=hl['name'], lv=dlv, cap=hl['storage'], heal=int(hl['heal_pct'] * 100)))
        if dlv < _cat_life.HOUSE_MAX_LEVEL:
            nxt = _cat_life.HOUSE_LEVELS[dlv + 1]
            cost = _T.text("house.upgrade_cost", gold=nxt['upgrade_cost']['gold']) + " + ".join(f"{_idx.display('materials', m)}×{c}" for m, c in nxt['upgrade_cost']['mats'].items())
            lines.append(_T.text("house.upgrade_row", lv=dlv + 1, name=nxt['name'], need=cost))
        else:
            lines.append(_T.static("house.max"))
        lines.append(_T.text("house.sell_hint", pct=int(_cat_life.HOUSE_REFUND.get(dlv, 0.5) * 100)))
    else:
        lines.append(_T.static("house.none_head"))
        for i, (pid, prop) in enumerate(_cat_life.PROPERTIES.items(), 1):
            mname = _cat_space.MAP_BY_ID.get(prop["map"], {}).get("name", "？")
            lines.append(_T.text("house.for_sale_row", idx=i, name=prop['name'], price=prop['price'], map=mname))
            lines.append(f"     {prop['desc']}")
        lines.append(self._tip("house"))
    yield event.plain_result("\n".join(lines))


async def deed_buy(self, event: AstrMessageEvent, group_id, qq_id, player):
    if player.get("deed"):
        yield event.plain_result(_T.static("house.already"))
        return
    raw = self._strip_cmd(event, "买房").strip()
    if not raw.isdigit():
        yield event.plain_result(_T.static("house.buy_usage"))
        return
    idx = int(raw)
    props = list(_cat_life.PROPERTIES.items())
    if idx < 1 or idx > len(props):
        yield event.plain_result(_T.text("house.buy_no_idx", idx=idx, total=len(props)))
        return
    pid, prop = props[idx - 1]
    price = prop["price"]
    if player["gold"] < price:
        yield event.plain_result(_T.text("house.buy_gold_short", name=prop['name'], price=price, have=player['gold']))
        return
    # v104 M09 P1 修复：房产全服唯一·先到先得（25 章承诺）——买时登记房主，他人已持有则拦截
    _owner = db.get_event_state(f"deed_owner_{pid}")
    if _owner and str(_owner) != str(qq_id):
        yield event.plain_result(_T.text("house.buy_taken", name=prop['name']))
        return
    db.update_player(group_id, qq_id, gold=player["gold"] - price, deed=pid)
    db.set_event_state(f"deed_owner_{pid}", str(qq_id))  # v104 M09 P1：登记房主（卖房时释放）
    yield event.plain_result(
        _T.text("house.buy_ok", name=prop['name'], price=price)
    )


async def deed_sell(self, event: AstrMessageEvent, group_id, qq_id, player):
    deed = player.get("deed", "") or ""
    if not deed or deed not in _cat_life.PROPERTIES:
        yield event.plain_result(_T.static("house.sell_none"))
        return
    prop = _cat_life.PROPERTIES[deed]
    dlv = int(player.get("deed_lv", 1) or 1)
    refund_pct = _cat_life.HOUSE_REFUND.get(dlv, 0.5)
    refund = int(prop["price"] * refund_pct)
    db.update_player(group_id, qq_id, gold=player["gold"] + refund, deed="", deed_lv=1)
    db.set_event_state(f"deed_owner_{deed}", "")  # v104 M09 P1：卖房释放产权（先到先得）
    yield event.plain_result(_T.text("house.sell_ok", name=prop['name'],
                                 lv_name=_cat_life.HOUSE_LEVELS.get(dlv, _cat_life.HOUSE_LEVELS[1])['name'],
                                 lv=dlv, gold=refund, pct=int(refund_pct * 100)))


async def _deed_upgrade(self, event, group_id, qq_id, player):
    """v84 房屋升级(25 章三)：『地契 升级』消耗金币+材料升房屋等级"""
    deed = player.get("deed", "") or ""
    if not deed or deed not in _cat_life.PROPERTIES:
        yield event.plain_result(_T.static("house.up_none"))
        return
    dlv = int(player.get("deed_lv", 1) or 1)
    if dlv >= _cat_life.HOUSE_MAX_LEVEL:
        yield event.plain_result(_T.static("house.up_max"))
        return
    nxt = _cat_life.HOUSE_LEVELS[dlv + 1]
    cost = nxt["upgrade_cost"]
    # 金币检查
    if player["gold"] < cost["gold"]:
        yield event.plain_result(
            _T.text("house.up_gold_short", lv=dlv + 1, name=nxt['name'], gold=cost['gold'],
                have=player['gold']))
        return
    # 材料检查
    inv = db.get_inventory(group_id, qq_id)
    inv_map = {}
    for it in inv:
        nm = it["data"].get("name", "")
        inv_map[nm] = inv_map.get(nm, 0) + it.get("count", 1)
    for mid, need in cost["mats"].items():
        mname = _idx.display("materials", mid)
        if inv_map.get(mname, 0) < need:
            yield event.plain_result(
                _T.text("house.up_mat_short", lv=dlv + 1, name=nxt['name'], mat=mname, qty=need,
                    have=inv_map.get(mname, 0)))
            return
    # 扣材料 + 扣金币 + 升级
    for mid, need in cost["mats"].items():
        mname = _idx.display("materials", mid)
        for _ in range(need):
            found = next((it for it in inv if it["data"].get("name") == mname), None)
            if found:
                db.remove_item(group_id, qq_id, found["key"], 1)
                inv = db.get_inventory(group_id, qq_id)
    db.update_player(group_id, qq_id, gold=player["gold"] - cost["gold"], deed_lv=dlv + 1)
    hl = _cat_life.HOUSE_LEVELS[dlv + 1]
    yield event.plain_result(
        _T.text("house.up_ok", name=hl['name'], lv=dlv + 1, cap=hl['storage'],
            heal=int(hl['heal_pct'] * 100))
        + (_T.text("house.up_shop_slot", n=hl['stall_slots']) if hl["stall_slots"] else "")
        + (_T.text("house.up_max_tip", ) if dlv + 1 >= _cat_life.HOUSE_MAX_LEVEL else ""))


async def go_home(self, event: AstrMessageEvent, group_id, qq_id, player):
    if not (player.get("deed") or ""):
        yield event.plain_result(_T.static("house.home_none"))
        return
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("prof.fish_battle"))
        return
    # v84 回家恢复（按房屋等级 heal_pct）
    dlv = int(player.get("deed_lv", 1) or 1)
    hl = _cat_life.HOUSE_LEVELS.get(dlv, _cat_life.HOUSE_LEVELS[1])
    heal_pct = hl.get("heal_pct", 0.5)
    new_hp = max(player.get("hp", 0), int(player.get("max_hp", 1) * heal_pct))
    new_mp = max(player.get("mp", 0), int(player.get("max_mp", 1) * heal_pct))
    db.update_player(group_id, qq_id, cur_map=self._home_map_id(qq_id), cur_subarea="", hp=new_hp, mp=new_mp)
    yield event.plain_result(
        _T.text("house.home_ok", name=hl['name'], hp=new_hp, hp_max=player.get('max_hp', 1), mp=new_mp,
            mp_max=player.get('max_mp', 1)))


async def go_out(self, event: AstrMessageEvent, group_id, qq_id, player):
    cur = player.get("cur_map", "")
    if not cur.startswith("home_"):
        yield event.plain_result(_T.static("house.out_none"))
        return
    deed = player.get("deed", "") or ""
    prop = _cat_life.PROPERTIES.get(deed)
    target = prop["map"] if prop else _cat_core.START_MAP
    tgt_sas = _cat_space.MAP_BY_ID.get(target, {}).get("subareas") or []
    first_sa = tgt_sas[0] if tgt_sas else None
    db.update_player(group_id, qq_id, cur_map=target,
                     cur_subarea=first_sa["id"] if first_sa else "")
    yield event.plain_result(_T.text("house.out_ok", where=_cat_space.MAP_BY_ID.get(target, {}).get('name', '城镇')))


async def visit_home(self, event: AstrMessageEvent, group_id, qq_id, player):
    raw = self._strip_cmd(event, "拜访").strip()
    if not raw:
        yield event.plain_result(_T.static("house.visit_usage"))
        return
    target = db.find_player_by_name(raw)
    if not target:
        yield event.plain_result(_T.text("house.visit_no_player", name=raw))
        return
    tid = target["qq_id"]
    tp = db.get_player(group_id, tid)
    if not tp or not (tp.get("deed") or ""):
        yield event.plain_result(_T.text("house.visit_no_house", name=target['name']))
        return
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("prof.fish_battle"))
        return
    db.update_player(group_id, qq_id, cur_map=self._home_map_id(tid), cur_subarea="")
    yield event.plain_result(_T.text("house.visit_ok", name=target['name']))


def _home_storage_key(self, group_id, qq_id):
    return f"home_storage_{group_id}_{qq_id}"


def _home_storage_load(self, group_id, qq_id):
    raw = db.get_event_state(self._home_storage_key(group_id, qq_id))
    if not raw:
        return []
    try:
        lst = json.loads(raw)
        return lst if isinstance(lst, list) else []
    except (ValueError, TypeError):
        return []


def _home_storage_save(self, group_id, qq_id, lst):
    db.set_event_state(self._home_storage_key(group_id, qq_id), json.dumps(lst, ensure_ascii=False))


async def home_storage(self, event: AstrMessageEvent, group_id, qq_id, player):
    if not player.get("cur_map", "").startswith("home_"):
        yield event.plain_result(_T.static("house.storage_not_home"))
        return
    raw = self._strip_cmd(event, "仓库").strip()
    # 存：仓库 <物品名>
    if raw:
        # v84 仓库容量按房屋等级
        dlv = int(player.get("deed_lv", 1) or 1)
        hl = _cat_life.HOUSE_LEVELS.get(dlv, _cat_life.HOUSE_LEVELS[1])
        lst = self._home_storage_load(group_id, qq_id)
        if len(lst) >= hl["storage"]:
            yield event.plain_result(
                _T.text("house.storage_full", cur=len(lst), cap=hl['storage']))
            return
        inv = db.get_inventory(group_id, qq_id)
        found = next((it for it in inv if it["data"].get("name") == raw), None)
        if not found:
            yield event.plain_result(_T.text("house.storage_no_item", name=raw))
            return
        # F1 P0-2：原子存仓（同事务：读-判容量→append→写回→扣背包），
        # 并发双请求只有首个成功（另一请求事务内重读 storage 已满 → 提示仓库满）
        _ok, _n = db.home_storage_deposit_atomic(
            group_id, qq_id, self._home_storage_key(group_id, qq_id),
            found["key"], found["data"], hl["storage"],
        )
        if not _ok:
            yield event.plain_result(
                _T.text("house.storage_full", cur=_n, cap=hl['storage']))
            return
        yield event.plain_result(_T.text("house.storage_ok", name=found['data'].get('name', raw), cur=_n, cap=hl['storage']))
        return
    # 查看
    lst = self._home_storage_load(group_id, qq_id)
    if not lst:
        yield event.plain_result(_T.static("house.storage_empty"))
        return
    lines = [_T.static("house.storage_head"), "━━━━━━━━━━━━"]
    for i, it in enumerate(lst, 1):
        lines.append(f"{i:>2}. {it['data'].get('name', '?')} ×{it.get('count', 1)}")
    lines.append(self._tip("storage"))
    yield event.plain_result("\n".join(lines))


async def home_storage_take(self, event: AstrMessageEvent, group_id, qq_id, player):
    if not player.get("cur_map", "").startswith("home_"):
        yield event.plain_result(_T.static("house.storage_not_home"))
        return
    raw = self._strip_cmd(event, "取出").strip()
    if not raw.isdigit():
        yield event.plain_result(_T.static("house.take_usage"))
        return
    idx = int(raw)
    # F1 P0-2：原子取出（单事务：读→pop→写回→加背包），并发双请求只有首个取出
    _ok, it = db.home_storage_take_atomic(
        group_id, qq_id, self._home_storage_key(group_id, qq_id), idx
    )
    if not _ok:
        lst = self._home_storage_load(group_id, qq_id)
        yield event.plain_result(_T.text("house.take_no_idx", idx=idx, total=len(lst)))
        return
    yield event.plain_result(_T.text("house.take_ok", name=it['data'].get('name', '?')))


async def map_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    # O114 修复：副本战斗中『地图』与副本状态同步——显示"副本战斗中"而非旧地点
    # （与『角色』位置显示同源，playtest O114 洛洛实测）
    # v137 副本地图化：副本 map 模式（mode=map，无战斗）→ 显示副本地图视图
    _inst_row = self._instance_battle_for(group_id, qq_id)
    if _inst_row:
        _st = _inst_row["state"]
        if _st.get("mode") == "map" or (_st.get("rooms") and not (_st.get("enemies") or _st.get("boss"))):
            # 副本内地图模式：显示副本地图（_instance_map_view 是 InstanceCmds 方法，
            # 通过主实例调用——Main 继承所有 Mixin，self 即 Main）
            if hasattr(self, "_instance_map_view"):
                yield event.plain_result(self._instance_map_view(_st, group_id))
                return
        yield event.plain_result(
            _T.text("world.inst_battle", tail=self._tip('instance'))
        )
        return
    cur = player["cur_map"]
    # v68 家地图：home_{qq_id} 不在 MAPS，定制展示
    if cur.startswith("home_"):
        yield event.plain_result(self._home_view(group_id, qq_id, cur))
        return
    cur_map = _cat_space.MAP_BY_ID[cur]
    cur_sa = player.get("cur_subarea") or ""
    sa_now = ""
    if cur_sa:
        for _sa in (cur_map.get("subareas") or []):
            if _sa["id"] == cur_sa:
                sa_now = _sa["name"]
                break
    lines = self._map_nav_body(player, cur_map, cur_sa, group_id, qq_id)
    # v134.3 赶路模式精简：move_mode 开启时『地图』只显示可前往；带 hurry_type
    # 参数才显示对应类型区（与 _subarea_arrive 同规则，鱼鱼拍板）
    # v161 意见#69：赶路模式也显示完整地图（玩家要看全局再决定去哪），
    # 仅移动（非赶路）时精简显示可前往。赶路模式 = nav + 完整 blocks + 赶路提示。
    _mv = bool(db.get_event_state(f"move_mode:{qq_id}"))
    _ht = db.get_event_state(f"hurry_type:{qq_id}") or ""
    if _mv:
        # 完整地图块（与普通地图一致）+ 赶路类型区 + 提示
        blocks = self._map_blocks(player, cur_map, cur_sa, group_id, qq_id)
        if blocks and lines and lines[-1]:
            lines.append("")
        lines += blocks
        if _ht:
            sec = self._hurry_section(player, cur_map, cur_sa, group_id, qq_id, _ht)
            if sec:
                lines.append("")
                lines.extend(sec)
        lines.append("")
        lines.append(_T.static("world.hurry_tip"))
        yield event.plain_result("\n".join(lines))
        return
    # v134.2 排版修复：导航区与公共区块间补空行——_map_blocks 内部从空 lines 开始，
    # 首区块前无法感知调用方已拼好的 nav 内容（镇长办公处『✨ 可交互场景』紧贴『🧭 出城』）
    blocks = self._map_blocks(player, cur_map, cur_sa, group_id, qq_id)
    if blocks and lines and lines[-1]:
        lines.append("")
    lines += blocks
    yield event.plain_result("\n".join(lines))


async def region_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    _inst_row = self._instance_battle_for(group_id, qq_id)
    if _inst_row:
        yield event.plain_result(
            _T.text("world.inst_battle", tail=self._tip('instance'))
        )
        return
    cur = player.get("cur_map") or ""
    if cur.startswith("home_"):
        yield event.plain_result(self._home_view(group_id, qq_id, cur))
        return
    cur_map = _cat_space.MAP_BY_ID.get(cur)
    if cur_map is None:
        yield event.plain_result(_T.static("region.not_found"))
        return
    cur_sa = player.get("cur_subarea") or ""
    cur_name = cur_map.get("name") or cur
    # ▼ 标题 = 当前区域名 + (LV等级)——等级取当前子区域 lv，缺省回退地图 lv（与赶路/到达展示同口径）
    _lv = cur_map.get("lv") or 0
    for _sa in (cur_map.get("subareas") or []):
        if _sa.get("id") == cur_sa:
            if _sa.get("lv"):
                _lv = _sa["lv"]
            break
    title = f"▼{cur_name}"
    if _lv:
        title += f"(Lv.{_lv})"
    lines = [title]
    sas = cur_map.get("subareas") or []
    town = (cur_map.get("type") == _cat_core.MAP_TYPE_TOWN) or bool(cur_map.get("shop")) or bool(cur_map.get("healer"))
    # 本区域全部可达地点（数据=地图级城镇标记 + 子区域类型），顺序 = 数据顺序
    # v167.1：行加两格缩进（对齐地图面板『  ●1.』风格）；标题 Lv 格式 Lv.N
    for sa in sas:
        nm = sa.get("name") or sa.get("id") or "？"
        if sa.get("id") == cur_sa:
            lines.append(f"  ●{nm}")
        elif sa.get("type") == _cat_core.SUB_TYPE_TOWN or town:
            lines.append(f"  □{nm}")
        else:
            lines.append(f"  ○{nm}")
    # ⊕ 跨区域连接点（MAP_CONNECTIONS 当前图邻居；概览面板常显——副本 no_exit 除外）
    _dun = cur_map.get("dungeon") or {}
    neighbors = _cat_b143.MAP_CONNECTIONS.get(cur, [])
    if _dun.get("no_exit"):
        neighbors = []
    for conn in neighbors:
        _mid = conn[0] if isinstance(conn, tuple) else conn
        nm = _cat_space.MAP_BY_ID.get(_mid)
        if nm:
            _lock = _T.static("world.hidden") if nm.get("hidden") else ""
            _nlv = nm.get("lv")
            # v167.1：⊕ 跨区域连接带等级 Lv.N（对齐标题格式）
            _lvs = f"(Lv.{_nlv})" if _nlv else ""
            lines.append(f"  ⊕{nm.get('name') or _mid}{_lvs}{_lock}")
    yield event.plain_result("\n".join(lines))


def _map_blocks(self, player: dict, cur_map: dict, cur_sa: str,
                group_id=None, qq_id=None) -> list:
    """v132 从 map_view 抽取：位置导航之外的完整区块（今日奇遇/设施/场景/NPC/旅人/玩家/怪物/tip）。

    『地图』与 `_subarea_arrive`（到达视图）共用此方法 → 两处排版永不分裂
    （v101.25c 铁律：鱼鱼抓"前往不同区域提示模板不一样"）。
    cur_sa 传 sa id：到达视图时 player.cur_subarea 尚未更新为落点（v87.13b 同源处理）。
    """
    lines = []
    cur = cur_map.get("id", "")
    sas = cur_map.get("subareas") or []
    # v132.2 全地图紧凑模式（鱼鱼拍板：地图排版统一 ●横排模板，不再区分城镇/野外）
    _compact = True
    # v115 今日奇遇：面板底部一行（getattr 兜底，A/C 未就绪则不显示）
    _today_ev_fn = getattr(_daily_events, "today_map_event", None)
    if _today_ev_fn is not None:
        try:
            _ev = _today_ev_fn(cur)
            if _ev and _ev.get("name"):
                _ev_fx = (_ev.get("effects") or {})
                _ev_note = ""
                if _ev_fx.get("encounter_rate", 0) > 0:
                    _ev_note = _T.static("map.ev_note_encounter")
                elif _ev_fx.get("event_chance", 0) > 0:
                    _ev_note = _T.static("map.ev_note_event")
                elif _ev_fx.get("loot_mult", 1.0) > 1.0:
                    _ev_note = _T.text("map.ev_note_loot", mult=_ev_fx.get('loot_mult', 1.0))
                lines.append(_T.text("map.today_event", name=_ev['name'], desc=_ev.get('desc', ''), note=_ev_note))
        except Exception:
            pass
    # v87.4 区块间统一空行分隔（不再叠分隔线）
    if lines and lines[-1]:
        lines.append("")
    # 此地设施 + 场景（v87.13 拆分：设施=功能入口，场景=氛围景物）
    fac = self._map_facilities(cur_map, player, cur_sa)
    if fac:
        if lines and lines[-1]:
            lines.append("")
        lines.append(_T.static("hurry.fac_head"))
        if _compact:
            lines.append("  ●" + " ●".join(fac))
        else:
            for l in fac:
                lines.append(f"  {l}")
    # v132 场景两区：🔎 可探索触发（POI/调查）+ ✨ 可交互场景（PROPS）
    poi_lines, prop_lines = self._map_scene(cur_map, player, cur_sa)
    if poi_lines:
        if lines and lines[-1]:
            lines.append("")
        lines.append(_T.static("hurry.poi_head"))
        if _compact:
            names = []
            for l in poi_lines:
                nm = l.split("(")[0].strip()
                names.append(f"●{nm}")
            lines.append("  " + " ".join(names))
        else:
            for l in poi_lines:
                lines.append(f"  {l}")
    if prop_lines:
        if lines and lines[-1]:
            lines.append("")
        lines.append(_T.static("hurry.prop_head"))
        if _compact:
            names = [f"●{i}. {l.split('(')[0].strip()}" for i, l in enumerate(prop_lines, 1)]
            lines.append("  " + " ".join(names))
        else:
            for l in prop_lines:
                lines.append(f"  {l}")
    # 本地 NPC
    # v86 子区域：NPC 按当前子区域显示（无子区域则地图级）
    cur_sa_obj = None
    if cur_sa:
        for _sa in sas:
            if _sa["id"] == cur_sa:
                cur_sa_obj = _sa
                break
    npc_ids = (cur_sa_obj.get("npcs") if cur_sa_obj else None) or cur_map.get("npcs", [])
    if cur_map.get("inline_npcs"):
        npc_ids = cur_map["inline_npcs"]
    # 查表走引擎 `Lookup`（HIDDEN 优先的真值链；缺席静默丢弃）—— 成员集合与豁免判据逐字不变
    npcs = [(nid, n) for nid, n, _t in _LOOKUP_HIDDEN_FIRST.rows(npc_ids)]
    # v95.30 城镇 NPC 随机性：酱油 NPC 按 游走(roam)/概率(appear)/时段(period) 过滤显示
    # （功能 NPC 恒显示；隐藏 NPC 走副本层逻辑不参与；无子区域(地图级)不做过滤）
    npcs = [(nid, n) for nid, n in npcs
            if nid in _cat_quests.HIDDEN_NPCS or not cur_sa or _wild.town_npc_visible(nid, n, cur_sa)]
    if npcs:
        if lines and lines[-1]:
            lines.append("")
        lines.append(_T.static("npclist.head"))
        if _compact:
            # 城镇紧凑：●1. 名 ●2. 名（无头衔，鱼鱼模板）
            _parts = [f"●{i}. {n['icon']}{n['name']}" for i, (_, n) in enumerate(npcs, 1)]
            lines.append("  " + " ".join(_parts))
        else:
            for i, (_, n) in enumerate(npcs, 1):
                lines.append(f"  {i:>2}. {n['icon']}{n['name']}({n['title']})")
            lines.append(f"  {self._tip('talk')}")
    # v127.5 限时NPC：在场野外旅人（偶遇进入限时状态，带 ⏳ 剩余分钟，全图可见）
    # v127.5.1 不重复加 _tip('talk')——对上城镇 NPC 区已有同分类提示（AST 防重铁律）
    wild_lines = self._present_wild_hints(group_id, qq_id, cur) if group_id is not None and qq_id is not None else []
    if wild_lines:
        if lines and lines[-1]:
            lines.append("")
        lines.append(_T.static("map.traveler_head"))
        lines.extend(wild_lines)
    # v66 此地玩家（含摆摊标记；v132 加编号，鱼鱼新排版）
    # v134 #33：无其他玩家时不显示本段（连标题行一并省略，不留空行）
    # v134.1 #46：排除自己——"只有玩家一个人时"不再显示『👤 此地的玩家：●1. 自己』
    here_players = [p for p in db.get_group_players(group_id).values()
                    if p.get("cur_map") == cur and str(p.get("qq_id")) != str(qq_id)]
    if here_players:
        stall_sellers = {str(s["seller"]) for s in db.market_list(group_id, cur)}
        if lines and lines[-1]:
            lines.append("")
        lines.append(_T.static("map.players_head"))
        if _compact:
            # 城镇紧凑：●1. 名 Lv.X ●2. 名 Lv.X（鱼鱼模板；摆摊标记保留——功能状态）
            _parts = [f"●{i}. {p['name']} Lv.{p['level']}"
                      + (" 🏪摆摊中" if str(p.get("qq_id")) in stall_sellers else "")
                      for i, p in enumerate(here_players, 1)]
            lines.append("  " + " ".join(_parts))
        else:
            for i, p in enumerate(here_players, 1):
                stall_mark = " 🏪摆摊中" if str(p.get("qq_id")) in stall_sellers else ""
                lines.append(f"  {i}. {p['name']} Lv.{p['level']}{stall_mark}")
    # v86 子区域：怪物按当前子区域（无则回退地图级）
    mons = (cur_sa_obj.get("monsters") if cur_sa_obj else None)
    if mons is None:
        mons = cur_map.get("monsters", [])
    # 精英/Boss（子区域优先）——先取值供去重判断与字段展示
    elite = (cur_sa_obj.get("elite") if cur_sa_obj else None) or cur_map.get("elite")
    boss = (cur_sa_obj.get("boss") if cur_sa_obj else None) or cur_map.get("boss")
    if mons:
        if lines and lines[-1]:
            lines.append("")
        # v101.25 #289：标题等级改用怪物实际 min-max——此前用子区域 lv+2 推断，
        # 与怪物真实等级差 2 级误导（round66 银风道口标 Lv.6-8 实际野狗 Lv.3）
        _mlvs = [lv for _m, _n, _r, lv, _s, _d in mons if lv]
        if _mlvs:
            _lo, _hi = min(_mlvs), max(_mlvs)
            lv_label = f"Lv.{_lo}" if _lo == _hi else f"Lv.{_lo}-{_hi}"
        else:
            base_lv = (cur_sa_obj.get("lv") if cur_sa_obj else None) or cur_map["lv"]
            lv_label = f"Lv.{base_lv}"
        lines.append(_T.text("hurry.monster_head", lv=lv_label))
        for mid, name, role, lv, skills, drops in mons:
            # v95r38 去重：池子条目与 elite/boss 字段重复时不重复显示（字段行会展示）
            if role == "elite" and elite and elite[0] == mid:
                continue
            if role == "boss" and boss and boss[0] == mid:
                continue
            mark = "👑" if role == "boss" else ("⭐" if role == "elite" else "")
            # v132 等级波动明示：普通怪 ±1（精英/Boss 不参与波动，不标注）
            jitter = "±1" if role not in ("elite", "boss") else ""
            lines.append(f"  {mark}{name} Lv.{lv}{jitter}")
    if elite:
        lines.append(_T.text("hurry.elite", name=elite[1]))
    if boss:
        lines.append(f"  👑 Boss：{boss[1]}")
    if lines and lines[-1]:
        lines.append("")
    lines.append(self._tip("map"))
    return lines


def _map_nav_body(self, player: dict, cur_map: dict, cur_sa: str,
                  group_id=None, qq_id=None, show_here=True, with_header=True) -> list:
    """v128 地图导航主体（标题/描述/当前位置/可前往列表）——『地图』『位置』共用。

    返回 lines 列表（未 join），调用方按需追加其余区块。
    可前往编号与 move 解析一致（同图子区域 → 隐藏🔒 → 跨图邻居）。
    v132 with_header=False：跳过标题三行（🗺️/描述/分隔线）——到达视图自带标题时用。
    """
    sas = cur_map.get("subareas") or []
    sa_now = ""
    sa_desc = ""
    for _sa in sas:
        if _sa["id"] == cur_sa:
            sa_now = _sa["name"]
            sa_desc = _sa.get("desc", "") or ""
            break
    # v87.3 标题修复：地图名 + 当前子区域（不再重复"橡木镇 · 橡木镇"）
    title = cur_map["name"]
    if sa_now:
        title = f"{cur_map['name']} · {sa_now}"
    # v87.13 描述优先显示当前子区域（子区域无 desc 时回退地图 desc）
    lines = ([f"🗺️ 【{title}】", f"{sa_desc or cur_map['desc']}", "━━━━━━━━━━━━"]
             if with_header else [])
    neighbors = _cat_b143.MAP_CONNECTIONS.get(cur_map.get("id", ""), [])
    links = _maps.subarea_links(cur_map.get("id", ""), cur_sa)
    _v_ids = {vs["id"] for vs in self._visible_sas(player, cur_map, group_id, qq_id)}
    _v_links = [lid for lid in links if lid in _v_ids]
    shown = [(i + 1, next((s for s in sas if s["id"] == lid), None))
             for i, lid in enumerate(_v_links)]
    shown = [(i, s) for i, s in shown if s]
    # 深度标记——v114.3 精简：只保留尽头标记 🔚（死胡同连接数==1 且非入口，提示此路到头需回头）
    _depth = getattr(_maps, "subarea_depth", None)
    _entry_id = _maps.map_entry_subarea(cur_map.get("id", ""))

    def _sa_mark(sa):
        if _depth is None:
            return ""
        # 死胡同（连接数==1 且非入口）
        try:
            if sa["id"] != _entry_id and len(_maps.subarea_links(cur_map.get("id", ""), sa["id"])) == 1:
                return "🔚"
        except Exception:
            pass
        return ""

    if shown or neighbors:
        # v132.2 全地图紧凑模式（鱼鱼拍板）：●横排、无📍/无Lv/无🔚——模板统一，野外同款
        _compact = True
        # v128 位置面板（show_here=False）始终显示当前位置；『地图』保持原有 if sa_now 语义
        if not _compact and (sa_now or not show_here):
            lines.append(_T.text("nav.cur_pos", name=sa_now or title))
        elif not show_here:
            # v132.1 城镇紧凑：『位置』面板/到达视图仍显示 📍（精简导航核心信息）；
            # 仅『地图』面板（show_here=True）按鱼鱼模板隐藏（标题已含位置）
            lines.append(_T.text("nav.cur_pos", name=sa_now or title))
        lines.append(_T.static("nav.dest_head"))
        if _compact and shown:
            _parts = [f"●{i}. {sa['name']}" for i, sa in shown]
            lines.append("  " + " ".join(_parts))
        else:
            for i, sa in shown:
                # v128 位置面板精简：不显示 "(你在这里)"（show_here=True 时保留）
                mark = _T.text("nav.here", ) if (show_here and sa["id"] == cur_sa) else ""
                lv_mark = f" Lv.{sa['lv']}" if sa.get("lv") else ""
                lines.append(f"  {i}. {_sa_mark(sa)}{sa['name']}{lv_mark}{mark}")
        # 隐藏未揭示房：显示 🔒？？？ 不编号（不可直接前往）
        _hidden_sas = [s for s in sas if s["id"] in links and s["id"] not in _v_ids]
        if _hidden_sas:
            for _hs in _hidden_sas:
                lines.append(_T.static("nav.hidden_corner"))
        exit_sa_id = _maps.map_exit_subarea(cur_map.get("id", ""))
        at_exit = (not exit_sa_id) or (cur_sa == exit_sa_id)
        # v137 副本地图化：副本内（no_exit）不显示通往野外的连接——副本是封闭地图
        _dun = cur_map.get("dungeon") or {}
        if _dun.get("no_exit"):
            neighbors = []
        # v95.21 跨图连接只在出口子区域列出：普通场所不显示野外/他镇目的地，
        # 出城必须走城门（镇郊/野外入口），符合"出城走城门"铁律
        if at_exit:
            if _compact:
                # v132.2 全地图紧凑：跨图邻居同样 ●横排（无 Lv，编号保留供『前往 N』直达）
                _parts = []
                for i, nid in enumerate(neighbors, len(_v_links) + 1):
                    nm, want_sa = self._conn_target(nid)
                    sa_lbl = self._conn_subarea_name(nm, want_sa)
                    lock = _T.static("world.hidden") if nm.get("hidden") else ""
                    _parts.append(f"●{i}. {nm['name']}{sa_lbl}{lock}")
                lines.append("  " + " ".join(_parts))
            else:
                for i, nid in enumerate(neighbors, len(_v_links) + 1):
                    nm, want_sa = self._conn_target(nid)
                    sa_lbl = self._conn_subarea_name(nm, want_sa)
                    lock = _T.static("world.hidden") if nm.get("hidden") else ""
                    lines.append(f"  {i}. {nm['name']}{sa_lbl} Lv.{nm['lv']}{lock}")
        else:
            # v95.25 #133：非出口子区域提示必经出口（与旧 _subarea_body 同口径，
            # v132 模板统一回归修复；街道链城镇在广场时提示必经之路）
            _exit_sa_name = next((s["name"] for s in sas if s["id"] == exit_sa_id), "出口")
            _hint = _exit_sa_name
            # v183：必经之路问引擎 —— 枢纽在广场时提示「先到哪个中间站」
            # （v95.25 起这里是手算的星形链首，已逐格比对证明与 route 等价）
            _mid = cur_map.get("id", "")
            _hub = _maps.map_center(_mid)
            if _hub and cur_sa == _hub:
                _r = _maps.map_route(_mid, cur_sa, exit_sa_id)
                if len(_r) >= 2:
                    _hint = next((s["name"] for s in sas if s["id"] == _r[1]), _hint)
            lines.append(_T.text("nav.need_first", sa=_hint))
        # v114.3 尽头标记图例（有深度数据才显示；城镇紧凑模式不显示——鱼鱼模板无此行）
        if _depth is not None and not _compact:
            lines.append(_T.static("nav.dead_end"))
    return lines


async def location_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    """v128.2 位置精简面板：当前位置 + 可前往列表 + 赶路入口提示。

    鱼鱼拍板：把『前往』指令拆成『位置』（精简）与『地图』（完整现状）。
    『位置』砍掉设施/场景/NPC/怪物等，只留导航。
    v128.2（鱼鱼拍板）：『位置 0』/发 0 进入赶路模式的旧捷径已移除——
    『位置 0』/『位置0』仍命中本面板（正则捕获 0 后缀）但不再切换赶路，
    面板统一提示用『赶路』指令进入（替代 v101.17 『前往开始/结束』）。
    """
    # O114 同源：副本战斗中与『地图』一致显示"副本战斗中"而非旧地点
    _inst_row = self._instance_battle_for(group_id, qq_id)
    if _inst_row:
        yield event.plain_result(
            _T.text("world.inst_battle", tail=self._tip('instance'))
        )
        return
    cur = player["cur_map"]
    # v68 家地图：home_{qq_id} 不在 MAPS，定制展示（与『地图』同款）
    if cur.startswith("home_"):
        yield event.plain_result(self._home_view(group_id, qq_id, cur))
        return
    cur_map = _cat_space.MAP_BY_ID[cur]
    cur_sa = player.get("cur_subarea") or ""
    lines = self._map_nav_body(player, cur_map, cur_sa, group_id, qq_id, show_here=False)
    # v128.2 赶路模式提示：唯一入口=『赶路』指令（旧『位置 0』捷径已移除）
    if db.get_event_state(f"move_mode:{qq_id}"):
        lines.append(_T.static("world.hurry_tip"))
    else:
        lines.append(_T.static("location.hurry_hint"))
    yield event.plain_result("\n".join(lines))


#: 赶路别名表（原宿主 `game/commands/world.py` 类属性 `_HURRY_ALIAS`；P5E「壳去逻辑」批搬回包内）。
#: 玩家输入词（中文/英文）→ 赶路类型域（`npc` / `monster` / `scene` / `facility`）。
#: D8：表体搬进包内域 `content/data/hurry_alias.json`（读口即本行；落点 / kind / 文件名唯一源 =
#: `editor/domains.json`，引擎 `records` fail-closed：域未声明 / 文件缺 / 键集不符 → 装载期点名报错）。
_HURRY_ALIAS = records_from_domain(
    _PKG_ROOT, "hurry_alias",
    order=("npc", "怪物", "monster", "场景", "scene", "景物", "设施", "facility", "商店"),
).into(lambda _e: _e.get("target"))


def _hurry_type(self, raw: str):
    """『赶路』可选参数归一：""=全量, None=无效；npc/monster/scene/facility=类型过滤。"""
    k = (raw or "").strip().lower()
    if k in ("", "全部", "全", "all"):
        return ""
    return _HURRY_ALIAS.get(k)


def _hurry_section(self, player: dict, cur_map: dict, cur_sa: str,
                   group_id, qq_id, ftype: str) -> list:
    """v128.1 类型过滤区（NPC/怪物/场景/设施）——赶路面板与移动落点过滤共用。

    返回 lines 列表（未 join）；无内容给"没有XX"提示行，保证赶路语境一致。
    """
    lines = []
    sas = cur_map.get("subareas") or []
    cur_sa_obj = None
    for _sa in sas:
        if _sa["id"] == cur_sa:
            cur_sa_obj = _sa
            break
    if ftype == "npc":
        npc_ids = (cur_sa_obj.get("npcs") if cur_sa_obj else None) or cur_map.get("npcs", [])
        if cur_map.get("inline_npcs"):
            npc_ids = cur_map["inline_npcs"]
        # 与 `_map_blocks` 同口径：HIDDEN 优先的真值链（成员集合与豁免判据逐字不变）
        npcs = [(nid, n) for nid, n, _t in _LOOKUP_HIDDEN_FIRST.rows(npc_ids)]
        npcs = [(nid, n) for nid, n in npcs
                if nid in _cat_quests.HIDDEN_NPCS or not cur_sa or _wild.town_npc_visible(nid, n, cur_sa)]
        if npcs:
            lines.append(_T.static("npclist.head"))
            for i, (_, n) in enumerate(npcs, 1):
                lines.append(f"  {i:>2}. {n['icon']}{n['name']}({n['title']})")
        else:
            lines.append(_T.static("hurry.npc_none"))
    elif ftype == "monster":
        mons = (cur_sa_obj.get("monsters") if cur_sa_obj else None)
        if mons is None:
            mons = cur_map.get("monsters", [])
        elite = (cur_sa_obj.get("elite") if cur_sa_obj else None) or cur_map.get("elite")
        boss = (cur_sa_obj.get("boss") if cur_sa_obj else None) or cur_map.get("boss")
        if mons:
            _mlvs = [lv for _m, _n, _r, lv, _s, _d in mons if lv]
            if _mlvs:
                _lo, _hi = min(_mlvs), max(_mlvs)
                lv_label = f"Lv.{_lo}" if _lo == _hi else f"Lv.{_lo}-{_hi}"
            else:
                base_lv = (cur_sa_obj.get("lv") if cur_sa_obj else None) or cur_map["lv"]
                lv_label = f"Lv.{base_lv}"
            lines.append(_T.text("hurry.monster_head", lv=lv_label))
            for mid, name, role, lv, skills, drops in mons:
                if role == "elite" and elite and elite[0] == mid:
                    continue
                if role == "boss" and boss and boss[0] == mid:
                    continue
                mark = "👑" if role == "boss" else ("⭐" if role == "elite" else "")
                lines.append(f"  {mark}{name} Lv.{lv}")
        if elite:
            lines.append(_T.text("hurry.elite", name=elite[1]))
        if boss:
            lines.append(f"  👑 Boss：{boss[1]}")
        if not mons and not elite and not boss:
            lines.append(_T.static("hurry.monster_none"))
    elif ftype == "scene":
        # v132 场景两区：🔎 可探索触发（POI）+ ✨ 可交互场景（PROPS），与 _map_blocks 同口径
        # ★ 修：_map_scene 返回 (poi_lines, prop_lines) 二元组——此前当平铺列表用 ⇒ 打印 list repr
        poi_lines, prop_lines = self._map_scene(cur_map, player, cur_sa)
        if poi_lines:
            lines.append(_T.static("hurry.poi_head"))
            for l in poi_lines:
                lines.append(f"  {l}")
        if prop_lines:
            lines.append(_T.static("hurry.prop_head"))
            for l in prop_lines:
                lines.append(f"  {l}")
        if not poi_lines and not prop_lines:
            lines.append(_T.static("hurry.scene_none"))
    elif ftype == "facility":
        fac = self._map_facilities(cur_map, player, cur_sa)
        if fac:
            lines.append(_T.static("hurry.fac_head"))
            for l in fac:
                lines.append(f"  {l}")
        else:
            lines.append(_T.static("hurry.fac_none"))
    return lines


def _hurry_panel(self, player: dict, cur_map: dict, cur_sa: str,
                 group_id, qq_id, ftype: str) -> str:
    """v128.1 赶路过滤面板：标题 + [类型清单] + 可前往通道 + 赶路提示。

    意见 #1（鱼鱼拍板合并为『赶路 <类型>』可选参数）：赶路时只看对应内容
    + 地图通道，省略其他信息，方便快速找 NPC/怪物/场景互动。ftype=""=全量。
    """
    nav = self._map_nav_body(player, cur_map, cur_sa, group_id, qq_id, show_here=False)
    lines = [nav[0], "━━━━━━━━━━━━"] if nav else []
    lines.extend(self._hurry_section(player, cur_map, cur_sa, group_id, qq_id, ftype))
    # 可前往通道（复用导航主体，跳过标题/desc/分隔线）
    rest = [x for x in nav[3:] if str(x).strip()]
    if rest:
        if ftype and lines and lines[-1]:  # v128.1 无参(full)无类型区不加分隔空行
            lines.append("")
        lines.extend(rest)
    lines.append("")
    lines.append(_T.static("world.hurry_tip"))
    return "\n".join(lines)


async def hurry_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    """v128.1 『赶路 [NPC/怪物/场景/设施]』过滤面板 + 进入赶路模式。

    意见 #1（赶路NPC/赶路怪物/赶路场景，鱼鱼拍板合并可选参数）：赶路时
    只看对应内容 + 地图通道，省略其他信息，方便快速找 NPC/怪物/场景互动。
    无参 = 当前位置全量可前往；全部形态进入赶路模式（0 结束）。
    """
    _inst_row = self._instance_battle_for(group_id, qq_id)
    if _inst_row:
        yield event.plain_result(
            _T.text("world.inst_battle", tail=self._tip('instance'))
        )
        return
    raw = self._strip_cmd(event, "赶路").strip()
    ftype = self._hurry_type(raw)
    if ftype is None:
        yield event.plain_result(
            _T.static("hurry.usage"))
        return
    # 进入赶路模式（0 结束；无参也进，方便直接回复序号走）
    db.set_event_state(f"move_mode:{qq_id}", "1")
    # v128.1 持久化过滤类型（移动落点也按该类型过滤）
    db.set_event_state(f"hurry_type:{qq_id}", ftype)
    cur = player["cur_map"]
    if cur.startswith("home_"):
        yield event.plain_result(self._home_view(group_id, qq_id, cur))
        return
    cur_map = _cat_space.MAP_BY_ID[cur]
    cur_sa = player.get("cur_subarea") or ""
    yield event.plain_result(self._hurry_panel(player, cur_map, cur_sa, group_id, qq_id, ftype))


def _move_blocked_msg(self, cur_map: dict, player: dict, target_sa: dict) -> str:
    """v87.14 同图内不可直达时的提示(城镇星形 / 野外线性)——v181 P4-8 已下沉 travel.move_blocked_msg。"""
    from .travel import move_blocked_msg
    return move_blocked_msg(cur_map, player, target_sa)


async def back_cmd(self, event: AstrMessageEvent, group_id, qq_id):
    dest = self._strip_cmd(event, "返回").strip()
    if dest:
        yield event.plain_result(
            _T.text("back.deprecated_named", arg=dest, arg2=dest))
    else:
        yield event.plain_result(_T.static("back.deprecated"))


async def ask_way(self, event: AstrMessageEvent, group_id, qq_id, player):
    msg0 = event.get_message_str()
    _cmd_used = "寻路" if re.search(r"(?:\[At:[^\]]*\]\s*)?寻路", msg0) else "问路"
    raw = self._strip_cmd(event, _cmd_used).strip()
    if not raw:
        yield event.plain_result(_T.static("way.usage"))
        return
    cur = player.get("cur_map", "")
    cur_map = _cat_space.MAP_BY_ID.get(cur, {})
    # 1) 同图子区域名：直接给『前往』指引
    for sa in (cur_map.get("subareas") or []):
        if raw in (sa.get("name", ""), sa.get("id", "")):
            if sa.get("id") == player.get("cur_subarea"):
                yield event.plain_result(_T.text("way.already_here_sub", map=cur_map.get('name', ''), sa=sa.get('name', '')))
            else:
                yield event.plain_result(
                    _T.text("way.nearby", name=sa.get('name', ''), map=cur_map.get('name', ''),
                        cmd=sa.get('name', '')))
            return
    # 2) 跨图目标：地图名/id/区域名/旧别名（与『前往』同口径）
    target = None
    for m in _cat_space.MAPS:
        if raw in (m["name"], m["id"]):
            target = m
            break
    if not target and raw in _cat_b143.LEGACY_MAP_ALIAS:
        target = _cat_space.MAP_BY_ID.get(_cat_b143.LEGACY_MAP_ALIAS[raw])
    if not target:
        for m in _cat_space.MAPS:
            if raw in m.get("area_name", ""):
                target = m
                break
    if not target:
        yield event.plain_result(_T.text("way.not_found", name=raw))
        return
    if target["id"] == cur:
        yield event.plain_result(_T.text("way.already_here", name=target['name']))
        return
    # 3) BFS 最短路径（MAP_CONNECTIONS 无向图）
    from collections import deque
    _conns = _cat_b143.MAP_CONNECTIONS
    q = deque([(cur, [cur])])
    seen = {cur}
    route = None
    while q:
        _c, _path = q.popleft()
        if _c == target["id"]:
            route = _path
            break
        for _conn in _conns.get(_c, []):
            _nid = _conn[0] if isinstance(_conn, tuple) else _conn
            if _nid not in seen:
                seen.add(_nid)
                q.append((_nid, _path + [_nid]))
    if not route:
        yield event.plain_result(_T.text("way.no_route", name=target['name']))
        return
    # v167.1 展示优化：起止标记 + 每段区域名(Lv.N)（首段=当前，末段=目标）
    _path_n = []
    for _i, _mid in enumerate(route):
        _mp = _cat_space.MAP_BY_ID.get(_mid, {})
        _nm = _mp.get("name") or _mid
        _nlv = _mp.get("lv")
        _lvs = f"(Lv.{_nlv})" if _nlv else ""
        if _i == 0:
            _path_n.append(f"📍{_nm}{_lvs}")
        elif _i == len(route) - 1:
            _path_n.append(f"🎯{_nm}{_lvs}")
        else:
            _path_n.append(f"{_nm}{_lvs}")
    yield event.plain_result(
        _T.text("way.path", name=target['name'], n=len(route) - 1, path=' → '.join(_path_n)))


def _instance_gate_block(shell, player, group_id, qq_id, target):
    """副本图门禁：徒步『前往/移动』不得直接进副本图（玩法规则，P5E「壳去逻辑」批搬回包内）。

    原实现住在宿主壳 `host/shell.py::_instance_gate_block`（原 `game/commands/world.py` 同名方法）。
    这里只做「取数 + 组装 `ctx`」；判定本体 = `content/flow/instance_gate.py::walk_admission`
    （三档任一满足即放行：任务放行 / 持钥匙 / 已通关），渲染走包内文案表。
    调用方 = 本模块 `move`（`self._instance_gate_block(...)`，宿主壳按名解析到本函数）。
    """
    if target.get("type") != _cat_core.MAP_TYPE_INSTANCE:
        return ""
    if hasattr(instance_gate, "set_text_table"):
        instance_gate.set_text_table(_texts.table())
    kid = target.get("id", "")
    mid = "inst_%s" % kid
    inst = (_cat_space.INSTANCES or {}).get(mid)
    quests = db.get_quests(group_id, qq_id)
    quest_open = False
    if quests.get("main_status") == "active":
        mq = next((q for q in _cat_quests.MAIN_QUESTS
                   if q["id"] == quests.get("main_quest")), None)
        if mq and mq["objective"].get("explore") == kid:
            quest_open = True
    if not quest_open:
        side = quests.get("side") or {}
        quest_open = any(
            sq.get("status") == "active"
            and next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == sid), {}).get(
                "objective", {}).get("explore") == kid
            for sid, sq in side.items())
    key_item = (inst or {}).get("key_item")
    ctx = {
        "inst_name": (inst or {}).get("name")
                     or (_cat_space.MAP_BY_ID.get(kid) or {}).get("name", "副本"),
        "tip": shell._tip("instance"),
        "quest_open": quest_open,
        "key_held": bool(key_item) and instance_gate.find_instance_key_item(
            db.get_inventory(group_id, qq_id) or [], key_item,
            items=(_cat_items.ITEMS or {})) is not None,
        "cleared": instance_gate.instance_cleared(
            db.get_achievements(group_id, qq_id) or [], mid),
    }
    verdict = instance_gate.walk_admission(ctx).check(ctx)
    return "" if verdict.ok else verdict.reason


async def move(self, event: AstrMessageEvent, group_id, qq_id):
    dest = self._strip_cmd(event, "前往")
    if dest.startswith("移动"):
        dest = dest[2:].strip()  # v104 P2(M22): 『移动 <地名/序号>』别名参数剥离（双名共存）
    player = self._player(group_id, qq_id)
    # v87.13 对话中禁止移动：多轮对话进行时先回复 0 结束（v127.8 起『对话 0』亦拦截）
    # O99 修复：统一对话状态判定（_talk_active 会清除损坏残留键，防判定漂移）
    if self._talk_active(group_id, qq_id):
        yield event.plain_result(_T.static("move.talk_block"))
        return
    # v137 副本地图化：副本内移动（队长带队，房间连通）——必须先于 _in_battle 全局拦截：
    # 副本地图模式（mode=map，st.boss=None）下 battle 锁仍持有，_in_battle 会拦截所有移动。
    # _instance_move_route 内部校验副本状态并自行处理锁（解锁→推进→按需重新上锁）。
    _mv_dest = dest
    if _mv_dest.startswith("移动"):
        _mv_dest = _mv_dest[2:].strip()
    _routed = False
    async for _r in self._instance_move_route(event, group_id, qq_id, player, _mv_dest.strip()):
        yield _r
        _routed = True
    if _routed:
        return
    dest = _mv_dest
    # v95.17 #146：战斗中禁止移动（与传送/回家/拜访一致，防战斗挂起跨图/被撞怪覆盖）
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("move.battle_block"))
        return
    dest = dest.strip()
    # v104 P1(M22)：空参数『前往』/『移动』不再静默移动——"" 是任意非空串的子串，
    # 此前会命中 area_name 首个非空地图静默跨图并扣体力，直接提示输入目标
    if not dest:
        yield event.plain_result(_T.static("move.no_dest"))
        return
    # v94 体力：同图子区域移动免费（城内溜达不算赶路）；跨图移动扣 1、体力不足拒绝
    cur = player["cur_map"]
    cur_map = _cat_space.MAP_BY_ID.get(cur, {})
    cur_sas = cur_map.get("subareas") or []
    # v86 子区域：『移动 <序号>』→ 同图可前往列表序号优先（v87.14 空间连接），再邻居地图序号
    # v104 P3(M24) 确认：全角数字兼容——Python str.isdigit()/int() 原生接受全角 ０-９(U+FF10-FF19)，
    # 『前往 １２』与『前往 12』等价（实测 2026-08-12：isdigit=True 且 int('１２')==12，无需 normalize）。
    # v115 网状：visible_links 用 _visible_sas 过滤（隐藏未揭示不可前往），与『地图』面板编号一致
    _raw_links = _maps.subarea_links(cur, player.get("cur_subarea") or "")
    _v_ids = {vs["id"] for vs in self._visible_sas(player, cur_map, group_id, qq_id)}
    links = [lid for lid in _raw_links if lid in _v_ids]
    if dest.isdigit():
        idx = int(dest)
        if 1 <= idx <= len(links):
            sa_id = links[idx - 1]
            sa = next((s for s in cur_sas if s["id"] == sa_id), None)
            if sa is None:
                yield event.plain_result(_T.static("move.sa_missing"))
                return
            if sa["id"] == player.get("cur_subarea"):
                yield event.plain_result(_T.text("move.same_sa", map=cur_map['name'], sa=sa['name']))
                return
            db.update_player(group_id, qq_id, cur_subarea=sa["id"])
            yield event.plain_result(self._subarea_arrive(player, cur_map, sa, group_id, qq_id))
            return
    # v86 子区域：『移动 <子区域名>』→ 同图子区域（免费切换）
    if dest:
        for sa in cur_sas:
            if dest in (sa["name"], sa["id"]):
                if sa["id"] == player.get("cur_subarea"):
                    yield event.plain_result(_T.text("move.same_sa", map=cur_map['name'], sa=sa['name']))
                    return
                # v87.14 空间连接：同图只能移动到相邻子区域
                # v115：隐藏未揭示房不能直接前往（提示需先探索揭开）
                from .travel import subarea_hidden_block
                _hidden_txt = subarea_hidden_block(group_id, qq_id, cur, sa)
                if _hidden_txt:
                    yield event.plain_result(_hidden_txt)
                    return
                links2 = _maps.subarea_links(cur, player.get("cur_subarea") or "")
                if sa["id"] not in links2:
                    yield event.plain_result(self._move_blocked_msg(cur_map, player, sa))
                    return
                db.update_player(group_id, qq_id, cur_subarea=sa["id"])
                yield event.plain_result(self._subarea_arrive(player, cur_map, sa, group_id, qq_id))
                return
    # 查找目标地图：优先序号（相对当前地图邻居列表），其次地图名/ID/旧区域别名
    target = None
    want_sa = None
    if dest.isdigit():
        neighbors = _cat_b143.MAP_CONNECTIONS.get(cur, [])
        idx = int(dest)
        offset = len(links)
        # #263: 与地图显示口径一致——跨图连接只在出口子区域有效（v95.21 出城走城门铁律），
        # 非出口子区域报错"可前往 N 处"此前无条件加邻居数（显示 1 处却报 5 处）
        exit_sa_id = _maps.map_exit_subarea(cur)
        at_exit = (not exit_sa_id) or (player.get("cur_subarea") == exit_sa_id)
        if not at_exit:
            neighbors = []
        if offset + 1 <= idx <= offset + len(neighbors):
            target, want_sa = self._conn_target(neighbors[idx - offset - 1])
        else:
            # #263 回归修复：不在出口子区域时序号命中邻居地图 → 引导去出口
            # （此前清空 neighbors 后直接"序号无效"，丢了 v87.14 出城走城门的路线引导；
            #   无效序号仍按实际可前往数量报错，保持 #263 口径一致）
            if not at_exit and offset + 1 <= idx <= offset + len(_cat_b143.MAP_CONNECTIONS.get(cur, [])):
                _exit_name = next((s["name"] for s in (cur_map.get("subareas") or []) if s["id"] == exit_sa_id), "出口")
                _cur_sa_name = next((s["name"] for s in (cur_map.get("subareas") or []) if s["id"] == player.get("cur_subarea")), player.get("cur_subarea", ""))
                yield event.plain_result(
                    _T.text("move.exit_hint", sa=_cur_sa_name,
                            map=cur_map.get('name', '此地'),
                            exit=_exit_name, exit2=_exit_name)
                )
                return
            total = len(links) + len(neighbors)
            yield event.plain_result(_T.text("move.idx_invalid", total=total))
            return
    else:
        from .travel import resolve_map_target
        target = resolve_map_target(dest)
    if not target:
        names = "、".join([m["name"] for m in _cat_space.MAPS])
        yield event.plain_result(_T.text("move.not_found", dest=dest))
        return
    # 隐藏图检查
    from .travel import hidden_map_block
    _hid_block = hidden_map_block(group_id, qq_id, player, target)
    if _hid_block:
        yield event.plain_result(_hid_block)
        return
    # 是否相邻
    cur = player["cur_map"]
    neighbors = _cat_b143.MAP_CONNECTIONS.get(cur, [])
    nids = [c[0] if isinstance(c, tuple) else c for c in neighbors]
    # v104 P1(M22)：目标==当前图（输入本图地图名/区域名）→ 提示已在，不再原地白走扣体力
    # （同图子区域名分支 :676-678 已有同款提示，跨图路径此前漏了）
    if target["id"] == cur:
        yield event.plain_result(_T.text("move.same_map", map=cur_map.get('name', '此地')))
        return
    if target["id"] != cur and target["id"] not in nids:
        yield event.plain_result(_T.text("move.not_adjacent", name=target['name']))
        return
    # v84 红名限制（26 章三 第一档）：红名不能进入城镇安全区（'城镇外郊' 数据不存在，v102.1 清理）
    if self._is_redname(qq_id) and target.get("type") == _cat_core.MAP_TYPE_TOWN:
        yield event.plain_result(_T.static("move.redname"))
        return
    # 等级提示
    from .travel import level_warn
    lv_msg = level_warn(player, target)
    # v87.14 出图必须在该图出口子区域（城镇=城门，野外=入口）
    from .travel import leave_map_block_msg
    _leave_block = leave_map_block_msg(cur_map, player)
    if _leave_block:
        yield event.plain_result(_leave_block)
        return
    # q1-B 副本图门禁：副本图（type=副本）不可徒步直入（终局副本旁路修复）——
    # 需已接取对应 explore 主线/支线任务、或持有副本钥匙、或已通关该副本才能进入。
    _inst_gate = self._instance_gate_block(player, group_id, qq_id, target)
    if _inst_gate:
        yield event.plain_result(_inst_gate)
        return
    # v137 副本地图化：副本内移动（已开本 + 在副本图内）——队长带队、房间连通、
    # discovery_agro 遇怪、Boss 房 Boss 战。目标房间名/序号解析与野外同款，
    # 但只在本图连通表内移动（no_exit 无出口，不连野外）。
    # 注意：_instance_move_route 已在 move 顶部先行路由（副本地图模式持有战斗锁，
    # _in_battle 全局拦截在前）；此处副本分支保留以兼容直接调用/后续路径。
    # ★ 修：st.inst_id 是 INSTANCES key（inst_xxx），与地图 id 比较须走 v137 统一口径
    # `_inst_map_id`（此前直比恒 False ⇒ 该兼容分支实为死分支）
    from .instance_cmds import _inst_map_id
    inst_row = self._instance_battle_for(group_id, qq_id)
    if inst_row and _inst_map_id(inst_row["state"].get("inst_id") or "") == target["id"] \
            and (inst_row["state"].get("mode") == "map" or inst_row["state"].get("rooms")):
        # v141 审计 #8：_instance_dungeon_move 去掉 target 死参数——地图目标
        # 在函数内按 inst_id 解析（大陆实例优先），此处只透传玩家原始 dest
        async for _r in self._instance_dungeon_move(event, group_id, qq_id, player, inst_row, dest):
            yield _r
        return
    # v86 子区域：跨图移动 → 落点：城镇=城门，野外=入口（v87.14）
    from .travel import landing_subarea
    first_sa = landing_subarea(target, want_sa)
    # v94 体力：跨图移动扣 1；体力 0 拒绝（同图移动免费已在上方处理）；v101.13 坐骑 stamina_reduce 概率免费
    if self._stamina(player) < 1:
        from .travel import stamina_tired_line
        yield event.plain_result(stamina_tired_line(player))
        return
    from .travel import move_stamina_cost
    _mv_cost = move_stamina_cost(player)
    if _mv_cost > 0:
        self._spend_stamina(group_id, qq_id, _mv_cost, player, "移动")
    db.update_player(group_id, qq_id, cur_map=target["id"],
                     cur_subarea=first_sa["id"] if first_sa else "")
    # 记录到访（称号用）
    db.add_visited(group_id, qq_id, target["id"])
    # 阶段九：到访成就判定（14 章 2.4 探索成就）
    _ach.check_achievements(group_id, qq_id, self._player(group_id, qq_id))
    # 探索型任务触发（到达目标子区域自动完成）
    quest_lines = self._update_explore_quests(group_id, qq_id, target["id"])
    extra = ""
    if quest_lines:
        extra = "\n\n" + "\n".join(quest_lines)
    # 旅者方碑提示（未激活时）
    from .travel import portal_arrive_note
    portal_msg = portal_arrive_note(group_id, qq_id, target)
    # v13：到达后显示可前往 + 设施/场景（v87.13 拆分）
    # v87.16 与地图面板一致：links 顺序号 + 邻居从 len(links)+1 编号
    target_sas = target.get("subareas") or []
    t_links = _maps.subarea_links(target["id"], first_sa["id"] if first_sa else "")
    t_shown = [(i + 1, next((s for s in target_sas if s["id"] == lid), None))
               for i, lid in enumerate(t_links)]
    t_shown = [(i, s) for i, s in t_shown if s]
    neighbors = _cat_b143.MAP_CONNECTIONS.get(target["id"], [])
    nav = ""
    # v101.25c 模板统一后：完整"可前往"列表已由 _subarea_body 输出，
    # 此处不再拼紧凑版（否则跨图移动出现两行重复列表，playtest #405）
    # v128 赶路模式提示统一由 _subarea_arrive 输出（回复 0 结束），此处不再重复。
    # v132：fac_msg/scene_msg 死代码已删（v101.25c 起跨图移动走 _subarea_arrive，
    # 此处拼装从未被消费；_map_scene 改返回 (poi, prop) 后旧 join 会直接崩）
    # v49 意见#4：移动撞怪（生物趋避利害——低级闯高级区容易撞怪，高级玩家威慑低级区）
    ambush = self._travel_ambush(player, target, group_id, qq_id)
    # v101.25c 模板统一：跨图移动也走 _subarea_arrive 完整模板（NPC/可互动/设施/场景/可前往）
    # 此前跨图是另一套精简拼接（fac_msg/scene_msg/nav），鱼鱼抓"前往不同区域提示模板不一样"
    if ambush:
        # v2 多对多：撞怪经 build_monster_group 生成敌方阵列（单只即可，伏击不引入随机双怪）
        # N5b4-6：撞怪开战 saintess_engine 化（同 _open_battle 仪式，跨图伏击 = 普通战斗形态）
        _grp = _drops().build_monster_group(ambush, target, player)
        # T6⑧（2026-09-20）：旧兜底分支已删 —— 它经别名
        # `from ext_combat import Battle as B2` 裸造 Battle（**不带 `text=`**）⇒ 绕过「玩家可见文案唯一真源」。
        # `_open_battle`（真源 `content/combat_cmds.py`）与 move 同属包内聚合面（facade
        # AGGREGATE_MODULES）⇒ 终态不可能缺席；缺即 AttributeError 大声失败（fail-closed，不静默兜底）。
        _nb = self._open_battle(player, _grp, "monster", group_id=group_id, qq_id=qq_id)
        db.save_battle(group_id, qq_id, _nb.to_state())
        self._lock_battle(group_id, qq_id)
        arrive_txt = _T.text("move.arrive", name=target['name'])
        if target.get("type") == _cat_core.MAP_TYPE_TOWN and first_sa:
            arrive_txt = _T.text("move.arrive_town", name=target['name'], sa=first_sa['name'])
        # 我方站位单机 = 玩家单位
        _cls = _cat_core.CLASSES.get(player.get("class_name", ""), {}) or {}
        _self_unit = {
            "uid": "p_self", "rank": int(_cls.get("default_rank", 2) or 2),
            "reach": int(_cls.get("reach", 2) or 2), "name": player.get("name", "你"),
            "hp": player.get("hp", 0), "max_hp": player.get("max_hp", 0),
        }
        _enemy_rows = formation_view(alive_units(_grp), side="enemy")
        _ally_rows = formation_view(alive_units([_self_unit]), side="ally")
        yield event.plain_result(
            _T.text("move.ambush_head", arrive=arrive_txt,
                    desc=(first_sa.get('desc') if first_sa else '') or target.get('desc', ''),
                    lv=lv_msg, extra=extra, portal=portal_msg, ambush=ambush['name'])
            + "\n".join(_enemy_rows) + _T.static("move.ally_head") + "\n".join(_ally_rows)
            + _T.text("move.ambush_tail", name=ambush['name'], lv=ambush['lv'],
                      hp=ambush['hp'], max_hp=ambush['max_hp'])
        )
        return
    # v87.3 必经之路：进入城镇时提示方向（从路图/野外进城）
    arrive_txt = _T.text("move.arrive", name=target['name'])
    if target.get("type") == _cat_core.MAP_TYPE_TOWN and first_sa:
        arrive_txt = _T.text("move.arrive_town", name=target['name'], sa=first_sa['name'])
    # v97.5 行为彩蛋规则：进入新地图
    _rule_txt = self._rule_fire("move_enter", group_id, qq_id, player, target)
    arrive_view = self._subarea_arrive(player, target, first_sa, group_id, qq_id) if first_sa else \
        _T.text("move.arrive_desc", name=target['name'], desc=target.get('desc', ''))
    # 跨图特有信息插在主体前（等级提示/任务/方碑）
    _head_extra = f"{lv_msg}{extra}{portal_msg}"
    yield event.plain_result(
        f"{arrive_view}{_head_extra}"
        + (f"\n{_rule_txt}" if _rule_txt else "")
    )


def _subarea_arrive(self, player: dict, cur_map: dict, sa: dict, group_id=None, qq_id=None) -> str:
    """v132 到达视图：🗺️ 标题 + 描述 + 完整区块（导航/奇遇/设施/场景/NPC/旅人/玩家/怪物/tip）。

    v86 子区域到达展示：位置 + 描述 + 本子区域可互动 + 可前往子区域。
    v6 修复：与跨图移动一致，展示本子区域 PROPS/POI 场景元素
    （鱼鱼验收：移动展示必须与『地图』面板一致）。
    v101.25c：主体复用 _subarea_body（与跨图移动/返回同模板）。
    v132：_subarea_body 移除，改为 _map_nav_body(without_header) + _map_blocks——
    与『地图』面板 100% 同源（鱼鱼拍板新排版：可前往带 Lv/尽头标记、场景分两区、
    玩家编号、怪物标 ±1 波动；移动面板与地图面板永不分裂）。
    v115：H 提供 exploration_record_visit 时，到达即记录 + 首访奖励文本追加。
    """
    title = cur_map["name"]
    if sa.get("name"):
        title = f"{cur_map['name']} · {sa['name']}"
    desc = sa.get("desc", "") or cur_map.get("desc", "")
    # v128.1 赶路类型过滤落点：hurry_type 非空时只显示该类型 + 可前往通道
    _ht = ""
    if group_id is not None and qq_id is not None:
        _ht = db.get_event_state(f"hurry_type:{qq_id}") or ""
    # v134.3 赶路模式精简：move_mode 开启时默认只显示可前往（不显示设施/场景/NPC
    # 等杂项），带 hurry_type 参数才显示对应类型——鱼鱼拍板"默认赶路状态不需要
    # 显示那么多，只显示可前往就行了，带参数才要显示别的"
    _mv = False
    if group_id is not None and qq_id is not None:
        _mv = bool(db.get_event_state(f"move_mode:{qq_id}"))
    if _ht or _mv:
        nav = self._map_nav_body(player, cur_map, sa["id"], group_id, qq_id,
                                 show_here=False, with_header=False)
        if _ht:
            sec = self._hurry_section(player, cur_map, sa["id"], group_id, qq_id, _ht)
        else:
            sec = []
        lines = [f"🗺️ 【{title}】", desc, "━━━━━━━━━━━━"] + sec
        rest = [x for x in nav if str(x).strip()]
        if rest:
            if sec:
                lines.append("")
            lines.extend(rest)
        out = "\n".join(lines)
    else:
        nav = self._map_nav_body(player, cur_map, sa["id"], group_id, qq_id,
                                 show_here=False, with_header=False)
        blocks = self._map_blocks(player, cur_map, sa["id"], group_id, qq_id)
        out = "\n".join([f"🗺️ 【{title}】", desc, "━━━━━━━━━━━━"] + nav + blocks)
    # v115 探索见闻：到达子区域记录 + 首访奖励（H 提供，getattr 兜底）
    _rec = getattr(_exploration, "exploration_record_visit", None)
    if _rec is not None and group_id is not None and qq_id is not None:
        try:
            _rv = _rec(group_id, qq_id, cur_map.get("id", ""), sa.get("id", ""))
        except Exception:
            _rv = None
        if _rv:
            if _rv.get("first"):
                _rw = _rv.get("reward") or ""
                if _rw:
                    out += f"\n🎉 {_rw}"
            else:
                _rw = _rv.get("reward") or ""
                if _rw:
                    out += f"\n{_rw}"

    # v128 赶路模式：移动落点统一提示（回复 0 结束），替代『前往结束』
    if group_id is not None and qq_id is not None and db.get_event_state(f"move_mode:{qq_id}"):
        out += _T.static("move.mode_hint")
    return out


async def _instance_dungeon_move(self, event, group_id, qq_id, player, inst_row, dest):
    """v137 副本内移动（world.move 副本分支）：队长带队 + 房间连通校验 + discovery_agro 遇怪 + Boss 房 Boss 战。

    与野外移动共用同一『前往/移动』入口（鱼鱼 v137：副本与野外共用一套代码机制），
    差异仅在：
      ① 仅队长可移动，全队 cur_subarea 同步（db.update_player 每个成员）
      ② 目标房间必须在本图 SUBAREA_LINKS_INDEX 连通表内（副本无出口，不连野外）
      ③ 遇怪概率 = dungeon.discovery_agro（core/encounter.encounter_chance 统一读，
         数据表驱动），消耗 rooms[cur_room].monsters_left
      ④ 到达 Boss 房 + boss_alive → 触发 Boss 战（走 _enter_stage_combat 现状战斗链路）

    dest：玩家原始输入（房间名/序号/图 id），内部统一解析（v141 审计 #8：
    本函数是目标解析唯一入口，_instance_move_route 直接透传，不再二次解析）。
    """
    st = inst_row["state"]
    if st.get("cleared"):
        yield event.plain_result(_T.static("inst_move.cleared"))
        return
    # 战斗进行中（mode != map）→ 不能移动（与野外战斗中禁止移动同规则）
    if st.get("mode") != "map":
        yield event.plain_result(_T.static("inst_move.in_battle"))
        return
    # 队长带队：仅队长可移动
    members = st.get("members") or []
    if str(qq_id) != str(st.get("leader")):
        _lead = self._player(group_id, st.get("leader")) or {}
        yield event.plain_result(
            _T.text("inst_move.not_leader", name=_lead.get('name', st.get('leader'))))
        return
    # 目标房间解析：序号（本图连通表）优先，其次房间名/id
    cur_sa = player.get("cur_subarea") or ""
    # v141 大陆隔离：优先从大陆实例读（克隆图），回退全局静态图
    _wid = st.get("world_id") or ""
    _inst = _worlds.get_instance_world(_wid) if _wid.startswith("inst:") else None
    cur_map = (_inst or {}).get("maps", {}).get((st.get("inst_id") or "").removeprefix("inst_"), {}) or _cat_space.MAP_BY_ID.get((st.get("inst_id") or "").removeprefix("inst_"), {})
    sas = cur_map.get("subareas") or []
    links = _maps.subarea_links(cur_map.get("id", ""), cur_sa) if cur_sa else []
    # 副本内不隐藏房间（v137 房间全可见），直接取连通表
    target_sa = None
    if isinstance(dest, str) and dest.isdigit():
        idx = int(dest)
        if 1 <= idx <= len(links):
            tid = links[idx - 1]
            target_sa = next((s for s in sas if s["id"] == tid), None)
    else:
        for s in sas:
            if dest in (s["name"], s["id"]):
                target_sa = s
                break
    if target_sa is None:
        names = "、".join(
            f"{i + 1}. {next((s['name'] for s in sas if s['id'] == lid), lid)}"
            for i, lid in enumerate(links)
        ) or "（无）"
        yield event.plain_result(
            _T.text("inst_move.room_list", names=names))
        return
    if target_sa["id"] == cur_sa:
        yield event.plain_result(_T.text("move.same_sa", map=cur_map.get('name', ''), sa=target_sa['name']))
        return
    if target_sa["id"] not in links:
        yield event.plain_result(
            _T.text("inst_move.not_linked", sa=target_sa['name']))
        return
    # 目标房间：rooms 存档（怪物池/资源池）——波次 3a 未实现则只做移动/展示
    rooms = st.get("rooms") or {}
    rstate = rooms.get(target_sa["id"]) or {}
    # 落点：全队 cur_subarea 同步
    for m in members:
        db.update_player(group_id, m, cur_subarea=target_sa["id"])
    db.save_battle(group_id, st["leader"], st)
    arrive_view = self._subarea_arrive(self._player(group_id, qq_id), cur_map, target_sa, group_id, qq_id)
    # v137 dungeon 修饰符：房间移动遇怪（消耗 monsters_left，打完不刷）
    # v164（鱼鱼拍板 2026-09-02）：移动遇怪改【必中】——房间怪物池非空就触发。
    # 原 discovery_agro 0.85 概率导致"走过房间没被拦"的观感（15% 落空），
    # 移动是副本推进主线，遇怪应确定；『探索』仍保持 discovery_agro 概率（主动探索可放空）。
    # v185：房间怪池剩余读点收口 instance_run（非空即遇怪）
    _hit = IR.monsters_left(st, target_sa["id"]) > 0
    if _hit:
        # 遇怪 → 弹出 1 只 → 构建敌方阵列 → 进战斗（现状 _enter_stage_combat 链路）
        # v141 审计 #7：死代码接线——consume_monster 弹出（原 _left.pop(0) 内联）
        _def = self.consume_monster(st, target_sa["id"])
        if _def is None:
            yield event.plain_result(arrive_view)
            return
        self._enter_stage_combat(group_id, st, _def, target_sa)
        db.save_battle(group_id, st["leader"], st)
        _mon = st.get("boss") or {}
        yield event.plain_result(
            _T.text("inst_move.ambush", arrive=arrive_view, name=target_sa['name'],
                     mon=_mon.get('name', '怪物'), footer=self._instance_battle_footer(st, group_id),
                     who=self._instance_turn_player_name(st, group_id))
        )
        return
    # Boss 房 + boss_alive → 触发 Boss 战（不消耗普通怪池）
    _dun = cur_map.get("dungeon") or {}
    _br = _dun.get("boss_room")
    _boss_alive = bool(rstate.get("boss_alive", False))
    if _br == target_sa["id"] and _boss_alive:
        boss_def = target_sa.get("boss")
        if boss_def:
            self._enter_stage_combat(group_id, st, boss_def, target_sa)
            rstate["boss_alive"] = False
            db.save_battle(group_id, st["leader"], st)
            _mon = st.get("boss") or {}
            yield event.plain_result(
                _T.text("inst_move.boss", arrive=arrive_view, name=target_sa['name'], boss=_mon.get('name', ''),
                         lv=_mon.get('lv', '?'), footer=self._instance_battle_footer(st, group_id),
                         who=self._instance_turn_player_name(st, group_id))
            )
            return
    # 无事到达
    yield event.plain_result(arrive_view)


def _travel_ambush(self, player: dict, target_map: dict, group_id=None, qq_id=None):
    """移动撞怪判定：返回撞到的怪物 dict 或 None——v181 P4-8 已下沉 travel.travel_ambush。

    生物趋避利害/副本分支/v130.7 越级线性档位逐行等价随迁；撞怪档位双轨
    （core/constants.MOVE_ENCOUNTER_CHANCE）本批先搬后统一，见 docs/archive/REFACTOR_P4_services.md §P4-8。
    """
    from .travel import travel_ambush
    return travel_ambush(player, target_map, group_id, qq_id,
                         main_kill_hook=self._main_kill_target_on_map)


async def portal_view(self, event: AstrMessageEvent, group_id, qq_id, player):
    portals = db.get_portals(qq_id)
    cur = player["cur_map"]
    lines = [_T.text("portal.head", n=len(portals), tot=len(PORTALS)), "━━━━━━━━━━━━"]
    # 当前地图
    if cur in PORTALS:
        p = PORTALS[cur]
        if cur in portals:
            lines.append(_T.text("portal.here_on", icon=p['icon'], name=p['name']))
        else:
            lines.append(_T.text("portal.here_off", icon=p['icon'], name=p['name']))
    else:
        lines.append(_T.static("portal.here_none"))
    lines.append("━━━━━━━━━━━━")
    if not portals:
        lines.append(_T.static("portal.none_yet"))
    else:
        lines.append(_T.static("portal.list_head"))
        # v101.30d #O26：坐骑折扣在列表标注（playtest 格温：显示 175 实际扣 140）
        mounts = player.get("mounts") or {}
        active_mk = mounts.get("active")
        disc = 0.0
        if active_mk and active_mk in _cat_life.MOUNT_BY_KEY:
            disc = float(_cat_life.MOUNT_BY_KEY[active_mk].get("discount", 0) or 0)
        for i, mid in enumerate(portals, 1):
            m = _cat_space.MAP_BY_ID.get(mid, {})
            p = PORTALS.get(mid, {})
            cost = _portals.portal_cost(m)
            shown = cost
            tag = ""
            if disc > 0:
                shown = max(_cat_life.ECON_CONFIG["portal_min_cost"], int(cost * (1 - disc)))
                tag = _T.text("portal.mount_disc", pct=int(disc*100))
            name = p.get("name", mid) if p else mid
            icon = p.get("icon", "🌌") if p else "🌌"
            lines.append(_T.text("portal.row", idx=i, icon=icon, name=name, map=m.get('name', '?'), cost=shown, tag=tag))
    lines.append("━━━━━━━━━━━━")
    lines.append(self._tip("portal"))
    yield event.plain_result("\n".join(lines))


async def portal_activate(self, event: AstrMessageEvent, group_id, qq_id, player):
    cur = player["cur_map"]
    if cur not in PORTALS:
        yield event.plain_result(_T.static("portal.act_none"))
        return
    # v87.17 子区域绑定：方碑矗立在首个子区域（广场），必须走到跟前才能激活
    _pm = _cat_space.MAP_BY_ID.get(cur, {})
    _first_sa = (_pm.get("subareas") or [None])[0]
    if _first_sa and player.get("cur_subarea") != _first_sa.get("id"):
        yield event.plain_result(
            _T.text("portal.act_far", icon=PORTALS[cur].get('icon', ''),
                name=PORTALS[cur].get('name', '方碑'), sa=_first_sa.get('name', '广场'),
                sa2=_first_sa.get('name', '广场'))
        )
        return
    p = PORTALS[cur]
    if cur in db.get_portals(qq_id):
        yield event.plain_result(_T.text("portal.act_done", icon=p['icon'], name=p['name']))
        return
    db.add_portal(qq_id, cur)
    m = _cat_space.MAP_BY_ID.get(cur, {})
    exp = max(20, int(m.get("lv", 1)) * 20)
    db.update_player(group_id, qq_id, exp=player["exp"] + exp)
    yield event.plain_result(
        _T.text("portal.act_ok", icon=p['icon'], name=p['name'], map=m.get('name', '?'), exp=exp,
            name2=p['name'])
    )


async def portal_travel(self, event: AstrMessageEvent, group_id, qq_id):
    dest = self._strip_cmd(event, "传送").strip()
    player = self._player(group_id, qq_id)
    if not dest:
        yield event.plain_result(_T.static("ptravel.usage"))
        return
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("ptravel.battle"))
        return
    portals = db.get_portals(qq_id)
    if not portals:
        yield event.plain_result(_T.static("ptravel.none"))
        return
    target = None
    if dest.isdigit():
        idx = int(dest)
        if 1 <= idx <= len(portals):
            target = _cat_space.MAP_BY_ID.get(portals[idx - 1])
        else:
            yield event.plain_result(_T.text("ptravel.no_idx", n=len(portals)))
            return
    else:
        for mid in portals:
            m = _cat_space.MAP_BY_ID.get(mid, {})
            p = PORTALS.get(mid, {})
            if dest in p.get("name", "") or dest in m.get("name", ""):
                target = m
                break
        if not target:
            # 未激活的祭坛名 → 提示未激活
            for mid, p in PORTALS.items():
                if dest in p.get("name", ""):
                    yield event.plain_result(_T.text("ptravel.not_act", icon=p['icon'], name=p['name']))
                    return
            yield event.plain_result(_T.text("ptravel.not_found", name=dest))
            return
    if target["id"] == player["cur_map"]:
        yield event.plain_result(_T.static("ptravel.here"))
        return
    cost = _portals.portal_cost(target)
    # v39 坐骑：骑乘中传送折扣
    mounts = player.get("mounts") or {}
    active_mk = mounts.get("active")
    if active_mk and active_mk in _cat_life.MOUNT_BY_KEY:
        disc = _cat_life.MOUNT_BY_KEY[active_mk].get("discount", 0)
        cost = max(_cat_life.ECON_CONFIG["portal_min_cost"], int(cost * (1 - disc)))
    if player["gold"] < cost:
        yield event.plain_result(_T.text("ptravel.gold_short", cost=cost, have=player['gold']))
        return
    # v86 子区域：传送落地目标图首个子区域
    tgt_sas = target.get("subareas") or []
    first_sa = tgt_sas[0] if tgt_sas else None
    db.update_player(group_id, qq_id, gold=player["gold"] - cost, cur_map=target["id"],
                     cur_subarea=first_sa["id"] if first_sa else "")
    db.add_visited(group_id, qq_id, target["id"])
    # v115 探索见闻：传送到达也记录子区域到访（H 提供，getattr 兜底）
    _rec_txt = ""
    _rec = getattr(_exploration, "exploration_record_visit", None)
    if _rec is not None and first_sa is not None:
        try:
            _rv = _rec(group_id, qq_id, target["id"], first_sa.get("id", ""))
            if _rv:
                _rwt = _rv.get("reward") or ""
                if _rwt:
                    _rec_txt = f"\n🎉 {_rwt}"
        except Exception:
            _rec_txt = ""
    # v95 #142：传送落地后清除对话会话（否则对话状态跨图残留，『前往』被"还在交谈中"拦截）
    db.clear_talk_state(group_id, qq_id)
    quest_lines = self._update_explore_quests(group_id, qq_id, target["id"])
    extra = ""
    if quest_lines:
        extra = "\n\n" + "\n".join(quest_lines)
    p = PORTALS.get(target["id"], {})
    pname = p.get("name", "方碑") if p else "方碑"
    picon = p.get("icon", "🌌") if p else "🌌"
    yield event.plain_result(
        _T.text("ptravel.ok", map=target['name'], picon=picon, pname=pname, cost=cost,
            desc=target['desc'], extra=extra, rec=_rec_txt)
    )


def _update_explore_quests(self, group_id, qq_id, map_id):
    """到达子区域时检查 explore 型任务（P4-2 壳：转调 services.quests_flow.update_explore_quests）"""
    from . import quests_flow as qf
    return qf.update_explore_quests(group_id, qq_id, map_id)


async def quest_accept(self, event: AstrMessageEvent, group_id, qq_id):
    """v95.7 #38：『接取任务』/『接取 <任务名>』——当前地图有发布 NPC 时直接接取，否则提示位置"""
    raw = self._strip_cmd(event, "接取").strip()
    player = self._player(group_id, qq_id)
    quests = db.get_quests(group_id, qq_id)
    # 主线（pending 可接）
    main_id = quests.get("main_quest")
    mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == main_id), None) if main_id else None
    # v123d：『接取 <序号>』——先按无参数列表全局序号映射到任务名（参数统一铁律：
    # 列表展示序号即可选），映射后统一走下方名字分支（主线/支线都命中）
    if raw and raw.isdigit():
        _avail = self._available_quest_list(player, quests, mq)
        idx = int(raw)
        if 1 <= idx <= len(_avail):
            raw = _avail[idx - 1]["name"]
        else:
            yield event.plain_result(_T.text("quest.no_idx", total=len(_avail)))
            return
    if mq:
        st = quests.get("main_status", "pending")
        if st == "pending" and (not raw or raw in (mq["name"], "任务", "主线")):
            npc = _cat_quests.NPCS.get(mq["giver"]) or _wild.ALL_WILD.get(mq["giver"]) or {}
            if npc.get("map") == player["cur_map"]:
                lines = self._take_main_quest(group_id, qq_id, mq["giver"], npc)
                yield event.plain_result("\n".join(lines))
                return
            giver_map = _cat_space.MAP_BY_ID.get(npc.get("map", ""), {}).get("name", "？")
            yield event.plain_result(_T.text("quest.main_giver", name=mq['name'], npc=npc.get('name', '？'), where=giver_map))
            return
        # v95.8 #47：主线进行中/待交付时，无参数『接取』不应静默去接支线
        # v95.14：『接取任务』/『接取 主线』（raw=任务/主线）等同无参数，同样提示主线状态
        if not raw or raw in ("任务", "主线"):
            if st == "ready":
                yield event.plain_result(_T.text("quest.main_ready", name=mq['name'],
                                             where=(_cat_quests.NPCS.get(mq['giver']) or _wild.ALL_WILD.get(mq['giver']) or {}).get('name', '发布人')))
            else:
                yield event.plain_result(_T.text("quest.main_running", name=mq['name']))
            return
        # v95.20 #103：指名当前主线名但非 pending → 明确提示进行中/待交付
        # （此前会落到底部"可接取任务列表"分支，回显无关支线误导玩家）
        if raw == mq["name"]:
            if st == "ready":
                yield event.plain_result(_T.text("quest.main_ready", name=mq['name'],
                                             where=(_cat_quests.NPCS.get(mq['giver']) or _wild.ALL_WILD.get(mq['giver']) or {}).get('name', '发布人')))
            else:
                yield event.plain_result(_T.text("quest.main_dup", name=mq['name']))
            return
    # 支线：必须指名道姓才接（v95.8 #47：无参数/『接取 任务』不再静默接支线）
    if raw and raw not in ("任务", "主线"):
        for sq in _cat_quests.SIDE_QUESTS:
            if raw not in (sq["name"],):
                continue
            # v95.27：先判已接（此前 continue 跳过后 raw 落到底部无关列表，提示不明确）
            if sq["id"] in (quests.get("side") or {}):
                yield event.plain_result(_T.text("quest.accepted", name=sq['name']))
                return
            # v104 审计 P1-1：『接取』指令同样校验 min_level
            # （此前只有 _offer_side_quests 自动接取路径校验，Lv.1 可直接接走 Lv.40 雾中灯塔）
            if sq.get("min_level") and player["level"] < sq["min_level"]:
                yield event.plain_result(
                    _T.text("quest.lv_short", name=sq['name'], need=sq['min_level'], lv=player['level'])
                )
                return
            # v124 链式支线：unlock 前置未满足 → 提示前置未完成
            if not self._sq_unlocked(quests, sq):
                _pre = sq.get("unlock")
                _pn = []
                if isinstance(_pre, list):
                    _pn = [next((q["name"] for q in _cat_quests.SIDE_QUESTS if q["id"] == x.get("id")), "前置任务") for x in _pre if isinstance(x, dict)]
                elif isinstance(_pre, dict):
                    _pn = [next((q["name"] for q in _cat_quests.SIDE_QUESTS if q["id"] == _pre.get("id")), "前置任务")]
                yield event.plain_result(
                    _T.text("quest.need_prev", name=sq['name'], prev=_pn[0] if _pn else '前置任务')
                )
                return
            # v124 隐藏线：require_stats 计数门槛
            if not self._sq_stats_met(player, sq):
                _rs = sq.get("require_stats") or {}
                _need = ", ".join(f"{k} {v}次" for k, v in _rs.items())
                yield event.plain_result(
                    _T.text("quest.secret", cond=_need)
                )
                return
            # v113 种族限制：require_race 指定血脉（隐藏线试炼）——非该种族拒绝接取
            if sq.get("require_race"):
                _rr = sq["require_race"]
                _cur = player.get("race") or "human"
                if _cur != _rr:
                    _rcn = (_cat_core.RACES.get(_rr) or {}).get("name", "对应血脉")
                    _ccn = (_cat_core.RACES.get(_cur) or {}).get("name", "未知血脉")
                    yield event.plain_result(
                        _T.text("quest.blood", name=sq['name'], need=_rcn, mine=_ccn)
                    )
                    return
            # v97.1 告示委托（board: true）：在告示板所在的子区域接取，不要求发布 NPC 在场
            if sq.get("board"):
                prop_ids = _pois.subarea_props(player["cur_map"], player.get("cur_subarea") or "")
                has_board = any(
                    _pois.prop_entry(e)[0] == "notice_board" for e in prop_ids
                )
                if not has_board:
                    yield event.plain_result(
                        _T.text("quest.need_board", name=sq['name']))
                    return
                # v95.27 修复：告示板只接指定委托，不连带同 giver 的其他支线
                # （此前走 _offer_side_quests 按 giver 全接，寻猫·虎斑顺带接了史莱姆果冻）
                side = dict(quests.get("side", {}))
                side[sq["id"]] = {"status": "active", "progress": {}}
                quests["side"] = side
                db.save_quests(group_id, qq_id, quests)
                lines = [
                    _T.text("quest.side_head", name=sq['name'], tail=sq['desc']),
                    _T.text("quest.reward", exp=sq['reward_exp'], gold=sq['reward_gold']),
                    _T.text("quest.objective", goal=self._obj_text(sq['objective'])),
                ]
                yield event.plain_result("\n".join(lines))
                return
            npc = _cat_quests.NPCS.get(sq["giver"]) or _wild.ALL_WILD.get(sq["giver"]) or {}
            if npc.get("map") == player["cur_map"]:
                # v95r65 #295：指名接取只接该任务（此前调 _offer_side_quests 按 giver 全接，
                # 会连带接取同 giver 的告示板委托——『接取 史莱姆果冻』顺带接走『寻猫·虎斑』）
                side = dict(quests.get("side", {}))
                side[sq["id"]] = {"status": "active", "progress": {}}
                quests["side"] = side
                db.save_quests(group_id, qq_id, quests)
                lines = [
                    _T.text("quest.side_head", name=sq['name'], tail=sq['desc']),
                    _T.text("quest.reward", exp=sq['reward_exp'], gold=sq['reward_gold']),
                    _T.text("quest.objective", goal=self._obj_text(sq['objective'])),
                ]
                yield event.plain_result("\n".join(lines))
                return
            giver_map = _cat_space.MAP_BY_ID.get(npc.get("map", ""), {}).get("name", "？")
            yield event.plain_result(_T.text("quest.side_giver", name=sq['name'], npc=npc.get('name', '？'), where=giver_map))
            return
    # 无参数 → 列出当前地图可接任务（主线 pending + 未接支线）
    available = self._available_quest_list(player, quests, mq)
    if available:
        lines = [_T.static("quest.list_head"), "━━━━━━━━━━━━"]
        lines += [f"{i:>2}. 📜 {a['line']}" for i, a in enumerate(available, 1)]
        lines.append(self._tip("accept"))
        yield event.plain_result("\n".join(lines))
        return
    # v95.15 #70：指名接取但上面没匹配到 → 明确提示未找到/已接取
    if raw and raw not in ("任务", "主线"):
        all_names = [q["name"] for q in _cat_quests.SIDE_QUESTS] + [q["name"] for q in _cat_quests.MAIN_QUESTS]
        if raw in all_names:
            yield event.plain_result(_T.text("quest.already", name=raw))
        else:
            yield event.plain_result(_T.text("quest.not_found", name=raw))
        return
    yield event.plain_result(_T.static("quest.none"))


def _sq_unlocked(self, quests, sq):
    """v124 链式支线：unlock 前置解锁检查（P4-2 壳：转调 services.quests_flow.sq_unlocked）"""
    from . import quests_flow as qf
    return qf.sq_unlocked(quests, sq)


def _sq_stats_met(self, player, sq):
    """v124 隐藏线/副业线：require_stats 动作计数门槛（P4-2 壳：转调 services.quests_flow.sq_stats_met）"""
    from . import quests_flow as qf
    return qf.sq_stats_met(player, sq)


def _available_quest_list(self, player, quests, mq) -> list:
    """当前地图可接取任务列表（P4-2 壳：转调 services.quests_flow.available_quest_list——本体含 sq_unlocked/sq_stats_met 收敛）"""
    from . import quests_flow as qf
    return qf.available_quest_list(player, quests, mq)


async def quest_abandon(self, event: AstrMessageEvent, group_id, qq_id):
    """『放弃 <序号>』——放弃进行中的支线/每日任务；主线走『任务』面板提示不可弃。

    序号与任务面板（quest_view）全局编号一致：侧支线 1..S，每日 S+1..S+D。
    已完成任务/序号越界/无任务 → 给明确提示。
    """
    raw = self._strip_cmd(event, "放弃").strip()
    quests = db.get_quests(group_id, qq_id)
    # 侧支线（按 dict 顺序，与面板一致；done 不算可放弃位）
    side = dict(quests.get("side", {}) or {})
    side_items = [(sid, sq) for sid, sq in side.items()
                  if sq.get("status", "active") != "done"]
    # 每日（剔除元数据键）
    daily = dict(quests.get("daily", {}) or {})
    daily_items = [(dk, dq) for dk, dq in daily.items() if dk not in _DAILY_META_KEYS]
    total = len(side_items) + len(daily_items)
    index_able = raw and raw.isdigit()
    if not index_able:
        # v116 §3.4：主线不可放弃——指名主线/『主线』字样给明确拒绝提示
        main_id = quests.get("main_quest")
        mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == main_id), None) if main_id else None
        if raw in ("主线", "main") or (mq and raw == mq["name"]):
            yield event.plain_result(_T.static("abandon.main"))
            return
        if total == 0:
            yield event.plain_result(_T.static("abandon.none"))
            return
        yield event.plain_result(_T.text("abandon.usage", total=total))
        return
    idx = int(raw)
    if not (1 <= idx <= total):
        yield event.plain_result(_T.text("abandon.no_idx", idx=idx, total=total))
        return
    # 主线不可放弃：序号全部落在侧支线/每日，主线本来就不参与编号；单独拦截侧支线里的"主线位"不存在
    if 1 <= idx <= len(side_items):
        sid, sq = side_items[idx - 1]
        del side[sid]
        quests["side"] = side
        qname = next((q["name"] for q in _cat_quests.SIDE_QUESTS if q["id"] == sid), "该支线")
        db.save_quests(group_id, qq_id, quests)
        yield event.plain_result(_T.text("abandon.done", name=qname))
        return
    # 每日任务
    dk, dq = daily_items[idx - len(side_items) - 1]
    del daily[dk]
    quests["daily"] = daily
    db.save_quests(group_id, qq_id, quests)
    yield event.plain_result(_T.text("abandon.done", name=dq.get('name', '该每日任务')))


async def daily(self, event: AstrMessageEvent, group_id, qq_id, player):
    if self._is_redname(qq_id):
        yield event.plain_result(_T.static("daily.redname"))
        return
    # v181 P4-1 试点：抽取/衰减/发布已收敛至 services.quests.draw_daily（红名守卫留命令层，
    # 上限/已有任务/跨天清理/面板行拼装全在 service 内，逐行原样搬迁）
    from .profession_quests import draw_daily
    ok, text = draw_daily(group_id, qq_id, player)
    yield event.plain_result(text)


def _daily_pool(self, player, dq):
    """（P4-1 兼容壳：转调 game/services/quests.daily_pool——『每日』抽取已改 services 直调）"""
    from .profession_quests import daily_pool as _daily_pool_impl
    return _daily_pool_impl(player, dq)


def _bump_daily_progress(self, group_id, qq_id, obj_key, lines=None):
    """v104 M20 修复：非击杀类每日任务进度推进（行会委托=完成支线 / 采集任务=采集材料）。

    与 combat.py 击杀分支（kill_any/kill_elite/kill_boss）互补：
    匹配 objective[obj_key] 的每日任务 +1，达标即发奖并从今日列表移除。
    调用点：_complete_side_quest（complete_side）、interact_prop 材料元素（collect_any）。
    （P4-1：本体已收敛 services.quests.bump_daily_progress，本方法为兼容壳。
    模块级 _bump_daily_progress 同款壳在文件头；此处保留因调用点是 self._bump_daily_progress。）
    """
    from .profession_quests import bump_daily_progress as _bump_daily_progress
    _bump_daily_progress(group_id, qq_id, obj_key, lines)


def _home_view(self, group_id, qq_id, cur_map_id):
    """v68 家地图展示：home_{owner} → 家的定制面板"""
    owner_qid = cur_map_id[len("home_"):]
    owner = db.get_player(group_id, owner_qid)
    if not owner:
        return _T.static("home.owner_left")
    is_mine = str(owner_qid) == str(qq_id)
    deed = owner.get("deed", "") or ""
    prop = _cat_life.PROPERTIES.get(deed, {})
    lines = [_T.static("home.head_mine") if is_mine
             else _T.text("home.head_other", name=owner['name'])]
    if prop:
        dlv = int(owner.get("deed_lv", 1) or 1)
        hl = _cat_life.HOUSE_LEVELS.get(dlv, _cat_life.HOUSE_LEVELS[1])
        lines.append(f"{prop['name']}({hl['name']} Lv.{dlv})")
        lines.append(f"　{prop['desc']}")
    lines.append("━━━━━━━━━━━━")
    # 此地玩家
    here = [p for p in db.get_group_players(group_id).values() if p.get("cur_map") == cur_map_id]
    if here:
        lines.append(_T.static("home.people"))
        for p in here:
            lines.append(f"  {p['name']} Lv.{p['level']}")
    # 铺面摊位
    stalls = db.market_list(group_id, cur_map_id)
    if stalls:
        lines.append(_T.static("home.stall_items"))
        for s in stalls:
            sname = "你" if str(s["seller"]) == str(qq_id) else (owner["name"] if str(s["seller"]) == str(owner_qid) else s["seller"])
            lines.append(f"  #{s['id']} {s['item_data'].get('name', '?')} ｜ {self._stall_label(s)} ｜ {sname}")
        lines.append(self._tip("home_stall"))
    else:
        # v104R3 P2：木屋(0 挂机位)不提示摆摊开张——与铺面挂机位实现对齐(25 章房产案)
        _odlv = int(owner.get("deed_lv", 1) or 1)
        _oslots = _cat_life.HOUSE_LEVELS.get(_odlv, _cat_life.HOUSE_LEVELS[1]).get("stall_slots", 0)
        if _oslots > 0:
            lines.append(_T.static("home.stall_owner_hint"))
        else:
            lines.append(_T.static("home.stall_locked_hint"))
    # 仓库（自己的家）
    if is_mine:
        storage = self._home_storage_load(group_id, qq_id)
        dlv = int(owner.get("deed_lv", 1) or 1)
        hl = _cat_life.HOUSE_LEVELS.get(dlv, _cat_life.HOUSE_LEVELS[1])
        lines.append(_T.text("home.storage_line", cur=len(storage), cap=hl['storage']))
        if hl.get("stall_slots"):
            lines.append(_T.text("home.stall_slots", n=hl['stall_slots']))
    lines.append("━━━━━━━━━━━━")
    lines.append(self._tip("home"))
    return "\n".join(lines)


def _current_npcs(self, player):
    """v86 子区域：当前所在位置可交互的 NPC 列表(子区域优先，回退地图级)。
    v95.30 随机性：酱油 NPC 按 游走/概率/时段 过滤（功能 NPC 恒在）。
    ★ U1-I4 L5：查表走引擎 `Lookup`（**城镇单表** —— 三份列表实现成员集合不同，口径分歧 ①：
    本处只含 `NPCS`、一律过滤；含 `HIDDEN_NPCS` 并豁免过滤的是 `_map_blocks`/`_hurry_section`）。"""
    cur_map = player["cur_map"]
    m = _cat_space.MAP_BY_ID.get(cur_map, {})
    sa_id = player.get("cur_subarea") or ""
    for sa in (m.get("subareas") or []):
        if sa["id"] == sa_id:
            return [row for nid, row, _t in _LOOKUP_TOWN.rows(sa.get("npcs") or [])
                    if _wild.town_npc_visible(nid, row, sa_id)]
    return [row for _nid, row, _t in _LOOKUP_TOWN.rows(m.get("npcs", []))]


def _present_wild_hints(self, group_id, qq_id, cur_map) -> list:
    """v127.5 限时NPC：当前地图（map 级，全图都算）在场限时野外NPC 显示行。

    偶遇后挂 timed events，倒计时内地图/位置可见并带 ⏳ 剩余分钟；过期
    list_timed 惰性清除 → 天然消失（显示与对话同时，铁律）。
    返回例：["  🧭游商·老马 ⏳剩60分", ...]（2 空格缩进，与普通 NPC 行一致）。
    """
    lines = []
    evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",
                       data_match={"map": cur_map})
    for ev in evs:
        nid = ev.get("data", {}).get("npc_id") or ""
        wnpc = _wild.ALL_WILD.get(nid)
        if not wnpc:
            continue
        remain_min = minutes_left(ev.get("remain", 0))  # max(1, ceil(remain/60)) —— 引擎口径
        lines.append(_T.text("npclist.wild_hint", icon=wnpc.get('icon', ''), name=wnpc.get('name', nid),
                         remain=remain_min))
    return lines


def _start_talk_list(self, group_id, qq_id) -> list:
    """当前地图 NPC 列表（带序号展示；交谈用『对话 <名字>』/『对话 <序号>』，v123a 起裸数字不再直接找 NPC）。『对话』空参共用。"""
    player = self._player(group_id, qq_id)
    if player and player["cur_map"].startswith("home_"):
        return [_T.static("npc.home_empty")]
    npcs = self._current_npcs(player) if player else []
    # v127.5 限时NPC：在场野外旅人并入裸『对话』列表（排城镇 NPC 之后，带序号可对话）
    wild_evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",
                            data_match={"map": player["cur_map"]}) if player else []
    if not npcs and not wild_evs:
        return [_T.static("npclist.empty")]
    lines = [_T.static("npclist.head")]
    # 编号走引擎 `Presence.slots`：静态 1..N、限时续号 N+1..；查不到表的限时项**跳号**（逐字保留）
    for i, kind, item in _PRESENCE.slots(npcs, wild_evs):
        if kind == "static":
            n = item
            lines.append(f"{i:>2}. {n['icon']}{n['name']}({n['title']})")
            continue
        ev = item
        nid = ev.get("data", {}).get("npc_id") or ""
        wnpc = _wild.ALL_WILD.get(nid)
        if not wnpc:
            continue
        remain_min = minutes_left(ev.get("remain", 0))  # 与 `_present_wild_hints` 同口径
        lines.append(_T.text("npclist.wild_row", i=i, icon=wnpc.get('icon', ''), name=wnpc.get('name', nid),
                         remain_min=remain_min))
    lines.append(self._tip("npc_list"))
    return lines


def _find_npc_in_map(self, player, name_key):
    """在当前地图找 NPC(子区域优先，回退地图级)，返回 (npc_id, npc_dict) 或 (None, None)。

    v95.30 随机性：酱油 NPC 名字匹配但今天不可见（游走别处/概率未出/时段不符）
    → 仍返回 (nid, npc)（由调用方给"不在"提示），并置 player['_npc_absent'] 供提示。
    """
    cur_map = player["cur_map"]
    m = _cat_space.MAP_BY_ID.get(cur_map, {})
    sa_id = player.get("cur_subarea") or ""
    player.pop("_npc_absent", None)
    # 子区域 NPC 优先
    for sa in (m.get("subareas") or []):
        if sa["id"] == sa_id:
            for nid in sa.get("npcs", []):
                npc = _LOOKUP_TOWN.first(nid)[0]
                if npc and (name_key in npc["name"] or name_key in nid):
                    if not _wild.town_npc_visible(nid, npc, sa_id):
                        player["_npc_absent"] = (nid, npc, sa_id)
                    return nid, npc
            break
    # 地图级 NPC（含其他子区域）
    for nid in m.get("npcs", []):
        npc = _LOOKUP_TOWN.first(nid)[0]
        if npc and (name_key in npc["name"] or name_key in nid):
            if not _wild.town_npc_visible(nid, npc, sa_id):
                player["_npc_absent"] = (nid, npc, sa_id)
            return nid, npc
    return None, None


def _town_npc_absent_hint(self, nid, npc, sa_id):
    """v95.30：酱油 NPC 名字命中但当前不可见 → 解释原因（游走去向 / 时段 / 概率未出）。
    显示必须可触发铁律：『找』必须给出明确信息。"""
    name = npc.get("name", "他")
    # B 游走：今天在别的子区域 → 指路
    today_sa = _wild.town_npc_day_sa(nid, npc, sa_id)
    if today_sa != sa_id:
        m = self._player_map_name(sa_id) or ""
        sa_name = self._subarea_name(today_sa)
        if sa_name:
            return _T.text("npcabsent.roam", name=name, sa_name=sa_name)
    # D 时段
    per = npc.get("period")
    if per:
        period_cn = (PERIOD_CN.get(_tw.current_period(), "") or "").strip()
        return _T.text("npcabsent.period", name=name, period=period_cn)
    # C 概率未出
    return _T.text("npcabsent.chance", name=name)


def _player_map_name(self, sa_id):
    """按子区域 id 找所属地图名（用于游走提示）"""
    for mid, m in _cat_space.MAP_BY_ID.items():
        for sa in (m.get("subareas") or []):
            if sa["id"] == sa_id:
                return m.get("name", "")
    return ""


def _subarea_name(self, sa_id):
    """按子区域 id 找显示名"""
    for mid, m in _cat_space.MAP_BY_ID.items():
        for sa in (m.get("subareas") or []):
            if sa["id"] == sa_id:
                return sa.get("name", "")
    return ""


def _find_wild_npc(self, player, name_key, group_id, qq_id):
    """9.4：在当前地图找野外 NPC（含 roam 定位 + 出现条件判定）。
    名字匹配但今天不在/条件不满足 → 返回 (None, None)，由调用方提示。"""
    cur = player["cur_map"]
    for nid, wnpc in _wild.ALL_WILD.items():
        # v95.4：与 _find_npc_in_map 一致的子串匹配（『找 游商』→『游商·老马』）
        if name_key not in (wnpc.get("name") or ""):
            continue
        if _wild.npc_map_id(nid, wnpc) != cur:
            return None, None
        if not _wild.wild_npc_findable(nid, wnpc, player, group_id, qq_id):
            return None, None
        wnpc = dict(wnpc)
        wnpc.setdefault("title", "游历于野外的旅人")
        return nid, wnpc
    return None, None


def _wild_unseen_hint(self, player, name_key, group_id, qq_id):
    """v95.15 #71：野外 NPC 名字命中、在本图但当前条件(时段/季节/天气/解锁)不满足
    → 提示出现条件，区分『NPC 在但需定位』vs『当前时段 NPC 未出现』；无命中返回 None"""
    cur = player["cur_map"]
    for nid, wnpc in _wild.ALL_WILD.items():
        if name_key not in (wnpc.get("name") or "") and name_key not in nid:
            continue
        if _wild.npc_map_id(nid, wnpc) != cur:
            continue  # 今天不在这张图 → 交给方向提示
        if _wild.wild_npc_findable(nid, wnpc, player, group_id, qq_id):
            continue  # 条件满足（概率/保底问题），不归这里管
        label = self._wild_cond_label(wnpc)
        period = (PERIOD_CN.get(_tw.current_period(), "") or "").strip()
        return _T.text("find.unseen_hint", name=name_key, label=label, period=period)
    return None


def _npc_direction_hint(self, player, name_key):
    """v95.8 #51：当前地图没找到 NPC 时，全局搜位置给方向提示；找不到返回 None
    v59.#51：同名 NPC 分散多城镇时，玩家所在地图有命中 → 只列当前地图位置（单一方向），
    不再三城镇并列无方位（实测『找 城主』曾并列白鹿城/铁港城/珍珠城）"""
    cur = player["cur_map"]
    hits = []
    for nid, npc in _cat_quests.NPCS.items():
        if name_key in (npc.get("name") or "") or name_key in nid:
            hits.append((nid, npc))
    for nid, wnpc in _wild.ALL_WILD.items():
        if name_key in (wnpc.get("name") or "") or name_key in nid:
            hits.append((nid, wnpc))
    # v101.29：野外精英/Boss 名也纳入搜索（任务目标常是强敌而非 NPC，
    # 如『找 铁牙』→ 丘陵狼王·铁牙在丘陵顶——旧代码只搜 NPC 表会命中同名
    # "地下守卫·铁牙/卫兵·铁牙" 给出错误方向）。精英/Boss 元组格式
    # (id, 显示名, role, lv, skills, drops)，伪 nid 用 "map:subarea" 便于定位。
    for mid, m in _cat_space.MAP_BY_ID.items():
        for sa in (m.get("subareas") or []):
            for ent in (sa.get("elite"), sa.get("boss")):
                if not ent:
                    continue
                ename = ent[1] if len(ent) > 1 else ""
                if ename and (name_key in ename or ename in name_key):
                    hits.append((f"{mid}:{sa['id']}", {"name": ename, "map": mid}))
    if not hits:
        return None
    locs = []  # (map_id, subarea_id 或 None, 显示位置)
    for nid, npc in hits:
        m_id = npc.get("map") or ""
        m = _cat_space.MAP_BY_ID.get(m_id, {})
        m_name = m.get("name", m_id or "未知之地")
        sa_name = ""
        sa_id = None
        if ":" in nid:
            # v101.29 精英/Boss 条目：nid 格式 "map_id:subarea_id"
            _said = nid.split(":", 1)[1]
            sa_id = _said
            for sa in (m.get("subareas") or []):
                if sa["id"] == _said:
                    sa_name = sa.get("name", "")
                    break
        else:
            for sa in (m.get("subareas") or []):
                if nid in (sa.get("npcs") or []):
                    sa_name = sa.get("name", "")
                    sa_id = sa["id"]
                    break
        locs.append((m_id, sa_id, f"{m_name}·{sa_name}" if sa_name else m_name))
    cur_sa = player.get("cur_subarea") or ""
    in_here = cur in {m_id for m_id, _, _ in locs}
    # v95.25 #135：前缀明确"在/不在你所在的地图"，不再用误导性的"你所在的地图的…"
    # v113.5 O90：同图但目标在别的子区域时，原文案说"就在你所在的「目标子区域」一带"
    # 把目标位置说成玩家所在（误导定位）——同图不同子区域统一走"（你现在不在这里）"样式
    # （对齐地精商人版文案）；子区域未知的 NPC 按旧行为视为同处
    if in_here:
        same_sa = [l for m_id, sa_id, l in locs
                   if m_id == cur and (not sa_id or not cur_sa or sa_id == cur_sa)]
        if same_sa:
            here_uniq = list(dict.fromkeys(same_sa))
            return _T.text("npcwhere.here", name=name_key, where='、'.join(here_uniq))
    uniq = list(dict.fromkeys(l for _, _, l in locs))
    return _T.text("npcwhere.else", name=name_key, where='、'.join(uniq))


def _npc_dialogue(self, group_id, qq_id, npc_id, npc):
    """按主线进度返回 NPC 对话(主线完成后不再重复初始台词)。
    v95.30 A 随机台词：酱油 NPC 配置了 lines 多条 → 每天换一条（日期哈希全服一致）。"""
    base = npc.get("dialogue", "……")
    # v95.30 酱油 NPC 随机台词（无功能 → 不参与主线逻辑）
    if not npc.get("funcs"):
        return _wild.town_npc_dialogue(npc_id, npc, base)
    # 只对发布主线的 NPC 动态化
    if "quest" not in npc.get("funcs", []):
        return base
    quests = db.get_quests(group_id, qq_id)
    main_id = quests.get("main_quest")
    # 主线全部完成（main_quest=None 且有完成记录）→ 用完成台词
    if not main_id and quests.get("completed_main"):
        return npc.get("dialogue_done", base)
    # 当前主线不是这位 NPC 发布的 → 保持初始台词（提示语会在任务逻辑里给出）
    mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == main_id), None)
    if mq and mq["giver"] != npc_id:
        return base
    # 主线已接取或进行中 → 初始台词（任务提示在 _take_main_quest 里）
    return base


def _take_main_quest(self, group_id, qq_id, npc_id, npc):
    """从 NPC 接主线任务；返回通知行列表（P4-2 壳：转调 services.quests_flow.take_main_quest）"""
    from . import quests_flow as qf
    return qf.take_main_quest(group_id, qq_id, npc_id, npc)


def _obj_text(self, obj):
    """v124 目标单行摘要（取接取通知/交付面板的单行目标行；转调引擎目标行骨架）。

    ★ U1-D2 L4：本段与 `quests_flow.obj_text` 原为**逐字同文的两份**（DESIGN §2.1 Q1），
    现统一为**单点模板**（`quests_flow._one_text_of`）—— 行文一字未改，只是不再各写一份。
    """
    from . import quests_flow as qf
    return qf.obj_text(obj)


def _obj_text_lines_of(type_key, obj, prog, st):
    """交付面板的**多行**目标模板（复合目标逐行；行文逐字保留，不出的型 → None）。

    本出口自己的 `text_of`：`find` 行按任务状态分「已找到 / (探索有概率遇到) / （未找到）」
    三态（DESIGN §2.1 Q1 —— 与 `obj_text` 单行口径**故意不同**，不许合并）。
    """
    from . import quests_flow as qf
    if not obj.get(type_key):
        return None
    if type_key == "kill":
        return _T.text("objline.kill", name=obj['kill'], n=qf._OBJECTIVES.need_of(obj, 'kill'))
    if type_key == "collect":
        # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError
        return _T.text("objline.collect", name=obj['collect'], n=qf._OBJECTIVES.need_of(obj, 'collect'))
    if type_key == "explore":
        return _T.text("objline.explore", map=_cat_space.MAP_BY_ID.get(obj['explore'], {}).get('name', '？'))
    if type_key == "find":
        _mname = _cat_space.MAP_BY_ID.get(obj.get("map", ""), {}).get("name", "")
        if st == "ready":
            if _mname:
                return _T.text("objline.find_ready_map", map=_mname, name=obj['find'])
            return _T.text("objline.find_ready", name=obj['find'])
        if _mname:
            return _T.text("objline.find_elsewhere", map=_mname, name=obj['find'])
        return _T.text("objline.find_missing", name=obj['find'])
    if type_key == "use":
        return _T.text("objline.use", name=obj['use'])
    if type_key == "talk":
        npc = _cat_quests.NPCS.get(obj["talk"], {})
        return _T.text("objline.talk", name=npc.get('name', '？'))
    return None


def _obj_text_lines(self, obj, st=None):
    """v124.2 复合 objective 逐行渲染（如 s18 kill 腐牙萨满·嚎骨 + find 白桦 两行都显示）。
    find 行按任务状态标 已找到/未找到（find 无进度存档，以 ready 态为准）；
    纯 find 委托（有 map）保留『探索有概率遇到』机制提示，与原 _obj_text 文案一致。

    ★ U1-D2 L4：三份目标行渲染的**多行**那一路 —— 行序/覆盖面走引擎目标行骨架
    （复合目标全出、行序 = 内容侧声明序），行文仍由本出口的 `_obj_text_lines_of` 给。
    """
    from . import quests_flow as qf
    return qf._obj_lines(obj, state=st, text_of=_obj_text_lines_of) or ["？"]


def _quest_reputation(self, group_id, qq_id, npc_id):
    """完成任务时给对应势力加声望，返回提示行（P4-2 壳：转调 services.quests_flow.quest_reputation）"""
    from . import quests_flow as qf
    return qf.quest_reputation(group_id, qq_id, npc_id)


def _wild_cond_label(self, npc: dict) -> str:
    """野外 NPC 出现条件 → 中文标签(见闻录/时间面板用)"""
    cond = npc.get("condition", {})
    labels = []
    t = cond.get("time")
    if t:
        tm = {"morning": _T.static("time_name.morning"), "day": _T.static("time_name.day"), "evening": _T.static("time_name.evening"), "night": _T.static("time_name.night")}
        labels.append("/".join(tm.get(x, x) for x in t) + _T.static("wildcond.appear"))
    s_ = cond.get("season")
    if s_:
        sm = {"spring": _T.static("season_cn.spring"), "summer": _T.static("season_cn.summer"), "autumn": _T.static("season_cn.autumn"), "winter": _T.static("season_cn.winter")}
        labels.append("/".join(sm.get(x, x) for x in s_) + _T.static("wildcond.season_suffix"))
    w = cond.get("weather")
    if w:
        wm = {"rain": _T.static("weather_cn.rain"), "storm": _T.static("weather_cn.storm"), "snow": _T.static("weather_cn.snow"), "fog": _T.static("weather_cn.fog"), "sunny": _T.static("weather_cn.sunny")}
        labels.append(wm.get(w, w) + _T.static("wildcond.appear"))
    if cond.get("min_level"):
        labels.append(f"Lv.{cond['min_level']}+")
    if npc.get("cycle"):
        labels.append(_T.text("wildcond.cycle", cycle=npc['cycle']))
    if npc.get("chance"):
        labels.append(_T.text("wildcond.chance", pct=int(npc['chance']*100)))
    if npc.get("unlock"):
        labels.append(_T.static("wildcond.locked"))
    return "，".join(labels) if labels else _T.static("wildcond.anytime")


async def time_cmd(self, event: AstrMessageEvent, group_id, qq_id, player):
    cur = player["cur_map"]
    summary = _tw.time_weather_summary(cur)
    cur_map = _cat_space.MAP_BY_ID.get(cur, {})
    lines = [
        _T.static("time.title"),
        f"⏰ {summary}",
        _T.text("time.location", name=cur_map.get('name', '未知区域')),
        "━━━━━━━━━━━━",
    ]
    hints = _wild.nearby_hints(group_id, qq_id, player, cur)
    if hints:
        lines.append(_T.static("time.hints_head"))
        for nid, npc in hints[:5]:
            lines.append(f"  {npc['icon']}{npc['name']}({self._wild_cond_label(npc)})")
        lines.append(self._tip("explore"))
    else:
        lines.append(_T.static("time.hints_none"))
    yield event.plain_result("\n".join(lines))


async def wild_notes(self, event: AstrMessageEvent, group_id, qq_id, player):
    met = _wild.met_wild(group_id, qq_id)
    if not met:
        yield event.plain_result(
            _T.static("notes.empty")
        )
        return
    lines = [_T.text("notes.head", n=len(met), tot=len(_wild.ALL_WILD)), "━━━━━━━━━━━━"]
    for nid in met:
        npc = _wild.ALL_WILD.get(nid)
        if not npc:
            continue
        lines.append(f"{npc['icon']}{npc['name']}")
        lines.append(f"　　{npc['desc']}")
        lines.append(f"　　🕐 {self._wild_cond_label(npc)}")
    lines.append(_T.static("notes.tip"))
    yield event.plain_result("\n".join(lines))


async def npc_quick_dialog(self, event: AstrMessageEvent, group_id, qq_id):
    """裸数字消费链：对话树选项 > 物品查看 > 移动模式 > 放行快捷指令。

    v101.16：『对话』改版配套——地图/NPC 列表带序号，回复序号直接交谈。
    v123a（鱼鱼拍板）：移除「序号直接找 NPC」——裸数字不再触发找 NPC 对话，
    NPC 列表序号仅作展示，交谈须『对话 <名字>』/『对话 <序号>』；
    对话树中的选项回复（_talk_active）保留。
    v128.2（鱼鱼拍板）：『位置 0』/发 0 进入赶路模式的旧捷径已移除，
    赶路入口统一为『赶路』指令（hurry_view 进入）；0 仅在赶路模式中用于结束。
    priority=100 高于 shortcut_trigger(默认0)：命中即 stop_event 拦截快捷指令；
    无状态可消费时 return（不 yield）→ 放行给快捷指令。
    v127.4：去掉 @require_player()——裸数字是对话树/移动/快捷等"已注册玩家专属"的
    交互链，未注册用户发『1』『2』不应被"你还没有角色"打扰（鱼鱼反馈），
    改为函数内对未注册静默 return（不 yield、不提示），放行顺延。
    """
    # v127.4：未注册玩家无对话树/物品查看/移动模式/快捷绑定可消费 → 静默放行，免"未注册"打扰
    if not self._player(group_id, qq_id):
        return
    num = event.get_message_str().strip()
    num = re.sub(r"^\[At:[^\]]*\]\s*", "", num).strip()
    # v124.2 全角数字兼容：全角『１』等回复转半角再比较（分支交付/对话树选项/物品查看/移动共用）
    num = num.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    # v124 分支交付：支线 ready + branch_wait 时，裸数字 = 分支选项（优先于对话树）
    _bw = self._branch_wait_sid(group_id, qq_id)
    if _bw and (num.isdigit() or num):
        lines = self._complete_side_quest(group_id, qq_id, _bw, branch_choice=num)
        yield event.plain_result("\n".join(lines))
        self._stop_event_safe(event)
        return
    # v173.3 意见#103：武器自选礼包挂起——回复数字领取对应武器
    _wp = self._weapon_pick_active(group_id, qq_id)
    if _wp:
        result = self._weapon_pick_choose(group_id, qq_id, num)
        yield event.plain_result(result)
        self._stop_event_safe(event)
        return
    # O99 修复：与 talk_choice/move 同源判定（_talk_active 清除损坏残留键）
    st = self._talk_active(group_id, qq_id)
    if st:
        # 对话树选项选择（复用 talk_choice 有状态分支：『对话 1』同款）
        # ★ 修：talk_choice 需 group_id/qq_id/player（此前漏传 ⇒ 生产壳 TypeError ⇒ 裸数字整条挂掉）
        async for r in self.talk_choice(event, group_id, qq_id, self._player(group_id, qq_id)):
            yield r
        self._stop_event_safe(event)
        return
    # v101.21 物品查看模式：开启时裸数字优先查物品（改消息转发 item_detail）
    if db.get_event_state(f"item_view_mode:{qq_id}"):
        event.message_str = f"物品详情 {num}"
        async for r in self.item_detail(event):
            yield r
        self._stop_event_safe(event)
        return
    # v128 赶路模式：开启时裸数字赶路（改消息转发 move），0=关闭
    if db.get_event_state(f"move_mode:{qq_id}"):
        if num == "0":
            db.set_event_state(f"move_mode:{qq_id}", "")
            db.set_event_state(f"hurry_type:{qq_id}", "")  # v128.1 结束赶路同时清过滤
            yield event.plain_result(_T.static("quick.hurry_end"))
            self._stop_event_safe(event)
            return
        event.message_str = f"前往 {num}"
        async for r in self.move(event, group_id, qq_id):      # ★ 修：move 需要 group_id/qq_id
            yield r                                      #   （此前漏传 ⇒ TypeError ⇒ 该快捷指令整条挂掉）
        self._stop_event_safe(event)
        return
    # v128.2：『位置 0』/发 0 进入赶路模式的旧捷径已移除——无状态可消费时
    # 回复 0 一律放行（不再开启赶路模式）；进入赶路唯一入口=『赶路』指令
    # （hurry_view）；0 仅在赶路模式中用于结束（见上）。
    # v123a：序号直接找 NPC 已移除——无对话/物品/移动状态时一律放行
    # （快捷指令由 shortcut_trigger 消费；未绑定则无响应）
    return


async def find_npc(self, event: AstrMessageEvent):
    """『对话 <NPC名/序号>』内部查找链：被 talk_choice 无对话分支调用；不对外注册（v127.8）"""
    group_id, qq_id = self._uid(event)
    name_key = self._strip_cmd(event, "找")
    player = self._player(group_id, qq_id)
    if self._is_redname(qq_id):
        yield event.plain_result(_T.static("find.redname"))
        return
    name_key = name_key.strip()
    if not name_key:
        cur_m = player["cur_map"]
        if cur_m.startswith("home_"):
            yield event.plain_result(_T.static("npc.home_empty"))
            return
        # v127.5 限时NPC：与『对话』空参同源——在场野外旅人也并入列表
        yield event.plain_result("\n".join(self._start_talk_list(group_id, qq_id)))
        return
    # 序号找：『找 1』→ 当前地图第 1 个 NPC（含 v127.5 在场野外旅人续号）
    if name_key.isdigit():
        if player["cur_map"].startswith("home_"):
            yield event.plain_result(_T.static("npc.home_empty"))
            return
        npcs = self._current_npcs(player)
        wild_evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",
                                data_match={"map": player["cur_map"]})
        # 编号走引擎 `Presence`：静态 + 限时**同一编号系**（`find_npc` 与『对话』列表同源）
        slots = _PRESENCE.slots(npcs, wild_evs)
        total = len(slots)
        idx = int(name_key)
        if idx < 1 or idx > total:
            yield event.plain_result(_T.text("find.idx_out", idx=idx, total=total))
            return
        _slot = _PRESENCE.slot_at(slots, idx)
        if _slot[1] == "static":
            npc = _slot[2]
            npc_id = next((nid for nid, n in _cat_quests.NPCS.items() if n is npc), None)
        else:
            # v127.5 限时NPC：序号命中在场野外旅人（不在 _cat_quests.NPCS，不能走反查）
            _ev = _slot[2]
            npc_id = _ev.get("data", {}).get("npc_id") or ""
            _w = _LOOKUP_WILD.first(npc_id)[0]
            if not _w:
                yield event.plain_result(_T.static("find.wild_left"))
                return
            npc = dict(_w)
            npc.setdefault("title", "游历于野外的旅人")  # 与 _find_wild_npc 一致
    else:
        npc_id, npc = self._find_npc_in_map(player, name_key)
        if npc and player.get("_npc_absent"):
            # v95.30 随机性：酱油 NPC 名字匹配但今天不在（游走/概率/时段）
            yield event.plain_result(self._town_npc_absent_hint(*player["_npc_absent"]))
            return
    if not npc:
        # v87.2 副本地图化：副本层内 NPC（HIDDEN_NPCS，按当前层 npcs 列表查）
        inst_row = self._instance_battle_for(group_id, qq_id)
        if inst_row and inst_row["state"].get("mode") == "map":
            stage_npcs = self._stage_npcs(group_id, qq_id)
            for nid in stage_npcs:
                n = _LOOKUP_HIDDEN.first(nid)[0] or {}
                if n and (name_key in n.get("name", "") or name_key in nid):
                    npc_id, npc = nid, n
                    break
    if not npc:
        # 9.4：野外 NPC（当前地图 + 出现条件）
        npc_id, npc = self._find_wild_npc(player, name_key, group_id, qq_id)
        if npc:
            # v127.5 限时NPC：偶遇制——只在倒计时内在场可找；未偶遇/过期 → "今天没遇到"
            if not _timed.get_timed(group_id, qq_id, f"wild:{npc_id}"):
                _ta = "她" if npc.get("gender") == "女" else "他"
                yield event.plain_result(
                    _T.text("find.wild_not_met", name=name_key, ta=_ta))
                return
    if not npc:
        # v95.15 #71：名字命中但时段/条件不满足（NPC 在本图却找不到）→ 提示出现条件
        unseen = self._wild_unseen_hint(player, name_key, group_id, qq_id)
        if unseen:
            yield event.plain_result(unseen)
            return
        # v95.8 #51：不在当前子区域/地图时，全局搜位置给方向提示
        hint = self._npc_direction_hint(player, name_key)
        if hint:
            yield event.plain_result(hint)
            return
        yield event.plain_result(
            _T.text("find.not_found", name=name_key))
        return
    dlg = _dlg.get_dialogue(npc_id)
    if dlg:
        # v65：配置了多轮对话树 → 进入对话
        db.set_talk_state(group_id, qq_id, npc_id, dlg.get("start", ""))
        ctx = self._talk_ctx(group_id, qq_id, npc_id)
        node = _dlg.dialogue_node(dlg, dlg.get("start", ""))
        lines = self._render_talk_node(npc, dlg, node, ctx)
    else:
        lines = [f"{npc['icon']}【{npc['name']}】{npc['title']}", f"“{self._npc_dialogue(group_id, qq_id, npc_id, npc)}”"]
    # 功能提示
    funcs = npc.get("funcs", [])
    if "quest" in funcs:
        # v95.11 #50：代词按 NPC 性别（玛莎等女性 NPC 用"她"）
        _ta = "她" if npc.get("gender") == "女" else "他"
        if dlg:
            # v95.9 对话式任务：有对话树的 NPC 通过对话选项接取/交付，这里只给引导
            _quests = db.get_quests(group_id, qq_id)
            _mid = _quests.get("main_quest")
            _mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == _mid), None) if _mid else None
            if _mq and _mq["giver"] == npc_id:
                _st = _quests.get("main_status", "pending")
                if _st == "pending":
                    lines.append(_T.text("find.main_avail", name=_mq['name'], ta=_ta))
                elif _st == "ready":
                    lines.append(_T.text("find.main_ready", name=_mq['name'], ta=_ta))
            _side = _quests.get("side", {})
            # v127.6 预告全量：复用 _side_available_list（与对话菜单同源过滤）——
            # 把该 NPC 所有可接支线都列出来（此前 break 只显示第一条，与实际可接数对不上）
            for _av in self._side_available_list(group_id, qq_id, npc_id, npc):
                lines.append(_T.text("find.side_avail", name=_av['name'], ta=_ta))
            for _sid, _sq in list(_side.items()):
                _sqd = next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == _sid), None)
                if _sqd and _sqd["giver"] == npc_id and _sq.get("status") == "ready":
                    lines.append(_T.text("find.side_ready", name=_sqd['name'], ta=_ta))
                    break
            # v124 progress_text：该 NPC 名下有进行中的链式支线 → 输出推进台词（有对话树的 NPC 也显示）
            for _sid, _sq in list(_side.items()):
                _sqd = next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == _sid), None)
                if _sqd and _sqd["giver"] == npc_id and _sq.get("status") == "active":
                    _pt = _sqd.get("progress_text")
                    if _pt:
                        lines.append(f"  💬 {_pt}")
                        break
        else:
            # 无对话树的 NPC：保持自动接取/交付（对话选项不存在，指令与提示兜底）
            lines += self._take_main_quest(group_id, qq_id, npc_id, npc)
            lines += self._offer_side_quests(group_id, qq_id, npc_id, npc)
    if "shop" in funcs and self._at_shop(player, group_id, qq_id):
        lines.append(_T.static("find.shop_hint"))
    if "trade" in funcs:
        _ta = "她" if npc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别
        lines.append(_T.text("find.trade_hint", ta=_ta))
    if "heal" in funcs and self._at_healer(player):
        lines.append(_T.static("find.heal_hint"))
    if "daily" in funcs:
        lines.append(_T.static("find.daily_hint"))
    if "lore" in funcs:
        ta = "她" if npc.get("gender") == "女" else "他"
        # v101.25 #311：lore 空挂修复——提示"讲传说"却没有传说内容（world.py 注释
        # 曾承认翠羽/说书人·巴尔空挂）。现在直接输出 NPC dialogue 作为传说正文，
        # 不再只给一句空引导。
        _lore_txt = npc.get("lore") or npc.get("dialogue", "")
        if _lore_txt:
            lines.append(_T.text("find.lore_block", ta=ta, lore=_lore_txt))
        else:
            lines.append(_T.text("find.lore_empty", ta=ta))
        lines.append(self._tip("encyclopedia"))
    if "teach" in funcs:
        # v104 P2（M21）teach 空挂修复：有对话树的教习 NPC 走对话树选项；
        # 无对话树的教习 NPC（龙语者·古尔/上古守卫者/墓王·静语）→ 按职业直接传授对应技能
        if dlg:
            lines.append(_T.static("find.teach_hint"))
        else:
            lines.extend(self._teach_by_npc(group_id, qq_id, player, npc_id))
    if "ency" in funcs:
        lines.append(_T.static("find.ency_hint"))
    # v104 P1（M21）：隐藏 NPC 解锁 flag 设置点——与特定野外 NPC 交谈即授予（幂等）
    _granted = self._grant_wild_unlock_flags(group_id, qq_id, npc_id)
    if _granted:
        lines.append(_granted)
    yield event.plain_result("\n".join(lines))


def _grant_wild_unlock_flags(self, group_id, qq_id, npc_id):
    """v104 P1（M21 隐藏 NPC 永久锁死修复）：与特定野外 NPC 交谈 → 授予隐藏 NPC 解锁 flag。

    v124.3（审计）：解锁链数据化——配置读 NPC 数据的 unlock_flags 字段
    （{"flag": "heard_owl_song", "notice": "…"}，见 wild_npcs.py 说书人·巴尔/
    流浪诗人·弦歌/老兵之魂），新增解锁型 NPC = 纯数据操作（加字段即可），
    本函数零改动。flag 存任意 NPC 桶即可，unlock_met 已改全桶扫描。
    返回首次授予的提示行；无授予返回 None。
    """
    npc = _LOOKUP_WILD.first(npc_id)[0]
    if not isinstance(npc, dict):
        return None
    cfg = npc.get("unlock_flags") or {}
    flag = cfg.get("flag", "")
    if not flag:
        return None
    if flag in db.get_talk_flags(group_id, qq_id, npc_id):
        return None
    db.set_talk_flag(group_id, qq_id, npc_id, flag)
    return cfg.get("notice", "")


def _teach_by_npc(self, group_id, qq_id, player, npc_id):
    """v104 P2（M21）teach 空挂修复：无对话树的教习型 NPC（龙语者·古尔/上古守卫者/墓王·静语）
    按职业传授对应技能。参照对话树 tutor_skill 写法：等级门槛 + 金币学费 → 直接学会（不耗技能点）。
    返回提示行列表；NPC 不在映射表时返回空列表（保持原行为）。
    v112：配置读 NPC 数据（teach_skills/teach_hint），无配置返回空列表。
    """
    npc = _LOOKUP_WILD.first(npc_id)[0] or {}
    if not isinstance(npc, dict):
        npc = {}
    cfg_skills = npc.get("teach_skills") or {}
    hint = npc.get("teach_hint") or ""
    if not cfg_skills:
        return []
    cid = _idx.resolve("classes", player.get("class_name", ""))
    sname = cfg_skills.get(cid)
    if not sname:
        return [_T.text("teach.wrong_class", hint=hint)]
    info = skill_info(player.get("class_name", ""), sname)
    if not info:
        return []
    sname_cn = info.get("name", sname)
    need_lv = int(info.get("lv", 1))
    cost = max(500, need_lv * 100)
    if player.get("level", 0) < need_lv:
        return [_T.text("teach.need_lv", hint=hint, need_lv=need_lv, lv=player.get('level', 1))]
    if (player.get("gold", 0) or 0) < cost:
        return [_T.text("teach.need_gold", hint=hint, cost=cost, gold=player.get('gold', 0))]
    learned = list(player.get("learned_skills", []))
    if _idx.resolve("skills", sname) in [_idx.resolve("skills", s) for s in learned if s]:
        return [_T.text("teach.learned", hint=hint, name=sname_cn)]
    db.update_player(group_id, qq_id, gold=(player.get("gold", 0) or 0) - cost,
                     learned_skills=learned + [sname_cn])
    return [
        f"{hint}",
        _T.text("teach.gift", cost=cost),
        _T.text("teach.ok", name=sname_cn),
        f"「{info['desc']}」",
        self._tip("skill_set"),
    ]


async def interact_prop(self, event: AstrMessageEvent, group_id, qq_id):
    """与当前子区域的场景元素(喷泉/雕像/告示板等)交互。纯氛围 + 极小彩蛋。"""
    name_key = self._strip_cmd(event, "交互").strip()
    player = self._player(group_id, qq_id)
    if self._is_redname(qq_id):
        yield event.plain_result(_T.static("ip.redname"))
        return
    cur = player["cur_map"]
    cur_map = _cat_space.MAP_BY_ID.get(cur, {})
    sa_id = player.get("cur_subarea") or ""
    prop_ids = _pois.subarea_props(cur, sa_id)
    # v104 M23 修复：过滤孤儿 prop（SUBAREA_PROPS 挂载了但 PROPS 未定义）。
    # 显示列表与『交互 <序号>』按下标取条目必须同源，否则序号错位/取到空定义
    # 会在 pp['icon']/pp['name'] 处 KeyError 崩溃。
    prop_ids = [e for e in prop_ids if _pois.prop_entry(e)[0] in _cat_items.PROPS]
    if not name_key:
        # 无参：列出当前子区域的场景元素
        if not prop_ids:
            yield event.plain_result(_T.static("ip.none"))
            return
        lines = [_T.static("ip.list_head")]
        for i, entry in enumerate(prop_ids, 1):
            pid, label = _pois.prop_entry(entry)
            pp = _cat_items.PROPS.get(pid, {})
            if pp:
                name = label or pp['name']
                lines.append(f"{i}. {pp['icon']}{name}：{pp.get('desc', '')}")
        lines.append(self._tip("interact"))
        yield event.plain_result("\n".join(lines))
        return
    # 序号交互：『交互 1』→ 当前子区域第 1 个元素
    if name_key.isdigit():
        idx = int(name_key)
        if idx < 1 or idx > len(prop_ids):
            yield event.plain_result(_T.text("ip.no_idx", idx=idx, tot=len(prop_ids)))
            return
        entry = prop_ids[idx - 1]
        pid, label = _pois.prop_entry(entry)
        found = (pid, _cat_items.PROPS.get(pid, {}), label)
    else:
        # 找 prop：专属名/默认名子串 / id 匹配
        found = None
        for entry in prop_ids:
            pid, label = _pois.prop_entry(entry)
            pp = _cat_items.PROPS.get(pid, {})
            name = label or pp.get("name", "")
            if pp and (name_key in name or name_key in pid):
                found = (pid, pp, label)
                break
        if not found:
            # v95.14：海象运算符只在 if 条件绑定 pid，label 未定义 → NameError；改用显式循环 + 去重
            _cand = []
            for _entry in prop_ids:
                _pid, _lbl = _pois.prop_entry(_entry)
                if _pid in _cat_items.PROPS:
                    _nm = _lbl or _cat_items.PROPS[_pid]["name"]
                    if _nm not in _cand:
                        _cand.append(_nm)
            names = "、".join(_cand) or "没有"
            yield event.plain_result(_T.text("ip.not_found", name=name_key, have=names))
            return
    pid, pp, label = found
    name = label or pp['name']
    texts = pp.get("texts") or []
    text = random.choice(texts) if texts else pp.get("desc", "……")
    lines = [f"{pp['icon']}【{name}】", f"“{text}”"]
    # v97.1 告示板：附加展示当前地图的告示委托（board 型支线，未接取时）
    # v104 M20 修复：真正按当前地图过滤（原实现遍历全部 board 委托，注释与实现不符）——
    # board 委托取顶层 map 字段（发布地）；没有则按 giver NPC 所在区域兜底。
    # 注意：find 型委托的 objective.map 是搜寻地而非发布地，不可用于此过滤。
    if pid == "notice_board":
        quests = db.get_quests(group_id, qq_id)
        side = quests.get("side") or {}
        here_board = []
        for sq in _cat_quests.SIDE_QUESTS:
            if not sq.get("board"):
                continue
            qmap = sq.get("map")
            if not qmap:
                _g = _cat_quests.NPCS.get(sq.get("giver")) or _wild.ALL_WILD.get(sq.get("giver")) or {}
                qmap = _g.get("map")
            if qmap and qmap != cur:
                continue
            here_board.append(sq)
        board_lines = []
        for sq in here_board:
            if sq["id"] in side:
                continue
            board_lines.append(f"  📜 {sq['name']}：{sq['desc']}")
        if board_lines:
            lines.append("━━━━━━━━━━━━")
            lines.append(_T.static("ip.board_head"))
            lines += board_lines
            lines.append(self._tip("notice_board"))
        else:
            done = any(
                side.get(sq["id"], {}).get("status") == "done"
                for sq in here_board
            )
            if done:
                lines.append(_T.static("ip.board_done"))
    # 极小彩蛋（纯趣味，不破坏平衡）
    # v87.12 专属元素带小效果：dict effect = {"type": "material"/"heal", "daily": True}
    import datetime as _dt
    eff = pp.get("effect")
    if eff == "wish":
        # v105 M23 P2-2：许愿井每日 1 次（策划案 23 章『许愿井（每日一次彩蛋）』）——
        # 原实现零成本无限刷（5%×1-5 金币无冷却无每日次数），现按 props_use 每日计数
        today = _dt.date.today().isoformat()
        use_key = f"{cur}:{sa_id}:{pid}"
        used = db.get_props_use(qq_id)
        if used.get(use_key) == today:
            lines.append(_T.static("ip.well_used"))
        elif random.random() < WISH_WELL_EGG_CHANCE:
            gold = random.randint(1, 5)
            # F1 P1-4：原子认领——并发双请求只有首个真正占下并发放（后手见"已应过一次愿"）
            if db.props_use_claim_atomic(qq_id, use_key, today):
                db.update_player(group_id, qq_id, gold=player["gold"] + gold)
                lines.append(_T.text("ip.well_gift", n=gold))
            else:
                lines.append(_T.static("ip.well_used"))
    elif eff == "refresh":
        lines.append(_T.static("ip.spring"))
    elif isinstance(eff, dict) and eff.get("daily"):
        # 每日 1 次（按元素实例：地图:子区域:prop_id 独立计数，防刷）
        today = _dt.date.today().isoformat()
        use_key = f"{cur}:{sa_id}:{pid}"
        used = db.get_props_use(qq_id)
        if used.get(use_key) == today:
            lines.append(_T.static("ip.used_today"))
        else:
            etype = eff.get("type")
            if etype == "material":
                pool = eff.get("pool") or []
                if pool:
                    # F1 P1-4：原子认领——并发双请求只有首个发放（后手提示已翻找过）
                    if not db.props_use_claim_atomic(qq_id, use_key, today):
                        lines.append(_T.static("ip.used_today"))
                    else:
                        mid = random.choice(pool)
                        mname = _idx.display("materials", mid)
                        db.add_item(group_id, qq_id, mid, {
                            "name": mname, "type": "材料", "stackable": True,
                            "price": _cat_items.MATERIALS[mid]["price"],
                        }, 1)
                        lines.append(_T.text("ip.found", text=eff.get('found_text', '你发现'), name=mname))
                        # v104 M20：采集任务每日（collect_any）——场景元素获得材料 +1（主采集动作在 economy.py）
                        self._bump_daily_progress(group_id, qq_id, "collect_any", lines)
            elif etype == "heal":
                pct = float(eff.get("pct", 0.1))
                missing = player.get("max_hp", 1) - player.get("hp", 0)
                # v104 M23 修复：满血时旧逻辑 max(1, int(0*pct))=1 会误走恢复分支、
                # 白吞每日次数；改为满血只出氛围文案，不 mark_props_use
                heal = max(1, int(missing * pct)) if missing > 0 else 0
                if heal <= 0:
                    lines.append(_T.static("ip.heal_full"))
                else:
                    # F1 P1-4：原子认领——并发双请求只有首个恢复（后手提示今日已翻找过）
                    if not db.props_use_claim_atomic(qq_id, use_key, today):
                        lines.append(_T.static("ip.used_today"))
                    else:
                        db.update_player(group_id, qq_id, hp=player["hp"] + heal)
                        lines.append(_T.text("ip.heal_ok", text=eff.get('found_text', '暖意袭来'), hp=heal, cur=player['hp'] + heal,
                                         cap=player.get('max_hp', 1)))
    yield event.plain_result("\n".join(lines))


def _talk_active(self, group_id, qq_id):
    """统一对话状态读取（O99 修复：统一对话结束状态判定）。

    对话结束判定（『对话 0』/移动拦截/副业材料保护）必须同源同判定：
    键存在但 JSON 损坏/非 dict（历史脏数据）时视为"无对话"并顺手清除残留键，
    杜绝『对话 0』提示"没有正在进行的对话"而移动仍被残留状态拦截的判定漂移。
    """
    st = db.get_talk_state(group_id, qq_id)
    if st is not None and not isinstance(st, dict):
        db.clear_talk_state(group_id, qq_id)
        return None
    if st is None:
        raw = db.get_event_state(db.talk_state_key(group_id, qq_id))
        if raw:
            db.clear_talk_state(group_id, qq_id)  # 损坏/无法解析的残留键 → 清除
    return st


def _talk_ctx(self, group_id, qq_id, npc_id):
    """对话引擎上下文：player + quests + 该 NPC 已设 flag + 已拜师副业"""
    player = self._player(group_id, qq_id) or {}
    return {
        "player": player,
        "_gid": group_id, "_qid": qq_id,   # v173.3：渲染层自动补任务入口需要
        "quests": db.get_quests(group_id, qq_id),
        "flags": db.get_talk_flags(group_id, qq_id, npc_id),
        "apprentices": player.get("apprentices", []),
        "npc_id": npc_id,
        "side_quests": _cat_quests.SIDE_QUESTS,
        "item_counts": {m: db.count_item(group_id, qq_id, m) for m in {(o.get("objective") or {}).get("collect") for o in _cat_quests.SIDE_QUESTS} if m},
        # v127.6 side_menu 动态菜单：core.visible_options 渲染时用该回调
        # 把『有活儿要交给我吗』类选项展开成『每个可接支线一个子选项』
        "side_menu_expand": lambda opt: self._side_menu_expand(group_id, qq_id, npc_id, opt),
    }


def _side_menu_expand(self, group_id, qq_id, npc_id, opt) -> list:
    """v127.6：side_menu 选项的动态展开——每个可接支线一个子选项（玩家自选单接）。

    供 core.visible_options 的 side_menu_expand 回调调用；无任何可接支线 → 返回 []（菜单不出现）。
    子选项 next：side_menu.after（连串接，通常为该 NPC 对话树 start）→ 选项原 next → __end__。
    每条子选项 action: {"side_take_one": sid}，走 talk_actions.side_take_one 单条接取。
    """
    available = self._side_available_list(group_id, qq_id, npc_id, None)
    if not available:
        return []
    nxt = (opt.get("side_menu") or {}).get("after") or opt.get("next") or "__end__"
    subs = []
    for item in available:
        subs.append({
            "text": _T.text("talk.side_take", name=item['name'], obj=item['objective_text']),
            "next": nxt,
            "action": {"side_take_one": item["sid"]},
        })
    return subs


def _render_talk_node(self, npc, dlg, node, ctx) -> list:
    """渲染一个对话节点：头像 + 台词 + 可见选项
    v101.23：台词走 _dlg.node_text——支持 texts 条件变体（随主线进度切换）
    v173.3 意见#113/#163/#164（鱼鱼拍板）：NPC 对话树自动补任务入口——
    当 NPC 名下有可接支线且当前节点选项没任务入口时，自动展开『📜 有委托可接』
    （复用 side_menu 动态子选项），新手不再"找不到任务"。"""
    lines = [f"{npc['icon']}【{npc['name']}】{npc['title']}",
             f"“{_dlg.node_text(node, ctx)}”"]
    opts = _dlg.visible_options(dlg, node, ctx)
    # v173.3：自动补任务入口——节点无任何任务类选项 & NPC 有可接支线时展开
    if not any((o.get("side_menu") is not None) or (o.get("action") or {}).get("side_offer")
               or (o.get("action") or {}).get("side_take") or (o.get("action") or {}).get("side_take_one")
               or (o.get("action") or {}).get("quest_take")
               for o in opts):
        try:
            npc_id = ctx.get("npc_id") or ""
            _auto_opt = {"text": _T.static("talk.auto_quest_opt"), "next": "__end__",
                         "need": {"side_available": True}, "side_menu": {"after": "welcome"}}
            _expanded = self._side_menu_expand(ctx.get("_gid") or "", ctx.get("_qid") or "", npc_id, _auto_opt)
            if _expanded:
                opts = list(opts) + _expanded
        except Exception:
            pass
    if opts:
        lines.append("━━━━━━━━━━━━")
        for i, opt in enumerate(opts, 1):
            lines.append(f"{i}. {opt['text']}")
        lines.append(_T.static("talk.end_opt"))
        lines.append(self._tip("talk_tree"))
    return lines


def _branch_wait_sid(self, group_id, qq_id):
    """v124 分支等待支线 sid 查询（P4-2 壳：转调 services.quests_flow.branch_wait_sid）"""
    from . import quests_flow as qf
    return qf.branch_wait_sid(group_id, qq_id)


def _weapon_pick_active(self, group_id, qq_id) -> bool:
    """v173.3 意见#103：是否有武器自选礼包挂起选择未完成。"""
    import json as _j
    try:
        st = _j.loads(db.get_event_state(f"weapon_pick_{qq_id}") or "{}")
    except (ValueError, TypeError):
        st = {}
    return bool(st.get("active"))


def _weapon_pick_choose(self, group_id, qq_id, num) -> str:
    """v173.3 意见#103：回复数字领取自选武器；0=收起下次再选。"""
    import json as _j
    key = f"weapon_pick_{qq_id}"
    try:
        st = _j.loads(db.get_event_state(key) or "{}")
    except (ValueError, TypeError):
        st = {}
    if not st.get("active"):
        return ""
    opts = st.get("opts") or []
    item_name = st.get("item") or "礼包"
    # 0 = 收起（保留道具，下次可再选）
    if num.strip() == "0":
        db.set_event_state(key, "{}")
        return _T.text("wpick.closed", item=item_name)
    if not num.isdigit():
        return _T.text("wpick.hint", n=len(opts))
    idx = int(num)
    if idx < 1 or idx > len(opts):
        return _T.text("wpick.no_idx", idx=idx, n=len(opts))
    opt = opts[idx - 1]
    eq_name = opt.get("equip") or opt.get("name", "")
    rid = opt.get("rid", "")
    # 生成装备入包（rid 优先名册；否则 fallback 名册按名查）
    try:
        rid_list = _cat_items.EQUIP_ROSTER_BY_NAME.get(eq_name, []) if eq_name else []
        if rid:
            rid_list = [rid]
        if not rid_list:
            return _T.text("wpick.no_data", name=opt.get('name', eq_name))
        eq = _drops().generate_roster_equip(rid_list[0])
        db.add_item(group_id, qq_id, rid_list[0], eq)
    except Exception:
        return _T.text("wpick.failed", name=opt.get('name', eq_name))
    # 扣除礼包道具（战斗中使用的兜底：此处按事件状态找到礼包名，从背包删 1 个）
    self._remove_one_by_name(group_id, qq_id, item_name)
    # 清挂起
    db.set_event_state(key, "{}")
    return _T.text("wpick.ok", name=eq.get('name', opt.get('name', eq_name)))


def _remove_one_by_name(self, group_id, qq_id, item_name) -> bool:
    """按名称从背包移除 1 个同名物品（礼包领取后扣道具用）。

    get_inventory 返回条目含 key（inventory.item_key）——remove_item 按 key 删，
    不能传 name（v46 起 key 是 ID/uuid）。匹配礼包名（事件状态里存的礼包名）。
    """
    items = db.get_inventory(group_id, qq_id)
    for it in items:
        d = it["data"]
        dname = d.get("name", "")
        if dname and (dname == item_name or (item_name and item_name in dname)):
            db.remove_item(group_id, qq_id, it["key"], 1)
            return True
    return False


def _update_use_quests(self, group_id, qq_id, item_name):
    """v124 use 目标支线：使用物品后置 ready（P4-2 壳：转调 services.quests_flow.update_use_quests）"""
    from . import quests_flow as qf
    return qf.update_use_quests(group_id, qq_id, item_name)


def _talk_quest_progress(self, group_id, qq_id, npc_id) -> list:
    """talk/collect/explore 型主线对话即达成（P4-2 壳：转调 services.quests_flow.talk_quest_progress）"""
    from . import quests_flow as qf
    return qf.talk_quest_progress(group_id, qq_id, npc_id)


def _do_join_class(self, group_id, qq_id, player, new_cls):
    """行会就职：见习冒险者 → 基础职业。
    属性按新职业重算（base+成长×等级+种族，自由点保留），赠送基础技能书（职业 Lv.1 技能）。
    返回通知行列表。"""
    lines = []
    if player.get("class_name") != _cat_core.CLASS_NOVICE:
        lines.append(_T.static("join.already"))
        return lines
    cls = _cat_core.CLASSES.get(new_cls)
    if not cls or cls.get("hidden"):
        lines.append(_T.static("join.unavailable"))
        return lines
    # 属性按新职业重算（参考隐藏职业传承的属性同步写法）
    st = player_final_stats(
        new_cls, player.get("level", 1), player.get("equipment", {}), 0,
        player.get("attributes"), 0,
        self._title_bonus(group_id, qq_id), player.get("race"))
    sk_table = _cat_core.PLAYER_SKILLS.get(new_cls, {})
    if isinstance(sk_table, dict) and "skills" in sk_table:
        sk_table = sk_table["skills"]
    init_skills = [s for s, info in sk_table.items() if info["lv"] <= 1]
    db.update_player(group_id, qq_id, class_name=new_cls,
                     max_hp=st["max_hp"], max_mp=st["max_mp"], hp=st["max_hp"], mp=st["max_mp"],
                     learned_skills=init_skills)
    bar = list(init_skills[:6])
    while len(bar) < 6:
        bar.append(None)
    db.set_skill_bar(qq_id, bar)
    names = "、".join(_idx.display("skills", s) for s in init_skills)
    lines.append(_T.text("join.ok", icon=cls['icon'], name=cls['name']))
    lines.append(f"『{cls['desc']}』")
    if names:
        lines.append(_T.text("join.books", names=names))
    lines.append(self._tip("skill_learn"))
    lines.append(_T.static("join.tip"))
    return lines


def _do_evolve_via_npc(self, group_id, qq_id, player, next_tier, path):
    """导师转职：Lv.30/60/90 找对应职业导师对话转职（同步版，返回通知行）。"""
    lines = []
    cls = _cat_core.CLASSES.get(player.get("class_name", ""), {})
    cur_tier = player.get("class_tier", 0)
    need_lv = _cat_core.EVOLVE_LEVELS.get(next_tier)
    if not need_lv:
        lines.append(_T.static("evolve.npc_done_all"))
        return lines
    if cur_tier != next_tier - 1:
        lines.append(_T.static("evolve.npc_not_yet"))
        return lines
    if player.get("level", 0) < need_lv:
        lines.append(_T.text("evolve.npc_need_lv", need_lv=need_lv, lv=player.get('level', 0)))
        return lines
    branches = cls.get("evolve_branches", {}).get(next_tier, [])
    if path < 1 or path > len(branches):
        path = 1
    old_title = self._tier_title(player["class_name"], cur_tier, player.get("evolve_path", 0))
    # v105 P1：转职同步重算属性并落库——TIER_GROWTH 成长加成随阶位跃升，
    # 仅写 class_tier 会让存档 max_hp/max_mp 长期与计算值脱节（战斗外休息/回家/
    # 药水/治疗全按存档上限回血，转职后回不满新上限）。参照 player.py 隐藏职业转职写法。
    new_evolve_path = path or player.get("evolve_path", 0)
    st = player_final_stats(
        player["class_name"], player.get("level", 1), player.get("equipment", {}),
        next_tier, player.get("attributes"), new_evolve_path,
        self._title_bonus(group_id, qq_id), player.get("race"))
    fields = {"class_tier": next_tier,
              "max_hp": st["max_hp"], "max_mp": st["max_mp"],
              "hp": st["max_hp"], "mp": st["max_mp"]}
    if path:
        fields["evolve_path"] = path
    db.update_player(group_id, qq_id, **fields)
    player = self._player(group_id, qq_id)
    new_title = self._branch_title(player["class_name"], next_tier, path or player.get("evolve_path", 0))
    bonus = int((TIER_GROWTH.get(next_tier, 1.0) - 1.0) * 100)
    branch_line = ""
    if path:
        tag = _T.static("evolve.path_atk") if path == 1 else _T.static("evolve.path_def")
        branch_line = f"\n🔀 {tag}"
    auto_skills = self._evolve_auto_skills(player, next_tier)
    if auto_skills:
        learned = player.get("learned_skills", [])
        learned = [s for s in learned if s not in auto_skills]
        learned += auto_skills
        db.update_player(group_id, qq_id, learned_skills=learned)
        player = self._player(group_id, qq_id)
    auto_line = ""
    if auto_skills:
        auto_line = _T.text("evolve.npc_gains", names='、'.join(auto_skills))
    _ach.check_achievements(group_id, qq_id, player)
    lines.append(_T.static("evolve.npc_ok"))
    lines.append("━━━━━━━━━━━━")
    lines.append(f"{old_title}")
    lines.append("  ↓↓↓")
    lines.append(f"{cls['icon']} {new_title}{branch_line}")
    lines.append("")
    lines.append(_T.text("evolve.npc_bonus", bonus=bonus))
    lines.append(_T.text("evolve.npc_skills", auto=auto_line))
    lines.append(_T.static("evolve.npc_final") if next_tier >= 3 else _T.static("evolve.npc_next"))
    return lines


async def _apply_talk_action_async(self, group_id, qq_id, player, npc_id, action):
    """异步版对话动作执行（v113：支持 hidden_evolve 等 async 动作）——talk_choice 调用本方法。

    返回 (通知行, 路由提示)。路由提示由条件型动作（apprentice_check 等）设置：
      None    → 走选项 next
      "fail"  → 走选项 fail_next
      "__end__" → 直接结束对话
    v124.3（审计）：apprentice_check 注册表化后 talk_choice 主循环不再特判，
    只做本方法返回的通用路由分发；未知 action 键由 talk_actions.check_action_keys 告警。"""
    lines = []
    route = None
    self._talk_route = None
    self._talk_tail = None
    if not action:
        return lines, route
    import inspect
    from .talk_actions import ACTIONS      # 包内注册表（宿主那份是 17+1 行转发，注册序同）
    _check_action_keys(action)             # 宿主独有（接口表第 4 行冻结：走注入/兜底口）
    for key, fn in ACTIONS.items():
        if not action.get(key):
            continue
        r = fn(self, group_id, qq_id, player, npc_id, action)
        if inspect.isawaitable(r):
            r = await r
        lines += r
        if self._talk_route is not None:
            # 条件型动作已判定：中断后续动作链（旧特判失败路径零动作执行——
            # 如 apprentice_check 失败时 consume_item 不扣料）
            route = self._talk_route
            break
    if self._talk_tail:
        lines += self._talk_tail
    return lines, route


def _apply_talk_action(self, group_id, qq_id, player, npc_id, action) -> list:
    """执行选项动作(涉及 DB 的副作用统一在这落地)，返回通知行
    v101.23d：动作注册表化——commands/talk_actions.py 的 ACTIONS（与 CONDITIONS
    注册表对称），加新动作 = register 一个函数，本方法零改动。
    同步版：仅执行同步动作（测试/旧调用用）；对话主链路走 _apply_talk_action_async。
    v113：hidden_evolve 为异步动作，同步版会跳过它（返回空）——对话内转职走 async 版。
    v124.3（审计）：与 async 版同源——未知 action 键告警 + 条件型动作（apprentice_check）
    中断动作链；路由提示不入返回值（仅 async 版返回，供 talk_choice 分发）。"""
    lines = []
    self._talk_route = None
    self._talk_tail = None
    if not action:
        return lines
    import inspect
    from .talk_actions import ACTIONS      # 包内注册表（宿主那份是 17+1 行转发，注册序同）
    _check_action_keys(action)             # 宿主独有（接口表第 4 行冻结：走注入/兜底口）
    for key, fn in ACTIONS.items():
        if not action.get(key):
            continue
        r = fn(self, group_id, qq_id, player, npc_id, action)
        if inspect.isawaitable(r):
            continue  # 异步动作（hidden_evolve）同步版跳过
        lines += r
        if self._talk_route is not None:
            break
    if self._talk_tail:
        lines += self._talk_tail
    return lines


async def talk_choice(self, event: AstrMessageEvent, group_id, qq_id, player):
    # O99 修复：统一对话状态判定（损坏残留键在 _talk_active 内清除，
    # 对话中『对话 0』亦拦截（v127.8b）与移动拦截同源同判定，不再出现"提示无对话但树仍在"的漂移）
    st = self._talk_active(group_id, qq_id)
    if not st:
        # v101.16 『找』→『对话』：无对话中时『对话 <名字/序号>』= 找 NPC 开始对话
        msg0 = event.get_message_str().strip()
        msg0 = re.sub(r"^\[At:[^\]]*\]\s*", "", msg0)
        if msg0.startswith("对话"):
            raw0 = msg0[len("对话"):].strip()
            if raw0:
                # v105 O64：『对话 0』在无对话状态时明确提示（原实现被 find_npc 当 NPC 序号 0，
                # 报"这里没有第 0 位 NPC"——玩家在单层 NPC 闲聊后想结束对话却得不到退出反馈）
                # O99 修复：全角 ０ 与 ASCII 0 同判（此前全角 ０ 落入 find_npc 报"没有第 0 位"）
                if raw0 in ("0", "０"):
                    yield event.plain_result(_T.static("talk.no_session"))
                    return
                # 复用 find_npc 查找/渲染链（改写消息为『找 X』）
                event.message_str = "找 " + raw0
                async for r in self.find_npc(event):
                    yield r
                return
            # 『对话』空参 = 显示当前 NPC 列表
            yield event.plain_result("\n".join(self._start_talk_list(group_id, qq_id)))
            return
        yield event.plain_result(_T.static("talk.no_session"))
        return
    # 会话游标**值**（引擎 `Cursor`）：还原不出时回落原始 schema 取值（口径分歧 ⑦ 逐字保留）
    _cur = Cursor.of(st, subject_key=_TALK_SUBJECT_KEY, node_key=_TALK_NODE_KEY)
    npc_id = _cur.subject if _cur is not None else st.get("npc", "")
    npc = _LOOKUP.first(npc_id)[0]                       # 两表真值链（原 `or` 链同口径）
    if not npc:
        db.clear_talk_state(group_id, qq_id)
        yield event.plain_result(_T.static("talk.npc_left_map"))
        return
    npc = dict(npc)
    npc.setdefault("title", "游历于野外的旅人")  # v95.11：wild NPC 无 title，与 _find_wild_npc 一致
    # 惰性失效：NPC 不在当前地图 → 会话作废（wild NPC 按 roam 定位）
    if _wild.npc_map_id(npc_id, npc) != player.get("cur_map"):
        db.clear_talk_state(group_id, qq_id)
        _ta = "她" if npc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别
        yield event.plain_result(_T.text("talk.gone_here", name=npc['name'], ta=_ta))
        return
    # v127.5 限时NPC：对话中野外NPC的在场的限时事件过期 → 会话作废
    # （倒计时结束显示与对话同时消失；与 npc_map_id 失效同位置、同文案风格）
    if npc_id in _wild.ALL_WILD and not _timed.get_timed(group_id, qq_id, f"wild:{npc_id}"):
        db.clear_talk_state(group_id, qq_id)
        _ta = "她" if npc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别
        yield event.plain_result(_T.text("talk.gone_timed", name=npc['name'], ta=_ta))
        return
    dlg = _dlg.get_dialogue(npc_id)
    if not dlg:
        db.clear_talk_state(group_id, qq_id)
        yield event.plain_result(_T.text("talk.silent", name=npc['name']))
        return
    # 剥指令名拿参数（对话/继续/结束对话/再见/告辞）
    msg = event.get_message_str().strip()
    msg = re.sub(r"^\[At:[^\]]*\]\s*", "", msg)
    raw = msg
    for cmd in ("结束对话", "对话", "继续", "再见", "告辞"):
        if msg.startswith(cmd):
            raw = msg[len(cmd):].strip()
            break
    # v127.8（鱼鱼拍板）：对话进行中『对话 <参数>』拦截——
    # ① 不能用于回复 NPC（选项回复走裸数字 1/2/3…，回复 0 结束对话）
    # ② 不能跳去别的 NPC（先回复 0 结束当前对话，才能『对话 <别的NPC>』）
    # 此前 v101.27 #412 的「『对话 数字』= 菜单选项 / 『对话 名字』= 找 NPC」规则整体作废。
    # 『对话』空参 → 重渲染当前节点（向下兼容）；v127.8 起对话中任何『对话 X』（含 0）一律拦截，结束统一回复 0。
    # v127.8b（鱼鱼拍板）：『对话 0』也不保留——对话中任何『对话 X』（含 0）
    # 一律拦截，结束对话统一回复裸数字 0（与选项回复同通道，无二义性）。
    if msg.startswith("对话") and raw:
        yield event.plain_result(
            _T.text("talk.busy_hint", name=npc['name']))
        return
    cur_node_id = _cur.node if _cur is not None else st.get("node", dlg.get("start", ""))
    node = _dlg.dialogue_node(dlg, cur_node_id)
    ctx = self._talk_ctx(group_id, qq_id, npc_id)
    if raw.isdigit():
        idx = int(raw)
        if idx == 0:
            db.clear_talk_state(group_id, qq_id)
            yield event.plain_result(_T.text("talk.farewell", name=npc['name']))
            return
        # 1-based 取可见选项走引擎 `Dialogue.pick`（越界 → None，不抛）
        opt = _TALK.of(dlg).pick(node, idx, ctx, expand=ctx.get("side_menu_expand"))
        if opt is None:
            # v101.28l #426：单选项时不再显示"1-1"（越界文案）
            _n = len(_dlg.visible_options(dlg, node, ctx))   # 文案需要可见选项总数
            _sel_hint = _T.static("talk.pick_one") if _n == 1 else _T.text("talk.pick_range", n=_n)
            yield event.plain_result(_T.text("talk.bad_option", hint=_sel_hint))
            return
        player = self._player(group_id, qq_id)
        action = opt.get("action") or {}
        nxt = _TALK.next_of(opt)                          # `next`，缺失 → 结束哨兵
        # v124.3（审计）：apprentice_check 已注册为动作（talk_actions.py），
        # 主循环不再特判——条件型动作经 _apply_talk_action_async 返回的路由分发：
        #   "fail"（材料不足）→ 走选项 fail_next；"__end__"（副业未解锁 #101.29）→ 结束对话
        notices, _route = await self._apply_talk_action_async(group_id, qq_id, player, npc_id, action)
        if _route == "__end__":
            db.clear_talk_state(group_id, qq_id)
            lines = notices + [_T.text("talk.farewell", name=npc['name'])]
            yield event.plain_result("\n".join(lines))
            return
        if _route == "fail":
            nxt = _TALK.next_of(opt, failed=True)         # `fail_next`（存在但假值也不回落）
        # v95.11：talk 型主线与目标 NPC 对话即达成（active 空进度遗留态 → ready，修复主线卡死）
        notices += self._talk_quest_progress(group_id, qq_id, npc_id)
        # v105 P3：对话动作链落地后补成就判定（拜师/转职/任务交付等动作改 DB 后立即解锁——
        # 原实现无此调用，『拜师学艺/全知全能』等依赖学徒数的成就要等下次事件才判定，
        # 全知全能(第 8 条拜师)的全副业经验 +10% 加成也因此延迟生效）
        _ach.check_achievements(group_id, qq_id)
        if _TALK.is_end(nxt):
            db.clear_talk_state(group_id, qq_id)
            lines = notices + [_T.text("talk.farewell", name=npc['name'])]
            yield event.plain_result("\n".join(lines))
            return
        db.set_talk_state(group_id, qq_id, npc_id, nxt)
        new_node = _dlg.dialogue_node(dlg, nxt)
        ctx = self._talk_ctx(group_id, qq_id, npc_id)
        lines = notices + self._render_talk_node(npc, dlg, new_node, ctx)
        yield event.plain_result("\n".join(lines))
        return
    if not raw and any(c in msg for c in ("结束对话", "再见", "告辞")):
        db.clear_talk_state(group_id, qq_id)
        yield event.plain_result(_T.text("talk.farewell", name=npc['name']))
        return
    # 无参数/其他 → 重渲染当前节点
    lines = self._render_talk_node(npc, dlg, node, ctx)
    yield event.plain_result("\n".join(lines))


def _deliver_hint(self, npc_id):
    """交付方式提示（P4-2 壳：转调 services.quests_flow.deliver_hint）"""
    from . import quests_flow as qf
    return qf.deliver_hint(npc_id)


def _side_available_list(self, group_id, qq_id, npc_id, npc) -> list:
    """该 NPC 名下当前"可接"的支线清单（P4-2 壳：转调 services.quests_flow.side_available_list）"""
    from . import quests_flow as qf
    return qf.side_available_list(group_id, qq_id, npc_id, npc)


def _offer_side_quest(self, group_id, qq_id, npc_id, sid) -> list:
    """单条支线接取（P4-2 壳：转调 services.quests_flow.offer_side_quest）"""
    from . import quests_flow as qf
    return qf.offer_side_quest(group_id, qq_id, npc_id, sid)


def _offer_side_quests(self, group_id, qq_id, npc_id, npc):
    """NPC 有未接的支线任务时自动接取，返回通知行列表（P4-2 壳：转调 services.quests_flow.offer_side_quests）"""
    from . import quests_flow as qf
    return qf.offer_side_quests(group_id, qq_id, npc_id, npc)


async def turn_in(self, event: AstrMessageEvent, group_id, qq_id, player):
    quests = db.get_quests(group_id, qq_id)
    # v101.27 #341：夜晚 NPC 不在场不能隔空交付——用官方出现条件判定
    # （base_conditions_met 覆盖 period/condition.time/season/weather 等全部条件，
    # 采药女·小荨 condition.time=['morning','day'] 夜晚交付实锤）
    def _npc_absent(npc_id, npc):
        if not npc:
            return None
        if not _wild.base_conditions_met(npc_id, npc, player, group_id, qq_id):
            period_cn = (PERIOD_CN.get(_tw.current_period(), "") or "").strip()
            return _T.text("npcabsent.turnin", name=npc.get('name', '他'), period=period_cn)
        return None
    # 主线可交
    main_id = quests.get("main_quest")
    st = quests.get("main_status", "pending")
    if main_id and st == "ready":
        mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == main_id), None)
        if mq:
            npc = _cat_quests.NPCS.get(mq["giver"])
            if npc and npc["map"] == player["cur_map"]:
                absent = _npc_absent(mq["giver"], npc)
                if absent:
                    yield event.plain_result(absent)
                    return
                lines = self._take_main_quest(group_id, qq_id, mq["giver"], npc)
                yield event.plain_result("\n".join(lines))
                return
            else:
                giver = _cat_quests.NPCS.get(mq["giver"], {}).get("name", "？")
                giver_map = _cat_quests.NPCS.get(mq["giver"], {}).get("map", "")
                yield event.plain_result(_T.text("quest.giver_other", where=_cat_space.MAP_BY_ID.get(giver_map, {}).get('name', '？'),
                                         npc=giver))
                return
    # 支线可交
    # O100 修复：『交付任务』按当前 NPC/地图过滤——此前遍历 dict 顺序取第一个 ready
    # 支线，在城主处可能先命中"护送商货(需找老赵)"而忽略当场可交的"码头的猫"。
    # 现逻辑：① 当前地图有交付 NPC → 当场交付（过滤优先）；② 无当场可交但别处有
    # ready 支线 → 一次性列出全部可交付任务与位置（不再只报第一条误导玩家）。
    collect_missing = None  # 收集型材料还差的信息（用于最后提示）
    waiting = []  # O100：已达成但交付 NPC 不在当前地图的支线 [(任务名, NPC名, 地图名)]
    for sid, sq in list(quests.get("side", {}).items()):
        sqd = next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == sid), None)
        if not sqd:
            continue
        if sq.get("status") == "done":  # v95.12：已交付支线不重复接取/交付
            continue
        # R3 P1-4：副本内 NPC（潮汐祭司）交付解析 —— 三表真值链走引擎 `Lookup`
        npc = _LOOKUP_ALL.first(sqd["giver"])[0]
        obj = sqd["objective"]
        # 收集型：实时检查背包材料（不依赖 ready 状态）
        if obj.get("collect"):
            # v104 审计 P1-3：复合目标（魔剑士试炼 collect_count=2/count=3）门槛统一按
            # collect_count 判定（此前用 obj["count"]=3 与 quest_view 的 2 不一致：
            # 面板显示"✅ 可交"、交付却拒"还差 ×1(背包 2/3)"）
            need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 不再 KeyError
            have = db.count_item(group_id, qq_id, obj["collect"])
            if have >= need:
                if npc and npc["map"] == player["cur_map"]:
                    absent = _npc_absent(sqd["giver"], npc)
                    if absent:
                        yield event.plain_result(absent)
                        return
                    lines = self._complete_side_quest(group_id, qq_id, sid)
                    yield event.plain_result("\n".join(lines))
                    return
                else:
                    _row = _LOOKUP_ALL.first(sqd["giver"])[0] or {}   # 三表真值链（同一条链两处取值）
                    giver = _row.get("name", "？")
                    giver_map = _cat_space.MAP_BY_ID.get(_row.get("map", ""), {}).get("name", "？")
                    waiting.append((sqd["name"], giver, giver_map))
            else:
                collect_missing = (sqd["name"], obj["collect"], have, need)
            continue
        # 击杀/探索型：按 ready 状态
        if sq.get("status") == "ready":
            # v124 分支任务：输出选项等待玩家回复（不自动完成）
            if sqd.get("branch") and not sq.get("branch_wait"):
                lines = self._complete_side_quest(group_id, qq_id, sid)
                yield event.plain_result("\n".join(lines))
                return
            if npc and npc["map"] == player["cur_map"]:
                absent = _npc_absent(sqd["giver"], npc)
                if absent:
                    yield event.plain_result(absent)
                    return
                lines = self._complete_side_quest(group_id, qq_id, sid)
                yield event.plain_result("\n".join(lines))
                return
            else:
                _row = _LOOKUP_ALL.first(sqd["giver"])[0] or {}   # 三表真值链（同一条链两处取值）
                giver = _row.get("name", "？")
                giver_map = _cat_space.MAP_BY_ID.get(_row.get("map", ""), {}).get("name", "？")
                waiting.append((sqd["name"], giver, giver_map))
    # O100：无当场可交付时，列出全部"已达成待交付"任务（带位置），不再只报第一条
    if waiting:
        lines = [_T.static("quest.deliver_head")]
        for i, (qname, giver, giver_map) in enumerate(waiting, 1):
            lines.append(_T.text("quest.deliver_row", i=i, qname=qname, giver=giver, giver_map=giver_map))
        lines.append(self._tip("quest_deliver"))
        yield event.plain_result("\n".join(lines))
        return
    if collect_missing:
        name, mat, have, need = collect_missing
        yield event.plain_result(_T.text("quest.collect_short", name=name, mat=mat, gap=need - have, have=have, need=need))
        return
    yield event.plain_result(_T.static("quest.none_deliver"))


def _grant_quest_rewards(self, group_id, qq_id, qdef, lines):
    """v124.3 统一任务奖励发放（P4-2 壳：转调 services.quests_flow.grant_quest_rewards）"""
    from . import quests_flow as qf
    return qf.grant_quest_rewards(group_id, qq_id, qdef, lines)


def _complete_side_quest(self, group_id, qq_id, sid, branch_choice=None):
    """交支线任务，返回通知行列表（P4-2 壳：转调 services.quests_flow.complete_side_quest；_tip/_rule_fire 以 hooks 注入）"""
    from . import quests_flow as qf
    return qf.complete_side_quest(group_id, qq_id, sid, branch_choice, hooks={"tip": self._tip, "rule_fire": self._rule_fire})


async def rest_camp(self, event: AstrMessageEvent, group_id, qq_id, player):
    cur_map = _cat_space.MAP_BY_ID.get(player["cur_map"], {})
    mid = cur_map.get("id", "")
    if mid not in _cat_life.CAMP_SPOTS:
        yield event.plain_result(_T.static("camp.none"))
        return
    # v87.17 子区域绑定：营地在指定子区域，不在那边够不着火堆
    _camp = _cat_life.CAMP_SPOTS[mid]
    _camp_sa = _camp.get("subarea", "") if isinstance(_camp, dict) else ""
    if _camp_sa and player.get("cur_subarea") != _camp_sa:
        _sa_name = ""
        for _s in (cur_map.get("subareas") or []):
            if _s["id"] == _camp_sa:
                _sa_name = _s.get("name", "")
                break
        _camp_name = _camp.get("name", "营地") if isinstance(_camp, dict) else str(_camp)
        yield event.plain_result(
            _T.text("camp.wrong_spot", name=_camp_name, where=_sa_name or _camp_sa,
                where2=_sa_name or _camp_sa)
        )
        return
    if self._in_battle(group_id, qq_id):
        yield event.plain_result(_T.static("camp.battle"))
        return
    # 30 秒冷却
    last = db.get_event_state(f"camp_{group_id}_{qq_id}")
    if last and int(time.time()) - int(last) < 30:
        left = 30 - (int(time.time()) - int(last))
        yield event.plain_result(_T.text("camp.cooldown", sec=left))
        return
    # v94 体力：营地篝火恢复 50 体力（+ 原有半伤恢复）
    if player["hp"] >= player["max_hp"] and self._stamina(player) >= self._stamina_max(player):
        yield event.plain_result(_T.static("camp.not_needed"))
        return
    db.set_event_state(f"camp_{group_id}_{qq_id}", str(int(time.time())))
    heal = max(1, int((player["max_hp"] - player["hp"]) * 0.5))
    new_hp = min(player["max_hp"], player["hp"] + heal)
    _st_gain = self._add_stamina(group_id, qq_id, 50, player)
    db.update_player(group_id, qq_id, hp=new_hp)
    _p2 = self._player(group_id, qq_id)
    _st_line = _T.text("camp.restore_stamina", n=_st_gain, cur=self._stamina(_p2), cap=self._stamina_max(_p2)) if _st_gain > 0 else ""
    yield event.plain_result(
        _T.text("camp.ok", where=_cat_life.CAMP_SPOTS[mid], hp=heal, cur=new_hp, cap=player['max_hp'],
            tail=_st_line)
    )


async def rest(self, event: AstrMessageEvent, group_id, qq_id, player):
    if self._is_redname(qq_id):
        yield event.plain_result(_T.static("inn.redname"))
        return
    # v87.17 子区域化旅店：_at_healer 检查当前子区域，不在旅店给设施提示
    if not self._at_healer(player):
        hint = self._facility_hint(player, "healer")
        # v95.25 #134：示例不再写死"橡木镇旅店"——优先提示最近旅店（含当前城镇）
        if not hint:
            _cur_m = _cat_space.MAP_BY_ID.get(player.get("cur_map"), {})
            _near = []
            for _s in (_cur_m.get("subareas") or []):
                if _s.get("healer"):
                    _near.append(f"{_cur_m.get('name', '')}·{_s.get('name', '')}")
            hint = "、".join(_near[:3]) if _near else ""
        yield event.plain_result(
            _T.static("inn.none")
            + (_T.text("inn.hint_where", where=hint) if hint else _T.static("inn.hint_town"))
        )
        return
    # v101.25i4 住宿费：Lv.≤15 保持 max(30, lv×5)（新手友好不动）；
    # Lv.16+ 纯等级线性 每级 5×2=10 金 并向下取整到百（鱼鱼拍板：凑整，Lv.100=1000金）
    # v131：解耦 hp_stage_mult——怪物曲线放缓后住宿跟随掉到 900，违反拍板 1000；
    #       费用按等级不按百分比（鱼鱼铁律），金币产出侧已由 monster_gold ×1.3 补偿。
    # v125.1：数值下沉 econ_config.ECON_CONFIG
    _ec = _cat_life.ECON_CONFIG
    lv = player.get("level") or 1
    if lv <= _ec["inn_cost_lv_cap"]:
        cost = max(_ec["inn_cost_min_low"], lv * _ec["inn_cost_per_lv"])
    else:
        cost = max(_ec["inn_cost_min_high"],
                   int(lv * _ec["inn_cost_per_lv"] * _ec["inn_cost_high_mult"])
                   // _ec["inn_cost_round"] * _ec["inn_cost_round"])
    if player["gold"] < cost:
        yield event.plain_result(_T.text("inn.gold_short", gold=cost, have=player['gold']))
        return
    # v94 体力：住宿恢复满体力（+ 生命魔力）
    _st = self._stamina_max(player)
    db.update_player(group_id, qq_id, gold=player["gold"] - cost, hp=player["max_hp"], mp=player["max_mp"],
                     stamina=_st, stamina_ts=int(time.time()))
    yield event.plain_result(
        _T.text("inn.ok", stamina=self._stamina_bar({**player, 'stamina': _st}), gold=cost,
            left=player['gold'] - cost)
    )


async def reputation(self, event: AstrMessageEvent, group_id, qq_id, player):
    rep = db.get_reputation(group_id, qq_id)
    lines = [_T.static("rep.head"), "━━━━━━━━━━━━"]
    for i, fid in enumerate(_cat_b143.FACTION_ORDER, 1):
        f = _cat_b143.FACTIONS[fid]
        pts = rep.get(fid, 0)
        tier = _fac.faction_reputation_tier(pts)
        lines.append(f"{i:>2}. {f['icon']} {f['name']}：{tier}({pts})")
    lines.append("")
    lines.append(_T.static("rep.tip"))
    # v105 M18 P2-7：声望消费侧入口（声望商店按等级解锁专属商品）
    lines.append(self._tip("rep_shop"))
    yield event.plain_result("\n".join(lines))


async def rep_shop(self, event: AstrMessageEvent):
    """v105 M18 P2-7：势力声望商店——按声望等级解锁专属商品（声望只作门槛，金币购买）。

    用法：
      声望商店                       → 七势力总览（当前等级 + 可购商品数）
      声望商店 <势力名/序号>          → 查看该势力专属商品（🔒=声望不足）
      声望商店 <势力名/序号> 购买 <序号> → 购买商品（声望不足 → 提示所需等级）
    """
    # ★ B16-W11b：`FACTION_SHOP` 走包内门面（真源 game/data/factions.py:34；宿主聚合层未导出）
    group_id, qq_id = self._uid(event)
    raw = self._strip_cmd(event, "声望商店").strip()
    rep = db.get_reputation(group_id, qq_id)
    player = self._player(group_id, qq_id)

    def _tier_name(th):
        for _t, _n in _cat_b143.REPUTATION_TIERS:
            if th <= _t:
                return _n
        return "崇拜"

    def _resolve_faction(arg):
        if not arg:
            return None
        if arg.isdigit():
            i = int(arg)
            if 1 <= i <= len(_cat_b143.FACTION_ORDER):
                return _cat_b143.FACTION_ORDER[i - 1]
            return None
        for fid in _cat_b143.FACTION_ORDER:
            if arg in _cat_b143.FACTIONS[fid]["name"]:
                return fid
        return None

    # 无参数：总览
    if not raw:
        lines = [_T.static("repshop.head"), "━━━━━━━━━━━━"]
        for i, fid in enumerate(_cat_b143.FACTION_ORDER, 1):
            f = _cat_b143.FACTIONS[fid]
            pts = rep.get(fid, 0)
            tier = _fac.faction_reputation_tier(pts)
            goods = FACTION_SHOP.get(fid, [])
            unlocked = sum(1 for g in goods if pts >= g["tier"])
            lines.append(_T.text("repshop.faction_row", idx=i, name=f['icon'], title=f['name'], icon=tier, owned=pts,
                             total=unlocked, tail=len(goods)))
        lines.append("")
        lines.append(self._tip("rep_shop"))
        yield event.plain_result("\n".join(lines))
        return

    parts = raw.split()
    if parts[0] == "购买":
        yield event.plain_result(_T.static("repshop.usage"))
        return
    fid = _resolve_faction(parts[0])
    if not fid:
        yield event.plain_result(_T.static("repshop.no_faction"))
        return
    f = _cat_b143.FACTIONS[fid]
    pts = rep.get(fid, 0)
    tier = _fac.faction_reputation_tier(pts)
    goods = FACTION_SHOP.get(fid, [])
    if not goods:
        yield event.plain_result(_T.text("repshop.empty", name=f['icon'], tail=f['name']))
        return
    # 购买分支：声望商店 <势力> 购买 <序号>
    if len(parts) >= 3 and parts[1] == "购买":
        if not parts[2].isdigit():
            yield event.plain_result(_T.static("repshop.usage2"))
            return
        idx = int(parts[2])
        if idx < 1 or idx > len(goods):
            yield event.plain_result(_T.text("repshop.no_item", idx=idx, faction=f['name']))
            return
        g = goods[idx - 1]
        # 声望门槛拦截：不足 → 提示所需等级
        if pts < g["tier"]:
            need_name = _tier_name(g["tier"])
            yield event.plain_result(
                _T.text("repshop.rep_short", need=f['name'], faction=need_name, tier=g['tier'], cur=tier,
                    cur2=pts)
            )
            return
        it = _cat_items.ITEMS[g["item"]]
        price = int(g.get("price", it["price"]))
        if player["gold"] < price:
            yield event.plain_result(_T.text("repshop.gold_short", gold=price))
            return
        db.update_player(group_id, qq_id, gold=player["gold"] - price)
        itype = "材料" if g["item"] in _cat_items.MATERIALS else "消耗品"
        # v104 M09-P0 教训：全量拷贝定义字段（hot/effect 等），防丢字段
        db.add_item(group_id, qq_id, g["item"], {**it, "type": itype, "stackable": True, "price": price})
        yield event.plain_result(_T.text("repshop.buy_ok", faction=f['name'], name=it['name'], gold=price))
        return
    # 商品列表
    lines = [_T.text("repshop.panel_head", faction=f['icon'], title=f['name'], cur=tier, tier=pts), "━━━━━━━━━━━━"]
    for i, g in enumerate(goods, 1):
        it = _cat_items.ITEMS[g["item"]]
        need_name = _tier_name(g["tier"])
        price = int(g.get("price", it["price"]))
        if pts >= g["tier"]:
            mark, extra = "✅", _T.text("repshop.item_gold", gold=price)
        else:
            mark, extra = "🔒", _T.text("repshop.item_locked", tier_name=need_name, tier=g['tier'])
        lines.append(f"{i:>2}. {mark} {it['name']}（{it['desc']}）{extra}")
    lines.append("")
    lines.append(_T.text("repshop.panel_tip", faction=f['name']))
    yield event.plain_result("\n".join(lines))


def _camp_ctx(self, group_id, qq_id) -> dict:
    """读取玩家阵营数据（贡献 + 每日任务）。首次/无记录返回默认结构。"""
    raw = db.get_event_state(f"faction_camp_{group_id}_{qq_id}")
    data = {}
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else {}
        except (ValueError, TypeError):
            data = {}
    data.setdefault("contrib", 0)
    data.setdefault("tasks", [])
    data.setdefault("done_today", 0)
    data.setdefault("done_total", 0)
    data.setdefault("join_ts", 0)
    data.setdefault("date", "")
    return data


def _camp_save(self, group_id, qq_id, data: dict):
    db.set_event_state(f"faction_camp_{group_id}_{qq_id}", json.dumps(data, ensure_ascii=False))


async def camp_join(self, event: AstrMessageEvent):
    """v116：加入四大可选阵营（Lv.20 开放；可切换，缺省 7 天冷却（FACTION_CAMP_SWITCH_COOLDOWN））。

    用法：
      加入阵营           → 查看四大阵营列表 + 当前状态
      加入阵营 <编号>     → 加入对应阵营（如『加入阵营 1』）
    """
    group_id, qq_id = self._uid(event)
    player = self._player(group_id, qq_id)
    raw = self._strip_cmd(event, "加入阵营").strip()
    cur = (player.get("faction") or "").strip()
    camp_order = list(FACTION_CAMPS.keys())

    def _camp_line(i, cid):
        c = FACTION_CAMPS[cid]
        mark = _T.static("campjoin.line_here") if cur == cid else ""
        return f"{i:>2}. {c['icon']} {c['name']}：{c['desc']}{mark and '　' + mark or ''}"

    # 列表/查看当前
    if not raw or raw == "查看":
        lines = [_T.static("campjoin.head"), "━━━━━━━━━━━━"]
        for i, cid in enumerate(camp_order, 1):
            lines.append(_camp_line(i, cid))
        lines.append("")
        if cur:
            ccur = FACTION_CAMPS[cur]
            lines.append(_T.text("campjoin.current", icon=ccur['icon'], name=ccur['name']))
            lines.append(_T.text("campjoin.switch_tip", days=FACTION_CAMP_SWITCH_COOLDOWN // 86400))
        else:
            lines.append(_T.text("campjoin.lv_tip", lv=FACTION_CAMP_OPEN_LV))
            lines.append(_T.static("campjoin.after_tip"))
        yield event.plain_result("\n".join(lines))
        return

    # 加入指定阵营
    if not raw.isdigit():
        yield event.plain_result(_T.static("campjoin.usage"))
        return
    idx = int(raw)
    if idx < 1 or idx > len(camp_order):
        yield event.plain_result(_T.text("campjoin.no_idx", idx=idx))
        return
    target = camp_order[idx - 1]
    # 等级门槛
    lv = player.get("level") or 1
    if lv < FACTION_CAMP_OPEN_LV:
        yield event.plain_result(
            _T.text("campjoin.lv_short", need=FACTION_CAMP_OPEN_LV, lv=lv))
        return
    # 已加入判定
    if cur == target:
        c = FACTION_CAMPS[target]
        yield event.plain_result(_T.text("campjoin.already", icon=c['icon'], name=c['name']))
        return
    # 切换冷却判定（有当前阵营时）
    if cur:
        data = self._camp_ctx(group_id, qq_id)
        spent = int(time.time()) - int(data.get("join_ts", 0))
        if spent < FACTION_CAMP_SWITCH_COOLDOWN:
            left = FACTION_CAMP_SWITCH_COOLDOWN - spent
            ccur = FACTION_CAMPS[cur]
            yield event.plain_result(
                _T.text("campjoin.cooldown", icon=ccur['icon'], name=ccur['name'], days=left // 86400))
            return
    # 写入阵营
    db.update_player(group_id, qq_id, faction=target)
    data = self._camp_ctx(group_id, qq_id)
    data["join_ts"] = int(time.time())
    self._camp_save(group_id, qq_id, data)
    c = FACTION_CAMPS[target]
    # 成就判定：选择阵营（faction 非空）等
    _ach.check_achievements(group_id, qq_id)
    yield event.plain_result(
        _T.text("campjoin.ok", icon=c['icon'], name=c['name'], desc=c['desc'], tail=c['buff_text'])
    )


async def camp_task(self, event: AstrMessageEvent):
    """v116：每日阵营任务（收集型·主动交付闭环）。跨天自动重发，交付扣背包材料加贡献。

    用法：
      阵营任务           → 查看今日任务（跨天自动刷新分配）
      阵营任务 <序号>     → 交付对应任务（需背包有足够材料）
    说明：完成上限 FACTION_CAMP_DAILY_LIMIT（缺省 2）；击杀/Boss 型待 combat 挂钩二期。
    """
    group_id, qq_id = self._uid(event)
    player = self._player(group_id, qq_id)
    cur = (player.get("faction") or "").strip()
    if not cur:
        yield event.plain_result(_T.static("camptask.no_faction"))
        return
    c = FACTION_CAMPS[cur]
    raw = self._strip_cmd(event, "阵营任务").strip()

    # 取数据，跨天重置任务列表
    data = self._camp_ctx(group_id, qq_id)
    today = time.strftime("%Y-%m-%d")
    if data.get("date") != today:
        random.shuffle(FACTION_CAMP_DAILY_TASKS)
        data["tasks"] = [
            {"item": t["item"], "count": t["count"], "name": t["name"], "reward": t["reward"], "delivered": 0}
            for t in FACTION_CAMP_DAILY_TASKS[:FACTION_CAMP_DAILY_LIMIT]
        ]
        data["date"] = today
        data["done_today"] = 0
        self._camp_save(group_id, qq_id, data)

    tasks = data.get("tasks", [])
    # 查看
    if not raw:
        lines = [_T.text("camptask.head", icon=c['icon'], name=c['name']), "━━━━━━━━━━━━"]
        if not tasks:
            lines.append(_T.static("camptask.empty"))
        else:
            for i, t in enumerate(tasks, 1):
                have = db.count_item(group_id, qq_id, t["item"])
                mark = "✅" if t["delivered"] >= t["count"] else "⏳"
                need = t["count"]
                lines.append(_T.text("camptask.row", idx=i, mark=mark, name=t['name'], item=t['item'], qty=need,
                                 contrib=t['reward'], own=have))
            lines.append(_T.text("camptask.done_count", done=data.get('done_today', 0), total=FACTION_CAMP_DAILY_LIMIT))
        lines.append("")
        lines.append(_T.text("camptask.stat", contrib=data.get('contrib', 0), n=data.get('done_total', 0)))
        lines.append(self._tip("faction_task"))
        yield event.plain_result("\n".join(lines))
        return

    # 交付
    if not raw.isdigit():
        yield event.plain_result(_T.static("camptask.usage"))
        return
    idx = int(raw)
    if idx < 1 or idx > len(tasks):
        yield event.plain_result(_T.text("camptask.no_idx", idx=idx))
        return
    t = tasks[idx - 1]
    if t["delivered"] >= t["count"]:
        yield event.plain_result(_T.text("camptask.already", name=t['name']))
        return
    # 每日完成上限
    if data.get("done_today", 0) >= FACTION_CAMP_DAILY_LIMIT:
        yield event.plain_result(
            _T.text("camptask.limit", cap=FACTION_CAMP_DAILY_LIMIT))
        return
    # 扣背包材料（按收集型交付模式）
    have = db.count_item(group_id, qq_id, t["item"])
    if have < t["count"]:
        yield event.plain_result(
            _T.text("camptask.mat_short", name=t['name'], item=t['item'], qty=t['count'], own=have,
                tail=self._tip('faction_task')))
        return
    db.remove_item(group_id, qq_id, t["item"], t["count"])
    t["delivered"] = t["count"]
    data["contrib"] = int(data.get("contrib", 0)) + t["reward"]
    data["done_today"] = int(data.get("done_today", 0)) + 1
    data["done_total"] = int(data.get("done_total", 0)) + 1
    self._camp_save(group_id, qq_id, data)
    # 成就判定：阵营贡献≥100/500（阵营先锋/大陆之柱）在此推进
    _ach.check_achievements(group_id, qq_id)
    yield event.plain_result(
        _T.text("camptask.deliver_ok", name=t['name'], item=t['item'], qty=t['count'],
            contrib=t['reward'], cur=data['contrib'], done=data['done_today'],
            total=FACTION_CAMP_DAILY_LIMIT)
    )


async def camp_shop(self, event: AstrMessageEvent):
    """v116：阵营商店——用阵营贡献兑换军需物资（不花金币）。

    用法：
      阵营商店                 → 列出全部商品（贡献门槛）
      阵营商店 <序号>           → 购买对应商品（扣贡献，物品入包）
    """
    group_id, qq_id = self._uid(event)
    player = self._player(group_id, qq_id)
    cur = (player.get("faction") or "").strip()
    raw = self._strip_cmd(event, "阵营商店").strip()
    data = self._camp_ctx(group_id, qq_id)
    contrib = int(data.get("contrib", 0))
    head = _T.static("campshop.head")
    if cur:
        c = FACTION_CAMPS[cur]
        head = _T.text("campshop.panel_head", icon=c['icon'], name=c['name'], contrib=contrib)
    # 列表
    if not raw:
        lines = [head, "━━━━━━━━━━━━"]
        for i, g in enumerate(FACTION_CAMP_SHOP, 1):
            if contrib >= g["cost"]:
                mark, extra = "✅", _T.text("campshop.item_cost", contrib=g['cost'])
            else:
                mark, extra = "🔒", _T.text("campshop.item_locked", contrib=g['cost'])
            lines.append(f"{i:>2}. {mark} {g['name']} {extra}")
        lines.append("")
        if not cur:
            lines.append(self._tip("faction_shop"))
        else:
            lines.append(self._tip("faction_shop"))
        yield event.plain_result("\n".join(lines))
        return

    # 购买
    if not cur:
        yield event.plain_result(_T.static("campshop.no_faction"))
        return
    if not raw.isdigit():
        yield event.plain_result(_T.static("campshop.usage"))
        return
    idx = int(raw)
    if idx < 1 or idx > len(FACTION_CAMP_SHOP):
        yield event.plain_result(_T.text("campshop.no_idx", idx=idx))
        return
    g = FACTION_CAMP_SHOP[idx - 1]
    if contrib < g["cost"]:
        yield event.plain_result(
            _T.text("campshop.contrib_short", need=g['cost'], cur=contrib, tail=self._tip('faction_task')))
        return
    # 扣贡献 + 发物品
    data["contrib"] = contrib - g["cost"]
    self._camp_save(group_id, qq_id, data)
    it = _cat_items.ITEMS.get(g["item"]) or {"name": g["name"], "price": 0, "desc": ""}
    itype = "材料" if g["item"] in _cat_items.MATERIALS else "消耗品"
    db.add_item(group_id, qq_id, g["item"], {**it, "type": itype, "stackable": True, "price": it.get("price", 0)})
    yield event.plain_result(
        _T.text("campshop.buy_ok", name=g['cost'], item=it.get('name', g['name']), left=data['contrib'])
    )


async def camp_rank(self, event: AstrMessageEvent):
    """v116：阵营排行——按阵营统计成员数与总贡献（从 players.faction + event_state contrib 聚合）。

    用法：阵营排行
    """
    group_id, qq_id = self._uid(event)
    # 全服玩家（players 全局，跨群共用；group_id 仅作贡献键前缀用）
    players = db.all_players(group_id)
    camp_contrib = {cid: 0 for cid in FACTION_CAMPS}
    camp_count = {cid: 0 for cid in FACTION_CAMPS}
    for p in players or []:
        fid = (p.get("faction") or "").strip()
        if not fid or fid not in FACTION_CAMPS:
            continue
        camp_count[fid] = camp_count.get(fid, 0) + 1
        try:
            raw = db.get_event_state(f"faction_camp_{group_id}_{p['qq_id']}")
            if raw:
                d = json.loads(raw) if isinstance(raw, str) else {}
                camp_contrib[fid] += int(d.get("contrib", 0) or 0)
        except (ValueError, TypeError):
            pass
    ranked = sorted(FACTION_CAMPS.keys(),
                    key=lambda cid: (camp_count.get(cid, 0), camp_contrib.get(cid, 0)),
                    reverse=True)
    lines = [_T.static("camprank.head"), "━━━━━━━━━━━━"]
    for i, cid in enumerate(ranked, 1):
        c = FACTION_CAMPS[cid]
        lines.append(
            _T.text("camprank.row", idx=i, name=c['icon'], icon=c['name'], members=camp_count.get(cid, 0),
                contrib=camp_contrib.get(cid, 0)))
    lines.append("")
    lines.append(self._tip("faction"))
    yield event.plain_result("\n".join(lines))


async def chronicle(self, event: AstrMessageEvent, group_id, qq_id, player):
    c = random.choice(_cat_b143.CHRONICLES)
    yield event.plain_result(
        _T.text("chronicle.panel", title=c['title'], text=c['text'])
    )


__all__ = ["_map_facilities", "_map_scene", "_visible_sas", "_conn_target", "_conn_subarea_name", "_home_map_id", "deed_view", "deed_buy", "deed_sell", "_deed_upgrade", "go_home", "go_out", "visit_home", "_home_storage_key", "_home_storage_load", "_home_storage_save", "home_storage", "home_storage_take", "map_view", "region_view", "_map_blocks", "_map_nav_body", "location_view", "_hurry_type", "_hurry_section", "_hurry_panel", "hurry_view", "_move_blocked_msg", "back_cmd", "ask_way", "move", "_subarea_arrive", "_instance_dungeon_move", "_travel_ambush", "portal_view", "portal_activate", "portal_travel", "_update_explore_quests", "quest_accept", "_sq_unlocked", "_sq_stats_met", "_available_quest_list", "quest_abandon", "daily", "_daily_pool", "_bump_daily_progress", "_home_view", "_current_npcs", "_present_wild_hints", "_start_talk_list", "_find_npc_in_map", "_town_npc_absent_hint", "_player_map_name", "_subarea_name", "_find_wild_npc", "_wild_unseen_hint", "_npc_direction_hint", "_npc_dialogue", "_take_main_quest", "_obj_text", "_obj_text_lines", "_quest_reputation", "_wild_cond_label", "time_cmd", "wild_notes", "npc_quick_dialog", "find_npc", "_grant_wild_unlock_flags", "_teach_by_npc", "interact_prop", "_talk_active", "_talk_ctx", "_side_menu_expand", "_render_talk_node", "_branch_wait_sid", "_weapon_pick_active", "_weapon_pick_choose", "_remove_one_by_name", "_update_use_quests", "_talk_quest_progress", "_do_join_class", "_do_evolve_via_npc", "_apply_talk_action_async", "_apply_talk_action", "talk_choice", "_deliver_hint", "_side_available_list", "_offer_side_quest", "_offer_side_quests", "turn_in", "_grant_quest_rewards", "_complete_side_quest", "rest_camp", "rest", "reputation", "rep_shop", "_camp_ctx", "_camp_save", "camp_join", "camp_task", "camp_shop", "camp_rank", "chronicle"]
