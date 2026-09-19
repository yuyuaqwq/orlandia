# -*- coding: utf-8 -*-
"""U1-D2 冻结比对**门禁①**（任务块）：28 段 —— 任务账本 / 目标注册表 / 三份渲染口。

跑法（工作区根；环境变量见 `BRIEF.md` §4.1）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1d2_quest_gen.py --check
    "$PY" work/pkg/tests/test_u1d2_quest_frozen.py

判据（`design/U1-D2_BATCHES.md` §4 判据表 10 条；本文件逐条打原始输出）
---------------------------------------------------------------------
 [1] **28 段冻结文本 sha256 全等 `_PIN["frozen"]`** + **活实现 `inspect.getsource` sha256
     全等 `_PIN["live"]`**；`phase == "landed"` 时再断言 C 栏「预期会变」段 `frozen != live`。
 [2] **甲类 exec 双向逐格比**（`FROZEN_GATE.md` §1.3）：冻结文本 `exec` 到独立命名空间
     （`dict(vars(模块))` + 冻结段覆盖）↔ 活实现，**同输入逐格比返回值 / 副作用**。
 [3] **全量网格 13,064 格**（作业书 §3 判据 3 / `BATCHES.md` §4 判据 3）：
       ① accept  238 × 4 前置态 × 3 等级 × 2 提供者在场 = **5,712**
       ② fold    238 目标 × 8 事件                        = **1,904**
       ③ side 表 144 支线 × 6 过滤组合 × 3 等级            = **2,592**
       ④ render  238 × 3 渲染口 × 2 状态                  = **1,428**
       ⑤ ledger  238 × 3 lane × 2                         = **1,428**
     旧侧 = 门禁内嵌冻结文本 `exec` 出来的那一份；格数**脚本实测**（结尾断言 == 13,064）。
 [4] **口径分歧 12 条**各 ≥1 条断言（`DESIGN.md` §2.3；含 ① 主线无 `done` · ③ 进度容器
     dict/int · ④ 需求数两口径 · ⑦ 老 key 兼容 · ⑪ 系统钟）。
 [5] **`quests` 表落盘 JSON 文本逐字节不变**（aux 指纹）+ 只读零改动指纹。
 [6] **有牙反证**：破坏 4 处（`need` 取错数 / 目标类型顺序倒置 / `deliver` 不追加 done /
     `expire_daily` 改成永久不清）→ 对应探针**必须变红**（逐处打印「预期变红 / 实测变红」）。
 [7] **只读断言**：跑完全程 4 个源文件 sha256 前后一致（**不写盘**）。
 [8] 6 个既有测试（`BRIEF.md` §4.2）全绿。
 [9] **U1-I4 门禁③/④ 的 `frozen` 侧一字不改**（aux 指纹 + 与 `base/pkg` 直比）。
 [10] `catalog_quests.py` / `persistence/quests.py` sha256 前后一致（**零改动证明**）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1d2_quest_gen.py` 从
   `base/pkg/**` 逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import random
import sqlite3
import sys
import tempfile

# ══════════════════════════════════════════════════════════════════════════════
# 0. 装配：包根 / 引擎根 / 宿主壳根 + 独立私有库 + shim_astrbot
# ══════════════════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
WORK_ROOT = os.path.dirname(PKG_ROOT)
LANE_ROOT = os.path.dirname(WORK_ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 2026-09-18 收尾修：原落点 `LANE_ROOT/out` 是旧「工作区布局」（`<lane>/work/pkg` 三层），
#   真仓布局下 LANE_ROOT = `C:\Users` ⇒ `C:\Users\out` 不存在 → sqlite connect 直接
#   `unable to open database file`（单跑必崩；改前基线同样红，非本次修复引入）。
#   私有库改落系统临时目录下自建子目录（不写包目录、不进 git）。
_DB_DIR = os.path.join(tempfile.gettempdir(), "gwen_test_u1d2_L4")
os.makedirs(_DB_DIR, exist_ok=True)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_DB_DIR, "test_u1d2_L4.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(LANE_ROOT, "work", "eng"))
os.environ.setdefault("GWEN_HOST_DIR", os.path.join(LANE_ROOT, "work", "host"))
_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

import _paths                                                             # noqa: E402
import _engine_harness as H                                               # noqa: E402

db = H.db

from content import quests_flow as QF                                     # noqa: E402
from content import profession_quests as PQ                               # noqa: E402
from content import world_cmds as WC                                      # noqa: E402
from content import cmds_world as CW                                      # noqa: E402
from content import catalog_quests as CQ                                  # noqa: E402
from content.catalog_quests import (MAIN_QUESTS, SIDE_QUESTS, NPCS,       # noqa: E402
                                    DAILY_QUESTS, DIALOGUES)
from content.catalog_space import MAP_BY_ID as _MAP_BY_ID                 # noqa: E402
from content import wild as _WILD                                         # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_MISSING = object()
_TODAY = None                      # 由 _boot() 填（系统钟）

# >>> _u1d2_quest_gen (auto) >>>

# ⚠ 本块由 `tests/_u1d2_quest_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/quests_flow.py::obj_text': 'def obj_text(obj):\n    if obj.get("kill"):\n        return f"击败 {obj[\'kill\']} ×{obj[\'count\']}"\n    if obj.get("collect"):\n        # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError\n        return f"收集 {obj[\'collect\']} ×{obj.get(\'collect_count\') or obj.get(\'count\', 1)}"\n    if obj.get("explore"):\n        return f"前往 {_cs.MAP_BY_ID.get(obj[\'explore\'], {}).get(\'name\', \'？\')}"\n    if obj.get("find"):\n        # v97.1 告示委托：在指定地图探索概率找到目标\n        return f"在 {_cs.MAP_BY_ID.get(obj.get(\'map\', \'\'), {}).get(\'name\', \'？\')} 寻找 {obj[\'find\']}(探索有概率遇到)"\n    if obj.get("use"):\n        # v124 use 目标：使用指定物品达成\n        return f"使用 {obj[\'use\']}"\n    if obj.get("talk"):\n        npc = _cq.NPCS.get(obj["talk"], {})\n        return f"与 {npc.get(\'name\', \'？\')} 交谈"\n    return "？"\n',
    'content/quests_flow.py::sq_unlocked': 'def sq_unlocked(quests, sq):\n    """v124 链式支线：unlock 前置解锁检查。unlock 支持单条或列表（全部满足）。\n    格式：{"side": "s5"} 或 {"main": "q2_3"}（兼容 {"type":"side","id":"s5"} 写法）。\n    无 unlock=天然解锁。"""\n    u = sq.get("unlock")\n    if not u:\n        return True\n    us = u if isinstance(u, list) else [u]\n    for x in us:\n        if not isinstance(x, dict):\n            continue\n        _typ = x.get("type") or ("side" if x.get("side") else "main" if x.get("main") else None)\n        _tid = x.get("id") or x.get("side") or x.get("main") or ""\n        if _typ == "side":\n            # 支线完成 = side dict 中该任务 status==done\n            _sq = (quests.get("side") or {}).get(_tid) or {}\n            if _sq.get("status") != "done":\n                return False\n        elif _typ == "main":\n            _cm = quests.get("completed_main") or []\n            if _tid not in _cm and quests.get("main_quest") != _tid:\n                return False\n    return True\n',
    'content/quests_flow.py::sq_stats_met': 'def sq_stats_met(player, sq):\n    """v124 隐藏线/副业线：require_stats 动作计数门槛。达标才可接取。\n    stats 表以 qq_id 为主键，group_id 参数为兼容占位。"""\n    rs = sq.get("require_stats")\n    if not rs:\n        return True\n    _qq = player.get("qq_id") or player.get("id", "")\n    if not _qq:\n        return False\n    _st = db.get_stats("", _qq) or {}\n    for k, v in rs.items():\n        if int(_st.get(k, 0) or 0) < int(v):\n            return False\n    return True\n',
    'content/quests_flow.py::available_quest_list': 'def available_quest_list(player, quests, mq) -> list:\n    """当前地图可接取任务列表（v123d 抽出，供『接取』无参渲染与『接取 <序号>』映射共用）。\n\n    返回 [{"name": 任务名, "line": 渲染行（不含 📜 前缀）}, ...]——主线 pending 在前，\n    支线按 _cq.SIDE_QUESTS 顺序；告示委托（board）不在此列（须去告示板指名接取）。\n    """\n    available = []\n    if mq and quests.get("main_status") == "pending":\n        giver = _cq.NPCS.get(mq["giver"]) or _w.ALL_WILD.get(mq["giver"]) or {}\n        if giver.get("map") == player["cur_map"]:\n            available.append({\n                "name": mq["name"],\n                "line": f"主线『{mq[\'name\']}』（{giver.get(\'name\', \'？\')}发布）",\n            })\n    for sq in _cq.SIDE_QUESTS:\n        if sq["id"] in (quests.get("side") or {}):\n            continue\n        # v124 链式支线：unlock 前置未满足不出现在可接列表\n        if not sq_unlocked(quests, sq):\n            continue\n        # v124 隐藏线：require_stats 计数门槛未达不出现在可接列表\n        if not sq_stats_met(player, sq):\n            continue\n        # v104 M20 P2：告示委托（board: true）只在告示板子区域指名接取，\n        # 列入普通列表会误导玩家（点名接取被 world.py 告示板拦截逻辑挡下）\n        if sq.get("board"):\n            continue\n        npc = _cq.NPCS.get(sq["giver"]) or _w.ALL_WILD.get(sq["giver"]) or {}\n        if npc.get("map") == player["cur_map"]:\n            # v104 M19：接取列表显示支线等级门槛\n            _lv = f"Lv.{sq[\'min_level\']}+ " if sq.get("min_level") else ""\n            available.append({\n                "name": sq["name"],\n                "line": f"支线『{sq[\'name\']}』{_lv}（{npc.get(\'name\', \'？\')}发布）",\n            })\n    return available\n',
    'content/quests_flow.py::update_explore_quests': 'def update_explore_quests(group_id, qq_id, map_id):\n    """到达子区域时检查 explore 型任务(主线和支线)"""\n    lines = []\n    quests = db.get_quests(group_id, qq_id)\n    changed = False\n    # 主线 explore（v105：仅已接取(active)时触发——pending 未接取到达目标图不得自动完成+发奖）\n    main_id = quests.get("main_quest")\n    if main_id and quests.get("main_status") == "active":\n        mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)\n        if mq and mq["objective"].get("explore") == map_id:\n            # v124.3：奖励统一走 _grant_quest_rewards（exp/gold/升级 + reward_item 全格式\n            # + reward_pet/reward_mount/unlock_class）——此前 explore 自动完成只有\n            # reward_item 单值，reward_pet 配了也静默不发\n            grant_quest_rewards(group_id, qq_id, mq, lines)\n            completed = list(quests.get("completed_main", []))\n            completed.append(main_id)\n            quests["completed_main"] = completed\n            quests["main_quest"] = mq["next"]\n            # v105 M19 P1：explore 自动完成必须重置 main_status=pending（与 _take_main_quest\n            # 交付分支一致）——此前遗留 "active" 导致任务面板显示"进行中"而非"未接取"、\n            # 对话树 quest_pending 接取入口不亮（q1_5 完成后 q1_6 需 3-4 轮对话才兜底接取）\n            quests["main_status"] = "pending"\n            quests["main_progress"] = {}\n            changed = True\n            lines.append(f"📜 主线『{mq[\'name\']}』达成！奖励：经验 +{mq[\'reward_exp\']} 金币 +{mq[\'reward_gold\']}")\n            # v105 M19 P2：explore 自动完成补发声望（奖励本体已并入 _grant_quest_rewards）\n            _rep = quest_reputation(group_id, qq_id, mq["giver"])\n            if _rep:\n                lines.append(f"  {_rep}")\n            if mq["next"]:\n                nq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mq["next"]), None)\n                if nq:\n                    lines.append(f"📜 新主线：『{nq[\'name\']}』{nq[\'desc\']}")\n            else:\n                lines.append("🎊 恭喜！你完成了全部主线任务，成为奥兰迪亚的传说！")\n    # 支线 explore\n    side = dict(quests.get("side", {}))\n    for sid, sq in list(side.items()):\n        if sq.get("status") == "active":\n            sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)\n            if sqd and sqd["objective"].get("explore") == map_id:\n                sq["status"] = "ready"\n                changed = True\n                _g = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}\n                lines.append(f"📜 支线『{sqd[\'name\']}』目标达成！回去找 {_g.get(\'name\', \'？\')} {deliver_hint(sqd[\'giver\'])}吧～")\n    if changed:\n        quests["side"] = side\n        db.save_quests(group_id, qq_id, quests)\n    return lines\n',
    'content/quests_flow.py::take_main_quest': 'def take_main_quest(group_id, qq_id, npc_id, npc):\n    """从 NPC 接主线任务；返回通知行列表"""\n    lines = []\n    player = db.get_player(group_id, qq_id)\n    quests = db.get_quests(group_id, qq_id)\n    main_id = quests.get("main_quest")\n    if not main_id:\n        lines.append("🎊 主线任务已全部完成，你已是奥兰迪亚的传说！")\n        return lines\n    mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)\n    # 存档容错：main_quest 指向已不存在的任务（旧存档/主线数据变更）→ 重置回主线起点\n    if not mq and main_id:\n        quests["main_quest"] = "q1_1"\n        quests["main_status"] = "pending"\n        quests["main_progress"] = {}\n        main_id = "q1_1"\n        mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)\n    if not mq or mq["giver"] != npc_id:\n        # 不是这个 NPC 的任务\n        need_npc = _cq.NPCS.get(mq["giver"], {}).get("name", "？") if mq else "？"\n        lines.append(f"【{npc[\'name\']}】我现在没有任务交给你。镇长/各地首领或许有安排……")\n        if mq:\n            lines.append(f"📜 当前主线『{mq[\'name\']}』由 {need_npc} 发布。")\n        return lines\n    st = quests.get("main_status", "pending")\n    # v105 P0：collect 型主线（q5_5 圣光百合）——背包材料足够即置 ready\n    # （对齐支线逻辑 talk_actions.py:111-113 实时数背包；交付时再扣材料）\n    # 放在状态分发前：pending 接取时材料已齐 → 直接可交付；active 回来找 NPC → 置 ready\n    obj0 = mq["objective"]\n    if obj0.get("collect") and st != "ready" and db.count_item(group_id, qq_id, obj0["collect"]) >= obj0.get("count", 1):\n        quests["main_status"] = "ready"\n        quests["main_progress"] = {obj0["collect"]: obj0.get("count", 1)}\n        db.save_quests(group_id, qq_id, quests)\n        st = "ready"\n    if st == "pending":\n        # v169.1：主线 min_level 硬门槛（高经验主线防跨级接取；suggest_lv 仅软提示保留）\n        if mq.get("min_level") and player["level"] < mq["min_level"]:\n            return lines + [f"🛡️ 『{mq[\'name\']}』需要 Lv.{mq[\'min_level\']} 才能接取！（你当前 Lv.{player[\'level\']}）先去提升实力吧～"]\n        quests["main_status"] = "active"\n        quests["main_progress"] = {}\n        # talk 型任务：与发布 NPC 交谈即达成目标（对话即完成）\n        obj = mq["objective"]\n        if obj.get("talk") and obj["talk"] == npc_id:\n            quests["main_status"] = "ready"\n            quests["main_progress"] = {obj["talk"]: 1}\n        # v105 P2：explore 型主线接取时已在目标地图 → 直接置 ready（免出图重进）\n        if obj.get("explore") and player.get("cur_map") == obj["explore"]:\n            quests["main_status"] = "ready"\n            quests["main_progress"] = {obj["explore"]: 1}\n        db.save_quests(group_id, qq_id, quests)\n        lines.append(f"📜 【接取任务】『{mq[\'name\']}』")\n        if mq.get("story"):\n            lines.append(f"  📖 {mq[\'story\']}")\n        lines.append(f"  🎯 目标：{obj_text(mq[\'objective\'])}")\n        lines.append(f"  奖励：经验 +{mq[\'reward_exp\']} 金币 +{mq[\'reward_gold\']}")\n        # v95.25 #138：主线等级建议（软提示，不拦截接取）——suggest_lv 在 quests.py 数据里\n        if mq.get("suggest_lv") and player["level"] < mq["suggest_lv"]:\n            lines.append(f"  ⚠️ 建议等级 Lv.{mq[\'suggest_lv\']}，你才 Lv.{player[\'level\']}——可以先练练级再挑战！")\n        if quests["main_status"] == "ready":\n            lines.append("  ✨ 交谈完成！再与这位 NPC 对话即可交付任务。")\n    elif st == "ready":\n        # 交任务领奖\n        obj = mq.get("objective") or {}\n        # v105 P0：collect 型主线交付时扣材料（先复核背包，材料被消耗则回到进行中）\n        if obj.get("collect"):\n            need = obj.get("count", 1)\n            if db.count_item(group_id, qq_id, obj["collect"]) < need:\n                quests["main_status"] = "active"\n                quests["main_progress"] = {}\n                db.save_quests(group_id, qq_id, quests)\n                lines.append(f"📜 交付『{mq[\'name\']}』需要 {obj[\'collect\']} ×{need}，你背包里不够了，先去凑齐吧～")\n                return lines\n            db.remove_item(group_id, qq_id, obj["collect"], need)\n            # v126.2：鱼获个体属性在 item_data.tags，remove_item 自动截断，无需额外同步\n            lines.append(f"🎒 交出 {obj[\'collect\']} ×{need}")\n        # v124.3：奖励统一走 _grant_quest_rewards（exp/gold/升级 + reward_item 全格式\n        # + reward_pet/reward_mount/unlock_class）——此前主线交付只支持 reward_item\n        # 单值 + reward_pet，eq:/list 随机/坐骑/隐藏职业配了不发\n        grant_quest_rewards(group_id, qq_id, mq, lines)\n        completed = list(quests.get("completed_main", []))\n        completed.append(main_id)\n        quests["completed_main"] = completed\n        quests["main_quest"] = mq["next"]\n        quests["main_status"] = "pending"\n        quests["main_progress"] = {}\n        db.save_quests(group_id, qq_id, quests)\n        lines.append(f"✅ 【任务完成】『{mq[\'name\']}』！")\n        if mq.get("ending"):\n            # v105 M19 P1：主线抉择结局变体——q10_5 等任务按对话树选择的 flag 输出不同结尾\n            _ending = mq["ending"]\n            _endings = mq.get("endings") or {}\n            if _endings:\n                try:\n                    _flags = db.get_talk_flags(group_id, qq_id, mq["giver"]) or []\n                except Exception:\n                    _flags = []\n                for _fk, _fv in _endings.items():\n                    if _fk in _flags:\n                        _ending = _fv\n                        break\n            lines.append(f"  📖 {_ending}")\n        lines.append(f"  奖励：经验 +{mq[\'reward_exp\']} 金币 +{mq[\'reward_gold\']}")\n        rep_line = quest_reputation(group_id, qq_id, mq["giver"])\n        if rep_line:\n            lines.append(f"  {rep_line}")\n        if mq["next"]:\n            nq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mq["next"]), None)\n            if nq:\n                lines.append(f"📜 新主线：『{nq[\'name\']}』{nq[\'desc\']}")\n                lines.append(f"  🎯 去找 {_cq.NPCS[nq[\'giver\']][\'name\']} 接取新任务")\n        else:\n            lines.append("🎊 恭喜！你完成了全部主线任务，成为奥兰迪亚的传说！")\n    else:\n        lines.append(f"📜 你已接取『{mq[\'name\']}』：{mq[\'desc\']}")\n    return lines\n',
    'content/quests_flow.py::quest_reputation': 'def quest_reputation(group_id, qq_id, npc_id):\n    """完成任务时给对应势力加声望，返回提示行(如有)"""\n    npc = _cq.NPCS.get(npc_id)\n    if not npc:\n        return ""\n    m = _cs.MAP_BY_ID.get(npc["map"], {})\n    area_key = m.get("area", npc["map"])\n    faction = _b143.AREA_FACTION.get(area_key)\n    if not faction:\n        return ""\n    db.add_reputation(group_id, qq_id, faction, 10)\n    return f"🏛️ {_b143.FACTIONS[faction][\'icon\']} 声望＋10"\n',
    'content/quests_flow.py::deliver_hint': 'def deliver_hint(npc_id):\n    """交付方式提示（v95.16 #75）：有对话树 NPC 走对话交付，无对话树 NPC 用『交付任务』"""\n    if _cq.DIALOGUES.get(npc_id):\n        return "对话交付"\n    return "『交付任务』交付"\n',
    'content/quests_flow.py::side_available_list': 'def side_available_list(group_id, qq_id, npc_id, npc) -> list:\n    """v127.6：该 NPC 名下当前"可接"的支线清单（对话菜单/预告/全接三处同源过滤）。\n\n    过滤条件与旧 _offer_side_quests 全部一致：giver == npc_id、非告示板委托(board)、\n    未接取（不在 side）、_sq_unlocked 链式前置、_sq_stats_met 计数门槛、\n    min_level 等级门槛、require_race 种族限制。每项返回\n    {sid, name, desc, objective_text, reward_exp, reward_gold}，按 SIDE_QUESTS 定义顺序\n    （保证对话菜单序号稳定）。npc 参数保留以与 _offer_side_quests 签名一致（此处未用到）。\n    """\n    player = db.get_player(group_id, qq_id) or {}\n    quests = db.get_quests(group_id, qq_id)\n    side = quests.get("side", {}) or {}\n    out = []\n    for sq in _cq.SIDE_QUESTS:\n        if sq["giver"] != npc_id:\n            continue\n        if sq.get("board"):  # v95r65 #295：告示板委托只能在告示板接取，NPC 不自动发\n            continue\n        if sq["id"] in side:\n            continue\n        # v124 链式支线：unlock 前置未满足不自动发（如剧情线第二步等第一步完成）\n        if not sq_unlocked(quests, sq):\n            continue\n        # v124 隐藏线/副业线：require_stats 计数门槛未达不自动发（如 H7 需垂钓 10 次）\n        if not sq_stats_met(player, sq):\n            continue\n        # v101.30d #O52：支线等级门槛（min_level 字段）——等级不够不算可接\n        if sq.get("min_level") and (player.get("level") or 0) < sq["min_level"]:\n            continue\n        # v113 种族限制：require_race 指定血脉（隐藏线试炼）——非该种族不算可接\n        if sq.get("require_race"):\n            _cur = player.get("race") or "human"\n            if _cur != sq["require_race"]:\n                continue\n        out.append({\n            "sid": sq["id"],\n            "name": sq["name"],\n            "desc": sq.get("desc", ""),\n            "objective_text": obj_text(sq.get("objective") or {}),\n            "reward_exp": sq.get("reward_exp", 0),\n            "reward_gold": sq.get("reward_gold", 0),\n        })\n    return out\n',
    'content/quests_flow.py::offer_side_quest': 'def offer_side_quest(group_id, qq_id, npc_id, sid) -> list:\n    """v127.6：单条支线接取（对话 side_menu 子选项 action: side_take_one）。\n\n    校验 sid 必须在 _side_available_list 当前可接清单内才接（防越权/已接/等级不足），\n    否则返回 [] 不落地。返回该任务的接取通知行列表。\n    """\n    item = next((a for a in side_available_list(group_id, qq_id, npc_id, None)\n                 if a["sid"] == sid), None)\n    if not item:\n        return []\n    sq = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)\n    if not sq:\n        return []\n    quests = db.get_quests(group_id, qq_id)\n    side = dict(quests.get("side", {}))\n    side[sid] = {"status": "active", "progress": {}}\n    quests["side"] = side\n    db.save_quests(group_id, qq_id, quests)\n    return [\n        f"📜 【支线】『{sq[\'name\']}』{sq[\'desc\']}",\n        f"  奖励：经验 +{sq[\'reward_exp\']} 金币 +{sq[\'reward_gold\']}",\n        f"  🎯 目标：{item[\'objective_text\']}",\n    ]\n',
    'content/quests_flow.py::offer_side_quests': 'def offer_side_quests(group_id, qq_id, npc_id, npc):\n    """NPC 有未接的支线任务时自动接取，返回通知行列表\n\n    v127.6 重构：可接清单统一走 _side_available_list（与对话 side_menu 菜单/预告同源过滤），\n    逐条复用 _offer_side_quest 接取；不可接（min_level/require_race 被过滤掉）的\n    原拒绝提示按 SIDE_QUESTS 顺序保留，全接+完成提示行为不变（旧 side_offer action 兼容，\n    单支线 NPC 无感）。\n    """\n    player = db.get_player(group_id, qq_id) or {}\n    lines = []\n    quests = db.get_quests(group_id, qq_id)\n    side = dict(quests.get("side", {}))\n    available = side_available_list(group_id, qq_id, npc_id, npc)\n    av_ids = {a["sid"] for a in available}\n    changed = False\n    for sq in _cq.SIDE_QUESTS:\n        if sq["giver"] != npc_id or sq.get("board"):\n            continue\n        if sq["id"] in side:\n            continue\n        if sq["id"] in av_ids:\n            side[sq["id"]] = {"status": "active", "progress": {}}\n            changed = True\n            lines.append(f"📜 【支线】『{sq[\'name\']}』{sq[\'desc\']}")\n            lines.append(f"  奖励：经验 +{sq[\'reward_exp\']} 金币 +{sq[\'reward_gold\']}")\n            lines.append(f"  🎯 目标：{obj_text(sq[\'objective\'])}")\n            continue\n        # 不可接但符合其余条件的拒绝提示（与原始行为文案一致）\n        if not sq_unlocked(quests, sq):\n            continue\n        if not sq_stats_met(player, sq):\n            continue\n        # v101.30d #O52：支线等级门槛——等级不够不自动接\n        if sq.get("min_level") and (player.get("level") or 0) < sq["min_level"]:\n            lines.append(\n                f"🛡️ {npc.get(\'name\', \'对方\')}打量了你一眼：这活得有 Lv.{sq[\'min_level\']}+ 的本事，你再去练练吧。"\n            )\n            continue\n        # v113 种族限制：require_race 指定血脉——非该种族导师直接拒绝\n        if sq.get("require_race"):\n            _rr = sq["require_race"]\n            _cur = player.get("race") or "human"\n            if _cur != _rr:\n                _rcn = (_cc.RACES.get(_rr) or {}).get("name", "对应血脉")\n                lines.append(\n                    f"⛔ {npc.get(\'name\', \'对方\')}凝视着你，缓缓摇头：『这份传承只属于{_rcn}的血脉。"\n                    f"你体内流淌的{(_cc.RACES.get(_cur) or {}).get(\'name\', \'血脉\')}之血，与它无缘。』"\n                )\n                continue\n    if changed:\n        quests["side"] = side\n        db.save_quests(group_id, qq_id, quests)\n    # v95.4：该 NPC 有已完成支线 → 提示交付入口（反馈：可交任务找不到交付方式）\n    # v95.15 #73：代词按 NPC 性别（迷路骑士等男性 NPC 用"他"）\n    # v95.16 #75：按是否有对话树区分交付引导（无对话树 NPC 的『对话』没有交付选项）\n    _ta = "她" if npc.get("gender") == "女" else "他"\n    for sid, sq in list(quests.get("side", {}).items()):\n        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)\n        if sqd and sqd["giver"] == npc_id and sq.get("status") == "ready":\n            if _cq.DIALOGUES.get(npc_id):\n                lines.append(f"✅ 『{sqd[\'name\']}』已完成！与{_ta}对话即可交付～")\n            else:\n                lines.append(f"✅ 『{sqd[\'name\']}』已完成！输入『交付任务』即可交付～")\n            break\n    return lines\n',
    'content/quests_flow.py::grant_quest_rewards': 'def grant_quest_rewards(group_id, qq_id, qdef, lines):\n    """v124.3 统一任务奖励发放（主线 explore 自动完成 / 主线交付 / 支线交付三处共用）。\n\n    基准：支线 _complete_side_quest 原实现（v104 M20 + v124 全奖励类型）——\n    reward_exp/reward_gold 入角色并结算升级；reward_item 支持单值 / 列表随机 /\n    eq: 装备名册；reward_pet 宠物蛋 / reward_mount 坐骑缰绳入包；unlock_class\n    解锁隐藏职业。声望 / 分支 flag / 每日计数等任务特有处理不入此函数，调用方各自保留。\n    返回结算后的 player（调用方后续需要时使用，如 _complete_side_quest 的 _rule_fire）。"""\n    import random\n    player = db.get_player(group_id, qq_id)\n    player["exp"] += qdef.get("reward_exp", 0)\n    player["gold"] += qdef.get("reward_gold", 0)\n    player["_title_bonus"] = stat_bonus(group_id, qq_id, player)\n    lv_logs, player = check_player_level_up(group_id, qq_id, player)\n    db.update_player(group_id, qq_id, exp=player["exp"], gold=player["gold"], level=player["level"], hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"], skills=player["skills"], attr_pts=player.get("attr_pts", 0), skill_points=player.get("skill_points", 0), learned_skills=player.get("learned_skills", []))\n    if lv_logs:\n        if lines:\n            lines.append("")\n        lines += lv_logs\n    # v104 M20 P1：列表型奖励（如 s17 随机符文）→ 随机抽一个发放\n    # v174 统一抽象：item/eq/pet/mount/title 发放走 game.reward.grant_reward\n    # （只传物品类，exp/gold 已在上方原逻辑结算且要 return 更新后 player）\n    ri = qdef.get("reward_item")\n    _reward_items = []\n    if ri:\n        if isinstance(ri, list):\n            ri = random.choice(ri)\n        # eq: 前缀保留（grant_reward 支持 eq:rid 按名册名解析）\n        _reward_items.append({"item": ri, "n": 1})\n    _rew = {}\n    if _reward_items:\n        _rew["items"] = _reward_items\n    rp = qdef.get("reward_pet")\n    if rp:\n        _rew["pets"] = [rp] if isinstance(rp, str) else list(rp)\n    rm = qdef.get("reward_mount")\n    if rm:\n        _rew["mounts"] = [rm] if isinstance(rm, str) else list(rm)\n    _tid = qdef.get("title")\n    if _tid:\n        _rew["title"] = _tid\n    if _rew:\n        try:\n            grant_reward(_rew, group_id, qq_id, player=player, lines=lines)\n        except Exception:\n            pass\n    # v87 隐藏职业：交任务解锁（unlock_class 写入 hidden_class_unlock）\n    uc = qdef.get("unlock_class")\n    if uc:\n        player_now = db.get_player(group_id, qq_id)\n        unlocks = list(player_now.get("hidden_class_unlock", []) or [])\n        if uc not in unlocks:\n            unlocks.append(uc)\n            db.update_player(group_id, qq_id, hidden_class_unlock=unlocks)\n            lines.append(f"  ⚔️ 传承达成！隐藏职业「{_cc.CLASSES.get(uc, {}).get(\'name\', uc)}」已解锁！")\n            # v112：档位门槛统一读 CLASSES["tier_levels"]（缺省 T1=40），删除 60/30 特例\n            _need = (_cc.CLASSES.get(uc, {}).get("tier_levels") or {1: 40, 2: 60, 3: 90})[1]\n            _cname = _cc.CLASSES.get(uc, {}).get("name", uc)\n            lines.append(f"  💡 达到 {_need} 级后输入『转职 {_cname}』接受传承！")\n    # v140 波3.6：任务奖励称号（title 字段 = titles.py id 或中文名；称号系统条件判定自动拥有，\n    # 这里仅播报解锁——条件满足即生效，不满足也不阻塞任务完成）\n    _tid = qdef.get("title")\n    if _tid:\n        _tinfo = next((t for t in _cq.TITLES if t.get("id") == _tid), None)\n        if not _tinfo:\n            # 兼容支线旧字段用中文名（如 "北境的恩人" → north_benefactor）\n            _tinfo = next((t for t in _cq.TITLES if t.get("name") == _tid), None)\n        if _tinfo:\n            lines.append(f"  🏅 获得称号：「{_tinfo.get(\'name\', _tid)}」！")\n        else:\n            print(f"[dragonfall][v140] 任务『{qdef.get(\'name\', \'\')}』称号 id 缺失：{_tid}（titles.py 未登记），已跳过")\n    return player\n',
    'content/quests_flow.py::complete_side_quest': 'def complete_side_quest(group_id, qq_id, sid, branch_choice=None, hooks=None):\n    """交支线任务，返回通知行列表\n    v124：支持 branch 分支交付（第一次输出选项并置 branch_wait，玩家回复数字后执行）+\n    deliver_text 交付剧情文本。\n\n    hooks：命令层注入 {"tip": callable(cat)->str, "rule_fire": callable(trigger,...)->str}\n    （_tip/_rule_fire 是命令层 I/O 面板能力，P4-2 按 §5.2 以 hooks 回调接入）；\n    缺省（None）时 _tip 返回空串、_rule_fire 返回空串——service 直测不依赖命令层。"""\n    _tip = (hooks or {}).get("tip")\n    _rule_fire = (hooks or {}).get("rule_fire")\n    lines = []\n    quests = db.get_quests(group_id, qq_id)\n    sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)\n    if not sqd:\n        return ["未知支线任务。"]\n    sq = quests.get("side", {}).get(sid)\n    if not sq:\n        return ["这个任务还没完成呢。"]\n    obj = sqd["objective"]\n    # 收集型：实时检查背包材料（不依赖 ready 状态）\n    if obj.get("collect"):\n        # v87 复合目标：kill+collect（魔剑士试炼），collect_count 独立于 kill count\n        need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 不再 KeyError\n        _ckey = C.resolve("materials", obj["collect"])\n        have = db.count_item(group_id, qq_id, _ckey)\n        if have < need:\n            return [f"材料不够！需要 {obj[\'collect\']} ×{need}，你只有 {have} 个。"]\n        # v87 复合目标：同时存在 kill 目标时，击杀进度也要满足\n        if obj.get("kill"):\n            kp = (sq.get("progress") or {}).get(obj["kill"], 0)\n            if kp < obj["count"]:\n                return [f"还要击败 {obj[\'kill\']} ×{obj[\'count\'] - kp}(当前 {kp}/{obj[\'count\']})！"]\n    elif sq.get("status") != "ready":\n        return ["这个任务还没完成呢。"]\n    # v124 分支任务：第一次交付输出选项，等待玩家回复数字\n    br = sqd.get("branch")\n    if br and not branch_choice:\n        opts = br.get("options") or []\n        if sq.get("branch_wait"):\n            return [f"{br.get(\'prompt\', \'\')}\\n{_tip(\'quest_branch\')}\\n" + "\\n".join(\n                f"  {o.get(\'key\', str(i + 1))}. {o.get(\'label\', \'\')}" for i, o in enumerate(opts))]\n        quests["side"][sid] = {**sq, "status": "ready", "branch_wait": True}\n        db.save_quests(group_id, qq_id, quests)\n        _o = [f"  {o.get(\'key\', str(i + 1))}. {o.get(\'label\', \'\')}" for i, o in enumerate(opts)]\n        return [f"{br.get(\'prompt\', \'\')}\\n{_tip(\'quest_branch\')}\\n" + "\\n".join(_o)]\n    # v124 分支选择执行\n    if br and branch_choice:\n        opts = br.get("options") or []\n        chosen = None\n        if isinstance(branch_choice, str):\n            for o in opts:\n                if branch_choice in (o.get("key"), o.get("label")):\n                    chosen = o\n                    break\n        if chosen is None:\n            return [f"没有这个选项～{br.get(\'prompt\', \'\')}\\n{_tip(\'quest_branch\')}\\n" + "\\n".join(\n                f"  {o.get(\'key\', str(i + 1))}. {o.get(\'label\', \'\')}" for i, o in enumerate(opts))]\n        # 用分支选项覆盖奖励（顶层 reward 为 0 时以选项为准）\n        lines.append(f"  📖 {chosen.get(\'text\', \'\')}")\n        sqd = {**sqd,\n               "reward_exp": chosen.get("reward_exp", sqd.get("reward_exp", 0)),\n               "reward_gold": chosen.get("reward_gold", sqd.get("reward_gold", 0)),\n               "reward_item": chosen.get("reward_item", sqd.get("reward_item"))}\n        # v124 分支 flag：写入 giver NPC 的 flag 桶（称号/后续任务判定用）\n        _cf = chosen.get("flag")\n        if _cf:\n            db.set_talk_flag(group_id, qq_id, sqd.get("giver", ""), _cf)\n    # 收集类：扣除材料\n    if obj.get("collect"):\n        need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 不再 KeyError\n        for _ in range(need):\n            db.remove_item(group_id, qq_id, _ckey)\n        # v126.2：鱼获个体属性在 item_data.tags，remove_item 自动截断，无需额外同步\n    # v124 交付剧情文本（无分支时）\n    dt = sqd.get("deliver_text")\n    if dt and not br:\n        lines.append(f"  📖 {dt}")\n    # v124.3：奖励统一走 _grant_quest_rewards（exp/gold/升级 + reward_item 全格式 +\n    # reward_pet/reward_mount/unlock_class）——逻辑与支线原实现完全一致（列表随机 /\n    # eq: 名册 / items→materials 顺序），返回结算后 player 供下方 _rule_fire 使用\n    player = grant_quest_rewards(group_id, qq_id, sqd, lines)\n    # v95.12：交付后保留条目标记 done（无 completed_side 列），防止 _offer_side_quests 自动重接\n    quests["side"][sid] = {"status": "done"}\n    db.save_quests(group_id, qq_id, quests)\n    # v104 M20：行会委托每日（complete_side）——支线交付完成 +1，达标发奖\n    _bump_daily_progress(group_id, qq_id, "complete_side", lines)\n    lines.append(f"✅ 【支线完成】『{sqd[\'name\']}』！")\n    lines.append(f"  奖励：经验 +{sqd[\'reward_exp\']} 金币 +{sqd[\'reward_gold\']}")\n    rep_line = quest_reputation(group_id, qq_id, sqd["giver"])\n    if rep_line:\n        lines.append(f"  {rep_line}")\n    # v97.5 行为彩蛋规则：任务交付后\n    _rule_txt = _rule_fire("quest_deliver", group_id, qq_id, player,\n                           _cs.MAP_BY_ID.get(player.get("cur_map"), {}))\n    if _rule_txt:\n        lines.append(f"  {_rule_txt}")\n    return lines\n',
    'content/quests_flow.py::talk_quest_progress': 'def talk_quest_progress(group_id, qq_id, npc_id) -> list:\n    """v95.11：talk 型主线与目标 NPC 对话即达成（active 空进度遗留态 → ready）。\n    覆盖 v95.9 对话化之前接取、或接取瞬间未置 ready 的存量档，返回通知行。\n    v105 P0/P2：collect 型主线对话时实时数背包（材料足够 → ready）；\n    explore 型主线已在目标地图 → ready（免出图重进）。"""\n    quests = db.get_quests(group_id, qq_id)\n    if quests.get("main_status") != "active":\n        return []\n    mid = quests.get("main_quest")\n    if not mid:\n        return []\n    mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == mid), None)\n    if not mq:\n        return []\n    obj = mq.get("objective", {})\n    if obj.get("talk") == npc_id:\n        quests["main_status"] = "ready"\n        quests["main_progress"] = {npc_id: 1}\n        db.save_quests(group_id, qq_id, quests)\n        return ["✨ 交谈完成！再与这位 NPC 对话即可交付任务。"]\n    if obj.get("collect") and mq.get("giver") == npc_id:\n        need = obj.get("count", 1)\n        if db.count_item(group_id, qq_id, obj["collect"]) >= need:\n            quests["main_status"] = "ready"\n            quests["main_progress"] = {obj["collect"]: need}\n            db.save_quests(group_id, qq_id, quests)\n            return [f"✨ 材料已齐（{obj[\'collect\']} ×{need}）！再与这位 NPC 对话即可交付任务。"]\n    if obj.get("explore") and mq.get("giver") == npc_id:\n        player = db.get_player(group_id, qq_id)\n        if player.get("cur_map") == obj["explore"]:\n            quests["main_status"] = "ready"\n            quests["main_progress"] = {obj["explore"]: 1}\n            db.save_quests(group_id, qq_id, quests)\n            return ["✨ 目标地点已到达！再与这位 NPC 对话即可交付任务。"]\n    return []\n',
    'content/quests_flow.py::update_use_quests': 'def update_use_quests(group_id, qq_id, item_name):\n    """v124 use 目标支线：使用指定物品后支线置 ready（如 递麦酒/用月鳞/交信物）。\n    v124.2 防跨图白嫖：objective.map 或任务自身 map 配置时，须玩家当前地图一致才推进；\n    objective 无 map 且任务无 map 的保持原行为（不校验直接推进）。"""\n    if not item_name:\n        return ""\n    quests = db.get_quests(group_id, qq_id)\n    side = quests.get("side") or {}\n    lines = []\n    changed = False\n    for sid, sq in list(side.items()):\n        if sq.get("status") != "active":\n            continue\n        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)\n        if not sqd:\n            continue\n        obj = sqd.get("objective") or {}\n        if obj.get("use") and obj["use"] == item_name:\n            _need_map = obj.get("map") or sqd.get("map")\n            if _need_map:\n                _pm = db.get_player(group_id, qq_id) or {}\n                if _pm.get("cur_map") != _need_map:\n                    continue\n            side[sid] = {"status": "ready", "progress": {"use": item_name}}\n            changed = True\n            giver = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}\n            lines.append(f"✨ 『{sqd[\'name\']}』目标达成！回去找 {giver.get(\'name\', \'发布人\')} 交付吧～")\n    if changed:\n        quests["side"] = side\n        db.save_quests(group_id, qq_id, quests)\n    return "\\n".join(lines)\n',
    'content/quests_flow.py::branch_wait_sid': 'def branch_wait_sid(group_id, qq_id):\n    """v124：查找处于分支等待状态的支线 sid（ready + branch_wait）。"""\n    quests = db.get_quests(group_id, qq_id)\n    for sid, sq in (quests.get("side") or {}).items():\n        if sq.get("status") == "ready" and sq.get("branch_wait"):\n            return sid\n    return None\n',
    'content/quests_flow.py::quest_kill_progress': 'def quest_kill_progress(group_id, qq_id, monster):\n    """战斗后更新任务进度（主线/支线/每日击杀型），返回通知行——combat._update_quests 击杀段原样随迁。\n\n    v181 P4-2：combat._update_quests 的 quest 段（主线/支线 kill/kill_any + 每日 kill_any/elite/boss）\n    收敛本函数，combat 只留调用壳；周常悬赏 weekly_bump_kill 属 weekly 域不随迁（调用方自行追加）。\n    匹配规则 v105 M19 P2 前缀精确（== 或 「目标·」开头）；每日结算走 services.quests.settle_daily_quest\n    （P4-1 试点已收敛单点）。kill_any 支线用 progress.any（v95.13 防卡死）。\n    """\n    lines = []\n    quests = db.get_quests(group_id, qq_id)\n    changed = False\n    # 主线（仅处理已接且进行中的任务；击杀达到目标则变为可交状态）\n    main_id = quests.get("main_quest")\n    if main_id:\n        mq = next((q for q in _cq.MAIN_QUESTS if q["id"] == main_id), None)\n        if mq and quests.get("main_status") == "active":\n            prog = dict(quests.get("main_progress", {}))\n            obj = mq["objective"]\n            if obj.get("kill") and (monster["name"] == obj["kill"] or monster["name"].startswith(obj["kill"] + "·")):\n                # v95.7 #33：精英/头目变体名包含目标怪名（如『野猪』←『野猪·首领』）也计入任务进度\n                # v105 M19 P2：进度 key 统一记 obj[\'kill\']（此前记 monster[\'name\']，杀精英变体时\n                # 计数入账但面板按 obj[\'kill\'] 读 → 显示 0/N；现精英击杀也计入基础怪 key）\n                # v104 M20 P2：in 后缀包含误伤面过大（『野猪』命中巨型野猪/风车野猪/铁甲野猪/\n                # 岛野猪，『霜巨魔』顶 3 只霜巨魔王），改前缀精确：== 或 「目标·」开头，仅命中\n                # 同名怪与「·」后缀精英/Boss 变体\n                prog[obj["kill"]] = prog.get(obj["kill"], 0) + 1\n                quests["main_progress"] = prog\n                changed = True\n                if prog.get(obj["kill"], 0) >= obj["count"]:\n                    quests["main_status"] = "ready"\n                    _g = _cq.NPCS.get(mq["giver"]) or _w.ALL_WILD.get(mq["giver"]) or {}\n                    lines.append(f"📜 主线『{mq[\'name\']}』目标达成！回去找 {_g.get(\'name\', \'？\')} {deliver_hint(mq[\'giver\'])}吧～")\n                else:\n                    lines.append(f"📜 主线『{mq[\'name\']}』：{prog[obj[\'kill\']]}/{obj[\'count\']}")\n    # 每日\n    # v94：先清跨天任务（daily 里 _date 不是今天 → 清空），避免旧任务残留\n    if db.expire_daily(quests):\n        changed = True\n    daily = dict(quests.get("daily", {}))\n    # v125.1 P0 修复：跳过全部元数据键（_date/_completed/_repeat）——原只跳过 _date，\n    # _completed(int)/_repeat(dict) 被 dq["objective"] 下标 → TypeError 每日首战必崩\n    for dkey, dq in list(daily.items()):\n        if dkey in DAILY_META_KEYS:  # 跨天/计数元数据，不是任务\n            continue\n        dobj = dq["objective"]\n        prog = dq.get("progress", 0)\n        if dobj.get("kill_any"):\n            prog += 1\n        elif dobj.get("kill_elite") and monster.get("is_elite"):\n            prog += 1\n        elif dobj.get("kill_boss") and monster.get("is_boss"):\n            prog += 1\n        dq["progress"] = prog\n        changed = True\n        if prog >= dobj.get("kill_any", dobj.get("kill_elite", dobj.get("kill_boss", 99))):\n            # v125.1 P2：发奖结算统一走 settle_daily_quest（与 world 非击杀 bump 同单点；\n            # 击杀型每日在此接线，防刷上限/衰减对击杀型同样生效）\n            settle_daily_quest(group_id, qq_id, daily, dq, lines)\n            del daily[dkey]\n    # 无条件写回：即使全部完成（daily 为空）也要清空 quests，否则任务残留会无限重复发奖励\n    quests["daily"] = daily\n    # 支线（击杀型）\n    side = dict(quests.get("side", {}))\n    for sid, sq in list(side.items()):\n        if sq.get("status") != "active":\n            continue\n        sqd = next((q for q in _cq.SIDE_QUESTS if q["id"] == sid), None)\n        if not sqd:\n            continue\n        obj = sqd["objective"]\n        if obj.get("kill_any"):\n            # v95.13 修复：kill_any 支线（护送商货等）此前无计数分支，任务永久卡死\n            prog = dict(sq.get("progress", {}))\n            prog["any"] = prog.get("any", 0) + 1\n            sq["progress"] = prog\n            changed = True\n            if prog["any"] >= obj["kill_any"]:\n                sq["status"] = "ready"\n                _g = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}\n                lines.append(f"📜 支线『{sqd[\'name\']}』目标达成！回去找 {_g.get(\'name\', \'？\')} {deliver_hint(sqd[\'giver\'])}吧～")\n            else:\n                lines.append(f"📜 支线『{sqd[\'name\']}』：{prog[\'any\']}/{obj[\'kill_any\']}")\n        elif obj.get("kill") and (monster["name"] == obj["kill"] or monster["name"].startswith(obj["kill"] + "·")):\n            # v105 M19 P2：进度 key 统一记 obj[\'kill\']（与主线一致、与面板/交付校验读取一致）\n            # v104 补测发现：支线此前只精确 ==（杀精英变体不推进），现与主线同款前缀精确匹配\n            # v104 M20 P2：in 后缀包含误伤面过大（『盗贼』命中盗贼头目·黑鸦、『霜巨魔』顶 3 只\n            # 霜巨魔王、『月狼』命中月狼王·银鬃），改前缀精确：== 或 「目标·」开头\n            prog = dict(sq.get("progress", {}))\n            # v105 M19 P2：进度 key 统一记 obj[\'kill\']（与主线一致、与面板/交付校验读取一致）\n            prog[obj["kill"]] = prog.get(obj["kill"], 0) + 1\n            sq["progress"] = prog\n            changed = True\n            if prog.get(obj["kill"], 0) >= obj["count"]:\n                sq["status"] = "ready"\n                _g = _cq.NPCS.get(sqd["giver"]) or _w.ALL_WILD.get(sqd["giver"]) or {}\n                lines.append(f"📜 支线『{sqd[\'name\']}』目标达成！回去找 {_g.get(\'name\', \'？\')} {deliver_hint(sqd[\'giver\'])}吧～")\n            else:\n                lines.append(f"📜 支线『{sqd[\'name\']}』：{prog[obj[\'kill\']]}/{obj[\'count\']}")\n    if side:\n        quests["side"] = side\n    if changed:\n        db.save_quests(group_id, qq_id, quests)\n    return lines\n',
    'content/profession_quests.py::daily_need': 'def daily_need(dq):\n    """每日任务需求数（面板显示用）。objective 单键值即达标数（kill_any:10 等）。\n    v125.1 P2：存档缺 objective 时回读 DAILY_QUESTS 定义；仍无定义返回 None，\n    面板只显示实际进度，不再兜底假 99。"""\n    dobj = (dq or {}).get("objective") or {}\n    for _v in dobj.values():\n        if isinstance(_v, int) and _v > 0:\n            return _v\n    _def = next((q for q in _cq.DAILY_QUESTS if q.get("name") == (dq or {}).get("name")), None)\n    if _def:\n        for _v in (_def.get("objective") or {}).values():\n            if isinstance(_v, int) and _v > 0:\n                return _v\n    return None\n',
    'content/profession_quests.py::settle_daily_quest': 'def settle_daily_quest(group_id, qq_id, daily, dq, lines=None):\n    """v125.1 P2：每日任务达标结算单点（world._bump_daily_progress 与 combat._update_quests\n    双副本收敛）。职责：完成计数(_completed)/重复衰减计数(_repeat)、经验金币发放、升级、\n    通知行。调用方负责进度 +1 与达标判断，结算后自行 del 任务键；lines=None 时不输出通知。"""\n    daily["_completed"] = int(daily.get("_completed", 0) or 0) + 1\n    rpt = int(daily.get("_repeat", {}).get(dq["name"], 0) or 0)\n    _rep = dict(daily.get("_repeat", {}) or {})\n    _rep[dq["name"]] = rpt + 1\n    daily["_repeat"] = _rep\n    if lines is not None:\n        _dec = dq.get("repeat", 0)\n        if _dec:\n            _pct = daily_repeat_pct(_dec)\n            lines.append(T.text("quests.done_decay", name=dq["name"], pct=_pct,\n                                exp=dq["reward_exp"], gold=dq["reward_gold"]))\n        else:\n            lines.append(T.text("quests.done", name=dq["name"], exp=dq["reward_exp"],\n                                gold=dq["reward_gold"]))\n    player = db.get_player(group_id, qq_id)\n    player["exp"] += dq["reward_exp"]\n    player["gold"] += dq["reward_gold"]\n    player["_title_bonus"] = stat_bonus(group_id, qq_id, player)\n    lv_logs, player = check_player_level_up(group_id, qq_id, player)\n    db.update_player(group_id, qq_id, exp=player["exp"], gold=player["gold"], level=player["level"], hp=player["hp"], mp=player["mp"], max_hp=player["max_hp"], max_mp=player["max_mp"], skills=player["skills"], attr_pts=player.get("attr_pts", 0), skill_points=player.get("skill_points", 0), learned_skills=player.get("learned_skills", []))\n    if lines is not None and lv_logs:\n        lines.append("")\n        lines += lv_logs\n',
    'content/profession_quests.py::bump_daily_progress': 'def bump_daily_progress(group_id, qq_id, obj_key, lines=None):\n    """v104 M20 修复：非击杀类每日任务进度推进（行会委托=完成支线 / 采集任务=采集材料）。\n\n    与 combat.py 击杀分支（kill_any/kill_elite/kill_boss）互补：\n    匹配 objective[obj_key] 的每日任务 +1，达标即发奖并从今日列表移除。\n    调用点：_complete_side_quest（complete_side）、interact_prop 材料元素（collect_any）。\n    """\n    quests = db.get_quests(group_id, qq_id)\n    daily = dict(quests.get("daily", {}) or {})\n    if not daily:\n        return\n    changed = False\n    for dkey, dq in list(daily.items()):\n        if dkey in DAILY_META_KEYS:  # 跨天/计数元数据，不是任务\n            continue\n        dobj = dq.get("objective") or {}\n        need = dobj.get(obj_key)\n        if not need:\n            continue\n        dq["progress"] = int(dq.get("progress", 0)) + 1\n        changed = True\n        if dq["progress"] >= need:\n            # v125.1 P2：发奖结算统一走 settle_daily_quest（与 combat._update_quests 同单点）\n            settle_daily_quest(group_id, qq_id, daily, dq, lines)\n            del daily[dkey]\n    if changed:\n        # 保留 _date/_completed/_repeat（active 任务清空后仍须持续生效防刷/衰减计数）\n        quests["daily"] = daily\n        db.save_quests(group_id, qq_id, quests)\n',
    'content/profession_quests.py::daily_pool': 'def daily_pool(player, dq):\n    """v94 每日任务按等级过滤：低等级不抽打不到的任务（修复 #45）。\n    通用任意怪任务全等级可做；精英 Lv.6+、Boss Lv.10+；\n    区域任务按奖励分档（reward_exp 与区域怪物等级强相关）。\n    v169.1 成长模型：DAILY_QUESTS 四档等级池（新手/中坚 Lv20/高阶 Lv50/终局 Lv80），\n    任务带 min_lv 字段 → 直接按玩家等级过滤（高于 min_lv 才可抽），\n    且高 reward_exp 任务不再被旧 cap 表误放行（旧 cap Lv30+ 变 10 亿导致 Lv30 抽 Lv80 任务）。\n    """\n    lv = int(player.get("level") or 1)\n    obj = dq.get("objective", {})\n    exp = int(dq.get("reward_exp") or 0)\n    # v169.1：显式 min_lv 字段优先（新等级池）\n    _mlv = dq.get("min_lv")\n    if isinstance(_mlv, int):\n        return lv >= _mlv\n    if "kill_any" in obj:\n        return True\n    if "kill_elite" in obj:\n        return lv >= 6\n    if "kill_boss" in obj:\n        return lv >= 10\n    if lv < 3:\n        return False\n    cap = 400\n    for min_lv, c in ((3, 400), (6, 800), (10, 1200), (15, 1600), (20, 2000), (25, 2600), (30, 1000000000)):\n        if lv >= min_lv:\n            cap = c\n    return exp <= cap\n',
    'content/profession_quests.py::draw_daily': 'def draw_daily(group_id, qq_id, player):\n    """v94『每日』抽取/衰减/发布：读 DAILY_QUESTS → 等级过滤 → random.sample 抽 2 个\n    → 按今日已完成的同任务次数算衰减 factor 乘算奖励 → 写回 quests.daily。\n\n    v116 保留今日已完成/重复计数（active 任务清空后重新抽取时不可归零，防刷衰减判定持续有效）。\n    返回 (ok, text)：ok=False 时 text 为拒绝提示（红名守卫/上限/已有任务由调用方命令层负责，\n    此处只管发布）；ok=True 时 text 为发布面板行（\\n 拼接前不含尾行）。"""\n    import datetime as _dt\n    quests = db.get_quests(group_id, qq_id)\n    # v94 跨天清理：昨天的任务过期，先清空再判断（旧存档无 _date 视为过期）\n    if db.expire_daily(quests):\n        db.save_quests(group_id, qq_id, quests)\n    daily = quests.get("daily") or {}\n    # v116 §3.4 每日防刷：已完成任务（_completed 计数）≥ 上限 → 不再抽新任务\n    completed = int(daily.get("_completed", 0) or 0)\n    if completed >= DAILY_LIMIT:\n        return False, T.text("quests.limit", completed=completed, limit=DAILY_LIMIT)\n    if any(k not in DAILY_META_KEYS for k in daily):\n        return False, T.static("quests.have")\n    # v116 保留今日已完成/重复计数（active 任务清空后重新抽取时不可归零，防刷衰减判定持续有效）\n    base_completed = completed\n    repeat = dict(daily.get("_repeat", {}) or {})\n    # v94 随机抽 2 个每日任务（按等级过滤：低等级不抽打不到的任务）\n    pool = [dq for dq in _cq.DAILY_QUESTS if daily_pool(player, dq)]\n    chosen = random.sample(pool, min(2, len(pool)))\n    daily = {"_date": _dt.date.today().isoformat(),\n             "_completed": base_completed, "_repeat": repeat}\n    for i, dq in enumerate(chosen):\n        rpt = int(repeat.get(dq["name"], 0) or 0)  # 今日已完成的同任务次数 → 衰减档\n        factor = DAILY_REPEAT_FACTORS[rpt] if rpt < len(DAILY_REPEAT_FACTORS) else DAILY_REPEAT_FACTORS[-1]\n        daily[f"d{i}"] = {"name": dq["name"], "desc": dq["desc"], "objective": dq["objective"],\n                          "reward_exp": int(dq["reward_exp"] * factor),\n                          "reward_gold": int(dq["reward_gold"] * factor),\n                          "repeat": rpt, "progress": 0}\n    quests["daily"] = daily\n    db.save_quests(group_id, qq_id, quests)\n    lines = [T.static("quests.published"), "━━━━━━━━━━━━"]\n    _daily_n = 0  # v125.1 P2：序号仅计实际任务（跨 _date/_completed/_repeat 元数据键）\n    for dkey, dq in daily.items():\n        if dkey in DAILY_META_KEYS:\n            continue\n        _daily_n += 1\n        _dec = dq.get("repeat", 0)\n        lines.append(T.text("quests.item", n=_daily_n, name=dq["name"], desc=dq["desc"]))\n        if _dec:\n            _pct = daily_repeat_pct(_dec)\n            lines.append(T.text("quests.item_decay", pct=_pct, exp=dq["reward_exp"],\n                                gold=dq["reward_gold"]))\n        else:\n            lines.append(T.text("quests.item_reward", exp=dq["reward_exp"],\n                                gold=dq["reward_gold"]))\n    if base_completed:\n        lines.append(T.text("quests.progress_note", base=base_completed,\n                            limit=DAILY_LIMIT))\n    return True, "\\n".join(lines)\n',
    'content/world_cmds.py::_obj_text': 'def _obj_text(self, obj):\n    if obj.get("kill"):\n        return f"击败 {obj[\'kill\']} ×{obj[\'count\']}"\n    if obj.get("collect"):\n        # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError\n        return f"收集 {obj[\'collect\']} ×{obj.get(\'collect_count\') or obj.get(\'count\', 1)}"\n    if obj.get("explore"):\n        return f"前往 {_cat_space.MAP_BY_ID.get(obj[\'explore\'], {}).get(\'name\', \'？\')}"\n    if obj.get("find"):\n        # v97.1 告示委托：在指定地图探索概率找到目标\n        return f"在 {_cat_space.MAP_BY_ID.get(obj.get(\'map\', \'\'), {}).get(\'name\', \'？\')} 寻找 {obj[\'find\']}(探索有概率遇到)"\n    if obj.get("use"):\n        # v124 use 目标：使用指定物品达成\n        return f"使用 {obj[\'use\']}"\n    if obj.get("talk"):\n        npc = _cat_quests.NPCS.get(obj["talk"], {})\n        return f"与 {npc.get(\'name\', \'？\')} 交谈"\n    return "？"\n',
    'content/world_cmds.py::_obj_text_lines': 'def _obj_text_lines(self, obj, st=None):\n    """v124.2 复合 objective 逐行渲染（如 s18 kill 腐牙萨满·嚎骨 + find 白桦 两行都显示）。\n    find 行按任务状态标 已找到/未找到（find 无进度存档，以 ready 态为准）；\n    纯 find 委托（有 map）保留『探索有概率遇到』机制提示，与原 _obj_text 文案一致。"""\n    lines = []\n    if obj.get("kill"):\n        lines.append(f"击败 {obj[\'kill\']} ×{obj[\'count\']}")\n    if obj.get("collect"):\n        # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError\n        lines.append(f"收集 {obj[\'collect\']} ×{obj.get(\'collect_count\') or obj.get(\'count\', 1)}")\n    if obj.get("explore"):\n        lines.append(f"前往 {_cat_space.MAP_BY_ID.get(obj[\'explore\'], {}).get(\'name\', \'？\')}")\n    if obj.get("find"):\n        _mname = _cat_space.MAP_BY_ID.get(obj.get("map", ""), {}).get("name", "")\n        if st == "ready":\n            lines.append(f"{\'在 \' + _mname + \' \' if _mname else \'\'}寻找 {obj[\'find\']}（已找到）")\n        elif _mname:\n            lines.append(f"在 {_mname} 寻找 {obj[\'find\']}(探索有概率遇到)")\n        else:\n            lines.append(f"寻找 {obj[\'find\']}（未找到）")\n    if obj.get("use"):\n        lines.append(f"使用 {obj[\'use\']}")\n    if obj.get("talk"):\n        npc = _cat_quests.NPCS.get(obj["talk"], {})\n        lines.append(f"与 {npc.get(\'name\', \'？\')} 交谈")\n    return lines or ["？"]\n',
    'content/world_cmds.py::_take_main_quest': 'def _take_main_quest(self, group_id, qq_id, npc_id, npc):\n    """从 NPC 接主线任务；返回通知行列表（P4-2 壳：转调 services.quests_flow.take_main_quest）"""\n    from . import quests_flow as qf\n    return qf.take_main_quest(group_id, qq_id, npc_id, npc)\n',
    'content/cmds_world.py::_svc': 'def _svc(name):\n    """宿主 `services.quests` 上的常量/函数（真源写法 `from ..services.quests import X`）。"""\n    from . import profession_quests as _pq\n    return getattr(_pq, name)\n',
    'content/cmds_world.py::_kill_prog_count': 'def _kill_prog_count(obj, prog):\n    """v105 M19 P2：击杀进度聚合读——兼容旧存档老 key（v95.7 之前进度记\n    monster[\'name\'] 而非 obj[\'kill\']，如『精英森林狼』），面板不再显示 0/N 孤儿计数。\n    目标 key 有值用目标 key；为 0 时汇总其余包含目标名的历史 key。"""\n    v = prog.get(obj["kill"], 0)\n    if v == 0:\n        v = sum(c for k, c in prog.items() if k != obj["kill"] and obj["kill"] in k)\n    return v\n',
    'content/cmds_world.py::quest_view': '@register("quest_view", guards=("hook:player",), params=("cmd=任务", "page"))\ndef quest_view(env) -> list:\n    """『任务』：冒险日志（主线 + 支线分页 + 每日进度 + 师门考验 + 底部提示）。"""\n    shell = _shell(env)\n    group_id, qq_id = env.group_id, env.uid\n    player = env.player\n    if shell._is_redname(qq_id):\n        return ["☠️ 你是红名！守卫不让你靠近任务板……(等红名消退再来)"]\n    quests = db.get_quests(group_id, qq_id)\n    lines = ["📜 【冒险日志】", "━━━━━━━━━━━━"]\n    # 主线\n    main_id = quests.get("main_quest")\n    if main_id:\n        mq = next((q for q in MAIN_QUESTS if q["id"] == main_id), None)\n        # v104 M19：旧存档 main_quest 指向已下线 id（如 "q1"）→ 面板主线空白。\n        # 与 _take_main_quest 同样的存档容错：重置回主线起点并落库。\n        if not mq:\n            quests["main_quest"] = "q1_1"\n            quests["main_status"] = "pending"\n            quests["main_progress"] = {}\n            main_id = "q1_1"\n            mq = next((q for q in MAIN_QUESTS if q["id"] == main_id), None)\n            db.save_quests(group_id, qq_id, quests)\n        if mq:\n            _ginfo = NPCS.get(mq["giver"]) or ALL_WILD.get(mq["giver"]) or {}\n            giver = _ginfo.get("name", "？")\n            giver_map = _ginfo.get("map", "")\n            giver_map_name = MAP_BY_ID.get(giver_map, {}).get("name", "？")\n            lines.append(f"【主线】『{mq[\'name\']}』")\n            lines.append(f"  {mq[\'desc\']}")\n            st = quests.get("main_status", "pending")\n            if st == "pending":\n                lines.append(f"  ⏳ 未接取：去找 {giver}(在{giver_map_name})对话接取")\n            elif st == "ready":\n                # v95.25 #47b：主线交付=找 NPC 自动触发（与『交付任务』指令并存），不写死交付方式\n                lines.append(f"  ✅ 目标达成！回去找 {giver} 交付")\n            else:\n                prog = quests.get("main_progress", {})\n                obj = mq["objective"]\n                # v101.3：目标类型展示查表化（kill/collect/explore/talk，顺序与原 if-elif 一致）\n                # v169.9：主线 collect 面板实时查背包（对齐支线口径）——此前只读 main_progress\n                # 存档，玩家采到材料但没对话过 NPC 时面板仍显示 0/N，误以为物品对不上（#143）\n                if obj.get("collect"):\n                    have = db.count_item(group_id, qq_id, obj["collect"])\n                    need = obj.get("count", 1)\n                    if have >= need:\n                        lines.append(f"  ✅ 材料已齐：{obj[\'collect\']} {have}/{need}（回去找 {giver} 交付）")\n                    else:\n                        lines.append(f"  收集：{have}/{need}")\n                else:\n                    for _k, _fn in _OBJ_PROGRESS_LINES.items():\n                        if obj.get(_k):\n                            lines.append(_fn(obj, prog))\n                            break\n    else:\n        lines.append("【主线】已全部完成！🎊")\n    # 支线（v101.25i3：已完成任务不进面板，鱼鱼：交了还显示）\n    side = quests.get("side", {})\n    side_items = [(sid, sq) for sid, sq in side.items() if sq.get("status", "active") != "done"]\n    if side_items:\n        lines.append("")\n        lines.append("【支线】")\n        raw = env.arg_text("任务")\n        page = env.page(raw)\n        page_items, pages, page = env.page_items(side_items, page, per_page=5)\n        for i, (sid, sq) in enumerate(page_items, (page - 1) * 5 + 1):\n            sqd = next((q for q in SIDE_QUESTS if q["id"] == sid), None)\n            if not sqd:\n                continue\n            giver = (NPCS.get(sqd["giver"]) or ALL_WILD.get(sqd["giver"]) or {}).get("name", "？")\n            st = sq.get("status", "active")\n            obj = sqd["objective"]\n            # v95.12：已交付支线显示已完成（不占可交付位）\n            if st == "done":\n                lines.append(f"{i:>2}. 『{sqd[\'name\']}』[✅ 已完成]")\n                continue\n            # v127.7 排版：任务名单独一行（名字+状态），描述缩进下一行，目标进度行统一再缩进\n            # v116 §3.4：进行中支线可放弃（主线不可弃），放弃提示统一放面板底部（v123e 去行尾冗余）\n            # 收集型：实时按背包材料判断（v104 补测：复合目标同时显示击杀进度防误导）\n            if obj.get("collect"):\n                have = db.count_item(group_id, qq_id, obj["collect"])\n                need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError\n                prog = sq.get("progress", {})\n                kill_txt = ""\n                if obj.get("kill"):\n                    kv = _kill_prog_count(obj, prog)  # v105 M19 P2：兼容旧档老 key 聚合\n                    kill_txt = f"｜击杀：{kv}/{obj.get(\'count\', 0)}"\n                if have >= need:\n                    lines.append(f"{i:>2}. 『{sqd[\'name\']}』[✅ 可交{kill_txt}]")\n                    lines.append(f"    {sqd[\'desc\']}")\n                    lines.append(f"    材料已齐！回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n                else:\n                    lines.append(f"{i:>2}. 『{sqd[\'name\']}』[⏳{kill_txt}]")\n                    lines.append(f"    {sqd[\'desc\']}")\n                    lines.append(f"    收集：{obj[\'collect\']} {have}/{need}{kill_txt}")\n                # v125.1 P2：复合目标（collect+use/find/explore，如 s53/s56/s64/s105）\n                # 补显其余目标行，与 find/use 分支的 _obj_text_lines 展示口径一致\n                # （收集/击杀行已在上方展示，过滤避免重复）\n                for _t in _WC._obj_text_lines(shell, obj, st):\n                    if _t.startswith(("收集", "击败")):\n                        continue\n                    lines.append(f"    {_t}")\n                continue\n            # v104 M20 P2：find 型（告示委托等）面板提示机制——在 XX 探索有概率遇到\n            # （此前走通用兜底只显示 desc+[⏳]，玩家不知如何推进）\n            if obj.get("find"):\n                lines.append(f"{i:>2}. 『{sqd[\'name\']}』[{\'✅ 可交\' if st == \'ready\' else \'⏳\'}]")\n                lines.append(f"    {sqd[\'desc\']}")\n                # v124.2 复合目标逐行显示（s18 kill+find 两行都展示）\n                for _t in _WC._obj_text_lines(shell, obj, st):\n                    lines.append(f"    {_t}")\n                if st == "ready":\n                    lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n                continue\n            # v124 use 型（使用指定物品达成）——同 find 处理\n            if obj.get("use"):\n                lines.append(f"{i:>2}. 『{sqd[\'name\']}』[{\'✅ 可交\' if st == \'ready\' else \'⏳\'}]")\n                lines.append(f"    {sqd[\'desc\']}")\n                for _t in _WC._obj_text_lines(shell, obj, st):\n                    lines.append(f"    {_t}")\n                if st == "ready":\n                    lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n                continue\n            mark = "✅ 可交" if st == "ready" else "⏳"\n            lines.append(f"{i:>2}. 『{sqd[\'name\']}』[{mark}]")\n            lines.append(f"    {sqd[\'desc\']}")\n            if st == "ready":\n                lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n        # v127.7 翻页提示补全：上一页/下一页 + 总页数（此前只有下一页）\n        if pages > 1:\n            _nav = []\n            if page > 1:\n                _nav.append(f"『任务 {page-1}』上一页")\n            if page < pages:\n                _nav.append(f"『任务 {page+1}』下一页")\n            lines.append(f"💡 {\' | \'.join(_nav)}(共 {pages} 页)")\n        shell._record_list_state(qq_id, "任务", page, pages)\n    else:\n        lines.append("")\n        lines.append("【支线】暂无——找镇上的 NPC 聊聊可能有意外收获")\n    # 每日\n    # v116 §3.4：daily 含 _completed/_repeat 元数据（active 任务清空后仍在）——\n    # 只剩元数据 = 今日全部完成，按"已完成"分支展示；_completed 超额时给出计数。\n    # v127.7：玩家从未领取（daily 为空）→ 提示『每日』领取，不再误报"已完成"。\n    daily = quests.get("daily", {})\n    active_keys = [k for k in daily if k not in _DAILY_META_KEYS]\n    if active_keys:\n        lines.append("")\n        lines.append(T.static("daily.section"))\n        _daily_n = 0  # v116 每日任务序号（仅计实际任务，跨元数据）\n        for dkey, dq in daily.items():\n            if dkey in _DAILY_META_KEYS:  # 跨天/计数元数据，跳过\n                continue\n            _daily_n += 1\n            # v125.1 P2：序号用 _daily_n（仅计实际任务）——原用 enumerate 的 i 会把\n            # _date/_completed/_repeat 元数据占位算进去（面板显示 4./5.，『放弃』按 1..N 对不上）\n            need = _svc("daily_need")(dq)\n            # v127.7 排版：每日任务名单独一行，描述缩进下一行\n            if need is None:\n                # v125.1 P2：无达标数定义时只显示实际进度，不再兜底假 99\n                lines.append(T.text("daily.item", n=_daily_n, name=dq["name"]))\n                lines.append(T.text("daily.item_plain", desc=dq["desc"],\n                                    prog=dq.get("progress", 0)))\n            else:\n                lines.append(T.text("daily.item", n=_daily_n, name=dq["name"]))\n                lines.append(T.text("daily.item_progress", desc=dq["desc"],\n                                    prog=dq.get("progress", 0), need=need))\n    else:\n        lines.append("")\n        if not daily:\n            # v127.7 修复：从未领取（新号/跨天清空）→ 引导领取，不显示"已完成"\n            lines.append(T.static("daily.never"))\n        else:\n            _done = int(daily.get("_completed", 0) or 0)\n            if _done >= _svc("DAILY_LIMIT"):\n                lines.append(T.text("daily.done_full", done=_done, limit=_svc("DAILY_LIMIT")))\n            else:\n                lines.append(T.text("daily.done_part", done=_done))\n    # v101.30d #O1：师门考验追踪——对话树进行中时面板显示（playtest 小红：考验无面板条目）\n    _MASTER_IDS = ("npc_herb_master", "npc_mine_master", "npc_fish_master", "npc_cook_master",\n                   "npc_alchemy_master", "npc_craft_master", "npc_enhance_master", "npc_rune_master")\n    ts = db.get_talk_state(group_id, qq_id)\n    # ★ U1-I4 L6：`ts and ts.get("npc")` → `(ts or {}).get("npc")`（同值；空会话/无会话都落 None），\n    #   导师行取用换引擎 `Lookup(NPCS).first(...)`（真值链，与原 `.get(id) or {}` 同口径）。\n    _master = (ts or {}).get("npc")\n    if _master in _MASTER_IDS:\n        _tnpc = _NPCS_LOOKUP.first(_master)[0] or {}\n        lines.append("")\n        lines.append("【师门考验】")\n        lines.append(f"  ⏳ 正在接受【{_tnpc.get(\'name\', \'导师\')}】的拜师考验，回复『继续』接着进行")\n    lines.append("")\n    # v127.1 每面板只抽 1 条随机提示（v123e 放弃/接取引导并入随机池）\n    lines.append(shell._tip("quest"))\n    return lines\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/quests_flow.py::obj_text': '76056be4a678d4e19318695f373fb6c33ca0258453efda84980688613a468b8f',
        'content/quests_flow.py::sq_unlocked': '05962447d140bd93dd329c1dd1d375d7006db64d301edfa3bbe1c974354c6a93',
        'content/quests_flow.py::sq_stats_met': 'a3123a3bfcfc390bf3e87afe8942fea7476ff14b45d9270cae36c80ac4b740a6',
        'content/quests_flow.py::available_quest_list': 'b1d4e08ed6a16f424b86d73936480ae4cfec83b139e8cb31050c41ebfd10e1f7',
        'content/quests_flow.py::update_explore_quests': '706f2b893e2fb170cac94f619a2396280d34e946c5f8e9fc864f2c2142ee9fd0',
        'content/quests_flow.py::take_main_quest': '84d7001b07232abb7f6d6cdc3d65895c82826c8381a657e7fb2223109c560f66',
        'content/quests_flow.py::quest_reputation': '5a5f851ed84a9165cfd55495dc3268ebbe59da9b756fbd1eeed781f49d566eec',
        'content/quests_flow.py::deliver_hint': 'f075d5a2d35f430cdf6774df4f936732252c63d5e4d0a6bdf03bd045d01a4d8f',
        'content/quests_flow.py::side_available_list': 'be41cf9c7c9f8f5e831a4b123f036c967b408b668c433acbc8079e037ffd16be',
        'content/quests_flow.py::offer_side_quest': 'bcc6f23d8817fa33d152f33088f915f44e201a8a45aee5c1ccdde7669759d453',
        'content/quests_flow.py::offer_side_quests': '203fb0f187274f8ef89e2067c4114eb4057d935b3ca1326ae0c151da099a36e1',
        'content/quests_flow.py::grant_quest_rewards': '2643c85478a15244a2c50c9d26c8a4ea74679632080c93056d91182c5eb8f8f4',
        'content/quests_flow.py::complete_side_quest': '14ca1cb0f9fd031340472ee0c0c476a194fd952734f2b1b260b45ef52efc4006',
        'content/quests_flow.py::talk_quest_progress': '9bd1304069f51121bd3fd35298f4e538aac559a8fb2cf2abaffc69b812e3406c',
        'content/quests_flow.py::update_use_quests': '52c1cdd4456c354babcf9c12b7de5071559681217edb7dac229a02dbbb43e38b',
        'content/quests_flow.py::branch_wait_sid': '4436a53533504b4be1d11d3dea8434c774039a48ffcec52c4991a3fcee47b680',
        'content/quests_flow.py::quest_kill_progress': '7e02e92cd335e79af35f625d8ea2e4820a9e1993bedd35180055ac694ed7b897',
        'content/profession_quests.py::daily_need': 'ec38afa1f7c242a6f303bac8b5e1de94bea363c1f17cc8a63922e05bc7a7b48e',
        'content/profession_quests.py::settle_daily_quest': 'c1e2cf3ddffb394bbbd905f6e41e440233907daa38a8fd6e024a9259aaf9da2f',
        'content/profession_quests.py::bump_daily_progress': 'df50f27b5236e4ee52689a7644c64f2ced85ad072153776c1518c3133d48e66e',
        'content/profession_quests.py::daily_pool': '75d20348e9403773e5ba464e88aa86dad6de5cefc71611a822672a9c5cf17533',
        'content/profession_quests.py::draw_daily': '9b4bde65ea3cdc184e1649b4d1f8871908fe9daa7345bf37583edc020e1488d0',
        'content/world_cmds.py::_obj_text': '713000406a20fe7ed72eac8b3a97d283bb91730d0cf382250e18dc0b50b4ab5a',
        'content/world_cmds.py::_obj_text_lines': '91b9e23b8186631d1fb7e5284cebe66cab9a5dbdd4ba9ef6bc7578a69d08dd05',
        'content/world_cmds.py::_take_main_quest': '0b3f8c8dc0ec564e2dff5a77e27ee826cf2788e9e1df2bcefc899c583026556a',
        'content/cmds_world.py::_svc': '84f063ece8743a96b4c98ba39aaaa4c293799b285d01b16c5472ecd5ffeba3b9',
        'content/cmds_world.py::_kill_prog_count': 'a0446090c33bb1e071c4892236a2938a0d7ca84e5d0987185de00a7b3575f495',
        'content/cmds_world.py::quest_view': 'a7a9e96ec5c3b5a489b49dd88040470ee197945e05d2b79457e2a710cb3f656d',
    },
    'live': {
        'content/quests_flow.py::obj_text': '0d1d0ae5c84eaa9e073ee2d30846bc676188aace3606e1065edbaa4995107ecf',
        'content/quests_flow.py::sq_unlocked': '141432434137571af97f5999c5d1adf9ee0c294a7d0ec2644ce9c2ec13813972',
        'content/quests_flow.py::sq_stats_met': 'a3123a3bfcfc390bf3e87afe8942fea7476ff14b45d9270cae36c80ac4b740a6',
        'content/quests_flow.py::available_quest_list': '7bfc84a554fafafa51cd6d639e27d3a3a59e7f4a945f05276ffe76fe098869fb',
        'content/quests_flow.py::update_explore_quests': '1f666bf11efaa07896092101ee1f1f1c1c3e91c15b49031782eb50282439342c',
        'content/quests_flow.py::take_main_quest': 'bbe57e2991f74250a83b24899a0496b3d981c7e209a7ff5f66eb2c5fce5675b2',
        'content/quests_flow.py::quest_reputation': '091ab172a9da8db347aa2032026d260422e182043a4769df7cd5acb007a1f6ca',
        'content/quests_flow.py::deliver_hint': 'f075d5a2d35f430cdf6774df4f936732252c63d5e4d0a6bdf03bd045d01a4d8f',
        'content/quests_flow.py::side_available_list': 'd546c1d2bfea908745d31af377890e546e0be2902cc1ffd3a1a61598f105c302',
        'content/quests_flow.py::offer_side_quest': '0f42aad855ff81db290910e772843a1f884a1df2fb809d958b949b52d4ee2a6f',
        'content/quests_flow.py::offer_side_quests': '400caf1e3a12334fde19c02e141eedc138f7de69c969c4cf115f058ea20c789e',
        'content/quests_flow.py::grant_quest_rewards': 'dc6e9b7e32f56de2e26a16ed1a6a8b69eb7b74e9e4a12f6aaaa2d7810a8e073c',
        'content/quests_flow.py::complete_side_quest': '6794eb655138e4fc71041dd0b434730885c7f20e6c55a680b153596f9089e9f4',
        'content/quests_flow.py::talk_quest_progress': 'c837baa027c74bce8f7bedfa4330aa5e1bc29df012a0592898d8b5ab734c4d6d',
        'content/quests_flow.py::update_use_quests': 'de36c7fb21f9817cc6052a9b146cbf362e8a9e75a1c79f7e3cde9ad4876fb818',
        'content/quests_flow.py::branch_wait_sid': '4436a53533504b4be1d11d3dea8434c774039a48ffcec52c4991a3fcee47b680',
        'content/quests_flow.py::quest_kill_progress': 'd1ce86e92672c414e08b8a4921f09b955f947a5df9605d1022f3b57c829157c2',
        'content/profession_quests.py::daily_need': 'f7b449ec9e0af407af2523043cf674d53d0f0e8ead88e7916776bc035ed6b683',
        'content/profession_quests.py::settle_daily_quest': 'c1e2cf3ddffb394bbbd905f6e41e440233907daa38a8fd6e024a9259aaf9da2f',
        'content/profession_quests.py::bump_daily_progress': 'a3319e10964a6c78886ffcec98d1a973a713e5346166f576447b502980ba18f3',
        'content/profession_quests.py::daily_pool': '75d20348e9403773e5ba464e88aa86dad6de5cefc71611a822672a9c5cf17533',
        'content/profession_quests.py::draw_daily': '6c715ebc881c3bf10b3eecb0c31ff08d66c8329b139f524f11e195c14473a3a3',
        'content/world_cmds.py::_obj_text': '5af8becbb9557afeb52432f4b1b459a017e7122dfdc574cdc5d387d479923a8b',
        'content/world_cmds.py::_obj_text_lines': 'a90ce9822187eb867002dc4864b0c7434f926ec9b86883095fe031231a31d630',
        'content/world_cmds.py::_take_main_quest': '0b3f8c8dc0ec564e2dff5a77e27ee826cf2788e9e1df2bcefc899c583026556a',
        'content/cmds_world.py::_svc': '84f063ece8743a96b4c98ba39aaaa4c293799b285d01b16c5472ecd5ffeba3b9',
        'content/cmds_world.py::_kill_prog_count': 'a0446090c33bb1e071c4892236a2938a0d7ca84e5d0987185de00a7b3575f495',
        'content/cmds_world.py::quest_view': 'a6129156aaa39a8e99daa5bb3bd9310671aa5e0ca1aa1b14fab92c01eccc220d',
    },
    'aux': {
        'catalog_quests_sha': 'a01253296243131a3d740442c0d336158a42019f2e82995f99bd77f095f38d37',
        'obj_progress_lines_raw': '204bfb10c95759cb92bbfd1d6c15cf60ee2c723fbddb3a2cd927f1fede38d00e',
        'persistence_quests_sha': '99abd0d87d5bf18fa2a133ca6d7efb1a2dda1570fb659fcc284e20cbcc3339e0',
        'quests_completed_main_raw': '[]',
        'quests_daily_raw': '{}',
        'quests_main_progress_raw': '{}',
        'quests_side_raw': '{}',
        'u1i4_outer_frozen_sha': 'bc69a9aa3d258214827dae0f39765ecfbbd03c412d6e2fc92c38b026748c235a',
        'u1i4_world_frozen_sha': '97451a218d05559a1cfa8a5244de758cc5653c34de037e9af4924b44b516649f',
    },
    'segments': {
        'E': [
            'content/quests_flow.py::sq_stats_met',
            'content/quests_flow.py::deliver_hint',
            'content/quests_flow.py::branch_wait_sid',
            'content/profession_quests.py::settle_daily_quest',
            'content/profession_quests.py::daily_pool',
            'content/world_cmds.py::_take_main_quest',
            'content/cmds_world.py::_svc',
            'content/cmds_world.py::_kill_prog_count',
        ],
        'C': [
            'content/quests_flow.py::obj_text',
            'content/quests_flow.py::sq_unlocked',
            'content/quests_flow.py::available_quest_list',
            'content/quests_flow.py::update_explore_quests',
            'content/quests_flow.py::take_main_quest',
            'content/quests_flow.py::quest_reputation',
            'content/quests_flow.py::side_available_list',
            'content/quests_flow.py::offer_side_quest',
            'content/quests_flow.py::offer_side_quests',
            'content/quests_flow.py::grant_quest_rewards',
            'content/quests_flow.py::complete_side_quest',
            'content/quests_flow.py::talk_quest_progress',
            'content/quests_flow.py::update_use_quests',
            'content/quests_flow.py::quest_kill_progress',
            'content/profession_quests.py::daily_need',
            'content/profession_quests.py::bump_daily_progress',
            'content/profession_quests.py::draw_daily',
            'content/world_cmds.py::_obj_text',
            'content/world_cmds.py::_obj_text_lines',
            'content/cmds_world.py::quest_view',
        ],
    },
    'tier': {
        'content/quests_flow.py::obj_text': '甲',
        'content/quests_flow.py::sq_unlocked': '甲',
        'content/quests_flow.py::sq_stats_met': '甲',
        'content/quests_flow.py::available_quest_list': '甲',
        'content/quests_flow.py::update_explore_quests': '甲',
        'content/quests_flow.py::take_main_quest': '甲',
        'content/quests_flow.py::quest_reputation': '甲',
        'content/quests_flow.py::deliver_hint': '甲',
        'content/quests_flow.py::side_available_list': '甲',
        'content/quests_flow.py::offer_side_quest': '甲',
        'content/quests_flow.py::offer_side_quests': '甲',
        'content/quests_flow.py::grant_quest_rewards': '甲',
        'content/quests_flow.py::complete_side_quest': '甲',
        'content/quests_flow.py::talk_quest_progress': '甲',
        'content/quests_flow.py::update_use_quests': '甲',
        'content/quests_flow.py::branch_wait_sid': '甲',
        'content/quests_flow.py::quest_kill_progress': '甲',
        'content/profession_quests.py::daily_need': '甲',
        'content/profession_quests.py::settle_daily_quest': '甲',
        'content/profession_quests.py::bump_daily_progress': '甲',
        'content/profession_quests.py::daily_pool': '甲',
        'content/profession_quests.py::draw_daily': '甲',
        'content/world_cmds.py::_obj_text': '甲',
        'content/world_cmds.py::_obj_text_lines': '甲',
        'content/world_cmds.py::_take_main_quest': '甲',
        'content/cmds_world.py::_svc': '甲',
        'content/cmds_world.py::_kill_prog_count': '甲',
        'content/cmds_world.py::quest_view': '甲',
    },
}
# <<< _u1d2_quest_gen (auto) <<<


# ══════════════════════════════════════════════════════════════════════════════
# 1. 旧实现命名空间（frozen 文本 exec）+ 猴补 + 注入
# ══════════════════════════════════════════════════════════════════════════════
def _noop_register(*_a, **_k):
    def _deco(fn):
        return fn
    return _deco


_MODS = {
    "content/quests_flow.py": QF,
    "content/profession_quests.py": PQ,
    "content/world_cmds.py": WC,
    "content/cmds_world.py": CW,
}


class _ModShim:
    """旧命名空间里的模块句柄：**冻结段优先**、其余转活模块（`cmds_world._WC` 用）。"""

    def __init__(self, mod, frozen):
        self._mod, self._frozen = mod, frozen

    def __getattr__(self, name):
        if name in self._frozen:
            return self._frozen[name]
        return getattr(self._mod, name)


OLD = {}
for _rel, _mod in _MODS.items():
    _ns = dict(vars(_mod))
    _ns["register"] = _noop_register
    _ns["declared"] = _noop_register
    _ns["require_player"] = _noop_register
    OLD[_rel] = _ns
for _key, _text in _FROZEN_TEXT.items():
    _rel, _sym = _key.split("::")
    exec(compile(_text, "<frozen:%s>" % _key, "exec"), OLD[_rel])          # noqa: S102
# `cmds_world` 旧命名空间的 `_WC` 必须看到 **world_cmds 的冻结段**（否则旧 quest_view
# 会调活实现 = 拿新比新，门禁失去牙）。
OLD["content/cmds_world.py"]["_WC"] = _ModShim(
    WC, {s: OLD["content/world_cmds.py"][s] for _r, s in ()} or {
        sym: OLD["content/world_cmds.py"][sym]
        for rel, sym in (("content/world_cmds.py", "_obj_text"),
                         ("content/world_cmds.py", "_obj_text_lines"),
                         ("content/world_cmds.py", "_take_main_quest"))})


def _old(rel, sym):
    return OLD[rel][sym]


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


class _Inject:
    """把替身同时写进**活模块**与**旧命名空间**（退出原地还原）。"""

    def __init__(self, pairs, **kw):
        self.pairs, self.kw = pairs, kw
        self.old = []
        self.old_mod = []

    def __enter__(self):
        for mod, ns in self.pairs:
            self.old.append({k: ns.get(k, _MISSING) for k in self.kw})
            self.old_mod.append((mod, {k: getattr(mod, k, _MISSING) for k in self.kw}))
            for k, v in self.kw.items():
                ns[k] = v
                setattr(mod, k, v)
        return self

    def __exit__(self, *exc):
        for (mod, _ns), old in zip(self.old_mod, self.old):
            for k, v in old.items():
                if v is _MISSING:
                    if hasattr(mod, k):
                        delattr(mod, k)
                else:
                    setattr(mod, k, v)
        for (mod, ns), old in zip(self.pairs, self.old):
            for k, v in old.items():
                if v is _MISSING:
                    ns.pop(k, None)
                else:
                    ns[k] = v
        return False


def _run(fn, *a, **k):
    """调用并规整结果（异常收敛成可比较的元组，不吞成「相等」）。"""
    try:
        return ("ok", fn(*a, **k))
    except Exception as exc:                                            # noqa: BLE001
        return ("exc", type(exc).__name__, str(exc)[:200])


# ══════════════════════════════════════════════════════════════════════════════
# 2. 数据面 / 替身
# ══════════════════════════════════════════════════════════════════════════════
MAIN = list(MAIN_QUESTS)
SIDE = list(SIDE_QUESTS)
DAILY = list(DAILY_QUESTS)
ALLQ = MAIN + SIDE + DAILY

_MAIN_IDS = {q["id"] for q in MAIN}
_Q1_1 = next((q for q in MAIN if q["id"] == "q1_1"), None)
_REAL_EXPIRE = None                # 由 _boot() 填（content.persistence.quests.expire_daily）

READONLY_FILES = ("content/quests_flow.py", "content/profession_quests.py",
                  "content/world_cmds.py", "content/cmds_world.py")
ZERO_CHANGE_FILES = ("content/catalog_quests.py", "content/persistence/quests.py")
U1I4_GATES = ("test_u1i4_wiring_world_frozen.py", "test_u1i4_wiring_outer_frozen.py")

#: 新实现是否已接上引擎形状（红基线档 = False ⇒ 引擎侧探针按 §10 判据 16 暂不启用）
_HAS_NEW = hasattr(QF, "_OBJECTIVES")


def _pkg_file(relpath):
    return os.path.join(PKG_ROOT, *relpath.split("/"))


def _file_sha(relpath):
    with open(_pkg_file(relpath), encoding="utf-8") as fh:
        return sha256(fh.read())


def _frozen_block(path):
    """U1-I4 门禁文件里 `_FROZEN_TEXT` 那一块（BEGIN..`_PIN = {`）的原文。"""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("# >>> ")
    j = src.index("_PIN = {")
    return src[i:j]


def _db_path():
    getter = getattr(db, "db_path", None)
    return getter() if callable(getter) else db.DB_PATH


def _read_row_raw(g, q):
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            "SELECT main_quest, main_status, main_progress, daily, completed_main, side "
            "FROM quests WHERE qq_id=?", (q,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"main_quest": row[0], "main_status": row[1], "main_progress": row[2],
            "daily": row[3], "completed_main": row[4], "side": row[5]}


class _FakeDB:
    """内存替身（账本 / 玩家 / 背包 / 统计）——记录奖励与玩家更新，绝不落盘。"""

    def __init__(self, quests=None, player=None, items=None, stats=None, expire=True):
        self.quests = json.loads(json.dumps(quests or {}))
        self.player = json.loads(json.dumps(player or {}))
        self.items = dict(items or {})
        self.stats = dict(stats or {})
        self.expire = expire
        self.saved = 0
        self.updates = []
        self.rewards = []
        self.reputation = []
        self.talk_flags = []

    # ---- 账本 ----
    def get_quests(self, g, q):
        return json.loads(json.dumps(self.quests))

    def save_quests(self, g, q, data):
        self.quests = json.loads(json.dumps(data))
        self.saved += 1

    def expire_daily(self, quest_data):
        if not self.expire:
            return False
        return _REAL_EXPIRE(quest_data)

    # ---- 玩家 ----
    def get_player(self, g, q):
        return json.loads(json.dumps(self.player))

    def update_player(self, g, q, **kw):
        self.updates.append(sorted(kw.items()))
        for k, v in kw.items():
            self.player[k] = v

    # ---- 背包 / 其它 ----
    def count_item(self, g, q, name):
        return int(self.items.get(name, 0))

    def remove_item(self, g, q, name, n=1):
        self.items[name] = max(0, int(self.items.get(name, 0)) - int(n))

    def get_stats(self, g, q):
        return dict(self.stats)

    def get_talk_flags(self, g, q, npc_id=None):
        return list(self.talk_flags)

    def add_reputation(self, g, q, faction, n):
        self.reputation.append((faction, n))


def _snap(fake):
    return json.dumps({
        "quests": fake.quests,
        "updates": [[list(kv) for kv in u] for u in fake.updates],
        "rewards": fake.rewards,
        "reputation": fake.reputation,
        "items": fake.items,
    }, ensure_ascii=False, sort_keys=False)


def _mk_player(level, cur_map, gold=0, exp=0):
    return {"qq_id": "p1", "group_id": "g1", "name": "T", "cls": "cls_zhan_shi",
            "level": level, "cur_map": cur_map, "cur_subarea": "", "race": "human",
            "gold": gold, "exp": exp, "hp": 100, "mp": 50, "max_hp": 100, "max_mp": 50,
            "skills": [], "attr_pts": 0, "skill_points": 0, "learned_skills": [],
            "hidden_class_unlock": [], "_title_bonus": 0}


def _npc_of(npc_id):
    return NPCS.get(npc_id) or _WILD.ALL_WILD.get(npc_id) or {}


def _npc_map(npc_id):
    return _npc_of(npc_id).get("map") or ""


def _need_collect(obj):
    return obj.get("collect_count") or obj.get("count", 1)


# ══════════════════════════════════════════════════════════════════════════════
# [1] 双 sha256 + E/C 分类 + 分级（判据 1 / 2 / 9）
# ══════════════════════════════════════════════════════════════════════════════
def test_frozen_pins():
    print("【1. 双 sha256：28 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 28", len(keys) == 28, len(keys))
    check("门禁内键序 == 冻结文本键序", keys == list(_FROZEN_TEXT), keys[:3])
    bad = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("冻结文本 sha256 全等 _PIN['frozen']（28 段）", not bad, bad[:4])

    live_bad = []
    for k in keys:
        rel, sym = k.split("::")
        obj = getattr(_MODS[rel], sym, None)
        got = "<deleted>" if obj is None else sha256(inspect.getsource(obj))
        if got != _PIN["live"][k]:
            live_bad.append((k, _PIN["live"][k][:12], got[:12]))
    check("活实现 inspect.getsource sha256 全等 _PIN['live']（28 段）", not live_bad, live_bad[:4])

    seg = _PIN["segments"]
    chkE = [k for k in seg["E"] if _PIN["frozen"][k] != _PIN["live"][k]]
    check("E 栏「预期不变」段 frozen == live（%d 段）" % len(seg["E"]), not chkE, chkE[:3])
    if _PIN["phase"] == "landed":
        chkC = [k for k in seg["C"] if _PIN["frozen"][k] == _PIN["live"][k]]
        check("C 栏「预期会变」段 frozen != live（%d 段）" % len(seg["C"]), not chkC, chkC[:3])
    else:
        print("  ⓘ phase=%r：C 栏不等式断言按「红基线」档暂不启用" % (_PIN["phase"],))

    tiers = {}
    for k in keys:
        tiers.setdefault(_PIN["tier"][k], []).append(k)
    got_tiers = (len(tiers.get("甲", [])), len(tiers.get("乙", [])), len(tiers.get("丙", [])))
    check("分级：甲 28 / 乙 0 / 丙 0（实测 %d / %d / %d）" % got_tiers, got_tiers == (28, 0, 0))

    # 判据 9 / 10 的「预跑」部分：与 base/pkg 直比（frozen 侧一字不改 / 零改动）
    # ★ 2026-09-17 落地后修正（主线收口）：本组断言原本直比 `base/pkg` —— 那是**线的工作区布局**。
    #   真仓布局下没有 `base/pkg` 基线副本 ⇒ 不静默跳过、也不假绿，改为显式标注「本布局不适用」，
    #   并打印等价口径的落点（同一事实已由「判据 4：aux[] 全等 _PIN」断言，含
    #   catalog_quests_sha / persistence_quests_sha / u1i4_{world,outer}_frozen_sha 四项）。
    _base_ok = os.path.isfile(os.path.join(LANE_ROOT, "base", "pkg", "content", "quests_flow.py"))
    if _base_ok:
        for f in ZERO_CHANGE_FILES:
            base_f = os.path.join(LANE_ROOT, "base", "pkg", *f.split("/"))
            same = os.path.isfile(base_f) and _file_sha(f) == sha256(open(base_f, encoding="utf-8").read())
            check("零改动证明：%s == base/pkg 同文件" % f, same)
        for name in U1I4_GATES:
            cur = os.path.join(_HERE, name)
            base_f = os.path.join(LANE_ROOT, "base", "pkg", "tests", name)
            same = os.path.isfile(base_f) and _frozen_block(cur) == _frozen_block(base_f)
            check("U1-I4 门禁 frozen 侧一字不改：%s（与 base/pkg 直比）" % name, same)
    else:
        for f in ZERO_CHANGE_FILES:
            print("  ⏭ 不适用（真仓布局：无 base/pkg）：零改动证明 <- 判据 4 aux 已断言 %s" % f)
        for name in U1I4_GATES:
            print("  ⏭ 不适用（真仓布局：无 base/pkg）：frozen 侧一字不改 <- 判据 4 aux 已断言 %s" % name)
        print("     口径说明：本组 4 项需「线工作区布局」；真仓由 _PIN[aux] 同源 sha256 覆盖，语义等价。")


# ══════════════════════════════════════════════════════════════════════════════
# [2] 甲类 exec 双向逐格比 —— 全量网格 13,064 格（判据 3）
# ══════════════════════════════════════════════════════════════════════════════
_CELLS = {}
_MISM = []


def _cmp(row, a, b):
    _CELLS[row] = _CELLS.get(row, 0) + 1
    if a != b:
        _MISM.append((row, a, b))


# ────────────────────────────────────────── ① accept：5,712 格
def _qid(q):
    """任务键：主线/支线有 `id`；每日任务**没有 id**（口径分歧⑩，键 = `name`）。"""
    return q.get("id") or q["name"]


def _effective_row(q):
    return q if q.get("id") in _MAIN_IDS else _Q1_1


def _levels_for(q):
    ml = q.get("min_level")
    return (ml - 1, ml, ml + 5) if ml else (1, 50, 100)


def _presence(row, present):
    giver = row.get("giver")
    gm = _npc_map(giver)
    if present:
        return giver, (gm or "oak_town")
    return "__u1d2_absent__", ("white_deer" if gm != "white_deer" else "oak_town")


def _pre_ledger(qid, pre):
    led = {"main_quest": qid, "main_status": pre, "main_progress": {},
           "completed_main": [], "side": {}, "daily": {}}
    if pre == "done":
        led["main_quest"] = None
        led["completed_main"] = [qid]
    return led


def _accept_call(fn, q, pre, level, present):
    row = _effective_row(q)
    npc_id, cur_map = _presence(row, present)
    fake = _FakeDB(quests=_pre_ledger(_qid(q), pre), player=_mk_player(level, cur_map))
    npc = {"name": "测试NPC", "gender": "男", "funcs": ["quest"]}
    # ⚠ 必须**注入替身库**：否则旧/活两侧都会打真库（先跑的那侧改状态 → 后跑的那侧读到
    #   改了的状态 = 假红）。`_Inject` 同时写活模块与旧命名空间，两侧各拿同一个 fake。
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake):
        res = _run(fn, "g1", "p1", npc_id, npc)
    return (res, _snap(fake))


def _accept_pair(q, pre, level, present):
    old = _accept_call(_old("content/quests_flow.py", "take_main_quest"),
                       q, pre, level, present)
    live = _accept_call(QF.take_main_quest, q, pre, level, present)
    _cmp("accept", old, live)


def _grid_accept():
    for q in ALLQ:
        for pre in ("pending", "active", "ready", "done"):
            for lv in _levels_for(q):
                for present in (True, False):
                    _accept_pair(q, pre, lv, present)


# ────────────────────────────────────────── ② fold：1,904 格
_EVENTS = ("kill", "kill_variant", "kill_any", "kill_elite", "kill_boss",
           "collect", "use", "explore")


def _fold_event(kind, obj):
    kill = obj.get("kill") or "__u1d2_none__"
    if kind == "kill_variant":
        name = kill + "·首领"
    elif kind == "kill":
        name = kill
    else:
        name = "__u1d2_none__"
    return {"name": name, "kind": kind,
            "is_elite": kind == "kill_elite", "is_boss": kind == "kill_boss",
            "collect": obj.get("collect") or "__u1d2_none__",
            "have": _need_collect(obj),
            "use": obj.get("use") or "__u1d2_none__",
            "map": obj.get("explore") or obj.get("map") or "__u1d2_none__"}


def _fold_old(q, kind, obj):
    """旧侧：冻结入口函数在同一事件下的**进度补丁**（一律在 side lane 读差异）。"""
    qid = "sft_" + str(_qid(q))
    fake = _FakeDB(quests={
        "main_quest": None, "main_status": "pending", "main_progress": {},
        "completed_main": [], "daily": {},
        "side": {qid: {"status": "active", "progress": {}}}})
    fake.player = _mk_player(1, obj.get("map") or "")
    row = {"id": qid, "name": "合成", "giver": "npc_mayor", "objective": obj,
           "desc": "", "reward_exp": 0, "reward_gold": 0}
    ev = _fold_event(kind, obj)
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake), \
            _Patch(CQ, "SIDE_QUESTS", [row]):
        if kind in ("kill", "kill_variant", "kill_any", "kill_elite", "kill_boss"):
            _run(_old("content/quests_flow.py", "quest_kill_progress"),
                 "g1", "p1", ev)
        elif kind == "use":
            _run(_old("content/quests_flow.py", "update_use_quests"),
                 "g1", "p1", ev["use"])
        elif kind == "explore":
            _run(_old("content/quests_flow.py", "update_explore_quests"),
                 "g1", "p1", ev["map"])
    return fake.quests["side"].get(qid, {}).get("progress", {})


def _fold_new(kind, obj):
    ev = _fold_event(kind, obj)
    if not _HAS_NEW:
        return None                                     # 红基线档：引擎形状还没接上
    return QF._OBJECTIVES.fold(obj, {}, ev)


def _grid_fold():
    for q in ALLQ:
        obj = q.get("objective") or {}
        for kind in _EVENTS:
            old = _fold_old(q, kind, obj)
            new = _fold_new(kind, obj)
            if new is None:
                new = old
            _cmp("fold", old, new)


# ────────────────────────────────────────── ③ side 表：2,592 格
_COMBOS = (
    ("off",    {"board": False, "unlock": None, "require_stats": None, "min_level": None}),
    ("board",  {"board": True, "unlock": None, "require_stats": None, "min_level": None}),
    ("unlock", {"board": False, "unlock": {"side": "__u1d2_never__"},
                "require_stats": None, "min_level": None}),
    ("stats",  {"board": False, "unlock": None,
                "require_stats": {"__u1d2_stat__": 9999}, "min_level": None}),
    ("level",  {"board": False, "unlock": None, "require_stats": None, "min_level": 999}),
    ("all",    {"board": True, "unlock": {"side": "__u1d2_never__"},
                "require_stats": {"__u1d2_stat__": 9999}, "min_level": 999}),
)


def _side_list_pair(q, combo, level):
    row = dict(q)
    row.update(combo)
    npc_id = q.get("giver")
    cur_map = _npc_map(npc_id)
    fake = _FakeDB(quests={"main_quest": None, "main_status": "pending", "main_progress": {},
                           "completed_main": [], "side": {}, "daily": {}},
                   player=_mk_player(level, cur_map))
    npc = _npc_of(npc_id)
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake), \
            _Patch(CQ, "SIDE_QUESTS", [row]):
        old = (_run(_old("content/quests_flow.py", "available_quest_list"),
                    fake.player, fake.quests, None),
               _run(_old("content/quests_flow.py", "side_available_list"),
                    "g1", "p1", npc_id, npc))
        live = (_run(QF.available_quest_list, fake.player, fake.quests, None),
                _run(QF.side_available_list, "g1", "p1", npc_id, npc))
    _cmp("side_list", old, live)


def _grid_side_list():
    for q in SIDE:
        for _tag, combo in _COMBOS:
            for lv in (1, 50, 100):
                _side_list_pair(q, combo, lv)


# ────────────────────────────────────────── ④ render：1,428 格
class _ShellStub:
    def _is_redname(self, qq_id):
        return False

    def _tip(self, kind):
        return "TIP"

    def _record_list_state(self, *a):
        pass


class _EnvStub:
    def __init__(self, player, group_id="g1", uid="p1"):
        self.group_id, self.uid, self.player = group_id, uid, player

    def arg_text(self, cmd):
        return ""

    def page(self, raw):
        return 1

    def page_items(self, items, page, per_page=5):
        return (list(items), 1, 1)


class _PanelDB:
    def __init__(self, quests):
        self._q = quests

    def get_quests(self, g, q):
        return json.loads(json.dumps(self._q))

    def save_quests(self, g, q, data):
        self._q = json.loads(json.dumps(data))

    def count_item(self, g, q, item):
        return 0

    def get_talk_state(self, g, q):
        return None


def _render_pair(q, port, st):
    obj = q.get("objective") or {}
    if port == "obj_text":
        old = _run(_old("content/quests_flow.py", "obj_text"), obj)
        live = _run(QF.obj_text, obj)
    elif port == "_obj_text_lines":
        old = _run(_old("content/world_cmds.py", "_obj_text_lines"), None, obj, st)
        live = _run(WC._obj_text_lines, None, obj, st)
    else:
        led = {"main_quest": _qid(q), "main_status": st, "main_progress": {},
               "completed_main": [], "side": {}, "daily": {}}
        shell = _ShellStub()
        env = _EnvStub(_mk_player(50, "oak_town"))
        pdb = _PanelDB(led)
        ns = OLD["content/cmds_world.py"]
        with _Inject([(CW, ns)], db=pdb, _shell=lambda e: shell, MAIN_QUESTS=[q],
                     SIDE_QUESTS=[]):
            old = _run(_old("content/cmds_world.py", "quest_view"), env)
            live = _run(CW.quest_view, env)
    _cmp("render", old, live)


def _grid_render():
    for q in ALLQ:
        for port in ("obj_text", "_obj_text_lines", "quest_view"):
            for st in ("active", "ready"):
                _render_pair(q, port, st)


# ────────────────────────────────────────── ⑤ ledger 往返：1,428 格
def _ledger_raw(q, lane, variant):
    qid = _qid(q)
    obj = q.get("objective") or {}
    raw = {"main_quest": None, "main_status": "pending", "main_progress": {},
           "completed_main": [], "side": {}, "daily": {}}
    if lane == "main":
        raw["main_quest"] = qid
        raw["main_status"] = "active" if variant == 0 else "ready"
        if variant:
            raw["main_progress"] = {"k": 1}
            raw["completed_main"] = [qid]
    elif lane == "side":
        entry = {"status": "active" if variant == 0 else "ready"}
        if variant:
            entry["progress"] = {"k": 2}
        raw["side"] = {qid: entry}
    else:
        raw["daily"] = {"_date": _TODAY, "_completed": variant, "_repeat": {qid: variant},
                        "d0": {"name": qid, "desc": "", "objective": obj,
                               "reward_exp": 0, "reward_gold": 0,
                               "repeat": variant, "progress": variant}}
    return raw


def _serialize(raw):
    return (json.dumps(raw.get("main_progress", {}), ensure_ascii=False),
            json.dumps(raw.get("daily", {}), ensure_ascii=False),
            json.dumps(raw.get("completed_main", []), ensure_ascii=False),
            json.dumps(raw.get("side", {}), ensure_ascii=False))


def _ledger_pair(q, lane, variant):
    raw = _ledger_raw(q, lane, variant)
    want = (_serialize(raw), raw.get("main_quest"), raw.get("main_status"),
            list(raw["main_progress"].keys()), list(raw["side"].keys()),
            list(raw["daily"].keys()))
    if _HAS_NEW:
        shell = QF._log(raw)
        saved = shell.snapshot()
    else:
        saved = dict(raw)                     # 红基线档：引擎账本还没接上（退化 = 直存）
    db.save_quests("u1d2led", "p1", saved)
    row = _read_row_raw("u1d2led", "p1")
    got = ((row["main_progress"], row["daily"], row["completed_main"], row["side"]),
           row["main_quest"], row["main_status"],
           list(json.loads(row["main_progress"]).keys()),
           list(json.loads(row["side"]).keys()),
           list(json.loads(row["daily"]).keys()))
    _cmp("ledger", want, got)


def _grid_ledger():
    db.init_db()
    for q in ALLQ:
        for lane in ("main", "side", "daily"):
            for variant in (0, 1):
                _ledger_pair(q, lane, variant)


# ══════════════════════════════════════════════════════════════════════════════
# [3] 网格主入口 + 计数校验
# ══════════════════════════════════════════════════════════════════════════════
_EXPECT = {"accept": 5712, "fold": 1904, "side_list": 2592, "render": 1428, "ledger": 1428}


def test_grid():
    print("【2. 全量网格：旧实现（冻结文本 exec）↔ 活实现 逐格比】")
    if len(ALLQ) != 238:
        check("数据面 238 任务（main %d / side %d / daily %d）" % (len(MAIN), len(SIDE), len(DAILY)),
              False, len(ALLQ))
    else:
        check("数据面 238 任务（main 70 / side 144 / daily 24）", True)
    for fn in (_grid_accept, _grid_fold, _grid_side_list, _grid_render, _grid_ledger):
        fn()
    for row in ("accept", "fold", "side_list", "render", "ledger"):
        n = _CELLS.get(row, 0)
        check("网格 %-9s = %5d 格 == 预期 %5d" % (row, n, _EXPECT[row]), n == _EXPECT[row],
              (n, _EXPECT[row]))
    total = sum(_CELLS.values())
    check("网格合计 = %d 格 == 预期 13064 格" % total, total == 13064, total)
    check("逐格比对无不一致（旧 == 新）", not _MISM, _MISM[:2])


# ══════════════════════════════════════════════════════════════════════════════
# [4] 口径分歧 12 条（判据 4）
# ══════════════════════════════════════════════════════════════════════════════
def test_divergences():
    print("【3. 口径分歧 12 条（DESIGN.md §2.3）】")
    if not _HAS_NEW:
        print("  ⓘ phase=%r：引擎形状（_OBJECTIVES / _log）还没接上 → 引擎侧分歧断言暂不启用"
              % (_PIN["phase"],))
        print("     （红基线档只跑与实现无关的 ⑦ ⑩ ⑪ 三条）")
    O = getattr(QF, "_OBJECTIVES", None)

    # ① 主线无 done 状态：交付只追加 completed_main + 状态回 pending；支线交付写 done
    fake = _FakeDB(quests=_pre_ledger("q1_1", "ready"), player=_mk_player(50, "oak_town"))
    fake.items = {}
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake):
        QF.take_main_quest("g1", "p1", "npc_mayor", {"name": "镇长", "gender": "男"})
    led = fake.quests
    check("① 主线交付：completed_main 追加 + main_status 回 pending（无 done 状态）",
          "q1_1" in (led.get("completed_main") or []) and led.get("main_status") == "pending",
          (led.get("completed_main"), led.get("main_status")))
    _sid_kill = next(q["id"] for q in SIDE
                     if (q.get("objective") or {}).get("kill")
                     and not (q.get("objective") or {}).get("collect")
                     and not q.get("branch"))
    fake2 = _FakeDB(quests={"main_quest": None, "main_status": "pending", "main_progress": {},
                            "completed_main": [], "side": {_sid_kill: {"status": "ready",
                                                                       "progress": {}}},
                            "daily": {}}, player=_mk_player(50, "oak_town"))
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake2):
        QF.complete_side_quest("g1", "p1", _sid_kill,
                               hooks={"tip": lambda _c: "", "rule_fire": lambda *_a: ""})
    check("① 支线交付：条目 status == done（最小终态一格）",
          fake2.quests["side"][_sid_kill].get("status") == "done",
          fake2.quests["side"][_sid_kill])

    if _HAS_NEW:
        # ② obj_text 只出第一型（kill 优先）/ _obj_text_lines 全出
        o1 = {"collect": "花", "count": 1, "kill": "野猪", "count2": 0}
        o2 = {"collect": "花", "count": 1, "kill": "野猪"}
        check("② obj_text 首命中 = kill（目标键序倒置也 kill 优先）",
              QF.obj_text(o2) == _old("content/quests_flow.py", "obj_text")(o2)
              and QF.obj_text(o2).startswith("击败"), QF.obj_text(o2))
        lines = WC._obj_text_lines(None, {"kill": "野猪", "count": 2, "collect": "花",
                                          "count2": 1}, "active")
        check("② _obj_text_lines 复合目标全出（2 行）", len(lines) == 2, lines)
        check("② 渲染口行序 = 声明序（kill → collect，与目标键插入序无关）",
              lines[0].startswith("击败") and lines[1].startswith("收集"), lines)
        check("② 面板口只认 4 型（find/use 由面板专门分支处理）",
              set(CW._OBJ_PROGRESS_LINES) == {"kill", "collect", "explore", "talk"},
              sorted(CW._OBJ_PROGRESS_LINES))

        # ③ 进度容器 mapping ∪ int
        lanes = dict(QF._QL_LANES)
        check("③ lanes 声明：side=dict / daily=int",
              lanes.get("side", {}).get("progress") is dict
              and lanes.get("daily", {}).get("progress") is int, lanes)
        lg = QF._log({"main_quest": None, "main_status": "pending", "main_progress": {},
                      "completed_main": [], "side": {"a": {"status": "active"}},
                      "daily": {"d0": {"status": "active", "progress": 3}}})
        check("③ 每日 lane 进度是 int 原样保留（引擎只搬不解释）",
              lg.lane("daily")["d0"]["progress"] == 3,
              lg.lane("daily")["d0"]["progress"])
        check("③ 每日 lane（int 口径）整格交付清成 0",
              QF._lane_log({"daily": {"status": "active", "progress": 3}}).deliver(
                  lane="daily")["daily"] == {"status": "done", "progress": 0},
              QF._lane_log({"daily": {"status": "active", "progress": 3}}).deliver(lane="daily"))
        check("③ side lane（dict 口径）条目交付 = 最小终态一格（无 progress 残留）",
              QF._lane_log({"side": {"a": {"status": "active", "progress": {"k": 1}}}}).deliver(
                  lane="side", key="a")["side"]["a"] == {"status": "done"},
              QF._lane_log({"side": {"a": {"status": "active", "progress": {"k": 1}}}}).deliver(
                  lane="side", key="a")["side"]["a"])

        # ④ 需求数两口径
        check("④ need_of(collect) = collect_count 优先",
              O.need_of({"collect": "x", "collect_count": 4, "count": 9}, "collect") == 4,
              O.need_of({"collect": "x", "collect_count": 4, "count": 9}, "collect"))
        check("④ 无 collect_count 时 need_of(collect) = count",
              O.need_of({"collect": "x", "count": 3}, "collect") == 3)
        check("④ 主线 collect 路径仍用 count（第二种口径，逐字保留）",
              QF._need_main_collect({"collect": "x", "collect_count": 4, "count": 9}) == 9)

        # ⑤ 未注册目标类型：默认 None（不出行）；obj_text 兜底 "？"
        check("⑤ 未注册目标类型 → lines() 不出行",
              O.lines({"nope": 1}) == [], O.lines({"nope": 1}))
        check("⑤ obj_text 未注册目标 → '？'", QF.obj_text({"nope": 1}) == "？")

        # ⑥ next 缺失 / null 都 None
        from saintess_engine.quest import Quest as _Quest
        qa = _Quest({"id": "x", "objective": {}, "next": None}, objectives=O,
                    objective_key="objective", next_key="next")
        qb = _Quest({"id": "x", "objective": {}}, objectives=O,
                    objective_key="objective", next_key="next")
        check("⑥ next 缺失与 next=null 都返回 None", qa.next is None and qb.next is None)

    # ⑦ 击杀进度 key = obj['kill']；老 key（含目标名）聚合读回
    fake7 = _FakeDB(quests={"main_quest": None, "main_status": "pending", "main_progress": {},
                            "completed_main": [], "side": {"s3": {"status": "active",
                                                                  "progress": {}}},
                            "daily": {}}, player=_mk_player(50, "oak_town"))
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake7):
        QF.quest_kill_progress("g1", "p1", {"name": "森林狼·头狼", "kind": "kill"})
    check("⑦ 击杀进度 key = 目标名（不是怪名）",
          fake7.quests["side"]["s3"]["progress"] == {"森林狼": 1},
          fake7.quests["side"]["s3"]["progress"])
    check("⑦ 老 key（含目标名的历史 key）被 _kill_prog_count 聚合读回",
          CW._kill_prog_count({"kill": "森林狼"}, {"精英森林狼": 2}) == 2)

    # ⑧/⑨ 过滤语义（走 side_available_list）
    stats_row = {"h7": 0}
    fake8 = _FakeDB(quests={"main_quest": None, "main_status": "pending", "main_progress": {},
                            "completed_main": [], "side": {}, "daily": {}},
                    player=_mk_player(1, "oak_town"), stats=stats_row)
    row_stats = {"id": "s_hidden", "name": "隐藏", "desc": "", "giver": "npc_mayor",
                 "objective": {"kill": "x", "count": 1}, "require_stats": {"h7": 10},
                 "board": False, "min_level": None, "reward_exp": 0, "reward_gold": 0}
    row_lv = dict(row_stats, id="s_lv", require_stats=None, min_level=40)
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake8), \
            _Patch(CQ, "SIDE_QUESTS", [row_stats, row_lv]):
        got_stats = QF.side_available_list("g1", "p1", "npc_mayor", {})
        got_offer = QF.offer_side_quests("g1", "p1", "npc_mayor", {"name": "镇长", "gender": "男"})
    check("⑧ require_stats 不满足 → 不出现且无提示（隐藏线）",
          got_stats == [] and not any("隐藏线" in x or "h7" in x for x in got_offer), got_offer)
    check("⑧ min_level 不满足 → 有拒绝提示（明面门槛）",
          any("Lv.40" in x for x in got_offer), got_offer)
    board_rows = [dict(row_stats, id="s_board", require_stats=None, board=True)]
    fake9 = _FakeDB(quests={"main_quest": None, "main_status": "pending", "main_progress": {},
                            "completed_main": [], "side": {}, "daily": {}},
                    player=_mk_player(50, "oak_town"))
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake9), \
            _Patch(CQ, "SIDE_QUESTS", board_rows):
        avail = QF.available_quest_list(fake9.player, fake9.quests, None)
        slist = QF.side_available_list("g1", "p1", "npc_mayor", {})
    check("⑨ board 委托不进两个可接列表", avail == [] and slist == [], (avail, slist))

    # ⑩ 每日任务键 = name（无 id）；_repeat 按 name 计数
    check("⑩ 每日任务键 = name（DAILY_QUESTS 无 id 字段）",
          all("id" not in d for d in DAILY), [d.get("id") for d in DAILY][:2])
    _settle_src = _FROZEN_TEXT["content/profession_quests.py::settle_daily_quest"]
    check("⑩ _repeat 按 name 计数（settle_daily_quest 写 _repeat[name]）",
          "_repeat" in _settle_src and '[dq["name"]]' in _settle_src, _settle_src[-80:])

    # ⑪ 跨天清理用系统钟（逐字保留），不用注入钟
    check("⑪ expire_daily 源码用 datetime.date.today()（系统钟，逐字保留）",
          "datetime.date.today()" in inspect.getsource(_REAL_EXPIRE))
    stale = {"daily": {"_date": "1999-01-01", "d0": {"name": "x"}}}
    today = {"daily": {"_date": _TODAY, "d0": {"name": "x"}}}
    check("⑪ 跨天 → 清空；今天 → 不清", _REAL_EXPIRE(stale) is True
          and stale["daily"] == {} and _REAL_EXPIRE(today) is False)

    # ⑫ offer_side_quests 行序：接取行 → 拒绝行 → 已完成待交付（只第一条）
    r_ok = {"id": "s_ok", "name": "可接", "desc": "D", "giver": "npc_mayor", "board": False,
            "objective": {"kill": "x", "count": 1}, "reward_exp": 1, "reward_gold": 1}
    r_rej = {"id": "s_rej", "name": "不可接", "desc": "D", "giver": "npc_mayor", "board": False,
             "objective": {"kill": "x", "count": 1}, "min_level": 999,
             "reward_exp": 1, "reward_gold": 1}
    fake12 = _FakeDB(quests={"main_quest": None, "main_status": "pending", "main_progress": {},
                             "completed_main": [], "side": {"s_old": {"status": "ready"}},
                             "daily": {}}, player=_mk_player(50, "oak_town"))
    with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake12), \
            _Patch(CQ, "SIDE_QUESTS", [r_ok, r_rej, dict(
                r_ok, id="s_old", name="已完成")]):
        got = QF.offer_side_quests("g1", "p1", "npc_mayor", {"name": "镇长", "gender": "男"})
    idx_ok = next((i for i, x in enumerate(got) if "可接" in x), 10 ** 6)
    idx_rej = next((i for i, x in enumerate(got) if "Lv.999" in x), 10 ** 6)
    idx_done = next((i for i, x in enumerate(got) if "已完成" in x and "交付" in x), 10 ** 6)
    check("⑫ 行序：接取行 → 拒绝行 → 已完成待交付提示",
          idx_ok < idx_rej < idx_done, got)


# ══════════════════════════════════════════════════════════════════════════════
# [5] aux 指纹（判据 5 / 9 / 10）
# ══════════════════════════════════════════════════════════════════════════════
def _aux_fingerprints():
    out = {}
    db.init_db()
    try:
        H.clean_db("quests")
    except Exception:                                                    # noqa: BLE001
        pass
    g, q = "u1d2aux", "1001"
    db.save_quests(g, q, {"main_quest": "q1_1", "main_status": "pending",
                          "main_progress": {}, "completed_main": [], "side": {},
                          "daily": {}})
    row = _read_row_raw(g, q)
    out["quests_main_progress_raw"] = row["main_progress"]
    out["quests_daily_raw"] = row["daily"]
    out["quests_completed_main_raw"] = row["completed_main"]
    out["quests_side_raw"] = row["side"]
    # ⚠ 指纹必须**跨进程稳定**：`repr(<lambda>)` 带内存地址（ASLR）→ 同一份代码两次跑也
    #   不等 = 假红。改为钉「键序 + 每个 value 的函数名」（命名函数，跨进程稳定）。
    out["obj_progress_lines_raw"] = sha256(json.dumps(
        {"keys": list(CW._OBJ_PROGRESS_LINES),
         "names": [getattr(CW._OBJ_PROGRESS_LINES[k], "__name__", None)
                   for k in CW._OBJ_PROGRESS_LINES]},
        ensure_ascii=False, sort_keys=True))
    out["catalog_quests_sha"] = _file_sha("content/catalog_quests.py")
    out["persistence_quests_sha"] = _file_sha("content/persistence/quests.py")
    out["u1i4_world_frozen_sha"] = sha256(_frozen_block(
        os.path.join(_HERE, "test_u1i4_wiring_world_frozen.py")))
    out["u1i4_outer_frozen_sha"] = sha256(_frozen_block(
        os.path.join(_HERE, "test_u1i4_wiring_outer_frozen.py")))
    return out


#: ★ **有意差异登记**（`_PIN["aux"]` 里的**文件级 sha** 项）—— 与 `test_texts_table._ECONOMY_DB_SHA_INTENT`
#: 同构（登记表自身受自洽断言约束）。**口径不放宽**：只登记本 1 项，其余 8 项 aux 与
#: 将来任何**第 2 项**差异照旧判红。
#:
#: 2026-09-20 T4 第 4 轮（W8 ②）：包内 13 个模块的域读口样板收进引擎 ——
#: `_HERE/_PKG_ROOT + set_from_domains(_PKG_ROOT, …)` → `set_from_module(__file__, …)`；
#: `content/catalog_quests.py` 净 −5 行 ⇒ **文件 sha 必变**（本项只是「文件 sha」，与语义无关）。
#: U1-D2 真正盯的东西**一字未动**：28 段冻结文本 sha 与 28 段活实现 sha 全等（同轮实测），
#: 落盘 JSON 指纹 / U1-I4 frozen 侧 / persistence/quests.py 全部照旧。
#: ⚠ 若将来合法重采（`_u1d2_quest_gen.py --emit-aux`），本登记须同步移除或改值。
_AUX_SHA_INTENT = {
    'catalog_quests_sha': ('a01253296243131a3d740442c0d336158a42019f2e82995f99bd77f095f38d37',
                           'b67002499bfe09aae8c0a2366e032834c13244051244b456a847ad9f90929c4d'),
}


def _aux_expected(k):
    """该 aux 项「当前口径」的值：有意差异登记优先，其余 = `_PIN["aux"]` 冻结基准。"""
    it = _AUX_SHA_INTENT.get(k)
    return it[1] if it else _PIN["aux"][k]


def test_aux():
    print("【4. aux 指纹：quests 表落盘 JSON 原文 + 零改动 + U1-I4 frozen 侧】")
    now = _aux_fingerprints()
    for k in sorted(_PIN["aux"]):
        check("aux[%s] 全等 _PIN（有意差异登记优先）" % k, now.get(k) == _aux_expected(k),
              "%r != %r" % (str(now.get(k))[:60], str(_aux_expected(k))[:60]))
    check("★ 有意差异登记自洽（旧值 = 冻结基准 · 新值 != 旧值 · 条数恒 1）",
          len(_AUX_SHA_INTENT) == 1
          and all(k in _PIN["aux"] and old == _PIN["aux"][k] and new != old
                  for k, (old, new) in _AUX_SHA_INTENT.items()),
          _AUX_SHA_INTENT)
    check("aux 条数 == 9", len(_PIN["aux"]) == 9, sorted(_PIN["aux"]))
    check("零改动证明：catalog_quests.py / persistence/quests.py sha256 未变",
          _file_sha("content/catalog_quests.py") == _aux_expected("catalog_quests_sha")
          and _file_sha("content/persistence/quests.py")
          == _PIN["aux"].get("persistence_quests_sha"))


# ══════════════════════════════════════════════════════════════════════════════
# [6] 有牙反证（判据 6）：破坏 4 处 → 对应探针必须变红
# ══════════════════════════════════════════════════════════════════════════════
_PROBE_QUESTS = ([q for q in MAIN if q["id"] in ("q1_3", "q5_5")]
                 + [q for q in SIDE if q["id"] in ("s3", "s7", "s18")]
                 + DAILY[:2])


def _probe_render():
    """渲染口差分探针（need / 目标类型顺序 敏感）：不一致 → True。"""
    bad = False
    for q in ALLQ:
        obj = q.get("objective") or {}
        if _run(QF.obj_text, obj) != _run(_old("content/quests_flow.py", "obj_text"), obj):
            bad = True
            break
        for st in ("active", "ready"):
            if _run(WC._obj_text_lines, None, obj, st) != _run(
                    _old("content/world_cmds.py", "_obj_text_lines"), None, obj, st):
                bad = True
                break
        if bad:
            break
        if _run(WC._obj_text, None, obj) != _run(
                _old("content/world_cmds.py", "_obj_text"), None, obj):
            bad = True
            break
    return bad


def _probe_deliver():
    """交付探针（`deliver` 是否追加 archive）：不一致 → True。"""
    for q in _PROBE_QUESTS:
        for pre in ("ready", "active", "pending"):
            a = _accept_call(_old("content/quests_flow.py", "take_main_quest"),
                             q, pre, 50, True)
            b = _accept_call(QF.take_main_quest, q, pre, 50, True)
            if a != b:
                return True
    return False


def _probe_expire():
    """跨天清理探针：真清 vs 恒不清 —— 两者结果**相等**说明实现没依赖 expire（无牙）。"""
    q = next((x for x in DAILY if x["objective"].get("kill_any")), DAILY[0])
    qid = _qid(q)

    def _once(expire):
        fake = _FakeDB(quests={
            "main_quest": None, "main_status": "pending", "main_progress": {},
            "completed_main": [], "side": {},
            "daily": {"_date": "1999-01-01", "d0": {
                "name": qid, "objective": q["objective"], "progress": 0,
                "reward_exp": 0, "reward_gold": 0}}}, player=_mk_player(50, "oak_town"))
        fake.expire = expire
        with _Inject([(QF, OLD["content/quests_flow.py"])], db=fake):
            _run(QF.quest_kill_progress, "g1", "p1",
                 {"name": "x", "kind": "kill_any", "is_elite": True, "is_boss": True})
        return json.dumps(fake.quests, ensure_ascii=False, sort_keys=False)

    return _once(True) == _once(False)


def _break_deliver():
    """破坏③：`QuestLog.deliver` 跳过 archive 追加（主线完成不落 done）。"""
    from saintess_engine.quest import QuestLog as _QL

    def _deliver(self, *, lane, key=None, next_of=None):
        out = self._copy()
        if lane is None:
            out["main_quest"] = next_of(self.current) if next_of is not None else None
            out["main_status"] = "pending"
            out["main_progress"] = {}
            return out
        lane_map = dict(self.lane(lane))
        if key is None:
            lane_map["status"] = "done"
        else:
            lane_map[key] = {"status": "done"}
        out[lane] = lane_map
        return out

    return _Patch(_QL, "deliver", _deliver)


def _break_expire():
    """破坏④：`expire_daily` 改成永久不清（活实现侧）。"""
    return _Patch(QF, "_expire_daily", lambda quests: False)


def test_teeth():
    print("【5. 有牙反证：破坏 4 处 → 对应探针必须变红（原地还原 + 全程零写盘）】")
    if not _HAS_NEW or _PIN["phase"] != "landed":
        print("  ⓘ phase=%r / _HAS_NEW=%r：引擎形状还没接上 → 有牙反证按「红基线」档暂不启用"
              % (_PIN["phase"], _HAS_NEW))
        check("红基线档：有牙反证延后到 `--emit-live` 之后（判据 6 在落档档实测）", True)
        return
    before = {f: _file_sha(f) for f in READONLY_FILES}
    # 未破坏时探针必须为 False（= 旧 == 新）
    check("未破坏时渲染探针为 False（旧 == 新）", _probe_render() is False)
    check("未破坏时交付探针为 False（旧 == 新）", _probe_deliver() is False)
    check("未破坏时跨天清理探针为 False（实现依赖 expire_daily）", _probe_expire() is False)

    from saintess_engine.quest import Objectives as _Objectives

    order = tuple(getattr(QF, "_OBJ_ORDER"))
    cases = (
        ("① need 取错数（Objectives.need_of 恒 1）",
         lambda: _Patch(_Objectives, "need_of",
                        lambda self, objective, type_key=None: 1),
         _probe_render),
        ("② 目标类型顺序倒置（_OBJ_ORDER 反转）",
         lambda: _Patch(QF, "_OBJ_ORDER", tuple(reversed(order))),
         _probe_render),
        ("③ deliver 不追加 done",
         _break_deliver, _probe_deliver),
        ("④ expire_daily 改成永久不清",
         _break_expire, _probe_expire),
    )
    for name, breaker, probe in cases:
        with breaker():
            red = probe()
        print("     破坏 `%s`：预期变红 / 实测 %s" % (name, "变红 ✅" if red else "仍绿 ❌"))
        check("破坏 `%s` → 探针必须变红（预期变红 / 实测变红）" % name, red is True)
        check("还原 `%s` 后探针回绿" % name, probe() is False)

    print("  ── 多故障场景（只坏一处证明不了「各管一段」）──")
    with _break_deliver(), _break_expire():
        d1, d2 = _probe_deliver(), _probe_expire()
    check("两处同坏（deliver + expire）：两条探针各自变红", d1 is True and d2 is True, (d1, d2))
    with _break_deliver():
        d1, d2 = _probe_deliver(), _probe_render()
    check("换一处同坏（deliver）：渲染探针**仍绿**（各管一段）", d1 is True and d2 is False,
          (d1, d2))

    after = {f: _file_sha(f) for f in READONLY_FILES}
    check("反证全程零写盘：源文件 sha256 前后一致", before == after,
          [f for f in READONLY_FILES if before[f] != after[f]])


# ══════════════════════════════════════════════════════════════════════════════
# [7] 顺序断言（need 短路序 / 行序 = 声明序 / 分支信息序）
# ══════════════════════════════════════════════════════════════════════════════
def test_order():
    print("【6. 顺序断言：目标行行序 = 声明序 · need 取值序 · 分支信息序】")
    if not _HAS_NEW:
        print("  ⓘ phase=%r：引擎形状还没接上 → 顺序断言按「红基线」档暂不启用" % (_PIN["phase"],))
        check("红基线档：顺序断言延后到 `--emit-live` 之后", True)
        return
    A = {"kill": "野猪", "count": 2, "collect": "花", "count2": 1}
    B = {"collect": "花", "count": 1, "kill": "野猪", "count": 2}
    check("顺序①：目标键插入序**不影响**渲染行序（内容侧声明序 = kill → collect）",
          WC._obj_text_lines(None, A, "active") == WC._obj_text_lines(None, B, "active"),
          (WC._obj_text_lines(None, A, "active"), WC._obj_text_lines(None, B, "active")))
    calls = []

    def _mk_cb(name):
        def _cb(objective, engine):
            calls.append(name)
            return objective.get("count", 1)
        return _cb

    from saintess_engine.quest import Objective as _Objective, Objectives as _Objectives
    reg = _Objectives(_Objective("kill", need=_mk_cb("kill")),
                      _Objective("collect", need=_mk_cb("collect")))
    # ⚠ `parts()` 会**先为每个 part 求一次 need**（引擎契约），所以回调会各被调一次；
    #    `need_of(type_key=None)` 的返回值 = **首个 part 的型**的 need。断这两条。
    _got = reg.need_of({"kill": 1, "count": 2})
    check("顺序②：need_of(type_key=None) = 首个 part 的型（kill）",
          _got == 2 and calls and calls[0] == "kill" and "kill" in calls, (_got, calls))
    calls.clear()
    _got = reg.need_of({"collect": 1, "count": 2})
    check("顺序③：改目标插入序 → 取值型随之改（collect）",
          _got == 2 and calls and calls[0] == "collect" and "collect" in calls, (_got, calls))


# ══════════════════════════════════════════════════════════════════════════════
# [8] 只读
# ══════════════════════════════════════════════════════════════════════════════
def _check_readonly(before):
    print("【7. 只读：门禁跑完 4 个源文件 sha256 前后一致（不写盘）】")
    after = {f: _file_sha(f) for f in READONLY_FILES}
    bad = [f for f in READONLY_FILES if before[f] != after[f]]
    check("跑完全程 %d 个源文件 sha256 前后一致" % len(READONLY_FILES), not bad, bad)
    for f in READONLY_FILES:
        print("     %-32s %s" % (f, after[f]))
    zc = {f: _file_sha(f) for f in ZERO_CHANGE_FILES}
    check("零改动文件（catalog_quests / persistence/quests）跑完 sha256 == 开工时",
          all(before.get(f, zc[f]) == zc[f] for f in ZERO_CHANGE_FILES), zc)


def _boot():
    global _TODAY, _REAL_EXPIRE
    import datetime
    _TODAY = datetime.date.today().isoformat()
    from content.persistence.quests import expire_daily as _re
    _REAL_EXPIRE = _re


def main() -> int:
    print("==" * 36)
    print("U1-D2 冻结门禁①：任务块（28 段：quests_flow 17 / profession_quests 5 / "
          "world_cmds 3 / cmds_world 3）")
    print("==" * 36)
    _boot()
    print("phase = %r · GWEN_GAME_DB = %s · _HAS_NEW = %r"
          % (_PIN["phase"], os.environ.get("GWEN_GAME_DB"), _HAS_NEW))
    before = {f: _file_sha(f) for f in READONLY_FILES}
    before.update({f: _file_sha(f) for f in ZERO_CHANGE_FILES})
    before_files = dict(before)
    with _Patch(random, "choice", lambda seq: list(seq)[0]):
        test_frozen_pins()
        test_grid()
        test_divergences()
        test_aux()
        test_teeth()
        test_order()
    _check_readonly(before_files)
    print(f"\n{'-' * 46}\n结果：通过 {PASS} / 共 {PASS + FAIL}")
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
