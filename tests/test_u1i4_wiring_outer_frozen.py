# -*- coding: utf-8 -*-
"""U1-I4 冻结比对**门禁④**（外围装配）：8 文件 / **9 段**冻结文本 + 双 sha256 + 逐格探针。

跑法（工作区根；环境变量见 `BRIEF.md` §3.1）::

    PY="C:/Users/yuyu/AppData/Roaming/uv/tools/astrbot/Scripts/python.exe"
    "$PY" work/pkg/tests/_u1i4_wiring_outer_gen.py --check
    "$PY" work/pkg/tests/test_u1i4_wiring_outer_frozen.py

判据（`design/U1-I4_FROZEN_GATE.md` §10；本文件逐条打原始输出）
-------------------------------------------------------------
 [1] **9 段冻结文本 sha256 全等 `_PIN["frozen"]`** + **活实现 `inspect.getsource` sha256 全等
     `_PIN["live"]`**；`phase == "landed"` 时再断言 C 栏 6 段 `frozen != live`、E 栏 3 段 `frozen == live`。
 [2] **甲类 6 段 `exec` 双向逐格**（旧 = `_FROZEN_TEXT` 成品字面量 `exec` 出的那一份 ↔ 活实现）：
     `wild_trader_here`（表/位/可找三态）× `apprentice_protect_mats`（会话网格 + 两边界）×
     `quest_view`（会话 `npc` × 任务态）× `action_apprentice_check`（材料 × 副业解锁 × 树）×
     `tpl_teleport_portal`（战斗 × 方碑）× `roll_wild_encounter`（转发面）。
 [3] **乙类 1 段**：`instance_cmds._stage_npcs`（替身 `self`，`inst_stages` 下标/越界/非表各态）。
 [4] **丙类 2 段**：`economy_cmds.shop` / `buy` —— **异步生成器端到端驱动**（`self` 替身 + 模块替身），
     `行商名解析` / `限时在场判定` 决定输出行；旧 ↔ 新逐行比。
 [5] **aux 指纹**：`talk_state_*` / `talk_flags_*` 键格式与落盘 JSON 原文（§3-②③）+
     **丙类 golden 输出行**（§3-⑪）。
 [6] **口径分歧** 4 条：① `_stage_npcs` 节点取用真值链；② `wild_trader_here` 首个命中序；
     ③ `apprentice_protect_mats` 两边界（无会话 → `{}` / 节点非映射 → `{}`）；
     ④ `shop` 标题名随在场行商变化。
 [7] **有牙反证** 6 处（每处对应一个已改段）→ 探针**必须变红**，还原后回绿；全程零写盘。
 [8] **只读断言**：跑完全程 8 个源文件 sha256 不变。
 [9] **计数校验**：每类探针 `比对次数 == 预期`（防「循环没跑」的假绿）。

⚠ 「旧实现」= `_FROZEN_TEXT` 里的**成品字面量**（由 `tests/_u1i4_wiring_outer_gen.py` 从
   `base/pkg/**` 逐行 `ast` 切片），`exec` 到独立命名空间跑 —— 不是「读代码觉得等价」。
⚠ 刻意**不依赖 pytest**：直接 `python <本文件>`，`sys.exit(1 if FAIL else 0)`。
"""
from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import sys
import textwrap
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

# ★ 独立私有库（绝不碰生产 game_data.db）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(LANE_ROOT, "out", "test_u1i4_outer.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
os.environ.setdefault("GWEN_FRAMEWORK_DIR", os.path.join(LANE_ROOT, "work", "eng"))
os.environ.setdefault("GWEN_HOST_DIR", os.path.join(LANE_ROOT, "work", "host"))
_shim = os.path.join(_HERE, "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

import _paths                                                             # noqa: E402
import _engine_harness as H                                              # noqa: E402

db = H.db

from content import cmds_base_rules as CBR                               # noqa: E402
from content import instance_cmds as IC                                  # noqa: E402
from content import shop as SHOP                                         # noqa: E402
from content import cmds_world as CW                                     # noqa: E402
from content import economy_cmds as EC                                   # noqa: E402
from content import talk_actions as TA                                   # noqa: E402
from content import item_templates as IT                                 # noqa: E402
from content import combat_cmds as CC                                    # noqa: E402
from content import wild as W                                            # noqa: E402
from content import dialogue as DLG                                      # noqa: E402
from content.catalog_quests import NPCS, WILD_NPCS, HIDDEN_NPCS          # noqa: E402
from content.catalog_space import MAP_BY_ID as _MAP_BY_ID                # noqa: E402
from content.persistence import world as PW                              # noqa: E402
import saintess_engine.presence as PRES                                  # noqa: E402

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


#: 读盘白名单（判据 [8]；全程零写盘）
READONLY_FILES = (
    "content/cmds_base_rules.py", "content/instance_cmds.py", "content/shop.py",
    "content/cmds_world.py", "content/economy_cmds.py", "content/talk_actions.py",
    "content/item_templates.py", "content/combat_cmds.py",
)

#: 本批实际改动的 6 个文件（真仓 cp 清单用）
CHANGED_FILES = (
    "content/cmds_base_rules.py", "content/instance_cmds.py", "content/shop.py",
    "content/cmds_world.py", "content/economy_cmds.py",
)

# >>> _u1i4_outer_gen (auto) >>>

# ⚠ 本块由 `tests/_u1i4_wiring_outer_gen.py` 生成 —— 手工改动 = 门禁失去安全网。
# 冻结侧读 `base/pkg/**`（改动前基线）；`_PIN["live"]` 由 --emit-live 重生成。

_FROZEN_TEXT = {
    'content/cmds_base_rules.py::wild_trader_here': 'def wild_trader_here(player: dict, group_id: str = "", qq_id: str = "") -> str | None:\n    """v95.4：当前地图是否有可交易的野外行商（funcs 含 trade 且出现条件满足）。\n    #151 修复：返回命中的 NPC id（用于货摊标题显示正确 NPC 名），无则 None。\n    ★ B18-L7：逐字 = 宿主旧 `base.CommandBase._wild_trader_here`。"""\n    if not (group_id and qq_id):\n        return None\n    cur = player.get("cur_map", "")\n    for nid, wnpc in _wild.ALL_WILD.items():\n        if "trade" not in (wnpc.get("funcs") or []):\n            continue\n        if _wild.npc_map_id(nid, wnpc) != cur:\n            continue\n        if _wild.wild_npc_findable(nid, wnpc, player, group_id, qq_id):\n            return nid\n    return None\n',
    'content/instance_cmds.py::_stage_npcs': '    def _stage_npcs(self, group_id, qq_id) -> list:\n        """当前副本层内 NPC 列表(供『找』路由)"""\n        st_row = self._instance_battle_for(group_id, qq_id)\n        if not st_row:\n            return []\n        st = st_row["state"]\n        stages = st.get("inst_stages") or []\n        sidx = IR.stages_progress(st).index  # v185：当前层下标走 core/instance_run\n        stage = stages[sidx] if sidx < len(stages) else {}\n        return stage.get("npcs") or []\n',
    'content/shop.py::apprentice_protect_mats': 'def apprentice_protect_mats(group_id, qq_id) -> dict:\n    """v101.25 #305：当前对话树节点（拜师考验）需要的材料名 → 数量。\n\n    玩家正在导师考验节点（apprentice_check 选项）时，批量出售不能误卖这些\n    材料——round68 小红实锤：『出售 材料』把铁矿石×7 混卖，挖掘拜师直接卡死。\n    返回 {材料名: 需要数量}，无考验返回 {}。\n    """\n    db = _h(\'db\')  # ← from .. import db  # 惰性导入\n    st = db.get_talk_state(group_id, qq_id)\n    if not st:\n        return {}\n    npc_id = st.get("npc", "")\n    node_id = st.get("node", "")\n    dlg = C.get_dialogue(npc_id)\n    if not dlg:\n        return {}\n    node = C.dialogue_node(dlg, node_id)\n    if not isinstance(node, dict):\n        return {}\n    mats = {}\n    for o in (node.get("options") or []):\n        ac = (o.get("action") or {}).get("apprentice_check")\n        if ac:\n            mats[ac.get("item", "")] = int(ac.get("count", 1))\n    return mats\n',
    'content/cmds_world.py::quest_view': '@register("quest_view", guards=("hook:player",), params=("cmd=任务", "page"))\ndef quest_view(env) -> list:\n    """『任务』：冒险日志（主线 + 支线分页 + 每日进度 + 师门考验 + 底部提示）。"""\n    shell = _shell(env)\n    group_id, qq_id = env.group_id, env.uid\n    player = env.player\n    if shell._is_redname(qq_id):\n        return ["☠️ 你是红名！守卫不让你靠近任务板……(等红名消退再来)"]\n    quests = db.get_quests(group_id, qq_id)\n    lines = ["📜 【冒险日志】", "━━━━━━━━━━━━"]\n    # 主线\n    main_id = quests.get("main_quest")\n    if main_id:\n        mq = next((q for q in MAIN_QUESTS if q["id"] == main_id), None)\n        # v104 M19：旧存档 main_quest 指向已下线 id（如 "q1"）→ 面板主线空白。\n        # 与 _take_main_quest 同样的存档容错：重置回主线起点并落库。\n        if not mq:\n            quests["main_quest"] = "q1_1"\n            quests["main_status"] = "pending"\n            quests["main_progress"] = {}\n            main_id = "q1_1"\n            mq = next((q for q in MAIN_QUESTS if q["id"] == main_id), None)\n            db.save_quests(group_id, qq_id, quests)\n        if mq:\n            _ginfo = NPCS.get(mq["giver"]) or ALL_WILD.get(mq["giver"]) or {}\n            giver = _ginfo.get("name", "？")\n            giver_map = _ginfo.get("map", "")\n            giver_map_name = MAP_BY_ID.get(giver_map, {}).get("name", "？")\n            lines.append(f"【主线】『{mq[\'name\']}』")\n            lines.append(f"  {mq[\'desc\']}")\n            st = quests.get("main_status", "pending")\n            if st == "pending":\n                lines.append(f"  ⏳ 未接取：去找 {giver}(在{giver_map_name})对话接取")\n            elif st == "ready":\n                # v95.25 #47b：主线交付=找 NPC 自动触发（与『交付任务』指令并存），不写死交付方式\n                lines.append(f"  ✅ 目标达成！回去找 {giver} 交付")\n            else:\n                prog = quests.get("main_progress", {})\n                obj = mq["objective"]\n                # v101.3：目标类型展示查表化（kill/collect/explore/talk，顺序与原 if-elif 一致）\n                # v169.9：主线 collect 面板实时查背包（对齐支线口径）——此前只读 main_progress\n                # 存档，玩家采到材料但没对话过 NPC 时面板仍显示 0/N，误以为物品对不上（#143）\n                if obj.get("collect"):\n                    have = db.count_item(group_id, qq_id, obj["collect"])\n                    need = obj.get("count", 1)\n                    if have >= need:\n                        lines.append(f"  ✅ 材料已齐：{obj[\'collect\']} {have}/{need}（回去找 {giver} 交付）")\n                    else:\n                        lines.append(f"  收集：{have}/{need}")\n                else:\n                    for _k, _fn in _OBJ_PROGRESS_LINES.items():\n                        if obj.get(_k):\n                            lines.append(_fn(obj, prog))\n                            break\n    else:\n        lines.append("【主线】已全部完成！🎊")\n    # 支线（v101.25i3：已完成任务不进面板，鱼鱼：交了还显示）\n    side = quests.get("side", {})\n    side_items = [(sid, sq) for sid, sq in side.items() if sq.get("status", "active") != "done"]\n    if side_items:\n        lines.append("")\n        lines.append("【支线】")\n        raw = env.arg_text("任务")\n        page = env.page(raw)\n        page_items, pages, page = env.page_items(side_items, page, per_page=5)\n        for i, (sid, sq) in enumerate(page_items, (page - 1) * 5 + 1):\n            sqd = next((q for q in SIDE_QUESTS if q["id"] == sid), None)\n            if not sqd:\n                continue\n            giver = (NPCS.get(sqd["giver"]) or ALL_WILD.get(sqd["giver"]) or {}).get("name", "？")\n            st = sq.get("status", "active")\n            obj = sqd["objective"]\n            # v95.12：已交付支线显示已完成（不占可交付位）\n            if st == "done":\n                lines.append(f"{i:>2}. 『{sqd[\'name\']}』[✅ 已完成]")\n                continue\n            # v127.7 排版：任务名单独一行（名字+状态），描述缩进下一行，目标进度行统一再缩进\n            # v116 §3.4：进行中支线可放弃（主线不可弃），放弃提示统一放面板底部（v123e 去行尾冗余）\n            # 收集型：实时按背包材料判断（v104 补测：复合目标同时显示击杀进度防误导）\n            if obj.get("collect"):\n                have = db.count_item(group_id, qq_id, obj["collect"])\n                need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError\n                prog = sq.get("progress", {})\n                kill_txt = ""\n                if obj.get("kill"):\n                    kv = _kill_prog_count(obj, prog)  # v105 M19 P2：兼容旧档老 key 聚合\n                    kill_txt = f"｜击杀：{kv}/{obj.get(\'count\', 0)}"\n                if have >= need:\n                    lines.append(f"{i:>2}. 『{sqd[\'name\']}』[✅ 可交{kill_txt}]")\n                    lines.append(f"    {sqd[\'desc\']}")\n                    lines.append(f"    材料已齐！回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n                else:\n                    lines.append(f"{i:>2}. 『{sqd[\'name\']}』[⏳{kill_txt}]")\n                    lines.append(f"    {sqd[\'desc\']}")\n                    lines.append(f"    收集：{obj[\'collect\']} {have}/{need}{kill_txt}")\n                # v125.1 P2：复合目标（collect+use/find/explore，如 s53/s56/s64/s105）\n                # 补显其余目标行，与 find/use 分支的 _obj_text_lines 展示口径一致\n                # （收集/击杀行已在上方展示，过滤避免重复）\n                for _t in _WC._obj_text_lines(shell, obj, st):\n                    if _t.startswith(("收集", "击败")):\n                        continue\n                    lines.append(f"    {_t}")\n                continue\n            # v104 M20 P2：find 型（告示委托等）面板提示机制——在 XX 探索有概率遇到\n            # （此前走通用兜底只显示 desc+[⏳]，玩家不知如何推进）\n            if obj.get("find"):\n                lines.append(f"{i:>2}. 『{sqd[\'name\']}』[{\'✅ 可交\' if st == \'ready\' else \'⏳\'}]")\n                lines.append(f"    {sqd[\'desc\']}")\n                # v124.2 复合目标逐行显示（s18 kill+find 两行都展示）\n                for _t in _WC._obj_text_lines(shell, obj, st):\n                    lines.append(f"    {_t}")\n                if st == "ready":\n                    lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n                continue\n            # v124 use 型（使用指定物品达成）——同 find 处理\n            if obj.get("use"):\n                lines.append(f"{i:>2}. 『{sqd[\'name\']}』[{\'✅ 可交\' if st == \'ready\' else \'⏳\'}]")\n                lines.append(f"    {sqd[\'desc\']}")\n                for _t in _WC._obj_text_lines(shell, obj, st):\n                    lines.append(f"    {_t}")\n                if st == "ready":\n                    lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n                continue\n            mark = "✅ 可交" if st == "ready" else "⏳"\n            lines.append(f"{i:>2}. 『{sqd[\'name\']}』[{mark}]")\n            lines.append(f"    {sqd[\'desc\']}")\n            if st == "ready":\n                lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd[\'giver\'])}")\n        # v127.7 翻页提示补全：上一页/下一页 + 总页数（此前只有下一页）\n        if pages > 1:\n            _nav = []\n            if page > 1:\n                _nav.append(f"『任务 {page-1}』上一页")\n            if page < pages:\n                _nav.append(f"『任务 {page+1}』下一页")\n            lines.append(f"💡 {\' | \'.join(_nav)}(共 {pages} 页)")\n        shell._record_list_state(qq_id, "任务", page, pages)\n    else:\n        lines.append("")\n        lines.append("【支线】暂无——找镇上的 NPC 聊聊可能有意外收获")\n    # 每日\n    # v116 §3.4：daily 含 _completed/_repeat 元数据（active 任务清空后仍在）——\n    # 只剩元数据 = 今日全部完成，按"已完成"分支展示；_completed 超额时给出计数。\n    # v127.7：玩家从未领取（daily 为空）→ 提示『每日』领取，不再误报"已完成"。\n    daily = quests.get("daily", {})\n    active_keys = [k for k in daily if k not in _DAILY_META_KEYS]\n    if active_keys:\n        lines.append("")\n        lines.append(T.static("daily.section"))\n        _daily_n = 0  # v116 每日任务序号（仅计实际任务，跨元数据）\n        for dkey, dq in daily.items():\n            if dkey in _DAILY_META_KEYS:  # 跨天/计数元数据，跳过\n                continue\n            _daily_n += 1\n            # v125.1 P2：序号用 _daily_n（仅计实际任务）——原用 enumerate 的 i 会把\n            # _date/_completed/_repeat 元数据占位算进去（面板显示 4./5.，『放弃』按 1..N 对不上）\n            need = _svc("daily_need")(dq)\n            # v127.7 排版：每日任务名单独一行，描述缩进下一行\n            if need is None:\n                # v125.1 P2：无达标数定义时只显示实际进度，不再兜底假 99\n                lines.append(T.text("daily.item", n=_daily_n, name=dq["name"]))\n                lines.append(T.text("daily.item_plain", desc=dq["desc"],\n                                    prog=dq.get("progress", 0)))\n            else:\n                lines.append(T.text("daily.item", n=_daily_n, name=dq["name"]))\n                lines.append(T.text("daily.item_progress", desc=dq["desc"],\n                                    prog=dq.get("progress", 0), need=need))\n    else:\n        lines.append("")\n        if not daily:\n            # v127.7 修复：从未领取（新号/跨天清空）→ 引导领取，不显示"已完成"\n            lines.append(T.static("daily.never"))\n        else:\n            _done = int(daily.get("_completed", 0) or 0)\n            if _done >= _svc("DAILY_LIMIT"):\n                lines.append(T.text("daily.done_full", done=_done, limit=_svc("DAILY_LIMIT")))\n            else:\n                lines.append(T.text("daily.done_part", done=_done))\n    # v101.30d #O1：师门考验追踪——对话树进行中时面板显示（playtest 小红：考验无面板条目）\n    _MASTER_IDS = ("npc_herb_master", "npc_mine_master", "npc_fish_master", "npc_cook_master",\n                   "npc_alchemy_master", "npc_craft_master", "npc_enhance_master", "npc_rune_master")\n    ts = db.get_talk_state(group_id, qq_id)\n    if ts and ts.get("npc") in _MASTER_IDS:\n        _tnpc = NPCS.get(ts["npc"]) or {}\n        lines.append("")\n        lines.append("【师门考验】")\n        lines.append(f"  ⏳ 正在接受【{_tnpc.get(\'name\', \'导师\')}】的拜师考验，回复『继续』接着进行")\n    lines.append("")\n    # v127.1 每面板只抽 1 条随机提示（v123e 放弃/接取引导并入随机池）\n    lines.append(shell._tip("quest"))\n    return lines\n',
    'content/economy_cmds.py::shop': '    @declared("shop")\n    @require_player()\n\n    async def shop(self, event: AstrMessageEvent):\n        group_id, qq_id = self._uid(event)\n        player = self._player(group_id, qq_id)\n        if self._is_redname(qq_id):\n            yield event.plain_result("☠️ 你是红名！商店老板把你轰了出来……（等红名消退再来）")\n            return\n        cur = player["cur_map"]\n        cur_map = _cspace.MAP_BY_ID.get(cur, {})\n        if not self._at_shop(player, group_id, qq_id):\n            hint = self._facility_hint(player, "shop")\n            yield event.plain_result(\n                f"这里没有商店！到有商店的地方（如 {hint}）再输入『商店』吧～" if hint else "这里没有商店！去城镇里找找商铺吧～"\n            )\n            return\n        area_id = cur_map.get("area", cur)\n        is_smith = self._is_smith_shop(player)\n        # v130.7 意见#23：sa_kind 提到函数级（铁匠分支原不计算该变量；坐骑块/武器块共用）\n        sa_kind = self._sa_shop_kind(player)\n        subarea = self._cur_subarea(player)\n        shop_title = (subarea.get("name") or cur_map.get("name") or cur)\n        lines = []\n        entries = []\n\n        # v101.30d #O41/O34：商店已拥有标注（playtest 5 角色复现重复购买）\n        def _owned(name):\n            n = db.count_item(group_id, qq_id, name)\n            for _d in (player.get("equipment") or {}).values():\n                if _d and _d.get("name") == name:\n                    n += 1\n            # v104 M09 P2 修复：已拥有统计含家中仓库（此前仓库存货不计数，玩家可能重复囤货）\n            try:\n                _hs = json.loads(db.get_event_state(f"home_storage_{group_id}_{qq_id}") or "[]")\n                for _it in _hs:\n                    if (_it.get("data") or {}).get("name") == name:\n                        n += _it.get("count", 1)\n            except (ValueError, TypeError):\n                pass\n            return f"（已拥有 ×{n}）" if n else ""\n\n        if is_smith:\n            # 铁匠类商店：武器 + 锻造材料 + 全套装备 + 图纸（v101.25h 追加子区域军需补给如强化石）\n            sa_id = player.get("cur_subarea") or ""\n            sa_items = _clife.SHOP_SUBAREA_ITEMS.get(sa_id)\n            for iid in sa_items or []:\n                it = _cit.ITEMS[iid]\n                _lim = self._shop_limit_label(sa_id, f"item:{iid}")  # v166 限购标注\n                entries.append((iid, f"{it[\'name\']}{_owned(it[\'name\'])} —— {it[\'price\']} 金币（{it[\'desc\']}）{_lim}"))\n            materials = _clife.SHOP_SMITH_MATERIALS.get(cur) or _clife.SHOP_SMITH_MATERIALS.get(area_id, [])\n            for mid in materials:\n                mt = _cit.MATERIALS[mid]\n                _lim = self._shop_limit_label(sa_id, f"mat:{mid}")  # v166 限购标注\n                entries.append((mid, f"{mt[\'name\']}{_owned(mt[\'name\'])} —— {mt[\'price\']} 金币（锻造材料）{_lim}"))\n            # v94 图纸经济：铁匠铺兜底卖图纸（随机一张，价格 = 图纸价×3 = (lv×3+20)×3）\n            bp_price = int((max(1, player["level"]) * _clife.ECON_CONFIG["bp_price_per_lv"]\n                            + _clife.ECON_CONFIG["bp_price_base"]) * _clife.ECON_CONFIG["bp_smith_mult"])\n            entries.append(("bp:rand", f"📜 神秘锻造图纸（随机一张）—— {bp_price} 金币"))\n            equip_items = self._shop_equip_roster(player, _clife.SHOP_EQUIP.get(cur) or _clife.SHOP_EQUIP.get(area_id, []))\n            for rid in equip_items:\n                r = _cit.EQUIP_ROSTER[rid]\n                q = _b143.QUALITY[r["quality"]]\n                _lim = self._shop_limit_label(sa_id, f"equip:{rid}")  # v166 限购标注\n                entries.append((f"e:{rid}", f"{q[\'color\']}{r[\'name\']}{_owned(r[\'name\'])}（{_b143.EQUIP_SLOTS[r[\'slot\']]}）Lv.{r[\'lv\']}{\' · \' + self._req_label(r) if self._req_label(r) else \'\'} —— {self._shop_equip_price(r[\'slot\'], r[\'lv\'], r[\'quality\'], r.get(\'weapon_type\'), rid)} 金币{_lim}"))\n            weapons = _clife.SHOP_WEAPONS.get(cur) or _clife.SHOP_WEAPONS.get(area_id, [])\n            for wname, wtype, wlv, wq in weapons:\n                q = _b143.QUALITY[wq]\n                _ids = _cit.EQUIP_ROSTER_BY_NAME.get(wname, [])\n                _r = _cit.EQUIP_ROSTER.get(_ids[0], {}) if _ids else {}\n                # v104 M09 P2 修复：非名册武器需求按 random_req 确定性推导标注（与 _buy_weapon 生成同源）\n                if not _r:\n                    _r = {"req": C.random_req("weapon", wlv, wtype)}\n                _lim = self._shop_limit_label(sa_id, f"weapon:{wname}")  # v166 限购标注\n                entries.append((f"w:{wname}", f"{q[\'color\']}{wname}{_owned(wname)}（{C.display(\'weapon_types\', wtype)}）Lv.{wlv}{\' · \' + self._req_label(_r) if self._req_label(_r) else \'\'} —— {self._shop_equip_price(\'weapon\', wlv, wq, wtype)} 金币{_lim}"))\n            # v135 铁匠铺货架（全服共享，NPC 作品）：2 武器 + 1 防具 + 1 饰品，每日 0 点换货 + 6h 补货\n            town_lv = _ss.town_level(cur)\n            smith_items = _ss.get_smith_stock(cur, town_lv)\n            _npc = _ss.SMITH_NPC_NAMES.get(cur, "铁匠")\n            for _sit in smith_items:\n                _rid = _sit["rid"]\n                _r = _cit.EQUIP_ROSTER[_rid]\n                _q = _b143.QUALITY[_r["quality"]]\n                _sl = _r["slot"]\n                _slot_cn = _b143.EQUIP_SLOTS[_sl] if _sl in _b143.EQUIP_SLOTS else (C.display(\'weapon_types\', _r.get(\'weapon_type\')) or _sl)\n                _n = f"{_r[\'name\']}（{_npc}的作品）"\n                _price = int(_ss.smith_stock_price(_rid, _sit["price_mult"]))\n                entries.append((f"s:{_rid}", f"{_q[\'color\']}{_n}{_owned(_r[\'name\'])}（{_slot_cn}）Lv.{_r[\'lv\']}{\' · \' + self._req_label(_r) if self._req_label(_r) else \'\'} ×{_sit[\'qty\']} —— {_price} 金币"))\n        else:\n            # 普通商店：消耗品 + 武器（v101.28g：只挂子区域配货，无城镇级兜底）\n            sa_kind = self._sa_shop_kind(player)\n            sa_id = player.get("cur_subarea") or ""\n            sa_items = _clife.SHOP_SUBAREA_ITEMS.get(sa_id)\n            shop_items = sa_items if sa_items is not None else []\n            trader = self._wild_trader_here(player, group_id, qq_id)\n            if not shop_items and trader:\n                shop_items = _clife.SHOP_WILD_TRADE  # v95.4：野外行商货物\n                tname = _cquest.WILD_NPCS.get(trader, {}).get("name", "行商")\n                shop_title = f"🧭 {tname}的货摊"  # #151：标题跟随实际在场的交易 NPC\n            # 意见#130（2026-09-03 白云白云狸雾理云/鱼神）：铁港码头栈桥(harbor_docks_1)挂着\n            # 行商(NPC 夜钓翁·老竿 map=harbor_docks 整图 roam)，本子区域没有商店也没有货摊，\n            # 却在『地图』里被 _wild_trader_here 判定为可交易 → 显示错配的「行商货摊」。\n            # 修复：交易放行条件收紧为「当前子区域是无 shop 的野外落点 OR 在场限时 NPC 事件已触发」\n            # （限时事件 = 探索偶遇后 set_timed 的 wild:{nid}，见 roll_wild_encounter；\n            #  _wild_trader_here 原本只按 NPC 静态 map 判定，夜钓翁 map=harbor_docks 全图放行）。\n            _here_trader_ok = False\n            if trader:\n                _tr_npc = _wild.ALL_WILD.get(trader, {})\n                _tr_roam = _tr_npc.get("roam")\n                _tr_timed = bool(C.get_timed(group_id, qq_id, f"wild:{trader}"))\n                # 无 roam 的 NPC 若 map 命中当前整图但未偶遇（无线时事件）→ 不在场，不显示行商\n                _here_trader_ok = bool(_tr_timed) if not _tr_roam else True\n            if not shop_items and _here_trader_ok:\n                shop_items = _clife.SHOP_WILD_TRADE  # v95.4：野外行商货物\n                tname = _cquest.WILD_NPCS.get(trader, {}).get("name", "行商")\n                shop_title = f"🧭 {tname}的货摊"  # #151：标题跟随实际在场的交易 NPC\n            for iid in shop_items:\n                it = _cit.ITEMS[iid]\n                _lim = self._shop_limit_label(sa_id, f"item:{iid}")  # v166 限购标注\n                entries.append((iid, f"{it[\'name\']}{_owned(it[\'name\'])} —— {it[\'price\']} 金币（{it[\'desc\']}）{_lim}"))\n            # 武器：铁匠/锻造类 + 普通商店（集市/商行/码头）可卖；草药铺/酒馆不卖\n            if sa_kind in ("smith", "general"):\n                weapons = _clife.SHOP_WEAPONS.get(cur) or _clife.SHOP_WEAPONS.get(area_id, [])\n                for wname, wtype, wlv, wq in weapons:\n                    q = _b143.QUALITY[wq]\n                    _ids = _cit.EQUIP_ROSTER_BY_NAME.get(wname, [])\n                    _r = _cit.EQUIP_ROSTER.get(_ids[0], {}) if _ids else {}\n                    # v104 M09 P2 修复：非名册武器需求按 random_req 确定性推导标注（与 _buy_weapon 生成同源）\n                    if not _r:\n                        _r = {"req": C.random_req("weapon", wlv, wtype)}\n                    _lim = self._shop_limit_label(sa_id, f"weapon:{wname}")  # v166 限购标注\n                    entries.append((f"w:{wname}", f"{q[\'color\']}{wname}{_owned(wname)}（{C.display(\'weapon_types\', wtype)}）Lv.{wlv}{\' · \' + self._req_label(_r) if self._req_label(_r) else \'\'} —— {self._shop_equip_price(\'weapon\', wlv, wq, wtype)} 金币{_lim}"))\n        # v104 修 M17-P2：橡木镇（新手村）商店面板列出可购坐骑（price>0 的老马/小毛驴），并入序号购买\n        # v130.7 意见#23：坐骑只挂 smith/general 贸易场所（草药铺 herb/酒馆 tavern 不再隔空卖坐骑，口径同武器块）\n        if area_id == "oak" and cur == _ccore.START_MAP and sa_kind in ("smith", "general"):\n            _mount_owned = set((player.get("mounts") or {}).get("owned") or [])\n            for mdef in _clife.MOUNT_POOL:\n                if (mdef.get("price") or 0) > 0:\n                    _mo = "（已拥有）" if mdef["key"] in _mount_owned else ""\n                    entries.append((f"mount:{mdef[\'key\']}",\n                                    f"{mdef[\'icon\']}{mdef[\'name\']}{_mo}（坐骑 Lv.{mdef[\'lv\']} 商店直购）—— {mdef[\'price\']} 金币"))\n        # v104 M09 P2 修复：世界事件商店折扣期面板标注（effects 数据驱动：shop_discount，0.8 = 8 折）\n        cur_evt = db.get_world_event()\n        _discount_tip = ""\n        if cur_evt:\n            _evt_def = next((e for e in _b143.WORLD_EVENT_POOL if e["type"] == cur_evt["etype"]), None)\n            _sd = (_evt_def.get("effects") or {}).get("shop_discount") if _evt_def else None\n            if _sd:\n                _discount_tip = f"（{_evt_def[\'name\']} {int(round(_sd * 10))} 折！）"\n        raw = self._strip_cmd(event, "商店")\n        page = self._parse_page(raw)\n        page_items, pages, page = self._page_items(entries, page, per_page=5)\n        lines = [f"🏪 【{shop_title} 商店】{_discount_tip}（第 {page}/{pages} 页 · 共 {len(entries)} 件）", "━━━━━━━━━━━━"]\n        for i, (key, row) in enumerate(page_items, (page - 1) * 5 + 1):\n            lines.append(f"{i:>2}. {row}")\n        if is_smith:\n            # v135 铁匠铺货架提示（不占序号，显示在商品列表后）\n            lines.append("💡 全服共享货架，售罄等补货；每日 0 点换新")\n        lines.append("")\n        self._record_list_state(qq_id, "商店", page, pages)\n        lines.append(f"💰 你的金币：{player[\'gold\']}")\n        lines.append(self._tip("shop"))\n        yield event.plain_result("\\n".join(lines))\n',
    'content/economy_cmds.py::buy': '    @declared("buy")\n    @require_player()\n\n    async def buy(self, event: AstrMessageEvent):\n        group_id, qq_id = self._uid(event)\n        item_name = self._strip_cmd(event, "购买")\n        player = self._player(group_id, qq_id)\n        _ec = _clife.ECON_CONFIG\n        if self._is_redname(qq_id):\n            yield event.plain_result("☠️ 你是红名！商店老板不敢卖你东西……（等红名消退再来）")\n            return\n        cur = player["cur_map"]\n        cur_map = _cspace.MAP_BY_ID.get(cur, {})\n        if not self._at_shop(player, group_id, qq_id):\n            hint = self._facility_hint(player, "shop")\n            yield event.plain_result(\n                f"这里没有商店！到有商店的地方（如 {hint}）再输入『商店』吧～" if hint else "这里没有商店！去城镇里找找商铺吧～"\n            )\n            return\n        area_id = cur_map.get("area", cur)\n        is_smith = self._is_smith_shop(player)\n        sa_kind = self._sa_shop_kind(player)\n        sa_id = player.get("cur_subarea") or ""\n        sa_items = _clife.SHOP_SUBAREA_ITEMS.get(sa_id)\n        # v101.28g：子区域独立配货（无城镇级兜底）；smith 分支无配货则空\n        if sa_items is not None:\n            shop_items = sa_items\n        else:\n            shop_items = []\n        if not shop_items and not is_smith and self._wild_trader_here(player, group_id, qq_id):\n            # 意见#130 同源修复（与 shop 面板一致）：未偶遇的静态野外行商不隔空放行——夜钓翁\n            # map=harbor_docks 但没探索偶遇时，玩家在码头任何子区域都会被判定可买它的货\n            _trader = self._wild_trader_here(player, group_id, qq_id)\n            _tr_npc = _wild.ALL_WILD.get(_trader, {}) if _trader else {}\n            _tr_timed = bool(C.get_timed(group_id, qq_id, f"wild:{_trader}")) if _trader else False\n            if _trader and (_tr_npc.get("roam") or _tr_timed):\n                shop_items = _clife.SHOP_WILD_TRADE  # v95.4：野外行商货物\n        materials = (_clife.SHOP_SMITH_MATERIALS.get(cur) or _clife.SHOP_SMITH_MATERIALS.get(area_id, [])) if is_smith else []\n        item_name = item_name.strip()\n        # F2-2：『购买 』空参静默买第一件（空串是任意名称的子串恒 True，report_18 P1-1）\n        #   ——显式格式提示（与『加点 』空参提示风格一致），不执行购买\n        if not item_name:\n            yield event.plain_result(\n                "格式：购买 <商品名/序号> [数量]，如『购买 治疗药水(小) 5』；『商店』查看商品列表～"\n            )\n            return\n# v95.25 #127 + 玩家意见#2（zerc）：支持『购买 <名称/序号> <数量>』（空格）与\n        #   『购买 <名称>*<数量>』（星号）两种批量格式（如『购买 治疗药水(中) 6』、『购买 治疗药水*10』、『购买 1*5』）；\n        #   数量校验显式报错：0/负/非数字/超 buy_qty_max 不再静默钳制（此前 0/负被钳成 1、超限被钳到上限，\n        #   用户感知为"买少了/买错了"；isdigit 误吞 ²/³ 等上标会在 int() 抛 ValueError，一并改为 isdecimal 加固）\n        qty = 1\n        _qty_raw = None\n        # 尾部数量 token 判定：十进制数字或带负号的数字（负号/0 走下方 qty<1 显式报错，\n        # 而不是被当成商品名的一部分去搜索——「商店里没有『治疗药水 -3』」不友好）\n        def _is_qty_token(tok: str) -> bool:\n            return tok.isdecimal() or (tok.startswith("-") and len(tok) > 1 and tok[1:].isdecimal())\n\n        _parts = item_name.split()\n        if len(_parts) >= 2 and _is_qty_token(_parts[-1]):\n            _qty_raw = _parts[-1]\n            item_name = " ".join(_parts[:-1])\n        elif "*" in item_name:\n            _head, _, _tail = item_name.rpartition("*")\n            _tail = _tail.strip()\n            if _is_qty_token(_tail):\n                _qty_raw = _tail\n                item_name = _head.strip()\n            else:\n                yield event.plain_result(\n                    "数量格式不对！例：『购买 治疗药水*5』或『购买 治疗药水 5』；『商店』查看商品列表～"\n                )\n                return\n        if _qty_raw is not None:\n            try:\n                qty = int(_qty_raw)\n            except ValueError:\n                yield event.plain_result("数量不合法！请输入正整数，如『购买 治疗药水 5』～")\n                return\n            if qty < 1:\n                yield event.plain_result("数量至少 1 个！大批量购买用『购买 <商品> 数量』或『购买 <商品>*数量』～")\n                return\n            if qty > _ec["buy_qty_max"]:\n                yield event.plain_result(f"单次最多购买 {_ec[\'buy_qty_max\']} 个！需要更多请分批购买～")\n                return\n        # 星号/数量剥离后无商品名（如『购买 *5』）→ 显式格式提示，防空名称静默买第一件（F2-2 同款兜底）\n        if not item_name:\n            yield event.plain_result(\n                "格式：购买 <商品名/序号> [数量]，如『购买 治疗药水(小) 5』；『商店』查看商品列表～"\n            )\n            return\n        # 全角括号容错：『购买 治疗药水（中）』→ 半角『治疗药水(中)』\n        item_name = item_name.replace("（", "(").replace("）", ")")\n        # 世界事件商店折扣（effects 数据驱动：shop_discount，0.8 = 8 折）\n        discount = 1.0\n        _evt_tip = ""\n        cur_evt = db.get_world_event()\n        if cur_evt:\n            _evt_def = next((e for e in _b143.WORLD_EVENT_POOL if e["type"] == cur_evt["etype"]), None)\n            _sd = (_evt_def.get("effects") or {}).get("shop_discount") if _evt_def else None\n            if _sd:\n                discount = float(_sd)\n                _evt_tip = f"（{_evt_def[\'name\']} {int(round(_sd * 10))} 折！）"\n        weapons = _clife.SHOP_WEAPONS.get(cur) or _clife.SHOP_WEAPONS.get(area_id, [])\n        # v101.25h：武器/名册装备只在 smith/general 卖（草药铺/酒馆不卖）\n        # v101.28o：is_smith 也放行——craft+alchemy 双职能店（如晨曦药剂坊 dawn_city_5）\n        #   面板 is_smith 分支会列出武器，购买侧若按 herb 过滤则"看得到买不到"（#445）\n        can_sell_weapons = is_smith or sa_kind in ("smith", "general")\n        if not can_sell_weapons:\n            weapons = []\n        equip_items = self._shop_equip_roster(player, _clife.SHOP_EQUIP.get(cur) or _clife.SHOP_EQUIP.get(area_id, []))\n        # v104 M09 P1 修复：装备只在 is_smith（铁匠类）面板列出——general 商店序号列表与面板严格同源\n        #   （此前 general 序号含 e: 名册装备，『购买 4』实测买到面板未显示的翡翠皮甲）\n        if not is_smith:\n            equip_items = []\n        # v135 铁匠铺货架（全服共享）：town_lv 供序号/名称购买共用（面板第 6 块同源）\n        smith_items = _ss.get_smith_stock(cur, _ss.town_level(cur)) if is_smith else []\n        # 序号购买：『购买 3』→ 与商店列表一致的第 3 件商品（顺序：材料→装备→武器，与 shop 面板一致）\n        if item_name.isdigit():\n            entries = list(shop_items) + [f"m:{m}" for m in materials] + (["bp:rand"] if is_smith else []) + [f"e:{rid}" for rid in equip_items] + [f"w:{w[0]}" for w in weapons]\n            # v135 铁匠铺货架（全服共享）：序号与商店面板第 6 块同源（材料→装备→武器→货架→坐骑）\n            if is_smith:\n                entries += [f"s:{sit[\'rid\']}" for sit in smith_items]\n            # v104 修 M17-P2：橡木镇序号购买含坐骑（与商店面板顺序一致，追加在末尾）\n            # v130.7 意见#23：序号购买与面板同口径（草药铺/酒馆序号不挂坐骑）\n            if area_id == "oak" and cur == _ccore.START_MAP and sa_kind in ("smith", "general"):\n                entries += [f"mount:{m[\'key\']}" for m in _clife.MOUNT_POOL if (m.get("price") or 0) > 0]\n            idx = int(item_name)\n            if idx < 1 or idx > len(entries):\n                yield event.plain_result(f"没有第 {idx} 号商品！『商店』查看商品列表。")\n                return\n            key = entries[idx - 1]\n            # ============ v181.P4-3：序号购买 key 分派（bp/m/w/mount/e/s/消耗品）业务下沉 services.shop ============\n            _buy_res, _buy_msg = _shop_svc.buy_index_dispatch(\n                key, group_id, qq_id, player, qty, discount,\n                shop_items=shop_items, materials=materials, weapons=weapons,\n                equip_items=equip_items, smith_items=smith_items,\n                sa_id=sa_id, area_id=area_id, cur=cur, is_smith=is_smith,\n                evt_tip=_evt_tip,\n                limit_guard=self._shop_limit_buy_guard,\n                at_shop=self._at_shop,\n                smith_stock=_ss, buy_weapon=self._buy_weapon,\n            )\n            if _buy_msg is not None:\n                yield event.plain_result(_buy_msg)\n                return\n            # （分派完成：msg None = 命中并完成成交分支——序号 key 分派穷尽终结，\n            #   所有 key 都落 bp:/m:/w:/mount:/e:/s:/消耗品 之一，原实现各分支均 return）\n            return\n        # 找铁匠铺随机图纸（按名称）：『购买 神秘锻造图纸』→ bp:rand（序号分支 v94 已支持，名称分支补上）\n        if is_smith and item_name in ("神秘锻造图纸", "锻造图纸", "图纸", "神秘图纸"):\n            bp_price = int((max(1, player["level"]) * _ec["bp_price_per_lv"]\n                            + _ec["bp_price_base"]) * _ec["bp_smith_mult"] * discount)\n            # v105 M09 P3-9：图纸单件商品\n            if qty > 1:\n                yield event.plain_result("神秘锻造图纸只能买 1 张！想再买一张就再输一次～")\n                return\n            if player["gold"] < bp_price:\n                yield event.plain_result(f"金币不足！需要 {bp_price} 金币。")\n                return\n            db.update_player(group_id, qq_id, gold=player["gold"] - bp_price)\n            bp = C.roll_blueprint(max(1, player["level"]))\n            import uuid\n            db.add_item(group_id, qq_id, f"eq_{uuid.uuid4().hex[:8]}", bp)\n            tip = _evt_tip\n            yield event.plain_result(f"✅ 你买到一张【{bp[\'name\']}】！{tip}")\n            return\n        # 找补给品（按名称）\n        for iid in shop_items:\n            it = _cit.ITEMS[iid]\n            if item_name in it["name"] or (item_name and item_name in it["name"].replace("(", "").replace(")", "")):\n                price = int(it["price"] * discount)\n                total = price * qty\n                if player["gold"] < total:\n                    yield event.plain_result(f"金币不足！需要 {total} 金币。")\n                    return\n                # v166 商店限购：消耗品（店内共享库存+每日个人限购）\n                _l_ok, _l_msg = self._shop_limit_buy_guard(group_id, qq_id, sa_id, f"item:{iid}", qty)\n                if not _l_ok:\n                    yield event.plain_result(_l_msg)\n                    return\n                db.update_player(group_id, qq_id, gold=player["gold"] - total)\n                # v21 防刷钱：消耗品卖出价 = 实际支付价（商队 8 折时不能原价卖出套利）\n                # v104 修 M09-P0：全量拷贝 ITEMS 定义字段（hot/hot_turns/hot_mana/food_effect/effect），\n                #   否则 9 种店售食物丢 hot 字段 → infer_template 判为药水，战斗内持续恢复失效\n                db.add_item(group_id, qq_id, iid, {**it, "type": "消耗品", "stackable": True, "price": price}, count=qty)\n                tip = _evt_tip\n                qty_str = f" ×{qty}"  # #254: 单件购买也回显数量（此前 qty=1 无回显）\n                yield event.plain_result(f"✅ 你购买了【{it[\'name\']}】{qty_str}！{tip}")\n                return\n        # 找材料（按名称）\n        for mid in materials:\n            mt = _cit.MATERIALS[mid]\n            if item_name in mt["name"]:\n                price = int(mt["price"] * discount)\n                total = price * qty\n                if player["gold"] < total:\n                    yield event.plain_result(f"金币不足！需要 {total} 金币。")\n                    return\n                # v166 商店限购：材料（店内共享库存+每日个人限购）\n                _l_ok, _l_msg = self._shop_limit_buy_guard(group_id, qq_id, sa_id, f"mat:{mid}", qty)\n                if not _l_ok:\n                    yield event.plain_result(_l_msg)\n                    return\n                db.update_player(group_id, qq_id, gold=player["gold"] - total)\n                # v104 修 M09-P3：材料购买全量拷贝定义字段（补 quality 等），不再丢字段\n                db.add_item(group_id, qq_id, mid, {**mt, "type": "材料", "stackable": True, "price": price}, count=qty)\n                tip = _evt_tip\n                qty_str = f" ×{qty}"  # #254: 单件购买也回显数量（此前 qty=1 无回显）\n                yield event.plain_result(f"✅ 你购买了【{mt[\'name\']}】{qty_str}！{tip}")\n                return\n        # 找武器（按名称）\n        for wname, wtype, wlv, wq in weapons:\n            if item_name in wname:\n                # v95.34：价格与显示/序号购买同源（v101.25e _shop_equip_price），修 #414 名称购买走旧公式低价漏洞\n                price = int(self._shop_equip_price("weapon", wlv, wq, wtype) * discount)\n                # v105 M09 P3-9：武器单件商品（此前『购买 铁剑 3』静默只买 1 把）\n                if qty > 1:\n                    yield event.plain_result(f"『{wname}』是武器，只能单件购买！需要几把就再买几次～")\n                    return\n                if player["gold"] < price:\n                    yield event.plain_result(f"金币不足！需要 {price} 金币。")\n                    return\n                # v166 商店限购：商店武器（店内共享库存+每日个人限购）\n                _l_ok, _l_msg = self._shop_limit_buy_guard(group_id, qq_id, sa_id, f"weapon:{wname}", 1)\n                if not _l_ok:\n                    yield event.plain_result(_l_msg)\n                    return\n                # 阶段八：武器不锁职业（20 章），名册名走名册精确生成\n                db.update_player(group_id, qq_id, gold=player["gold"] - price)\n                equip_item = self._buy_weapon(wname, wtype, wlv, wq)\n                # v21 防刷钱：商店装备卖出价 = 买入价一半\n                equip_item["price"] = int(price * _ec["equip_resale_rate"])\n                import uuid\n                db.add_item(group_id, qq_id, f"eq_{uuid.uuid4().hex[:8]}", equip_item)\n                yield event.plain_result(f"✅ 你购买了【{wname}】！放到背包了，输入『装备 {wname}』使用。")\n                return\n        # 找装备（按名称）\n        for rid in equip_items:\n            r = _cit.EQUIP_ROSTER[rid]\n            if item_name in r["name"]:\n                # v95.34：价格与显示/序号购买同源（v101.25e _shop_equip_price），修 #414 名称购买走旧公式低价漏洞\n                price = int(self._shop_equip_price(r["slot"], r["lv"], r["quality"], r.get("weapon_type"), rid) * discount)\n                # v105 M09 P3-9：装备单件商品（数量参数不适用）\n                if qty > 1:\n                    yield event.plain_result(f"『{r[\'name\']}』是装备，只能单件购买！需要几件就再买几次～")\n                    return\n                if player["gold"] < price:\n                    yield event.plain_result(f"金币不足！需要 {price} 金币。")\n                    return\n                # v166 商店限购：名册装备（店内共享库存+每日个人限购）\n                _l_ok, _l_msg = self._shop_limit_buy_guard(group_id, qq_id, sa_id, f"equip:{rid}", 1)\n                if not _l_ok:\n                    yield event.plain_result(_l_msg)\n                    return\n                db.update_player(group_id, qq_id, gold=player["gold"] - price)\n                equip_item = C.generate_roster_equip(rid)\n                equip_item["price"] = int(price * _ec["equip_resale_rate"])\n                import uuid\n                db.add_item(group_id, qq_id, f"eq_{uuid.uuid4().hex[:8]}", equip_item)\n                yield event.plain_result(f"✅ 你购买了【{r[\'name\']}】！放到背包了，输入『装备 {r[\'name\']}』使用。")\n                return\n        # v135 铁匠铺货架（全服共享）按名称购买（NPC 作品，如『购买 汉斯的精铁长剑』）\n        # 前置判定：带「作品」字样或命中本城铁匠名 → 只查货架（防误吞普通装备名）\n        if is_smith:\n            _npc = _ss.SMITH_NPC_NAMES.get(cur, "铁匠")\n            _want_stock = ("作品" in item_name) or (_npc in item_name)\n            for _sit in smith_items:\n                _r = _cit.EQUIP_ROSTER[_sit["rid"]]\n                if _want_stock and (item_name in _r["name"] or _r["name"] in item_name):\n                    ok, item_data, price = _ss.buy_stock_item(cur, _ss.town_level(cur), _sit["rid"])\n                    if not ok:\n                        yield event.plain_result("😢 这件作品已被别的冒险者买走了，售罄等补货吧～")\n                        return\n                    if qty > 1:\n                        yield event.plain_result("铁匠的作品是孤品，只能单件购买！")\n                        return\n                    if player["gold"] < price:\n                        yield event.plain_result(f"金币不足！需要 {price} 金币。")\n                        return\n                    db.update_player(group_id, qq_id, gold=player["gold"] - price)\n                    item_data["price"] = int(price * _ec["equip_resale_rate"])\n                    import uuid\n                    db.add_item(group_id, qq_id, f"eq_{uuid.uuid4().hex[:8]}", item_data)\n                    yield event.plain_result(f"✅ 你买下了【{item_data[\'name\']}】！铁匠的手艺交到你手里，输入『装备』查看。")\n                    return\n        # v39/v101.15 坐骑：橡木镇马厩购买（老马/小毛驴等 price>0 的坐骑）\n        shop_mounts = [m for m in _clife.MOUNT_POOL if (m.get("price") or 0) > 0]\n        for mdef in shop_mounts:\n            if item_name in mdef["name"] or item_name.strip() == mdef["key"]:\n                # v130.7 意见#23：名称购买同口径（草药铺/酒馆『购买 老马』同样拦截）\n                if area_id != "oak" or cur != _ccore.START_MAP or sa_kind not in ("smith", "general"):\n                    yield event.plain_result(f"橡木镇的商人才能买到{mdef[\'name\']}！去橡木镇『商店』看看～")\n                    return\n                mounts = player.get("mounts") or {}\n                if mdef["key"] in (mounts.get("owned") or []):\n                    yield event.plain_result(f"你已经拥有{mdef[\'name\']}了！")\n                    return\n                # v104 M17 P2-1：名称购买坐骑同样校验骑乘等级（与序号购买同口径）\n                if player["level"] < mdef["lv"]:\n                    yield event.plain_result(f"『{mdef[\'name\']}』需要 Lv.{mdef[\'lv\']} 才能骑乘，你才 Lv.{player[\'level\']}！先升级再来买吧～")\n                    return\n                price = int(mdef["price"] * discount)\n                if player["gold"] < price:\n                    yield event.plain_result(f"金币不足！{mdef[\'name\']}要 {price} 金币。")\n                    return\n                db.update_player(group_id, qq_id, gold=player["gold"] - price)\n                mounts = dict(player.get("mounts") or {})\n                owned = list(mounts.get("owned") or [])\n                owned.append(mdef["key"])\n                mounts["owned"] = owned\n                db.update_player(group_id, qq_id, mounts=mounts)\n                yield event.plain_result(\n                    f"{mdef[\'icon\']} 你买了{mdef[\'name\']}！缰绳交到你手里，它打了个响鼻。\\n"\n                    f"💡 『骑乘 {mdef[\'name\']}』骑上它，『坐骑』查看全部！")\n                return\n        yield event.plain_result(f"商店里没有『{item_name}』！输入『商店』查看商品。")\n',
    'content/talk_actions.py::action_apprentice_check': '@register("apprentice_check")\ndef action_apprentice_check(world, group_id, qq_id, player, npc_id, action):\n    """v81 导师进修：考验判定（检查背包材料）——由 talk_choice 主循环特判迁入注册表。\n\n    条件型动作：判定结果经 world._talk_route / world._talk_tail 通道传出，\n    _apply_talk_action_async 返回路由，talk_choice 主循环只做通用分发：\n      _talk_route = "__end__" → 副业未解锁直接结束对话（#101.29，不再渲染 fail 节点）\n      _talk_route = "fail"    → 材料不足，走选项 fail_next\n      通过（不设 route）     → 成功提示放 _talk_tail，待全部动作行之后追加\n                                （与旧特判 notices.append("✅…") 的输出顺序一致）\n    交互行为（选项显示/失败提示/通过流程）与 v101.23d 前内联特判完全一致。\n    """\n    check = action["apprentice_check"]\n    # #255: 副业未解锁（未拜师）时考验提前拦截——遍历对话树找 unlock_prof 目标副业，\n    # 未解锁则材料也不收，避免玩家交完材料才被拦白跑。\n    # v167：副业数量上限已解除，此拦截只剩"未拜师"一种情况（位满分支已随上限移除）。\n    # #417: 遍历层级 bug——dlg 顶层是 {start, nodes}，必须遍历 nodes 子表\n    prof_target = None\n    dlg = C.get_dialogue(npc_id)\n    for _nid, _node in ((dlg.get("nodes") or {}).items()):\n        if not isinstance(_node, dict):\n            continue  # 对话树部分节点为纯字符串（跳转别名）\n        for _o in (_node.get("options") or []):\n            _ua = (_o.get("action") or {}).get("unlock_prof")\n            if _ua:\n                prof_target = _ua\n                break\n        if prof_target:\n            break\n    _npc = _cq.NPCS.get(npc_id) or _wild.ALL_WILD.get(npc_id) or {}\n    _name = _npc.get("name", npc_id)\n    if prof_target:\n        _okp, _msgp = world._prof_active_check(group_id, qq_id, prof_target)\n        if not _okp:\n            # v101.29：副业未解锁拦截直接结束对话（不再渲染 fail 节点）——旧代码跳\n            # fail_next 会渲染"材料凑不齐"类台词，与"副业未解锁先不收材料"的拦截\n            # 归因矛盾（小红实测梅尔文交付被抓包）。v167 起仅剩未拜师场景，\n            # 提示语已由 _prof_active_check 输出"先去拜师"引导。\n            world._talk_route = "__end__"\n            return [_msgp + "（这次考验先不收材料，先去拜师解锁再来吧）"]\n    have = db.count_item(group_id, qq_id, check.get("item", ""))\n    need = int(check.get("count", 1))\n    if have >= need:\n        world._talk_tail = [f"✅ {_name}满意地点了点头。"]\n        return []\n    world._talk_route = "fail"\n    return [f"{_name}摇头：还差 {need - have} 份{check.get(\'item\', \'材料\')}，备齐了再来。"]\n',
    'content/item_templates.py::tpl_teleport_portal': '@register("teleport_portal")\ndef tpl_teleport_portal(ctx):\n    """传送卷轴（v104 P2(M22)：与回城卷轴区分）——方碑锚定传送：\n    传送到玩家最后激活的方碑所在城镇广场（复用方碑激活表 db.get_portals，\n    落点 subareas[0] 对齐"城内直达走广场"约定，同方碑传送/战败回城）。\n    回城卷轴=回最近城镇保命；传送卷轴=回已激活的方碑锚点（定点）。\n    说明：菜单式选城需命令层把『使用 卷轴 <目标>』参数透传给模板\n    （economy.py cmd_use 不传参，超本文件修改范围），故取最后激活锚点。"""\n    if ctx.battle:\n        return ItemResult(text="战斗中无法使用传送卷轴！先解决眼前的敌人吧～", consume=False)\n    db = ctx._db()\n    cur = ctx._focus.get("cur_map", "")\n    portals = [m for m in (db.get_portals(ctx.qq_id) or []) if _cs.MAP_BY_ID.get(m)]\n    if not portals:\n        return ItemResult(\n            text="🌀 传送卷轴泛起微光又暗淡下去——还没有可用的方碑锚点！\\n"\n                 + _rand_tip("portal"),\n            consume=False)\n    dest = portals[-1]  # 最后激活的方碑（add_portal 追加序）\n    if dest == cur:\n        return ItemResult(\n            text="你已经在这座方碑所在的城镇了！(传送卷轴没有消耗)",\n            consume=False)\n    tgt = _cs.MAP_BY_ID[dest]\n    sas = tgt.get("subareas") or []\n    first_sa = sas[0] if sas else None\n    db.update_player(ctx.group_id, ctx.qq_id,\n                     cur_map=dest, cur_subarea=first_sa["id"] if first_sa else "")\n    db.add_visited(ctx.group_id, ctx.qq_id, dest)\n    db.clear_talk_state(ctx.group_id, ctx.qq_id)  # v95 #142：传送落地清对话，防"还在交谈中"残留\n    ctx.hook("remove_item")\n    p = _cs.PORTALS.get(dest, {})\n    pname = p.get("name", "方碑") if p else "方碑"\n    picon = p.get("icon", "🌌") if p else "🌌"\n    anchors = "、".join(_cs.MAP_BY_ID[m].get("name", m) for m in portals)\n    return ItemResult(text=(\n        f"🌀 传送卷轴展开，星辉流转——你抵达了【{tgt.get(\'name\', \'城镇\')}】({picon}{pname})！\\n"\n        f"📍 当前方碑锚点：{anchors}\\n"\n        + _rand_tip("portal")))\n',
    'content/combat_cmds.py::roll_wild_encounter': 'def roll_wild_encounter(*args, **kwargs):\n    """真源 `..wild.roll_wild_encounter`（+ 聚合层覆写面，见 `_overlay`）。"""\n    return _overlay("roll_wild_encounter", _pkg_roll_wild_encounter)(*args, **kwargs)\n',
}

_PIN = {
    'phase': 'landed',
    'frozen': {
        'content/cmds_base_rules.py::wild_trader_here': 'cf749f93dba39692b80e519c207e424c855e72a6fd7ac3a4bdbd375d1b293f65',
        'content/instance_cmds.py::_stage_npcs': '9fb5d4685298dc82b8c314ade09dda2e3ebc0bd43019f0bc3dde2ff0255451ef',
        'content/shop.py::apprentice_protect_mats': '09bedd406ae58502c0d8d10bbfbe9ff54a93ccb9d5356ef5d1b42b54f9703370',
        'content/cmds_world.py::quest_view': 'bcccf11297a8ae87c51fbb8d14c851c833510ecf30a0888d95a23faf208e1d21',
        'content/economy_cmds.py::shop': 'c381329ddf1bd4b1865194b0f7a4dd37b8fa7e28db24d407fc96a6a992ba8638',
        'content/economy_cmds.py::buy': '76e2b9307e4579d659485c66837430a817b2af8280c2580a4f0a4f3cc6581690',
        'content/talk_actions.py::action_apprentice_check': '3079da595d629cb8a83530cbfdaf221a85ee971804ae29895c47577748585edc',
        'content/item_templates.py::tpl_teleport_portal': 'f833ca2a3eebd4c0fb13e365a049d0b3f484e906bb80f63c4481e15201cc2bd2',
        'content/combat_cmds.py::roll_wild_encounter': '2c66022b9137474a748b8bfb1135c88e09e7fa6cbcab9214016e95ae786709a1',
    },
    'live': {
        'content/cmds_base_rules.py::wild_trader_here': '1c9ebab2da508b821c09e81540d04b3f417ecba48681b61f0d2ef91175fc9c4b',
        'content/instance_cmds.py::_stage_npcs': 'cf6ae326b0300abdd6ef55605c688811807800d4ebc9684755c56b96ed433f20',
        'content/shop.py::apprentice_protect_mats': '12f8e4751608242aa5d9de2daccaf3271edc5b710102db78fa718161216d7141',
        'content/cmds_world.py::quest_view': 'ef6d56b2df216ac3faba67d108de3010bb407b57ed411e1685ef8a5015debc46',
        'content/economy_cmds.py::shop': '26116239eefc8181717b6d8f520a2a1e5c5ff37cdd1365872b3a8feab870233f',
        'content/economy_cmds.py::buy': 'b497ca80f824ad6b90adb2da1c57169577740b764e669b21a785e22a022e1b29',
        'content/talk_actions.py::action_apprentice_check': '3079da595d629cb8a83530cbfdaf221a85ee971804ae29895c47577748585edc',
        'content/item_templates.py::tpl_teleport_portal': 'f833ca2a3eebd4c0fb13e365a049d0b3f484e906bb80f63c4481e15201cc2bd2',
        'content/combat_cmds.py::roll_wild_encounter': '2c66022b9137474a748b8bfb1135c88e09e7fa6cbcab9214016e95ae786709a1',
    },
    'aux': {
        'golden_buy': '67680ae9662d874c29f3d6ac8b3ed7b4449fba6a974df7c1023e62f78b3b6862',
        'golden_shop': '1feeeb518db7077d09f3077da3ec9227d41f1fe81e8f7d4573f66021250f4508',
        'talk_flag_raw': '{"npc_mayor": ["pledged"]}',
        'talk_key': 'talk_u1i4o_1001',
        'talk_state_raw': '{"npc": "npc_mayor", "node": "welcome"}',
    },
    'segments': {
        'E': [
            'content/talk_actions.py::action_apprentice_check',
            'content/item_templates.py::tpl_teleport_portal',
            'content/combat_cmds.py::roll_wild_encounter',
        ],
        'C': [
            'content/cmds_base_rules.py::wild_trader_here',
            'content/instance_cmds.py::_stage_npcs',
            'content/shop.py::apprentice_protect_mats',
            'content/cmds_world.py::quest_view',
            'content/economy_cmds.py::shop',
            'content/economy_cmds.py::buy',
        ],
    },
    'tier': {
        'content/cmds_base_rules.py::wild_trader_here': '甲',
        'content/instance_cmds.py::_stage_npcs': '乙',
        'content/shop.py::apprentice_protect_mats': '甲',
        'content/cmds_world.py::quest_view': '甲',
        'content/economy_cmds.py::shop': '丙',
        'content/economy_cmds.py::buy': '丙',
        'content/talk_actions.py::action_apprentice_check': '甲',
        'content/item_templates.py::tpl_teleport_portal': '甲',
        'content/combat_cmds.py::roll_wild_encounter': '甲',
    },
}
# <<< _u1i4_outer_gen (auto) <<<

_MODULES = {
    "content/cmds_base_rules.py": CBR,
    "content/instance_cmds.py": IC,
    "content/shop.py": SHOP,
    "content/cmds_world.py": CW,
    "content/economy_cmds.py": EC,
    "content/talk_actions.py": TA,
    "content/item_templates.py": IT,
    "content/combat_cmds.py": CC,
}


def _key(relpath, symbol):
    return "%s::%s" % (relpath, symbol)


# ══════════════════════════════════════════════════════════════════════════════
# 1. 只读哈希 / 猴补
# ══════════════════════════════════════════════════════════════════════════════
def _pkg_file(relpath):
    return os.path.join(PKG_ROOT, *relpath.split("/"))


def _file_sha(relpath):
    with open(_pkg_file(relpath), encoding="utf-8") as fh:
        return sha256(fh.read())


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


@contextlib.contextmanager
def _patch_many(obj, **kw):
    with contextlib.ExitStack() as st:
        for k, v in kw.items():
            st.enter_context(_Patch(obj, k, v))
        yield obj


# ══════════════════════════════════════════════════════════════════════════════
# 2. 旧实现（frozen 文本 exec 到独立命名空间）
# ══════════════════════════════════════════════════════════════════════════════
def _noop_register(*_a, **_k):
    def _deco(fn):
        return fn
    return _deco


def _old_fn(relpath, symbol, *, overrides=None, register_noop=False):
    """把冻结段 `exec` 成**成品函数对象**（`ns` 独立，不碰活模块）。

    类方法（`_stage_npcs` / `shop` / `buy`）带 4 空格缩进 ⇒ 套一个空类壳再 exec
    （**不能 `textwrap.dedent`**：`buy` 体内有一行列 0 的注释，公共前缀为空 ⇒ dedent 失效；
    注释的缩进对 tokenizer 无意义，套类壳即可）。冻结字面量本身一字不改（pin 钉的是字面量）。
    """
    mod = _MODULES[relpath]
    ns = dict(vars(mod))
    if register_noop:
        ns["register"] = _noop_register
        ns["declared"] = _noop_register
        ns["require_player"] = _noop_register
    if overrides:
        ns.update(overrides)
    text = _FROZEN_TEXT[_key(relpath, symbol)]
    tag = "<frozen:%s>" % _key(relpath, symbol)
    if text[:1].isspace():
        exec(compile("class _FrozenNS:\n" + text, tag, "exec"), ns)           # noqa: S102
        return ns["_FrozenNS"].__dict__[symbol], ns
    exec(compile(text, tag, "exec"), ns)                                     # noqa: S102
    return ns[symbol], ns


def _live_method_class(mod, symbol):
    for _n, val in list(vars(mod).items()):
        if isinstance(val, type) and symbol in vars(val):
            return val
    raise KeyError(symbol)


def _live_fn(relpath, symbol):
    mod = _MODULES[relpath]
    obj = getattr(mod, symbol, None)
    if obj is not None:
        return obj
    return _live_method_class(mod, symbol).__dict__[symbol]


# ══════════════════════════════════════════════════════════════════════════════
# 3. 甲类探针 ① `wild_trader_here`（Lookup + Presence 装配）
# ══════════════════════════════════════════════════════════════════════════════
class _WildShim:
    """`content.wild` 的最小替身：只给 `wild_trader_here` 用到的三个口。"""

    def __init__(self, table, place_fn, findable_fn):
        self.ALL_WILD = table
        self._place = place_fn
        self._find = findable_fn

    def npc_map_id(self, npc_id, npc, now=None):
        return self._place(npc_id, npc)

    def wild_npc_findable(self, npc_id, npc, player, group_id, qq_id):
        return self._find(npc_id, npc)


_SYNTH_TABLE = {
    "t_a": {"funcs": ["trade"], "map": "m1"},
    "t_b": {"funcs": ["trade"], "roam": ["m1", "m2"]},
    "t_c": {"funcs": ["talk"], "map": "m1"},
    "t_d": {"funcs": ["trade", "shop"], "map": "m2"},
    "t_e": {"funcs": [], "map": "m1"},
}
_SYNTH_PLACES = {"t_a": "m1", "t_b": "m2", "t_c": "m1", "t_d": "m2", "t_e": "m1"}
_REAL_TRADERS = {k: v for k, v in W.ALL_WILD.items() if "trade" in (v.get("funcs") or [])}

_COUNT = {k: 0 for k in ("trader", "shop_mats", "quest_view", "apprentice_check",
                          "portal", "roll", "stage_npcs", "econ_shop", "econ_buy")}
_EXPECT = {}


def _trader_call(table, place_fn, findable_fn, player, g, q):
    shim = _WildShim(table, place_fn, findable_fn)
    old, _ns = _old_fn("content/cmds_base_rules.py", "wild_trader_here",
                       overrides={"_wild": shim})
    with _Patch(CBR, "_wild", shim):
        return old(player, g, q), CBR.wild_trader_here(player, g, q)


def _probe_trader():
    player = {"cur_map": "m1"}
    bad = []
    for place in ("m1", "m2", "m3"):
        for finds in ((), ("t_a",), ("t_b",), ("t_a", "t_b", "t_d")):
            a, b = _trader_call(_SYNTH_TABLE, lambda n, r: _SYNTH_PLACES[n],
                                lambda n, r: n in finds, player, "g1", "q1")
            _COUNT["trader"] += 1
            if a != b:
                bad.append(("synth", place, finds, a, b))
    for nid, row in list(_REAL_TRADERS.items()):
        place = W.npc_map_id(nid, row)
        for finds in ((), (nid,)):
            a, b = _trader_call(W.ALL_WILD, lambda n, r: W.npc_map_id(n, r),
                                lambda n, r: n in finds, {"cur_map": place}, "g1", "q1")
            _COUNT["trader"] += 1
            if a != b:
                bad.append(("real", nid, place, finds, a, b))
        a, b = _trader_call(W.ALL_WILD, lambda n, r: W.npc_map_id(n, r),
                            lambda n, r: True, {"cur_map": "ZZZ"}, "g1", "q1")
        _COUNT["trader"] += 1
        if a != b:
            bad.append(("real-miss", nid, a, b))
    for gq in ((None, None), ("", "q1"), ("g1", "")):
        a, b = _trader_call(_SYNTH_TABLE, lambda n, r: _SYNTH_PLACES[n],
                            lambda n, r: True, player, gq[0], gq[1])
        _COUNT["trader"] += 1
        if a != b:
            bad.append(("early", gq, a, b))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 4. 甲类探针 ② `shop.apprentice_protect_mats`（dialogue 游标 + 节点取用）
# ══════════════════════════════════════════════════════════════════════════════
_SYNTH_TREES = {
    "zz_synth": {
        "start": "good",
        "nodes": {
            "good": {"options": [
                {"action": {"apprentice_check": {"item": "矿石", "count": 3}}},
                {"action": {"apprentice_check": {"item": "草药", "count": 1}}},
                {"action": {"unlock_prof": "mining"}},
            ]},
            "bad": None,
            "alias": "good",
        },
    },
}


class _DbState:
    def __init__(self, st):
        self._st = st

    def get_talk_state(self, group_id, qq_id):
        return self._st


class _DlgShim:
    def __init__(self, extra=None):
        self.extra = dict(extra or {})

    def get_dialogue(self, npc_id):
        if npc_id in self.extra:
            return self.extra[npc_id]
        return DLG.get_dialogue(npc_id)

    def dialogue_node(self, dlg, node_id):
        return DLG.dialogue_node(dlg, node_id)


def _shop_mats_sessions():
    out = [None, {}]
    for npc_id, tree in DLG._dialogues().items():
        for nid in (tree.get("nodes") or {}):
            out.append({"npc": npc_id, "node": nid})
    out += [
        {"npc": "zz_synth", "node": "good"},
        {"npc": "zz_synth", "node": "bad"},
        {"npc": "zz_synth", "node": "alias"},
        {"npc": "zz_synth", "node": "nope"},
        {"npc": "npc_not_exist", "node": "x"},
        {"npc": "zz_synth", "node": ""},
        {"npc": "zz_synth"},
        {"npc": ""},
        {"node": "good"},
    ]
    return out


def _shop_mats_call(st):
    dbst = _DbState(st)
    cshim = _DlgShim(_SYNTH_TREES)
    old, _ns = _old_fn("content/shop.py", "apprentice_protect_mats",
                       overrides={"_h": lambda _n: dbst, "C": cshim})
    with _Patch(SHOP, "_h", lambda _n: dbst), _Patch(SHOP, "C", cshim):
        return old("g1", "q1"), SHOP.apprentice_protect_mats("g1", "q1")


def _probe_shop_mats():
    bad = []
    for st in _shop_mats_sessions():
        a, b = _shop_mats_call(st)
        _COUNT["shop_mats"] += 1
        if a != b:
            bad.append((st, a, b))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 5. 甲类探针 ③ `cmds_world.quest_view`（师门考验面板判据）
# ══════════════════════════════════════════════════════════════════════════════
_MASTERS = ("npc_herb_master", "npc_mine_master", "npc_fish_master", "npc_cook_master",
            "npc_alchemy_master", "npc_craft_master", "npc_enhance_master", "npc_rune_master")


class _ShellStub:
    def _is_redname(self, qq_id):
        return False

    def _tip(self, kind):
        return "TIP"

    def _record_list_state(self, *a):
        pass


class _EnvStub:
    def __init__(self, player, group_id="g1", uid="q1"):
        self.group_id = group_id
        self.uid = uid
        self.player = player

    def arg_text(self, cmd):
        return ""

    def page(self, raw):
        return 1

    def page_items(self, items, page, per_page=5):
        return (list(items), 1, 1)


class _QDb:
    def __init__(self, quests, ts):
        self._q = quests
        self._ts = ts

    def get_quests(self, group_id, qq_id):
        return json.loads(json.dumps(self._q))

    def save_quests(self, group_id, qq_id, quests):
        pass

    def get_talk_state(self, group_id, qq_id):
        return self._ts

    def count_item(self, group_id, qq_id, item):
        return 0


def _quest_view_call(ts, quests):
    shell = _ShellStub()
    qdb = _QDb(quests, ts)
    overrides = {"register": _noop_register, "_shell": lambda env: shell, "db": qdb}
    old, _ns = _old_fn("content/cmds_world.py", "quest_view", overrides=overrides)
    with _patch_many(CW, _shell=lambda env: shell, db=qdb):
        return old(_EnvStub({"cur_map": "oak"})), CW.quest_view(_EnvStub({"cur_map": "oak"}))


def _quest_view_matrix():
    quest_cases = [
        {"main_quest": None},
        {"main_quest": "q1_1", "main_status": "pending", "main_progress": {}},
        {"main_quest": "q1_1", "main_status": "ready", "main_progress": {}},
        {"main_quest": "q_nonexistent", "main_status": "active", "main_progress": {}},
        {"main_quest": None, "side": {"s1": {"status": "ready"}}},
    ]
    ts_cases = [None, {}]
    ts_cases += [{"npc": m} for m in _MASTERS]
    ts_cases += [{"npc": "npc_mayor"}, {"npc": "npc_not_exist"}]
    ts_cases += [{"npc": m, "node": "n1"} for m in _MASTERS[:2]]
    return quest_cases, ts_cases


def _probe_quest_view():
    bad = []
    quest_cases, ts_cases = _quest_view_matrix()
    for quests in quest_cases:
        for ts in ts_cases:
            a, b = _quest_view_call(ts, quests)
            _COUNT["quest_view"] += 1
            if a != b:
                bad.append((ts, quests.get("main_status"), a[-4:], b[-4:]))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 6. 甲类探针 ④ `talk_actions.action_apprentice_check`（E 栏：树遍历）
# ══════════════════════════════════════════════════════════════════════════════
class _TADb:
    def __init__(self, have):
        self.have = have

    def count_item(self, group_id, qq_id, item):
        return self.have


class _WorldStub:
    def __init__(self, unlocked=True):
        self._unlocked = unlocked
        self._talk_route = ""
        self._talk_tail = []
        self.calls = []

    def _prof_active_check(self, group_id, qq_id, prof):
        self.calls.append((group_id, qq_id, prof))
        return (True, "") if self._unlocked else (False, "先拜师解锁")


def _apprentice_trees():
    hits = []
    for npc_id, tree in DLG._dialogues().items():
        for _nid, node in (tree.get("nodes") or {}).items():
            if not isinstance(node, dict):
                continue
            if any(((o.get("action") or {}).get("unlock_prof")) for o in (node.get("options") or [])):
                hits.append(npc_id)
                break
    return hits


def _apprentice_call(npc_id, have, unlocked, action):
    dbst = _TADb(have)
    old, _ns = _old_fn("content/talk_actions.py", "action_apprentice_check",
                       overrides={"register": _noop_register, "db": dbst})
    w_old, w_new = _WorldStub(unlocked), _WorldStub(unlocked)

    def _run(fn, world):
        """异常也纳入比对口径（`npc_not_exist` 无树时两态必须**同样**抛错，不许一边兜底）。"""
        try:
            return ("OK", list(fn(world, "g1", "q1", {}, npc_id, action)),
                    world._talk_route, list(world._talk_tail))
        except Exception as exc:                                        # noqa: BLE001
            return ("EXC", type(exc).__name__)

    a = _run(old, w_old)
    with _Patch(TA, "db", dbst):
        b = _run(TA.action_apprentice_check, w_new)
    return a, b


def _apprentice_matrix():
    action = {"apprentice_check": {"item": "铁矿石", "count": 7}}
    npcs = _apprentice_trees()[:2] + ["npc_not_exist"]
    combos = [(h, u) for h in (0, 3, 7, 99) for u in (True, False) if not (h == 3 and u)]
    return action, npcs, combos


def _probe_apprentice_check():
    bad = []
    action, npcs, combos = _apprentice_matrix()
    for npc_id in npcs:
        for have, unlocked in combos:
            a, b = _apprentice_call(npc_id, have, unlocked, action)
            _COUNT["apprentice_check"] += 1
            if a != b:
                bad.append((npc_id, have, unlocked, a, b))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 7. 甲类探针 ⑤ `item_templates.tpl_teleport_portal`（E 栏）+ ⑥ combat 转发
# ══════════════════════════════════════════════════════════════════════════════
class _PortalDb:
    def __init__(self, portals):
        self.portals = list(portals)
        self.cleared = 0
        self.moved = None
        self.visited = []

    def get_portals(self, qq_id):
        return list(self.portals)

    def update_player(self, g, q, **kw):
        self.moved = kw

    def add_visited(self, g, q, m):
        self.visited.append(m)

    def clear_talk_state(self, g, q):
        self.cleared += 1


_CURRENT_DB = None


class _CtxStub:
    def __init__(self, player, battle=None):
        self._focus = player
        self.battle = battle
        self.group_id = "g1"
        self.qq_id = "q1"
        self.hook_calls = []

    def _db(self):
        return _CURRENT_DB

    def hook(self, name, *a, **k):
        self.hook_calls.append(name)


def _portal_call(player, battle, portals):
    global _CURRENT_DB
    saved = _CURRENT_DB
    try:
        pdb = _PortalDb(portals)
        _CURRENT_DB = pdb
        old, _ns = _old_fn("content/item_templates.py", "tpl_teleport_portal",
                           overrides={"register": _noop_register, "_rand_tip": lambda c: "TIP"})
        a = old(_CtxStub(player, battle))
        a_clear = pdb.cleared
        pdb2 = _PortalDb(portals)
        _CURRENT_DB = pdb2
        with _Patch(IT, "_rand_tip", lambda c: "TIP"):
            b = IT.tpl_teleport_portal(_CtxStub(player, battle))
        b_clear = pdb2.cleared
    finally:
        _CURRENT_DB = saved
    key = lambda r: (getattr(r, "text", None), getattr(r, "payload", None),
                     getattr(r, "consume", None))
    return (key(a), a_clear), (key(b), b_clear)


def _portal_matrix():
    dests = [m for m in IT._cs.PORTALS if m in _MAP_BY_ID]
    dest = dests[0] if dests else None
    out = []
    for battle in (None, object()):
        for player, portals in (
                ({"cur_map": "oak_plain"}, []),
                ({"cur_map": dest}, [dest]),
                ({"cur_map": "oak_plain"}, [dest]),
                ({"cur_map": "oak_plain"}, ["not_a_map"])):
            out.append((player, battle, portals))
    return out


def _probe_portal():
    bad = []
    for player, battle, portals in _portal_matrix():
        a, b = _portal_call(player, battle, portals)
        _COUNT["portal"] += 1
        if a != b:
            bad.append((battle is None, player, portals, a, b))
    return bad


def _probe_roll():
    calls = []

    def fake_overlay(name, pkg_obj):
        def _call(*a, **k):
            calls.append(("overlay", name))
            return pkg_obj(*a, **k)
        return _call

    def fake_pkg(*a, **k):
        calls.append(("pkg",) + tuple(a))
        return ("R", a, tuple(sorted(k.items())))

    overrides = {"_overlay": fake_overlay, "_pkg_roll_wild_encounter": fake_pkg}
    old, _ns = _old_fn("content/combat_cmds.py", "roll_wild_encounter", overrides=overrides)
    bad = []
    for args in (("g1", "q1"), ("g1", "q1", {"a": 1}, "oak_plain")):
        calls.clear()
        a = old(*args)
        ca = list(calls)
        calls.clear()
        with _patch_many(CC, _overlay=fake_overlay, _pkg_roll_wild_encounter=fake_pkg):
            b = CC.roll_wild_encounter(*args)
        cb = list(calls)
        _COUNT["roll"] += 1
        if (a, ca) != (b, cb):
            bad.append((args, a, ca, b, cb))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 8. 乙类探针 `instance_cmds._stage_npcs`（替身 self）
# ══════════════════════════════════════════════════════════════════════════════
class _IRShim:
    def __init__(self, index):
        self._index = index

    def stages_progress(self, st):
        return types.SimpleNamespace(index=self._index)


class _InstanceSelf:
    def __init__(self, row):
        self._row = row

    def _instance_battle_for(self, group_id, qq_id):
        return self._row


def _stage_npcs_call(row, index):
    ir = _IRShim(index)
    old, _ns = _old_fn("content/instance_cmds.py", "_stage_npcs", overrides={"IR": ir})
    selfobj = _InstanceSelf(row)
    a = old(selfobj, "g1", "q1")
    cls = _live_method_class(IC, "_stage_npcs")
    with _Patch(IC, "IR", ir):
        b = cls._stage_npcs(selfobj, "g1", "q1")
    return a, b


def _stage_npcs_matrix():
    rows = [
        None,
        {"state": {"inst_stages": []}},
        {"state": {"inst_stages": [{"npcs": ["n1", "n2"]}]}},
        {"state": {"inst_stages": [{"npcs": []}, {"npcs": ["n3"]}]}},
        {"state": {"inst_stages": [{"npcs": None}]}},
        {"state": {"inst_stages": [{}]}},
        {"state": {}},
    ]
    return rows, (0, 1, 5)


def _probe_stage_npcs():
    bad = []
    rows, indexes = _stage_npcs_matrix()
    for i, row in enumerate(rows):
        for index in indexes:
            a, b = _stage_npcs_call(row, index)
            _COUNT["stage_npcs"] += 1
            if a != b:
                bad.append((i, index, a, b))
    return bad


# ══════════════════════════════════════════════════════════════════════════════
# 9. 丙类探针 `economy_cmds.shop` / `buy`（异步生成器端到端）
# ══════════════════════════════════════════════════════════════════════════════
_WT_IDS = ["wt_a", "wt_b", "wt_c", "wt_d", "wt_e", "wt_f"]


class _ClifeStub:
    SHOP_SUBAREA_ITEMS = {}
    SHOP_WILD_TRADE = list(_WT_IDS)
    SHOP_WEAPONS = {}
    SHOP_SMITH_MATERIALS = {}
    SHOP_EQUIP = {}
    MOUNT_POOL = []
    ECON_CONFIG = {"buy_qty_max": 99, "bp_price_per_lv": 1, "bp_price_base": 1,
                   "bp_smith_mult": 1}


class _CitStub:
    ITEMS = {i: {"name": "行商货" + i[-1], "price": 10, "desc": "d"} for i in _WT_IDS}
    MATERIALS = {}


class _CspaceStub:
    MAP_BY_ID = {}


class _B143Stub:
    QUALITY = {}
    WORLD_EVENT_POOL = []


class _CcoreStub:
    START_MAP = "oak"


class _SsStub:
    def town_level(self, cur):
        return 1

    def get_smith_stock(self, cur, lv):
        return []


class _EconDb:
    def count_item(self, group_id, qq_id, item):
        return 0

    def get_world_event(self):
        return None

    def get_event_state(self, key):
        return None

    def update_player(self, *a, **k):
        return None

    def add_item(self, *a, **k):
        return None


class _EconC:
    def __init__(self, timed):
        self._timed = timed

    def get_timed(self, group_id, qq_id, key):
        return self._timed

    def random_req(self, *a, **k):
        return {}

    def display(self, *a, **k):
        return ""


class _ShopSvcStub:
    def buy_index_dispatch(self, *a, **k):
        return (None, "STUB-BUY")


class _EconEvent:
    def __init__(self, msg=""):
        self.message_str = msg

    def plain_result(self, text):
        return text


class _EconSelf:
    def __init__(self, trader, msg=""):
        self._trader = trader
        self._msg = msg
        self._pdata = {"cur_map": "oak_plain", "cur_subarea": "", "level": 5,
                       "gold": 99999, "equipment": {}, "mounts": {}}

    def _uid(self, event):
        return ("g1", "q1")

    def _player(self, group_id, qq_id):
        return self._pdata

    def _is_redname(self, qq_id):
        return False

    def _at_shop(self, player, group_id="", qq_id=""):
        return True

    def _facility_hint(self, player, kind):
        return ""

    def _is_smith_shop(self, player):
        return False

    def _sa_shop_kind(self, player):
        return "general"

    def _cur_subarea(self, player):
        return {"name": "测试子区域"}

    def _wild_trader_here(self, player, group_id="", qq_id=""):
        return self._trader

    def _shop_limit_label(self, sa_id, key):
        return ""

    def _shop_equip_roster(self, player, ids):
        return []

    def _shop_equip_price(self, *a, **k):
        return 1

    def _req_label(self, r):
        return ""

    def _shop_limit_buy_guard(self, group_id, qq_id, sa_id, key, qty):
        return (True, "")

    def _buy_weapon(self, *a, **k):
        return None

    def _strip_cmd(self, event, cmd):
        return self._msg

    def _parse_page(self, raw):
        return 1

    def _page_items(self, entries, page, per_page=5):
        return (list(entries), 1, 1)

    def _record_list_state(self, *a):
        pass

    def _tip(self, kind):
        return "TIP"


#: **原始**读口引用（import 期抓）：旧侧命名空间必须用这两份 pristine，
#: 否则「猴补 `EC._wild` / `EC._cquest` 造反证」会被 `_old_fn` 的 `vars(mod)` 拷贝一起拿走，
#: 两侧同样被破坏 ⇒ 探针假绿。
_ORIG_EC_WILD = EC._wild
_ORIG_EC_CQUEST = EC._cquest


def _econ_globals(trader, timed):
    """只含**注入面**（不含 `_wild` / `_cquest`：那两个留给反证猴补）。"""
    return {
        "_clife": _ClifeStub, "_cit": _CitStub, "_cspace": _CspaceStub,
        "_b143": _B143Stub, "_ccore": _CcoreStub, "_ss": _SsStub,
        "db": _EconDb(), "C": _EconC(timed), "_shop_svc": _ShopSvcStub(),
        "json": json,
    }


def _drain(agen):
    import asyncio

    async def _go():
        out = []
        async for item in agen:
            out.append(item if isinstance(item, str) else getattr(item, "text", item))
        return out
    return asyncio.run(_go())


def _econ_run_live(symbol, trader, timed, msg):
    gl = _econ_globals(trader, timed)
    cls = _live_method_class(EC, symbol)
    with _patch_many(EC, **gl):
        return _drain(cls.__dict__[symbol](_EconSelf(trader, msg), _EconEvent(msg)))


def _econ_call(symbol, trader, timed, msg):
    over = dict(_econ_globals(trader, timed))
    over["_wild"] = _ORIG_EC_WILD          # ★ 旧侧恒用 pristine 读口（见上注）
    over["_cquest"] = _ORIG_EC_CQUEST
    old, _ns = _old_fn("content/economy_cmds.py", symbol, overrides=over)
    a = _drain(old(_EconSelf(trader, msg), _EconEvent(msg)))
    b = _econ_run_live(symbol, trader, timed, msg)
    return a, b


#: 行商场景：`w_old_trader` 无 roam（需限时）/ `h_night_trader` 有 roam（恒在场）/
#: `w_night_merchant` 未命中 `WILD_NPCS`（标题回落「行商」）/ None
_ECON_CASES = (
    (None, None),
    ("w_old_trader", None),
    ("w_old_trader", {"key": "wild:w_old_trader"}),
    ("h_night_trader", None),
    ("w_night_merchant", None),
    ("w_night_merchant", {"key": "wild:w_night_merchant"}),
)


def _probe_econ_shop():
    bad = []
    for trader, timed in _ECON_CASES:
        a, b = _econ_call("shop", trader, timed, "")
        _COUNT["econ_shop"] += 1
        if a != b:
            bad.append((trader, bool(timed), a, b))
    return bad


def _probe_econ_buy():
    bad = []
    for trader, timed in _ECON_CASES:
        a, b = _econ_call("buy", trader, timed, "6")
        _COUNT["econ_buy"] += 1
        if a != b:
            bad.append((trader, bool(timed), a, b))
    return bad


def _econ_outputs():
    """丙类 golden 用的**绝对输出**（只跑活侧；golden 在红基线期抓）。"""
    out = {}
    for label in ("shop", "buy"):
        msg = "" if label == "shop" else "6"
        out[label] = [[t, bool(ev), _econ_run_live(label, t, ev, msg)]
                      for t, ev in _ECON_CASES]
    return out


# ══════════════════════════════════════════════════════════════════════════════
# [1] 双 sha256 + E/C 分类
# ══════════════════════════════════════════════════════════════════════════════
def test_frozen_pins():
    print("【1. 双 sha256：9 段冻结文本 + 活实现 inspect.getsource】")
    keys = list(_PIN["frozen"])
    check("冻结段数 == 9（外围 8 文件）", len(keys) == 9, len(keys))
    check("门禁内键序 == 冻结文本键序", keys == list(_FROZEN_TEXT), keys[:3])
    bad_frozen = [k for k in keys if sha256(_FROZEN_TEXT[k]) != _PIN["frozen"][k]]
    check("9 段冻结文本 sha256 全等 _PIN['frozen']（安全网未被改）", not bad_frozen, bad_frozen)
    check("档位计数：甲 6 / 乙 1 / 丙 2",
          [sum(1 for v in _PIN["tier"].values() if v == t) for t in ("甲", "乙", "丙")] == [6, 1, 2],
          _PIN["tier"])
    bad_live = []
    for key in keys:
        relpath, symbol = key.split("::")
        if sha256(inspect.getsource(_live_fn(relpath, symbol))) != _PIN["live"].get(key):
            bad_live.append(key)
    check("9 段活实现 sha256 全等 _PIN['live']", not bad_live, bad_live)
    if _PIN["phase"] == "landed":
        e_bad = [k for k in _PIN["segments"]["E"] if _PIN["live"][k] != _PIN["frozen"][k]]
        c_bad = [k for k in _PIN["segments"]["C"] if _PIN["live"][k] == _PIN["frozen"][k]]
        check("E 栏 3 段 frozen == live（没顺手动过）", not e_bad, e_bad)
        check("C 栏 6 段 frozen != live（真接上了）", not c_bad, c_bad)
    else:
        check("phase != landed ⇒ C 栏不等式断言按设计不启用", _PIN["phase"] == "baseline",
              _PIN["phase"])


# ══════════════════════════════════════════════════════════════════════════════
# [2] aux 指纹（§3-②③⑪）
# ══════════════════════════════════════════════════════════════════════════════
def _aux_fingerprints():
    out = {}
    db.init_db()
    g, q = "u1i4o", "1001"
    db.clear_talk_state(g, q)
    db.set_talk_state(g, q, "npc_mayor", "welcome")
    out["talk_key"] = PW.talk_state_key(g, q)
    out["talk_state_raw"] = db.get_event_state(PW.talk_state_key(g, q))
    db.set_talk_flag(g, q, "npc_mayor", "pledged")
    out["talk_flag_raw"] = db.get_event_state(PW.talk_flags_key(g, q))
    db.clear_talk_state(g, q)
    econ = _econ_outputs()
    out["golden_shop"] = sha256(json.dumps(econ["shop"], ensure_ascii=False, sort_keys=True))
    out["golden_buy"] = sha256(json.dumps(econ["buy"], ensure_ascii=False, sort_keys=True))
    return out


def test_aux():
    print("【2. aux 指纹：会话键/落盘 JSON 原文 + 丙类 golden（§3-②③⑪）】")
    now = _aux_fingerprints()
    for k in sorted(_PIN["aux"]):
        check("aux[%s] 全等 _PIN" % k, now.get(k) == _PIN["aux"][k],
              "%r != %r" % (str(now.get(k))[:60], str(_PIN["aux"][k])[:60]))
    check("aux 条数 == 5（talk_key/talk_state_raw/talk_flag_raw/golden_shop/golden_buy）",
          len(_PIN["aux"]) == 5, sorted(_PIN["aux"]))


# ══════════════════════════════════════════════════════════════════════════════
# [3] 甲 / 乙 / 丙 探针
# ══════════════════════════════════════════════════════════════════════════════
_PROBES = (
    ("wild_trader_here", _probe_trader),
    ("apprentice_protect_mats", _probe_shop_mats),
    ("quest_view", _probe_quest_view),
    ("action_apprentice_check", _probe_apprentice_check),
    ("tpl_teleport_portal", _probe_portal),
    ("combat_cmds.roll_wild_encounter", _probe_roll),
    ("instance_cmds._stage_npcs", _probe_stage_npcs),
    ("economy_cmds.shop", _probe_econ_shop),
    ("economy_cmds.buy", _probe_econ_buy),
)


def _expected_counts():
    _rows, _idx = _stage_npcs_matrix()
    _action, _npcs, _combos = _apprentice_matrix()
    _qc, _ts = _quest_view_matrix()
    return {
        "trader": 3 * 4 + len(_REAL_TRADERS) * 3 + 3,
        "shop_mats": len(_shop_mats_sessions()),
        "quest_view": len(_qc) * len(_ts),
        "apprentice_check": len(_npcs) * len(_combos),
        "portal": len(_portal_matrix()),
        "roll": 2,
        "stage_npcs": len(_rows) * len(_idx),
        "econ_shop": len(_ECON_CASES),
        "econ_buy": len(_ECON_CASES),
    }


def test_probes():
    print("【3. 甲/乙/丙 探针：旧实现（冻结文本 exec）↔ 活实现 逐格比】")
    for name, fn in _PROBES:
        bad = fn()
        check("探针 %s：旧 == 新 逐格" % name, not bad, bad[:2])
    print("  ── 计数校验（防「循环没跑」的假绿）──")
    exp = _expected_counts()
    for k in sorted(exp):
        check("计数 %s = %d == 预期 %d" % (k, _COUNT[k], exp[k]), _COUNT[k] == exp[k],
              (_COUNT[k], exp[k]))
    check("比对总数 == %d" % sum(exp.values()), sum(_COUNT.values()) == sum(exp.values()),
          sum(_COUNT.values()))


# ══════════════════════════════════════════════════════════════════════════════
# [4] 口径分歧（本门禁覆盖的 4 条）
# ══════════════════════════════════════════════════════════════════════════════
def test_divergences():
    print("【4. 口径分歧：节点真值链 / 首个命中序 / 两边界 / 标题名随口】")
    for stage in ({"npcs": []}, {"npcs": None}, {}, {"npcs": ["a"]}):
        a, b = _stage_npcs_call({"state": {"inst_stages": [stage]}}, 0)
        check("分歧① 节点取用真值链 %r" % (stage,), a == b == (stage.get("npcs") or []), (a, b))
    table = {"z_first": {"funcs": ["trade"], "map": "m1"},
             "a_second": {"funcs": ["trade"], "map": "m1"}}
    a, b = _trader_call(table, lambda n, r: "m1", lambda n, r: True, {"cur_map": "m1"}, "g", "q")
    check("分歧② 首个命中 = 插入序首条（不是字典序）", a == b == "z_first", (a, b))
    a, b = _shop_mats_call(None)
    check("分歧③ 无会话 → {}（旧 == 新）", a == b == {}, (a, b))
    a, b = _shop_mats_call({})
    check("分歧③ 空会话 → {}（旧 == 新）", a == b == {}, (a, b))
    a, b = _shop_mats_call({"npc": "zz_synth", "node": "bad"})
    check("分歧③ 节点非映射 → {}（旧 == 新）", a == b == {}, (a, b))
    a, b = _shop_mats_call({"npc": "zz_synth", "node": "good"})
    check("分歧③ 真节点 → 材料映射逐键逐值", a == b == {"矿石": 3, "草药": 1}, (a, b))
    t1, t1b = _econ_call("shop", "w_old_trader", None, "")
    t2, t2b = _econ_call("shop", "w_night_merchant", None, "")
    check("分歧④ 行商名命中 WILD_NPCS → 用真名", "游商·老马" in "".join(t1) and t1 == t1b, t1)
    check("分歧④ 未命中 WILD_NPCS → 回落『行商』", "行商" in "".join(t2) and t2 == t2b, t2)


# ══════════════════════════════════════════════════════════════════════════════
# [5] 有牙反证（6 处破坏 → 对应探针必须变红；原地还原，零写盘）
# ══════════════════════════════════════════════════════════════════════════════
def _break_trader():
    """破坏 ① `wild_trader_here`：丢掉「当天定位 == 当前图」这条判据（只留 funcs 判据）。"""
    def _f(player, group_id="", qq_id=""):
        if not (group_id and qq_id):
            return None
        w = CBR._wild
        for nid, row in w.ALL_WILD.items():
            if "trade" not in (row.get("funcs") or []):
                continue
            if w.wild_npc_findable(nid, row, player, group_id, qq_id):
                return nid
        return None
    return _Patch(CBR, "wild_trader_here", _f)


def _break_shop_mats():
    """破坏 ② `apprentice_protect_mats`：返回映射多一个哨兵键（映射不再逐键逐值）。"""
    orig = SHOP.apprentice_protect_mats

    def _f(group_id, qq_id):
        out = dict(orig(group_id, qq_id))
        if out:
            out["__BREAK__"] = 1
        return out
    return _Patch(SHOP, "apprentice_protect_mats", _f)


def _break_quest_view():
    """破坏 ③ `quest_view`：面板多一行（渲染行不再逐字相同）。"""
    orig = CW.quest_view

    def _f(env):
        return list(orig(env)) + ["__BREAK__"]
    return _Patch(CW, "quest_view", _f)


def _break_stage_npcs():
    """破坏 ④ `_stage_npcs`：节点取用不再走真值链（`{"npcs": None}` → `None`）。"""
    def _f(self, group_id, qq_id):
        row = self._instance_battle_for(group_id, qq_id)
        if not row:
            return []
        st = row["state"]
        stages = st.get("inst_stages") or []
        idx = IC.IR.stages_progress(st).index
        stage = stages[idx] if idx < len(stages) else {}
        return stage.get("npcs")
    return _Patch(_live_method_class(IC, "_stage_npcs"), "_stage_npcs", _f)


def _break_econ_buy():
    """破坏 ⑤ `buy` 的「行商行表」读口：给静态行商强塞一个 roam（在场判定被改）。"""
    table = {k: dict(v) for k, v in W.ALL_WILD.items()}
    table["w_old_trader"] = {**table["w_old_trader"], "roam": ["oak_plain"]}
    if hasattr(EC, "_ALL_WILD_LOOKUP"):
        return _Patch(EC, "_ALL_WILD_LOOKUP", PRES.Lookup(table))
    return _Patch(EC, "_wild", types.SimpleNamespace(ALL_WILD=table))


def _break_econ_shop():
    """破坏 ⑥ `shop` 的「行商标题名」读口：把在场行商的名字换掉。"""
    table = dict(WILD_NPCS)
    table["w_old_trader"] = {"name": "__BREAK__"}
    if hasattr(EC, "_WILD_NPCS_LOOKUP"):
        return _Patch(EC, "_WILD_NPCS_LOOKUP", PRES.Lookup(table))
    return _Patch(EC, "_cquest", types.SimpleNamespace(WILD_NPCS=table))


_TEETH = (
    ("① wild_trader_here 丢定位判据", _break_trader, _probe_trader),
    ("② apprentice_protect_mats 多哨兵键", _break_shop_mats, _probe_shop_mats),
    ("③ quest_view 多一行", _break_quest_view, _probe_quest_view),
    ("④ _stage_npcs 丢真值链", _break_stage_npcs, _probe_stage_npcs),
    ("⑤ economy buy 行表被换", _break_econ_buy, _probe_econ_buy),
    ("⑥ economy shop 标题名被换", _break_econ_shop, _probe_econ_shop),
)


def test_teeth():
    print("【5. 有牙反证：破坏 6 处已改段 → 对应探针必须变红（原地还原）】")
    before = {f: _file_sha(f) for f in READONLY_FILES}
    for name, fn in _PROBES:
        bad = fn()
        check("未破坏时 `%s` 探针为绿（真实现成立）" % name, not bad, bad[:1])
    print("  ── 逐处破坏 / 还原 ──")
    for label, breaker, probe in _TEETH:
        with breaker():
            red = bool(probe())
        print("     破坏 `%s`：预期变红 / 实测 %s" % (label, "变红 ✅" if red else "仍绿 ❌"))
        check("破坏 `%s` → 探针必须变红（预期变红 / 实测变红）" % label, red is True)
        check("还原 `%s` 后探针回绿" % label, not probe())
    after = {f: _file_sha(f) for f in READONLY_FILES}
    check("反证全程零写盘（猴补原地还原）：源文件 sha256 前后一致", before == after,
          [f for f in READONLY_FILES if before[f] != after[f]])


# ══════════════════════════════════════════════════════════════════════════════
# [6] 只读断言
# ══════════════════════════════════════════════════════════════════════════════
def _check_readonly(before):
    print("【6. 只读：全程零写盘】")
    after = {f: _file_sha(f) for f in READONLY_FILES}
    bad = [f for f in READONLY_FILES if before[f] != after[f]]
    check("跑完全程 8 个源文件 sha256 前后一致", not bad, bad)
    for f in READONLY_FILES:
        print("     %-34s %s" % (f, after[f]))


def main() -> int:
    print("==" * 36)
    print("U1-I4 冻结门禁④：外围装配（8 文件 / 9 段：甲 6 · 乙 1 · 丙 2）")
    print("==" * 36)
    print("phase = %r · GWEN_GAME_DB = %s" % (_PIN["phase"], os.environ.get("GWEN_GAME_DB")))
    before = {f: _file_sha(f) for f in READONLY_FILES}
    test_frozen_pins()
    test_aux()
    test_probes()
    test_divergences()
    test_teeth()
    _check_readonly(before)
    print("\n%s\n结果：通过 %d / 共 %d" % ("-" * 46, PASS, PASS + FAIL))
    if FAILURES:
        print("失败项：")
        for f in FAILURES:
            print("  ❌", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
