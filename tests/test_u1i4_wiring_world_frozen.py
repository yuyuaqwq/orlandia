# -*- coding: utf-8 -*-
"""U1-I4 冻结比对**门禁③**（世界侧装配）：`content/world_cmds.py` 29 段 —— 三份 NPC 列表 /
查找链 / 会话路由 / 限时叠加 / 编号接引擎 `dialogue` + `presence` 形状。

跑法（工作区根；环境变量见 `BRIEF.md` §3.1）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1i4_wiring_world_gen.py --check
    "$PY" work/pkg/tests/test_u1i4_wiring_world_frozen.py

判据（`design/U1-I4_FROZEN_GATE.md` §10；本文件逐条打原始输出）
-------------------------------------------------------------
 [1] **29 段冻结文本 sha256 全等 `_PIN["frozen"]`** + **活实现 `inspect.getsource` sha256 全等
     `_PIN["live"]`**；`phase == "landed"` 时再断言 C 栏「预期会变」段 `frozen != live`（§2.3）。
 [2] **甲/乙类 exec 双向逐格比**（§1.3）：冻结文本 `exec` 到独立命名空间（甲 = 模块级；
     乙 = 给替身 `self`）↔ 活实现，**同输入逐格比返回值 / 副作用**。21 段（甲 11 + 乙 10）。
 [3] **丙类端到端探针**（§5.3）：8 个 async 段用 `tests/_engine_harness.py` 的 `Main` 驱动，
     断言「输出的**全部行** + `talk_state` 原文 + `set/clear_talk_state` 调用序」逐字节等于
     改实现**之前**抓的 `_PIN["aux"]["golden_wiring_probes"]`。
 [4] **aux 指纹**：会话键 / flag 键 / 落盘 JSON 文本（§3 的 ①②③）。
 [5] **口径分歧**（`U1-I4_DESIGN.md` §3.7）：① 三份列表成员集合不同（含 `HIDDEN_NPCS` 两处 +
     不含一处，判据 #3）· ③『找』不可见仍返回 + `_npc_absent` · ④ 野外首个同名早退 ·
     ⑦ 空壳 `{}` 不清残留 / 坏值才清 · ⑫ 三表零交集。
 [6] **有牙反证**（§7）：破坏 5 处（need 忽略 / 变体取末条 / `next_of` 丢 `fail_next` /
     `is_end` 恒 False / `_current_npcs` 并入 HIDDEN）→ 对应探针**必须变红**；再跑多故障场景。
 [7] **顺序断言**（§8.2）：② 限时续号随静态清单序整体改变 · ③ `side_menu` 插入原位置 ·
     ⑤ `need` 键序 = 短路序。
 [8] **只读断言**：跑完全程 3 个源文件 sha256 不变（全程零写盘）。
 [9] **计数校验**：逐网格 `sum(比对次数) == 预期`（防「循环没跑」的假绿）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1i4_wiring_world_gen.py` 从
   `base/pkg/content/world_cmds.py` 逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import inspect
import json
import os
import random
import re
import sys
import tempfile
import types

# ══════════════════════════════════════════════════════════════════════════════
# 0. 装配：包根 / 引擎根 / 宿主壳根 + 独立私有库 + shim_astrbot
# ══════════════════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ★ 独立私有库（绝不碰生产 game_data.db）
# 2026-09-18 收尾修：原落点 `LANE_ROOT/out` 是旧「工作区布局」（`<lane>/work/pkg` 三层），
#   真仓布局下 LANE_ROOT = `C:\Users` ⇒ `C:\Users\out` 不存在 → sqlite connect 直接
#   `unable to open database file`（单跑必崩；改前基线同样红，非本次修复引入）。
#   私有库改落系统临时目录下自建子目录（不写包目录、不进 git）。
_DB_DIR = os.path.join(tempfile.gettempdir(), "gwen_test_u1i4_world")
os.makedirs(_DB_DIR, exist_ok=True)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_DB_DIR, "test_u1i4_world.db"))
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
FakeEvent = H.FakeEvent
h_run = H.run

from content import world_cmds as WC                                     # noqa: E402
from content import wild as W                                            # noqa: E402
from content import dialogue as DLG                                      # noqa: E402
from content import talk_actions as TA                                   # noqa: E402
from content.catalog_quests import (NPCS, WILD_NPCS, HIDDEN_NPCS,        # noqa: E402
                                    MAIN_QUESTS, SIDE_QUESTS)
from content.catalog_space import MAP_BY_ID as _MAP_BY_ID                # noqa: E402
from content.persistence import world as PW                              # noqa: E402
import saintess_engine.dialogue as DENG                                  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_MISSING = object()

# >>> _u1i4_gen (auto) >>>

# ⚠ 本块由 `tests/_u1i4_wiring_world_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/world_cmds.py::_npc_dialogue': 'def _npc_dialogue(self, group_id, qq_id, npc_id, npc):\n    """按主线进度返回 NPC 对话(主线完成后不再重复初始台词)。\n    v95.30 A 随机台词：酱油 NPC 配置了 lines 多条 → 每天换一条（日期哈希全服一致）。"""\n    base = npc.get("dialogue", "……")\n    # v95.30 酱油 NPC 随机台词（无功能 → 不参与主线逻辑）\n    if not npc.get("funcs"):\n        return _wild.town_npc_dialogue(npc_id, npc, base)\n    # 只对发布主线的 NPC 动态化\n    if "quest" not in npc.get("funcs", []):\n        return base\n    quests = db.get_quests(group_id, qq_id)\n    main_id = quests.get("main_quest")\n    # 主线全部完成（main_quest=None 且有完成记录）→ 用完成台词\n    if not main_id and quests.get("completed_main"):\n        return npc.get("dialogue_done", base)\n    # 当前主线不是这位 NPC 发布的 → 保持初始台词（提示语会在任务逻辑里给出）\n    mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == main_id), None)\n    if mq and mq["giver"] != npc_id:\n        return base\n    # 主线已接取或进行中 → 初始台词（任务提示在 _take_main_quest 里）\n    return base\n',
    'content/world_cmds.py::_current_npcs': 'def _current_npcs(self, player):\n    """v86 子区域：当前所在位置可交互的 NPC 列表(子区域优先，回退地图级)。\n    v95.30 随机性：酱油 NPC 按 游走/概率/时段 过滤（功能 NPC 恒在）。"""\n    cur_map = player["cur_map"]\n    m = _cat_space.MAP_BY_ID.get(cur_map, {})\n    sa_id = player.get("cur_subarea") or ""\n    for sa in (m.get("subareas") or []):\n        if sa["id"] == sa_id:\n            npc_ids = sa.get("npcs") or []\n            return [_cat_quests.NPCS[nid] for nid in npc_ids if nid in _cat_quests.NPCS\n                    and _wild.town_npc_visible(nid, _cat_quests.NPCS[nid], sa_id)]\n    return [_cat_quests.NPCS[nid] for nid in m.get("npcs", []) if nid in _cat_quests.NPCS]\n',
    'content/world_cmds.py::_present_wild_hints': 'def _present_wild_hints(self, group_id, qq_id, cur_map) -> list:\n    """v127.5 限时NPC：当前地图（map 级，全图都算）在场限时野外NPC 显示行。\n\n    偶遇后挂 timed events，倒计时内地图/位置可见并带 ⏳ 剩余分钟；过期\n    list_timed 惰性清除 → 天然消失（显示与对话同时，铁律）。\n    返回例：["  🧭游商·老马 ⏳剩60分", ...]（2 空格缩进，与普通 NPC 行一致）。\n    """\n    lines = []\n    evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",\n                       data_match={"map": cur_map})\n    for ev in evs:\n        nid = ev.get("data", {}).get("npc_id") or ""\n        wnpc = _wild.ALL_WILD.get(nid)\n        if not wnpc:\n            continue\n        remain_min = max(1, -(-int(ev.get("remain", 0)) // 60))  # ceil(remain/60)\n        lines.append(f"  {wnpc.get(\'icon\', \'\')}{wnpc.get(\'name\', nid)} ⏳剩{remain_min}分")\n    return lines\n',
    'content/world_cmds.py::_start_talk_list': 'def _start_talk_list(self, group_id, qq_id) -> list:\n    """当前地图 NPC 列表（带序号展示；交谈用『对话 <名字>』/『对话 <序号>』，v123a 起裸数字不再直接找 NPC）。『对话』空参共用。"""\n    player = self._player(group_id, qq_id)\n    if player and player["cur_map"].startswith("home_"):\n        return ["家里没有 NPC 可以交谈～『出门』去镇上找人吧！"]\n    npcs = self._current_npcs(player) if player else []\n    # v127.5 限时NPC：在场野外旅人并入裸『对话』列表（排城镇 NPC 之后，带序号可对话）\n    wild_evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",\n                            data_match={"map": player["cur_map"]}) if player else []\n    if not npcs and not wild_evs:\n        return ["这里没有 NPC。输入『地图』看看哪里有 NPC～"]\n    lines = ["👥 这里的 NPC："]\n    for i, n in enumerate(npcs, 1):\n        lines.append(f"{i:>2}. {n[\'icon\']}{n[\'name\']}({n[\'title\']})")\n    # 在场野外旅人：续在城镇 NPC 之后编号（带 ⏳ 剩余分钟）\n    for j, ev in enumerate(wild_evs, len(npcs) + 1):\n        nid = ev.get("data", {}).get("npc_id") or ""\n        wnpc = _wild.ALL_WILD.get(nid)\n        if not wnpc:\n            continue\n        remain_min = max(1, -(-int(ev.get("remain", 0)) // 60))  # ceil(remain/60)\n        lines.append(f"{j:>2}. {wnpc.get(\'icon\', \'\')}{wnpc.get(\'name\', nid)} ⏳剩{remain_min}分")\n    lines.append(self._tip("npc_list"))\n    return lines\n',
    'content/world_cmds.py::_find_npc_in_map': 'def _find_npc_in_map(self, player, name_key):\n    """在当前地图找 NPC(子区域优先，回退地图级)，返回 (npc_id, npc_dict) 或 (None, None)。\n\n    v95.30 随机性：酱油 NPC 名字匹配但今天不可见（游走别处/概率未出/时段不符）\n    → 仍返回 (nid, npc)（由调用方给"不在"提示），并置 player[\'_npc_absent\'] 供提示。\n    """\n    cur_map = player["cur_map"]\n    m = _cat_space.MAP_BY_ID.get(cur_map, {})\n    sa_id = player.get("cur_subarea") or ""\n    player.pop("_npc_absent", None)\n    # 子区域 NPC 优先\n    for sa in (m.get("subareas") or []):\n        if sa["id"] == sa_id:\n            for nid in sa.get("npcs", []):\n                npc = _cat_quests.NPCS.get(nid)\n                if npc and (name_key in npc["name"] or name_key in nid):\n                    if not _wild.town_npc_visible(nid, npc, sa_id):\n                        player["_npc_absent"] = (nid, npc, sa_id)\n                    return nid, npc\n            break\n    # 地图级 NPC（含其他子区域）\n    for nid in m.get("npcs", []):\n        npc = _cat_quests.NPCS.get(nid)\n        if npc and (name_key in npc["name"] or name_key in nid):\n            if not _wild.town_npc_visible(nid, npc, sa_id):\n                player["_npc_absent"] = (nid, npc, sa_id)\n            return nid, npc\n    return None, None\n',
    'content/world_cmds.py::_town_npc_absent_hint': 'def _town_npc_absent_hint(self, nid, npc, sa_id):\n    """v95.30：酱油 NPC 名字命中但当前不可见 → 解释原因（游走去向 / 时段 / 概率未出）。\n    显示必须可触发铁律：『找』必须给出明确信息。"""\n    name = npc.get("name", "他")\n    # B 游走：今天在别的子区域 → 指路\n    today_sa = _wild.town_npc_day_sa(nid, npc, sa_id)\n    if today_sa != sa_id:\n        m = self._player_map_name(sa_id) or ""\n        sa_name = self._subarea_name(today_sa)\n        if sa_name:\n            return f"🧭 『{name}』今天不在这儿，在「{sa_name}」那边。过去找找看吧～"\n    # D 时段\n    per = npc.get("period")\n    if per:\n        period_cn = (PERIOD_CN.get(_tw.current_period(), "") or "").strip()\n        return f"🌙 『{name}』现在({period_cn})不在这里，换个时间再来吧～"\n    # C 概率未出\n    return f"🍃 『{name}』今天没来这边，改天再来看看吧～"\n',
    'content/world_cmds.py::_player_map_name': 'def _player_map_name(self, sa_id):\n    """按子区域 id 找所属地图名（用于游走提示）"""\n    for mid, m in _cat_space.MAP_BY_ID.items():\n        for sa in (m.get("subareas") or []):\n            if sa["id"] == sa_id:\n                return m.get("name", "")\n    return ""\n',
    'content/world_cmds.py::_subarea_name': 'def _subarea_name(self, sa_id):\n    """按子区域 id 找显示名"""\n    for mid, m in _cat_space.MAP_BY_ID.items():\n        for sa in (m.get("subareas") or []):\n            if sa["id"] == sa_id:\n                return sa.get("name", "")\n    return ""\n',
    'content/world_cmds.py::_find_wild_npc': 'def _find_wild_npc(self, player, name_key, group_id, qq_id):\n    """9.4：在当前地图找野外 NPC（含 roam 定位 + 出现条件判定）。\n    名字匹配但今天不在/条件不满足 → 返回 (None, None)，由调用方提示。"""\n    cur = player["cur_map"]\n    for nid, wnpc in _wild.ALL_WILD.items():\n        # v95.4：与 _find_npc_in_map 一致的子串匹配（『找 游商』→『游商·老马』）\n        if name_key not in (wnpc.get("name") or ""):\n            continue\n        if _wild.npc_map_id(nid, wnpc) != cur:\n            return None, None\n        if not _wild.wild_npc_findable(nid, wnpc, player, group_id, qq_id):\n            return None, None\n        wnpc = dict(wnpc)\n        wnpc.setdefault("title", "游历于野外的旅人")\n        return nid, wnpc\n    return None, None\n',
    'content/world_cmds.py::_wild_unseen_hint': 'def _wild_unseen_hint(self, player, name_key, group_id, qq_id):\n    """v95.15 #71：野外 NPC 名字命中、在本图但当前条件(时段/季节/天气/解锁)不满足\n    → 提示出现条件，区分『NPC 在但需定位』vs『当前时段 NPC 未出现』；无命中返回 None"""\n    cur = player["cur_map"]\n    for nid, wnpc in _wild.ALL_WILD.items():\n        if name_key not in (wnpc.get("name") or "") and name_key not in nid:\n            continue\n        if _wild.npc_map_id(nid, wnpc) != cur:\n            continue  # 今天不在这张图 → 交给方向提示\n        if _wild.wild_npc_findable(nid, wnpc, player, group_id, qq_id):\n            continue  # 条件满足（概率/保底问题），不归这里管\n        label = self._wild_cond_label(wnpc)\n        period = (PERIOD_CN.get(_tw.current_period(), "") or "").strip()\n        return f"🧭 『{name_key}』{label}，现在({period})还没到出现的时候，换个时间再来找找吧～"\n    return None\n',
    'content/world_cmds.py::_npc_direction_hint': 'def _npc_direction_hint(self, player, name_key):\n    """v95.8 #51：当前地图没找到 NPC 时，全局搜位置给方向提示；找不到返回 None\n    v59.#51：同名 NPC 分散多城镇时，玩家所在地图有命中 → 只列当前地图位置（单一方向），\n    不再三城镇并列无方位（实测『找 城主』曾并列白鹿城/铁港城/珍珠城）"""\n    cur = player["cur_map"]\n    hits = []\n    for nid, npc in _cat_quests.NPCS.items():\n        if name_key in (npc.get("name") or "") or name_key in nid:\n            hits.append((nid, npc))\n    for nid, wnpc in _wild.ALL_WILD.items():\n        if name_key in (wnpc.get("name") or "") or name_key in nid:\n            hits.append((nid, wnpc))\n    # v101.29：野外精英/Boss 名也纳入搜索（任务目标常是强敌而非 NPC，\n    # 如『找 铁牙』→ 丘陵狼王·铁牙在丘陵顶——旧代码只搜 NPC 表会命中同名\n    # "地下守卫·铁牙/卫兵·铁牙" 给出错误方向）。精英/Boss 元组格式\n    # (id, 显示名, role, lv, skills, drops)，伪 nid 用 "map:subarea" 便于定位。\n    for mid, m in _cat_space.MAP_BY_ID.items():\n        for sa in (m.get("subareas") or []):\n            for ent in (sa.get("elite"), sa.get("boss")):\n                if not ent:\n                    continue\n                ename = ent[1] if len(ent) > 1 else ""\n                if ename and (name_key in ename or ename in name_key):\n                    hits.append((f"{mid}:{sa[\'id\']}", {"name": ename, "map": mid}))\n    if not hits:\n        return None\n    locs = []  # (map_id, subarea_id 或 None, 显示位置)\n    for nid, npc in hits:\n        m_id = npc.get("map") or ""\n        m = _cat_space.MAP_BY_ID.get(m_id, {})\n        m_name = m.get("name", m_id or "未知之地")\n        sa_name = ""\n        sa_id = None\n        if ":" in nid:\n            # v101.29 精英/Boss 条目：nid 格式 "map_id:subarea_id"\n            _said = nid.split(":", 1)[1]\n            sa_id = _said\n            for sa in (m.get("subareas") or []):\n                if sa["id"] == _said:\n                    sa_name = sa.get("name", "")\n                    break\n        else:\n            for sa in (m.get("subareas") or []):\n                if nid in (sa.get("npcs") or []):\n                    sa_name = sa.get("name", "")\n                    sa_id = sa["id"]\n                    break\n        locs.append((m_id, sa_id, f"{m_name}·{sa_name}" if sa_name else m_name))\n    cur_sa = player.get("cur_subarea") or ""\n    in_here = cur in {m_id for m_id, _, _ in locs}\n    # v95.25 #135：前缀明确"在/不在你所在的地图"，不再用误导性的"你所在的地图的…"\n    # v113.5 O90：同图但目标在别的子区域时，原文案说"就在你所在的「目标子区域」一带"\n    # 把目标位置说成玩家所在（误导定位）——同图不同子区域统一走"（你现在不在这里）"样式\n    # （对齐地精商人版文案）；子区域未知的 NPC 按旧行为视为同处\n    if in_here:\n        same_sa = [l for m_id, sa_id, l in locs\n                   if m_id == cur and (not sa_id or not cur_sa or sa_id == cur_sa)]\n        if same_sa:\n            here_uniq = list(dict.fromkeys(same_sa))\n            return f"🧭 『{name_key}』就在你所在的「{\'、\'.join(here_uniq)}」一带。输入『地图』查看路线，到了地方用『对话』定位～"\n    uniq = list(dict.fromkeys(l for _, _, l in locs))\n    return f"🧭 『{name_key}』在「{\'、\'.join(uniq)}」一带（你现在不在这里）。输入『地图』查看路线，到了地方用『对话』定位～"\n',
    'content/world_cmds.py::_wild_cond_label': 'def _wild_cond_label(self, npc: dict) -> str:\n    """野外 NPC 出现条件 → 中文标签(见闻录/时间面板用)"""\n    cond = npc.get("condition", {})\n    labels = []\n    t = cond.get("time")\n    if t:\n        tm = {"morning": "清晨", "day": "白天", "evening": "黄昏", "night": "夜晚"}\n        labels.append("/".join(tm.get(x, x) for x in t) + "出现")\n    s_ = cond.get("season")\n    if s_:\n        sm = {"spring": "春季", "summer": "夏季", "autumn": "秋季", "winter": "冬季"}\n        labels.append("/".join(sm.get(x, x) for x in s_) + "限定")\n    w = cond.get("weather")\n    if w:\n        wm = {"rain": "雨天", "storm": "暴风雨", "snow": "雪天", "fog": "雾天", "sunny": "晴夜"}\n        labels.append(wm.get(w, w) + "出现")\n    if cond.get("min_level"):\n        labels.append(f"Lv.{cond[\'min_level\']}+")\n    if npc.get("cycle"):\n        labels.append(f"每{npc[\'cycle\']}天")\n    if npc.get("chance"):\n        labels.append(f"概率 {int(npc[\'chance\']*100)}%")\n    if npc.get("unlock"):\n        labels.append("🔓 需解锁")\n    return "，".join(labels) if labels else "随时可能出现"\n',
    'content/world_cmds.py::_talk_active': 'def _talk_active(self, group_id, qq_id):\n    """统一对话状态读取（O99 修复：统一对话结束状态判定）。\n\n    对话结束判定（『对话 0』/移动拦截/副业材料保护）必须同源同判定：\n    键存在但 JSON 损坏/非 dict（历史脏数据）时视为"无对话"并顺手清除残留键，\n    杜绝『对话 0』提示"没有正在进行的对话"而移动仍被残留状态拦截的判定漂移。\n    """\n    st = db.get_talk_state(group_id, qq_id)\n    if st is not None and not isinstance(st, dict):\n        db.clear_talk_state(group_id, qq_id)\n        return None\n    if st is None:\n        raw = db.get_event_state(db.talk_state_key(group_id, qq_id))\n        if raw:\n            db.clear_talk_state(group_id, qq_id)  # 损坏/无法解析的残留键 → 清除\n    return st\n',
    'content/world_cmds.py::_talk_ctx': 'def _talk_ctx(self, group_id, qq_id, npc_id):\n    """对话引擎上下文：player + quests + 该 NPC 已设 flag + 已拜师副业"""\n    player = self._player(group_id, qq_id) or {}\n    return {\n        "player": player,\n        "_gid": group_id, "_qid": qq_id,   # v173.3：渲染层自动补任务入口需要\n        "quests": db.get_quests(group_id, qq_id),\n        "flags": db.get_talk_flags(group_id, qq_id, npc_id),\n        "apprentices": player.get("apprentices", []),\n        "npc_id": npc_id,\n        "side_quests": _cat_quests.SIDE_QUESTS,\n        "item_counts": {m: db.count_item(group_id, qq_id, m) for m in {(o.get("objective") or {}).get("collect") for o in _cat_quests.SIDE_QUESTS} if m},\n        # v127.6 side_menu 动态菜单：core.visible_options 渲染时用该回调\n        # 把『有活儿要交给我吗』类选项展开成『每个可接支线一个子选项』\n        "side_menu_expand": lambda opt: self._side_menu_expand(group_id, qq_id, npc_id, opt),\n    }\n',
    'content/world_cmds.py::_side_menu_expand': 'def _side_menu_expand(self, group_id, qq_id, npc_id, opt) -> list:\n    """v127.6：side_menu 选项的动态展开——每个可接支线一个子选项（玩家自选单接）。\n\n    供 core.visible_options 的 side_menu_expand 回调调用；无任何可接支线 → 返回 []（菜单不出现）。\n    子选项 next：side_menu.after（连串接，通常为该 NPC 对话树 start）→ 选项原 next → __end__。\n    每条子选项 action: {"side_take_one": sid}，走 talk_actions.side_take_one 单条接取。\n    """\n    available = self._side_available_list(group_id, qq_id, npc_id, None)\n    if not available:\n        return []\n    nxt = (opt.get("side_menu") or {}).get("after") or opt.get("next") or "__end__"\n    subs = []\n    for item in available:\n        subs.append({\n            "text": f"📜 接『{item[\'name\']}』({item[\'objective_text\']})",\n            "next": nxt,\n            "action": {"side_take_one": item["sid"]},\n        })\n    return subs\n',
    'content/world_cmds.py::_render_talk_node': 'def _render_talk_node(self, npc, dlg, node, ctx) -> list:\n    """渲染一个对话节点：头像 + 台词 + 可见选项\n    v101.23：台词走 _dlg.node_text——支持 texts 条件变体（随主线进度切换）\n    v173.3 意见#113/#163/#164（鱼鱼拍板）：NPC 对话树自动补任务入口——\n    当 NPC 名下有可接支线且当前节点选项没任务入口时，自动展开『📜 有委托可接』\n    （复用 side_menu 动态子选项），新手不再"找不到任务"。"""\n    lines = [f"{npc[\'icon\']}【{npc[\'name\']}】{npc[\'title\']}",\n             f"“{_dlg.node_text(node, ctx)}”"]\n    opts = _dlg.visible_options(dlg, node, ctx)\n    # v173.3：自动补任务入口——节点无任何任务类选项 & NPC 有可接支线时展开\n    if not any((o.get("side_menu") is not None) or (o.get("action") or {}).get("side_offer")\n               or (o.get("action") or {}).get("side_take") or (o.get("action") or {}).get("side_take_one")\n               or (o.get("action") or {}).get("quest_take")\n               for o in opts):\n        try:\n            npc_id = ctx.get("npc_id") or ""\n            _auto_opt = {"text": "📜 有活儿要交给我吗？", "next": "__end__",\n                         "need": {"side_available": True}, "side_menu": {"after": "welcome"}}\n            _expanded = self._side_menu_expand(ctx.get("_gid") or "", ctx.get("_qid") or "", npc_id, _auto_opt)\n            if _expanded:\n                opts = list(opts) + _expanded\n        except Exception:\n            pass\n    if opts:\n        lines.append("━━━━━━━━━━━━")\n        for i, opt in enumerate(opts, 1):\n            lines.append(f"{i}. {opt[\'text\']}")\n        lines.append("0. 结束对话")\n        lines.append(self._tip("talk_tree"))\n    return lines\n',
    'content/world_cmds.py::_apply_talk_action_async': 'async def _apply_talk_action_async(self, group_id, qq_id, player, npc_id, action):\n    """异步版对话动作执行（v113：支持 hidden_evolve 等 async 动作）——talk_choice 调用本方法。\n\n    返回 (通知行, 路由提示)。路由提示由条件型动作（apprentice_check 等）设置：\n      None    → 走选项 next\n      "fail"  → 走选项 fail_next\n      "__end__" → 直接结束对话\n    v124.3（审计）：apprentice_check 注册表化后 talk_choice 主循环不再特判，\n    只做本方法返回的通用路由分发；未知 action 键由 talk_actions.check_action_keys 告警。"""\n    lines = []\n    route = None\n    self._talk_route = None\n    self._talk_tail = None\n    if not action:\n        return lines, route\n    import inspect\n    from .talk_actions import ACTIONS      # 包内注册表（宿主那份是 17+1 行转发，注册序同）\n    _check_action_keys(action)             # 宿主独有（接口表第 4 行冻结：走注入/兜底口）\n    for key, fn in ACTIONS.items():\n        if not action.get(key):\n            continue\n        r = fn(self, group_id, qq_id, player, npc_id, action)\n        if inspect.isawaitable(r):\n            r = await r\n        lines += r\n        if self._talk_route is not None:\n            # 条件型动作已判定：中断后续动作链（旧特判失败路径零动作执行——\n            # 如 apprentice_check 失败时 consume_item 不扣料）\n            route = self._talk_route\n            break\n    if self._talk_tail:\n        lines += self._talk_tail\n    return lines, route\n',
    'content/world_cmds.py::_apply_talk_action': 'def _apply_talk_action(self, group_id, qq_id, player, npc_id, action) -> list:\n    """执行选项动作(涉及 DB 的副作用统一在这落地)，返回通知行\n    v101.23d：动作注册表化——commands/talk_actions.py 的 ACTIONS（与 CONDITIONS\n    注册表对称），加新动作 = register 一个函数，本方法零改动。\n    同步版：仅执行同步动作（测试/旧调用用）；对话主链路走 _apply_talk_action_async。\n    v113：hidden_evolve 为异步动作，同步版会跳过它（返回空）——对话内转职走 async 版。\n    v124.3（审计）：与 async 版同源——未知 action 键告警 + 条件型动作（apprentice_check）\n    中断动作链；路由提示不入返回值（仅 async 版返回，供 talk_choice 分发）。"""\n    lines = []\n    self._talk_route = None\n    self._talk_tail = None\n    if not action:\n        return lines\n    import inspect\n    from .talk_actions import ACTIONS      # 包内注册表（宿主那份是 17+1 行转发，注册序同）\n    _check_action_keys(action)             # 宿主独有（接口表第 4 行冻结：走注入/兜底口）\n    for key, fn in ACTIONS.items():\n        if not action.get(key):\n            continue\n        r = fn(self, group_id, qq_id, player, npc_id, action)\n        if inspect.isawaitable(r):\n            continue  # 异步动作（hidden_evolve）同步版跳过\n        lines += r\n        if self._talk_route is not None:\n            break\n    if self._talk_tail:\n        lines += self._talk_tail\n    return lines\n',
    'content/world_cmds.py::talk_choice': 'async def talk_choice(self, event: AstrMessageEvent, group_id, qq_id, player):\n    # O99 修复：统一对话状态判定（损坏残留键在 _talk_active 内清除，\n    # 对话中『对话 0』亦拦截（v127.8b）与移动拦截同源同判定，不再出现"提示无对话但树仍在"的漂移）\n    st = self._talk_active(group_id, qq_id)\n    if not st:\n        # v101.16 『找』→『对话』：无对话中时『对话 <名字/序号>』= 找 NPC 开始对话\n        msg0 = event.get_message_str().strip()\n        msg0 = re.sub(r"^\\[At:[^\\]]*\\]\\s*", "", msg0)\n        if msg0.startswith("对话"):\n            raw0 = msg0[len("对话"):].strip()\n            if raw0:\n                # v105 O64：『对话 0』在无对话状态时明确提示（原实现被 find_npc 当 NPC 序号 0，\n                # 报"这里没有第 0 位 NPC"——玩家在单层 NPC 闲聊后想结束对话却得不到退出反馈）\n                # O99 修复：全角 ０ 与 ASCII 0 同判（此前全角 ０ 落入 find_npc 报"没有第 0 位"）\n                if raw0 in ("0", "０"):\n                    yield event.plain_result("你现在没有正在进行的对话。输入『对话 <NPC名>』开始交谈～")\n                    return\n                # 复用 find_npc 查找/渲染链（改写消息为『找 X』）\n                event.message_str = "找 " + raw0\n                async for r in self.find_npc(event):\n                    yield r\n                return\n            # 『对话』空参 = 显示当前 NPC 列表\n            yield event.plain_result("\\n".join(self._start_talk_list(group_id, qq_id)))\n            return\n        yield event.plain_result("你现在没有正在进行的对话。输入『对话 <NPC名>』开始交谈～")\n        return\n    npc_id = st.get("npc", "")\n    npc = _cat_quests.NPCS.get(npc_id) or _wild.ALL_WILD.get(npc_id)\n    if not npc:\n        db.clear_talk_state(group_id, qq_id)\n        yield event.plain_result("这位 NPC 似乎已经离开了……")\n        return\n    npc = dict(npc)\n    npc.setdefault("title", "游历于野外的旅人")  # v95.11：wild NPC 无 title，与 _find_wild_npc 一致\n    # 惰性失效：NPC 不在当前地图 → 会话作废（wild NPC 按 roam 定位）\n    if _wild.npc_map_id(npc_id, npc) != player.get("cur_map"):\n        db.clear_talk_state(group_id, qq_id)\n        _ta = "她" if npc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别\n        yield event.plain_result(f"{npc[\'name\']}不在这里了，对话只能作罢。去找{_ta}再聊聊吧～")\n        return\n    # v127.5 限时NPC：对话中野外NPC的在场的限时事件过期 → 会话作废\n    # （倒计时结束显示与对话同时消失；与 npc_map_id 失效同位置、同文案风格）\n    if npc_id in _wild.ALL_WILD and not _timed.get_timed(group_id, qq_id, f"wild:{npc_id}"):\n        db.clear_talk_state(group_id, qq_id)\n        _ta = "她" if npc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别\n        yield event.plain_result(f"{npc[\'name\']}已经离开了，对话只能作罢。去找{_ta}再聊聊吧～")\n        return\n    dlg = _dlg.get_dialogue(npc_id)\n    if not dlg:\n        db.clear_talk_state(group_id, qq_id)\n        yield event.plain_result(f"{npc[\'name\']}似乎不想再多说了。")\n        return\n    # 剥指令名拿参数（对话/继续/结束对话/再见/告辞）\n    msg = event.get_message_str().strip()\n    msg = re.sub(r"^\\[At:[^\\]]*\\]\\s*", "", msg)\n    raw = msg\n    for cmd in ("结束对话", "对话", "继续", "再见", "告辞"):\n        if msg.startswith(cmd):\n            raw = msg[len(cmd):].strip()\n            break\n    # v127.8（鱼鱼拍板）：对话进行中『对话 <参数>』拦截——\n    # ① 不能用于回复 NPC（选项回复走裸数字 1/2/3…，回复 0 结束对话）\n    # ② 不能跳去别的 NPC（先回复 0 结束当前对话，才能『对话 <别的NPC>』）\n    # 此前 v101.27 #412 的「『对话 数字』= 菜单选项 / 『对话 名字』= 找 NPC」规则整体作废。\n    # 『对话』空参 → 重渲染当前节点（向下兼容）；v127.8 起对话中任何『对话 X』（含 0）一律拦截，结束统一回复 0。\n    # v127.8b（鱼鱼拍板）：『对话 0』也不保留——对话中任何『对话 X』（含 0）\n    # 一律拦截，结束对话统一回复裸数字 0（与选项回复同通道，无二义性）。\n    if msg.startswith("对话") and raw:\n        yield event.plain_result(\n            f"你正在和 {npc[\'name\']} 对话——直接回复数字选选项，回复 0 结束对话～\\n"\n            f"💡 想找别的 NPC？先回复 0 结束当前对话再说")\n        return\n    cur_node_id = st.get("node", dlg.get("start", ""))\n    node = _dlg.dialogue_node(dlg, cur_node_id)\n    ctx = self._talk_ctx(group_id, qq_id, npc_id)\n    opts = _dlg.visible_options(dlg, node, ctx)\n    if raw.isdigit():\n        idx = int(raw)\n        if idx == 0:\n            db.clear_talk_state(group_id, qq_id)\n            yield event.plain_result(f"{npc[\'name\']}：那就再会了，冒险者。")\n            return\n        if idx < 1 or idx > len(opts):\n            # v101.28l #426：单选项时不再显示"1-1"（越界文案）\n            _sel_hint = "回复 1 选择" if len(opts) == 1 else f"回复 1-{len(opts)} 选择"\n            yield event.plain_result(f"没有这个选项！{_sel_hint}，回复 0 结束。")\n            return\n        opt = opts[idx - 1]\n        player = self._player(group_id, qq_id)\n        action = opt.get("action") or {}\n        nxt = opt.get("next", "__end__")\n        # v124.3（审计）：apprentice_check 已注册为动作（talk_actions.py），\n        # 主循环不再特判——条件型动作经 _apply_talk_action_async 返回的路由分发：\n        #   "fail"（材料不足）→ 走选项 fail_next；"__end__"（副业未解锁 #101.29）→ 结束对话\n        notices, _route = await self._apply_talk_action_async(group_id, qq_id, player, npc_id, action)\n        if _route == "__end__":\n            db.clear_talk_state(group_id, qq_id)\n            lines = notices + [f"{npc[\'name\']}：那就再会了，冒险者。"]\n            yield event.plain_result("\\n".join(lines))\n            return\n        if _route == "fail":\n            nxt = opt.get("fail_next", nxt)\n        # v95.11：talk 型主线与目标 NPC 对话即达成（active 空进度遗留态 → ready，修复主线卡死）\n        notices += self._talk_quest_progress(group_id, qq_id, npc_id)\n        # v105 P3：对话动作链落地后补成就判定（拜师/转职/任务交付等动作改 DB 后立即解锁——\n        # 原实现无此调用，『拜师学艺/全知全能』等依赖学徒数的成就要等下次事件才判定，\n        # 全知全能(第 8 条拜师)的全副业经验 +10% 加成也因此延迟生效）\n        _ach.check_achievements(group_id, qq_id)\n        if _dlg.is_end(nxt):\n            db.clear_talk_state(group_id, qq_id)\n            lines = notices + [f"{npc[\'name\']}：那就再会了，冒险者。"]\n            yield event.plain_result("\\n".join(lines))\n            return\n        db.set_talk_state(group_id, qq_id, npc_id, nxt)\n        new_node = _dlg.dialogue_node(dlg, nxt)\n        ctx = self._talk_ctx(group_id, qq_id, npc_id)\n        lines = notices + self._render_talk_node(npc, dlg, new_node, ctx)\n        yield event.plain_result("\\n".join(lines))\n        return\n    if not raw and any(c in msg for c in ("结束对话", "再见", "告辞")):\n        db.clear_talk_state(group_id, qq_id)\n        yield event.plain_result(f"{npc[\'name\']}：那就再会了，冒险者。")\n        return\n    # 无参数/其他 → 重渲染当前节点\n    lines = self._render_talk_node(npc, dlg, node, ctx)\n    yield event.plain_result("\\n".join(lines))\n',
    'content/world_cmds.py::npc_quick_dialog': 'async def npc_quick_dialog(self, event: AstrMessageEvent, group_id, qq_id):\n    """裸数字消费链：对话树选项 > 物品查看 > 移动模式 > 放行快捷指令。\n\n    v101.16：『对话』改版配套——地图/NPC 列表带序号，回复序号直接交谈。\n    v123a（鱼鱼拍板）：移除「序号直接找 NPC」——裸数字不再触发找 NPC 对话，\n    NPC 列表序号仅作展示，交谈须『对话 <名字>』/『对话 <序号>』；\n    对话树中的选项回复（_talk_active）保留。\n    v128.2（鱼鱼拍板）：『位置 0』/发 0 进入赶路模式的旧捷径已移除，\n    赶路入口统一为『赶路』指令（hurry_view 进入）；0 仅在赶路模式中用于结束。\n    priority=100 高于 shortcut_trigger(默认0)：命中即 stop_event 拦截快捷指令；\n    无状态可消费时 return（不 yield）→ 放行给快捷指令。\n    v127.4：去掉 @require_player()——裸数字是对话树/移动/快捷等"已注册玩家专属"的\n    交互链，未注册用户发『1』『2』不应被"你还没有角色"打扰（鱼鱼反馈），\n    改为函数内对未注册静默 return（不 yield、不提示），放行顺延。\n    """\n    # v127.4：未注册玩家无对话树/物品查看/移动模式/快捷绑定可消费 → 静默放行，免"未注册"打扰\n    if not self._player(group_id, qq_id):\n        return\n    num = event.get_message_str().strip()\n    num = re.sub(r"^\\[At:[^\\]]*\\]\\s*", "", num).strip()\n    # v124.2 全角数字兼容：全角『１』等回复转半角再比较（分支交付/对话树选项/物品查看/移动共用）\n    num = num.translate(str.maketrans("０１２３４５６７８９", "0123456789"))\n    # v124 分支交付：支线 ready + branch_wait 时，裸数字 = 分支选项（优先于对话树）\n    _bw = self._branch_wait_sid(group_id, qq_id)\n    if _bw and (num.isdigit() or num):\n        lines = self._complete_side_quest(group_id, qq_id, _bw, branch_choice=num)\n        yield event.plain_result("\\n".join(lines))\n        self._stop_event_safe(event)\n        return\n    # v173.3 意见#103：武器自选礼包挂起——回复数字领取对应武器\n    _wp = self._weapon_pick_active(group_id, qq_id)\n    if _wp:\n        result = self._weapon_pick_choose(group_id, qq_id, num)\n        yield event.plain_result(result)\n        self._stop_event_safe(event)\n        return\n    # O99 修复：与 talk_choice/move 同源判定（_talk_active 清除损坏残留键）\n    st = self._talk_active(group_id, qq_id)\n    if st:\n        # 对话树选项选择（复用 talk_choice 有状态分支：『对话 1』同款）\n        async for r in self.talk_choice(event):\n            yield r\n        self._stop_event_safe(event)\n        return\n    # v101.21 物品查看模式：开启时裸数字优先查物品（改消息转发 item_detail）\n    if db.get_event_state(f"item_view_mode:{qq_id}"):\n        event.message_str = f"物品详情 {num}"\n        async for r in self.item_detail(event):\n            yield r\n        self._stop_event_safe(event)\n        return\n    # v128 赶路模式：开启时裸数字赶路（改消息转发 move），0=关闭\n    if db.get_event_state(f"move_mode:{qq_id}"):\n        if num == "0":\n            db.set_event_state(f"move_mode:{qq_id}", "")\n            db.set_event_state(f"hurry_type:{qq_id}", "")  # v128.1 结束赶路同时清过滤\n            yield event.plain_result("🚶 赶路模式已结束，回复数字不再自动赶路～")\n            self._stop_event_safe(event)\n            return\n        event.message_str = f"前往 {num}"\n        async for r in self.move(event, group_id, qq_id):      # ★ 修：move 需要 group_id/qq_id\n            yield r                                      #   （此前漏传 ⇒ TypeError ⇒ 该快捷指令整条挂掉）\n        self._stop_event_safe(event)\n        return\n    # v128.2：『位置 0』/发 0 进入赶路模式的旧捷径已移除——无状态可消费时\n    # 回复 0 一律放行（不再开启赶路模式）；进入赶路唯一入口=『赶路』指令\n    # （hurry_view）；0 仅在赶路模式中用于结束（见上）。\n    # v123a：序号直接找 NPC 已移除——无对话/物品/移动状态时一律放行\n    # （快捷指令由 shortcut_trigger 消费；未绑定则无响应）\n    return\n',
    'content/world_cmds.py::find_npc': 'async def find_npc(self, event: AstrMessageEvent):\n    """『对话 <NPC名/序号>』内部查找链：被 talk_choice 无对话分支调用；不对外注册（v127.8）"""\n    group_id, qq_id = self._uid(event)\n    name_key = self._strip_cmd(event, "找")\n    player = self._player(group_id, qq_id)\n    if self._is_redname(qq_id):\n        yield event.plain_result("☠️ 你是红名！城里的 NPC 都躲着你走……(等红名消退再来)")\n        return\n    name_key = name_key.strip()\n    if not name_key:\n        cur_m = player["cur_map"]\n        if cur_m.startswith("home_"):\n            yield event.plain_result("家里没有 NPC 可以交谈～『出门』去镇上找人吧！")\n            return\n        # v127.5 限时NPC：与『对话』空参同源——在场野外旅人也并入列表\n        yield event.plain_result("\\n".join(self._start_talk_list(group_id, qq_id)))\n        return\n    # 序号找：『找 1』→ 当前地图第 1 个 NPC（含 v127.5 在场野外旅人续号）\n    if name_key.isdigit():\n        if player["cur_map"].startswith("home_"):\n            yield event.plain_result("家里没有 NPC 可以交谈～『出门』去镇上找人吧！")\n            return\n        npcs = self._current_npcs(player)\n        wild_evs = _timed.list_timed(group_id, qq_id, type_key="wild_npc",\n                                data_match={"map": player["cur_map"]})\n        total = len(npcs) + len(wild_evs)\n        idx = int(name_key)\n        if idx < 1 or idx > total:\n            yield event.plain_result(f"这里没有第 {idx} 位 NPC(共 {total} 位)！『对话』查看列表～")\n            return\n        if idx <= len(npcs):\n            npc = npcs[idx - 1]\n            npc_id = next((nid for nid, n in _cat_quests.NPCS.items() if n is npc), None)\n        else:\n            # v127.5 限时NPC：序号命中在场野外旅人（不在 _cat_quests.NPCS，不能走反查）\n            _ev = wild_evs[idx - len(npcs) - 1]\n            npc_id = _ev.get("data", {}).get("npc_id") or ""\n            _w = _wild.ALL_WILD.get(npc_id)\n            if not _w:\n                yield event.plain_result("这位旅人似乎已经离开了……")\n                return\n            npc = dict(_w)\n            npc.setdefault("title", "游历于野外的旅人")  # 与 _find_wild_npc 一致\n    else:\n        npc_id, npc = self._find_npc_in_map(player, name_key)\n        if npc and player.get("_npc_absent"):\n            # v95.30 随机性：酱油 NPC 名字匹配但今天不在（游走/概率/时段）\n            yield event.plain_result(self._town_npc_absent_hint(*player["_npc_absent"]))\n            return\n    if not npc:\n        # v87.2 副本地图化：副本层内 NPC（HIDDEN_NPCS，按当前层 npcs 列表查）\n        inst_row = self._instance_battle_for(group_id, qq_id)\n        if inst_row and inst_row["state"].get("mode") == "map":\n            stage_npcs = self._stage_npcs(group_id, qq_id)\n            for nid in stage_npcs:\n                n = _cat_quests.HIDDEN_NPCS.get(nid, {})\n                if n and (name_key in n.get("name", "") or name_key in nid):\n                    npc_id, npc = nid, n\n                    break\n    if not npc:\n        # 9.4：野外 NPC（当前地图 + 出现条件）\n        npc_id, npc = self._find_wild_npc(player, name_key, group_id, qq_id)\n        if npc:\n            # v127.5 限时NPC：偶遇制——只在倒计时内在场可找；未偶遇/过期 → "今天没遇到"\n            if not _timed.get_timed(group_id, qq_id, f"wild:{npc_id}"):\n                _ta = "她" if npc.get("gender") == "女" else "他"\n                yield event.plain_result(\n                    f"🍃 『{name_key}』今天还没遇到……多『探索』几圈，{_ta}不定什么时候就路过这里啦～")\n                return\n    if not npc:\n        # v95.15 #71：名字命中但时段/条件不满足（NPC 在本图却找不到）→ 提示出现条件\n        unseen = self._wild_unseen_hint(player, name_key, group_id, qq_id)\n        if unseen:\n            yield event.plain_result(unseen)\n            return\n        # v95.8 #51：不在当前子区域/地图时，全局搜位置给方向提示\n        hint = self._npc_direction_hint(player, name_key)\n        if hint:\n            yield event.plain_result(hint)\n            return\n        yield event.plain_result(\n            f"你在这里没找到『{name_key}』。他可能不在这里，或还没到出现的时候……(『时间』看看此刻谁在附近)")\n        return\n    dlg = _dlg.get_dialogue(npc_id)\n    if dlg:\n        # v65：配置了多轮对话树 → 进入对话\n        db.set_talk_state(group_id, qq_id, npc_id, dlg.get("start", ""))\n        ctx = self._talk_ctx(group_id, qq_id, npc_id)\n        node = _dlg.dialogue_node(dlg, dlg.get("start", ""))\n        lines = self._render_talk_node(npc, dlg, node, ctx)\n    else:\n        lines = [f"{npc[\'icon\']}【{npc[\'name\']}】{npc[\'title\']}", f"“{self._npc_dialogue(group_id, qq_id, npc_id, npc)}”"]\n    # 功能提示\n    funcs = npc.get("funcs", [])\n    if "quest" in funcs:\n        # v95.11 #50：代词按 NPC 性别（玛莎等女性 NPC 用"她"）\n        _ta = "她" if npc.get("gender") == "女" else "他"\n        if dlg:\n            # v95.9 对话式任务：有对话树的 NPC 通过对话选项接取/交付，这里只给引导\n            _quests = db.get_quests(group_id, qq_id)\n            _mid = _quests.get("main_quest")\n            _mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == _mid), None) if _mid else None\n            if _mq and _mq["giver"] == npc_id:\n                _st = _quests.get("main_status", "pending")\n                if _st == "pending":\n                    lines.append(f"📜 主线『{_mq[\'name\']}』可接取——和{_ta}对话接下任务吧～")\n                elif _st == "ready":\n                    lines.append(f"✅ 主线『{_mq[\'name\']}』达成！和{_ta}对话交付领奖～")\n            _side = _quests.get("side", {})\n            # v127.6 预告全量：复用 _side_available_list（与对话菜单同源过滤）——\n            # 把该 NPC 所有可接支线都列出来（此前 break 只显示第一条，与实际可接数对不上）\n            for _av in self._side_available_list(group_id, qq_id, npc_id, npc):\n                lines.append(f"📜 支线『{_av[\'name\']}』可接取——和{_ta}对话接下吧～")\n            for _sid, _sq in list(_side.items()):\n                _sqd = next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == _sid), None)\n                if _sqd and _sqd["giver"] == npc_id and _sq.get("status") == "ready":\n                    lines.append(f"✅ 支线『{_sqd[\'name\']}』已完成！和{_ta}对话交付～")\n                    break\n            # v124 progress_text：该 NPC 名下有进行中的链式支线 → 输出推进台词（有对话树的 NPC 也显示）\n            for _sid, _sq in list(_side.items()):\n                _sqd = next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == _sid), None)\n                if _sqd and _sqd["giver"] == npc_id and _sq.get("status") == "active":\n                    _pt = _sqd.get("progress_text")\n                    if _pt:\n                        lines.append(f"  💬 {_pt}")\n                        break\n        else:\n            # 无对话树的 NPC：保持自动接取/交付（对话选项不存在，指令与提示兜底）\n            lines += self._take_main_quest(group_id, qq_id, npc_id, npc)\n            lines += self._offer_side_quests(group_id, qq_id, npc_id, npc)\n    if "shop" in funcs and self._at_shop(player, group_id, qq_id):\n        lines.append("🏪 输入『商店』可以买东西")\n    if "trade" in funcs:\n        _ta = "她" if npc.get("gender") == "女" else "他"  # v95 #141：代词跟随 NPC 性别\n        lines.append(f"🧭 输入『商店』看看{_ta}的货（行商有独家补给）")\n    if "heal" in funcs and self._at_healer(player):\n        lines.append("🏨 输入『住宿』恢复满血(需要金币)")\n    if "daily" in funcs:\n        lines.append("📜 输入『每日』领取今日悬赏")\n    if "lore" in funcs:\n        ta = "她" if npc.get("gender") == "女" else "他"\n        # v101.25 #311：lore 空挂修复——提示"讲传说"却没有传说内容（world.py 注释\n        # 曾承认翠羽/说书人·巴尔空挂）。现在直接输出 NPC dialogue 作为传说正文，\n        # 不再只给一句空引导。\n        _lore_txt = npc.get("lore") or npc.get("dialogue", "")\n        if _lore_txt:\n            lines.append(f"🎻 {ta}给你讲了一个传说：\\n“{_lore_txt}”")\n        else:\n            lines.append(f"🎻 {ta}捋了捋胡子，说起一段大陆往事……(传说散落在各地，多去听听老人们的见闻吧)")\n        lines.append(self._tip("encyclopedia"))\n    if "teach" in funcs:\n        # v104 P2（M21）teach 空挂修复：有对话树的教习 NPC 走对话树选项；\n        # 无对话树的教习 NPC（龙语者·古尔/上古守卫者/墓王·静语）→ 按职业直接传授对应技能\n        if dlg:\n            lines.append("🗡️ 直接回复序号继续交谈，这位前辈或许能指点你一二")\n        else:\n            lines.extend(self._teach_by_npc(group_id, qq_id, player, npc_id))\n    if "ency" in funcs:\n        lines.append("📚 输入『百科 <材料/怪物/地图名>』查询世界知识(镇长藏书)")\n    # v104 P1（M21）：隐藏 NPC 解锁 flag 设置点——与特定野外 NPC 交谈即授予（幂等）\n    _granted = self._grant_wild_unlock_flags(group_id, qq_id, npc_id)\n    if _granted:\n        lines.append(_granted)\n    yield event.plain_result("\\n".join(lines))\n',
    'content/world_cmds.py::move': 'async def move(self, event: AstrMessageEvent, group_id, qq_id):\n    dest = self._strip_cmd(event, "前往")\n    if dest.startswith("移动"):\n        dest = dest[2:].strip()  # v104 P2(M22): 『移动 <地名/序号>』别名参数剥离（双名共存）\n    player = self._player(group_id, qq_id)\n    # v87.13 对话中禁止移动：多轮对话进行时先回复 0 结束（v127.8 起『对话 0』亦拦截）\n    # O99 修复：统一对话状态判定（_talk_active 会清除损坏残留键，防判定漂移）\n    if self._talk_active(group_id, qq_id):\n        yield event.plain_result("你还在和 NPC 交谈中！先回复 0 结束对话再动身吧。")\n        return\n    # v137 副本地图化：副本内移动（队长带队，房间连通）——必须先于 _in_battle 全局拦截：\n    # 副本地图模式（mode=map，st.boss=None）下 battle 锁仍持有，_in_battle 会拦截所有移动。\n    # _instance_move_route 内部校验副本状态并自行处理锁（解锁→推进→按需重新上锁）。\n    _mv_dest = dest\n    if _mv_dest.startswith("移动"):\n        _mv_dest = _mv_dest[2:].strip()\n    _routed = False\n    async for _r in self._instance_move_route(event, group_id, qq_id, player, _mv_dest.strip()):\n        yield _r\n        _routed = True\n    if _routed:\n        return\n    dest = _mv_dest\n    # v95.17 #146：战斗中禁止移动（与传送/回家/拜访一致，防战斗挂起跨图/被撞怪覆盖）\n    if self._in_battle(group_id, qq_id):\n        yield event.plain_result("⚔️ 你正在战斗中！输入『攻击』/『技能 <名称>』继续战斗，『防御』『逃跑』『用药』可选——先解决眼前的敌人再说移动。")\n        return\n    dest = dest.strip()\n    # v104 P1(M22)：空参数『前往』/『移动』不再静默移动——"" 是任意非空串的子串，\n    # 此前会命中 area_name 首个非空地图静默跨图并扣体力，直接提示输入目标\n    if not dest:\n        yield event.plain_result("前往哪？输入『地图』查看～")\n        return\n    # v94 体力：同图子区域移动免费（城内溜达不算赶路）；跨图移动扣 1、体力不足拒绝\n    cur = player["cur_map"]\n    cur_map = _cat_space.MAP_BY_ID.get(cur, {})\n    cur_sas = cur_map.get("subareas") or []\n    # v86 子区域：『移动 <序号>』→ 同图可前往列表序号优先（v87.14 空间连接），再邻居地图序号\n    # v104 P3(M24) 确认：全角数字兼容——Python str.isdigit()/int() 原生接受全角 ０-９(U+FF10-FF19)，\n    # 『前往 １２』与『前往 12』等价（实测 2026-08-12：isdigit=True 且 int(\'１２\')==12，无需 normalize）。\n    # v115 网状：visible_links 用 _visible_sas 过滤（隐藏未揭示不可前往），与『地图』面板编号一致\n    _raw_links = _maps.subarea_links(cur, player.get("cur_subarea") or "")\n    _v_ids = {vs["id"] for vs in self._visible_sas(player, cur_map, group_id, qq_id)}\n    links = [lid for lid in _raw_links if lid in _v_ids]\n    if dest.isdigit():\n        idx = int(dest)\n        if 1 <= idx <= len(links):\n            sa_id = links[idx - 1]\n            sa = next((s for s in cur_sas if s["id"] == sa_id), None)\n            if sa is None:\n                yield event.plain_result("目标子区域不存在！输入『地图』查看～")\n                return\n            if sa["id"] == player.get("cur_subarea"):\n                yield event.plain_result(f"你已经在这里了({cur_map[\'name\']}·{sa[\'name\']})～")\n                return\n            db.update_player(group_id, qq_id, cur_subarea=sa["id"])\n            yield event.plain_result(self._subarea_arrive(player, cur_map, sa, group_id, qq_id))\n            return\n    # v86 子区域：『移动 <子区域名>』→ 同图子区域（免费切换）\n    if dest:\n        for sa in cur_sas:\n            if dest in (sa["name"], sa["id"]):\n                if sa["id"] == player.get("cur_subarea"):\n                    yield event.plain_result(f"你已经在这里了({cur_map[\'name\']}·{sa[\'name\']})～")\n                    return\n                # v87.14 空间连接：同图只能移动到相邻子区域\n                # v115：隐藏未揭示房不能直接前往（提示需先探索揭开）\n                from .travel import subarea_hidden_block\n                _hidden_txt = subarea_hidden_block(group_id, qq_id, cur, sa)\n                if _hidden_txt:\n                    yield event.plain_result(_hidden_txt)\n                    return\n                links2 = _maps.subarea_links(cur, player.get("cur_subarea") or "")\n                if sa["id"] not in links2:\n                    yield event.plain_result(self._move_blocked_msg(cur_map, player, sa))\n                    return\n                db.update_player(group_id, qq_id, cur_subarea=sa["id"])\n                yield event.plain_result(self._subarea_arrive(player, cur_map, sa, group_id, qq_id))\n                return\n    # 查找目标地图：优先序号（相对当前地图邻居列表），其次地图名/ID/旧区域别名\n    target = None\n    want_sa = None\n    if dest.isdigit():\n        neighbors = _cat_b143.MAP_CONNECTIONS.get(cur, [])\n        idx = int(dest)\n        offset = len(links)\n        # #263: 与地图显示口径一致——跨图连接只在出口子区域有效（v95.21 出城走城门铁律），\n        # 非出口子区域报错"可前往 N 处"此前无条件加邻居数（显示 1 处却报 5 处）\n        exit_sa_id = _maps.map_exit_subarea(cur)\n        at_exit = (not exit_sa_id) or (player.get("cur_subarea") == exit_sa_id)\n        if not at_exit:\n            neighbors = []\n        if offset + 1 <= idx <= offset + len(neighbors):\n            target, want_sa = self._conn_target(neighbors[idx - offset - 1])\n        else:\n            # #263 回归修复：不在出口子区域时序号命中邻居地图 → 引导去出口\n            # （此前清空 neighbors 后直接"序号无效"，丢了 v87.14 出城走城门的路线引导；\n            #   无效序号仍按实际可前往数量报错，保持 #263 口径一致）\n            if not at_exit and offset + 1 <= idx <= offset + len(_cat_b143.MAP_CONNECTIONS.get(cur, [])):\n                _exit_name = next((s["name"] for s in (cur_map.get("subareas") or []) if s["id"] == exit_sa_id), "出口")\n                _cur_sa_name = next((s["name"] for s in (cur_map.get("subareas") or []) if s["id"] == player.get("cur_subarea")), player.get("cur_subarea", ""))\n                yield event.plain_result(\n                    f"🧭 你身处【{_cur_sa_name}】，还不能离开{cur_map.get(\'name\', \'此地\')}——"\n                    f"需要先到{_exit_name}(『前往 {_exit_name}』)才能出城/出图。"\n                )\n                return\n            total = len(links) + len(neighbors)\n            yield event.plain_result(f"序号无效！这里可前往 {total} 处，输入『地图』查看～")\n            return\n    else:\n        from .travel import resolve_map_target\n        target = resolve_map_target(dest)\n    if not target:\n        names = "、".join([m["name"] for m in _cat_space.MAPS])\n        yield event.plain_result(f"找不到『{dest}』！输入『地图』查看可前往区域，或『传送 <名称>』用方碑快速旅行～")\n        return\n    # 隐藏图检查\n    from .travel import hidden_map_block\n    _hid_block = hidden_map_block(group_id, qq_id, player, target)\n    if _hid_block:\n        yield event.plain_result(_hid_block)\n        return\n    # 是否相邻\n    cur = player["cur_map"]\n    neighbors = _cat_b143.MAP_CONNECTIONS.get(cur, [])\n    nids = [c[0] if isinstance(c, tuple) else c for c in neighbors]\n    # v104 P1(M22)：目标==当前图（输入本图地图名/区域名）→ 提示已在，不再原地白走扣体力\n    # （同图子区域名分支 :676-678 已有同款提示，跨图路径此前漏了）\n    if target["id"] == cur:\n        yield event.plain_result(f"你已经在这里了！(当前：{cur_map.get(\'name\', \'此地\')})")\n        return\n    if target["id"] != cur and target["id"] not in nids:\n        yield event.plain_result(f"无法直接前往{target[\'name\']}！需要先到相邻地图。看看『地图』～")\n        return\n    # v84 红名限制（26 章三 第一档）：红名不能进入城镇安全区（\'城镇外郊\' 数据不存在，v102.1 清理）\n    if self._is_redname(qq_id) and target.get("type") == _cat_core.MAP_TYPE_TOWN:\n        yield event.plain_result(\n            "🛡️ 城门口的守卫拦住了你：\\"你身上沾着血腥味！红名期间禁止进入城镇！\\"\\n"\n            "(红名期间不能进入安全区，去野外避避风头吧)")\n        return\n    # 等级提示\n    from .travel import level_warn\n    lv_msg = level_warn(player, target)\n    # v87.14 出图必须在该图出口子区域（城镇=城门，野外=入口）\n    from .travel import leave_map_block_msg\n    _leave_block = leave_map_block_msg(cur_map, player)\n    if _leave_block:\n        yield event.plain_result(_leave_block)\n        return\n    # q1-B 副本图门禁：副本图（type=副本）不可徒步直入（终局副本旁路修复）——\n    # 需已接取对应 explore 主线/支线任务、或持有副本钥匙、或已通关该副本才能进入。\n    _inst_gate = self._instance_gate_block(player, group_id, qq_id, target)\n    if _inst_gate:\n        yield event.plain_result(_inst_gate)\n        return\n    # v137 副本地图化：副本内移动（已开本 + 在副本图内）——队长带队、房间连通、\n    # discovery_agro 遇怪、Boss 房 Boss 战。目标房间名/序号解析与野外同款，\n    # 但只在本图连通表内移动（no_exit 无出口，不连野外）。\n    # 注意：_instance_move_route 已在 move 顶部先行路由（副本地图模式持有战斗锁，\n    # _in_battle 全局拦截在前）；此处副本分支保留以兼容直接调用/后续路径。\n    inst_row = self._instance_battle_for(group_id, qq_id)\n    if inst_row and inst_row["state"].get("inst_id") == target["id"] \\\n            and (inst_row["state"].get("mode") == "map" or inst_row["state"].get("rooms")):\n        # v141 审计 #8：_instance_dungeon_move 去掉 target 死参数——地图目标\n        # 在函数内按 inst_id 解析（大陆实例优先），此处只透传玩家原始 dest\n        async for _r in self._instance_dungeon_move(event, group_id, qq_id, player, inst_row, dest):\n            yield _r\n        return\n    # v86 子区域：跨图移动 → 落点：城镇=城门，野外=入口（v87.14）\n    from .travel import landing_subarea\n    first_sa = landing_subarea(target, want_sa)\n    # v94 体力：跨图移动扣 1；体力 0 拒绝（同图移动免费已在上方处理）；v101.13 坐骑 stamina_reduce 概率免费\n    if self._stamina(player) < 1:\n        from .travel import stamina_tired_line\n        yield event.plain_result(stamina_tired_line(player))\n        return\n    from .travel import move_stamina_cost\n    _mv_cost = move_stamina_cost(player)\n    if _mv_cost > 0:\n        self._spend_stamina(group_id, qq_id, _mv_cost, player, "移动")\n    db.update_player(group_id, qq_id, cur_map=target["id"],\n                     cur_subarea=first_sa["id"] if first_sa else "")\n    # 记录到访（称号用）\n    db.add_visited(group_id, qq_id, target["id"])\n    # 阶段九：到访成就判定（14 章 2.4 探索成就）\n    _ach.check_achievements(group_id, qq_id, self._player(group_id, qq_id))\n    # 探索型任务触发（到达目标子区域自动完成）\n    quest_lines = self._update_explore_quests(group_id, qq_id, target["id"])\n    extra = ""\n    if quest_lines:\n        extra = "\\n\\n" + "\\n".join(quest_lines)\n    # 旅者方碑提示（未激活时）\n    from .travel import portal_arrive_note\n    portal_msg = portal_arrive_note(group_id, qq_id, target)\n    # v13：到达后显示可前往 + 设施/场景（v87.13 拆分）\n    # v87.16 与地图面板一致：links 顺序号 + 邻居从 len(links)+1 编号\n    target_sas = target.get("subareas") or []\n    t_links = _maps.subarea_links(target["id"], first_sa["id"] if first_sa else "")\n    t_shown = [(i + 1, next((s for s in target_sas if s["id"] == lid), None))\n               for i, lid in enumerate(t_links)]\n    t_shown = [(i, s) for i, s in t_shown if s]\n    neighbors = _cat_b143.MAP_CONNECTIONS.get(target["id"], [])\n    nav = ""\n    # v101.25c 模板统一后：完整"可前往"列表已由 _subarea_body 输出，\n    # 此处不再拼紧凑版（否则跨图移动出现两行重复列表，playtest #405）\n    # v128 赶路模式提示统一由 _subarea_arrive 输出（回复 0 结束），此处不再重复。\n    # v132：fac_msg/scene_msg 死代码已删（v101.25c 起跨图移动走 _subarea_arrive，\n    # 此处拼装从未被消费；_map_scene 改返回 (poi, prop) 后旧 join 会直接崩）\n    # v49 意见#4：移动撞怪（生物趋避利害——低级闯高级区容易撞怪，高级玩家威慑低级区）\n    ambush = self._travel_ambush(player, target, group_id, qq_id)\n    # v101.25c 模板统一：跨图移动也走 _subarea_arrive 完整模板（NPC/可互动/设施/场景/可前往）\n    # 此前跨图是另一套精简拼接（fac_msg/scene_msg/nav），鱼鱼抓"前往不同区域提示模板不一样"\n    if ambush:\n        # v2 多对多：撞怪经 build_monster_group 生成敌方阵列（单只即可，伏击不引入随机双怪）\n        # N5b4-6：撞怪开战 saintess_engine 化（同 _open_battle 仪式，跨图伏击 = 普通战斗形态）\n        _grp = _drops().build_monster_group(ambush, target, player)\n        _open2 = getattr(self, "_open_battle", None)\n        if _open2 is not None:\n            _nb = _open2(player, _grp, "monster", group_id=group_id, qq_id=qq_id)\n        else:\n            from . import bridge as BR\n            BR.prepare_player_for_battle(player, self._title_bonus(group_id, qq_id), db)\n            _sides = BR.build_sides(player=player, enemies=_grp)\n            from saintess_engine import Battle as B2\n            _nb = B2("monster", sides=_sides,\n                     title_bonus=self._title_bonus(group_id, qq_id),\n                     pet=db.pet_get(qq_id))\n        db.save_battle(group_id, qq_id, _nb.to_state())\n        self._lock_battle(group_id, qq_id)\n        arrive_txt = f"🚶 你来到了【{target[\'name\']}】"\n        if target.get("type") == _cat_core.MAP_TYPE_TOWN and first_sa:\n            arrive_txt = f"🚶 你从野外方向来到了【{target[\'name\']}】{first_sa[\'name\']}"\n        # 我方站位单机 = 玩家单位\n        _cls = _cat_core.CLASSES.get(player.get("class_name", ""), {}) or {}\n        _self_unit = {\n            "uid": "p_self", "rank": int(_cls.get("default_rank", 2) or 2),\n            "reach": int(_cls.get("reach", 2) or 2), "name": player.get("name", "你"),\n            "hp": player.get("hp", 0), "max_hp": player.get("max_hp", 0),\n        }\n        _enemy_rows = formation_view(alive_units(_grp), side="enemy")\n        _ally_rows = formation_view(alive_units([_self_unit]), side="ally")\n        yield event.plain_result(\n            f"{arrive_txt}\\n{(first_sa.get(\'desc\') if first_sa else \'\') or target.get(\'desc\', \'\')}{lv_msg}{extra}{portal_msg}\\n"\n            f"━━━━━━━━━━━━\\n"\n            f"🛡️ 还没站稳，{ambush[\'name\']} 就拦住了去路！\\n"\n            f"── 敌方 ──\\n" + "\\n".join(_enemy_rows) + "\\n── 我方 ──\\n" + "\\n".join(_ally_rows) + "\\n"\n            f"🐾【{ambush[\'name\']}】Lv.{ambush[\'lv\']} ❤️ {ambush[\'hp\']}/{ambush[\'max_hp\']}\\n"\n            f"━━━━━━━━━━━━\\n"\n            f"你的行动：『攻击』『技能 <名称>』『防御』『逃跑』"\n        )\n        return\n    # v87.3 必经之路：进入城镇时提示方向（从路图/野外进城）\n    arrive_txt = f"🚶 你来到了【{target[\'name\']}】"\n    if target.get("type") == _cat_core.MAP_TYPE_TOWN and first_sa:\n        arrive_txt = f"🚶 你从野外方向来到了【{target[\'name\']}】{first_sa[\'name\']}"\n    # v97.5 行为彩蛋规则：进入新地图\n    _rule_txt = self._rule_fire("move_enter", group_id, qq_id, player, target)\n    arrive_view = self._subarea_arrive(player, target, first_sa, group_id, qq_id) if first_sa else \\\n        f"🚶 你来到了【{target[\'name\']}】\\n{target.get(\'desc\', \'\')}"\n    # 跨图特有信息插在主体前（等级提示/任务/方碑）\n    _head_extra = f"{lv_msg}{extra}{portal_msg}"\n    yield event.plain_result(\n        f"{arrive_view}{_head_extra}"\n        + (f"\\n{_rule_txt}" if _rule_txt else "")\n    )\n',
    'content/world_cmds.py::time_cmd': 'async def time_cmd(self, event: AstrMessageEvent, group_id, qq_id, player):\n    cur = player["cur_map"]\n    summary = _tw.time_weather_summary(cur)\n    cur_map = _cat_space.MAP_BY_ID.get(cur, {})\n    lines = [\n        "🕰️ 【时间】",\n        f"⏰ {summary}",\n        f"📍 你在【{cur_map.get(\'name\', \'未知区域\')}】",\n        "━━━━━━━━━━━━",\n    ]\n    hints = _wild.nearby_hints(group_id, qq_id, player, cur)\n    if hints:\n        lines.append("🍃 附近似乎有人影出没：")\n        for nid, npc in hints[:5]:\n            lines.append(f"  {npc[\'icon\']}{npc[\'name\']}({self._wild_cond_label(npc)})")\n        lines.append(self._tip("explore"))\n    else:\n        lines.append("🍃 附近没有特别的气息……")\n    yield event.plain_result("\\n".join(lines))\n',
    'content/world_cmds.py::wild_notes': 'async def wild_notes(self, event: AstrMessageEvent, group_id, qq_id, player):\n    met = _wild.met_wild(group_id, qq_id)\n    if not met:\n        yield event.plain_result(\n            "📖 【见闻录】还是空白的……\\n"\n            "去野外走走，那些藏在角落里的旅人、隐士、夜行者，都在等着被遇见。"\n        )\n        return\n    lines = [f"📖 【见闻录】你见过的人({len(met)}/{len(_wild.ALL_WILD)})：", "━━━━━━━━━━━━"]\n    for nid in met:\n        npc = _wild.ALL_WILD.get(nid)\n        if not npc:\n            continue\n        lines.append(f"{npc[\'icon\']}{npc[\'name\']}")\n        lines.append(f"\u3000\u3000{npc[\'desc\']}")\n        lines.append(f"\u3000\u3000🕐 {self._wild_cond_label(npc)}")\n    lines.append("💡 集齐见闻是冒险者的浪漫——见过的人会记住你。")\n    yield event.plain_result("\\n".join(lines))\n',
    'content/world_cmds.py::turn_in': 'async def turn_in(self, event: AstrMessageEvent, group_id, qq_id, player):\n    quests = db.get_quests(group_id, qq_id)\n    # v101.27 #341：夜晚 NPC 不在场不能隔空交付——用官方出现条件判定\n    # （base_conditions_met 覆盖 period/condition.time/season/weather 等全部条件，\n    # 采药女·小荨 condition.time=[\'morning\',\'day\'] 夜晚交付实锤）\n    def _npc_absent(npc_id, npc):\n        if not npc:\n            return None\n        if not _wild.base_conditions_met(npc_id, npc, player, group_id, qq_id):\n            period_cn = (PERIOD_CN.get(_tw.current_period(), "") or "").strip()\n            return f"🌙 {npc.get(\'name\', \'他\')}现在({period_cn})不在这里，换个时间再来交付吧～"\n        return None\n    # 主线可交\n    main_id = quests.get("main_quest")\n    st = quests.get("main_status", "pending")\n    if main_id and st == "ready":\n        mq = next((q for q in _cat_quests.MAIN_QUESTS if q["id"] == main_id), None)\n        if mq:\n            npc = _cat_quests.NPCS.get(mq["giver"])\n            if npc and npc["map"] == player["cur_map"]:\n                absent = _npc_absent(mq["giver"], npc)\n                if absent:\n                    yield event.plain_result(absent)\n                    return\n                lines = self._take_main_quest(group_id, qq_id, mq["giver"], npc)\n                yield event.plain_result("\\n".join(lines))\n                return\n            else:\n                giver = _cat_quests.NPCS.get(mq["giver"], {}).get("name", "？")\n                giver_map = _cat_quests.NPCS.get(mq["giver"], {}).get("map", "")\n                yield event.plain_result(f"你需要到 {_cat_space.MAP_BY_ID.get(giver_map, {}).get(\'name\', \'？\')} 找 {giver} 交付任务！")\n                return\n    # 支线可交\n    # O100 修复：『交付任务』按当前 NPC/地图过滤——此前遍历 dict 顺序取第一个 ready\n    # 支线，在城主处可能先命中"护送商货(需找老赵)"而忽略当场可交的"码头的猫"。\n    # 现逻辑：① 当前地图有交付 NPC → 当场交付（过滤优先）；② 无当场可交但别处有\n    # ready 支线 → 一次性列出全部可交付任务与位置（不再只报第一条误导玩家）。\n    collect_missing = None  # 收集型材料还差的信息（用于最后提示）\n    waiting = []  # O100：已达成但交付 NPC 不在当前地图的支线 [(任务名, NPC名, 地图名)]\n    for sid, sq in list(quests.get("side", {}).items()):\n        sqd = next((q for q in _cat_quests.SIDE_QUESTS if q["id"] == sid), None)\n        if not sqd:\n            continue\n        if sq.get("status") == "done":  # v95.12：已交付支线不重复接取/交付\n            continue\n        npc = _cat_quests.NPCS.get(sqd["giver"]) or _wild.ALL_WILD.get(sqd["giver"]) or _cat_quests.HIDDEN_NPCS.get(sqd["giver"])  # R3 P1-4：副本内 NPC（潮汐祭司）交付解析\n        obj = sqd["objective"]\n        # 收集型：实时检查背包材料（不依赖 ready 状态）\n        if obj.get("collect"):\n            # v104 审计 P1-3：复合目标（魔剑士试炼 collect_count=2/count=3）门槛统一按\n            # collect_count 判定（此前用 obj["count"]=3 与 quest_view 的 2 不一致：\n            # 面板显示"✅ 可交"、交付却拒"还差 ×1(背包 2/3)"）\n            need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 不再 KeyError\n            have = db.count_item(group_id, qq_id, obj["collect"])\n            if have >= need:\n                if npc and npc["map"] == player["cur_map"]:\n                    absent = _npc_absent(sqd["giver"], npc)\n                    if absent:\n                        yield event.plain_result(absent)\n                        return\n                    lines = self._complete_side_quest(group_id, qq_id, sid)\n                    yield event.plain_result("\\n".join(lines))\n                    return\n                else:\n                    giver = (_cat_quests.NPCS.get(sqd["giver"]) or _wild.ALL_WILD.get(sqd["giver"]) or _cat_quests.HIDDEN_NPCS.get(sqd["giver"]) or {}).get("name", "？")  # R3 P1-4\n                    giver_map = _cat_space.MAP_BY_ID.get((_cat_quests.NPCS.get(sqd["giver"]) or _wild.ALL_WILD.get(sqd["giver"]) or _cat_quests.HIDDEN_NPCS.get(sqd["giver"]) or {}).get("map", ""), {}).get("name", "？")\n                    waiting.append((sqd["name"], giver, giver_map))\n            else:\n                collect_missing = (sqd["name"], obj["collect"], have, need)\n            continue\n        # 击杀/探索型：按 ready 状态\n        if sq.get("status") == "ready":\n            # v124 分支任务：输出选项等待玩家回复（不自动完成）\n            if sqd.get("branch") and not sq.get("branch_wait"):\n                lines = self._complete_side_quest(group_id, qq_id, sid)\n                yield event.plain_result("\\n".join(lines))\n                return\n            if npc and npc["map"] == player["cur_map"]:\n                absent = _npc_absent(sqd["giver"], npc)\n                if absent:\n                    yield event.plain_result(absent)\n                    return\n                lines = self._complete_side_quest(group_id, qq_id, sid)\n                yield event.plain_result("\\n".join(lines))\n                return\n            else:\n                giver = (_cat_quests.NPCS.get(sqd["giver"]) or _wild.ALL_WILD.get(sqd["giver"]) or _cat_quests.HIDDEN_NPCS.get(sqd["giver"]) or {}).get("name", "？")  # R3 P1-4\n                giver_map = _cat_space.MAP_BY_ID.get((_cat_quests.NPCS.get(sqd["giver"]) or _wild.ALL_WILD.get(sqd["giver"]) or _cat_quests.HIDDEN_NPCS.get(sqd["giver"]) or {}).get("map", ""), {}).get("name", "？")\n                waiting.append((sqd["name"], giver, giver_map))\n    # O100：无当场可交付时，列出全部"已达成待交付"任务（带位置），不再只报第一条\n    if waiting:\n        lines = ["📜 可交付任务："]\n        for i, (qname, giver, giver_map) in enumerate(waiting, 1):\n            lines.append(f"{i:>2}. 『{qname}』→ 找 {giver}(在{giver_map})")\n        lines.append(self._tip("quest_deliver"))\n        yield event.plain_result("\\n".join(lines))\n        return\n    if collect_missing:\n        name, mat, have, need = collect_missing\n        yield event.plain_result(f"支线『{name}』还差 {mat} ×{need - have}(背包 {have}/{need})！")\n        return\n    yield event.plain_result("没有可交的任务。输入『任务』查看进度～")\n',
    'content/world_cmds.py::_grant_wild_unlock_flags': 'def _grant_wild_unlock_flags(self, group_id, qq_id, npc_id):\n    """v104 P1（M21 隐藏 NPC 永久锁死修复）：与特定野外 NPC 交谈 → 授予隐藏 NPC 解锁 flag。\n\n    v124.3（审计）：解锁链数据化——配置读 NPC 数据的 unlock_flags 字段\n    （{"flag": "heard_owl_song", "notice": "…"}，见 wild_npcs.py 说书人·巴尔/\n    流浪诗人·弦歌/老兵之魂），新增解锁型 NPC = 纯数据操作（加字段即可），\n    本函数零改动。flag 存任意 NPC 桶即可，unlock_met 已改全桶扫描。\n    返回首次授予的提示行；无授予返回 None。\n    """\n    npc = (_wild.ALL_WILD or {}).get(npc_id)\n    if not isinstance(npc, dict):\n        return None\n    cfg = npc.get("unlock_flags") or {}\n    flag = cfg.get("flag", "")\n    if not flag:\n        return None\n    if flag in db.get_talk_flags(group_id, qq_id, npc_id):\n        return None\n    db.set_talk_flag(group_id, qq_id, npc_id, flag)\n    return cfg.get("notice", "")\n',
    'content/world_cmds.py::_teach_by_npc': 'def _teach_by_npc(self, group_id, qq_id, player, npc_id):\n    """v104 P2（M21）teach 空挂修复：无对话树的教习型 NPC（龙语者·古尔/上古守卫者/墓王·静语）\n    按职业传授对应技能。参照对话树 tutor_skill 写法：等级门槛 + 金币学费 → 直接学会（不耗技能点）。\n    返回提示行列表；NPC 不在映射表时返回空列表（保持原行为）。\n    v112：配置读 NPC 数据（teach_skills/teach_hint），无配置返回空列表。\n    """\n    npc = (_wild.ALL_WILD or {}).get(npc_id, {})\n    if not isinstance(npc, dict):\n        npc = {}\n    cfg_skills = npc.get("teach_skills") or {}\n    hint = npc.get("teach_hint") or ""\n    if not cfg_skills:\n        return []\n    cid = _idx.resolve("classes", player.get("class_name", ""))\n    sname = cfg_skills.get(cid)\n    if not sname:\n        return [f"{hint}他打量了你片刻，摇了摇头：你这身本事，不在我能指点的路数上。"]\n    info = skill_info(player.get("class_name", ""), sname)\n    if not info:\n        return []\n    sname_cn = info.get("name", sname)\n    need_lv = int(info.get("lv", 1))\n    cost = max(500, need_lv * 100)\n    if player.get("level", 0) < need_lv:\n        return [f"{hint}这套本事要 Lv.{need_lv} 才学得动，你才 Lv.{player.get(\'level\', 1)}，先练练基本功。"]\n    if (player.get("gold", 0) or 0) < cost:\n        return [f"{hint}想学？拿 {cost} 金币来，一分诚意一分本事。(你现在有 {player.get(\'gold\', 0)} 金币)"]\n    learned = list(player.get("learned_skills", []))\n    if _idx.resolve("skills", sname) in [_idx.resolve("skills", s) for s in learned if s]:\n        return [f"{hint}『{sname_cn}』你早已掌握，不必再学。"]\n    db.update_player(group_id, qq_id, gold=(player.get("gold", 0) or 0) - cost,\n                     learned_skills=learned + [sname_cn])\n    return [\n        f"{hint}",\n        f"💰 你献上 {cost} 金币作为谢礼",\n        f"✨ 前辈悉心传授，你学会了技能『{sname_cn}』！",\n        f"「{info[\'desc\']}」",\n        self._tip("skill_set"),\n    ]\n',
    'content/world_cmds.py::_map_blocks': 'def _map_blocks(self, player: dict, cur_map: dict, cur_sa: str,\n                group_id=None, qq_id=None) -> list:\n    """v132 从 map_view 抽取：位置导航之外的完整区块（今日奇遇/设施/场景/NPC/旅人/玩家/怪物/tip）。\n\n    『地图』与 `_subarea_arrive`（到达视图）共用此方法 → 两处排版永不分裂\n    （v101.25c 铁律：鱼鱼抓"前往不同区域提示模板不一样"）。\n    cur_sa 传 sa id：到达视图时 player.cur_subarea 尚未更新为落点（v87.13b 同源处理）。\n    """\n    lines = []\n    cur = cur_map.get("id", "")\n    sas = cur_map.get("subareas") or []\n    # v132.2 全地图紧凑模式（鱼鱼拍板：地图排版统一 ●横排模板，不再区分城镇/野外）\n    _compact = True\n    # v115 今日奇遇：面板底部一行（getattr 兜底，A/C 未就绪则不显示）\n    _today_ev_fn = getattr(_daily_events, "today_map_event", None)\n    if _today_ev_fn is not None:\n        try:\n            _ev = _today_ev_fn(cur)\n            if _ev and _ev.get("name"):\n                _ev_fx = (_ev.get("effects") or {})\n                _ev_note = ""\n                if _ev_fx.get("encounter_rate", 0) > 0:\n                    _ev_note = "(遇怪率↑)"\n                elif _ev_fx.get("event_chance", 0) > 0:\n                    _ev_note = "(事件率↑)"\n                elif _ev_fx.get("loot_mult", 1.0) > 1.0:\n                    _ev_note = f"(掉落×{_ev_fx.get(\'loot_mult\', 1.0)})"\n                lines.append(f"🌤 今日奇遇：{_ev[\'name\']}——{_ev.get(\'desc\', \'\')}{_ev_note}")\n        except Exception:\n            pass\n    # v87.4 区块间统一空行分隔（不再叠分隔线）\n    if lines and lines[-1]:\n        lines.append("")\n    # 此地设施 + 场景（v87.13 拆分：设施=功能入口，场景=氛围景物）\n    fac = self._map_facilities(cur_map, player, cur_sa)\n    if fac:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("🏪 此地设施：")\n        if _compact:\n            lines.append("  ●" + " ●".join(fac))\n        else:\n            for l in fac:\n                lines.append(f"  {l}")\n    # v132 场景两区：🔎 可探索触发（POI/调查）+ ✨ 可交互场景（PROPS）\n    poi_lines, prop_lines = self._map_scene(cur_map, player, cur_sa)\n    if poi_lines:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("🔎 可探索触发：")\n        if _compact:\n            names = []\n            for l in poi_lines:\n                nm = l.split("(")[0].strip()\n                names.append(f"●{nm}")\n            lines.append("  " + " ".join(names))\n        else:\n            for l in poi_lines:\n                lines.append(f"  {l}")\n    if prop_lines:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("✨ 可交互场景：")\n        if _compact:\n            names = [f"●{i}. {l.split(\'(\')[0].strip()}" for i, l in enumerate(prop_lines, 1)]\n            lines.append("  " + " ".join(names))\n        else:\n            for l in prop_lines:\n                lines.append(f"  {l}")\n    # 本地 NPC\n    # v86 子区域：NPC 按当前子区域显示（无子区域则地图级）\n    cur_sa_obj = None\n    if cur_sa:\n        for _sa in sas:\n            if _sa["id"] == cur_sa:\n                cur_sa_obj = _sa\n                break\n    npc_ids = (cur_sa_obj.get("npcs") if cur_sa_obj else None) or cur_map.get("npcs", [])\n    if cur_map.get("inline_npcs"):\n        npc_ids = cur_map["inline_npcs"]\n    npcs = []\n    for nid in npc_ids:\n        if nid in _cat_quests.HIDDEN_NPCS:\n            npcs.append((nid, _cat_quests.HIDDEN_NPCS[nid]))\n        elif nid in _cat_quests.NPCS:\n            npcs.append((nid, _cat_quests.NPCS[nid]))\n    # v95.30 城镇 NPC 随机性：酱油 NPC 按 游走(roam)/概率(appear)/时段(period) 过滤显示\n    # （功能 NPC 恒显示；隐藏 NPC 走副本层逻辑不参与；无子区域(地图级)不做过滤）\n    npcs = [(nid, n) for nid, n in npcs\n            if nid in _cat_quests.HIDDEN_NPCS or not cur_sa or _wild.town_npc_visible(nid, n, cur_sa)]\n    if npcs:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("👥 这里的 NPC：")\n        if _compact:\n            # 城镇紧凑：●1. 名 ●2. 名（无头衔，鱼鱼模板）\n            _parts = [f"●{i}. {n[\'icon\']}{n[\'name\']}" for i, (_, n) in enumerate(npcs, 1)]\n            lines.append("  " + " ".join(_parts))\n        else:\n            for i, (_, n) in enumerate(npcs, 1):\n                lines.append(f"  {i:>2}. {n[\'icon\']}{n[\'name\']}({n[\'title\']})")\n            lines.append(f"  {self._tip(\'talk\')}")\n    # v127.5 限时NPC：在场野外旅人（偶遇进入限时状态，带 ⏳ 剩余分钟，全图可见）\n    # v127.5.1 不重复加 _tip(\'talk\')——对上城镇 NPC 区已有同分类提示（AST 防重铁律）\n    wild_lines = self._present_wild_hints(group_id, qq_id, cur) if group_id is not None and qq_id is not None else []\n    if wild_lines:\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("🧭 游历的旅人：")\n        lines.extend(wild_lines)\n    # v66 此地玩家（含摆摊标记；v132 加编号，鱼鱼新排版）\n    # v134 #33：无其他玩家时不显示本段（连标题行一并省略，不留空行）\n    # v134.1 #46：排除自己——"只有玩家一个人时"不再显示『👤 此地的玩家：●1. 自己』\n    here_players = [p for p in db.get_group_players(group_id).values()\n                    if p.get("cur_map") == cur and str(p.get("qq_id")) != str(qq_id)]\n    if here_players:\n        stall_sellers = {str(s["seller"]) for s in db.market_list(group_id, cur)}\n        if lines and lines[-1]:\n            lines.append("")\n        lines.append("👤 此地的玩家：")\n        if _compact:\n            # 城镇紧凑：●1. 名 Lv.X ●2. 名 Lv.X（鱼鱼模板；摆摊标记保留——功能状态）\n            _parts = [f"●{i}. {p[\'name\']} Lv.{p[\'level\']}"\n                      + (" 🏪摆摊中" if str(p.get("qq_id")) in stall_sellers else "")\n                      for i, p in enumerate(here_players, 1)]\n            lines.append("  " + " ".join(_parts))\n        else:\n            for i, p in enumerate(here_players, 1):\n                stall_mark = " 🏪摆摊中" if str(p.get("qq_id")) in stall_sellers else ""\n                lines.append(f"  {i}. {p[\'name\']} Lv.{p[\'level\']}{stall_mark}")\n    # v86 子区域：怪物按当前子区域（无则回退地图级）\n    mons = (cur_sa_obj.get("monsters") if cur_sa_obj else None)\n    if mons is None:\n        mons = cur_map.get("monsters", [])\n    # 精英/Boss（子区域优先）——先取值供去重判断与字段展示\n    elite = (cur_sa_obj.get("elite") if cur_sa_obj else None) or cur_map.get("elite")\n    boss = (cur_sa_obj.get("boss") if cur_sa_obj else None) or cur_map.get("boss")\n    if mons:\n        if lines and lines[-1]:\n            lines.append("")\n        # v101.25 #289：标题等级改用怪物实际 min-max——此前用子区域 lv+2 推断，\n        # 与怪物真实等级差 2 级误导（round66 银风道口标 Lv.6-8 实际野狗 Lv.3）\n        _mlvs = [lv for _m, _n, _r, lv, _s, _d in mons if lv]\n        if _mlvs:\n            _lo, _hi = min(_mlvs), max(_mlvs)\n            lv_label = f"Lv.{_lo}" if _lo == _hi else f"Lv.{_lo}-{_hi}"\n        else:\n            base_lv = (cur_sa_obj.get("lv") if cur_sa_obj else None) or cur_map["lv"]\n            lv_label = f"Lv.{base_lv}"\n        lines.append(f"🐾 此地的怪物 ({lv_label})：")\n        for mid, name, role, lv, skills, drops in mons:\n            # v95r38 去重：池子条目与 elite/boss 字段重复时不重复显示（字段行会展示）\n            if role == "elite" and elite and elite[0] == mid:\n                continue\n            if role == "boss" and boss and boss[0] == mid:\n                continue\n            mark = "👑" if role == "boss" else ("⭐" if role == "elite" else "")\n            # v132 等级波动明示：普通怪 ±1（精英/Boss 不参与波动，不标注）\n            jitter = "±1" if role not in ("elite", "boss") else ""\n            lines.append(f"  {mark}{name} Lv.{lv}{jitter}")\n    if elite:\n        lines.append(f"  ⭐ 精英：{elite[1]}")\n    if boss:\n        lines.append(f"  👑 Boss：{boss[1]}")\n    if lines and lines[-1]:\n        lines.append("")\n    lines.append(self._tip("map"))\n    return lines\n',
    'content/world_cmds.py::_hurry_section': 'def _hurry_section(self, player: dict, cur_map: dict, cur_sa: str,\n                   group_id, qq_id, ftype: str) -> list:\n    """v128.1 类型过滤区（NPC/怪物/场景/设施）——赶路面板与移动落点过滤共用。\n\n    返回 lines 列表（未 join）；无内容给"没有XX"提示行，保证赶路语境一致。\n    """\n    lines = []\n    sas = cur_map.get("subareas") or []\n    cur_sa_obj = None\n    for _sa in sas:\n        if _sa["id"] == cur_sa:\n            cur_sa_obj = _sa\n            break\n    if ftype == "npc":\n        npc_ids = (cur_sa_obj.get("npcs") if cur_sa_obj else None) or cur_map.get("npcs", [])\n        if cur_map.get("inline_npcs"):\n            npc_ids = cur_map["inline_npcs"]\n        npcs = []\n        for nid in npc_ids:\n            if nid in _cat_quests.HIDDEN_NPCS:\n                npcs.append((nid, _cat_quests.HIDDEN_NPCS[nid]))\n            elif nid in _cat_quests.NPCS:\n                npcs.append((nid, _cat_quests.NPCS[nid]))\n        npcs = [(nid, n) for nid, n in npcs\n                if nid in _cat_quests.HIDDEN_NPCS or not cur_sa or _wild.town_npc_visible(nid, n, cur_sa)]\n        if npcs:\n            lines.append("👥 这里的 NPC：")\n            for i, (_, n) in enumerate(npcs, 1):\n                lines.append(f"  {i:>2}. {n[\'icon\']}{n[\'name\']}({n[\'title\']})")\n        else:\n            lines.append("👥 这里附近没有可交谈的 NPC ～")\n    elif ftype == "monster":\n        mons = (cur_sa_obj.get("monsters") if cur_sa_obj else None)\n        if mons is None:\n            mons = cur_map.get("monsters", [])\n        elite = (cur_sa_obj.get("elite") if cur_sa_obj else None) or cur_map.get("elite")\n        boss = (cur_sa_obj.get("boss") if cur_sa_obj else None) or cur_map.get("boss")\n        if mons:\n            _mlvs = [lv for _m, _n, _r, lv, _s, _d in mons if lv]\n            if _mlvs:\n                _lo, _hi = min(_mlvs), max(_mlvs)\n                lv_label = f"Lv.{_lo}" if _lo == _hi else f"Lv.{_lo}-{_hi}"\n            else:\n                base_lv = (cur_sa_obj.get("lv") if cur_sa_obj else None) or cur_map["lv"]\n                lv_label = f"Lv.{base_lv}"\n            lines.append(f"🐾 此地的怪物 ({lv_label})：")\n            for mid, name, role, lv, skills, drops in mons:\n                if role == "elite" and elite and elite[0] == mid:\n                    continue\n                if role == "boss" and boss and boss[0] == mid:\n                    continue\n                mark = "👑" if role == "boss" else ("⭐" if role == "elite" else "")\n                lines.append(f"  {mark}{name} Lv.{lv}")\n        if elite:\n            lines.append(f"  ⭐ 精英：{elite[1]}")\n        if boss:\n            lines.append(f"  👑 Boss：{boss[1]}")\n        if not mons and not elite and not boss:\n            lines.append("🐾 这里没什么怪物，比较安全～")\n    elif ftype == "scene":\n        scene = self._map_scene(cur_map, player, cur_sa)\n        if scene:\n            lines.append("✨ 场景：")\n            for l in scene:\n                lines.append(f"  {l}")\n        else:\n            lines.append("✨ 这里没什么特别的场景～")\n    elif ftype == "facility":\n        fac = self._map_facilities(cur_map, player, cur_sa)\n        if fac:\n            lines.append("🏪 此地设施：")\n            for l in fac:\n                lines.append(f"  {l}")\n        else:\n            lines.append("🏪 这里没有商店/设施～")\n    return lines\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/world_cmds.py::_npc_dialogue': '3b69a0d7c1a114dcc097a38025160792ed5c9a5d3c351a368cf072a91e39ffdc',
        'content/world_cmds.py::_current_npcs': '7abc1fe193d17017edf3981096651dd1232c60813e0ea7cdda9ef6eff3c81e6a',
        'content/world_cmds.py::_present_wild_hints': '4ffdf11b8f8e88591f0b8b565c3e8524a5c19f147d9a00019594cc5031b3a303',
        'content/world_cmds.py::_start_talk_list': 'ae896c0baca4ad399de8719be51c08b1a3c70dae63bc300cc073d86726f70082',
        'content/world_cmds.py::_find_npc_in_map': '2022fd8f37f85789d196f8794b993f90809db551025cdcfb3b7473138c3c69d3',
        'content/world_cmds.py::_town_npc_absent_hint': '4cc4004260498e94271315ee3125b83dbaecee7fb24471997a09ef21a4c4e2aa',
        'content/world_cmds.py::_player_map_name': 'f716578d359827ea51e1ee9f32cfd6f1ec286e47c530ebf218aea0915544e91e',
        'content/world_cmds.py::_subarea_name': '4250943f42e65eee747ecab6aede8dfab04880085198bbcaf9a34d4e4c178a90',
        'content/world_cmds.py::_find_wild_npc': '1547f72725e15d2e0d7221ceba33951077de824fc564aaf7393db1ed1041ca7a',
        'content/world_cmds.py::_wild_unseen_hint': '229bc0f30467a9a6e131bd42f2ef03f5a398242ecfd8df0fb5306049423af9b3',
        'content/world_cmds.py::_npc_direction_hint': 'ac72a5c65db6f2b95fafd633d72f247438173174b372af5dd718dc53c7e03b99',
        'content/world_cmds.py::_wild_cond_label': 'bb68183bc60caec285e16eb6d0a78dcf959b5be3c59c9b72979a68170a969db2',
        'content/world_cmds.py::_talk_active': 'a58b89826c0a868e6c1336d44ec31e3f64f4a7f63a5b9f3f92e9cabe5233ffd2',
        'content/world_cmds.py::_talk_ctx': '830fcdd577ad841c402ab24f81f75a05bce67184808c871fcc4c36cdf898fae9',
        'content/world_cmds.py::_side_menu_expand': '315931d7f905d344260257f516e666a18c3290782052ee4949166a1317dba563',
        'content/world_cmds.py::_render_talk_node': '1845ed7d74e681366d72742c3bd1f517b799853b627cbf58cd5882eabc1b0d48',
        'content/world_cmds.py::_apply_talk_action_async': '5d112ddfde2e89557a474980dfe998af450e49c73fb4d72ef9b65077e258205b',
        'content/world_cmds.py::_apply_talk_action': '0e9f55287f28d2e08354d2ab539b0d44fa38e16bac38ed7e6b2a97a06ce576f8',
        'content/world_cmds.py::talk_choice': '3dd272614848e5ee448f41df9a0439a2003faf3297f3f1076aefdaa485cec7c6',
        'content/world_cmds.py::npc_quick_dialog': 'd2cea7fd1041323fe0822fba1b413094dfc49228c0558d03240e8ed7327fe129',
        'content/world_cmds.py::find_npc': 'afb1319343a37b7e8cb7b364d6aaf05d4771b303fa6c87d3c655e21ed0de3a4c',
        'content/world_cmds.py::move': 'c5e307ec7b424ccba7487bf7f3191aa672b44374498c06a27216726158b02fd1',
        'content/world_cmds.py::time_cmd': 'ecd979490d5019b349af04e3f2ac6526423cf7a0d32c35af7c1b6ede50302e39',
        'content/world_cmds.py::wild_notes': '99fddc5597f852dee3877e3b2ec9e3d0d0332d5b5c7ada99cf8a682ba87f4dcb',
        'content/world_cmds.py::turn_in': 'fcae401a25489b2bb19222c949e86a668d3d7068ecc3b35848bfc3cdd9980b3b',
        'content/world_cmds.py::_grant_wild_unlock_flags': '6df46a6ece624f86847309f5679539b5e8f7cafa4a8220595d2c7ca78ad8e591',
        'content/world_cmds.py::_teach_by_npc': 'c1d30c6e42918f3521637ebe51aa1c9cf4109fc4d59d7eebe2e8d8e82ae7bf54',
        'content/world_cmds.py::_map_blocks': '3b6e9a5a63a1d03338acbee0e9fcbb72980651615001a4195695d76f6b3c55c5',
        'content/world_cmds.py::_hurry_section': '7c29af49565217d3853e7efc9606b3f2155d9569c711cf8eef060e84fcae86fd',
    },
    'live': {
        'content/world_cmds.py::_npc_dialogue': '3b69a0d7c1a114dcc097a38025160792ed5c9a5d3c351a368cf072a91e39ffdc',
        'content/world_cmds.py::_current_npcs': '3db861c90b1bc8435a1dd7b8d4c0a426fe9312e4491c1092e340f400db1343c4',
        'content/world_cmds.py::_present_wild_hints': '5842eeb60d91e44f00a0f7939219b6d43a2105d1f4fd020001a42153a47649cd',
        'content/world_cmds.py::_start_talk_list': 'f689d88931d48265ff4c3c35e4c61da484be5d8d63b006ca764f6dc6bdc56b87',
        'content/world_cmds.py::_find_npc_in_map': 'ddd119fb7e1d4e4d2d1c499e01226983d9d32dd82ead20bc9cb41aca33697733',
        'content/world_cmds.py::_town_npc_absent_hint': '527b5705d3879566f07287655f4bce6be09e0dd260feeb6487e463b844bfccb9',
        'content/world_cmds.py::_player_map_name': 'f716578d359827ea51e1ee9f32cfd6f1ec286e47c530ebf218aea0915544e91e',
        'content/world_cmds.py::_subarea_name': '4250943f42e65eee747ecab6aede8dfab04880085198bbcaf9a34d4e4c178a90',
        'content/world_cmds.py::_find_wild_npc': '1547f72725e15d2e0d7221ceba33951077de824fc564aaf7393db1ed1041ca7a',
        'content/world_cmds.py::_wild_unseen_hint': '229bc0f30467a9a6e131bd42f2ef03f5a398242ecfd8df0fb5306049423af9b3',
        'content/world_cmds.py::_npc_direction_hint': 'ac72a5c65db6f2b95fafd633d72f247438173174b372af5dd718dc53c7e03b99',
        'content/world_cmds.py::_wild_cond_label': 'bb68183bc60caec285e16eb6d0a78dcf959b5be3c59c9b72979a68170a969db2',
        'content/world_cmds.py::_talk_active': 'a58b89826c0a868e6c1336d44ec31e3f64f4a7f63a5b9f3f92e9cabe5233ffd2',
        'content/world_cmds.py::_talk_ctx': '830fcdd577ad841c402ab24f81f75a05bce67184808c871fcc4c36cdf898fae9',
        'content/world_cmds.py::_side_menu_expand': '315931d7f905d344260257f516e666a18c3290782052ee4949166a1317dba563',
        'content/world_cmds.py::_render_talk_node': 'bc07dbdcf5bd2d4a960fe09a09b17b9ff4266f96a5da86657a79ba15f3a53e52',
        'content/world_cmds.py::_apply_talk_action_async': '5d112ddfde2e89557a474980dfe998af450e49c73fb4d72ef9b65077e258205b',
        'content/world_cmds.py::_apply_talk_action': '0e9f55287f28d2e08354d2ab539b0d44fa38e16bac38ed7e6b2a97a06ce576f8',
        'content/world_cmds.py::talk_choice': 'aed0593592c295f41a7c474229f97e90264bf21426a1d5aa0c2184202c1d354c',
        'content/world_cmds.py::npc_quick_dialog': '988c03dd329a2ab3b04bee9c1381453788477f84de8c2d3fe4e7cb7b0523962f',
        'content/world_cmds.py::find_npc': '89d945fca2f2e6b53b5a94118fc74b20f8e11f9d54ec281ad58252e026d30fe7',
        'content/world_cmds.py::move': 'a74a1c039761b7d29beb96738c14ad53e3f6ed485cd0dca5471b1db213fcd1d8',
        'content/world_cmds.py::time_cmd': 'ecd979490d5019b349af04e3f2ac6526423cf7a0d32c35af7c1b6ede50302e39',
        'content/world_cmds.py::wild_notes': '99fddc5597f852dee3877e3b2ec9e3d0d0332d5b5c7ada99cf8a682ba87f4dcb',
        'content/world_cmds.py::turn_in': 'bb2d404f207d33b3067698aaad35ee09e5b9690db7d6f9368298c5dfa22a8c74',
        'content/world_cmds.py::_grant_wild_unlock_flags': '4ecdf31eec9b8b2b34b4e8d525149d5e82349673e1c090b7dc58acc1a127d41e',
        'content/world_cmds.py::_teach_by_npc': 'cc57f2fe211b55199068388cbd341aba7c56c89c26c962d63901c3fd5c6b704b',
        'content/world_cmds.py::_map_blocks': '7adce186867a63fd3b1ddf9ff1c2868bc36b12a1f396991a6595e41fdfce993d',
        'content/world_cmds.py::_hurry_section': 'c81983fb47495c00fadd0aa5daa34080c443b52dfce0f8919d5294fc6b4837b2',
    },
    'aux': {
        'golden_wiring_probes': '79413d21ce4e29772bdbe72cda6e0058894780dce27ddbac6a2d9129c7b0097f',
        'talk_flag_raw': '{"npc_mayor": ["pledged"]}',
        'talk_flags_key': 'talkflags_g1_1001',
        'talk_key': 'talk_g1_1001',
        'talk_state_raw': '{"npc": "npc_mayor", "node": "welcome"}',
    },
    'segments': {
        'E': [
            'content/world_cmds.py::_npc_dialogue',
            'content/world_cmds.py::_player_map_name',
            'content/world_cmds.py::_subarea_name',
            'content/world_cmds.py::_find_wild_npc',
            'content/world_cmds.py::_wild_unseen_hint',
            'content/world_cmds.py::_npc_direction_hint',
            'content/world_cmds.py::_wild_cond_label',
            'content/world_cmds.py::_talk_active',
            'content/world_cmds.py::_talk_ctx',
            'content/world_cmds.py::_side_menu_expand',
            'content/world_cmds.py::_apply_talk_action_async',
            'content/world_cmds.py::_apply_talk_action',
            'content/world_cmds.py::time_cmd',
            'content/world_cmds.py::wild_notes',
        ],
        'C': [
            'content/world_cmds.py::_current_npcs',
            'content/world_cmds.py::_present_wild_hints',
            'content/world_cmds.py::_start_talk_list',
            'content/world_cmds.py::_find_npc_in_map',
            'content/world_cmds.py::_town_npc_absent_hint',
            'content/world_cmds.py::_render_talk_node',
            'content/world_cmds.py::talk_choice',
            'content/world_cmds.py::npc_quick_dialog',
            'content/world_cmds.py::find_npc',
            'content/world_cmds.py::move',
            'content/world_cmds.py::turn_in',
            'content/world_cmds.py::_grant_wild_unlock_flags',
            'content/world_cmds.py::_teach_by_npc',
            'content/world_cmds.py::_map_blocks',
            'content/world_cmds.py::_hurry_section',
        ],
        'A': [
        ],
    },
    'tier': {
        'content/world_cmds.py::_npc_dialogue': '甲',
        'content/world_cmds.py::_current_npcs': '甲',
        'content/world_cmds.py::_present_wild_hints': '甲',
        'content/world_cmds.py::_start_talk_list': '乙',
        'content/world_cmds.py::_find_npc_in_map': '甲',
        'content/world_cmds.py::_town_npc_absent_hint': '乙',
        'content/world_cmds.py::_player_map_name': '甲',
        'content/world_cmds.py::_subarea_name': '甲',
        'content/world_cmds.py::_find_wild_npc': '甲',
        'content/world_cmds.py::_wild_unseen_hint': '乙',
        'content/world_cmds.py::_npc_direction_hint': '甲',
        'content/world_cmds.py::_wild_cond_label': '甲',
        'content/world_cmds.py::_talk_active': '甲',
        'content/world_cmds.py::_talk_ctx': '乙',
        'content/world_cmds.py::_side_menu_expand': '乙',
        'content/world_cmds.py::_render_talk_node': '乙',
        'content/world_cmds.py::_apply_talk_action_async': '丙',
        'content/world_cmds.py::_apply_talk_action': '乙',
        'content/world_cmds.py::talk_choice': '丙',
        'content/world_cmds.py::npc_quick_dialog': '丙',
        'content/world_cmds.py::find_npc': '丙',
        'content/world_cmds.py::move': '丙',
        'content/world_cmds.py::time_cmd': '丙',
        'content/world_cmds.py::wild_notes': '丙',
        'content/world_cmds.py::turn_in': '丙',
        'content/world_cmds.py::_grant_wild_unlock_flags': '甲',
        'content/world_cmds.py::_teach_by_npc': '乙',
        'content/world_cmds.py::_map_blocks': '乙',
        'content/world_cmds.py::_hurry_section': '乙',
    },
}
# <<< _u1i4_gen (auto) <<<


# ══════════════════════════════════════════════════════════════════════════════
# 1. 冻结段清单 / 分级 / 旧实现命名空间 / 猴补
# ══════════════════════════════════════════════════════════════════════════════
_KEYS = list(_FROZEN_TEXT)                                   # 生成器写盘顺序 = SEGMENTS 顺序
_SYMS = [k.split("::")[1] for k in _KEYS]
_TIER = dict(_PIN.get("tier") or {})
_ALPHA = [k for k in _KEYS if _TIER.get(k) == "甲"]          # 模块级（无 self.）
_BETA = [k for k in _KEYS if _TIER.get(k) == "乙"]           # 有 self.、非 async
_GAMMA = [k for k in _KEYS if _TIER.get(k) == "丙"]          # async def


def _build_old_ns() -> dict:
    """旧命名空间：活模块 globals（同对象）+ 29 段冻结文本 exec 覆盖同名函数。

    甲类段读的就是这个 ns 的 globals；乙类段经 `_OldSelf` 绑成方法后同样读它。
    """
    ns = dict(vars(WC))
    for key, text in _FROZEN_TEXT.items():
        sym = key.split("::")[1]
        exec(compile(text, "<frozen:world_cmds:%s>" % sym, "exec"), ns)          # noqa: S102
    return ns


OLD = _build_old_ns()


class _Missing:
    """替身 `self` 未实现的口子 —— 一旦被调用即报错（防「门禁自己补了实现」）。"""

    def __init__(self, name):
        self._name = name

    def __call__(self, *a, **k):
        raise AssertionError("替身 self 未实现 %r（门禁不许自己补实现）" % self._name)

    def __getattr__(self, item):
        raise AssertionError("替身 self 未实现 %r.%s" % (self._name, item))


class _OldSelf:
    """旧侧 `self`：29 段冻结实现绑到自己身上，其余一律转活实现（同一批替身、同一份库）。"""

    def __init__(self, live):
        object.__setattr__(self, "_live", live)

    def __getattr__(self, name):
        live = object.__getattribute__(self, "_live")
        try:
            return getattr(live, name)
        except AttributeError:
            return _Missing(name)


def _mk_pair():
    """返回 (old_self, live_self)：old_self 的 29 段全是冻结实现。"""
    live = Main(None)
    old = _OldSelf(live)
    for key in _FROZEN_TEXT:
        sym = key.split("::")[1]
        old.__dict__[sym] = types.MethodType(OLD[sym], old)
    return old, live


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
        elif hasattr(self.obj, self.name):
            delattr(self.obj, self.name)
        return False


class _inject:
    """把 `content.world_cmds` 的模块级名字换成替身 —— 同时换到旧命名空间（退出原地还原）。"""

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: OLD.get(k, _MISSING) for k in self.kw}
        self.live = {k: getattr(WC, k, _MISSING) for k in self.kw}
        for k, v in self.kw.items():
            OLD[k] = v
            setattr(WC, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is _MISSING:
                OLD.pop(k, None)
            else:
                OLD[k] = v
        for k, v in self.live.items():
            if v is _MISSING:
                if hasattr(WC, k):
                    delattr(WC, k)
            else:
                setattr(WC, k, v)
        return False


def _run(fn, *a, **k):
    """调用并规整结果（异常收敛成可比较的元组，不吞成「相等」）。"""
    try:
        return ("ok", fn(*a, **k))
    except Exception as exc:                                            # noqa: BLE001
        return ("exc", type(exc).__name__, str(exc)[:160])


def _norm_ctx(d):
    """`_talk_ctx` 的归一：回调（`side_menu_expand`）只留「可调用」标记，其余逐值比。"""
    return {k: ("<callable>" if callable(v) else v) for k, v in d.items()}


# ══════════════════════════════════════════════════════════════════════════════
# 2. 数据面 / 夹具
# ══════════════════════════════════════════════════════════════════════════════
ALL = {**NPCS, **WILD_NPCS, **HIDDEN_NPCS}
ALL_ITEMS = list(ALL.items())
MAP_ITEMS = list(_MAP_BY_ID.items())

#: 749 用例 = 121 图（地图级 cur_sa=""）+ 628 子区域
SA_CASES = []
for _mid, _m in MAP_ITEMS:
    for _sa in (_m.get("subareas") or []):
        SA_CASES.append((_mid, _m, _sa["id"]))
    SA_CASES.append((_mid, _m, ""))

_NAME_KEYS = sorted({(n.get("name") or "") for _i, n in ALL_ITEMS if n.get("name")}
                    | set(ALL)
                    | {(n.get("name") or "")[:2] for _i, n in ALL_ITEMS
                       if len(n.get("name") or "") >= 2})
_NAME_KEYS = [k for k in _NAME_KEYS if k]

_TREES = {nid: DLG.get_dialogue(nid) for nid in NPCS}
_TREES = {k: v for k, v in _TREES.items() if v}
_TREE_NODES = [(nid, d, nk, nd) for nid, d in _TREES.items()
               for nk, nd in (d.get("nodes") or {}).items() if isinstance(nd, dict)]

#: 丙类探针选用的树（覆盖 texts / fail_next / side_menu / need / __end__ 五种特征）
_PROBE_NPCS = ["npc_mayor", "npc_innkeeper", "npc_rune_master", "npc_baron"]

READONLY_FILES = ("content/world_cmds.py", "content/data/dialogues.json",
                  "content/data/npcs.json")


def _pkg_file(relpath):
    return os.path.join(PKG_ROOT, *relpath.split("/"))


def _file_sha(relpath):
    with open(_pkg_file(relpath), encoding="utf-8") as fh:
        return sha256(fh.read())


class _TimedRecorder:
    """`content.timed_events` 的替身：只回给定事件表，不改存储。"""

    def __init__(self, events=None):
        self.events = list(events or [])

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


class _WildProxy:
    """`_wild` 的替身：只换 `ALL_WILD` 表，其余转真模块（口径分歧 ④ 合成用例用）。"""

    def __init__(self, table):
        self.ALL_WILD = table

    def __getattr__(self, name):
        return getattr(W, name)


class _RecDB:
    """`db` 的替身：只记 `update_player`（`_teach_by_npc` 差分用，零副作用）。"""

    def __init__(self):
        self.updates = []

    def update_player(self, *a, **k):
        self.updates.append((a, sorted(k.items())))


#: 丙类 golden 必须**跨日/跨时段可复现**：`turn_in` / `_find_wild_npc` 经 `base_conditions_met`
#: 读挂钟（`current_period` / `current_season` / `today_weather` / `date.today().weekday()`），
#: 不给伪时钟 → 上午抓的 golden 下午必红（实测踩过）。
_FAKE_TODAY = datetime.date(2026, 1, 5)


class _FakeDate(datetime.date):
    @classmethod
    def today(cls):
        return _FAKE_TODAY


_DT_CLS = datetime.datetime          # 先取模块级引用：类体里再写 `datetime = datetime.datetime` 会自遮蔽
_TD_CLS = datetime.timedelta


class _ClockModule:
    date = _FakeDate
    datetime = _DT_CLS
    timedelta = _TD_CLS


_FAKE_DT = _ClockModule
_FIXED_PERIOD = "day"
_FIXED_SEASON = "spring"
_FIXED_WEATHER = "sunny"


def _freeze_clock():
    """伪时钟上下文（退出原地还原）：`content.wild` 的四个挂钟读口 + `content.time_weather` 的时段口。"""
    class _Multi:
        def __init__(self, *cms):
            self.cms = cms

        def __enter__(self):
            for cm in self.cms:
                cm.__enter__()
            return self

        def __exit__(self, *exc):
            for cm in reversed(self.cms):
                cm.__exit__(*exc)
            return False
    return _Multi(
        _Patch(W, "datetime", _FAKE_DT),
        _Patch(W, "current_period", lambda *a, **k: _FIXED_PERIOD),
        _Patch(W, "current_season", lambda *a, **k: _FIXED_SEASON),
        _Patch(W, "today_weather", lambda *a, **k: _FIXED_WEATHER),
        _Patch(WC._tw, "current_period", lambda *a, **k: _FIXED_PERIOD),
    )


def _mk_events(n, map_id, ids, remain=60):
    out = []
    for i in range(n):
        nid = ids[i % len(ids)]
        out.append({"key": "wild:%s" % nid, "type": "wild_npc",
                    "data": {"npc_id": nid, "map": map_id},
                    "expire": 1767225600 + 3600, "remain": remain * (i + 1)})
    return out


def _first_sa(mid, npc_id):
    for sa in ((_MAP_BY_ID.get(mid) or {}).get("subareas") or []):
        if npc_id in (sa.get("npcs") or []):
            return sa["id"]
    return ""


def _npcs_in_place(m, sa_id):
    if sa_id:
        for sa in (m.get("subareas") or []):
            if sa["id"] == sa_id:
                return list(sa.get("npcs") or [])
        return []
    return list(m.get("npcs") or [])


def _synth_map(mid, npcs=(), inline=(), subareas=(), **kw):
    base = dict(MAP_ITEMS[0][1])
    base.update(id=mid, name="合成·%s" % mid, npcs=list(npcs), inline_npcs=list(inline),
                subareas=list(subareas), monsters=[], elite=None, boss=None, lv=1)
    base.update(kw)
    return base


def _synth_sa(sid, npcs=(), **kw):
    sa = {"id": sid, "name": "合成子区域·%s" % sid, "npcs": list(npcs), "monsters": [],
          "elite": None, "boss": None}
    sa.update(kw)
    return sa


def _drive(handler, *args):
    """直接驱动 async 实现体（不经声明表）：收集全部 yield 结果。"""
    return asyncio.run(h_run(lambda _e: handler(*args), None))


# ══════════════════════════════════════════════════════════════════════════════
# [1] 双 sha256 + E/C 分类 + 分级
# ══════════════════════════════════════════════════════════════════════════════
def test_frozen_pins():
    print("【1. 双 sha256：29 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 29（全在 content/world_cmds.py）", len(keys) == 29, len(keys))
    check("门禁内键序 == 冻结文本键序", keys == list(_FROZEN_TEXT), keys[:3])
    bad = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("冻结文本 sha256 全等 _PIN['frozen']（29 段）", not bad, bad[:4])

    live_bad = []
    for k in keys:
        sym = k.split("::")[1]
        obj = getattr(WC, sym, None)
        got = "<deleted>" if obj is None else sha256(inspect.getsource(obj))
        if got != _PIN["live"][k]:
            live_bad.append((k, _PIN["live"][k][:12], got[:12]))
    check("活实现 inspect.getsource sha256 全等 _PIN['live']（29 段）", not live_bad, live_bad[:4])

    seg = _PIN["segments"]
    chkE = [k for k in seg["E"] if _PIN["frozen"][k] != _PIN["live"][k]]
    check("E 栏「预期不变」段 frozen == live（%d 段）" % len(seg["E"]), not chkE, chkE[:3])
    if _PIN["phase"] == "landed":
        chkC = [k for k in seg["C"] if _PIN["frozen"][k] == _PIN["live"][k]]
        check("C 栏「预期会变」段 frozen != live（%d 段）" % len(seg["C"]), not chkC, chkC[:3])
    else:
        print("  ⓘ phase=%r：C 栏不等式断言按 §8 的「红基线」档暂不启用" % (_PIN["phase"],))

    tiers = {}
    for k in keys:
        tiers.setdefault(_TIER[k], []).append(k)
    got_tiers = (len(tiers.get("甲", [])), len(tiers.get("乙", [])), len(tiers.get("丙", [])))
    check("分级：甲 %d / 乙 %d / 丙 %d（期望 11 / 10 / 8）" % got_tiers, got_tiers == (11, 10, 8))
    check("丙类 8 段名单 == §1.3 名单",
          sorted(k.split("::")[1] for k in tiers.get("丙", []))
          == sorted(["_apply_talk_action_async", "talk_choice", "npc_quick_dialog", "find_npc",
                     "move", "time_cmd", "wild_notes", "turn_in"]),
          sorted(k.split("::")[1] for k in tiers.get("丙", [])))
    if _PIN["phase"] == "landed":
        check("世界侧已接引擎形状：Lookup / Presence / minutes_left / Cursor 在活模块"
              "（`_TALK` = L3 的 `Dialogue` 注入面，具备 pick/next_of/is_end）",
              all(hasattr(WC, n) for n in ("Lookup", "Presence", "minutes_left", "Cursor"))
              and all(hasattr(getattr(WC, "_TALK", None), m)
                      for m in ("pick", "next_of", "is_end", "options")),
              [n for n in ("Lookup", "Presence", "minutes_left", "Cursor")
               if not hasattr(WC, n)])
    else:
        print("  ⓘ phase=%r：引擎形状接入断言按「红基线」档暂不启用" % (_PIN["phase"],))


# ══════════════════════════════════════════════════════════════════════════════
# [2] 甲 / 乙类 exec 双向逐格比（21 段）
# ══════════════════════════════════════════════════════════════════════════════
CELLS = 0
NONEMPTY = 0
_MISM = []


def _cmp(label, sym, a, b):
    global CELLS, NONEMPTY
    CELLS += 1
    if a != b:
        _MISM.append((label, sym, a, b))
    elif a[0] == "ok" and a[1] not in (None, [], {}, "", 0, False):
        NONEMPTY += 1


def _mod(sym):
    return OLD[sym]


def _grid_npc_dialogue(old, live):
    """`_npc_dialogue`：431 NPC × 4 任务态（读 `db.get_quests`）。"""
    states = [
        {"main_quest": None, "main_status": "pending", "completed_main": [], "side": {}},
        {"main_quest": None, "main_status": "pending", "completed_main": ["q1"], "side": {}},
        {"main_quest": "q1", "main_status": "active", "completed_main": [], "side": {}},
        {"main_quest": "q2", "main_status": "ready", "completed_main": [], "side": {}},
    ]
    for st in states:
        db.save_quests("g1", "w1", st)
        for nid, npc in ALL_ITEMS:
            _cmp("npc_dialogue", "_npc_dialogue",
                 _run(_mod("_npc_dialogue"), "g1", "w1", nid, npc),
                 _run(WC._npc_dialogue, "g1", "w1", nid, npc))


def _grid_current_npcs(old, live):
    """`_current_npcs`：749 场所用例 + 3 合成（地图级 / inline / 子区域）。"""
    for mid, m, sa_id in SA_CASES:
        player = {"cur_map": mid, "cur_subarea": sa_id}
        _cmp("current_npcs", "_current_npcs",
             _run(_mod("_current_npcs"), player), _run(WC._current_npcs, player))
    base = MAP_ITEMS[0][1]
    ids = [nid for nid, _r in list(NPCS.items())[:6]]
    hid = list(HIDDEN_NPCS)
    sa = _synth_sa("u1i4_sa", ids[:3] + hid[:1])
    syn = _synth_map("u1i4_map", npcs=ids[3:5], subareas=[sa])
    syn_inline = dict(syn, inline_npcs=ids[5:6])
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_map=syn)):
        for cur_sa in ("u1i4_sa", ""):
            player = {"cur_map": "u1i4_map", "cur_subarea": cur_sa}
            _cmp("current_npcs/syn", "_current_npcs",
                 _run(_mod("_current_npcs"), player), _run(WC._current_npcs, player))
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_map=syn_inline)):
        player = {"cur_map": "u1i4_map", "cur_subarea": "u1i4_sa"}
        _cmp("current_npcs/inline", "_current_npcs",
             _run(_mod("_current_npcs"), player), _run(WC._current_npcs, player))


def _grid_present_wild_hints(old, live):
    """`_present_wild_hints`：20 图 × 0..3 限时事件 × 5 种 remain。"""
    ids = list(W.ALL_WILD)
    mids = [mid for mid, _m in MAP_ITEMS[:20]]
    for remain in (0, 1, 60, 3599, 3600):
        for mid in mids:
            for nev in (0, 1, 3):
                rec = _TimedRecorder(_mk_events(nev, mid, ids, remain=remain))
                with _inject(_timed=rec):
                    _cmp("present_wild_hints", "_present_wild_hints",
                         _run(old._present_wild_hints, "g1", "w1", mid),
                         _run(live._present_wild_hints, "g1", "w1", mid))


def _grid_find_npc_in_map(old, live):
    """`_find_npc_in_map`：749 场所 × 该场所前 2 个 id 的名字 / id / 不存在键 + `_npc_absent`。"""
    for mid, m, sa_id in SA_CASES:
        ids = _npcs_in_place(m, sa_id)
        keys = []
        for nid in ids[:2]:
            npc = NPCS.get(nid)
            if npc:
                keys.append(npc["name"])
            keys.append(nid)
        keys.append("绝不存在xyz")
        for k in keys:
            p1 = {"cur_map": mid, "cur_subarea": sa_id}
            p2 = {"cur_map": mid, "cur_subarea": sa_id}
            a = _run(_mod("_find_npc_in_map"), p1, k)
            b = _run(WC._find_npc_in_map, p2, k)
            _cmp("find_npc_in_map", "_find_npc_in_map",
                 a + (p1.get("_npc_absent"),), b + (p2.get("_npc_absent"),))


def _grid_player_map_name(old, live):
    for _mid, _m, sa_id in SA_CASES:
        if sa_id:
            _cmp("player_map_name", "_player_map_name",
                 _run(_mod("_player_map_name"), sa_id), _run(WC._player_map_name, sa_id))
    for bogus in ("", "no_such_sa", "oak_town"):
        _cmp("player_map_name/bogus", "_player_map_name",
             _run(_mod("_player_map_name"), bogus), _run(WC._player_map_name, bogus))


def _grid_subarea_name(old, live):
    for _mid, _m, sa_id in SA_CASES:
        if sa_id:
            _cmp("subarea_name", "_subarea_name",
                 _run(_mod("_subarea_name"), sa_id), _run(WC._subarea_name, sa_id))
    for bogus in ("", "no_such_sa", "oak_town"):
        _cmp("subarea_name/bogus", "_subarea_name",
             _run(_mod("_subarea_name"), bogus), _run(WC._subarea_name, bogus))


def _grid_find_wild_npc(old, live):
    maps = [mid for mid, _m in MAP_ITEMS[:3]] + ["no_such_map"]
    names = sorted({(r.get("name") or "") for r in W.ALL_WILD.values()} | set(W.ALL_WILD))
    names = [n for n in names if n][:80]
    for mid in maps:
        for k in names:
            p1 = {"cur_map": mid, "cur_subarea": "", "level": 99}
            p2 = {"cur_map": mid, "cur_subarea": "", "level": 99}
            _cmp("find_wild_npc", "_find_wild_npc",
                 _run(old._find_wild_npc, p1, k, "g1", "w1"),
                 _run(live._find_wild_npc, p2, k, "g1", "w1"))


def _grid_wild_unseen_hint(old, live):
    maps = [mid for mid, _m in MAP_ITEMS[:3]] + ["no_such_map"]
    names = sorted({(r.get("name") or "") for r in W.ALL_WILD.values()} | set(W.ALL_WILD))
    names = [n for n in names if n][:60]
    for mid in maps:
        for k in names:
            p1 = {"cur_map": mid, "cur_subarea": "", "level": 99}
            p2 = {"cur_map": mid, "cur_subarea": "", "level": 99}
            _cmp("wild_unseen_hint", "_wild_unseen_hint",
                 _run(old._wild_unseen_hint, p1, k, "g1", "w1"),
                 _run(live._wild_unseen_hint, p2, k, "g1", "w1"))


def _grid_npc_direction_hint(old, live):
    maps = [mid for mid, _m in MAP_ITEMS[:3]] + ["no_such_map"]
    for mid in maps:
        for k in _NAME_KEYS[:300]:
            player = {"cur_map": mid, "cur_subarea": ""}
            _cmp("npc_direction_hint", "_npc_direction_hint",
                 _run(_mod("_npc_direction_hint"), player, k),
                 _run(WC._npc_direction_hint, player, k))


_SYNTH_CONDS = [
    {}, {"time": ["night"]}, {"season": ["winter"]}, {"weather": "rain"},
    {"weather": "sunny"}, {"min_level": 10}, {"max_level": 5},
    {"day_of_week": [0]}, {"quest_done": ["q1"]}, {"quest_active": ["q1"]},
    {"flag": "heard_owl_song"}, {"item": "mat_herb"},
    {"time": ["morning", "day"], "season": ["spring"]},
]


def _grid_wild_cond_label(old, live):
    for _nid, npc in ALL_ITEMS:
        _cmp("wild_cond_label", "_wild_cond_label",
             _run(_mod("_wild_cond_label"), npc), _run(WC._wild_cond_label, npc))
    for cond in _SYNTH_CONDS:
        for extra in ({}, {"cycle": 3}, {"chance": 0.25}, {"unlock": "flag:x"},
                      {"cycle": 3, "chance": 0.9, "unlock": "flag:x"}):
            row = {"condition": dict(cond)}
            row.update(extra)
            _cmp("wild_cond_label/syn", "_wild_cond_label",
                 _run(_mod("_wild_cond_label"), row), _run(WC._wild_cond_label, row))


def _grid_talk_active(old, live):
    """`_talk_active`：会话值矩阵（空壳 / 坏值 / 合法 / 缺键 / 非字符串）+ 残留清除副作用。"""
    key = db.talk_state_key("g1", "w1")
    cases = [None, "", "{'npc': 'npc_mayor'}", "[]", "0", "null", "{}",
             '{"npc": "npc_mayor", "node": "welcome"}',
             '{"npc": "", "node": ""}', '{"npc": 1, "node": "welcome"}',
             '{"node": "welcome"}', "not json at all"]
    for raw in cases:
        for side in ("old", "new"):
            db.init_db()
            db.delete_event_state(key)
            if raw is not None:
                db.set_event_state(key, raw)
            fn = _mod("_talk_active") if side == "old" else WC._talk_active
            res = _run(fn, "g1", "w1")
            raw_after = db.get_event_state(key)
            if side == "old":
                a = res + (raw_after,)
            else:
                b = res + (raw_after,)
        _cmp("talk_active", "_talk_active", a, b)
    db.delete_event_state(key)


def _grid_grant_wild_unlock_flags(old, live):
    """`_grant_wild_unlock_flags`：带 `unlock_flags` 的 NPC × flag 已设/未设。"""
    rows = [(nid, r) for nid, r in W.ALL_WILD.items() if r.get("unlock_flags")]
    keys = [nid for nid, _r in rows] or list(W.ALL_WILD)[:3]
    for nid in keys:
        flag = (W.ALL_WILD[nid].get("unlock_flags") or {}).get("flag", "f")
        for preset in (False, True):
            res = {}
            for side in ("old", "new"):
                db.init_db()
                db.delete_event_state(PW.talk_flags_key("g1", "w1"))
                if preset:
                    db.set_talk_flag("g1", "w1", nid, flag)
                fn = _mod("_grant_wild_unlock_flags") if side == "old" \
                    else WC._grant_wild_unlock_flags
                res[side] = _run(fn, "g1", "w1", nid) + \
                    (db.get_event_state(PW.talk_flags_key("g1", "w1")),)
            _cmp("grant_unlock", "_grant_wild_unlock_flags", res["old"], res["new"])
    db.delete_event_state(PW.talk_flags_key("g1", "w1"))


def _grid_start_talk_list(old, live):
    """`_start_talk_list`：静态 N ∈ {0,1,2,5,36} × 限时 M ∈ {0,1,3} + 家里。"""
    ids = list(NPCS)
    overlay = list(W.ALL_WILD)
    mid = "u1i4_map2"
    for N in (0, 1, 2, 5, 36):
        sa = _synth_sa("u1i4_sa2", ids[:N])
        m = _synth_map(mid, subareas=[sa])
        for M in (0, 1, 3):
            rec = _TimedRecorder(_mk_events(M, mid, overlay))
            player = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 1,
                      "cur_map": mid, "cur_subarea": "u1i4_sa2"}
            live._player = lambda g, q, p=player: p
            with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_map2=m)), \
                    _Patch(W, "town_npc_visible", lambda *a, **k: True), \
                    _Patch(random, "choice", lambda seq: list(seq)[0]), \
                    _inject(_timed=rec):
                _cmp("start_talk_list", "_start_talk_list",
                     _run(old._start_talk_list, "g1", "w1"),
                     _run(live._start_talk_list, "g1", "w1"))
    home = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 1,
            "cur_map": "home_g1", "cur_subarea": ""}
    live._player = lambda g, q, p=home: p
    with _Patch(random, "choice", lambda seq: list(seq)[0]), _inject(_timed=_TimedRecorder()):
        _cmp("start_talk_list/home", "_start_talk_list",
             _run(old._start_talk_list, "g1", "w1"), _run(live._start_talk_list, "g1", "w1"))


def _grid_town_npc_absent_hint(old, live):
    """`_town_npc_absent_hint`：roam / period / appear 三因 × 各 NPC 自身场所。"""
    rows = [(nid, npc) for nid, npc in ALL_ITEMS
            if npc.get("roam") or npc.get("period") or npc.get("appear") is not None]
    for nid, npc in rows[:120]:
        places = [p for p in (npc.get("roam") or []) if p] or [npc.get("map")]
        for place in places[:3]:
            if place is None:
                continue
            _cmp("town_npc_absent_hint", "_town_npc_absent_hint",
                 _run(old._town_npc_absent_hint, nid, npc, place),
                 _run(live._town_npc_absent_hint, nid, npc, place))


def _grid_talk_ctx(old, live):
    """`_talk_ctx`：若干 npc × 两种玩家（回调只留「可调用」标记）。"""
    for nid in _PROBE_NPCS + ["npc_nobody_zzz"]:
        for level in (1, 60):
            H.clean_db("players", "player_groups", "quests", "inventory")
            player = H.make_player("g1", "w1", name="T", cls="战士", level=level)
            live._player = lambda g, q, p=player: p
            a = _run(old._talk_ctx, "g1", "w1", nid)
            b = _run(live._talk_ctx, "g1", "w1", nid)
            if a[0] == "ok":
                a = ("ok", _norm_ctx(a[1]))
            if b[0] == "ok":
                b = ("ok", _norm_ctx(b[1]))
            _cmp("talk_ctx", "_talk_ctx", a, b)


def _grid_side_menu_expand(old, live):
    """`_side_menu_expand`：把 `_side_available_list` 换成确定性桩，喂 3 种 available × opt。"""
    items = [{"sid": "s1", "name": "迷路的商人", "objective_text": "前往 白鹿之森"},
             {"sid": "s2", "name": "码头的猫", "objective_text": "收集 鱼 ×3"}]
    for avail in ([], items[:1], items):
        live._side_available_list = lambda g, q, nid, npc, _a=avail: list(_a)
        for opt in ({"side_menu": {}}, {"side_menu": {"after": "welcome"}},
                    {"side_menu": {"after": "welcome"}, "next": "dogg"}):
            _cmp("side_menu_expand", "_side_menu_expand",
                 _run(old._side_menu_expand, "g1", "w1", "npc_mayor", opt),
                 _run(live._side_menu_expand, "g1", "w1", "npc_mayor", opt))
    if "_side_available_list" in live.__dict__:
        del live.__dict__["_side_available_list"]


def _grid_render_talk_node(old, live):
    """`_render_talk_node`：全部树 × 全部节点 × 3 种 `_side_available_list` 桩（`_tip` 固定）。

    ⚠ 桩的是 `_side_available_list`（`_side_menu_expand` 的数据源）而**不是** `_side_menu_expand`
    本身 —— 后者是 29 段之一、旧侧会走冻结实现，桩它会让旧侧与活侧走不同分支（假红）。
    """
    items = [{"sid": "s1", "name": "迷路的商人", "objective_text": "前往 白鹿之森"}]
    for avail in ([], items, items * 2):
        live._side_available_list = lambda g, q, nid, npc, _a=avail: list(_a)
        with _Patch(random, "choice", lambda seq: list(seq)[0]):
            for nid, dlg, _nk, nd in _TREE_NODES:
                npc = NPCS.get(nid) or W.ALL_WILD.get(nid) or {"icon": "", "name": nid,
                                                               "title": ""}
                ctx = {"npc_id": nid, "_gid": "g1", "_qid": "w1", "side_menu_expand": None}
                _cmp("render_talk_node", "_render_talk_node",
                     _run(old._render_talk_node, npc, dlg, nd, ctx),
                     _run(live._render_talk_node, npc, dlg, nd, ctx))
    if "_side_available_list" in live.__dict__:
        del live.__dict__["_side_available_list"]


def _grid_apply_talk_action(old, live):
    """`_apply_talk_action`（同步版）：ACTIONS / `_check_action_keys` 换确定性桩。"""
    def _act_ok(self, g, q, p, nid, action):
        return ["ok-line"]

    def _act_async(self, g, q, p, nid, action):
        async def _coro():
            return ["async-line"]
        return _coro()

    def _act_route(self, g, q, p, nid, action):
        self._talk_route = "fail"
        return ["fail-line"]

    def _act_end(self, g, q, p, nid, action):
        self._talk_route = "__end__"
        return ["end-line"]

    def _act_tail(self, g, q, p, nid, action):
        self._talk_tail = ["tail-line"]
        return ["mid-line"]

    fake = {"k_ok": _act_ok, "k_async": _act_async, "k_route": _act_route,
            "k_end": _act_end, "k_tail": _act_tail}
    actions = [None, {}, {"k_ok": 1}, {"k_async": 1}, {"k_ok": 1, "k_route": 1},
               {"k_route": 1, "k_ok": 1}, {"k_end": 1}, {"k_tail": 1},
               {"k_tail": 1, "k_ok": 1}, {"nope": 1}]
    player = {"qq_id": "w1", "level": 5}
    with _Patch(TA, "ACTIONS", fake), _inject(_check_action_keys=lambda a: None):
        for act in actions:
            old._talk_route = None
            old._talk_tail = None
            a = _run(old._apply_talk_action, "g1", "w1", player, "npc_mayor", act)
            a = a + (getattr(old, "_talk_route", None), getattr(old, "_talk_tail", None))
            live._talk_route = None
            live._talk_tail = None
            b = _run(live._apply_talk_action, "g1", "w1", player, "npc_mayor", act)
            b = b + (getattr(live, "_talk_route", None), getattr(live, "_talk_tail", None))
            _cmp("apply_talk_action", "_apply_talk_action", a, b)


def _grid_teach_by_npc(old, live):
    """`_teach_by_npc`：带 `teach_skills` 的 NPC × 玩家（等级/金钱/职业），db 换记账替身。"""
    rows = [(nid, r) for nid, r in W.ALL_WILD.items() if r.get("teach_skills")]
    if not rows:
        rows = list(W.ALL_WILD.items())[:2]
    for nid, _r in rows[:6]:
        for level, gold in ((1, 0), (60, 5000), (99, 999999)):
            for cls in ("战士", "法师", "见习者"):
                player = {"qq_id": "w1", "name": "T", "level": level, "gold": gold,
                          "class_name": cls, "learned_skills": []}
                rec_old, rec_new = _RecDB(), _RecDB()
                with _inject(db=rec_old):
                    a = _run(old._teach_by_npc, "g1", "w1", player, nid) + \
                        (list(rec_old.updates),)
                with _inject(db=rec_new):
                    b = _run(live._teach_by_npc, "g1", "w1", player, nid) + \
                        (list(rec_new.updates),)
                _cmp("teach_by_npc", "_teach_by_npc", a, b)


def _grid_map_blocks(old, live):
    """`_map_blocks`：749 场所 × 0..2 限时事件（`_tip` 固定取第一条）。"""
    overlay = list(W.ALL_WILD)
    with _Patch(random, "choice", lambda seq: list(seq)[0]):
        for mid, m, sa_id in SA_CASES:
            for nev in (0, 2):
                rec = _TimedRecorder(_mk_events(nev, mid, overlay))
                player = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 5,
                          "cur_map": mid, "cur_subarea": sa_id}
                live._player = lambda g, q, p=player: p
                with _inject(_timed=rec):
                    _cmp("map_blocks", "_map_blocks",
                         _run(old._map_blocks, player, m, sa_id, "g1", "w1"),
                         _run(live._map_blocks, player, m, sa_id, "g1", "w1"))


def _grid_hurry_section(old, live):
    """`_hurry_section`：749 场所 × 4 类型（npc/monster/scene/facility）。"""
    with _Patch(random, "choice", lambda seq: list(seq)[0]):
        for mid, m, sa_id in SA_CASES:
            player = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 5,
                      "cur_map": mid, "cur_subarea": sa_id}
            live._player = lambda g, q, p=player: p
            with _inject(_timed=_TimedRecorder()):
                for ftype in ("npc", "monster", "scene", "facility"):
                    _cmp("hurry_section", "_hurry_section",
                         _run(old._hurry_section, player, m, sa_id, "g1", "w1", ftype),
                         _run(live._hurry_section, player, m, sa_id, "g1", "w1", ftype))


_GRIDS = [
    ("_npc_dialogue", _grid_npc_dialogue),
    ("_current_npcs", _grid_current_npcs),
    ("_present_wild_hints", _grid_present_wild_hints),
    ("_find_npc_in_map", _grid_find_npc_in_map),
    ("_player_map_name", _grid_player_map_name),
    ("_subarea_name", _grid_subarea_name),
    ("_find_wild_npc", _grid_find_wild_npc),
    ("_wild_unseen_hint", _grid_wild_unseen_hint),
    ("_npc_direction_hint", _grid_npc_direction_hint),
    ("_wild_cond_label", _grid_wild_cond_label),
    ("_talk_active", _grid_talk_active),
    ("_grant_wild_unlock_flags", _grid_grant_wild_unlock_flags),
    ("_start_talk_list", _grid_start_talk_list),
    ("_town_npc_absent_hint", _grid_town_npc_absent_hint),
    ("_talk_ctx", _grid_talk_ctx),
    ("_side_menu_expand", _grid_side_menu_expand),
    ("_render_talk_node", _grid_render_talk_node),
    ("_apply_talk_action", _grid_apply_talk_action),
    ("_teach_by_npc", _grid_teach_by_npc),
    ("_map_blocks", _grid_map_blocks),
    ("_hurry_section", _grid_hurry_section),
]


#: ★ 2026-09-18 有意行为变更登记（审计修复批次）：旧 ↔ 新的格子差异**只允许**出现在这些
#: 符号上；其余 20 段必须继续逐格全等。登记表同时被下方「必须命中」断言守卫 —— 差异消失
#: 或差异扩散到未登记段都会报红（不做静默放宽）。
#:  · `_hurry_section`：旧实现把 `_map_scene` 的 (poi_lines, prop_lines) 二元组当平铺列表
#:    用 ⇒ 直接打印 list repr（`  ['🛕 古老神龛(『探索』有机会发现)', …]`）且两区不分离；
#:    修后按 🔎 可探索触发 / ✨ 可交互场景 两区逐行输出（与 `_map_blocks` 同口径）。
_INTENDED_GRID_MISMATCH = {"_hurry_section"}


def test_render_literals():
    """渲染行**逐字节不变**的明文证据（判据 #2）：冻结旧实现 ↔ 活实现 + 逐条字面量。"""
    print("【2′. 渲染行逐字节不变的明文证据（⏳剩N分 / 分节标题 / 「这里没有 NPC」/ 头衔括号）】")
    mid = "u1i4_render"
    ids = list(NPCS)[:3]
    overlay = list(W.ALL_WILD)[:2]
    sa = _synth_sa("u1i4_render_sa", ids[:2])
    m = _synth_map(mid, npcs=ids[2:], subareas=[sa])
    rec = _TimedRecorder(_mk_events(2, mid, overlay, remain=60))
    old, live = _mk_pair()
    player = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 5,
              "cur_map": mid, "cur_subarea": "u1i4_render_sa"}
    live._player = lambda g, q, p=player: p
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_render=m)), \
            _Patch(W, "town_npc_visible", lambda *a, **k: True), \
            _Patch(random, "choice", lambda seq: list(seq)[0]), _inject(_timed=rec):
        a_blocks = _run(old._map_blocks, player, m, "u1i4_render_sa", "g1", "w1")
        b_blocks = _run(live._map_blocks, player, m, "u1i4_render_sa", "g1", "w1")
        a_hurry = _run(old._hurry_section, player, m, "u1i4_render_sa", "g1", "w1", "npc")
        b_hurry = _run(live._hurry_section, player, m, "u1i4_render_sa", "g1", "w1", "npc")
        a_talk = _run(old._start_talk_list, "g1", "w1")
        b_talk = _run(live._start_talk_list, "g1", "w1")
        a_pres = _run(old._present_wild_hints, "g1", "w1", mid)
        b_pres = _run(live._present_wild_hints, "g1", "w1", mid)
    check("`_map_blocks` 渲染行 旧 == 新 逐字节", a_blocks == b_blocks)
    check("`_hurry_section` 渲染行 旧 == 新 逐字节", a_hurry == b_hurry)
    check("`_start_talk_list` 渲染行 旧 == 新 逐字节", a_talk == b_talk)
    check("`_present_wild_hints` 渲染行 旧 == 新 逐字节", a_pres == b_pres)
    blk = "\n".join(b_blocks[1] if b_blocks[0] == "ok" else [])
    hry = "\n".join(b_hurry[1] if b_hurry[0] == "ok" else [])
    talk = "\n".join(b_talk[1] if b_talk[0] == "ok" else [])
    pres = "\n".join(b_pres[1] if b_pres[0] == "ok" else [])
    check("分节标题「👥 这里的 NPC：」逐字节", "👥 这里的 NPC：" in talk, talk[:60])
    check("分节标题「🧭 游历的旅人：」逐字节", "🧭 游历的旅人：" in blk, blk[:60])
    check("限时行模板 `⏳剩N分` 逐字节（remain=60 → 剩1分；120 → 剩2分）",
          "⏳剩1分" in pres and "⏳剩2分" in pres and "⏳剩1分" in talk, pres[:120])
    check("头衔括号模板 `(title)` 逐字节（赶路面板 `N. icon name(title)`）",
          re.search(r"^\s+\d+\. .+\(.+\)$", hry, re.M) is not None, hry[:120])
    check("紧凑 NPC 行 `●N. icon name`（无头衔，鱼鱼模板）逐字节",
          "●1. " in blk, blk[:120])
    # 空场所：「这里没有 NPC」两处文案
    empty = _synth_map("u1i4_empty", subareas=[_synth_sa("u1i4_empty_sa", [])])
    live._player = lambda g, q: {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 1,
                                 "cur_map": "u1i4_empty", "cur_subarea": "u1i4_empty_sa"}
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_empty=empty)), \
            _Patch(W, "town_npc_visible", lambda *a, **k: True), \
            _Patch(random, "choice", lambda seq: list(seq)[0]), \
            _inject(_timed=_TimedRecorder()):
        old, live2 = _mk_pair()
        live2._player = live._player
        a2 = _run(old._start_talk_list, "g1", "w1")
        b2 = _run(live2._start_talk_list, "g1", "w1")
        a3 = _run(old._hurry_section, live2._player("g", "q"), empty, "u1i4_empty_sa",
                  "g1", "w1", "npc")
        b3 = _run(live2._hurry_section, live2._player("g", "q"), empty, "u1i4_empty_sa",
                  "g1", "w1", "npc")
    check("「这里没有 NPC。输入『地图』看看哪里有 NPC～」逐字节",
          a2 == b2 and b2[0] == "ok"
          and b2[1] == ["这里没有 NPC。输入『地图』看看哪里有 NPC～"], b2)
    check("「👥 这里附近没有可交谈的 NPC ～」逐字节",
          a3 == b3 and b3[1] == ["👥 这里附近没有可交谈的 NPC ～"], b3)


def test_alpha_beta():
    print("【2. 甲/乙类 exec 双向逐格比：21 段（甲 11 + 乙 10）】")
    check("网格数 == 21（= 29 − 丙 8）", len(_GRIDS) == 21, len(_GRIDS))
    covered = {s for s, _f in _GRIDS}
    check("覆盖全部甲/乙段（无遗漏）",
          covered == {k.split("::")[1] for k in _ALPHA + _BETA},
          sorted(covered ^ {k.split("::")[1] for k in _ALPHA + _BETA}))
    db.init_db()
    H.clean_db()
    H.make_player("g1", "w1", name="T", cls="战士", level=5)
    old, live = _mk_pair()
    live._player = lambda g, q: db.get_player(g, q) or {}
    for sym, fn in _GRIDS:
        before = CELLS
        try:
            fn(old, live)
        except Exception as exc:                                        # noqa: BLE001
            check("网格 `%s` 跑通" % sym, False, "%s: %s" % (type(exc).__name__, exc))
            continue
        print("     %-28s +%d 格" % (sym, CELLS - before))
    check("网格总格数 == %d（> 8000，矩阵没退化成空跑）" % CELLS, CELLS > 8000, CELLS)
    check("有非空输出格（%d 格，矩阵真跑到了内容）" % NONEMPTY, NONEMPTY > 300, NONEMPTY)
    print("     不一致格数 = %d" % len(_MISM))
    if _MISM:
        hist = {}
        for row in _MISM:
            hist[row[0]] = hist.get(row[0], 0) + 1
        print("     不一致分布 = %s" % sorted(hist.items(), key=lambda kv: -kv[1]))
    _unexpected = [r for r in _MISM if r[1] not in _INTENDED_GRID_MISMATCH]
    check("21 段 旧 ↔ 新 逐格全等（返回值 + 副作用；已登记有意变更段除外）",
          not _unexpected, _unexpected[:3])
    _hit = {r[1] for r in _MISM} & _INTENDED_GRID_MISMATCH
    check("已登记有意变更段确实出现差异（%d 段，防登记表变免死金牌）"
          % len(_INTENDED_GRID_MISMATCH), _hit == _INTENDED_GRID_MISMATCH,
          sorted(_INTENDED_GRID_MISMATCH - _hit))


# ══════════════════════════════════════════════════════════════════════════════
# [3]+[4] 丙类端到端探针（8 段 async）+ aux 指纹
# ══════════════════════════════════════════════════════════════════════════════
class _TalkLog:
    """`WC.db` 代理：记录 `set_talk_state` / `clear_talk_state` 的**调用序**，其余透传。"""

    def __init__(self, real):
        self._real = real
        self.calls = []

    def __getattr__(self, name):
        return getattr(self._real, name)

    def set_talk_state(self, group_id, qq_id, npc_id, node_id):
        self.calls.append(("set", npc_id, node_id))
        return self._real.set_talk_state(group_id, qq_id, npc_id, node_id)

    def clear_talk_state(self, group_id, qq_id):
        self.calls.append(("clear",))
        return self._real.clear_talk_state(group_id, qq_id)


def _talk_state_raw():
    return db.get_event_state(db.talk_state_key("g1", "w1"))


def _probe_talk_choice(log, m):
    out = {}
    for nid in _PROBE_NPCS:
        npc = NPCS.get(nid) or W.ALL_WILD.get(nid)
        if not npc:
            continue
        mid = npc.get("map") or "oak_town"
        sa = _first_sa(mid, nid)
        for tag, quests in (("pending", {"main_quest": "q1", "main_status": "pending",
                                         "completed_main": [], "side": {}}),
                            ("done", {"main_quest": None, "main_status": "pending",
                                      "completed_main": ["q1"], "side": {}})):
            for state in ("in_talk", "no_talk"):
                for msg in ("1", "2", "3", "0", "99", "abc", "对话 1", "结束对话", "再见"):
                    db.init_db()
                    db.delete_event_state(db.talk_state_key("g1", "w1"))
                    db.save_quests("g1", "w1", quests)
                    db.update_player("g1", "w1", cur_map=mid, cur_subarea=sa)
                    p2 = db.get_player("g1", "w1")
                    if state == "in_talk":
                        db.set_talk_state("g1", "w1", nid,
                                          (_TREES.get(nid) or {}).get("start", ""))
                    log.calls = []
                    ev = FakeEvent("g1", "w1", msg)
                    try:
                        res = _drive(WC.talk_choice, m, ev, "g1", "w1", p2)
                    except Exception as exc:                            # noqa: BLE001
                        res = ["<exc:%s>" % type(exc).__name__]
                    out["tc:%s:%s:%s:%s" % (nid, tag, state, msg)] = [
                        "\n".join(res), _talk_state_raw(), list(log.calls)]
    for msg in ("对话 0", "对话 ０", "对话 镇长", "对话", "1", "再见", "找 镇长"):
        db.init_db()
        db.delete_event_state(db.talk_state_key("g1", "w1"))
        db.save_quests("g1", "w1", {"main_quest": None, "main_status": "pending",
                                    "completed_main": [], "side": {}})
        db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
        p2 = db.get_player("g1", "w1")
        log.calls = []
        try:
            res = _drive(WC.talk_choice, m, FakeEvent("g1", "w1", msg), "g1", "w1", p2)
        except Exception as exc:                                        # noqa: BLE001
            res = ["<exc:%s>" % type(exc).__name__]
        out["tc-idle:%s" % msg] = ["\n".join(res), _talk_state_raw(), list(log.calls)]
    return out


def _probe_find_npc(log, m):
    out = {}
    cases = [("oak_town", "oak_town_2", "找 镇长"), ("oak_town", "oak_town_2", "找 1"),
             ("oak_town", "oak_town_2", "找 99"), ("oak_town", "oak_town_2", "找"),
             ("oak_town", "oak_town_2", "找 绝不存在xyz"), ("oak_plain", "", "找 游商"),
             ("home_g1", "", "找 镇长"), ("oak_town", "oak_town_2", "找 npc_mayor")]
    for mid, sa, msg in cases:
        db.init_db()
        db.delete_event_state(db.talk_state_key("g1", "w1"))
        db.update_player("g1", "w1", cur_map=mid, cur_subarea=sa)
        p2 = db.get_player("g1", "w1")
        log.calls = []
        try:
            res = _drive(WC.find_npc, m, FakeEvent("g1", "w1", msg))
        except Exception as exc:                                        # noqa: BLE001
            res = ["<exc:%s>" % type(exc).__name__]
        out["fn:%s:%s:%s" % (mid, sa, msg)] = ["\n".join(res), _talk_state_raw(),
                                               list(log.calls)]
    db.init_db()
    db.set_talk_state("g1", "w1", "npc_mayor", (_TREES.get("npc_mayor") or {}).get("start", ""))
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    log.calls = []
    try:
        res = _drive(WC.find_npc, m, FakeEvent("g1", "w1", "找 文书"))
    except Exception as exc:                                            # noqa: BLE001
        res = ["<exc:%s>" % type(exc).__name__]
    out["fn:in_talk"] = ["\n".join(res), _talk_state_raw(), list(log.calls)]
    return out


def _probe_quick_dialog(log, m):
    out = {}
    for tag, setup in (("no_state", {}), ("talk", {"talk": True}),
                       ("item_view", {"item": True}), ("move_mode", {"move": True})):
        for msg in ("1", "0"):
            db.init_db()
            db.delete_event_state(db.talk_state_key("g1", "w1"))
            db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
            if setup.get("talk"):
                db.set_talk_state("g1", "w1", "npc_mayor",
                                  (_TREES.get("npc_mayor") or {}).get("start", ""))
            if setup.get("item"):
                db.set_event_state("item_view_mode:w1", "1")
            if setup.get("move"):
                db.set_event_state("move_mode:w1", "1")
            log.calls = []
            try:
                res = _drive(WC.npc_quick_dialog, m, FakeEvent("g1", "w1", msg), "g1", "w1")
            except Exception as exc:                                    # noqa: BLE001
                res = ["<exc:%s>" % type(exc).__name__]
            out["qd:%s:%s" % (tag, msg)] = ["\n".join(res), _talk_state_raw(),
                                            list(log.calls)]
    db.delete_event_state("item_view_mode:w1")
    db.delete_event_state("move_mode:w1")
    return out


def _probe_move(log, m):
    out = {}
    db.init_db()
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    db.set_talk_state("g1", "w1", "npc_mayor", (_TREES.get("npc_mayor") or {}).get("start", ""))
    log.calls = []
    try:
        res = _drive(WC.move, m, FakeEvent("g1", "w1", "前往 铁盾镇"), "g1", "w1")
    except Exception as exc:                                            # noqa: BLE001
        res = ["<exc:%s>" % type(exc).__name__]
    out["mv:talk"] = ["\n".join(res), db.get_player("g1", "w1").get("cur_map"),
                      list(log.calls)]
    db.init_db()
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    db.set_event_state(db.talk_state_key("g1", "w1"), "{'npc': 'npc_mayor'}")
    log.calls = []
    try:
        _drive(WC.move, m, FakeEvent("g1", "w1", "前往 绝不存在的地方"), "g1", "w1")
    except Exception:                                                   # noqa: BLE001
        pass
    out["mv:bad_residual_cleared"] = [db.get_event_state(db.talk_state_key("g1", "w1")) is None,
                                      list(log.calls)]
    return out


def _probe_time_cmd(log, m):
    out = {}
    db.init_db()
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    p2 = db.get_player("g1", "w1")
    hints = [(nid, npc) for nid, npc in list(W.ALL_WILD.items())[:7]]
    with _Patch(WC._tw, "time_weather_summary", lambda mid: "晴 · 白天 · 第 3 天"), \
            _Patch(WC._wild, "nearby_hints", lambda g, q, p, mid, _h=hints: list(_h)):
        try:
            res = _drive(WC.time_cmd, m, FakeEvent("g1", "w1", "时间"), "g1", "w1", p2)
        except Exception as exc:                                        # noqa: BLE001
            res = ["<exc:%s>" % type(exc).__name__]
    out["time:hints"] = ["\n".join(res)]
    with _Patch(WC._tw, "time_weather_summary", lambda mid: "晴 · 白天 · 第 3 天"), \
            _Patch(WC._wild, "nearby_hints", lambda g, q, p, mid: []):
        try:
            res = _drive(WC.time_cmd, m, FakeEvent("g1", "w1", "时间"), "g1", "w1", p2)
        except Exception as exc:                                        # noqa: BLE001
            res = ["<exc:%s>" % type(exc).__name__]
    out["time:empty"] = ["\n".join(res)]
    return out


def _probe_wild_notes(log, m):
    out = {}
    db.init_db()
    db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
    p2 = db.get_player("g1", "w1")
    met = list(W.ALL_WILD)[:3]
    for tag, lst in (("empty", []), ("three", met), ("stale", met + ["npc_zzz_not_exist"])):
        with _Patch(WC._wild, "met_wild", lambda g, q, _l=list(lst): list(_l)):
            try:
                res = _drive(WC.wild_notes, m, FakeEvent("g1", "w1", "见闻"), "g1", "w1", p2)
            except Exception as exc:                                    # noqa: BLE001
                res = ["<exc:%s>" % type(exc).__name__]
        out["wn:%s" % tag] = ["\n".join(res)]
    return out


def _probe_turn_in(log, m):
    out = {}
    giver = next(q for q in MAIN_QUESTS if NPCS.get(q.get("giver")))
    gmap = NPCS[giver["giver"]].get("map")
    side = next((q for q in SIDE_QUESTS if NPCS.get(q.get("giver"))
                 and (q.get("objective") or {}).get("collect")), None)
    cases = [
        ("main_ready_here", {"main_quest": giver["id"], "main_status": "ready",
                             "completed_main": [], "side": {}}, gmap, {}),
        ("main_ready_away", {"main_quest": giver["id"], "main_status": "ready",
                             "completed_main": [], "side": {}}, "oak_plain", {}),
        ("nothing", {"main_quest": None, "main_status": "pending",
                     "completed_main": [], "side": {}}, gmap, {}),
    ]
    if side:
        obj = side["objective"]
        need = obj.get("collect_count") or obj.get("count", 1)
        smap = NPCS[side["giver"]].get("map")
        cases.append(("side_ready_here",
                      {"main_quest": None, "main_status": "pending", "completed_main": [],
                       "side": {side["id"]: {"status": "ready"}}}, smap, {}))
        cases.append(("side_collect_missing",
                      {"main_quest": None, "main_status": "pending", "completed_main": [],
                       "side": {side["id"]: {"status": "active"}}}, smap, {}))
        cases.append(("side_collect_enough",
                      {"main_quest": None, "main_status": "pending", "completed_main": [],
                       "side": {side["id"]: {"status": "active"}}},
                      smap, {obj["collect"]: need}))
    for tag, quests, mid, items in cases:
        db.init_db()
        db.delete_event_state(db.talk_state_key("g1", "w1"))
        db.save_quests("g1", "w1", quests)
        db.update_player("g1", "w1", cur_map=mid, cur_subarea="", level=99)
        for item, cnt in items.items():
            try:
                db.add_item("g1", "w1", item, cnt)
            except Exception:                                           # noqa: BLE001
                pass
        p2 = db.get_player("g1", "w1")
        log.calls = []
        try:
            res = _drive(WC.turn_in, m, FakeEvent("g1", "w1", "交付任务"), "g1", "w1", p2)
        except Exception as exc:                                        # noqa: BLE001
            res = ["<exc:%s>" % type(exc).__name__]
        out["ti:%s" % tag] = ["\n".join(res), _talk_state_raw(), list(log.calls)]
    return out


def _probe_apply_action_async(log, m):
    out = {}

    def _act_ok(self, g, q, p, nid, action):
        return ["ok-line"]

    async def _act_async(_self, g, q, p, nid, action):
        return ["async-line"]

    def _act_route(self, g, q, p, nid, action):
        self._talk_route = "fail"
        return ["fail-line"]

    def _act_tail(self, g, q, p, nid, action):
        self._talk_tail = ["tail-line"]
        return ["mid-line"]

    fake = {"k_ok": _act_ok, "k_async": _act_async, "k_route": _act_route,
            "k_tail": _act_tail}
    actions = [None, {}, {"k_ok": 1}, {"k_async": 1}, {"k_ok": 1, "k_route": 1},
               {"k_route": 1, "k_ok": 1}, {"k_tail": 1}, {"k_tail": 1, "k_ok": 1}]
    p2 = {"qq_id": "w1", "level": 5}
    with _Patch(TA, "ACTIONS", fake), _Patch(WC, "_check_action_keys", lambda a: None):
        for act in actions:
            try:
                res = asyncio.run(
                    WC._apply_talk_action_async(m, "g1", "w1", p2, "npc_mayor", act))
                rec = [list(res[0]), res[1]]
            except Exception as exc:                                    # noqa: BLE001
                rec = ["<exc:%s>" % type(exc).__name__]
            out["aa:%s" % json.dumps(act, sort_keys=True, ensure_ascii=False)] = [
                rec, getattr(m, "_talk_route", None), getattr(m, "_talk_tail", None)]
    return out


#: 合成对话树（teeth/golden 用）：同时覆盖 `texts` 变体（两条都满足）/ need 门控 /
#: `fail_next`（动作返回 fail）/ `__end__` 哨兵四条链 —— 真实数据里这四种未必同时命中一格。
#: 挂在一个**真实** NPC id 上（只换它的树）—— 这样不碰 `NPCS` 表，活实现的 `Lookup` 仍命中。
_SYNTH_ID = "npc_mayor"
_SYNTH_TREE = {
    "start": "n0",
    "nodes": {
        "n0": {"text": "兜底开场",
               "texts": [{"need": {}, "text": "变体A"}, {"need": {}, "text": "变体B"}],
               "options": [
                   {"text": "去 n1", "next": "n1"},
                   {"text": "带 need（默认不可见）", "next": "n2",
                    "need": {"quest_done": ["__never__"]}},
                   {"text": "失败转 n3", "next": "n2", "fail_next": "n3",
                    "action": {"k_route": 1}},
                   {"text": "结束", "next": "__end__"},
               ]},
        "n1": {"text": "n1 台词", "options": [{"text": "结束", "next": "__end__"}]},
        "n2": {"text": "n2 台词（next 路径）", "options": [{"text": "结束", "next": "__end__"}]},
        "n3": {"text": "n3 台词（fail_next 路径）",
               "options": [{"text": "结束", "next": "__end__"}]},
    },
}


def _probe_synth_tree(log, m):
    """合成树探针：4 条链（变体序 / need / fail_next / `__end__`）逐输入取输出 + 会话。"""
    rows = {}
    orig_get = WC._dlg.get_dialogue

    def _get_dialogue(nid):
        return _SYNTH_TREE if nid == _SYNTH_ID else orig_get(nid)

    def _route_fn(self, g, q, p, nid, action):
        self._talk_route = "fail"
        return ["⚠️ 合成动作失败"]

    with _Patch(WC._dlg, "get_dialogue", _get_dialogue), \
            _Patch(TA, "ACTIONS", {"k_route": _route_fn}), \
            _Patch(WC, "_check_action_keys", lambda a: None):
        for msg in ("1", "2", "3", "4", "0", "99", "abc"):
            db.init_db()
            db.delete_event_state(db.talk_state_key("g1", "w1"))
            db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
            db.set_talk_state("g1", "w1", _SYNTH_ID, "n0")
            p2 = db.get_player("g1", "w1")
            log.calls = []
            try:
                res = _drive(WC.talk_choice, m, FakeEvent("g1", "w1", msg), "g1", "w1", p2)
            except Exception as exc:                                    # noqa: BLE001
                res = ["<exc:%s>" % type(exc).__name__]
            rows["syn:%s" % msg] = ["\n".join(res), _talk_state_raw(), list(log.calls)]
    return rows


def _wiring_probes() -> dict:
    """丙类 8 段的端到端探针 → 规整 dict（全部输出行 + `talk_state` 原文 + set/clear 调用序）。

    ⚠ **必须在改任何实现之前跑一次**（`--emit-aux` 抓 golden）；改完后逐字节相等 = 行为不变。
    """
    out = {}
    with _freeze_clock(), _Patch(random, "choice", lambda seq: list(seq)[0]):
        db.init_db()
        H.clean_db()
        H.make_player("g1", "w1", name="T", cls="战士", level=5)
        m = Main(None)
        log = _TalkLog(db)
        with _inject(db=log):
            db.init_db()
            db.update_player("g1", "w1", cur_map="oak_town", cur_subarea="oak_town_2")
            out.update(_probe_talk_choice(log, m))
            out.update(_probe_find_npc(log, m))
            out.update(_probe_quick_dialog(log, m))
            out.update(_probe_move(log, m))
            out.update(_probe_time_cmd(log, m))
            out.update(_probe_wild_notes(log, m))
            out.update(_probe_turn_in(log, m))
            out.update(_probe_apply_action_async(log, m))
            out.update(_probe_synth_tree(log, m))
    db.delete_event_state("item_view_mode:w1")
    db.delete_event_state("move_mode:w1")
    return out


def _probe_digest() -> str:
    return sha256(json.dumps(_wiring_probes(), sort_keys=True, ensure_ascii=False))


def _aux_fingerprints() -> dict:
    out = {}
    db.init_db()
    out["talk_key"] = PW.talk_state_key("g1", "1001")
    out["talk_flags_key"] = PW.talk_flags_key("g1", "1001")
    db.delete_event_state(out["talk_key"])
    PW.set_talk_state("g1", "1001", "npc_mayor", "welcome")
    out["talk_state_raw"] = db.get_event_state(out["talk_key"]) or ""
    db.delete_event_state(out["talk_flags_key"])
    PW.set_talk_flag("g1", "1001", "npc_mayor", "pledged")
    out["talk_flag_raw"] = db.get_event_state(out["talk_flags_key"]) or ""
    PW.clear_talk_state("g1", "1001")
    db.delete_event_state(out["talk_flags_key"])
    out["golden_wiring_probes"] = _probe_digest()
    return out


def test_aux():
    print("【4. aux 指纹：会话键 / flag 键 / JSON 文本 + 丙类 golden】")
    got = _aux_fingerprints()
    if not _PIN["aux"]:
        check("_PIN['aux'] 已生成", False, "先用 `_u1i4_wiring_world_gen.py --emit-aux` 生成")
        return
    bad = [k for k in _PIN["aux"] if got.get(k) != _PIN["aux"][k]]
    check("aux 指纹 %d 条全等 _PIN['aux']（含 golden）" % len(_PIN["aux"]), not bad,
          [(k, str(_PIN["aux"][k])[:24], str(got.get(k))[:24]) for k in bad][:3])
    check("会话键格式 == talk_g1_1001", got["talk_key"] == "talk_g1_1001", got["talk_key"])
    check("flag 键格式 == talkflags_g1_1001",
          got["talk_flags_key"] == "talkflags_g1_1001", got["talk_flags_key"])
    check("会话 JSON 文本逐字节 == '{\"npc\": \"npc_mayor\", \"node\": \"welcome\"}'",
          got["talk_state_raw"] == '{"npc": "npc_mayor", "node": "welcome"}',
          got["talk_state_raw"])


def test_golden_probes():
    print("【3. 丙类端到端探针：8 段 async（输出全部行 + talk_state + set/clear 调用序）】")
    if not _PIN["aux"].get("golden_wiring_probes"):
        check("golden 已抓", False, "先用 `--emit-aux` 在改实现之前抓 golden")
        return
    probes = _wiring_probes()
    check("丙类探针用例数 == %d（> 150）" % len(probes), len(probes) > 150, len(probes))
    got = sha256(json.dumps(probes, sort_keys=True, ensure_ascii=False))
    check("丙类探针 golden 指纹逐字节不变", got == _PIN["aux"]["golden_wiring_probes"],
          (got[:16], _PIN["aux"]["golden_wiring_probes"][:16]))
    pref = {k.split(":", 1)[0] for k in probes}
    check("丙类覆盖 8 个 async 段（探针键前缀）",
          {"tc", "fn", "qd", "mv", "time", "wn", "ti", "aa"} <= pref, sorted(pref))
    check("丙类明文含「那就再会了」结束行",
          any("那就再会了" in v[0] for v in probes.values()))
    check("丙类明文含「你现在没有正在进行的对话」入口行",
          any("你现在没有正在进行的对话" in v[0] for v in probes.values()))
    check("丙类明文含「0. 结束对话」渲染行",
          any("0. 结束对话" in v[0] for v in probes.values()))
    check("丙类明文含越界文案「没有这个选项」",
          any("没有这个选项" in v[0] for v in probes.values()))
    check("丙类明文含拦截文案「直接回复数字选选项」",
          any("直接回复数字选选项" in v[0] for v in probes.values()))
    check("丙类记录到 set/clear 调用序（至少有 clear 发生过）",
          any(any(c and c[0] == "clear" for c in v[2]) for v in probes.values()
              if isinstance(v, list) and len(v) > 2 and isinstance(v[2], list)))


# ══════════════════════════════════════════════════════════════════════════════
# [5] 口径分歧
# ══════════════════════════════════════════════════════════════════════════════
def test_divergences():
    print("【5. 口径分歧：① 三份列表成员集合 · ③ 不可见仍返回 · ④ 首个同名早退 · ⑦ 空壳会话 · ⑫ 零交集】")
    town_ids = [nid for nid, _r in list(NPCS.items())[:8]]
    # `_hurry_section` 的 NPC 行用 `n['title']` → 合成用例必须取**带 title** 的 HIDDEN 条目
    hid_ids = [nid for nid, r in HIDDEN_NPCS.items() if r.get("title")][:3]
    hid_names = [HIDDEN_NPCS[n]["name"] for n in hid_ids]
    mid = "u1i4_dv"
    sa = _synth_sa("u1i4_dv_sa", town_ids[:3] + hid_ids)
    m = _synth_map(mid, npcs=town_ids[3:5], subareas=[sa])
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_dv=m)), \
            _Patch(W, "town_npc_visible", lambda *a, **k: False), \
            _Patch(random, "choice", lambda seq: list(seq)[0]), \
            _inject(_timed=_TimedRecorder()):
        live = Main(None)
        player = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 5,
                  "cur_map": mid, "cur_subarea": "u1i4_dv_sa"}
        live._player = lambda g, q, p=player: p
        cur = live._current_npcs(player)
        hurry = live._hurry_section(player, m, "u1i4_dv_sa", "g1", "w1", "npc")
        hry_lines = [ln for ln in hurry if re.match(r"^\s+\d+\.", ln)]
        check("口径分歧①：`_current_npcs` 成员集合**不含** HIDDEN_NPCS（可见性过滤全过）",
              cur == [], [r.get("name") for r in cur])
        check("口径分歧①：`_hurry_section` NPC 段**含** HIDDEN_NPCS 且豁免可见性过滤",
              len(hry_lines) == len(hid_ids)
              and all(nm in "".join(hry_lines) for nm in hid_names),
              (len(hry_lines), hry_lines))
        check("口径分歧①：含 HIDDEN 的两处（`_map_blocks`/`_hurry_section`）成员 > 不含的一处"
              "（`_current_npcs`）", len(hry_lines) == len(hid_ids) > len(cur),
              (len(hry_lines), len(cur)))
        blocks = live._map_blocks(player, m, "u1i4_dv_sa", "g1", "w1")
        blk = "\n".join(blocks)
        check("口径分歧①′：`_map_blocks` NPC 段与 `_hurry_section` 同口径（都只留 HIDDEN）",
              all(nm in blk for nm in hid_names)
              and all(NPCS[i]["name"] not in blk for i in town_ids[:3]),
              [nm for nm in hid_names if nm not in blk])
        check("口径分歧⑫：三表零交集（WILD ∩ HIDDEN == ∅）",
              not (set(WILD_NPCS) & set(HIDDEN_NPCS))
              and not (set(NPCS) & set(WILD_NPCS)) and not (set(NPCS) & set(HIDDEN_NPCS)),
              sorted(set(WILD_NPCS) & set(HIDDEN_NPCS))[:3])

        # ③『找』不可见也返回 + `_npc_absent`；列表里没有它
        player2 = {"cur_map": mid, "cur_subarea": "u1i4_dv_sa"}
        target = next((i for i in sa["npcs"] if i in NPCS), None)
        nid, npc = live._find_npc_in_map(player2, NPCS[target]["name"])
        check("口径分歧③：不可见的 NPC『找』仍返回 (nid, npc) 且置 `_npc_absent`",
              nid == target and player2.get("_npc_absent") is not None,
              (nid, player2.get("_npc_absent")))
        check("口径分歧③′：同一 NPC 不在 `_current_npcs` 列表里（列表只列在场者）",
              npc not in cur, npc)

    # ④ 野外首个同名早退（合成两同名：第一个在别图、第二个在本图）
    alias = "u1i4_alias_name"
    fake_wild = {"zz_first": {"name": alias, "map": "no_such_map_a"},
                 "zz_second": {"name": alias, "map": "oak_plain"}}
    live = Main(None)
    proxy = _WildProxy(fake_wild)
    with _inject(_wild=proxy):
        nid4, npc4 = live._find_wild_npc({"cur_map": "oak_plain", "cur_subarea": "",
                                          "level": 99}, alias, "g1", "w1")
    check("口径分歧④：野外『找』首个同名早退（第一个在别图 → (None, None)，不继续搜）",
          nid4 is None and npc4 is None, (nid4, npc4))
    check("口径分歧④′：同名表里第二个确实在本图（证明早退不是「都没命中」）",
          fake_wild["zz_second"]["map"] == "oak_plain")

    # ⑦ 空壳会话 `{}` 不清残留；坏值才清
    key = db.talk_state_key("g1", "w1")
    live = Main(None)
    for raw, expect_cleared, expect_ret in (("{}", False, {}),
                                            ("[]", True, None),
                                            ("0", True, None),
                                            ("null", True, None),
                                            ("{'npc': 1}", True, None)):
        db.init_db()
        db.set_event_state(key, raw)
        ret = live._talk_active("g1", "w1")
        cleared = db.get_event_state(key) is None
        check("口径分歧⑦：会话 %r → 返回 %r / 残留清除=%s" % (raw, expect_ret, expect_cleared),
              ret == expect_ret and cleared is expect_cleared, (ret, cleared))
    db.delete_event_state(key)
    check("口径分歧⑦′：`Cursor.of` 对空壳与坏值都还原不出（两种口径不可统一）",
          DENG.Cursor.of({}, subject_key="npc", node_key="node") is None
          and DENG.Cursor.of("[]", subject_key="npc", node_key="node") is None)


# ══════════════════════════════════════════════════════════════════════════════
# [6] 有牙反证
# ══════════════════════════════════════════════════════════════════════════════
def _quick_probe():
    """轻量丙类矩阵（teeth 用）：3 棵树 × 2 任务态 × 4 输入 + 合成树 4 条链。"""
    rows = []
    with _freeze_clock(), _Patch(random, "choice", lambda seq: list(seq)[0]):
        db.init_db()
        H.clean_db()
        H.make_player("g1", "w1", name="T", cls="战士", level=5)
        m = Main(None)
        log = _TalkLog(db)
        with _inject(db=log):
            for nid in ("npc_mayor", "npc_rune_master", "npc_baron"):
                npc = NPCS.get(nid)
                if not npc:
                    continue
                mid = npc.get("map") or "oak_town"
                sa = _first_sa(mid, nid)
                start = (_TREES.get(nid) or {}).get("start", "")
                for tag, quests in (("pending", {"main_quest": "q1", "main_status": "pending",
                                                 "completed_main": [], "side": {}}),
                                    ("done", {"main_quest": None, "main_status": "pending",
                                              "completed_main": ["q1"], "side": {}})):
                    for msg in ("1", "2", "3", "0"):
                        db.init_db()
                        db.delete_event_state(db.talk_state_key("g1", "w1"))
                        db.save_quests("g1", "w1", quests)
                        db.update_player("g1", "w1", cur_map=mid, cur_subarea=sa)
                        db.set_talk_state("g1", "w1", nid, start)
                        p2 = db.get_player("g1", "w1")
                        log.calls = []
                        try:
                            res = _drive(WC.talk_choice, m, FakeEvent("g1", "w1", msg),
                                         "g1", "w1", p2)
                        except Exception as exc:                        # noqa: BLE001
                            res = ["<exc:%s>" % type(exc).__name__]
                        rows.append(["%s:%s:%s" % (nid, tag, msg), "\n".join(res),
                                     _talk_state_raw(), list(log.calls)])
            syn = _probe_synth_tree(log, m)
            for key in sorted(syn):
                rows.append([key] + syn[key])
    return rows


def _quick_digest() -> str:
    return sha256(json.dumps(_quick_probe(), sort_keys=True, ensure_ascii=False))


def _break_need():
    """破坏①：need 判定忽略全部条件（引擎 `satisfied` 恒 True）。"""
    return _Patch(DENG.Dialogue, "satisfied", lambda self, need, ctx: True)


def _break_text_variant():
    """破坏②：`texts` 变体从**末条**往前取（顺序敏感）。"""
    def _text(self, node, ctx):
        for variant in list(node.get("texts") or [])[::-1]:
            if self.satisfied(variant.get("need"), ctx):
                return variant["text"]
        src = node.get("text_from")
        if isinstance(src, str) and self._sources is not None:
            gen = self._sources.get(src)
            if gen is not None:
                auto = gen(node, ctx)
                if auto:
                    return auto
        return node.get("text", self._fallback)
    return _Patch(DENG.Dialogue, "text", _text)


def _break_next_of():
    """破坏③：`next_of` 忽略 `failed`（`fail_next` 永不生效）。"""
    def _next_of(self, option, *, failed=False):
        return option.get("next", self._end)
    return _Patch(DENG.Dialogue, "next_of", _next_of)


def _break_is_end():
    """破坏④：`is_end` 恒 False（结束哨兵失效）。"""
    return _Patch(DENG.Dialogue, "is_end", lambda self, node_id: False)


def _break_current_npcs_hidden():
    """破坏⑤（附加）：`_current_npcs` 把 `HIDDEN_NPCS` 也并进来（口径分歧 ① 被抹平）。"""
    orig = WC._current_npcs

    def _cur(self, player):
        rows = orig(self, player)
        mid = player["cur_map"]
        sa_id = player.get("cur_subarea") or ""
        for nid, row in HIDDEN_NPCS.items():
            if nid in _npcs_in_place(_MAP_BY_ID.get(mid, {}), sa_id) and row not in rows:
                rows = rows + [row]
        return rows
    return _Patch(WC, "_current_npcs", _cur)


def _probe_current_npcs_hidden():
    """成员集合探针：`_current_npcs` 与冻结旧实现逐格比出现差异即 True（口径分歧 ①）。"""
    town_ids = [nid for nid, _r in list(NPCS.items())[:8]]
    hid_ids = [nid for nid, r in HIDDEN_NPCS.items() if r.get("title")][:3]
    m = _synth_map("u1i4_teeth", subareas=[_synth_sa("u1i4_teeth_sa",
                                                     town_ids[:3] + hid_ids)])
    with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_teeth=m)), \
            _Patch(W, "town_npc_visible", lambda *a, **k: False):
        player = {"cur_map": "u1i4_teeth", "cur_subarea": "u1i4_teeth_sa"}
        new = _run(WC._current_npcs, player)
        old = _run(OLD["_current_npcs"], player)
    return new != old


_BREAKS = {
    "need_忽略(satisfied 恒 True)": _break_need,
    "变体取末条(Dialogue.text)": _break_text_variant,
    "next_of_丢 fail_next": _break_next_of,
    "is_end_恒 False": _break_is_end,
}

#: 「需接上引擎路由才咬得住」的破坏：`next_of` 是 C 段（`talk_choice`）**改后**才走的路径 ——
#: `phase == "landed"` 前不启用它的「必须变红」断言（否则红基线档会假红）。
_LANDED_ONLY_BREAKS = {"next_of_丢 fail_next"}


def test_teeth():
    print("【6. 有牙反证：破坏 5 处 → 对应探针必须变红（原地还原 + 全程零写盘）】")
    before = {f: _file_sha(f) for f in READONLY_FILES}
    base = _quick_digest()
    check("未破坏时轻量丙类探针基线已取到", bool(base), base[:12])

    for name, breaker in _BREAKS.items():
        if name in _LANDED_ONLY_BREAKS and _PIN["phase"] != "landed":
            print("     ⓘ 破坏 `%s`：phase=%r（`talk_choice` 还没接 `next_of`）→ 该齿暂不启用"
                  % (name, _PIN["phase"]))
            check("还原 `%s` 后探针回绿" % name, _quick_digest() == base)
            continue
        with breaker():
            red = _quick_digest()
        print("     破坏 `%s`：预期变红 / 实测 %s"
              % (name, "变红 ✅" if red != base else "仍绿 ❌"))
        check("破坏 `%s` → 丙类探针必须变红（预期变红 / 实测变红）" % name, red != base)
        check("还原 `%s` 后探针回绿" % name, _quick_digest() == base)

    # ⑤（附加）：`_current_npcs` 并入 HIDDEN → 21 段差分里的成员集合探针红
    check("未破坏时 `_current_npcs` 成员集合探针为 False（旧 == 新）",
          _probe_current_npcs_hidden() is False)
    with _break_current_npcs_hidden():
        red5 = _probe_current_npcs_hidden()
    print("     破坏 `_current_npcs`(并入 HIDDEN)：预期变红 / 实测 %s"
          % ("变红 ✅" if red5 else "仍绿 ❌"))
    check("破坏 `_current_npcs`(并入 HIDDEN) → 成员集合探针必须变红（口径分歧 ①）",
          red5 is True)
    check("还原 `_current_npcs` 后成员集合探针回绿", _probe_current_npcs_hidden() is False)

    print("  ── 多故障场景（只坏一处证明不了「各管一段」）──")
    with _break_need(), _break_is_end():
        d1, d2 = _quick_digest(), _probe_current_npcs_hidden()
    check("两处同坏（need + is_end）：丙类探针变红，成员集合探针**仍绿**（各管一段）",
          d1 != base and d2 is False, (d1 != base, d2))
    with _break_current_npcs_hidden():
        d1, d2 = _quick_digest(), _probe_current_npcs_hidden()
    check("换一处同坏（并入 HIDDEN）：成员集合探针变红，丙类探针**仍绿**",
          d1 == base and d2 is True, (d1 == base, d2))

    after = {f: _file_sha(f) for f in READONLY_FILES}
    check("反证全程零写盘：源文件 sha256 前后一致", before == after,
          [f for f in READONLY_FILES if before[f] != after[f]])


# ══════════════════════════════════════════════════════════════════════════════
# [7] 顺序断言（② 限时续号 · ③ side_menu 插入位置 · ⑤ need 短路序）
# ══════════════════════════════════════════════════════════════════════════════
def test_order():
    print("【7. 顺序断言：② 限时续号 · ③ side_menu 插入原位置 · ⑤ need 短路序】")
    mid = "u1i4_ord"
    ids = list(NPCS)[:5]
    overlay = list(W.ALL_WILD)[:2]
    m_f = _synth_map(mid, subareas=[_synth_sa("u1i4_ord_sa", ids)])
    m_r = _synth_map(mid, subareas=[_synth_sa("u1i4_ord_sa", list(reversed(ids)))])
    rec = _TimedRecorder(_mk_events(2, mid, overlay))
    live = Main(None)
    player = {"qq_id": "w1", "group_id": "g1", "name": "T", "level": 1,
              "cur_map": mid, "cur_subarea": "u1i4_ord_sa"}
    live._player = lambda g, q, p=player: p

    def _nums(mm):
        with _Patch(WC._cat_space, "MAP_BY_ID", dict(_MAP_BY_ID, u1i4_ord=mm)), \
                _Patch(W, "town_npc_visible", lambda *a, **k: True), \
                _Patch(random, "choice", lambda seq: list(seq)[0]), _inject(_timed=rec):
            lines = live._start_talk_list("g1", "w1")
        out = []
        for ln in lines:
            head = ln.split(".", 1)[0].strip()
            if head.isdigit():
                out.append((int(head), ln.split(".", 1)[1].strip()))
        return out

    fwd, rev = _nums(m_f), _nums(m_r)
    check("顺序②：限时项续号在静态之后（1..N+M）",
          [n for n, _t in fwd] == list(range(1, len(ids) + 3)), [n for n, _t in fwd])
    check("顺序②：静态清单倒序 → 编号-内容对应整体改变（门禁真在看序）",
          [t for _n, t in fwd] != [t for _n, t in rev]
          and [t for _n, t in fwd][:5] == list(reversed([t for _n, t in rev][:5])),
          ([t for _n, t in fwd][:2], [t for _n, t in rev][:2]))

    # ③ side_menu 插回**原位置**（不是追加末尾）
    dlg = {"start": "s", "nodes": {"s": {"text": "t", "options": [
        {"text": "A", "next": "s"},
        {"text": "MENU", "next": "s", "side_menu": {}},
        {"text": "C", "next": "s"},
    ]}}}
    node = dlg["nodes"]["s"]
    subs = [{"text": "m1", "next": "s"}, {"text": "m2", "next": "s"}]
    ctx = {"side_menu_expand": lambda opt: subs}
    opts = DLG.visible_options(dlg, node, ctx)
    check("顺序③：side_menu 展开的 2 项出现在**原位置**（A, m1, m2, C）",
          [o.get("text") for o in opts] == ["A", "m1", "m2", "C"],
          [o.get("text") for o in opts])
    check("顺序③′：展开项 `is` 回调给的对象（I8 对象标识）",
          opts[1] is subs[0] and opts[2] is subs[1])

    # ⑤ need 键序 = 短路序（前键假 → 后键谓词一次都没被调用）
    calls = []

    class _Conds:
        def get(self, key):
            def _fn(ctx, value, _k=key):
                calls.append(_k)
                return _k != "b"
            return _fn

    eng = DENG.Dialogue(end_marker="__end__", fallback_text="……", conditions=_Conds(),
                        unknown=lambda k, v: True)
    eng.satisfied({"a": 1, "b": 1, "c": 1}, {})
    check("顺序⑤：need 短路序 = 键插入序（b 假 → 调 a,b；c 不被调用）",
          calls == ["a", "b"], calls)
    calls.clear()
    eng.satisfied({"c": 1, "b": 1, "a": 1}, {})
    check("顺序⑤′：改 dict 序 → 调用序随之改（c,b；不重排）", calls == ["c", "b"], calls)


# ══════════════════════════════════════════════════════════════════════════════
# [8] 只读
# ══════════════════════════════════════════════════════════════════════════════
def _check_readonly(before):
    print("【8. 只读：全程零写盘】")
    after = {f: _file_sha(f) for f in READONLY_FILES}
    bad = [f for f in READONLY_FILES if before[f] != after[f]]
    check("跑完全程 %d 个源文件 sha256 前后一致" % len(READONLY_FILES), not bad, bad)
    for f in READONLY_FILES:
        print("     %-32s %s" % (f, after[f]))


def main() -> int:
    print("==" * 36)
    print("U1-I4 冻结门禁③：世界侧装配（content/world_cmds.py 29 段：甲 11 / 乙 10 / 丙 8）")
    print("==" * 36)
    print("phase = %r · GWEN_GAME_DB = %s" % (_PIN["phase"], os.environ.get("GWEN_GAME_DB")))
    before = {f: _file_sha(f) for f in READONLY_FILES}
    test_frozen_pins()
    test_alpha_beta()
    test_render_literals()
    test_aux()
    test_golden_probes()
    test_divergences()
    test_teeth()
    test_order()
    _check_readonly(before)
    print(f"\n{'-' * 46}\n结果：通过 {PASS} / 共 {PASS + FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
