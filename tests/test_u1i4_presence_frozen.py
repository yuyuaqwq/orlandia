# -*- coding: utf-8 -*-
"""U1-I4 冻结比对**门禁②**（在场块）：`content/wild.py` 换引擎在场派生 + `content/persistence/world.py` 文本钉。

跑法（工作区根；环境变量见 `BRIEF.md` §3.1）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1i4_presence_gen.py --check
    "$PY" work/pkg/tests/test_u1i4_presence_frozen.py

判据（`design/U1-I4_FROZEN_GATE.md` §10；本文件逐条打原始输出）
-------------------------------------------------------------
 [1] **25 段冻结文本 sha256 全等 `_PIN["frozen"]`** + **活实现 `inspect.getsource` sha256 全等 `_PIN["live"]`**
     （`_PIN["live"][…] == "<deleted>"` = 该符号本批**已删除**，另断言活模块里确实没有）。
     `phase == "landed"` 时再断言 C 栏「预期会变」段的 `frozen != live`（§2.3）。
 [2] **网格 A（定位，逐格）** 489 × 62 = **30,318** 格：`npc_map_id` + `town_npc_day_sa` 旧 ↔ 新。
     另加**台词网格** 431 × 62 = **26,722** 格（`town_npc_dialogue`，覆盖 `lines` 派生）。
 [3] **网格 B（在场，满格）** 431 × 185 场所 × 7 代表日 × `now` 三态 = **1,674,435** 格
     （`town_npc_visible` 旧 ↔ 新）；**条件矩阵**：`base_conditions_met` / `unlock_met`
     （十字段全量 + 单开 + 两两/三三组合 + 5 个数据里 0 条的合成字段）。
 [4] **网格 C（偶遇）** 47 野外 × cycle 命中/不命中 × miss ∈ {0,6,7,8} × 冷却 ∈ {0,1799,1800,1801}
     = **1,504** 格：`roll_wild_encounter` 返回值 + `wildmeta` 终态**逐键** + 限时挂载。
 [5] **网格 D（列表）** 121 图 + 628 子区域 = 749 用例 × 0..3 限时事件 = **2,996** 用例 ×
     3 份列表实现（`_map_blocks` / `_hurry_section` / `_current_npcs`）：**行序 + 行内容 + 编号**逐行比
     （含 `inline_npcs` 合成用例）；另 **编号网格**（`_start_talk_list` 静态 N × 限时 M）。
 [6] **aux 指纹**：`ALL_WILD` 63 键序 · `wildmeta_*` JSON 文本 · `timed_events_*` 键格式 ·
     子区域序 · 三张 NPC 表指纹 · 会话/flag 键格式与 JSON 文本（§3 的 ②③④⑤⑥⑦⑨）。
 [7] **口径分歧 12 条**（`U1-I4_DESIGN.md` §3.7）各 ≥1 条断言（含 ④ 首个同名早退、⑪ miss 命中不清零）。
 [8] **有牙反证** 3 处（`appear` 恒真 / 定位派生换盐 / 保底阈值恒不保底）→ 对应探针**必须变红**；
     再跑多故障场景（两处同坏 + 第三处仍绿）。
 [9] **只读断言**：跑完全程 5 个源文件 sha256 不变（全程零写盘）。
 [10] **计数校验**：逐网格 `sum(比对次数) == 预期`（防「循环没跑」的假绿）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1i4_presence_gen.py` 从 `base/pkg/**`
   逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
"""
from __future__ import annotations

import ast
import contextlib
import datetime
import hashlib
import inspect
import io
import json
import os
import random
import sys
import tempfile
import types

# ══════════════════════════════════════════════════════════════════════════════
# 0. 装配：包根 / 引擎根 / 宿主壳根（`_paths` 单点）+ 独立私有库 + shim_astrbot
# ══════════════════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ★ 独立私有库（绝不碰生产 game_data.db；`conftest` 与本文件同口径用 setdefault）
# 2026-09-18 收尾修：原落点 `LANE_ROOT/out` 是旧「工作区布局」（`<lane>/work/pkg` 三层），
#   真仓布局下 LANE_ROOT = `C:\Users` ⇒ `C:\Users\out` 不存在 → sqlite connect 直接
#   `unable to open database file`（单跑必崩；改前基线同样红，非本次修复引入）。
#   私有库改落系统临时目录下自建子目录（不写包目录、不进 git）。
_DB_DIR = os.path.join(tempfile.gettempdir(), "gwen_test_u1i4_presence")
os.makedirs(_DB_DIR, exist_ok=True)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_DB_DIR, "test_u1i4_presence.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(LANE_ROOT, "work", "eng"))
os.environ.setdefault("GWEN_HOST_DIR", os.path.join(LANE_ROOT, "work", "host"))
_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

import _paths                                                             # noqa: E402
import _engine_harness as H                                              # noqa: E402

db = H.db
Main = H.Main

from content import wild as W                                            # noqa: E402
from content import world_cmds as WC                                     # noqa: E402
from content import timed_events as TE                                   # noqa: E402
from content.persistence import world as PW                              # noqa: E402
from content.catalog_quests import NPCS, WILD_NPCS, HIDDEN_NPCS          # noqa: E402
from content.catalog_space import MAP_BY_ID as _MAP_BY_ID                # noqa: E402
import ext_social.presence as PRES                                  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_MISSING = object()


# >>> _u1i4_gen (auto) >>>

# ⚠ 本块由 `tests/_u1i4_presence_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/wild.py::_wild_tables': 'def _wild_tables():\n    """包内两张 NPC 表（真源模块级 `from ..data.wild_npcs import WILD_NPCS, HIDDEN_NPCS`）。"""\n    return _WILD_NPCS_47, _HIDDEN_NPCS_22\n',
    'content/wild.py::_ALL_WILD': 'def _ALL_WILD() -> dict:\n    """真源 `ALL_WILD = {**WILD_NPCS, **HIDDEN_NPCS}`（`core.wild` import 期求值一次）。\n\n    真源快照发生在 `data/_assembly.py:163` 把 6 条层内 NPC 并进 `HIDDEN_NPCS` **之前**\n    ⇒ 真源 ALL_WILD = wild 47 ∪ hidden 16 = **63** 条；这里用 `not inst_stage` 精确还原\n    （与 `content/talk_actions.py` 同口径），首次调用后缓存 = 真源的「import 期求值一次」。\n\n    ★ B16-W8：源在包内 ⇒ 取值与「谁先触发」解耦，恒为 63。改前两张表走宿主句柄，\n    而宿主 `HIDDEN_NPCS` 是**会被装配期就地 update 的同一只字典**，`game.*` 回退路径下\n    实测取到过 69（并入后）。\n    """\n    global _ALL_WILD_CACHE\n    if _ALL_WILD_CACHE is None:\n        _ALL_WILD_CACHE = {**_WILD_NPCS_47,\n                           **{k: v for k, v in _HIDDEN_NPCS_22.items()\n                              if k not in _INST_STAGE_IDS}}\n    return _ALL_WILD_CACHE\n',
    'content/wild.py::_wild_npc_expire': 'def _wild_npc_expire(group_id, qq_id, data):\n    try:\n        db.clear_talk_state(group_id, qq_id)\n    except Exception:\n        pass  # 清除失败无副作用\n',
    'content/wild.py::_day_hash': 'def _day_hash(seed: int, salt: str = "") -> int:\n    h = seed * 2654435761 + (sum(ord(c) for c in salt) if salt else 0)\n    return h & 0x7FFFFFFF\n',
    'content/wild.py::npc_map_id': 'def npc_map_id(npc_id: str, npc: dict, now: datetime.date | None = None) -> str | None:\n    """NPC 当天所在地图：roam 用日期哈希定位，否则返回固定 map"""\n    roam = npc.get("roam")\n    if roam:\n        now = now or datetime.date.today()\n        return roam[_day_hash(now.toordinal(), npc_id) % len(roam)]\n    return npc.get("map")\n',
    'content/wild.py::_quest_known': 'def _quest_known(q: dict, qid: str) -> bool:\n    """任务已知(主线完成 / 支线已接或进行中)。支线完成即从 side 删除，无完成记录。"""\n    return qid in q.get("completed_main", []) or qid in q.get("side", {})\n',
    'content/wild.py::unlock_met': 'def unlock_met(npc_id: str, npc: dict, group_id: str, qq_id: str) -> bool:\n    """解锁条件(unlock)：flag:xxx / item:mat_xxx / quest:qid。无 unlock=天然解锁。"""\n    unlock = npc.get("unlock")\n    if not unlock:\n        return True\n    if unlock.startswith("flag:"):\n        flag = unlock[5:]\n        # v104 P1（M21）：扫全量 flag 桶——flag 可能由其他 NPC 对话设置（如 说书人·巴尔 →\n        # heard_owl_song），只查本 NPC 自己的桶会永久锁死。base_conditions_met 已有全桶扫描先例。\n        return any(flag in db.get_talk_flags(group_id, qq_id, nid) for nid in _ALL_WILD())\n    if unlock.startswith("item:"):\n        item = unlock[5:]\n        return db.count_item(group_id, qq_id, item) > 0\n    if unlock.startswith("quest:"):\n        qid = unlock[6:]\n        return _quest_known(db.get_quests(group_id, qq_id), qid)\n    if unlock.startswith("quest_done:"):\n        # v87：已完成任务解锁（如 图书管理员·贝拉 需通关圣堂地窖/主线第11章）\n        qid = unlock[11:]\n        q = db.get_quests(group_id, qq_id)\n        if _quest_known(q, qid):\n            return True\n        # v104 P1（M21）：quest_done 兼容副本 id——battle_state 中该副本已通关(cleared)\n        # 也算达成（副本通关不写 quests 完成记录，battle_state 是唯一临时标记；\n        # 持久路径为 unlock 指向主线任务 id，如 q11_3）\n        try:\n            _row = db.get_battle(group_id, qq_id)\n            if _row:\n                _st = _row.get("state") or {}\n                if _st.get("cleared") and _st.get("inst_id") == qid:\n                    return True\n        except Exception:\n            pass\n        return False\n    if unlock.startswith("stats:"):\n        # v124 隐藏线触发：stats 计数门槛（如 候鸟·翎信 需垂钓 10 次）——stats:key:min\n        try:\n            _key, _min = unlock[6:].split(":", 1)\n            _st = db.get_stats(group_id, qq_id) or {}\n            return int(_st.get(_key, 0) or 0) >= int(_min)\n        except Exception:\n            return False\n    return True\n',
    'content/wild.py::base_conditions_met': 'def base_conditions_met(npc_id: str, npc: dict, player: dict, group_id: str, qq_id: str) -> bool:\n    """基础出现条件(AND)：time/season/weather/min_level/max_level/quest_done/quest_active/flag/item/day_of_week"""\n    cond = npc.get("condition", {})\n    # 时间段\n    t = cond.get("time")\n    if t and current_period() not in t:\n        return False\n    # 季节\n    s = cond.get("season")\n    if s and current_season() not in s:\n        return False\n    # 天气\n    w = cond.get("weather")\n    if w:\n        cur_w = today_weather(npc_map_id(npc_id, npc))\n        if w == "sunny":\n            if cur_w not in ("sunny", "cloudy"):\n                return False\n        elif cur_w != w:\n            return False\n    # 等级区间\n    if cond.get("min_level") and player.get("level", 1) < cond["min_level"]:\n        return False\n    if cond.get("max_level") and player.get("level", 1) > cond["max_level"]:\n        return False\n    q = db.get_quests(group_id, qq_id)\n    # 已完成任务\n    qd = cond.get("quest_done")\n    if qd and not all(_quest_known(q, x) for x in qd):\n        return False\n    # 任务进行中\n    # v105 M23 P2-7：原只查 side（支线），主线进行中（main_status=active 且 main_quest 命中）\n    # 也会被误判不满足——补主线查询。当前数据层无 quest_active 使用者（潜伏），语义对齐无行为变化\n    qa = cond.get("quest_active")\n    if qa:\n        _side = q.get("side", {})\n        _main_hit = q.get("main_status") == "active" and q.get("main_quest") in qa\n        if not _main_hit and not any(x in _side for x in qa):\n            return False\n    # 对话 flag（任意 NPC 的 flag 都算——talkflags 按 NPC 分组，这里扫全部）\n    if cond.get("flag"):\n        if not any(cond["flag"] in db.get_talk_flags(group_id, qq_id, nid) for nid in _ALL_WILD()):\n            return False\n    # 持有道具\n    if cond.get("item") and db.count_item(group_id, qq_id, cond["item"]) <= 0:\n        return False\n    # 星期（周一=0）\n    dw = cond.get("day_of_week")\n    if dw and datetime.date.today().weekday() not in dw:\n        return False\n    return True\n',
    'content/wild.py::_get_meta': 'def _get_meta(group_id: str, qq_id: str) -> dict:\n    raw = db.get_event_state(WILD_META_KEY.format(gid=group_id, qid=qq_id))\n    if not raw:\n        return {"met": [], "miss": {}, "last": {}}\n    try:\n        return json.loads(raw)\n    except (ValueError, TypeError):\n        return {"met": [], "miss": {}, "last": {}}\n',
    'content/wild.py::_save_meta': 'def _save_meta(group_id: str, qq_id: str, meta: dict):\n    db.set_event_state(WILD_META_KEY.format(gid=group_id, qid=qq_id),\n                       json.dumps(meta, ensure_ascii=False))\n',
    'content/wild.py::met_wild': 'def met_wild(group_id: str, qq_id: str) -> list:\n    """见闻录：已遇见的野外 NPC id 列表"""\n    return _get_meta(group_id, qq_id).get("met", [])\n',
    'content/wild.py::_roll_random': 'def _roll_random(npc_id: str, npc: dict, group_id: str, qq_id: str) -> bool:\n    """随机性判定：cycle 硬条件 + chance 概率(含保底)。返回是否出现。"""\n    cycle = npc.get("cycle")\n    if cycle and datetime.date.today().toordinal() % cycle != 0:\n        return False\n    chance = npc.get("chance")\n    if not chance:\n        return True\n    meta = _get_meta(group_id, qq_id)\n    miss = meta.get("miss", {}).get(npc_id, 0)\n    if miss >= MISS_GUARANTEE:\n        meta.setdefault("miss", {}).pop(npc_id, None)  # 保底必出 = 本次遇到，清计数\n        _save_meta(group_id, qq_id, meta)\n        return True  # 保底：连续 7 次未遇必出\n    if random.random() < chance:\n        return True\n    meta.setdefault("miss", {})[npc_id] = miss + 1\n    _save_meta(group_id, qq_id, meta)\n    return False\n',
    'content/wild.py::wild_npc_findable': 'def wild_npc_findable(npc_id: str, npc: dict, player: dict, group_id: str, qq_id: str) -> bool:\n    """『找 <名字>』直接寻找的判定：解锁 + 基础条件 + cycle 硬条件（跳过 chance——\n    主动寻找不受概率限制，条件满足就能找到；cycle 是硬规律必须满足）。"""\n    if npc.get("cycle") and datetime.date.today().toordinal() % npc["cycle"] != 0:\n        return False\n    return unlock_met(npc_id, npc, group_id, qq_id) and base_conditions_met(npc_id, npc, player, group_id, qq_id)\n',
    'content/wild.py::roll_wild_encounter': 'def roll_wild_encounter(group_id: str, qq_id: str, player: dict, map_id: str):\n    """探索/进入地图时调用：当前地图满足条件的野外 NPC → 返回 (npc_id, npc)，否则 None。\n\n    记录见闻录 + 清保底计数 + 30 分钟冷却（同一 NPC 30 分钟内不重复偶遇，防蹲守刷屏）。\n    只返回第一个命中的 NPC（偶遇一次）。\n    """\n    today = datetime.date.today()\n    now = int(datetime.datetime.now().timestamp())\n    meta = _get_meta(group_id, qq_id)\n    for nid, npc in _ALL_WILD().items():\n        if npc_map_id(nid, npc, today) != map_id:\n            continue\n        if not unlock_met(nid, npc, group_id, qq_id):\n            continue\n        if not base_conditions_met(nid, npc, player, group_id, qq_id):\n            continue\n        # 30 分钟冷却（偶遇过的不立刻重复出现）\n        last = meta.get("last", {}).get(nid, 0)\n        if last and now - last < 1800:\n            continue\n        if not _roll_random(nid, npc, group_id, qq_id):\n            continue\n        # 偶遇！见闻录记录 + 清保底 + 冷却\n        if nid not in meta["met"]:\n            meta["met"].append(nid)\n        meta.setdefault("miss", {}).pop(nid, None)\n        meta.setdefault("last", {})[nid] = now\n        _save_meta(group_id, qq_id, meta)\n        # v127.5 限时NPC：偶遇命中 → 挂"在场限时"事件（通用懒计时引擎）。\n        # 时长按 NPC 的 duration 分钟（缺省 60）；map 用 npc_map_id 支持 roam 当日定位。\n        _dur_min = npc.get("duration", 60) or 60\n        set_timed(group_id, qq_id, f"wild:{nid}", "wild_npc",\n                  data={"npc_id": nid, "map": npc_map_id(nid, npc, today)},\n                  duration_sec=int(_dur_min) * 60)\n        return nid, npc\n    return None\n',
    'content/wild.py::nearby_hints': 'def nearby_hints(group_id: str, qq_id: str, player: dict, map_id: str) -> list:\n    """『时间』指令：当前地图满足条件(含随机性)的野外 NPC 提示列表(供"附近可遇"显示)"""\n    hints = []\n    today = datetime.date.today()\n    for nid, npc in _ALL_WILD().items():\n        if npc_map_id(nid, npc, today) != map_id:\n            continue\n        if not unlock_met(nid, npc, group_id, qq_id):\n            continue\n        if not base_conditions_met(nid, npc, player, group_id, qq_id):\n            continue\n        hints.append((nid, npc))\n    return hints\n',
    'content/wild.py::town_npc_day_sa': 'def town_npc_day_sa(npc_id: str, npc: dict, home_sa: str, now: datetime.date | None = None) -> str | None:\n    """城镇 NPC 今日所在子区域（B 游走）。\n\n    - 无 roam → 返回 home_sa（静态）\n    - 有 roam（同图子区域 id 列表）→ 日期哈希定位当天位置\n    返回 None 仅表示数据异常（roam 列表空），正常恒返回一个 sa id。\n    """\n    roam = npc.get("roam")\n    if not roam:\n        return home_sa\n    now = now or datetime.date.today()\n    return roam[_day_hash(now.toordinal(), npc_id) % len(roam)]\n',
    'content/wild.py::town_npc_visible': 'def town_npc_visible(npc_id: str, npc: dict, sa_id: str, now: datetime.date | None = None) -> bool:\n    """城镇 NPC 当前是否在指定子区域可见（B 游走 + C 随机出现 + D 时段）。\n\n    - 功能 NPC（funcs 非空）恒可见（铁律）\n    - period 时段不符 → 不可见（『找』提示时段）\n    - appear 概率（日期哈希，如 0.7 = 7 成天数出现）→ 不可见（『找』提示没来）\n    - roam 当天位置 ≠ sa_id → 不可见（『找』提示去向）\n    """\n    if npc.get("funcs"):\n        return True\n    # D 时段（v95.30b 修复：period 判定必须确定性——now 未传（生产）用真实时钟，\n    # 传 date 对象（测试固定日期）→ 固定白天映射；传 datetime → 按该时间）\n    per = npc.get("period")\n    if per:\n        if now is None:\n            _cur = current_period()\n        elif isinstance(now, datetime.datetime):\n            _cur = current_period(now)\n        else:\n            _cur = "day"\n        if _cur not in per:\n            return False\n    now = now or datetime.date.today()\n    # C 随机出现（appear ∈ (0,1]，日期哈希全服一致）\n    app = npc.get("appear")\n    if app is not None and app < 1.0:\n        if _day_hash(now.toordinal(), npc_id + ":appear") % 100 >= int(app * 100):\n            return False\n    # B 游走：今天在这才可见\n    if town_npc_day_sa(npc_id, npc, sa_id, now) != sa_id:\n        return False\n    return True\n',
    'content/wild.py::town_npc_dialogue': 'def town_npc_dialogue(npc_id: str, npc: dict, base: str, now: datetime.date | None = None) -> str:\n    """A 随机台词：funcs=[] 且配置了 lines（多条）→ 按日期哈希选一条（每天换台词，全服一致）。\n\n    功能 NPC / 未配置 lines / 配置了对话树（多轮）→ 返回原台词。\n    """\n    if npc.get("funcs"):\n        return base\n    lines = npc.get("lines")\n    if not lines or len(lines) < 2:\n        return base\n    now = now or datetime.date.today()\n    return lines[_day_hash(now.toordinal(), npc_id + ":line") % len(lines)]\n',
    'content/persistence/world.py::talk_state_key': 'def talk_state_key(group_id, qq_id):\n    return f"talk_{group_id}_{qq_id}"\n',
    'content/persistence/world.py::talk_flags_key': 'def talk_flags_key(group_id, qq_id):\n    return f"talkflags_{group_id}_{qq_id}"\n',
    'content/persistence/world.py::get_talk_state': 'def get_talk_state(group_id, qq_id):\n    """返回当前对话会话 {"npc": id, "node": id} 或 None"""\n    raw = get_event_state(talk_state_key(group_id, qq_id))\n    if not raw:\n        return None\n    try:\n        import json\n        return json.loads(raw)\n    except (ValueError, TypeError):\n        return None\n',
    'content/persistence/world.py::set_talk_state': 'def set_talk_state(group_id, qq_id, npc_id, node_id):\n    """保存对话会话"""\n    import json\n    set_event_state(talk_state_key(group_id, qq_id),\n                    json.dumps({"npc": npc_id, "node": node_id}, ensure_ascii=False))\n',
    'content/persistence/world.py::clear_talk_state': 'def clear_talk_state(group_id, qq_id):\n    """结束对话(删除会话，flag 保留)"""\n    delete_event_state(talk_state_key(group_id, qq_id))\n',
    'content/persistence/world.py::get_talk_flags': 'def get_talk_flags(group_id, qq_id, npc_id):\n    """该 NPC 已设置的对话 flag 列表"""\n    raw = get_event_state(talk_flags_key(group_id, qq_id))\n    if not raw:\n        return []\n    try:\n        import json\n        data = json.loads(raw)\n        return list(data.get(npc_id, []))\n    except (ValueError, TypeError):\n        return []\n',
    'content/persistence/world.py::set_talk_flag': 'def set_talk_flag(group_id, qq_id, npc_id, flag):\n    """给该 NPC 设置对话 flag(幂等)"""\n    import json\n    key = talk_flags_key(group_id, qq_id)\n    raw = get_event_state(key)\n    data = {}\n    if raw:\n        try:\n            data = json.loads(raw)\n        except (ValueError, TypeError):\n            data = {}\n    lst = list(data.get(npc_id, []))\n    if flag not in lst:\n        lst.append(flag)\n    data[npc_id] = lst\n    set_event_state(key, json.dumps(data, ensure_ascii=False))\n',
    # ── 额外夹具（不计入 25 段）：网格 D 旧侧（门禁③ 的文件，本线只读不改）──
    'content/world_cmds.py::_current_npcs': 'def _current_npcs(self, player):\n    """v86 子区域：当前所在位置可交互的 NPC 列表(子区域优先，回退地图级)。\n    v95.30 随机性：酱油 NPC 按 游走/概率/时段 过滤（功能 NPC 恒在）。"""\n    cur_map = player["cur_map"]\n    m = _cat_space.MAP_BY_ID.get(cur_map, {})\n    sa_id = player.get("cur_subarea") or ""\n    for sa in (m.get("subareas") or []):\n        if sa["id"] == sa_id:\n            npc_ids = sa.get("npcs") or []\n            return [_cat_quests.NPCS[nid] for nid in npc_ids if nid in _cat_quests.NPCS\n                    and _wild.town_npc_visible(nid, _cat_quests.NPCS[nid], sa_id)]\n    return [_cat_quests.NPCS[nid] for nid in m.get("npcs", []) if nid in _cat_quests.NPCS]\n',
    'content/world_cmds.py::_present_wild_hints': 'def _present_wild_hints(self, group_id, qq_id, cur_map) -> list:\n    """v127.5 限时NPC：当前地图（map 级，全图都算）在场限时野外NPC 显示行。\n\n    偶遇后挂 timed events，倒计时内地图/位置可见并带 ⏳ 剩余分钟；过期\n    list_timed 惰性清除 → 天然消失（显示与对话同时，铁律）。\n    返回例：["  🧭游商·老马 ⏳剩60分", ...]（2 空格缩进，与普通 NPC 行一致）。\n    """\n    lines = []\n    evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",\n                       data_match={"map": cur_map})\n    for ev in evs:\n        nid = ev.get("data", {}).get("npc_id") or ""\n        wnpc = _wild.ALL_WILD.get(nid)\n        if not wnpc:\n            continue\n        remain_min = max(1, -(-int(ev.get("remain", 0)) // 60))  # ceil(remain/60)\n        lines.append(f"  {wnpc.get(\'icon\', \'\')}{wnpc.get(\'name\', nid)} ⏳剩{remain_min}分")\n    return lines\n',
    'content/world_cmds.py::_start_talk_list': 'def _start_talk_list(self, group_id, qq_id) -> list:\n    """当前地图 NPC 列表（带序号展示；交谈用『对话 <名字>』/『对话 <序号>』，v123a 起裸数字不再直接找 NPC）。『对话』空参共用。"""\n    player = self._player(group_id, qq_id)\n    if player and player["cur_map"].startswith("home_"):\n        return ["家里没有 NPC 可以交谈～『出门』去镇上找人吧！"]\n    npcs = self._current_npcs(player) if player else []\n    # v127.5 限时NPC：在场野外旅人并入裸『对话』列表（排城镇 NPC 之后，带序号可对话）\n    wild_evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",\n                            data_match={"map": player["cur_map"]}) if player else []\n    if not npcs and not wild_evs:\n        return ["这里没有 NPC。输入『地图』看看哪里有 NPC～"]\n    lines = ["👥 这里的 NPC："]\n    for i, n in enumerate(npcs, 1):\n        lines.append(f"{i:>2}. {n[\'icon\']}{n[\'name\']}({n[\'title\']})")\n    # 在场野外旅人：续在城镇 NPC 之后编号（带 ⏳ 剩余分钟）\n    for j, ev in enumerate(wild_evs, len(npcs) + 1):\n        nid = ev.get("data", {}).get("npc_id") or ""\n        wnpc = _wild.ALL_WILD.get(nid)\n        if not wnpc:\n            continue\n        remain_min = max(1, -(-int(ev.get("remain", 0)) // 60))  # ceil(remain/60)\n        lines.append(f"{j:>2}. {wnpc.get(\'icon\', \'\')}{wnpc.get(\'name\', nid)} ⏳剩{remain_min}分")\n    lines.append(self._tip("npc_list"))\n    return lines\n',
    'content/world_cmds.py::_map_blocks': 'def _map_blocks(self, player: dict, cur_map: dict, cur_sa: str,\n                group_id=None, qq_id=None) -> list:\n    """v132 从 map_view 抽取：位置导航之外的完整区块（今日奇遇/设施/场景/NPC/旅人/玩家/怪物/tip）。\n\n    『地图』与 `_subarea_arrive`（到达视图）共用此方法 → 两处排版永不分裂\n    （v101.25c 铁律：鱼鱼抓"前往不同区域提示模板不一样"）。\n    cur_sa 传 sa id：到达视图时 player.cur_subarea 尚未更新为落点（v87.13b 同源处理）。\n    """\n    lines = []\n    cur = cur_map.get("id", "")\n    sas = cur_map.get("subareas") or []\n    # v132.2 全地图紧凑模式（鱼鱼拍板：地图排版统一 ●横排模板，不再区分城镇/野外）\n    _compact = True\n    # v115 今日奇遇：面板底部一行（getattr 兜底，A/C 未就绪则不显示）\n    _today_ev_fn = getattr(_daily_events, "today_map_event", None)\n    if _today_ev_fn is not None:\n        try:\n            _ev = _today_ev_fn(cur)\n            if _ev and _ev.get("name"):\n                _ev_fx = (_ev.get("effects") or {})\n                _ev_note = ""\n                if _ev_fx.get("encounter_rate", 0) > 0:\n                    _ev_note = "(遇怪率↑)"\n                elif _ev_fx.get("event_chance", 0) > 0:\n                    _ev_note = "(事件率↑)"\n                elif _ev_fx.get("loot_mult", 1.0) > 1.0:\n                    _ev_note = f"(掉落×{_ev_fx.get(\'loot_mult\', 1.0)})"\n                lines.append(f"🌤 今日奇遇：{_ev[\'name\']}——{_ev.get(\'desc\', \'\')}{_ev_note}")\n        except Exception:\n            pass\n    # v87.4 区块间统一空行分隔（不再叠分隔线）\n    if lines and lines[-1]:\n        lines.append("")\n    # 此地设施 + 场景（v87.13 拆分：设施=功能入口，场景=氛围景物）\n    fac = self._map_facilities(cur_map, player, cur_sa)\n    if fac:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("🏪 此地设施：")\n        if _compact:\n            lines.append("  ●" + " ●".join(fac))\n        else:\n            for l in fac:\n                lines.append(f"  {l}")\n    # v132 场景两区：🔎 可探索触发（POI/调查）+ ✨ 可交互场景（PROPS）\n    poi_lines, prop_lines = self._map_scene(cur_map, player, cur_sa)\n    if poi_lines:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("🔎 可探索触发：")\n        if _compact:\n            names = []\n            for l in poi_lines:\n                nm = l.split("(")[0].strip()\n                names.append(f"●{nm}")\n            lines.append("  " + " ".join(names))\n        else:\n            for l in poi_lines:\n                lines.append(f"  {l}")\n    if prop_lines:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("✨ 可交互场景：")\n        if _compact:\n            names = [f"●{i}. {l.split(\'(\')[0].strip()}" for i, l in enumerate(prop_lines, 1)]\n            lines.append("  " + " ".join(names))\n        else:\n            for l in prop_lines:\n                lines.append(f"  {l}")\n    # 本地 NPC\n    # v86 子区域：NPC 按当前子区域显示（无子区域则地图级）\n    cur_sa_obj = None\n    if cur_sa:\n        for _sa in sas:\n            if _sa["id"] == cur_sa:\n                cur_sa_obj = _sa\n                break\n    npc_ids = (cur_sa_obj.get("npcs") if cur_sa_obj else None) or cur_map.get("npcs", [])\n    if cur_map.get("inline_npcs"):\n        npc_ids = cur_map["inline_npcs"]\n    npcs = []\n    for nid in npc_ids:\n        if nid in _cat_quests.HIDDEN_NPCS:\n            npcs.append((nid, _cat_quests.HIDDEN_NPCS[nid]))\n        elif nid in _cat_quests.NPCS:\n            npcs.append((nid, _cat_quests.NPCS[nid]))\n    # v95.30 城镇 NPC 随机性：酱油 NPC 按 游走(roam)/概率(appear)/时段(period) 过滤显示\n    # （功能 NPC 恒显示；隐藏 NPC 走副本层逻辑不参与；无子区域(地图级)不做过滤）\n    npcs = [(nid, n) for nid, n in npcs\n            if nid in _cat_quests.HIDDEN_NPCS or not cur_sa or _wild.town_npc_visible(nid, n, cur_sa)]\n    if npcs:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("👥 这里的 NPC：")\n        if _compact:\n            # 城镇紧凑：●1. 名 ●2. 名（无头衔，鱼鱼模板）\n            _parts = [f"●{i}. {n[\'icon\']}{n[\'name\']}" for i, (_, n) in enumerate(npcs, 1)]\n            lines.append("  " + " ".join(_parts))\n        else:\n            for i, (_, n) in enumerate(npcs, 1):\n                lines.append(f"  {i:>2}. {n[\'icon\']}{n[\'name\']}({n[\'title\']})")\n            lines.append(f"  {self._tip(\'talk\')}")\n    # v127.5 限时NPC：在场野外旅人（偶遇进入限时状态，带 ⏳ 剩余分钟，全图可见）\n    # v127.5.1 不重复加 _tip(\'talk\')——对上城镇 NPC 区已有同分类提示（AST 防重铁律）\n    wild_lines = self._present_wild_hints(group_id, qq_id, cur) if group_id is not None and qq_id is not None else []\n    if wild_lines:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("🧭 游历的旅人：")\n        lines.extend(wild_lines)\n    # v66 此地玩家（含摆摊标记；v132 加编号，鱼鱼新排版）\n    # v134 #33：无其他玩家时不显示本段（连标题行一并省略，不留空行）\n    # v134.1 #46：排除自己——"只有玩家一个人时"不再显示『👤 此地的玩家：●1. 自己』\n    here_players = [p for p in db.get_group_players(group_id).values()\n                    if p.get("cur_map") == cur and str(p.get("qq_id")) != str(qq_id)]\n    if here_players:\n        stall_sellers = {str(s["seller"]) for s in db.market_list(group_id, cur)}\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("👤 此地的玩家：")\n        if _compact:\n            # 城镇紧凑：●1. 名 Lv.X ●2. 名 Lv.X（鱼鱼模板；摆摊标记保留——功能状态）\n            _parts = [f"●{i}. {p[\'name\']} Lv.{p[\'level\']}"\n                      + (" 🏪摆摊中" if str(p.get("qq_id")) in stall_sellers else "")\n                      for i, p in enumerate(here_players, 1)]\n            lines.append("  " + " ".join(_parts))\n        else:\n            for i, p in enumerate(here_players, 1):\n                stall_mark = " 🏪摆摊中" if str(p.get("qq_id")) in stall_sellers else ""\n                lines.append(f"  {i}. {p[\'name\']} Lv.{p[\'level\']}{stall_mark}")\n    # v86 子区域：怪物按当前子区域（无则回退地图级）\n    mons = (cur_sa_obj.get("monsters") if cur_sa_obj else None)\n    if mons is None:\n        mons = cur_map.get("monsters", [])\n    # 精英/Boss（子区域优先）——先取值供去重判断与字段展示\n    elite = (cur_sa_obj.get("elite") if cur_sa_obj else None) or cur_map.get("elite")\n    boss = (cur_sa_obj.get("boss") if cur_sa_obj else None) or cur_map.get("boss")\n    if mons:\n        if lines and lines[-1]:\n            lines.append("")\n        # v101.25 #289：标题等级改用怪物实际 min-max——此前用子区域 lv+2 推断，\n        # 与怪物真实等级差 2 级误导（round66 银风道口标 Lv.6-8 实际野狗 Lv.3）\n        _mlvs = [lv for _m, _n, _r, lv, _s, _d in mons if lv]\n        if _mlvs:\n            _lo, _hi = min(_mlvs), max(_mlvs)\n            lv_label = f"Lv.{_lo}" if _lo == _hi else f"Lv.{_lo}-{_hi}"\n        else:\n            base_lv = (cur_sa_obj.get("lv") if cur_sa_obj else None) or cur_map["lv"]\n            lv_label = f"Lv.{base_lv}"\n        lines.append(f"🐾 此地的怪物 ({lv_label})：")\n        for mid, name, role, lv, skills, drops in mons:\n            # v95r38 去重：池子条目与 elite/boss 字段重复时不重复显示（字段行会展示）\n            if role == "elite" and elite and elite[0] == mid:\n                continue\n            if role == "boss" and boss and boss[0] == mid:\n                continue\n            mark = "👑" if role == "boss" else ("⭐" if role == "elite" else "")\n            # v132 等级波动明示：普通怪 ±1（精英/Boss 不参与波动，不标注）\n            jitter = "±1" if role not in ("elite", "boss") else ""\n            lines.append(f"  {mark}{name} Lv.{lv}{jitter}")\n    if elite:\n        lines.append(f"  ⭐ 精英：{elite[1]}")\n    if boss:\n        lines.append(f"  👑 Boss：{boss[1]}")\n    if lines and lines[-1]:\n        lines.append("")\n    lines.append(self._tip("map"))\n    return lines\n',
    'content/world_cmds.py::_hurry_section': 'def _hurry_section(self, player: dict, cur_map: dict, cur_sa: str,\n                   group_id, qq_id, ftype: str) -> list:\n    """v128.1 类型过滤区（NPC/怪物/场景/设施）——赶路面板与移动落点过滤共用。\n\n    返回 lines 列表（未 join）；无内容给"没有XX"提示行，保证赶路语境一致。\n    """\n    lines = []\n    sas = cur_map.get("subareas") or []\n    cur_sa_obj = None\n    for _sa in sas:\n        if _sa["id"] == cur_sa:\n            cur_sa_obj = _sa\n            break\n    if ftype == "npc":\n        npc_ids = (cur_sa_obj.get("npcs") if cur_sa_obj else None) or cur_map.get("npcs", [])\n        if cur_map.get("inline_npcs"):\n            npc_ids = cur_map["inline_npcs"]\n        npcs = []\n        for nid in npc_ids:\n            if nid in _cat_quests.HIDDEN_NPCS:\n                npcs.append((nid, _cat_quests.HIDDEN_NPCS[nid]))\n            elif nid in _cat_quests.NPCS:\n                npcs.append((nid, _cat_quests.NPCS[nid]))\n        npcs = [(nid, n) for nid, n in npcs\n                if nid in _cat_quests.HIDDEN_NPCS or not cur_sa or _wild.town_npc_visible(nid, n, cur_sa)]\n        if npcs:\n            lines.append("👥 这里的 NPC：")\n            for i, (_, n) in enumerate(npcs, 1):\n                lines.append(f"  {i:>2}. {n[\'icon\']}{n[\'name\']}({n[\'title\']})")\n        else:\n            lines.append("👥 这里附近没有可交谈的 NPC ～")\n    elif ftype == "monster":\n        mons = (cur_sa_obj.get("monsters") if cur_sa_obj else None)\n        if mons is None:\n            mons = cur_map.get("monsters", [])\n        elite = (cur_sa_obj.get("elite") if cur_sa_obj else None) or cur_map.get("elite")\n        boss = (cur_sa_obj.get("boss") if cur_sa_obj else None) or cur_map.get("boss")\n        if mons:\n            _mlvs = [lv for _m, _n, _r, lv, _s, _d in mons if lv]\n            if _mlvs:\n                _lo, _hi = min(_mlvs), max(_mlvs)\n                lv_label = f"Lv.{_lo}" if _lo == _hi else f"Lv.{_lo}-{_hi}"\n            else:\n                base_lv = (cur_sa_obj.get("lv") if cur_sa_obj else None) or cur_map["lv"]\n                lv_label = f"Lv.{base_lv}"\n            lines.append(f"🐾 此地的怪物 ({lv_label})：")\n            for mid, name, role, lv, skills, drops in mons:\n                if role == "elite" and elite and elite[0] == mid:\n                    continue\n                if role == "boss" and boss and boss[0] == mid:\n                    continue\n                mark = "👑" if role == "boss" else ("⭐" if role == "elite" else "")\n                lines.append(f"  {mark}{name} Lv.{lv}")\n        if elite:\n            lines.append(f"  ⭐ 精英：{elite[1]}")\n        if boss:\n            lines.append(f"  👑 Boss：{boss[1]}")\n        if not mons and not elite and not boss:\n            lines.append("🐾 这里没什么怪物，比较安全～")\n    elif ftype == "scene":\n        scene = self._map_scene(cur_map, player, cur_sa)\n        if scene:\n            lines.append("✨ 场景：")\n            for l in scene:\n                lines.append(f"  {l}")\n        else:\n            lines.append("✨ 这里没什么特别的场景～")\n    elif ftype == "facility":\n        fac = self._map_facilities(cur_map, player, cur_sa)\n        if fac:\n            lines.append("🏪 此地设施：")\n            for l in fac:\n                lines.append(f"  {l}")\n        else:\n            lines.append("🏪 这里没有商店/设施～")\n    return lines\n',
    'content/world_cmds.py::_find_npc_in_map': 'def _find_npc_in_map(self, player, name_key):\n    """在当前地图找 NPC(子区域优先，回退地图级)，返回 (npc_id, npc_dict) 或 (None, None)。\n\n    v95.30 随机性：酱油 NPC 名字匹配但今天不可见（游走别处/概率未出/时段不符）\n    → 仍返回 (nid, npc)（由调用方给"不在"提示），并置 player[\'_npc_absent\'] 供提示。\n    """\n    cur_map = player["cur_map"]\n    m = _cat_space.MAP_BY_ID.get(cur_map, {})\n    sa_id = player.get("cur_subarea") or ""\n    player.pop("_npc_absent", None)\n    # 子区域 NPC 优先\n    for sa in (m.get("subareas") or []):\n        if sa["id"] == sa_id:\n            for nid in sa.get("npcs", []):\n                npc = _cat_quests.NPCS.get(nid)\n                if npc and (name_key in npc["name"] or name_key in nid):\n                    if not _wild.town_npc_visible(nid, npc, sa_id):\n                        player["_npc_absent"] = (nid, npc, sa_id)\n                    return nid, npc\n            break\n    # 地图级 NPC（含其他子区域）\n    for nid in m.get("npcs", []):\n        npc = _cat_quests.NPCS.get(nid)\n        if npc and (name_key in npc["name"] or name_key in nid):\n            if not _wild.town_npc_visible(nid, npc, sa_id):\n                player["_npc_absent"] = (nid, npc, sa_id)\n            return nid, npc\n    return None, None\n',
    'content/world_cmds.py::_find_wild_npc': 'def _find_wild_npc(self, player, name_key, group_id, qq_id):\n    """9.4：在当前地图找野外 NPC（含 roam 定位 + 出现条件判定）。\n    名字匹配但今天不在/条件不满足 → 返回 (None, None)，由调用方提示。"""\n    cur = player["cur_map"]\n    for nid, wnpc in _wild.ALL_WILD.items():\n        # v95.4：与 _find_npc_in_map 一致的子串匹配（『找 游商』→『游商·老马』）\n        if name_key not in (wnpc.get("name") or ""):\n            continue\n        if _wild.npc_map_id(nid, wnpc) != cur:\n            return None, None\n        if not _wild.wild_npc_findable(nid, wnpc, player, group_id, qq_id):\n            return None, None\n        wnpc = dict(wnpc)\n        wnpc.setdefault("title", "游历于野外的旅人")\n        return nid, wnpc\n    return None, None\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/wild.py::_wild_tables': '4ae971cf8344dde190af12049fb7f97448e137dc0d22c4cbc6a350d10c5c0bdf',
        'content/wild.py::_ALL_WILD': '03442ee3068495334a8798871bbeeada58031da678cf377ed417b7343e34b4b4',
        'content/wild.py::_wild_npc_expire': 'efd30d2bd57d22ae5efdf2b2f6526b654a3d24d527c77883531a6d41ff1cc743',
        'content/wild.py::_day_hash': '84c12f1574114da1163ed087cd9c18ce49e522be65ebf1837f2796453c72a677',
        'content/wild.py::npc_map_id': '9d7b7ad09dc9ecf52724c6956f15a0a747ce95f8ea19f7bf10ff261b21088e46',
        'content/wild.py::_quest_known': '1d3e8096e1d936b870150647284bef7f4153d4316df0cd7a124576d03a803753',
        'content/wild.py::unlock_met': '3a53328208e986c5399c2f7742b76f774927175cea1eeac6513479f58546a66a',
        'content/wild.py::base_conditions_met': '8850d6cb3ef1c5e6d393e2ec7edf970e1742f7e7fe9f95e4247574966df9e21b',
        'content/wild.py::_get_meta': '7db56cdbc3e89f1d63bc877193e9eee6ecbe97bcdd59c7c937abdf264a9119ea',
        'content/wild.py::_save_meta': 'a7f4aed3a9866f4f6163bfb266b9ba422ee0f608da3d24377a016335158eb244',
        'content/wild.py::met_wild': 'aecd3b97ab0d7994f2ff5bfa2bd397346f508899211c05d76272757bd823bfd6',
        'content/wild.py::_roll_random': '2d83db512dcf449d862287d0bd780fc12c1d8ce0594a65affd44db82069f2868',
        'content/wild.py::wild_npc_findable': 'cda310ff6969af57e55860f379cac836d6df55f851a8d59fe48f8a635a21657a',
        'content/wild.py::roll_wild_encounter': '94ab325957303c857d1ba792346129226865f2f101c942b9b4fee9cd15862285',
        'content/wild.py::nearby_hints': '0a00016eeda74c9eff9b829bb94952d1e31446ebbad79dcbf98e4cc8235b5fcd',
        'content/wild.py::town_npc_day_sa': '7a9cb42dcbadcc4a420e7349c548705f2c94952bc12d858a4d9960404e7c2300',
        'content/wild.py::town_npc_visible': '4ae244fb2f2f688e200b2590c0284f1eaf40f2f42959370e290ad28740c776d1',
        'content/wild.py::town_npc_dialogue': '61e86c11ad239e6a14939d9af0034736de1413a489e3eb94c84bacafd55e3fcb',
        'content/persistence/world.py::talk_state_key': '508250a32e7b298d42bac9831de793b58e6208f298059fc1671192d478318939',
        'content/persistence/world.py::talk_flags_key': '38011e8a01e017e7975a78ba17489f376b9765e44ce5da83efeadf9a1a4efb2c',
        'content/persistence/world.py::get_talk_state': 'd755d4e2a493d8324bfd1858917220534fc047e56206f1697471132f7f69bc12',
        'content/persistence/world.py::set_talk_state': '928ed09992a0ee2db0fdfd1f5765829f662587762a15c5074b5432220ee3361b',
        'content/persistence/world.py::clear_talk_state': '7e2f0e651b7a83c6a4934d7ebbe2329c0fac0a403a765d1fc57a13fd1589ceb4',
        'content/persistence/world.py::get_talk_flags': 'd31abb333a6098dcd337ae8fc04253b15df109e88dca667ef7fa5e36ef065f60',
        'content/persistence/world.py::set_talk_flag': '1e4037a9c2136c048e3fca3d51d8d447677572c1608adfb79bca35ff978ace60',
    },
    'live': {
        'content/wild.py::_wild_tables': '4ae971cf8344dde190af12049fb7f97448e137dc0d22c4cbc6a350d10c5c0bdf',
        'content/wild.py::_ALL_WILD': '07063cf4c0cfb74cb807c3e2a85b49eae6de9e95dbb6aef6ab0e5d974c907443',
        'content/wild.py::_wild_npc_expire': 'efd30d2bd57d22ae5efdf2b2f6526b654a3d24d527c77883531a6d41ff1cc743',
        'content/wild.py::_day_hash': '<deleted>',
        'content/wild.py::npc_map_id': 'cd85dec8d1597f1657ee9d26aa0ac71d7f48a5c34c96ff538f679944c87a52e5',
        'content/wild.py::_quest_known': '1d3e8096e1d936b870150647284bef7f4153d4316df0cd7a124576d03a803753',
        'content/wild.py::unlock_met': '3a53328208e986c5399c2f7742b76f774927175cea1eeac6513479f58546a66a',
        'content/wild.py::base_conditions_met': '8850d6cb3ef1c5e6d393e2ec7edf970e1742f7e7fe9f95e4247574966df9e21b',
        'content/wild.py::_get_meta': '7db56cdbc3e89f1d63bc877193e9eee6ecbe97bcdd59c7c937abdf264a9119ea',
        'content/wild.py::_save_meta': 'a7f4aed3a9866f4f6163bfb266b9ba422ee0f608da3d24377a016335158eb244',
        'content/wild.py::met_wild': 'aecd3b97ab0d7994f2ff5bfa2bd397346f508899211c05d76272757bd823bfd6',
        'content/wild.py::_roll_random': '3f8e096a575ce934c67868b10eab3c5d117f0e3468b10829eb1fc9cded685976',
        'content/wild.py::wild_npc_findable': 'cda310ff6969af57e55860f379cac836d6df55f851a8d59fe48f8a635a21657a',
        'content/wild.py::roll_wild_encounter': 'fe9cbeb9ad90d158faf7cabef44f0d6da7d04ad56d9fc8d8e01e1f2d551f6a0a',
        'content/wild.py::nearby_hints': '0a00016eeda74c9eff9b829bb94952d1e31446ebbad79dcbf98e4cc8235b5fcd',
        'content/wild.py::town_npc_day_sa': '5ca1c7507cef05346b24cb24419de54ad0aaf4e52a608ef475fcc2054cd31872',
        'content/wild.py::town_npc_visible': 'dccacd0b1decd90d1fd0c29abb1d26bd4de6cc59ed87117bdfddf856d6212f0b',
        'content/wild.py::town_npc_dialogue': 'e454c3846d3474908a3ae175f4fdcbd1b4fdaa7ce6f3a82dbf6707a2fa14e072',
        'content/persistence/world.py::talk_state_key': '508250a32e7b298d42bac9831de793b58e6208f298059fc1671192d478318939',
        'content/persistence/world.py::talk_flags_key': '38011e8a01e017e7975a78ba17489f376b9765e44ce5da83efeadf9a1a4efb2c',
        'content/persistence/world.py::get_talk_state': 'd755d4e2a493d8324bfd1858917220534fc047e56206f1697471132f7f69bc12',
        'content/persistence/world.py::set_talk_state': '928ed09992a0ee2db0fdfd1f5765829f662587762a15c5074b5432220ee3361b',
        'content/persistence/world.py::clear_talk_state': '7e2f0e651b7a83c6a4934d7ebbe2329c0fac0a403a765d1fc57a13fd1589ceb4',
        'content/persistence/world.py::get_talk_flags': 'd31abb333a6098dcd337ae8fc04253b15df109e88dca667ef7fa5e36ef065f60',
        'content/persistence/world.py::set_talk_flag': '1e4037a9c2136c048e3fca3d51d8d447677572c1608adfb79bca35ff978ace60',
    },
    'aux': {
        'all_wild_first5': 'w_old_trader|w_forest_girl|w_sage_ryder|w_lost_knight|w_gravekeeper',
        'all_wild_last5': 'h_librarian|h_night_trader|w_night_merchant|npc_gravedigger|npc_letter_bird',
        'all_wild_len': '63',
        'all_wild_order': '0c70aa40219d45372c111f3e21c5899345d732c1c33047fa489dbb001b7dd02e',
        'miss_guarantee': '7',
        'npcs_fp_hidden': '1b8fd4dd3cb0d25e6e90661f5dfbdea866f6db6292364225dfcf4863be599b58',
        'npcs_fp_town': '4db692ce296ebe64c0746fdd4c7995d620c9137afb637768a5a987377e2d94b4',
        'npcs_fp_wild': '8a99f63f81ffbdebc0f3b9850ee6cc3615c34d6699e102a9640c333c8e1f5d76',
        'npcs_len_hidden': '22',
        'npcs_len_town': '362',
        'npcs_len_wild': '47',
        'subareas_counts': '121:628',
        'subareas_order': '5c02b841ac614ce795cb18e479bc1c1a80951fd48473d79fa901afe849d03aed',
        'talk_flag_raw': '{"npc_mayor": ["pledged"]}',
        'talk_flags_key': 'talkflags_g1_1001',
        'talk_key': 'talk_g1_1001',
        'talk_state_raw': '{"npc": "npc_mayor", "node": "welcome"}',
        'timed_key': 'timed_events_1001',
        'timed_raw': '{"wild:w_old_trader": {"type": "wild_npc", "data": {"npc_id": "w_old_trader", "map": "oak_plain"}, "expire": 1767229200}}',
        'wildmeta_key': 'wildmeta_g1_1001',
        'wildmeta_raw': '{"met": ["w_old_trader"], "miss": {"h_owl": 3}, "last": {"h_owl": 1700000000}}',
    },
    'segments': {
        'E': [
            'content/wild.py::_wild_tables',
            'content/wild.py::_wild_npc_expire',
            'content/wild.py::_quest_known',
            'content/wild.py::unlock_met',
            'content/wild.py::base_conditions_met',
            'content/wild.py::_get_meta',
            'content/wild.py::_save_meta',
            'content/wild.py::met_wild',
            'content/wild.py::wild_npc_findable',
            'content/wild.py::nearby_hints',
            'content/persistence/world.py::talk_state_key',
            'content/persistence/world.py::talk_flags_key',
            'content/persistence/world.py::get_talk_state',
            'content/persistence/world.py::set_talk_state',
            'content/persistence/world.py::clear_talk_state',
            'content/persistence/world.py::get_talk_flags',
            'content/persistence/world.py::set_talk_flag',
        ],
        'C': [
            'content/wild.py::_ALL_WILD',
            'content/wild.py::npc_map_id',
            'content/wild.py::_roll_random',
            'content/wild.py::roll_wild_encounter',
            'content/wild.py::town_npc_day_sa',
            'content/wild.py::town_npc_visible',
            'content/wild.py::town_npc_dialogue',
        ],
        'A': [
            'content/wild.py::_day_hash',
        ],
    },
}
# <<< _u1i4_gen (auto) <<<


# ══════════════════════════════════════════════════════════════════════════════
# 1. 可拨伪时钟 / 伪随机 / 伪存储
# ══════════════════════════════════════════════════════════════════════════════
_CLOCK = {"date": datetime.date(2026, 1, 5), "ts": 1767225600,
          "period": "day", "season": "spring", "weather": "sunny"}
_STDLIB_DATETIME = datetime


class _FakeDate(datetime.date):
    """可拨 `today()`；真 `datetime.date` 子类 ⇒ `datetime.date | None` 标注照旧可求值。"""

    @classmethod
    def today(cls):
        return _CLOCK["date"]


class _DTMeta(type):
    """`isinstance(x, _DTClass)` 透传真 `datetime.datetime`（保住源码里的 isinstance 分支）。"""

    def __instancecheck__(cls, obj):
        return isinstance(obj, datetime.datetime)


class _DTClass(metaclass=_DTMeta):
    """`datetime.datetime` 的替身：`now()` 可拨，`isinstance` 兼容真 datetime。"""

    @staticmethod
    def now(tz=None):
        return datetime.datetime.fromtimestamp(_CLOCK["ts"])


class _DTModule:
    """伪 `datetime` 模块（`date` / `datetime` / `timedelta` 三名齐）。"""

    date = _FakeDate
    datetime = _DTClass
    timedelta = _STDLIB_DATETIME.timedelta


_DTM = _DTModule


def _current_period(now=None):
    return _CLOCK["period"]


def _current_season():
    return _CLOCK["season"]


def _today_weather(map_id=None):
    return _CLOCK["weather"]


class _FakeRandom:
    """可复现随机源：循环给定序列。"""

    def __init__(self, seq=(0.5,)):
        self.seq = list(seq) or [0.5]
        self.i = 0

    def random(self):
        v = self.seq[self.i % len(self.seq)]
        self.i += 1
        return v


class _FakeDB:
    """`db` 替身（只实现 wild.py / persistence 真用到的那几个口）。"""

    def __init__(self, quests=None, flags=None, items=None, stats=None, battle=None):
        self.d = {}
        self.quests = quests if quests is not None else {"completed_main": [], "side": {}}
        self.flags = dict(flags or {})
        self.items = dict(items or {})
        self.stats = dict(stats or {})
        self.battle = battle

    # 存档面
    def get_event_state(self, k):
        return self.d.get(k)

    def set_event_state(self, k, v):
        self.d[k] = v

    def delete_event_state(self, k):
        self.d.pop(k, None)

    def clear_talk_state(self, g, q):
        self.d.pop(f"talk_{g}_{q}", None)

    # 内容面
    def get_quests(self, g, q):
        return json.loads(json.dumps(self.quests))

    def get_talk_flags(self, g, q, nid):
        return list(self.flags.get(nid, []))

    def count_item(self, g, q, item):
        return int(self.items.get(item, 0))

    def get_stats(self, g, q):
        return dict(self.stats)

    def get_battle(self, g, q):
        return json.loads(json.dumps(self.battle)) if self.battle else None


class _TimedRecorder:
    """`set_timed` 的替身：记调用，不改存储。"""

    def __init__(self, events=None):
        self.calls = []
        self.events = list(events or [])

    def __call__(self, group_id, qq_id, key, type_key, data=None, duration_sec=None):
        self.calls.append((group_id, qq_id, key, type_key,
                           json.loads(json.dumps(data or {})), duration_sec))
        return 0

    def list_timed(self, group_id, qq_id, type_key=None, data_match=None):
        out = []
        for ev in self.events:
            if type_key is not None and ev.get("type") != type_key:
                continue
            if data_match and not all(ev.get("data", {}).get(k) == v
                                      for k, v in data_match.items()):
                continue
            out.append(ev)
        return out

    def get_timed(self, group_id, qq_id, key):
        for ev in self.events:
            if ev.get("key") == key:
                return ev
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 2. 旧实现（frozen 文本 exec 到独立命名空间）
# ══════════════════════════════════════════════════════════════════════════════
_WILD_SYMBOLS = ("_wild_tables", "_ALL_WILD", "_wild_npc_expire", "_day_hash", "npc_map_id",
                 "_quest_known", "unlock_met", "base_conditions_met", "_get_meta", "_save_meta",
                 "met_wild", "_roll_random", "wild_npc_findable", "roll_wild_encounter",
                 "nearby_hints", "town_npc_day_sa", "town_npc_visible", "town_npc_dialogue")

#: 冻结段文本 ↔ 运行时用的键（生成器按同一口径写 `_FROZEN_TEXT`）
_FKEY = {s: "content/wild.py::" + s for s in _WILD_SYMBOLS}
_WKEY = {s: "content/persistence/world.py::" + s for s in
         ("talk_state_key", "talk_flags_key", "get_talk_state", "set_talk_state",
          "clear_talk_state", "get_talk_flags", "set_talk_flag")}


def _build_wild_old_ns() -> dict:
    ns = {
        "datetime": _DTM, "json": json, "random": None, "db": None,
        "current_period": _current_period, "current_season": _current_season,
        "today_weather": _today_weather, "set_timed": None,
        "MISS_GUARANTEE": 7, "WILD_META_KEY": "wildmeta_{gid}_{qid}",
        "_WILD_NPCS_47": WILD_NPCS, "_HIDDEN_NPCS_22": HIDDEN_NPCS,
        "_INST_STAGE_IDS": W._INST_STAGE_IDS, "_ALL_WILD_CACHE": None,
    }
    for sym in _WILD_SYMBOLS:
        exec(compile(_FROZEN_TEXT[_FKEY[sym]], "<frozen:wild:%s>" % sym, "exec"), ns)  # noqa: S102
    return ns


OLD = _build_wild_old_ns()

#: 冻结侧世界侧函数（把 `_wild` 换成旧 shim 后 exec；`self` 由替身对象给）
_WC_SYMBOLS = ("_current_npcs", "_present_wild_hints", "_start_talk_list",
               "_map_blocks", "_hurry_section", "_find_npc_in_map", "_find_wild_npc")


def _build_wc_old_ns() -> dict:
    ns = dict(vars(WC))
    for sym in _WC_SYMBOLS:
        exec(compile(_FROZEN_TEXT["content/world_cmds.py::" + sym],
                     "<frozen:world_cmds:%s>" % sym, "exec"), ns)                    # noqa: S102
    return ns


class _Missing:
    """替身 `self` 未实现的口子 —— 一旦被调用即报错（防「门禁自己补了实现」）。"""

    def __init__(self, name):
        self._name = name

    def __call__(self, *a, **k):
        raise AssertionError("替身 self 未实现 %r（门禁不许自己补实现）" % self._name)

    def __getattr__(self, item):
        raise AssertionError("替身 self 未实现 %r.%s" % (self._name, item))


class _OldSelf:
    """旧侧 `self`：冻结段绑到自己身上，其余一律转活实现（同一批替身、同一份 db）。"""

    def __init__(self, live):
        object.__setattr__(self, "_live", live)

    def __getattr__(self, name):
        live = object.__getattribute__(self, "_live")
        try:
            return getattr(live, name)
        except AttributeError:
            return _Missing(name)


class _inject:
    """把旧 ns 与活模块 `content.wild` 的同名注入面换成**同一批**替身（退出原地还原）。"""

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: OLD.get(k, _MISSING) for k in self.kw}
        for k, v in self.kw.items():
            OLD[k] = v
        self.live = {k: getattr(W, k, _MISSING) for k in self.kw}
        for k, v in self.kw.items():
            setattr(W, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is _MISSING:
                OLD.pop(k, None)
            else:
                OLD[k] = v
        for k, v in self.live.items():
            if v is _MISSING:
                if hasattr(W, k):
                    delattr(W, k)
            else:
                setattr(W, k, v)
        return False


@contextlib.contextmanager
def _bind(*, db=None, rng=None, set_timed=None, unlocked=None, cond=None,
          date=None, ts=None, period="day", season="spring", weather="sunny"):
    """绑一批替身 + 拨伪时钟（退出全部还原）。"""
    saved = dict(_CLOCK)
    if date is not None:
        _CLOCK["date"] = date
    if ts is not None:
        _CLOCK["ts"] = ts
    _CLOCK["period"] = period
    _CLOCK["season"] = season
    _CLOCK["weather"] = weather
    kw = {"db": db if db is not None else _FakeDB(),
          "random": rng if rng is not None else _FakeRandom(),
          "set_timed": set_timed if set_timed is not None else _TimedRecorder(),
          "datetime": _DTM, "current_period": _current_period,
          "current_season": _current_season, "today_weather": _today_weather}
    if unlocked is not None:
        kw["unlock_met"] = unlocked
    if cond is not None:
        kw["base_conditions_met"] = cond
    with _inject(**kw):
        yield
    _CLOCK.clear()
    _CLOCK.update(saved)


def _old(sym):
    return OLD[sym]


# ══════════════════════════════════════════════════════════════════════════════
# 3. 数据面（431 表 / 场所 / 代表日）
# ══════════════════════════════════════════════════════════════════════════════
ALL = {**NPCS, **WILD_NPCS, **HIDDEN_NPCS}
ALL_ITEMS = list(ALL.items())

_OWN_PLACES = []
for _nid, _npc in ALL_ITEMS:
    if _npc.get("roam"):
        _OWN_PLACES.extend((_nid, _npc, _p) for _p in _npc["roam"])
    else:
        _OWN_PLACES.append((_nid, _npc, _npc.get("map")))

DAYS62 = [datetime.date(2025, 12, 1) + datetime.timedelta(days=i) for i in range(62)]
DAYS_N = [datetime.date(2025, 12, 1) + datetime.timedelta(days=i) for i in range(366)]

#: 网格 B 的 185 场所 = 101 个 `map` 取值（含 3 个 `null` 折成的 `None` 桶）∪ 70 个 `roam` 值
#: ∪ 121 个地图 id。实测 = 185（与 `FROZEN_GATE.md` §5.2 的 185 一致）。
PLACES = sorted({None} | {_n for _n in (n.get("map") for n in ALL.values()) if _n is not None}
                | {_p for _n in ALL.values() for _p in (_n.get("roam") or [])}
                | set(_MAP_BY_ID), key=lambda x: (x is None, x or ""))

_DAYS7 = [datetime.date(2025, 12, 1),            # 周一
          datetime.date(2025, 12, 7),            # 周日
          datetime.date(2025, 12, 29),           # 跨年周（周一）
          datetime.date(2026, 1, 1),             # 元旦
          datetime.date(2026, 1, 4),             # 周日
          datetime.date(2026, 1, 5),             # 周一
          datetime.date(2026, 2, 1)]             # 次月

#: 读盘白名单（判据 [9]；全程零写盘）
READONLY_FILES = ("content/wild.py", "content/persistence/world.py",
                  "content/timed_events.py", "content/world_cmds.py",
                  "content/data/npcs.json")


def _pkg_file(relpath):
    return os.path.join(PKG_ROOT, *relpath.split("/"))


def _file_sha(relpath):
    with open(_pkg_file(relpath), encoding="utf-8") as fh:
        return sha256(fh.read())


# ══════════════════════════════════════════════════════════════════════════════
# 4. 猴补（原地还原，不写盘）
# ══════════════════════════════════════════════════════════════════════════════
class _Patch:
    """猴补上下文（进入记原值，退出原地还原；**不写盘**）。"""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value
        self.had = hasattr(obj, name)
        self.old = getattr(obj, name, None)

    def __enter__(self):
        setattr(self.obj, self.name, self.value)
        return self

    def __exit__(self, *exc):
        if self.had:
            setattr(self.obj, self.name, self.old)
        else:
            if hasattr(self.obj, self.name):
                delattr(self.obj, self.name)
        return False


def _live_obj(relpath, symbol):
    if relpath == "content/wild.py":
        return getattr(W, symbol, None)
    if relpath == "content/persistence/world.py":
        return getattr(PW, symbol, None)
    return None


def _modname_of(relpath):
    return "content." + relpath.split("/", 1)[1][:-3].replace("/", ".")


# ══════════════════════════════════════════════════════════════════════════════
# [1] 双 sha256 + E/C/A 分类
# ══════════════════════════════════════════════════════════════════════════════
def test_frozen_pins():
    print("【1. 双 sha256：25 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 25（wild 18 + persistence/world 7）", len(keys) == 25, len(keys))
    check("门禁内键序 == 冻结文本键序（前 25 段）",
          keys == [k for k in _FROZEN_TEXT][:25], keys[:3])
    bad = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("冻结文本 sha256 全等 _PIN['frozen']（25 段）", not bad, bad[:4])

    live_bad = []
    for k in keys:
        relpath, sym = k.split("::")
        obj = _live_obj(relpath, sym)
        got = "<deleted>" if obj is None else sha256(inspect.getsource(obj))
        if got != _PIN["live"][k]:
            live_bad.append((k, _PIN["live"][k][:12], got[:12]))
    check("活实现 inspect.getsource sha256 全等 _PIN['live']（25 段）", not live_bad, live_bad[:4])

    seg = _PIN["segments"]
    chkE = [k for k in seg["E"] if _PIN["frozen"][k] != _PIN["live"][k]]
    check("E 栏「预期不变」段 frozen == live（%d 段）" % len(seg["E"]), not chkE, chkE[:3])
    if _PIN["phase"] == "landed":
        chkC = [k for k in seg["C"] if _PIN["frozen"][k] == _PIN["live"][k]]
        check("C 栏「预期会变」段 frozen != live（%d 段）" % len(seg["C"]), not chkC, chkC[:3])
        gone = [k for k in seg["A"] if _live_obj(*k.split("::")) is not None]
        check("A 栏 %s 已删除（活模块里没有这个名字）" % "·".join(seg["A"]), not gone, gone)
        check("_day_hash 行为由 day_slot 顶替：引擎符号已进入活模块",
              hasattr(W, "day_slot") and hasattr(W, "day_hit") and hasattr(W, "guarded_roll")
              and hasattr(W, "cooldown_ok") and hasattr(W, "merge_tables"))
    else:
        print("  ⓘ phase=%r：C 栏不等式断言按 `FROZEN_GATE` §8 的「红基线」档暂不启用"
              % (_PIN["phase"],))

    # 被 25 段覆盖不到、但属存档面/行为面的模块级字面量
    check("WILD_META_KEY 字面量未变（存档键格式）",
          W.WILD_META_KEY == "wildmeta_{gid}_{qid}", W.WILD_META_KEY)
    check("MISS_GUARANTEE == 7（保底门槛）", W.MISS_GUARANTEE == 7, W.MISS_GUARANTEE)
    check("冻结侧 WILD_META_KEY / MISS_GUARANTEE 与活侧一致",
          OLD["WILD_META_KEY"] == W.WILD_META_KEY and OLD["MISS_GUARANTEE"] == W.MISS_GUARANTEE)


# ══════════════════════════════════════════════════════════════════════════════
# [6] aux 数据面 / 存档面指纹
# ══════════════════════════════════════════════════════════════════════════════
def _aux_fingerprints() -> dict:
    """§3 的 ②③④⑤⑥⑦⑨：实跑取产物（写独立私有库，绝不碰生产库）。"""
    out = {}
    db.init_db()
    # ②③ 会话键 / flag 键 + 落盘 JSON 文本（字节级）
    out["talk_key"] = PW.talk_state_key("g1", "1001")
    out["talk_flags_key"] = PW.talk_flags_key("g1", "1001")
    PW.set_talk_state("g1", "1001", "npc_mayor", "welcome")
    out["talk_state_raw"] = db.get_event_state(out["talk_key"]) or ""
    PW.set_talk_flag("g1", "1001", "npc_mayor", "pledged")
    out["talk_flag_raw"] = db.get_event_state(out["talk_flags_key"]) or ""
    PW.clear_talk_state("g1", "1001")
    db.delete_event_state(out["talk_flags_key"])
    # ④ wildmeta 键 + JSON 文本
    out["wildmeta_key"] = W.WILD_META_KEY.format(gid="g1", qid="1001")
    kv = _FakeDB()
    with _inject(db=kv):
        W._save_meta("g1", "1001", {"met": ["w_old_trader"], "miss": {"h_owl": 3},
                                    "last": {"h_owl": 1700000000}})
    out["wildmeta_raw"] = kv.d[out["wildmeta_key"]]
    out["miss_guarantee"] = str(W.MISS_GUARANTEE)
    # ⑤ timed_events 键 + JSON 文本（expire = 固定时钟 + 3600）
    out["timed_key"] = TE._PLAYER_KEY.format(qq_id="1001")
    with _Patch(TE._timers, "clock", lambda: 1767225600):
        TE.set_timed("g1", "1001", "wild:w_old_trader", "wild_npc",
                     data={"npc_id": "w_old_trader", "map": "oak_plain"}, duration_sec=3600)
    out["timed_raw"] = db.get_event_state(out["timed_key"]) or ""
    TE.remove_timed("g1", "1001", "wild:w_old_trader")
    db.delete_event_state(out["timed_key"])
    # ⑥ ALL_WILD 63 键序
    keys = list(W.ALL_WILD)
    out["all_wild_len"] = str(len(keys))
    out["all_wild_first5"] = "|".join(keys[:5])
    out["all_wild_last5"] = "|".join(keys[-5:])
    out["all_wild_order"] = sha256("|".join(keys))
    # ⑦ 子区域序（地图序 × 子区域声明序）
    rows = ["%s:%s" % (mid, sa["id"]) for mid, m in _MAP_BY_ID.items()
            for sa in (m.get("subareas") or [])]
    out["subareas_counts"] = "%d:%d" % (len(_MAP_BY_ID), len(rows))
    out["subareas_order"] = sha256("|".join(rows))
    # ⑨ 三张 NPC 表指纹
    for label, table in (("town", NPCS), ("wild", WILD_NPCS), ("hidden", HIDDEN_NPCS)):
        blob = "|".join("%s:%s:%s:%s" % (nid, r.get("name", ""), r.get("map", ""),
                                         "".join(sorted(r.get("funcs") or [])))
                        for nid, r in table.items())
        out["npcs_fp_" + label] = sha256(blob)
        out["npcs_len_" + label] = str(len(table))
    return out


def test_aux():
    print("【6. aux 数据面 / 存档面指纹（逐字节）】")
    got = _aux_fingerprints()
    if not _PIN["aux"]:
        check("_PIN['aux'] 已生成", False, "先用 `_u1i4_presence_gen.py --emit-aux` 生成")
        return
    bad = [k for k in _PIN["aux"] if got.get(k) != _PIN["aux"][k]]
    check("aux 指纹 %d 条全等 _PIN['aux']" % len(_PIN["aux"]), not bad,
          [(k, str(_PIN["aux"][k])[:24], str(got.get(k))[:24]) for k in bad][:3])
    check("会话键格式 == talk_g1_1001", got["talk_key"] == "talk_g1_1001", got["talk_key"])
    check("flag 键格式 == talkflags_g1_1001",
          got["talk_flags_key"] == "talkflags_g1_1001", got["talk_flags_key"])
    check("会话 JSON 文本逐字节 == '{\"npc\": \"npc_mayor\", \"node\": \"welcome\"}'",
          got["talk_state_raw"] == '{"npc": "npc_mayor", "node": "welcome"}',
          got["talk_state_raw"])
    check("wildmeta 键格式 == wildmeta_g1_1001",
          got["wildmeta_key"] == "wildmeta_g1_1001", got["wildmeta_key"])
    check("timed 键格式 == timed_events_1001",
          got["timed_key"] == "timed_events_1001", got["timed_key"])
    check("timed JSON 含整数 expire", '"expire": 1767229200' in got["timed_raw"], got["timed_raw"])
    check("ALL_WILD 63 条（wild 47 ∪ hidden 16）", got["all_wild_len"] == "63", got["all_wild_len"])
    check("子区域序 121 图 / 628 行", got["subareas_counts"] == "121:628", got["subareas_counts"])
    check("三表条数 362 / 47 / 22",
          (got["npcs_len_town"], got["npcs_len_wild"], got["npcs_len_hidden"]) == ("362", "47", "22"),
          (got["npcs_len_town"], got["npcs_len_wild"], got["npcs_len_hidden"]))


# ══════════════════════════════════════════════════════════════════════════════
# [2] 网格 A：定位（逐格）
# ══════════════════════════════════════════════════════════════════════════════
FULL = "--full" in sys.argv


def test_grid_a_locate():
    days = DAYS_N if FULL else DAYS62
    print("【2. 网格 A（定位，逐格）】%d NPC 场所对 × %d 天 = %d 格"
          % (len(_OWN_PLACES), len(days), len(_OWN_PLACES) * len(days)))
    check("NPC 场所对数 == 489（431 NPC 的 map 或 roam 桶）", len(_OWN_PLACES) == 489,
          len(_OWN_PLACES))
    check("天数 == %d（2025-12-01..2026-01-31 = 62）" % len(days),
          len(days) == (366 if FULL else 62), len(days))
    old_map, old_sa = _old("npc_map_id"), _old("town_npc_day_sa")
    new_map, new_sa = W.npc_map_id, W.town_npc_day_sa
    cells = 0
    mism = []
    with _bind(date=days[0]):
        for nid, npc, place in _OWN_PLACES:
            for d in days:
                cells += 1
                a, b = old_map(nid, npc, d), new_map(nid, npc, d)
                if a != b:
                    mism.append(("npc_map_id", nid, place, d.isoformat(), a, b))
                c, e = old_sa(nid, npc, place, d), new_sa(nid, npc, place, d)
                if c != e:
                    mism.append(("town_npc_day_sa", nid, place, d.isoformat(), c, e))
    expect = len(_OWN_PLACES) * len(days)
    check("网格 A 计数校验：%d 格 == 预期 %d" % (cells, expect), cells == expect, cells)
    check("网格 A：npc_map_id / town_npc_day_sa 旧 == 新 逐格（%d 格 × 2 判据）" % cells,
          not mism, mism[:3])
    check("网格 A：roam NPC 的当天定位**真的动**（不是恒等函数）",
          len({new_map(nid, npc, d) for nid, npc, _p in _OWN_PLACES if npc.get("roam")
               for d in days}) > 1)


def test_dialogue_grid():
    print("【2′. 台词网格：431 NPC × 62 天 = 26,722】")
    old_d, new_d = _old("town_npc_dialogue"), W.town_npc_dialogue
    cells = 0
    mism = []
    with _bind(date=DAYS62[0]):
        for nid, npc in ALL_ITEMS:
            for d in DAYS62:
                cells += 1
                a, b = old_d(nid, npc, "BASE", d), new_d(nid, npc, "BASE", d)
                if a != b:
                    mism.append((nid, d.isoformat(), a, b))
    check("台词网格计数校验：%d 格 == 431 × 62" % cells, cells == 431 * 62, cells)
    check("台词网格：town_npc_dialogue 旧 == 新 逐格", not mism, mism[:3])
    check("台词网格：有 lines 的 NPC 真的换台词（不是恒等函数）",
          len({new_d(nid, npc, "BASE", d) for nid, npc in ALL_ITEMS
               if (npc.get("lines") or []) and not npc.get("funcs") for d in DAYS62}) > 1)


# ══════════════════════════════════════════════════════════════════════════════
# [3] 网格 B：在场（满格）
# ══════════════════════════════════════════════════════════════════════════════
def test_grid_b_present():
    days = DAYS62 if FULL else _DAYS7
    nows = ([d for d in days]
            + [datetime.datetime(d.year, d.month, d.day, 12, 0) for d in days]
            + [datetime.datetime(d.year, d.month, d.day, 22, 0) for d in days])
    nd, np_, nnow = len(ALL_ITEMS), len(PLACES), len(nows)
    print("【3. 网格 B（在场）】431 × %d 场所 × %d 日 × 3 态 = %d 格%s"
          % (np_, len(days), nd * np_ * nnow, "（--full 慢档）" if FULL else "（默认档）"))
    check("场所并集 P == 185（101 map 值含 3 个 null ∪ 70 roam 值 ∪ 121 图）",
          np_ == 185, np_)
    check("代表日 == %d / now 三态 == %d" % (len(days), nnow),
          len(days) == (62 if FULL else 7) and nnow == 3 * len(days),
          (len(days), nnow))
    old_vis, new_vis = _old("town_npc_visible"), W.town_npc_visible
    cells = 0
    mism = []
    with _bind(date=days[0]):
        for nid, npc in ALL_ITEMS:
            for now in nows:
                for place in PLACES:
                    cells += 1
                    a = old_vis(nid, npc, place, now)
                    b = new_vis(nid, npc, place, now)
                    if a is not b:
                        mism.append((nid, place, str(now), a, b))
    expect = nd * np_ * nnow
    check("网格 B 计数校验：%d 格 == 431 × 185 × %d × 3%s"
          % (cells, len(days), " = 14,830,710" if FULL else " = 1,674,435"),
          cells == expect == (14830710 if FULL else 1674435), cells)
    check("网格 B：town_npc_visible 旧 == 新 逐格", not mism, mism[:3])


# ══════════════════════════════════════════════════════════════════════════════
# [3′] 条件矩阵：base_conditions_met / unlock_met
# ══════════════════════════════════════════════════════════════════════════════
_WILD_ITEMS = list(WILD_NPCS.items()) + list(HIDDEN_NPCS.items())


def _vals(field):
    out = set()
    for _nid, r in ALL.items():
        v = (r.get("condition") or {}).get(field)
        if isinstance(v, list):
            out.update(v)
        elif v is not None:
            out.add(v)
    return sorted(out, key=str)


_TIME_VALS = _vals("time")
_WEATHER_VALS = _vals("weather")
_SEASON_VALS = _vals("season")
_DOW_VALS = _vals("day_of_week")
_MINLV_VALS = _vals("min_level")

_FULL_QUESTS = {"completed_main": ["q11_3"], "side": {"q_side_1": {}, "q1_1": {}},
                "main_status": "active", "main_quest": "q1_1"}
_FULL_BATTLE = {"state": {"cleared": True, "inst_id": "inst_abyss_throne"}}
_FLAG_NPC = sorted(ALL)[0] if ALL else "npc_x"

_STORE_STATES = [
    ("empty", {}),
    ("quests", dict(quests=_FULL_QUESTS)),
    ("flags", dict(flags={_FLAG_NPC: ["heard_owl_song"]})),
    ("items", dict(items={"mat_iron": 3})),
    ("stats", dict(stats={"fishing": 12})),
    ("battle", dict(battle=_FULL_BATTLE)),
]


def _store(spec):
    return _FakeDB(quests=spec.get("quests"), flags=spec.get("flags"),
                   items=spec.get("items"), stats=spec.get("stats"),
                   battle=spec.get("battle"))


def _condition_cases():
    cases = [("none", {})]
    for v in _TIME_VALS:
        cases.append(("time=%s" % v, {"time": [v]}))
    for v in _WEATHER_VALS:
        cases.append(("weather=%s" % v, {"weather": v}))
    for v in _SEASON_VALS:
        cases.append(("season=%s" % v, {"season": [v]}))
    for v in _DOW_VALS:
        cases.append(("dow=%s" % v, {"day_of_week": [v]}))
    for v in _MINLV_VALS:
        cases.append(("min_level=%s" % v, {"min_level": v}))
    # 数据里 0 条的 5 个字段 —— 必须合成才覆盖得到
    cases += [
        ("max_level=5", {"max_level": 5}),
        ("quest_done", {"quest_done": ["q1_1"]}),
        ("quest_active", {"quest_active": ["q1_1"]}),
        ("flag", {"flag": "heard_owl_song"}),
        ("item", {"item": "mat_iron"}),
    ]
    # 两两 / 三三组合（真数据里最多同时出现 3 个字段）
    t0 = _TIME_VALS[0] if _TIME_VALS else "day"
    w0 = _WEATHER_VALS[0] if _WEATHER_VALS else "sunny"
    s0 = _SEASON_VALS[0] if _SEASON_VALS else "spring"
    cases += [
        ("time+weather", {"time": [t0], "weather": w0}),
        ("time+season", {"time": [t0], "season": [s0]}),
        ("weather+season", {"weather": w0, "season": [s0]}),
        ("time+weather+season", {"time": [t0], "weather": w0, "season": [s0]}),
        ("quest_done+flag+item", {"quest_done": ["q1_1"], "flag": "heard_owl_song",
                                  "item": "mat_iron"}),
        ("max_level+min_level", {"max_level": 5, "min_level": 1}),
        ("dow+time+item", {"day_of_week": [_DOW_VALS[0]] if _DOW_VALS else [0],
                           "time": [t0], "item": "mat_iron"}),
    ]
    return cases


_COND_CASES = _condition_cases()


def _env_matrix():
    envs = [("base", dict(period="day", season="spring", weather="sunny",
                          date=datetime.date(2025, 12, 1), level=1))]
    for p in _TIME_VALS:
        envs.append(("period=%s" % p, dict(period=p, date=datetime.date(2025, 12, 1), level=1)))
    for w in _WEATHER_VALS:
        envs.append(("weather=%s" % w, dict(weather=w, date=datetime.date(2025, 12, 1), level=1)))
    for s in _SEASON_VALS:
        envs.append(("season=%s" % s, dict(season=s, date=datetime.date(2025, 12, 1), level=1)))
    for v in _MINLV_VALS + [5, 30, 60]:
        envs.append(("level=%s" % v, dict(level=v, date=datetime.date(2025, 12, 1))))
    for wd in (0, 6):
        envs.append(("weekday=%d" % wd,
                     dict(date=datetime.date(2025, 12, 1) + datetime.timedelta(days=wd))))
    envs.append(("night+winter+rain+lv60",
                 dict(period="night", season="winter", weather="rain", level=60,
                      date=datetime.date(2025, 12, 7))))
    envs.append(("morning+autumn+fog+lv30",
                 dict(period="morning", season="autumn", weather="fog", level=30,
                      date=datetime.date(2025, 12, 6))))
    return envs


_ENVS = _env_matrix()

_UNLOCK_CASES = ["flag:heard_owl_song", "item:mat_iron", "quest:q1_1", "quest_done:q1_1",
                 "quest_done:inst_abyss_throne", "stats:fishing:10", "weird_prefix:x",
                 "stats:missing_key:1", None]


def test_conditions_matrix():
    print("【3′. 条件矩阵】%d 条件 × %d 环境 × %d 存储态 × 69 野外/隐藏 NPC"
          % (len(_COND_CASES), len(_ENVS), len(_STORE_STATES)))
    o_base, n_base = _old("base_conditions_met"), W.base_conditions_met
    o_unlock, n_unlock = _old("unlock_met"), W.unlock_met
    cells = 0
    mism = []
    for label, spec in _STORE_STATES:
        store = _store(spec)
        for env_label, env in _ENVS:
            level = env.get("level", 1)
            clock = {k: v for k, v in env.items() if k != "level"}
            with _bind(db=store, **clock):
                for cname, cond in _COND_CASES:
                    for nid, npc in _WILD_ITEMS:
                        probe = dict(npc)
                        probe["condition"] = cond
                        probe["unlock"] = None
                        cells += 1
                        a = o_base(nid, probe, {"level": level}, "g1", "q1")
                        b = n_base(nid, probe, {"level": level}, "g1", "q1")
                        if a is not b:
                            mism.append((label, env_label, cname, nid, a, b))
    expect_base = len(_STORE_STATES) * len(_ENVS) * len(_COND_CASES) * len(_WILD_ITEMS)
    check("base_conditions_met 计数校验：%d 格 == 预期 %d" % (cells, expect_base),
          cells == expect_base, cells)
    check("base_conditions_met 旧 == 新 逐格（%d 格）" % cells, not mism, mism[:3])

    ucells = 0
    umism = []
    for label, spec in _STORE_STATES:
        store = _store(spec)
        with _bind(db=store, date=datetime.date(2025, 12, 1)):
            cases = [(("real:%s" % nid), r.get("unlock")) for nid, r in _WILD_ITEMS]
            cases += [("synth:%s" % u, u) for u in _UNLOCK_CASES]
            for cname, unlock in cases:
                probe = {"unlock": unlock}
                ucells += 1
                a = o_unlock("w_probe", probe, "g1", "q1")
                b = n_unlock("w_probe", probe, "g1", "q1")
                if a is not b:
                    umism.append((label, cname, a, b))
    check("unlock_met 计数校验：%d 格 == %d" % (ucells, len(_STORE_STATES) * (len(_WILD_ITEMS) + len(_UNLOCK_CASES))),
          ucells == len(_STORE_STATES) * (len(_WILD_ITEMS) + len(_UNLOCK_CASES)), ucells)
    check("unlock_met 旧 == 新 逐格（%d 格，含 5 前缀 + 未知前缀 + null）" % ucells,
          not umism, umism[:3])

    # 条件矩阵必须真覆盖到 10 个字段（防「矩阵退化成恒真」）
    seen = {f for _c, cond in _COND_CASES for f in cond}
    check("条件矩阵覆盖 10 个字段", seen == {"time", "season", "weather", "min_level",
                                            "max_level", "quest_done", "quest_active",
                                            "flag", "item", "day_of_week"}, sorted(seen))
    check("真数据只用到 5 个字段（其余 5 个靠合成用例）",
          {k for _n, r in ALL.items() for k in (r.get("condition") or {})}
          == {"time", "season", "weather", "min_level", "day_of_week"},
          sorted({k for _n, r in ALL.items() for k in (r.get("condition") or {})}))


# ══════════════════════════════════════════════════════════════════════════════
# [4] 网格 C：偶遇（返回值 + wildmeta 终态 + 限时挂载）
# ══════════════════════════════════════════════════════════════════════════════
def _encounter_pair(nid, npc, today, miss, cd, cyc_hit, seed=0.99):
    """跑一次 `roll_wild_encounter` 的旧/新两侧（强制 unlock/condition 通过 → 只考随机/保底/冷却/硬周期）。"""
    ts = 1767225600
    meta_key = W.WILD_META_KEY.format(gid="g1", qid="1001")
    map_id = OLD["npc_map_id"](nid, npc, today)
    player = {"level": 99, "cur_map": map_id, "cur_subarea": ""}

    def _side(fn):
        store = _FakeDB()
        store.d[meta_key] = json.dumps({"met": [], "miss": {nid: miss},
                                        "last": {nid: ts - cd}}, ensure_ascii=False)
        rec = _TimedRecorder()
        rng = _FakeRandom((seed,))
        # 只放行目标 NPC（`unlock_met` 按 id 过滤）→ 矩阵考的是**该 NPC** 的
        # cycle / 冷却 / chance / 保底，而不是「同图里谁先被扫到」。
        with _bind(db=store, rng=rng, set_timed=rec, date=today, ts=ts,
                   unlocked=lambda n2, r2, g, q: n2 == nid,
                   cond=lambda *a, **k: True):
            ret = fn("g1", "1001", player, map_id)
        return (None if ret is None else ret[0]), store.d, rec.calls

    return _side(OLD["roll_wild_encounter"]), _side(W.roll_wild_encounter)


def test_grid_c_encounter():
    items = list(WILD_NPCS.items())
    print("【4. 网格 C（偶遇）】47 野外 × cycle 2 态 × miss 4 × 冷却 4 = 1,504")
    cells = 0
    mism = []
    hits = 0
    hits_cycle_miss = 0
    for nid, npc in items:
        cyc = npc.get("cycle")
        for cyc_hit in (True, False):
            day = datetime.date(2025, 12, 1)
            if cyc:
                for i in range(cyc * 2 + 1):
                    d = datetime.date(2025, 12, 1) + datetime.timedelta(days=i)
                    if (d.toordinal() % cyc == 0) is cyc_hit:
                        day = d
                        break
            for miss in (0, 6, 7, 8):
                for cd in (0, 1799, 1800, 1801):
                    cells += 1
                    a, b = _encounter_pair(nid, npc, day, miss, cd, cyc_hit)
                    if a != b:
                        mism.append((nid, cyc_hit, miss, cd, a[0], b[0]))
                    if b[0]:
                        hits += 1
                        if b[0] == nid and cyc and not cyc_hit:
                            hits_cycle_miss += 1
    check("网格 C 计数校验：%d 格 == 47 × 2 × 4 × 4 = 1,504" % cells,
          cells == 1504, cells)
    check("网格 C：roll_wild_encounter 返回值 + wildmeta 终态 + 限时挂载 旧 == 新（逐键）",
          not mism, mism[:3])
    check("网格 C：真的有命中（矩阵没退化成全 None）", hits > 0, hits)
    check("网格 C：cycle 不命中那一列，**该 NPC 自己** 0 次命中（硬周期不掷骰、不写 miss）",
          hits_cycle_miss == 0, hits_cycle_miss)

    # 补列：`chance` + 保底只出现在 11 条 **hidden** 条目上（真数据里 47 条野外 NPC 一条都没有
    # `chance`）—— 它们同样经 `ALL_WILD` 被 `roll_wild_encounter` 扫到，必须逐格比。
    chance_items = [(nid, r) for nid, r in W.ALL_WILD.items() if r.get("chance") is not None]
    ccells = 0
    cmism = []
    cguar = 0
    for nid, npc in chance_items:
        for miss in (0, 6, 7, 8):
            for cd in (0, 1799, 1800, 1801):
                ccells += 1
                a, b = _encounter_pair(nid, npc, datetime.date(2025, 12, 1), miss, cd, True)
                if a != b:
                    cmism.append((nid, miss, cd, a[0], b[0]))
                if miss >= 7 and b[0]:
                    cguar += 1
    check("网格 C 补列（chance/保底）计数校验：%d 格 == 11 × 4 × 4 = 176" % ccells,
          ccells == 176, ccells)
    check("网格 C 补列：chance/保底 逐格旧 == 新", not cmism, cmism[:3])
    check("网格 C 补列：miss ∈ {7,8} 那两列**真的走保底**（命中数 > 0）", cguar > 0, cguar)


# ══════════════════════════════════════════════════════════════════════════════
# [5] 网格 D：三份列表实现（行序 + 行内容 + 编号）
# ══════════════════════════════════════════════════════════════════════════════
class _WildShim:
    """旧侧 `world_cmds` 眼里的 `_wild` 模块（冻结派生 + 冻结 ALL_WILD 表）。"""

    def __init__(self, ns):
        self.ALL_WILD = ns["_ALL_WILD"]()
        for k in _WILD_SYMBOLS:
            setattr(self, k, ns[k])


_WILD_SHIM = _WildShim(OLD)


def _wc_old_self(live_self, events=None):
    dns = _build_wc_old_ns()
    timed = _TimedRecorder(events)
    dns["_timed"] = timed
    dns["_wild"] = _WILD_SHIM
    old_self = _OldSelf(live_self)
    for sym in _WC_SYMBOLS:
        old_self.__dict__[sym] = types.MethodType(dns[sym], old_self)
    return old_self, timed


def _map_cases():
    cases = []
    for mid, m in _MAP_BY_ID.items():
        for sa in (m.get("subareas") or []):
            cases.append((mid, m, sa["id"]))
        cases.append((mid, m, ""))
    return cases


def _mk_events(n, map_id, ids):
    out = []
    for i in range(n):
        nid = ids[i % len(ids)]
        out.append({"key": "wild:%s" % nid, "type": "wild_npc",
                    "data": {"npc_id": nid, "map": map_id},
                    "expire": 1767225600 + 3600, "remain": 60 * (i + 1)})
    return out


def _run(fn, *a, **k):
    try:
        return ("ok", fn(*a, **k))
    except Exception as exc:                                            # noqa: BLE001
        return ("exc", type(exc).__name__, str(exc)[:160])


def test_grid_d_lists():
    live_self = Main(None)
    old_self, timed = _wc_old_self(live_self)
    cases = _map_cases()
    overlay_ids = list(W.ALL_WILD)
    print("【5. 网格 D（列表）】%d 图 + 628 子区域 = %d 用例 × 0..3 限时事件 = %d 用例 × 3 份实现"
          % (len(_MAP_BY_ID), len(cases), len(cases) * 4))
    check("网格 D 用例基座 == 749（121 图 + 628 子区域）", len(cases) == 749, len(cases))

    cells = 0
    mism = []
    nonempty = 0
    # `self._tip(...)` 是引擎侧 `pick_tip` 的**随机抽一条**（与本批无关）→ 固定成「取第一条」，
    # 让两侧的**全部行**（含提示行）都可逐行比，而不是把提示行排除在外。
    with _Patch(random, "choice", lambda seq: list(seq)[0]), _Patch(WC, "_timed", timed), \
            _bind(date=datetime.date(2026, 1, 5)):
        for mid, m, cur_sa in cases:
            for nev in (0, 1, 2, 3):
                timed.events = _mk_events(nev, mid, overlay_ids)
                player = {"qq_id": "1001", "group_id": "g1", "name": "测试",
                          "level": 1, "cur_map": mid, "cur_subarea": cur_sa}
                live_self._player = lambda g, q, p=player: p
                a = _run(old_self._map_blocks, player, m, cur_sa, "g1", "1001")
                b = _run(live_self._map_blocks, player, m, cur_sa, "g1", "1001")
                cells += 1
                if a != b:
                    mism.append(("map_blocks", mid, cur_sa, nev, a, b))
                if a[0] == "ok" and len(a[1]) > 3:
                    nonempty += 1
                a = _run(old_self._hurry_section, player, m, cur_sa, "g1", "1001", "npc")
                b = _run(live_self._hurry_section, player, m, cur_sa, "g1", "1001", "npc")
                cells += 1
                if a != b:
                    mism.append(("hurry_npc", mid, cur_sa, nev, a, b))
                a = _run(old_self._current_npcs, player)
                b = _run(live_self._current_npcs, player)
                cells += 1
                if a != b:
                    mism.append(("current_npcs", mid, cur_sa, nev, a, b))
    expect = len(cases) * 4 * 3
    check("网格 D 计数校验：%d 格 == 749 × 4 × 3 = 2,996 × 3" % cells,
          cells == expect == 8988, cells)
    check("网格 D：行序 + 行内容 旧 == 新 逐行（三份实现）", not mism, mism[:3])
    check("网格 D：真的有实内容行（矩阵没退化成空列表）", nonempty > 200, nonempty)

    # ── 合成 3 例（冷路径：地图级 npcs / inline_npcs / 子区域与 inline 同时非空）──
    town_ids = [nid for nid, r in list(NPCS.items())[:40]]
    hidden_ids = [nid for nid in HIDDEN_NPCS]
    base_map = _MAP_BY_ID[sorted(_MAP_BY_ID)[0]]
    base_sa = (base_map.get("subareas") or [{}])[0]
    synth_sa = {"id": "u1i4_sa", "name": "合成子区域", "npcs": town_ids[:3] + hidden_ids[:1],
                "monsters": [], "elite": None, "boss": None}
    synth_map = dict(base_map, id="u1i4_map", name="合成图", npcs=town_ids[3:6],
                     inline_npcs=[], subareas=[synth_sa], monsters=[],
                     elite=None, boss=None, lv=1, type="野外")
    synth_inline = dict(synth_map, inline_npcs=town_ids[6:9])
    synth = dict(_MAP_BY_ID, u1i4_map=synth_map)
    timed.events = []
    live_self._player = lambda g, q: {"qq_id": "1001", "group_id": "g1", "name": "测试",
                                      "level": 1, "cur_map": "u1i4_map",
                                      "cur_subarea": "u1i4_sa"}
    with _Patch(random, "choice", lambda seq: list(seq)[0]), \
            _Patch(WC._cat_space, "MAP_BY_ID", synth), _Patch(WC, "_timed", timed), \
            _bind(date=datetime.date(2026, 1, 5)):
        for label, m in (("地图级 npcs", synth_map), ("inline_npcs", synth_inline)):
            a = _run(old_self._map_blocks, live_self._player("g", "q"), m, "u1i4_sa", "g1", "1001")
            b = _run(live_self._map_blocks, live_self._player("g", "q"), m, "u1i4_sa", "g1", "1001")
            check("网格 D 合成用例（%s）：旧 == 新 逐行" % label, a == b, (a, b))
        a = _run(old_self._hurry_section, live_self._player("g", "q"), synth_inline,
                 "u1i4_sa", "g1", "1001", "npc")
        b = _run(live_self._hurry_section, live_self._player("g", "q"), synth_inline,
                 "u1i4_sa", "g1", "1001", "npc")
        check("网格 D 合成用例（inline_npcs × 赶路面板）：旧 == 新 逐行", a == b, (a, b))
        a = _run(old_self._current_npcs, live_self._player("g", "q"))
        b = _run(live_self._current_npcs, live_self._player("g", "q"))
        check("网格 D 合成用例（子区域 npcs × 对话列表）：旧 == 新 逐行", a == b, (a, b))


def _numbers(lines):
    out = []
    for ln in lines:
        head = ln.split(".", 1)[0].strip()
        if head.isdigit():
            out.append((int(head), ln.split(".", 1)[1].strip()))
    return out


def test_numbering():
    live_self = Main(None)
    old_self, timed = _wc_old_self(live_self)
    base_map = _MAP_BY_ID[sorted(_MAP_BY_ID)[0]]
    town_ids = list(NPCS)
    overlay_ids = list(W.ALL_WILD)[:3]
    print("【5′. 编号网格：静态 N ∈ {0,1,2,5,36} × 限时 M ∈ {0,1,3} = 15】")
    cells = 0
    mism = []
    for N in (0, 1, 2, 5, 36):
        ids = town_ids[:N]
        sa = {"id": "u1i4_sa2", "name": "合成子区域2", "npcs": ids, "monsters": [],
              "elite": None, "boss": None}
        m = dict(base_map, id="u1i4_map2", name="合成图2", npcs=[], inline_npcs=[],
                 subareas=[sa], monsters=[], elite=None, boss=None, lv=1, type="野外")
        for M in (0, 1, 3):
            timed.events = _mk_events(M, "u1i4_map2", overlay_ids)
            player = {"qq_id": "1001", "group_id": "g1", "name": "测试", "level": 1,
                      "cur_map": "u1i4_map2", "cur_subarea": "u1i4_sa2"}
            live_self._player = lambda g, q, p=player: p
            with _Patch(random, "choice", lambda seq: list(seq)[0]), \
                    _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_map2=m)), \
                    _Patch(WC, "_timed", timed), \
                    _Patch(W, "town_npc_visible", lambda *a, **k: True), \
                    _Patch(_WILD_SHIM, "town_npc_visible", lambda *a, **k: True), \
                    _bind(date=datetime.date(2026, 1, 5)):
                a = _run(old_self._start_talk_list, "g1", "1001")
                b = _run(live_self._start_talk_list, "g1", "1001")
            cells += 1
            if a != b:
                mism.append((N, M, a, b))
            if a[0] == "ok" and N and M:
                nums = [n for n, _t in _numbers(a[1])]
                if nums != list(range(1, N + M + 1)):
                    mism.append(("numbering", N, M, nums))
    check("编号网格计数校验：%d 格 == 15" % cells, cells == 15, cells)
    check("编号网格：静态 1..N、限时 N+1.. 旧 == 新 逐行", not mism, mism[:3])

    # 顺序敏感：静态清单倒序 → 编号-内容对应整体改变（证明门禁真在看序）
    sa_f = {"id": "u1i4_sa3", "name": "S", "npcs": list(NPCS)[:5], "monsters": [],
            "elite": None, "boss": None}
    sa_r = dict(sa_f, npcs=list(reversed(list(NPCS)[:5])))
    m_f = dict(base_map, id="u1i4_map3", npcs=[], inline_npcs=[], subareas=[sa_f],
               monsters=[], elite=None, boss=None, lv=1, type="野外")
    m_r = dict(m_f, subareas=[sa_r])
    timed.events = _mk_events(2, "u1i4_map3", overlay_ids)
    player = {"qq_id": "1001", "group_id": "g1", "name": "测试", "level": 1,
              "cur_map": "u1i4_map3", "cur_subarea": "u1i4_sa3"}
    live_self._player = lambda g, q, p=player: p
    with _Patch(random, "choice", lambda seq: list(seq)[0]), \
            _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_map3=m_f)), \
            _Patch(WC, "_timed", timed), \
            _Patch(W, "town_npc_visible", lambda *a, **k: True), \
            _Patch(_WILD_SHIM, "town_npc_visible", lambda *a, **k: True):
        fwd = _run(live_self._start_talk_list, "g1", "1001")
    with _Patch(random, "choice", lambda seq: list(seq)[0]), \
            _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_map3=m_r)), \
            _Patch(WC, "_timed", timed), \
            _Patch(W, "town_npc_visible", lambda *a, **k: True), \
            _Patch(_WILD_SHIM, "town_npc_visible", lambda *a, **k: True):
        rev = _run(live_self._start_talk_list, "g1", "1001")
    fwd_n = [t for _n, t in _numbers(fwd[1])]
    rev_n = [t for _n, t in _numbers(rev[1])]
    check("编号顺序断言：静态清单倒序 → 编号-内容对应整体改变（门禁在看序）",
          fwd_n != rev_n and fwd_n[:5] == list(reversed(rev_n[:5])), (fwd_n[:3], rev_n[:3]))
    check("编号顺序断言：限时项续号在静态之后（N+1 起）",
          [n for n, _t in _numbers(fwd[1])] == list(range(1, 8)), _numbers(fwd[1]))


# ══════════════════════════════════════════════════════════════════════════════
# [7] 口径分歧 12 条（`U1-I4_DESIGN.md` §3.7）
# ══════════════════════════════════════════════════════════════════════════════
def _synth_subarea(npcs, sid="u1i4_sa", **kw):
    sa = {"id": sid, "name": "合成子区域", "npcs": list(npcs), "monsters": [],
          "elite": None, "boss": None}
    sa.update(kw)
    return sa


def _synth_map(mid, subareas=(), npcs=(), inline=(), **kw):
    base = _MAP_BY_ID[sorted(_MAP_BY_ID)[0]]
    m = dict(base, id=mid, name="合成图", subareas=list(subareas), npcs=list(npcs),
             inline_npcs=list(inline), monsters=[], elite=None, boss=None, lv=1, type="野外")
    m.update(kw)
    return m


def test_divergences():
    print("【7. 口径分歧 12 条（故意不统一，后人不得顺手统一）】")
    live_self = Main(None)
    old_self, timed = _wc_old_self(live_self)
    hidden_ids = [nid for nid, r in HIDDEN_NPCS.items() if r.get("title") and r.get("icon")]
    town_ids = list(NPCS)

    # ① 三份列表成员集合不同：含 HIDDEN 的两处 + 不含的一处
    sa = _synth_subarea([town_ids[0], town_ids[1], hidden_ids[0]], sid="u1i4_d1")
    m = _synth_map("u1i4_d1_map", [sa], )
    player = {"qq_id": "1001", "group_id": "g1", "name": "语", "level": 1,
              "cur_map": "u1i4_d1_map", "cur_subarea": "u1i4_d1"}
    live_self._player = lambda g, q, p=player: p
    timed.events = []
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, **{"u1i4_d1_map": m})), \
            _Patch(WC, "_timed", timed), \
            _Patch(W, "town_npc_visible", lambda *a, **k: False), \
            _Patch(_WILD_SHIM, "town_npc_visible", lambda *a, **k: False):
        blocks = "\n".join(_run(live_self._map_blocks, player, m, "u1i4_d1", "g1", "1001")[1])
        hurry = "\n".join(_run(live_self._hurry_section, player, m, "u1i4_d1", "g1", "1001", "npc")[1])
        cur = _run(live_self._current_npcs, player)[1]
    hn = HIDDEN_NPCS[hidden_ids[0]]["name"]
    check("分歧①：`_map_blocks` 含 HIDDEN_NPCS 且对其**豁免**可见性过滤",
          hn in blocks, blocks[:120])
    check("分歧①：`_hurry_section` 同口径（含 HIDDEN 并豁免）", hn in hurry, hurry[:120])
    check("分歧①：`_current_npcs` 只含 NPCS → 成员集合**严格小于**前者",
          all(n["name"] != hn for n in cur), [n.get("name") for n in cur])

    # ② 地图级（无子区域）不做可见性过滤 → 55 条 appear 的 NPC 全部出现
    appear_ids = [nid for nid, r in ALL.items()
                  if r.get("appear") is not None and not r.get("funcs")]
    appear_names = {r["name"] for nid, r in ALL.items() if nid in set(appear_ids)}
    sa2 = _synth_subarea(appear_ids, sid="u1i4_d2")
    m2 = _synth_map("u1i4_d2_map", [sa2], npcs=appear_ids)
    p2 = dict(player, cur_map="u1i4_d2_map", cur_subarea="")
    live_self._player = lambda g, q, p=p2: p
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, **{"u1i4_d2_map": m2})), \
            _Patch(WC, "_timed", timed):
        top = "\n".join(_run(live_self._map_blocks, p2, m2, "", "g1", "1001")[1])
        p2s = dict(p2, cur_subarea="u1i4_d2")
        sub = "\n".join(_run(live_self._map_blocks, p2s, m2, "u1i4_d2", "g1", "1001")[1])
    check("分歧②：`cur_sa == \"\"`（地图级）时 55 条 appear NPC **全部出现**（不过滤）",
          all(nm in top for nm in appear_names),
          [nm for nm in appear_names if nm not in top][:3])
    check("分歧②′：同一批 NPC 在**子区域级**被 appear 过滤掉（证明上面那条不是空转）",
          sum(1 for nm in appear_names if nm not in sub) > 0,
          (len(appear_names), len(sub)))

    # ③ 『找』与列表的不可见处理不同
    nid3, npc3 = next((n, r) for n, r in NPCS.items() if r.get("appear") is not None
                      and not r.get("funcs"))
    sa3 = _synth_subarea([nid3], sid="u1i4_d3")
    m3 = _synth_map("u1i4_d3_map", [sa3])
    p3 = {"qq_id": "1001", "group_id": "g1", "name": "语", "level": 1,
          "cur_map": "u1i4_d3_map", "cur_subarea": "u1i4_d3"}
    live_self._player = lambda g, q, p=p3: p
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, **{"u1i4_d3_map": m3})), \
            _Patch(WC, "_timed", timed), \
            _Patch(W, "town_npc_visible", lambda *a, **k: False), \
            _Patch(_WILD_SHIM, "town_npc_visible", lambda *a, **k: False):
        hit = _run(live_self._find_npc_in_map, p3, npc3["name"])
        cur3 = _run(live_self._current_npcs, p3)[1]
    check("分歧③：`_find_npc_in_map` 命中但不可见 → **仍返回** (nid, npc)",
          hit[0] == "ok" and hit[1][0] == nid3, hit)
    check("分歧③：并置 `player['_npc_absent']` 供提示", p3.get("_npc_absent", (None,))[0] == nid3,
          str(p3.get("_npc_absent"))[:60])
    check("分歧③′：`_current_npcs` 里**没有**该 NPC（列表是「此刻在场」）",
          all(n.get("name") != npc3["name"] for n in cur3), [n.get("name") for n in cur3])

    # ④ 野外『找』的首个同名早退
    name4 = "同名·甲"
    first = {"name": name4, "map": "u1i4_other_map", "condition": {}, "unlock": None}
    second = {"name": name4, "map": "u1i4_here_map", "condition": {}, "unlock": None}
    fake_table = {"u1i4_a": first, "u1i4_b": second}
    shim = _WildShim(OLD)
    shim.ALL_WILD = fake_table

    class _Shim:
        ALL_WILD = fake_table
        npc_map_id = staticmethod(lambda nid, npc: npc.get("map"))
        wild_npc_findable = staticmethod(lambda *a, **k: True)

    p4 = {"qq_id": "1001", "group_id": "g1", "cur_map": "u1i4_here_map", "cur_subarea": ""}
    with _Patch(WC, "_wild", _Shim):
        r4 = _run(live_self._find_wild_npc, p4, name4, "g1", "1001")
    check("分歧④：两个同名 NPC（第一个在别图）→ `_find_wild_npc` 首个**早退** (None, None)",
          r4[0] == "ok" and r4[1] == (None, None), r4)

    # ⑤ 确定性：城镇在场两次同结果；野外偶遇用注入 RNG 可复现
    nid5, npc5 = next((n, r) for n, r in NPCS.items() if r.get("roam"))
    with _bind(date=datetime.date(2026, 1, 5)):
        v1 = W.town_npc_visible(nid5, npc5, npc5["roam"][0], datetime.date(2026, 1, 5))
        v2 = W.town_npc_visible(nid5, npc5, npc5["roam"][0], datetime.date(2026, 1, 5))
    check("分歧⑤：`town_npc_visible` 是确定性的（两次调用同结果）", v1 is v2, (v1, v2))
    c1 = _encounter_pair(nid5, npc5, datetime.date(2026, 1, 5), 0, 0, True)[1]
    c2 = _encounter_pair(nid5, npc5, datetime.date(2026, 1, 5), 0, 0, True)[1]
    check("分歧⑤′：`roll_wild_encounter` 注入 RNG → 可复现", c1 == c2, (c1, c2))

    # ⑥ remain → 分钟：ceil 且下限 1
    vals = (0, 1, 59, 60, 61, 119, 120, 3599, 3600, 3601, -5)
    inline = [max(1, -(-int(x) // 60)) for x in vals]
    check("分歧⑥：`minutes_left` == 内联 `max(1, ceil(x/60))`（11 值）",
          [PRES.minutes_left(x) for x in vals] == inline,
          [(x, PRES.minutes_left(x), y) for x, y in zip(vals, inline)
           if PRES.minutes_left(x) != y][:3])
    check("分歧⑥′：`minutes_left(0) == 1`（剩 0 秒也显示「剩 1 分」）",
          PRES.minutes_left(0) == 1 and PRES.minutes_left(60) == 1 and PRES.minutes_left(61) == 2)

    # ⑦ 限时项只按 data['map'] 匹配：同图任意子区域都出现
    evn = list(W.ALL_WILD)[0]
    sa7 = _synth_subarea([town_ids[0]], sid="u1i4_d7")
    sa7b = _synth_subarea([town_ids[1]], sid="u1i4_d7b")
    m7 = _synth_map("u1i4_d7_map", [sa7, sa7b])
    live_self._player = lambda g, q: dict(player, cur_map="u1i4_d7_map", cur_subarea="u1i4_d7")
    timed.events = _mk_events(1, "u1i4_d7_map", [evn])
    with _Patch(WC, "_timed", timed):
        h7a = _run(live_self._present_wild_hints, "g1", "1001", "u1i4_d7_map")[1]
        h7b = _run(live_self._present_wild_hints, "g1", "1001", "u1i4_d7_map")[1]
    check("分歧⑦：限时项只按 `data['map']` 匹配 → 同图**任意**子区域都出现（与子区域无关）",
          h7a == h7b and len(h7a) == 1 and "⏳" in h7a[0], (h7a, h7b))

    # ⑧ funcs 铁律只给城镇
    exempt = {"funcs": ["x"], "appear": 0.0, "period": ["night"], "roam": ["a", "b"]}
    plain = {"funcs": [], "appear": 0.0, "period": ["night"], "roam": ["a", "b"]}
    with _bind(date=datetime.date(2026, 1, 5), period="day"):
        check("分歧⑧：`funcs` 非空 → 恒可见（appear=0 / period=night 也豁免）",
              W.town_npc_visible("u1i4_f", exempt, "zz", datetime.date(2026, 1, 5)) is True)
        check("分歧⑧′：`funcs` 空的同字段 NPC → 不可见（豁免不是全局的）",
              W.town_npc_visible("u1i4_p", plain, "zz", datetime.date(2026, 1, 5)) is False)
        a = _old("_roll_random")("w1", {"chance": 0.5, "funcs": ["x"]}, "g1", "q1")
        b = _old("_roll_random")("w1", {"chance": 0.5, "funcs": []}, "g1", "q1")
    check("分歧⑧″：野外侧不看 `funcs`（`_roll_random` 对 funcs 两态同结果）", a is b, (a, b))

    # ⑨ chance 假值 = 必定出现
    with _bind(db=_FakeDB(), rng=_FakeRandom((0.999,))):
        check("分歧⑨：`chance=None` → **必定出现**（不是永不出现）",
              _old("_roll_random")("w1", {"chance": None}, "g1", "q1") is True
              and W._roll_random("w1", {"chance": None}, "g1", "q1") is True)
        check("分歧⑨′：`chance=0` 同口径（假值即放行）",
              W._roll_random("w1", {"chance": 0}, "g1", "q1") is True)

    # ⑩ unlock 未知前缀 = 解锁
    with _bind(db=_FakeDB()):
        check("分歧⑩：`unlock='weird_prefix:x'` → `unlock_met` 返回 True（故意不 fail-closed）",
              W.unlock_met("w1", {"unlock": "weird_prefix:x"}, "g1", "q1") is True)

    # ⑪ miss 命中不清零（清点在 roll_wild_encounter 的命中副作用里）
    store = _FakeDB()
    with _bind(db=store, rng=_FakeRandom((0.9,))):
        for _ in range(3):
            W._roll_random("w1", {"chance": 0.5}, "g1", "q1")
    meta_key = W.WILD_META_KEY.format(gid="g1", qid="q1")
    miss_after = json.loads(store.d[meta_key])["miss"]["w1"]
    with _bind(db=store, rng=_FakeRandom((0.1,))):
        hit = W._roll_random("w1", {"chance": 0.5}, "g1", "q1")
    miss_hit = json.loads(store.d[meta_key])["miss"]["w1"]
    check("分歧⑪：`_roll_random` **命中时不清** miss（命中后计数原样保留）",
          hit is True and miss_hit == miss_after == 3, (hit, miss_after, miss_hit))

    # ⑫ 三表 id 零交集 + import 守卫不抛
    check("分歧⑫：`WILD_NPCS ∩ HIDDEN_NPCS == ∅`（模块级守卫仍生效，import 未抛）",
          not (set(WILD_NPCS) & set(HIDDEN_NPCS)) and len(W.ALL_WILD) == 63,
          len(W.ALL_WILD))


# ══════════════════════════════════════════════════════════════════════════════
# [8] 有牙反证 + 多故障
# ══════════════════════════════════════════════════════════════════════════════
_ORIG_VISIBLE = W.town_npc_visible
_ORIG_DAY_HASH = OLD["_day_hash"]


def _break_appear():
    """破坏 `appear` 判据：活 `town_npc_visible` 里 appear 恒 True。"""

    def _vis(npc_id, npc, sa_id, now=None):
        probe = dict(npc)
        probe["appear"] = None
        return _ORIG_VISIBLE(npc_id, probe, sa_id, now)

    return _Patch(W, "town_npc_visible", _vis)


def _break_salt():
    """破坏当天定位派生：本批前 = 内容侧 `_day_hash`；本批后 = 引擎 `day_slot`（盐多一个字符）。"""
    if hasattr(W, "day_slot"):
        return _Patch(W, "day_slot",
                      lambda seed, size, *, salt="": PRES.day_slot(seed, size, salt=salt + "X"))
    return _Patch(W, "_day_hash",
                  lambda seed, salt="": _ORIG_DAY_HASH(seed, salt + "X"))


def _break_guarantee():
    """破坏保底：`MISS_GUARANTEE` 拉到天文数字 ⇒ 永不保底。"""
    return _Patch(W, "MISS_GUARANTEE", 10 ** 9)


def _probe_appear():
    """在场探针：55 条 appear NPC × 62 天 × {自身场所, None} → 旧 ↔ 新 出现差异即 True。"""
    new_vis = getattr(W, "town_npc_visible")
    items = [(nid, r) for nid, r in ALL_ITEMS
             if r.get("appear") is not None and not r.get("funcs")]
    with _bind(date=DAYS62[0]):
        for nid, npc in items:
            for d in DAYS62:
                for place in (npc.get("map"), None):
                    if OLD["town_npc_visible"](nid, npc, place, d) is not new_vis(nid, npc, place, d):
                        return True
    return False


def _probe_locate():
    """定位探针：47 条 roam NPC × 62 天 → `npc_map_id` / `town_npc_day_sa` 出现差异即 True。"""
    with _bind(date=DAYS62[0]):
        for nid, npc, place in _OWN_PLACES:
            if not npc.get("roam"):
                continue
            new_map = getattr(W, "npc_map_id")
            new_sa = getattr(W, "town_npc_day_sa")
            for d in DAYS62:
                if OLD["npc_map_id"](nid, npc, d) != new_map(nid, npc, d):
                    return True
                if OLD["town_npc_day_sa"](nid, npc, place, d) != new_sa(nid, npc, place, d):
                    return True
    return False


def _probe_guarantee():
    """保底探针：带 `chance` 的 ALL_WILD 条目（真数据 11 条，全在 hidden）× miss ∈ {7,8}、冷却已过
    → 返回值 / miss 终态出现差异即 True。"""
    for nid, npc in W.ALL_WILD.items():
        if npc.get("chance") is None:
            continue
        cyc = npc.get("cycle")
        day = datetime.date(2025, 12, 1)
        if cyc:
            for i in range(cyc * 2 + 1):
                d = datetime.date(2025, 12, 1) + datetime.timedelta(days=i)
                if d.toordinal() % cyc == 0:
                    day = d
                    break
        for miss in (7, 8):
            a, b = _encounter_pair(nid, npc, day, miss, 9999, True)
            if a != b:
                return True
    return False


_BREAKS = {
    "appear_恒真": (_break_appear, _probe_appear),
    "day_slot_换盐": (_break_salt, _probe_locate),
    "保底_恒不保底": (_break_guarantee, _probe_guarantee),
}


def test_teeth():
    print("【8. 有牙反证：破坏 3 处 → 对应探针必须变红（原地还原）】")
    before = {f: _file_sha(f) for f in READONLY_FILES}
    for name, (_b, probe) in _BREAKS.items():
        check("未破坏时 `%s` 探针为 False（真实现成立）" % name, probe() is False)
    for name, (breaker, probe) in _BREAKS.items():
        with breaker():
            red = probe()
        print("     破坏 `%s`：预期变红 / 实测 %s" % (name, "变红 ✅" if red else "仍绿 ❌"))
        check("破坏 `%s` → 探针必须变红（预期变红 / 实测变红）" % name, red is True)
        check("还原 `%s` 后探针回绿" % name, probe() is False)

    print("  ── 多故障场景（只坏一处证明不了「各管一段」）──")
    with _break_appear(), _break_salt():
        r1, r2 = _probe_appear(), _probe_locate()
    check("两处同坏（appear + day_slot）：两条断言各管一段，都变红", r1 and r2, (r1, r2))
    with _break_salt(), _break_guarantee():
        r1, r2 = _probe_locate(), _probe_guarantee()
    check("两处同坏（day_slot + 保底）：两条断言各管一段，都变红", r1 and r2, (r1, r2))
    with _break_appear(), _break_guarantee():
        r1, r2, r3 = _probe_appear(), _probe_guarantee(), _probe_locate()
    check("两处同坏时**第三处**仍绿（证明不是「一个大探针管全部」）",
          r1 is True and r2 is True and r3 is False, (r1, r2, r3))
    after = {f: _file_sha(f) for f in READONLY_FILES}
    check("反证全程零写盘：源文件 sha256 前后一致", before == after,
          [f for f in READONLY_FILES if before[f] != after[f]])


# ══════════════════════════════════════════════════════════════════════════════
# [8′] 顺序断言（§8.2）① `roll_wild_encounter` 门序 ② 限时续号 ⑥ 过期至多一次
# ══════════════════════════════════════════════════════════════════════════════
def test_order_assertions():
    print("【8′. 顺序断言：门序 / 限时续号 / 过期至多一次】")
    # ① roll_wild_encounter 门序：cycle → unlock → condition → 冷却 → chance
    nid, npc = next((n, r) for n, r in WILD_NPCS.items()
                    if (r.get("condition") or {}).get("time"))
    ok_period = list(npc["condition"]["time"])[0]
    bad_period = "day" if ok_period != "day" else "night"
    cyc = npc.get("cycle")
    day = datetime.date(2025, 12, 1)
    if cyc:
        for i in range(cyc * 2 + 1):
            d = datetime.date(2025, 12, 1) + datetime.timedelta(days=i)
            if d.toordinal() % cyc == 0:
                day = d
                break
    ts = 1767225600
    map_id = OLD["npc_map_id"](nid, npc, day)
    meta_key = W.WILD_META_KEY.format(gid="g1", qid="1001")

    def _run_gate(period):
        store = _FakeDB()
        store.d[meta_key] = json.dumps({"met": [], "miss": {nid: 7}, "last": {}},
                                       ensure_ascii=False)
        rec = _TimedRecorder()
        with _bind(db=store, rng=_FakeRandom((0.999,)), set_timed=rec, date=day, ts=ts,
                   period=period, unlocked=lambda n2, r2, g, q: n2 == nid):
            ret = W.roll_wild_encounter("g1", "1001",
                                        {"level": 99, "cur_map": map_id, "cur_subarea": ""},
                                        map_id)
        return ret, json.loads(store.d[meta_key]), rec.calls

    ret_bad, meta_bad, rec_bad = _run_gate(bad_period)
    ret_ok, meta_ok, rec_ok = _run_gate(ok_period)
    check("顺序①：condition 不满足 → 返回 None、**miss 保持 7**、不挂限时（先判后写）",
          ret_bad is None and meta_bad.get("miss", {}).get(nid) == 7 and not rec_bad,
          (ret_bad, meta_bad.get("miss"), rec_bad))
    check("顺序①′：condition 满足 → 保底命中（返回该 NPC + 清 miss + 挂限时）",
          ret_ok is not None and ret_ok[0] == nid
          and nid not in meta_ok.get("miss", {}) and len(rec_ok) == 1,
          (None if ret_ok is None else ret_ok[0], meta_ok.get("miss"), rec_ok))
    check("顺序①″：门序敏感 —— 同一输入下「condition 先于 chance」才成立",
          ret_bad is None and ret_ok is not None)

    # ⑥ 过期：三条读路径都清、on_expire **至多一次**、回调里再读同 key 得 None
    db.init_db()
    rec = []

    def _cb(group_id, qq_id, data):
        rec.append((group_id, qq_id, dict(data or {}),
                    TE.get_timed(group_id, qq_id, "k1")))

    TE.register_timed("u1i4_probe", duration_sec=10, on_expire=_cb)
    cleaned = {}
    for path in ("get", "list", "refresh"):
        TE.remove_timed("g1", "u1i4expire", "k1")
        with _Patch(TE._timers, "clock", lambda: 1000):
            TE.set_timed("g1", "u1i4expire", "k1", "u1i4_probe", data={"path": path},
                         duration_sec=10)
        with _Patch(TE._timers, "clock", lambda: 1010):
            if path == "get":
                cleaned[path] = TE.get_timed("g1", "u1i4expire", "k1")
            elif path == "list":
                cleaned[path] = TE.list_timed("g1", "u1i4expire")
            else:
                cleaned[path] = TE.refresh_timed("g1", "u1i4expire")
    check("顺序⑥：get / list / refresh 三条读路径都清（结果分别为 None / [] / 1）",
          cleaned == {"get": None, "list": [], "refresh": 1}, cleaned)
    check("顺序⑥′：`on_expire` 每次过期**恰好一次**（三次挂载 → 3 次回调）",
          len(rec) == 3, len(rec))
    check("顺序⑥″：回调里**再读同 key 得 None**（证明「先物理清除、后触发回调」）",
          all(x[3] is None for x in rec), [x[3] for x in rec])

    # ⑥‴ wild_npc 过期回调 = 清对话会话（铁律：显示与对话同时消失）
    PW.set_talk_state("g1", "u1i4expire", "npc_mayor", "welcome")
    with _Patch(TE._timers, "clock", lambda: 2000):
        TE.set_timed("g1", "u1i4expire", f"wild:{nid}", "wild_npc", data={"npc_id": nid},
                     duration_sec=10)
    with _Patch(TE._timers, "clock", lambda: 2020):
        TE.refresh_timed("g1", "u1i4expire")
    check("顺序⑥‴：`wild_npc` 过期 → `on_expire` 清掉当前对话会话",
          PW.get_talk_state("g1", "u1i4expire") is None,
          str(PW.get_talk_state("g1", "u1i4expire")))


# ══════════════════════════════════════════════════════════════════════════════
# [9] 只读断言
# ══════════════════════════════════════════════════════════════════════════════
def _check_readonly(before):
    print("【9. 只读：全程零写盘】")
    after = {f: _file_sha(f) for f in READONLY_FILES}
    bad = [f for f in READONLY_FILES if before[f] != after[f]]
    check("跑完全程 5 个源文件 sha256 前后一致（%s）" % " · ".join(READONLY_FILES),
          not bad, bad)
    for f in READONLY_FILES:
        print("     %-38s %s" % (f, after[f]))


def main() -> int:
    print("==" * 36)
    print("U1-I4 冻结门禁②：在场块（content/wild.py 18 段 + content/persistence/world.py 7 段）")
    print("==" * 36)
    print("phase = %r · GWEN_GAME_DB = %s" % (_PIN["phase"], os.environ.get("GWEN_GAME_DB")))
    before = {f: _file_sha(f) for f in READONLY_FILES}
    test_frozen_pins()
    test_aux()
    test_grid_a_locate()
    test_dialogue_grid()
    test_grid_b_present()
    test_conditions_matrix()
    test_grid_c_encounter()
    test_grid_d_lists()
    test_numbering()
    test_divergences()
    test_teeth()
    test_order_assertions()
    _check_readonly(before)
    print(f"\n{'-' * 46}\n结果：通过 {PASS} / 共 {PASS + FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
