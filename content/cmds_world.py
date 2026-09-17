# -*- coding: utf-8 -*-
"""包内世界域命令（`content/cmds_world.py`）—— 『任务』面板（世界域唯一真逻辑命令）。

本模块现在只剩一件事
--------------------
`quest_view`（『任务』）—— 世界域里唯一**含真逻辑**的一条命令：主线/支线分页面板要自己
拼行并落 `content/texts.py` 的渲染点，不是「取参 + 调实现体」能表达的。

> ★ S1：本模块原有一个 `_no_prof_waiting`（等待型副业互斥守卫的**第二份**实现，
> `_GUARDS.setdefault("no_prof_waiting", …)` 注册）—— 因为 `content/guards.py` 在
> import 期已经登记了同名守卫（`GUARDS.update({...})`），`setdefault` 恒为 no-op，
> 那一份是**死副本**。按「本包约定只允许一处」删掉，守卫唯一真源 = `content/guards.py`。

其余世界域命令由**声明式绑定**接管：`content/data/commands.json` 的 `bind` 直接点名实现体
（`content.world_cmds:<名>`）+ 调用模式 + 取参槽位，命令层薄壳与本地驱动助手
（`_Say` / `_resume` / `_drain` / `_run`）已删 —— 驱动与文本收集替身收进引擎
`saintess_engine.command.binding`，宿主取件口收进 `content/cmds_env.py`。

实现体真源仍是 `content/world_cmds.py`（B9 线2 逐字搬包，**一字未改**）：历史形状的
async generator（`yield event.plain_result(...)`），由引擎按 `bind.call` 驱动。

⚠️ 两条与**宿主/包内落点**有关的登记（不是本模块的活）
  * `_instance_gate_block` 已在 `content/world_cmds.py`（P5E「壳去逻辑」批从宿主壳
    `host/shell.py` 搬回）—— `tests/test_v185_instance_admission.py`（t7_wiring）要的
    `instance_gate.walk_admission` 调用点是那边的**真调用**（不再靠注释凑字符串）。
  * `quest_view` 在本模块 —— `daily.*` 渲染点随之进包，`tests/test_texts_table.py`
    的 WIRED 表按「周常」先例补上包内文件。

包内不 import 宿主（I2）：宿主壳对象经 `content/cmds_env.py::shell(env)` 取（桥接层透传），
`content/world_cmds.py` 侧既有的「宿主替身口」（`_host_attr` / `_HostMod` / `C` / `db`）一字未动。
"""
from __future__ import annotations

from . import texts as T
from . import world_cmds as _WC
from .catalog_quests import MAIN_QUESTS, NPCS, SIDE_QUESTS
from .catalog_space import MAP_BY_ID
from .cmds_env import shell as _shell
# B14 口径：数据面走包内门面（不新增 `C.<数据名>` 读点；实测与宿主 `C` 逐对象同一）
from .commands import register
from .wild import ALL_WILD
from .world_cmds import db, _DAILY_META_KEYS   # B2-W2：清死 import（C/_host_attr 全仓零调用点）
# ★ U1-D2 L4：面板目标行改走引擎目标行骨架（`quests_flow._obj_lines` = 注册表 + 声明序）
from . import quests_flow as _qf
# ★ U1-I4 L6：导师行取用 → 引擎多表首命中形状（单表**真值**链）
from saintess_engine.presence import Lookup

#: 导师行查表口（`NPCS.get(id) or {}` 的引擎形状；真值链口径逐字同义）
_NPCS_LOOKUP = Lookup(NPCS)


# ============================================================
# ① 宿主服务取件（`services.quests` 上的常量/函数）
# ============================================================
def _svc(name):
    """宿主 `services.quests` 上的常量/函数（真源写法 `from ..services.quests import X`）。"""
    from . import profession_quests as _pq
    return getattr(_pq, name)


# ============================================================
# ② 『任务』面板口径（原宿主 world.py 模块级两处，随 quest_view 一起进包）
# ============================================================
def _kill_prog_count(obj, prog):
    """v105 M19 P2：击杀进度聚合读——兼容旧存档老 key（v95.7 之前进度记
    monster['name'] 而非 obj['kill']，如『精英森林狼』），面板不再显示 0/N 孤儿计数。
    目标 key 有值用目标 key；为 0 时汇总其余包含目标名的历史 key。"""
    v = prog.get(obj["kill"], 0)
    if v == 0:
        v = sum(c for k, c in prog.items() if k != obj["kill"] and obj["kill"] in k)
    return v


# 任务目标类型 → 进度展示行（v101.3：加新目标类型 = 加一行，quest_view 零改动）
# ★ U1-D2 L4：**行文表逐字未动**；选型/行序改走引擎骨架（`_panel_text_of` 是把
#   引擎的 `text_of(type_key, obj, prog, st)` 适配到本表的薄模板）。
_OBJ_PROGRESS_LINES = {
    "kill":    lambda obj, prog: f"  进度：{_kill_prog_count(obj, prog)}/{obj['count']}",
    "collect": lambda obj, prog: f"  收集：{prog.get(obj['collect'], 0)}/{obj['count']}",
    "explore": lambda obj, prog: f"  前往：{MAP_BY_ID.get(obj['explore'], {}).get('name', '？')}",
    "talk":    lambda obj, prog: f"  交谈：与 {NPCS.get(obj['talk'], {}).get('name', '？')} 对话",
}


def _panel_text_of(type_key, obj, prog, st):
    """面板目标行模板（**内容侧声明序里首个可展示的型**，与原「查表首命中即 break」同义）。

    `未登记型 / 值为空` → `None`（不出行）——面板口只认 `_OBJ_PROGRESS_LINES` 那 4 型
    （`find`/`use` 由面板上面的专门分支处理，DESIGN §2.3 口径②）。
    """
    _fn = _OBJ_PROGRESS_LINES.get(type_key)
    if _fn is None or not obj.get(type_key):
        return None
    return _fn(obj, prog)


# ============================================================
# ③ 『任务』面板（原宿主 world.py:390-580 **逐字搬入**；渲染点 = 包内 T.text/T.static）
# ============================================================
@register("quest_view", guards=("hook:player",), params=("cmd=任务", "page"))
def quest_view(env) -> list:
    """『任务』：冒险日志（主线 + 支线分页 + 每日进度 + 师门考验 + 底部提示）。"""
    shell = _shell(env)
    group_id, qq_id = env.group_id, env.uid
    player = env.player
    if shell._is_redname(qq_id):
        return ["☠️ 你是红名！守卫不让你靠近任务板……(等红名消退再来)"]
    quests = db.get_quests(group_id, qq_id)
    lines = ["📜 【冒险日志】", "━━━━━━━━━━━━"]
    # 主线
    main_id = quests.get("main_quest")
    if main_id:
        mq = next((q for q in MAIN_QUESTS if q["id"] == main_id), None)
        # v104 M19：旧存档 main_quest 指向已下线 id（如 "q1"）→ 面板主线空白。
        # 与 _take_main_quest 同样的存档容错：重置回主线起点并落库。
        if not mq:
            quests["main_quest"] = "q1_1"
            quests["main_status"] = "pending"
            quests["main_progress"] = {}
            main_id = "q1_1"
            mq = next((q for q in MAIN_QUESTS if q["id"] == main_id), None)
            db.save_quests(group_id, qq_id, quests)
        if mq:
            _ginfo = NPCS.get(mq["giver"]) or ALL_WILD.get(mq["giver"]) or {}
            giver = _ginfo.get("name", "？")
            giver_map = _ginfo.get("map", "")
            giver_map_name = MAP_BY_ID.get(giver_map, {}).get("name", "？")
            lines.append(f"【主线】『{mq['name']}』")
            lines.append(f"  {mq['desc']}")
            st = quests.get("main_status", "pending")
            if st == "pending":
                lines.append(f"  ⏳ 未接取：去找 {giver}(在{giver_map_name})对话接取")
            elif st == "ready":
                # v95.25 #47b：主线交付=找 NPC 自动触发（与『交付任务』指令并存），不写死交付方式
                lines.append(f"  ✅ 目标达成！回去找 {giver} 交付")
            else:
                prog = quests.get("main_progress", {})
                obj = mq["objective"]
                # v101.3：目标类型展示查表化（kill/collect/explore/talk，顺序与原 if-elif 一致）
                # v169.9：主线 collect 面板实时查背包（对齐支线口径）——此前只读 main_progress
                # 存档，玩家采到材料但没对话过 NPC 时面板仍显示 0/N，误以为物品对不上（#143）
                if obj.get("collect"):
                    have = db.count_item(group_id, qq_id, obj["collect"])
                    need = obj.get("count", 1)
                    if have >= need:
                        lines.append(f"  ✅ 材料已齐：{obj['collect']} {have}/{need}（回去找 {giver} 交付）")
                    else:
                        lines.append(f"  收集：{have}/{need}")
                else:
                    # v101.3：目标类型展示查表化（kill/collect/explore/talk，顺序与原 if-elif 一致）
                    # ★ U1-D2 L4：改走引擎「有序目标注册表 + 行骨架」（内容侧 text_of = 上面
                    #   那 4 型行文表）；与原「查表首命中即 break」同义（首个可展示的型出一行）
                    for _t in _qf._obj_lines(obj, progress=prog, text_of=_panel_text_of):
                        lines.append(_t)
                        break
    else:
        lines.append("【主线】已全部完成！🎊")
    # 支线（v101.25i3：已完成任务不进面板，鱼鱼：交了还显示）
    side = quests.get("side", {})
    side_items = [(sid, sq) for sid, sq in side.items() if sq.get("status", "active") != "done"]
    if side_items:
        lines.append("")
        lines.append("【支线】")
        raw = env.arg_text("任务")
        page = env.page(raw)
        page_items, pages, page = env.page_items(side_items, page, per_page=5)
        for i, (sid, sq) in enumerate(page_items, (page - 1) * 5 + 1):
            sqd = next((q for q in SIDE_QUESTS if q["id"] == sid), None)
            if not sqd:
                continue
            giver = (NPCS.get(sqd["giver"]) or ALL_WILD.get(sqd["giver"]) or {}).get("name", "？")
            st = sq.get("status", "active")
            obj = sqd["objective"]
            # v95.12：已交付支线显示已完成（不占可交付位）
            if st == "done":
                lines.append(f"{i:>2}. 『{sqd['name']}』[✅ 已完成]")
                continue
            # v127.7 排版：任务名单独一行（名字+状态），描述缩进下一行，目标进度行统一再缩进
            # v116 §3.4：进行中支线可放弃（主线不可弃），放弃提示统一放面板底部（v123e 去行尾冗余）
            # 收集型：实时按背包材料判断（v104 补测：复合目标同时显示击杀进度防误导）
            if obj.get("collect"):
                have = db.count_item(group_id, qq_id, obj["collect"])
                need = obj.get("collect_count") or obj.get("count", 1)  # v125.1 P2：s64 等 collect_count 无 count 的复合目标不再 KeyError
                prog = sq.get("progress", {})
                kill_txt = ""
                if obj.get("kill"):
                    kv = _kill_prog_count(obj, prog)  # v105 M19 P2：兼容旧档老 key 聚合
                    kill_txt = f"｜击杀：{kv}/{obj.get('count', 0)}"
                if have >= need:
                    lines.append(f"{i:>2}. 『{sqd['name']}』[✅ 可交{kill_txt}]")
                    lines.append(f"    {sqd['desc']}")
                    lines.append(f"    材料已齐！回去找 {giver} {_WC._deliver_hint(shell, sqd['giver'])}")
                else:
                    lines.append(f"{i:>2}. 『{sqd['name']}』[⏳{kill_txt}]")
                    lines.append(f"    {sqd['desc']}")
                    lines.append(f"    收集：{obj['collect']} {have}/{need}{kill_txt}")
                # v125.1 P2：复合目标（collect+use/find/explore，如 s53/s56/s64/s105）
                # 补显其余目标行，与 find/use 分支的 _obj_text_lines 展示口径一致
                # （收集/击杀行已在上方展示，过滤避免重复）
                for _t in _WC._obj_text_lines(shell, obj, st):
                    if _t.startswith(("收集", "击败")):
                        continue
                    lines.append(f"    {_t}")
                continue
            # v104 M20 P2：find 型（告示委托等）面板提示机制——在 XX 探索有概率遇到
            # （此前走通用兜底只显示 desc+[⏳]，玩家不知如何推进）
            if obj.get("find"):
                lines.append(f"{i:>2}. 『{sqd['name']}』[{'✅ 可交' if st == 'ready' else '⏳'}]")
                lines.append(f"    {sqd['desc']}")
                # v124.2 复合目标逐行显示（s18 kill+find 两行都展示）
                for _t in _WC._obj_text_lines(shell, obj, st):
                    lines.append(f"    {_t}")
                if st == "ready":
                    lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd['giver'])}")
                continue
            # v124 use 型（使用指定物品达成）——同 find 处理
            if obj.get("use"):
                lines.append(f"{i:>2}. 『{sqd['name']}』[{'✅ 可交' if st == 'ready' else '⏳'}]")
                lines.append(f"    {sqd['desc']}")
                for _t in _WC._obj_text_lines(shell, obj, st):
                    lines.append(f"    {_t}")
                if st == "ready":
                    lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd['giver'])}")
                continue
            mark = "✅ 可交" if st == "ready" else "⏳"
            lines.append(f"{i:>2}. 『{sqd['name']}』[{mark}]")
            lines.append(f"    {sqd['desc']}")
            if st == "ready":
                lines.append(f"    回去找 {giver} {_WC._deliver_hint(shell, sqd['giver'])}")
        # v127.7 翻页提示补全：上一页/下一页 + 总页数（此前只有下一页）
        if pages > 1:
            _nav = []
            if page > 1:
                _nav.append(f"『任务 {page-1}』上一页")
            if page < pages:
                _nav.append(f"『任务 {page+1}』下一页")
            lines.append(f"💡 {' | '.join(_nav)}(共 {pages} 页)")
        shell._record_list_state(qq_id, "任务", page, pages)
    else:
        lines.append("")
        lines.append("【支线】暂无——找镇上的 NPC 聊聊可能有意外收获")
    # 每日
    # v116 §3.4：daily 含 _completed/_repeat 元数据（active 任务清空后仍在）——
    # 只剩元数据 = 今日全部完成，按"已完成"分支展示；_completed 超额时给出计数。
    # v127.7：玩家从未领取（daily 为空）→ 提示『每日』领取，不再误报"已完成"。
    daily = quests.get("daily", {})
    active_keys = [k for k in daily if k not in _DAILY_META_KEYS]
    if active_keys:
        lines.append("")
        lines.append(T.static("daily.section"))
        _daily_n = 0  # v116 每日任务序号（仅计实际任务，跨元数据）
        for dkey, dq in daily.items():
            if dkey in _DAILY_META_KEYS:  # 跨天/计数元数据，跳过
                continue
            _daily_n += 1
            # v125.1 P2：序号用 _daily_n（仅计实际任务）——原用 enumerate 的 i 会把
            # _date/_completed/_repeat 元数据占位算进去（面板显示 4./5.，『放弃』按 1..N 对不上）
            need = _svc("daily_need")(dq)
            # v127.7 排版：每日任务名单独一行，描述缩进下一行
            if need is None:
                # v125.1 P2：无达标数定义时只显示实际进度，不再兜底假 99
                lines.append(T.text("daily.item", n=_daily_n, name=dq["name"]))
                lines.append(T.text("daily.item_plain", desc=dq["desc"],
                                    prog=dq.get("progress", 0)))
            else:
                lines.append(T.text("daily.item", n=_daily_n, name=dq["name"]))
                lines.append(T.text("daily.item_progress", desc=dq["desc"],
                                    prog=dq.get("progress", 0), need=need))
    else:
        lines.append("")
        if not daily:
            # v127.7 修复：从未领取（新号/跨天清空）→ 引导领取，不显示"已完成"
            lines.append(T.static("daily.never"))
        else:
            _done = int(daily.get("_completed", 0) or 0)
            if _done >= _svc("DAILY_LIMIT"):
                lines.append(T.text("daily.done_full", done=_done, limit=_svc("DAILY_LIMIT")))
            else:
                lines.append(T.text("daily.done_part", done=_done))
    # v101.30d #O1：师门考验追踪——对话树进行中时面板显示（playtest 小红：考验无面板条目）
    _MASTER_IDS = ("npc_herb_master", "npc_mine_master", "npc_fish_master", "npc_cook_master",
                   "npc_alchemy_master", "npc_craft_master", "npc_enhance_master", "npc_rune_master")
    ts = db.get_talk_state(group_id, qq_id)
    # ★ U1-I4 L6：`ts and ts.get("npc")` → `(ts or {}).get("npc")`（同值；空会话/无会话都落 None），
    #   导师行取用换引擎 `Lookup(NPCS).first(...)`（真值链，与原 `.get(id) or {}` 同口径）。
    _master = (ts or {}).get("npc")
    if _master in _MASTER_IDS:
        _tnpc = _NPCS_LOOKUP.first(_master)[0] or {}
        lines.append("")
        lines.append("【师门考验】")
        lines.append(f"  ⏳ 正在接受【{_tnpc.get('name', '导师')}】的拜师考验，回复『继续』接着进行")
    lines.append("")
    # v127.1 每面板只抽 1 条随机提示（v123e 放弃/接取引导并入随机池）
    lines.append(shell._tip("quest"))
    return lines


# ============================================================
# ④ 其余 35 条：既有实现在 `content/world_cmds.py`，本模块只做「守卫 + 取参 + 登记」
# ============================================================
# 形参口径 = 宿主改造前逐条调用点（`_WC.<名>(self, event[, group_id, qq_id[, player]])`）。
