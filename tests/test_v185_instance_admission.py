#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v185 副本准入链搬到引擎 —— 内容侧**逐格一致**门禁（路线图 #8）。

搬形状最容易出的错不是崩溃，是**语义漂移**：某条规则少判一次、顺序换了、
措辞被"顺手统一"、副作用从链尾跑回链中段。所以本门禁不看代码，只看**输出**：

  ① 把 v185 之前的**四处手写 if 链逐字冻结**在本文件里（`_old_*`），并给出旧源码
     位置（文件:行号）+ 片段 sha256：测试自检 sha（防后来人偷改冻结体），
     再与 `git show <rev>:<file>` 的旧源码交叉校验（片段确实逐字来自旧源码）；
  ② **27 个真实副本（C.INSTANCES）× 21 场景矩阵**逐格比对
     `(ok, rule, reason)` 与解析出的成员列表（开本链）；其中 ⑰–㉑ 是**多故障场景**，
     专门钉住「谁先拒」＝链顺序（单故障场景看不出顺序漂移，实测踩过）；
  ③ 徒步进图链（world `_instance_gate_block`，真调方法）/ 加入战斗链 / 恢复旧进度链
     各自逐格比对；
  ④ ★ **白扣反证（有意差异 D1）**：位置拒绝 / 体力拒绝时旧实现已把开本钥匙扣走，
     新链不扣 —— 断言新行为 `drop_key` 未被调用，并留下旧行为证据；
  ⑤ 真实 DB 端到端：真调『副本 <名字>』『加入战斗』，断言提示文案逐字一致与钥匙扣减行为。

跑法：python tests/test_v185_instance_admission.py（exit=0 全绿）
"""
import copy
import hashlib
import inspect
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
_HERE = _paths.TESTS_DIR            # 包内 tests/ 本身（旧 `_HERE`）
_PD = _paths.HOST_ROOT              # 宿主插件根（旧插件根语义；旧源码 git 交叉校验的仓库根）

from _engine_harness import C, db, clean_db, Main, FakeEvent, run  # noqa: E402
from content.flow import instance_gate  # noqa: E402

# ★ P5D-REPOINT（宿主独有取数口 + 文案面接线）
# 1) `find_instance_key_item(group_id, qq_id, key_item)` / `instance_cleared_qq(group_id, qq_id,
#    inst_key)` 是**宿主独有**（DB 取数）签名，真源住在 `game/core/instance_gate.py`，随 game/**
#    退役。包内对应物是**纯函数** `find_instance_key_item(inventory, key_item, items=None)` /
#    `instance_cleared(achievements, inst_key)`（判定本体同一份）。这里按宿主壳**逐行同义**
#    补上取数适配（背包 = `db.get_inventory`、成就 = `db.get_achievements`、`items` = 包内 ITEMS），
#    并挂回模块名 —— 门禁调用点与断言语义一字未改。
# 2) 包内链按**模块全局名**调 12 个 `text_*` 文案函数（宿主壳 `_bind_text_funcs()` 的猴补面）。
#    终态无宿主壳 ⇒ 本文件提供 `_bind_text_funcs()`（读本模块同名属性回挂到包内全局），
#    并在每个链入口前调用；`tests/test_v185_gate_teeth.py` 的猴补破坏法据此仍然有牙。
_TEXT_FUNCS = ("stamina_short_msg", "text_party_need", "text_leader_only", "text_too_few",
               "text_too_many", "text_member_no_char", "text_member_level", "text_member_dead",
               "text_member_in_battle", "text_member_prof_wait", "text_key_seal",
               "text_walk_deny")


def _bind_text_funcs() -> None:
    """把本模块当前的 12 个文案函数属性回挂到包内模块全局（幂等；等价宿主壳同名函数）。"""
    for _n in _TEXT_FUNCS:
        _f = globals().get(_n)
        if _f is not None:
            setattr(instance_gate, _n, _f)


# 包内文案表接线（≡ 宿主壳 `_G.set_text_table(T.table())`；真源 = 包内 content/data/text_specs.json）
from content import texts as _TXT  # noqa: E402
from content import obs as _obs  # noqa: E402
instance_gate.set_text_table(_TXT.table())
_TXT.bind_log(_obs.log())
_bind_text_funcs()

#: 包内 ITEMS（≡ 宿主壳 `game.content.ITEMS` 取件）
from content.catalog_items import ITEMS as _PKG_ITEMS  # noqa: E402

#: ★ 先把包内**纯函数**真身存下来（挂回模块名之后不能再按属性取，否则自递归）
_PKG_FIND_KEY = instance_gate.find_instance_key_item
_PKG_CLEARED = instance_gate.instance_cleared


def find_instance_key_item(*args, **kwargs):
    """宿主独有**取数口**适配（逐行等价 `game/core/instance_gate.py::find_instance_key_item`）。

    ★ P5D 越界登记（host 侧缺陷，本线不改 `host/**`）：`host/shell.py:235` 的
    `_instance_gate_block` 按包内**纯函数**形状调用本符号
    （`gate.find_instance_key_item(inventory, key_item, items=…)`），而宿主壳原签名是
    `(group_id, qq_id, key_item)`；删壳期还有第三方调用者按 2 参调用。本适配把三种形状
    都归一：
      · `(group_id, qq_id, key_item)`        —— 门禁调用点（宿主取数语）
      · `(inventory, key_item)`              —— 包内纯函数形状（无 items）
      · `(inventory, key_item, items=…)`     —— 包内纯函数形状（带 items，`host/shell.py`）
    首参是 list ⇒ 已是背包条目表 ⇒ 直接透传包内纯函数；否则按宿主取数口语义查库。
    判据零改动；详见 `W-P5D.md`「未解决项」。
    """
    items = kwargs.get("items")
    pos = list(args)
    if pos and isinstance(pos[0], (list, tuple)):
        inv = pos[0]
        key = pos[1] if len(pos) > 1 else kwargs.get("key_item")
        return _PKG_FIND_KEY(
            inv or [], key, items=items if items is not None else _PKG_ITEMS)
    gid = pos[0] if len(pos) > 0 else kwargs.get("group_id")
    qid = pos[1] if len(pos) > 1 else kwargs.get("qq_id")
    key = pos[2] if len(pos) > 2 else kwargs.get("key_item")
    return _PKG_FIND_KEY(
        db.get_inventory(gid, qid) or [], key, items=_PKG_ITEMS)


def instance_cleared_qq(group_id, qq_id, inst_key):
    """宿主独有取数口（逐行等价 `game/core/instance_gate.py::instance_cleared_qq`）。"""
    return _PKG_CLEARED(db.get_achievements(group_id, qq_id) or [], inst_key)


# 把两个宿主独有取数口挂回**模块名**（门禁调用点是 `instance_gate.find_instance_key_item(...)`）
instance_gate.find_instance_key_item = find_instance_key_item
instance_gate.instance_cleared_qq = instance_cleared_qq

passed = failed = 0
cells = 0          # 逐格比对（单元格）计数


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def _norm(text):
    """冻结比对用的规范化：逐行去尾空白、去掉首尾空行。"""
    return "\n".join(ln.rstrip() for ln in (text or "").splitlines()).strip("\n")


def _sha(text):
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# 一、旧源码片段（逐字冻结；sha256 自检 + git 交叉校验）
#    rev = HEAD 7012403321daba83ad37645a466ac260dbe03c37（v185 改动前的最后一次提交）
# ══════════════════════════════════════════════════════════════════════════
OLD_REV = "7012403321daba83ad37645a466ac260dbe03c37"

# game/commands/instance.py:2099-2243 开本链（队伍解析 → 全队检查 → 钥匙(扣) → 入口 → 体力(扣)）
OLD_SRC_OPEN = r"""        min_players = inst.get("min_players", 2)
        max_players = inst.get("max_players", 3)
        # 纯单人副本：无需组队，直接以自己开本
        if min_players <= 1 and max_players <= 1:
            members = [qq_id]
        else:
            members = db.party_members(group_id, qq_id)
            if not members:
                if min_players <= 1:
                    # v101.24 弹性副本（如哥布林营地 1-2 人）：无队可单人进
                    members = [qq_id]
                else:
                    yield event.plain_result(
                        f"『{inst['name']}』需要 {min_players}-{max_players} 人组队！先『组队 <对方名字>』～"
                    )
                    return
            else:
                if str(members[0]) != str(qq_id):
                    yield event.plain_result("只有队长才能开启副本！让队长来『副本 <名字>』吧～")
                    return
                if len(members) < min_players:
                    yield event.plain_result(
                        f"『{inst['name']}』至少需要 {min_players} 人！还差 {min_players - len(members)} 个队友，让队长『组队 <名字>』拉人～"
                    )
                    return
                if len(members) > max_players:
                    yield event.plain_result(
                        f"『{inst['name']}』最多 {max_players} 人！当前 {len(members)} 人太多了～"
                    )
                    return
        # 全队等级 / 战斗检查
        for m in members:
            p = self._player(group_id, m)
            if not p:
                yield event.plain_result("队友还没有角色！无法开本～")
                return
            if p["level"] < inst["lv"]:
                yield event.plain_result(
                    f"{p['name']} 才 Lv.{p['level']}，副本需要全队 Lv.{inst['lv']}+！"
                )
                return
            # v101.27 #393：0 血进本拦截——0 血被碰即倒体验极差，先恢复再来
            if int(p.get("hp", 0)) <= 0:
                yield event.plain_result(
                    f"💀 {p['name']} 生命值为 0！先去住宿或用药恢复，别拿命闯副本～"
                )
                return
            if self._in_battle(group_id, m):
                # v101.30d #O17：拦截时补队伍构成（playtest 影刃/小四：只报名字不知队伍现状）
                roster = "、".join(
                    (self._player(group_id, mm) or {}).get("name", mm) for mm in members
                )
                yield event.plain_result(
                    f"{p['name']} 正在战斗中，先打完再来！\n👥 当前队伍：{roster}（队友打完即可开本）"
                )
                return
            # v104 M04 P2：队员等待型副业（垂钓/采集/挖掘）中开本——此前无任何提示，
            # 队员被拉进副本锁战斗，等待结束物品照常入包（无死锁但体验突兀）。与
            # no_prof_waiting 对发起者的拦截同规则，对全队生效。
            _pw = self._prof_wait_state(group_id, m)
            if _pw and int(_pw.get("finish", 0)) > int(time.time()):
                _left = int(_pw["finish"]) - int(time.time())
                _pt = C.PROF_WAIT_BASE.get(_pw.get("type"), (0, 0, "副业"))[2]
                yield event.plain_result(
                    f"⏳ {p['name']} 还在{_pt}呢，再有 {_left} 秒完成！等 TA 忙完再开本吧～"
                )
                return
        # v86.3 入场钥匙检查（29 章 11 节）：队长持有 key_item 才能开本
        # v116 副本已通关免钥匙：已通关副本(首通记录 inst_clear_* )再进不扣钥匙、不拦门，
        # 并给出明确提示。判定复用存档成就体系（db.get_achievements），非凭空造存储。
        key_item = inst.get("key_item")
        key_free_note = ""  # 已通关免钥匙提示（有钥匙要求的副本通关过则显示）
        if key_item:
            # v141 审计 #9：钥匙三路匹配 + 通关豁免抽到 core/instance_gate.py
            # （world.py 门禁同源公共函数；开本不放行是设计——开本走完整校验，
            # 有钥匙且未通关才扣钥匙，已通关免钥匙入场）
            from ..core.instance_gate import find_instance_key_item, instance_cleared_qq
            key_entry = find_instance_key_item(group_id, qq_id, key_item)
            has_key = key_entry is not None
            cleared_before = instance_cleared_qq(group_id, qq_id, kid)
            if not has_key and not cleared_before:
                src = inst.get("key_source", "？？？")
                yield event.plain_result(
                    f"🔒 『{inst['name']}』被封印之门挡住！\n"
                    f"需要『{key_item}』才能进入(已通关副本可免钥匙)\n"
                    f"📜 获取途径：{src}"
                )
                return
            # 消耗钥匙（首通前）：已通关副本免钥匙，首通后才不扣
            if has_key and not cleared_before:
                db.remove_item(group_id, qq_id, key_entry["key"])
            else:
                key_free_note = "✅ 已通关副本，免钥匙入场！\n"
        # F2 副本入口设施化：走到入口才能开本（消费 F1 的 entry 字段 + funcs=instance 标记）
        # 兼容红线：entry 为空免校验；已通关免校验；cur_map 已在副本图视为已在入口；
        # 主线/支线 explore 目标 == 本副本图（任务内单人可进图）免校验。
        _entry_cfg = inst.get("entry")
        if _entry_cfg:
            _entry_map = _entry_cfg.get("map")
            _entry_sa = _entry_cfg.get("subarea")
            _leader_p = self._player(group_id, qq_id)
            _ok_pos = True
            if _entry_map and _entry_sa:
                _ok_pos = (str(_leader_p.get("cur_map") or "") == str(_entry_map)
                           and str(_leader_p.get("cur_subarea") or "") == str(_entry_sa))
                # 兼容红线：存量玩家 cur_map 已在副本图（旧存档徒步进图）→ 视为已在入口
                if not _ok_pos and str(_leader_p.get("cur_map") or "") == _inst_map_id(kid):
                    _ok_pos = True
            if not _ok_pos:
                # 兼容红线：已通关该副本 → 免位置校验（老玩家便利）
                from ..core.instance_gate import instance_cleared_qq
                _cleared = instance_cleared_qq(group_id, qq_id, kid)
                if not _cleared:
                    # 兼容红线：主线/支线 explore 目标 == 本副本图 → 任务内单人可进图，免校验
                    _quests = db.get_quests(group_id, qq_id)
                    _in_quest = False
                    if _quests.get("main_status") == "active":
                        _mq = next((q for q in C.MAIN_QUESTS if q["id"] == _quests.get("main_quest")), None)
                        if _mq and _mq.get("objective", {}).get("explore") == _inst_map_id(kid):
                            _in_quest = True
                    if not _in_quest:
                        _side = _quests.get("side") or {}
                        if any(
                            sq.get("status") == "active"
                            and next((q for q in C.SIDE_QUESTS if q["id"] == sid), {}).get("objective", {}).get("explore") == _inst_map_id(kid)
                            for sid, sq in _side.items()
                        ):
                            _in_quest = True
                    if not _in_quest:
                        _em_name = C.MAP_BY_ID.get(_entry_map, {}).get("name", _entry_map)
                        _esa_name = ""
                        for _esa in (C.MAP_BY_ID.get(_entry_map, {}).get("subareas") or []):
                            if _esa.get("id") == _entry_sa:
                                _esa_name = _esa.get("name", "")
                                break
                        yield event.plain_result(
                            f"📍 请先到【{_em_name}·{_esa_name or _entry_sa}】副本入口处（『前往』）再开本！\n"
                            f"（副本入口在 {_em_name} 的 {_esa_name or _entry_sa}，走到那里输入『副本 {inst['name']}』）"
                        )
                        return
        # v94 体力：开本消耗 20 体力（全队队长扣）
        _ok, _st = self._spend_stamina(group_id, qq_id, 20, player, "进入副本")
        if not _ok:
            yield event.plain_result(_st)
            return"""
OLD_SHA_OPEN = "667d782fe0c5f6a72945a2926c2757f19b4675ace3a50d3849a6b284e24b648e"

# game/commands/instance.py:318-337 恢复旧进度的人数/等级/0血/战斗中四连
OLD_SRC_RESUME = r"""                # 人数/等级重校验（与 _instance_start 同规则）
                min_players = inst.get("min_players", 2)
                max_players = inst.get("max_players", 3)
                valid = len(ok_members) >= min_players and len(ok_members) <= max_players
                if valid:
                    for m in ok_members:
                        p = self._player(group_id, m)
                        if not p or p["level"] < inst.get("lv", 0):
                            valid = False
                            break
                        # v104 M04 P1（N6 复验缺项）：恢复路径补 0 血/战斗检查，
                        # 与 _instance_start 同规则——0 血恢复会进入地图模式后碰怪即倒；
                        # 成员在野外战斗中会被加锁进本（双线战斗）。不通过则放弃旧进度，
                        # 落到 _instance_start 输出对应拦截提示。
                        if int(p.get("hp", 0)) <= 0:
                            valid = False
                            break
                        if self._in_battle(group_id, m):
                            valid = False
                            break"""
OLD_SHA_RESUME = "3ab4d3400cebf1e31d38a704951d83f48211e7d2492a2164735164e9a362ecff"

# game/commands/instance.py:101-156 『加入战斗』四条（队伍/队员视角/战斗状态/重复/满员/敌灭/0血）
OLD_SRC_JOIN = r"""        # 1. 同队伍校验：无队 → 拒绝
        members = db.party_members(group_id, qq_id)
        if not members:
            yield event.plain_result("你还没有队伍！先『组队 <对方名字>』拉上队友，再一起并肩作战～")
            return
        if str(members[0]) != new_key:
            # 队员视角：目标战斗 = 队长名下（副本 battle 存队长行）
            leader_key = str(members[0])
            battle_row = db.get_battle(group_id, leader_key)
            if not battle_row or battle_row["state"].get("type") != "instance":
                yield event.plain_result("附近没有可加入的战斗！让队长先在副本中遇怪开战吧～")
                return
            st = battle_row["state"]
            # 2a. 地理校验：队员在副本中（副本是封闭地图，野外玩家不能跨图加入）。
            #     队员自己的 battle 行不存在（副本战斗存队长名下），用 _instance_battle_for
            #     反查（party 表 → 队长行）；再比对 inst_id 防跨副本串台。
            inst_row_self = self._instance_battle_for(group_id, qq_id)
            if not inst_row_self or inst_row_self["state"].get("inst_id") != st.get("inst_id"):
                yield event.plain_result("副本是封闭区域——先进入副本（队长『副本 <名字>』开本）才能加入战斗！")
                return
        else:
            # 队长视角：自己开本遇怪 → 自己就是战斗；无需再加入（上面已拦）
            yield event.plain_result("你就是这场战斗的队长！『攻击』『技能 <名称>』『防御』行动～")
            return
        # 3. 战斗状态校验
        if st.get("over") or st.get("cleared"):
            yield event.plain_result("这场战斗已经结束了！")
            return
        if st.get("retreated"):
            yield event.plain_result("这场战斗已经撤退了！")
            return
        if st.get("type") != "instance":
            yield event.plain_result("这个战斗不支持加入！")
            return
        players = st.setdefault("players", {})
        # 3a. 重复加入：已在 st["players"] → 拒绝（幂等）
        if new_key in players:
            yield event.plain_result("你已在战斗中！『攻击』『技能 <名称>』『防御』行动～")
            return
        # 3b. 满员：len(members) >= 4 → 拒绝（与队伍上限对齐）
        if len(st.get("members") or []) >= 4:
            yield event.plain_result("战斗满员了（4 人）！")
            return
        # 3c. 敌方已全灭（残局无怪）→ 拒绝（无敌人可打）
        if not self._instance_enemies_alive(st):
            yield event.plain_result("这场战斗的敌人已经全部倒下！没有可加入的战斗了～")
            return
        # 3d. 0 血 → 拒绝（与开本 0 血拦截同规则）
        if int(player.get("hp", 0) or 0) <= 0:
            yield event.plain_result("💀 你生命值为 0！先去住宿或用药恢复，别拿命加入战斗～")
            return
        # 4. 构造新玩家快照（_instance_start 同款：player_final_stats 实时属性 + 站位/单位字段）
        _p = self._player(group_id, qq_id)
        if not _p:
            yield event.plain_result("你的角色数据异常，无法加入战斗！")
            return"""
OLD_SHA_JOIN = "a9e626351529299a2e2921f50b0f8038a9b80e67c998ca015daef76f03770b4b"

# game/commands/world.py:1260-1282 徒步进图三档（任务放行 → 持钥匙 → 已通关豁免）
OLD_SRC_WALK = r"""        # 1) 任务内进入：active 主线或支线 explore 目标 == 本副本图 → 放行
        quests = db.get_quests(group_id, qq_id)
        if quests.get("main_status") == "active":
            mq = next((q for q in C.MAIN_QUESTS if q["id"] == quests.get("main_quest")), None)
            if mq and mq["objective"].get("explore") == kid:
                return ""
        side = quests.get("side") or {}
        if any(sq.get("status") == "active"
               and next((q for q in C.SIDE_QUESTS if q["id"] == sid), {}).get("objective", {}).get("explore") == kid
               for sid, sq in side.items()):
            return ""
        # 2) 持有钥匙（与 instance.py 开本钥匙判定同源，抽公共 core/instance_gate.py）
        from ..core.instance_gate import find_instance_key_item
        key_item = (inst or {}).get("key_item")
        if key_item and find_instance_key_item(group_id, qq_id, key_item) is not None:
            return ""
        # 3) 已通关副本 → 免钥匙放行（与 instance.py 同口径，抽公共 core/instance_gate.py）
        from ..core.instance_gate import instance_cleared_qq
        if instance_cleared_qq(group_id, qq_id, kid):
            return ""
        inst_name = (inst or {}).get("name") or C.MAP_BY_ID.get(kid, {}).get("name", "副本")
        return (f"🔒 此处为【{inst_name}】入口，需接取相应任务（或持有钥匙）才能进入。\n"
                f"{self._tip('instance')}；或先完成任务、收集所需钥匙～")"""
OLD_SHA_WALK = "c8ba34c01415acc28030bdc6fc60b6b66d7471ef8f7f5120674b99e3ad974d86"

# game/commands/base.py:482-487 体力不足三行措辞
OLD_SRC_STAMINA = r"""        if cur < cost:
            return False, (
                f"😮‍💨 体力不足！{action}需要 {cost} 点体力，你只有 {cur} 点。\n"
                f"🍖 吃点食物(『烹饪』/『使用 <食物>』)或去旅店『住宿』恢复体力～\n"
                f"💡 体力每 1 分钟自然恢复 1 点(上限 100+等级×2)，『防御』不耗体力可拖延时间～"
            )"""
OLD_SHA_STAMINA = "552f577ea16d969c602489e36f80eac873cb1a57e28f9684698678d0d3e6764c"

# 冻结体所在文件（git 交叉校验用）：{路径: [(片段, 冻结 sha)]}
_OLD_SOURCES = {
    "game/commands/instance.py": [
        (OLD_SRC_OPEN, OLD_SHA_OPEN),
        (OLD_SRC_RESUME, OLD_SHA_RESUME),
        (OLD_SRC_JOIN, OLD_SHA_JOIN),
    ],
    "game/commands/world.py": [(OLD_SRC_WALK, OLD_SHA_WALK)],
    "game/commands/base.py": [(OLD_SRC_STAMINA, OLD_SHA_STAMINA)],
}

# 冻结决策函数的源 sha（防偷改 `_old_*` 函数体；见 t0_freeze_self_check）
FROZEN_SHA = {
    "_old_open_decision": "81d49f3f36b8eb25d276f3a2d8350674c92b04c3f5e0c757ac5cf7d22eecff77",
    "_old_resume_decision": "666cd65dcfc4d2398c34defe32ff6ad4f74dff2cdb7dc440942359885b7e20d0",
    "_old_join_decision": "67f2a4ef5244604453a0fc98e69518ddbaa3f2d101e3a5f427385b467d673f93",
    "_old_walk_decision": "fcaa3a36f2bdca4b54a6dbe207ad0c65e455f723515922102c71da803c28fbed",
    "_old_entry_hint": "505cd1d0643186e66e4a90d760494b9e04efbd99b8e1466c797d796ed333b2eb",
    "_old_stamina_msg": "d9bd06ed7dc45eaa46cb77fc287ce0e6450cae65b26f9c5f19dac811a06f568f",
}


# ══════════════════════════════════════════════════════════════════════════
# 二、冻结：v185 之前的**判定逻辑**（逐字搬自上面五个旧源码片段，勿改）
#    旧源码是 async generator（yield + return），此处剥成纯函数以便逐格比对；
#    条件表达式、判断顺序、f-string 措辞与旧源码逐字相同。
# ══════════════════════════════════════════════════════════════════════════
def _old_stamina_msg(cost, cur, action="行动"):
    """冻结：base.py:483-487 体力不足三行措辞（旧实现就写在 `_spend_stamina` 里）。"""
    return (
        f"😮‍💨 体力不足！{action}需要 {cost} 点体力，你只有 {cur} 点。\n"
        f"🍖 吃点食物(『烹饪』/『使用 <食物>』)或去旅店『住宿』恢复体力～\n"
        f"💡 体力每 1 分钟自然恢复 1 点(上限 100+等级×2)，『防御』不耗体力可拖延时间～"
    )


def _old_entry_hint(inst, map_name, subarea_name, subarea_id):
    """冻结：instance.py:2234-2237 入口位置提示（`_sa = name or id` 回退口径）。"""
    _sa = subarea_name or subarea_id
    return (
        f"📍 请先到【{map_name}·{_sa}】副本入口处（『前往』）再开本！\n"
        f"（副本入口在 {map_name} 的 {_sa}，走到那里输入『副本 {inst['name']}』）"
    )


def _old_open_decision(inst, my_key, sim):
    """冻结：开本链旧实现（instance.py:2099-2243）。

    返回 `(ok, rule, reason, members)`。规则名按新链口径命名（"party" /
    "member:<key>" / "key" / "entry" / "stamina"），于是两边的「首个拒绝位置」
    可以直接对齐比较。

    sim 提供：party / player_of / in_battle / prof_wait / prof_label / now /
    find_key / cleared / entry_ok / quest_exempt / entry_hint / stamina /
    stamina_msg / drop_key。
    入口位置的**三条兼容红线**（entry 配置读取 / cur_map 已在副本图 / 已通关免校验 /
    任务 explore 放行）在本轮重构中**逐字留在原位**，故此处由 sim 的
    `entry_ok`（已含三红线的**放行**结果）/ `cleared` / `quest_exempt` 提供，
    冻结体只钉「拒绝顺序 + 措辞」。
    """
    min_players = inst.get("min_players", 2)
    max_players = inst.get("max_players", 3)
    # 纯单人副本：无需组队，直接以自己开本
    if min_players <= 1 and max_players <= 1:
        members = [my_key]
    else:
        members = sim["party"]
        if not members:
            if min_players <= 1:
                members = [my_key]
            else:
                return (False, "party",
                        f"『{inst['name']}』需要 {min_players}-{max_players} 人组队！先『组队 <对方名字>』～", [])
        else:
            if str(members[0]) != str(my_key):
                return (False, "party", "只有队长才能开启副本！让队长来『副本 <名字>』吧～", members)
            if len(members) < min_players:
                return (False, "party",
                        f"『{inst['name']}』至少需要 {min_players} 人！还差 {min_players - len(members)} 个队友，让队长『组队 <名字>』拉人～",
                        members)
            if len(members) > max_players:
                return (False, "party",
                        f"『{inst['name']}』最多 {max_players} 人！当前 {len(members)} 人太多了～", members)
    # 全队等级 / 战斗检查
    for m in members:
        p = sim["player_of"](m)
        if not p:
            return (False, f"member:{m}", "队友还没有角色！无法开本～", members)
        if p["level"] < inst["lv"]:
            return (False, f"member:{m}",
                    f"{p['name']} 才 Lv.{p['level']}，副本需要全队 Lv.{inst['lv']}+！", members)
        if int(p.get("hp", 0)) <= 0:
            return (False, f"member:{m}",
                    f"💀 {p['name']} 生命值为 0！先去住宿或用药恢复，别拿命闯副本～", members)
        if sim["in_battle"](m):
            roster = "、".join((sim["player_of"](mm) or {}).get("name", mm) for mm in members)
            return (False, f"member:{m}",
                    f"{p['name']} 正在战斗中，先打完再来！\n👥 当前队伍：{roster}（队友打完即可开本）", members)
        _pw = sim["prof_wait"](m)
        if _pw and int(_pw.get("finish", 0)) > int(sim["now"]):
            _left = int(_pw["finish"]) - int(sim["now"])
            _pt = sim["prof_label"](_pw.get("type"))
            return (False, f"member:{m}",
                    f"⏳ {p['name']} 还在{_pt}呢，再有 {_left} 秒完成！等 TA 忙完再开本吧～", members)
    # 入场钥匙检查
    key_item = inst.get("key_item")
    if key_item:
        key_entry = sim["find_key"](key_item)
        has_key = key_entry is not None
        cleared_before = sim["cleared"]
        if not has_key and not cleared_before:
            src = inst.get("key_source", "？？？")
            return (False, "key",
                    f"🔒 『{inst['name']}』被封印之门挡住！\n"
                    f"需要『{key_item}』才能进入(已通关副本可免钥匙)\n"
                    f"📜 获取途径：{src}", members)
        # ★ 旧实现：这里就把钥匙扣走了（instance.py:2187-2191）——D1 白扣来源
        if has_key and not cleared_before:
            sim["drop_key"]()
    # 入口位置（三红线见 docstring）
    if not sim["entry_ok"]:
        if not sim["cleared"]:
            if not sim["quest_exempt"]:
                return (False, "entry", sim["entry_hint"], members)
    # 体力（旧实现在此才扣；不足则拒）
    if int(sim["stamina"]) < 20:
        return (False, "stamina", sim["stamina_msg"](20, int(sim["stamina"]), "进入副本"), members)
    return (True, None, "", members)


def _old_resume_decision(inst, ok_members, sim):
    """冻结：恢复旧进度的四连（instance.py:318-337）。

    ★ 旧实现**不查副业等待**、不查钥匙/位置/体力 —— 与开本链的差别在门禁里钉住。
    """
    min_players = inst.get("min_players", 2)
    max_players = inst.get("max_players", 3)
    valid = len(ok_members) >= min_players and len(ok_members) <= max_players
    if valid:
        for m in ok_members:
            p = sim["player_of"](m)
            if not p or p["level"] < inst.get("lv", 0):
                valid = False
                break
            if int(p.get("hp", 0)) <= 0:
                valid = False
                break
            if sim["in_battle"](m):
                valid = False
                break
    return valid


def _old_join_decision(sim):
    """冻结：『加入战斗』四条（instance.py:101-156）。

    返回 `(ok, rule, reason)`。**不含**处理函数最前面的两步（"你还没有角色" 与
    已经战斗中的队长判定，instance.py:89-100）——它们本轮原样留在原位，不属于准入链。
    """
    new_key = sim["my_key"]
    members = sim["party_members"]
    if not members:
        return (False, "party", "你还没有队伍！先『组队 <对方名字>』拉上队友，再一起并肩作战～")
    if str(members[0]) != new_key:
        leader_key = str(members[0])
        battle_row = sim["battle_of_leader"]()
        if not battle_row or battle_row["state"].get("type") != "instance":
            return (False, "has_battle", "附近没有可加入的战斗！让队长先在副本中遇怪开战吧～")
        st = battle_row["state"]
        inst_row_self = sim["self_row"]()
        if not inst_row_self or inst_row_self["state"].get("inst_id") != st.get("inst_id"):
            return (False, "same_inst", "副本是封闭区域——先进入副本（队长『副本 <名字>』开本）才能加入战斗！")
    else:
        return (False, "member_view", "你就是这场战斗的队长！『攻击』『技能 <名称>』『防御』行动～")
    if st.get("over") or st.get("cleared"):
        return (False, "not_over", "这场战斗已经结束了！")
    if st.get("retreated"):
        return (False, "not_retreated", "这场战斗已经撤退了！")
    if st.get("type") != "instance":
        return (False, "is_instance", "这个战斗不支持加入！")
    players = st.setdefault("players", {})
    if new_key in players:
        return (False, "not_dupe", "你已在战斗中！『攻击』『技能 <名称>』『防御』行动～")
    if len(st.get("members") or []) >= 4:
        return (False, "not_full", "战斗满员了（4 人）！")
    if not sim["enemies_alive"](st):
        return (False, "enemy_alive", "这场战斗的敌人已经全部倒下！没有可加入的战斗了～")
    if int((sim["player"] or {}).get("hp", 0) or 0) <= 0:
        return (False, "hp", "💀 你生命值为 0！先去住宿或用药恢复，别拿命加入战斗～")
    if not sim["player"]:
        return (False, "profile", "你的角色数据异常，无法加入战斗！")
    return (True, None, "")


def _old_walk_decision(inst_name, quest_open, key_held, cleared, tip):
    """冻结：徒步进图三档（world.py:1260-1282）。返回 "" 放行 / 拦截文案。

    旧实现是「首档命中即 `return ""`」；新链是 `mode='any'` 的同一语义。
    """
    if quest_open:
        return ""
    if key_held:
        return ""
    if cleared:
        return ""
    return (f"🔒 此处为【{inst_name}】入口，需接取相应任务（或持有钥匙）才能进入。\n"
            f"{tip}；或先完成任务、收集所需钥匙～")


# ══════════════════════════════════════════════════════════════════════════
# 三、新实现（内容侧唯一真相源 core/instance_gate.py + 引擎 run.Admission）
# ══════════════════════════════════════════════════════════════════════════
def _open_ctx_of(inst, members, sim):
    """开本链 ctx（与 `_instance_start` 的 ctx 契约逐键同形）。"""
    return {
        "members": members,
        "inst": inst,
        "now": sim["now"],
        "player_of": sim["player_of"],
        "in_battle": sim["in_battle"],
        "prof_wait": sim["prof_wait"],
        "prof_label": sim["prof_label"],
        "key_entry": sim["find_key"](inst.get("key_item")) if inst.get("key_item") else None,
        "cleared": sim["cleared"],
        "entry_ok": sim["entry_ok"],
        "entry_hint": sim["entry_hint"],
        "stamina": sim["stamina"],
        "stamina_cost": 20,
        "drop_key": sim["drop_key"],
        "pay_stamina": sim["pay_stamina"],
    }


def _new_open_decision(inst, my_key, sim):
    """v185 开本链：resolve_open_members + open_admission（与命令层同一套 ctx 契约）。

    ctx 键顺序/取数口径与 `game/commands/instance.py::_instance_start` 完全一致
    （见该函数 v185 段）。`sim["entry_ok"]` 已是命令层三条兼容红线算完的**放行结果**
    （红线是「放行」而非「不拒绝」）。
    """
    _bind_text_funcs()
    members, deny = instance_gate.resolve_open_members(inst, my_key, sim["party"])
    if deny:
        return (False, "party", deny, members)
    ctx = _open_ctx_of(inst, members, sim)
    v = instance_gate.open_admission(ctx).check(ctx)
    if v.ok:
        return (True, None, "", members)
    return (False, v.rule, v.reason, members)


def _new_resume_decision(inst, ok_members, sim):
    ctx = {
        "members": ok_members,
        "inst": inst,
        "now": sim["now"],
        "player_of": sim["player_of"],
        "in_battle": sim["in_battle"],
    }
    v = instance_gate.resume_admission(ctx).check(ctx)
    return v.ok


def _new_join_decision(sim):
    ctx = {
        "party_members": sim["party_members"],
        "my_key": sim["my_key"],
        "battle_of_leader": sim["battle_of_leader"],
        "self_inst_id": sim["self_inst_id"],
        "enemies_alive": lambda: sim["enemies_alive"](ctx.get("st") or {}),
        "player": sim["player"],
    }
    v = instance_gate.join_admission(ctx).check(ctx)
    if v.ok:
        return (True, None, "")
    return (False, v.rule, v.reason)


# ══════════════════════════════════════════════════════════════════════════
# 四、场景模拟器（同一份 sim 同时喂给旧冻结体与新链）
# ══════════════════════════════════════════════════════════════════════════
NOW = 1000000  # 固定「当前时刻」，让副业等待的剩余秒数确定


def _entry_names(inst):
    """入口图/子区域名（旧实现取名字的那三行：instance.py:2228-2233）。"""
    cfg = inst.get("entry") or {}
    em, esa = cfg.get("map"), cfg.get("subarea")
    mp = C.MAP_BY_ID.get(em, {})
    em_name = mp.get("name", em)
    esa_name = ""
    for s in (mp.get("subareas") or []):
        if s.get("id") == esa:
            esa_name = s.get("name", "")
            break
    return em_name, esa_name, esa


def _party_for(inst, my_key="1"):
    """该副本「刚好够人数」的队伍（纯单人/弹性副本 → 单元素）。"""
    minp = inst.get("min_players", 2)
    maxp = inst.get("max_players", 3)
    n = 1 if maxp <= 1 else max(2, int(minp))
    return [my_key] + [str(i + 2) for i in range(n - 1)]


def _members_of(inst, party, my_key="1"):
    """本次判定实际参战的成员（与 resolve_open_members 同口径）。"""
    minp, maxp = inst.get("min_players", 2), inst.get("max_players", 3)
    if minp <= 1 and maxp <= 1:
        return [my_key]
    if not party:
        return [my_key] if minp <= 1 else []
    return [str(m) for m in party]


def _mk_sim(inst, my_key, party, *, lv_delta=5, hp=100, in_battle=(), prof=(), now=NOW,
            key_held=True, cleared=False, at_entry=True, cur_map_in_inst=False,
            quest_exempt=False, stamina=100):
    """可观测的场景 sim：成员表 + 战斗/副业/钥匙/通关/位置/体力 + 副作用日志。

    ★ `at_entry` / `cur_map_in_inst` / `cleared` / `quest_exempt` 四条按**命令层旧有序**
      合成 `entry_ok`（红线是「放行」而非「不拒绝」）——该合成逻辑本轮未改，逐字留在
      `instance.py` 原位；`entry_hint` 只在最终仍不放行时才有值。
    """
    need_lv = int(inst.get("lv", 0) or 0)
    keys = set()
    for m in _members_of(inst, party, my_key):
        keys.add(str(m))
    keys.add(my_key)
    keys.update(str(m) for m in party)
    players = {k: {"name": f"玩家{k}", "level": need_lv + lv_delta, "hp": hp} for k in sorted(keys)}
    drops, pays = [], []
    em, esa_name, esa = _entry_names(inst)
    has_entry_cfg = bool((inst.get("entry") or {}).get("map"))
    entry_ok_eff = True if not has_entry_cfg else bool(
        at_entry or cur_map_in_inst or cleared or quest_exempt)
    sim = {
        "party": [str(m) for m in party],
        "now": now,
        "player_of": lambda m: copy.deepcopy(players.get(str(m))),
        "in_battle": lambda m: str(m) in {str(x) for x in in_battle},
        "prof_wait": lambda m: copy.deepcopy(
            next((p for k, p in prof if str(k) == str(m)), None)),
        "prof_label": lambda t: C.PROF_WAIT_BASE.get(t, (0, 0, "副业"))[2],
        "find_key": lambda ki: ({"key": f"item_of:{ki}", "data": {"name": ki}, "count": 1}
                                if key_held else None),
        "cleared": cleared,
        "entry_ok": entry_ok_eff,
        "quest_exempt": quest_exempt,
        "entry_hint": "" if entry_ok_eff else _old_entry_hint(inst, em, esa_name, esa),
        "stamina": stamina,
        "stamina_msg": _old_stamina_msg,
        "drop_key": lambda: drops.append("key"),
        "pay_stamina": lambda: pays.append(20),
        "drops": drops,
        "pays": pays,
    }
    return sim


def _open_scenarios(inst):
    """开本矩阵的 21 个场景（每个副本都跑一遍）。

    ⑰–㉑ 是**故意多故障**的：只坏一处的场景只能证明「判定结果」，证明不了**顺序**——
    成员关挪到钥匙后面、钥匙关挪到入口后面，单故障场景照样全绿（实测踩过）。
    多故障场景把「谁先拒」钉死，链顺序一改即红。
    """
    party = _party_for(inst)
    maxp = inst.get("max_players", 3)
    short = party[:-1] if len(party) > 1 else []
    many = ["1"] + [str(i + 20) for i in range(int(maxp) + 1)]
    return [
        ("①有钥匙正常", dict(party=party, key_held=True)),
        ("②无队", dict(party=[], key_held=True)),
        ("③人少", dict(party=short, key_held=True)),
        ("④人多", dict(party=many, key_held=True)),
        ("⑤非队长", dict(party=["2", "1"], key_held=True)),
        ("⑥等级不足", dict(party=party, key_held=True, lv_delta=-1)),
        ("⑦0 血", dict(party=party, key_held=True, hp=0)),
        ("⑧战斗中", dict(party=party, key_held=True, in_battle=("1",))),
        ("⑨副业等待中", dict(party=party, key_held=True,
                          prof=(("1", {"finish": NOW + 30, "type": "fishing"}),))),
        ("⑩无钥匙未通关", dict(party=party, key_held=False, cleared=False)),
        ("⑪已通关免钥匙", dict(party=party, key_held=False, cleared=True)),
        ("⑫位置不对+持钥匙", dict(party=party, key_held=True, at_entry=False)),
        ("⑬体力不足+持钥匙", dict(party=party, key_held=True, stamina=5)),
        ("⑭已通关+位置不对", dict(party=party, key_held=False, cleared=True, at_entry=False)),
        ("⑮位置不对+任务放行", dict(party=party, key_held=False, at_entry=False, quest_exempt=True)),
        ("⑯位置不对+cur_map 已在副本图", dict(party=party, key_held=False, at_entry=False,
                                      cur_map_in_inst=True)),
        # ★ 多故障：钉住「谁先拒」= 钉住链顺序（单故障场景看不出顺序漂移）
        ("⑰等级不足+无钥匙→先报成员关", dict(party=party, key_held=False, lv_delta=-1)),
        ("⑱0 血+无钥匙→先报成员关", dict(party=party, key_held=False, hp=0)),
        ("⑲无钥匙+位置不对→先报钥匙关", dict(party=party, key_held=False, at_entry=False)),
        ("⑳位置不对+体力不足→先报入口关", dict(party=party, key_held=True, at_entry=False,
                                       stamina=5)),
        ("㉑等级不足+战斗中→同一成员内 等级 先于 战斗", dict(party=party, key_held=True,
                                            lv_delta=-1, in_battle=("1",))),
    ]


# ══════════════════════════════════════════════════════════════════════════
# 五、门禁小节
# ══════════════════════════════════════════════════════════════════════════
def _git_revisions(path, limit=25):
    try:
        out = subprocess.run(["git", "log", f"-n{limit}", "--format=%H", "--", path],
                             cwd=_PD, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60)
    except Exception:
        return []
    if out.returncode != 0:
        return []
    return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]


def _git_show(rev, path):
    try:
        out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=_PD, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=60)
    except Exception:
        return ""
    return out.stdout if out.returncode == 0 else ""


def _git_available() -> bool:
    """本工作副本是否是 git 工作树（沙箱副本无 `.git` ⇒ git 交叉校验不可跑）。

    ★ P5D 环境分支：`_OLD_SOURCES` 的**判据本身不变**（仍是「片段逐字来自旧源码」），
    但其中「与 git 历史交叉校验」这一半需要仓库历史，而作业沙箱的 `work/host` 是**拷贝**
    （无 `.git`，且真仓只读、不跑 git）⇒ 该半判据在此环境不可评估。此时登记「环境受限」
    并跳过那两条断言（片段 sha256 自检仍在，冻结体 sha256 自检仍在）；在有 git 的环境
    里跑则两条断言照旧生效（本函数返回 True）。
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=_PD,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=60)
    except Exception:
        return False
    return out.returncode == 0 and (out.stdout or "").strip() == "true"


def t0_freeze_self_check():
    print("\n[0] 冻结体自检：旧源码片段 sha256 + git 交叉校验 + 冻结函数体 sha256")
    bad = []
    n_src = 0
    for path, items in _OLD_SOURCES.items():
        for src, pin in items:
            n_src += 1
            if _sha(src) != pin:
                bad.append((path, pin[:12], _sha(src)[:12]))
    check(f"★ 旧源码片段 sha256 自检（{n_src} 段）", not bad, str(bad))
    if not _git_available():
        print("    ⏸️  [环境受限] 本工作副本无 git 工作树（`work/host` 是拷贝、真仓只读、"
              "不跑 git）→ 「与 git 历史交叉校验」两条断言不可评估，已登记跳过；"
              "片段 sha256 自检 + 冻结体 sha256 自检仍在，判据本体不变。")
    else:
        git_bad, found = [], []
        for path, items in _OLD_SOURCES.items():
            revs = _git_revisions(path)
            for src, pin in items:
                hit = next((r for r in revs if _norm(src) in _norm(_git_show(r, path))), None)
                if hit:
                    found.append((path, hit[:8]))
                else:
                    git_bad.append((path, pin[:12]))
        for path, rev in sorted(found):
            print(f"    · {path}: 旧片段逐字命中 revision {rev}")
        check("★ 旧源码片段与 git 历史逐字一致（片段确实来自旧源码）", not git_bad, str(git_bad))
        check(f"★ {n_src} 段旧源码都被 git 历史交叉验证（{len(found)}/{n_src}）",
              len(found) == n_src, str(found))
    fbad = []
    for fn_name, pin in FROZEN_SHA.items():
        fn = globals().get(fn_name)
        if fn is None:
            fbad.append((fn_name, "函数不存在"))
            continue
        got = _sha(inspect.getsource(fn))
        if got != pin:
            fbad.append((fn_name, pin[:12], got[:12]))
    check(f"★ 冻结函数体 sha256 自检（{len(FROZEN_SHA)} 个 `_old_*`，改冻结体即红）",
          not fbad, str(fbad))
    miss = []
    for phrase, holder in (("只有队长才能开启副本！让队长来", OLD_SRC_OPEN),
                           ("人组队！先『组队 <对方名字>』～", OLD_SRC_OPEN),
                           ("你还没有队伍！先『组队 <对方名字>』拉上队友", OLD_SRC_JOIN),
                           ("这场战斗已经撤退了！", OLD_SRC_JOIN),
                           ("需接取相应任务（或持有钥匙）才能进入", OLD_SRC_WALK),
                           ("体力每 1 分钟自然恢复 1 点", OLD_SRC_STAMINA)):
        if phrase not in holder:
            miss.append(phrase)
    check("★ 冻结体措辞逐字来自旧源码片段（6 条抽样）", not miss, str(miss))


def t1_open_matrix():
    global cells
    print("\n[1] 开本链：27 个真实副本 × 21 场景 逐格比对 (ok, rule, reason) + 成员表")
    insts = list(C.INSTANCES.items())
    bad, n_cmp = [], 0
    for kid, inst in insts:
        for name, kw in _open_scenarios(inst):
            old = _old_open_decision(inst, "1", _mk_sim(inst, "1", **kw))
            new = _new_open_decision(inst, "1", _mk_sim(inst, "1", **kw))
            n_cmp += 1
            cells += 1
            if old != new:
                bad.append((kid, name, old, new))
    print(f"  （副本 {len(insts)} 个 × 场景 {len(_open_scenarios(insts[0][1]))} 个 = {n_cmp} 格）")
    check(f"★ 开本链逐格全等（{n_cmp} 格 × ok/rule/reason/成员表 四元组）", not bad, str(bad[:3]))
    denies = [(inst, kw) for _, inst in insts for _, kw in _open_scenarios(inst)
              if not _new_open_decision(inst, "1", _mk_sim(inst, "1", **kw))[0]]
    check(f"★ 每条拒绝都给出非空措辞且能指到规则（{len(denies)} 条拒绝）",
          all(_new_open_decision(inst, "1", _mk_sim(inst, "1", **kw))[1]
              and _new_open_decision(inst, "1", _mk_sim(inst, "1", **kw))[2]
              for inst, kw in denies))
    check("★ 五类准入关（队伍/成员/钥匙/入口/体力）在矩阵里都真的被触发过",
          {(_new_open_decision(inst, "1", _mk_sim(inst, "1", **kw))[1] or "").split(":")[0]
           for inst, kw in denies} == {"party", "member", "key", "entry", "stamina"})

    # ★ 顺序刻度（1）：链自身的规则序（成员关* → key → entry → stamina）
    inst_k = C.INSTANCES["inst_old_king_tomb"]
    p_k = _party_for(inst_k)
    _ctx = _open_ctx_of(inst_k, _members_of(inst_k, p_k), _mk_sim(inst_k, "1", party=p_k))
    check("★ 开本链规则序 = 全部成员关 → key → entry → stamina（顺序即语义）",
          instance_gate.open_admission(_ctx).rule_names()
          == ("member:1", "member:2", "key", "entry", "stamina"),
          str(instance_gate.open_admission(_ctx).rule_names()))

    # ★ 顺序刻度（2）：多故障场景「谁先拒」逐条点名（单故障场景看不出顺序漂移，
    #    这条是本轮实测「把成员关挪到钥匙后面仍全绿」之后补的）
    for name, kw, want_rule in (
            ("等级不足 + 无钥匙", dict(party=p_k, key_held=False, lv_delta=-1), "member:1"),
            ("0 血 + 无钥匙", dict(party=p_k, key_held=False, hp=0), "member:1"),
            ("无钥匙 + 位置不对", dict(party=p_k, key_held=False, at_entry=False), "key"),
            ("位置不对 + 体力不足", dict(party=p_k, key_held=True, at_entry=False, stamina=5), "entry"),
            ("等级不足 + 战斗中", dict(party=p_k, key_held=True, lv_delta=-1, in_battle=("1",)),
             "member:1")):
        r = _new_open_decision(inst_k, "1", _mk_sim(inst_k, "1", **kw))
        check(f"★ 谁先拒（{name}）→ {want_rule}", (not r[0]) and r[1] == want_rule, str(r[:3]))


def t2_open_text_verbatim():
    print("\n[2] 开本链措辞与入口三红线：提示逐字一致 + 红线是「放行」")
    bad_hint, n_h = 0, 0
    for kid, inst in C.INSTANCES.items():
        em, esa_name, esa = _entry_names(inst)
        if not (inst.get("entry") or {}).get("map"):
            continue
        n_h += 1
        if _old_entry_hint(inst, em, esa_name, esa) != instance_gate.text_entry_hint(inst, em, esa_name, esa):
            bad_hint += 1
    check(f"★ 入口提示逐字一致（{n_h} 个副本）", bad_hint == 0, str(bad_hint))
    bad_stam = [cur for cur in (0, 5, 19)
                if instance_gate.stamina_short_msg(20, cur, "进入副本") != _old_stamina_msg(20, cur, "进入副本")]
    check("★ 体力不足提示逐字一致（cur=0/5/19）", not bad_stam, str(bad_stam))
    inst = C.INSTANCES["inst_old_king_tomb"]
    check("★ 已通关免钥匙提示逐字一致",
          instance_gate.key_free_note({"inst": inst, "key_entry": None, "cleared": True})
          == "✅ 已通关副本，免钥匙入场！\n")
    check("无钥匙需求的副本不给免钥匙提示",
          instance_gate.key_free_note({"inst": C.INSTANCES["inst_goblin_camp"],
                                       "key_entry": None, "cleared": False}) == "")
    check("持钥匙未通关 → 免钥匙提示为空（旧 else 分支口径）",
          instance_gate.key_free_note({"inst": inst, "key_entry": {"key": "k"}, "cleared": False}) == "")
    # ★ 三红线必须**放行**（不是「不拒绝」）——本轮实测过的回归点：
    #   只把拒绝分支跳过而没把 entry_ok 置 True，会让「已通关/任务内」的老玩家开不了本。
    party = _party_for(inst)
    for name, kw in (("已通关免位置校验", dict(cleared=True, at_entry=False)),
                     ("主线/支线 explore 目标放行", dict(quest_exempt=True, at_entry=False)),
                     ("cur_map 已在副本图视为已在入口", dict(cur_map_in_inst=True, at_entry=False))):
        sc = dict(party=party, key_held=(not kw.get("cleared")), **kw)
        res = _new_open_decision(inst, "1", _mk_sim(inst, "1", **sc))
        check(f"★ 红线放行：{name} → 可开本", res[0] is True, str(res[:3]))
    res = _new_open_decision(inst, "1", _mk_sim(inst, "1", party=party, key_held=True,
                                               at_entry=False))
    check("对照：位置不对且无任何豁免 → entry 关拦截且给入口提示",
          res[0] is False and res[1] == "entry" and res[2].startswith("📍 请先到"),
          str(res[:3]))


def t3_walk_matrix():
    global cells
    print("\n[3] 徒步进图链：27 副本 × 8 组合（纯函数）+ 真调 world 方法（真实 DB）")
    insts = list(C.INSTANCES.items())
    bad, n_cmp = [], 0
    tip = "『前往』查看地图与可去之地"
    for kid, inst in insts:
        inst_name = inst.get("name") or C.MAP_BY_ID.get(kid, {}).get("name", "副本")
        for q in (False, True):
            for k in (False, True):
                for c in (False, True):
                    n_cmp += 1
                    cells += 1
                    old = _old_walk_decision(inst_name, q, k, c, tip)
                    ctx = {"inst_name": inst_name, "tip": tip,
                           "quest_open": q, "key_held": k, "cleared": c}
                    v = instance_gate.walk_admission(ctx).check(ctx)
                    new = "" if v.ok else v.reason
                    if old != new:
                        bad.append((kid, q, k, c, old, new))
    print(f"  （副本 {len(insts)} 个 × 8 组合 = {n_cmp} 格）")
    check(f"★ 徒步链逐格全等（{n_cmp} 格，返回文案逐字）", not bad, str(bad[:3]))
    clean_db()
    m = Main(None)
    db.create_player("g9", "q9", "门禁", C.resolve("classes", "战士"), {}, 100, 100)
    gid, qid = "g9", "q9"
    key_inst = C.INSTANCES["inst_old_king_tomb"]
    wrong, n_real = [], 0
    for kid, inst in insts:
        # world 门禁的 target 是**地图** dict（id = 地图 id，无 inst_ 前缀；mid = f"inst_{kid}"）
        target = {"id": kid[5:], "type": C.MAP_TYPE_INSTANCE}
        out = m._instance_gate_block({}, gid, qid, target)
        n_real += 1
        # 提示语里的 tip 是随机抽取的（_tip('instance')），故只钉「首行 + 尾句」逐字
        _head = f"🔒 此处为【{inst.get('name') or '副本'}】入口，需接取相应任务（或持有钥匙）才能进入。"
        if out == "":
            wrong.append((kid, "应拦截却放行"))
        elif not (out.startswith(_head + "\n") and out.endswith("；或先完成任务、收集所需钥匙～")):
            wrong.append((kid, "拦截文案不一致", out[:60]))
    check(f"★ 真调 world 门禁：{n_real} 副本无钥匙无任务一律拦截且文案逐字一致", not wrong, str(wrong[:3]))
    db.add_item(gid, qid, "i_key_old_king", {"name": key_inst["key_item"], "type": "钥匙"}, 1)
    out = m._instance_gate_block({}, gid, qid, {"id": "old_king_tomb", "type": C.MAP_TYPE_INSTANCE})
    check("真调 world 门禁：持钥匙放行（与旧三档判定一致）",
          out == _old_walk_decision(key_inst["name"], False, True, False, m._tip("instance")) == "",
          repr(out))
    check("徒步进图不扣钥匙（钥匙仍在包里）",
          instance_gate.find_instance_key_item(gid, qid, key_inst["key_item"]) is not None)
    db.remove_item(gid, qid, "i_key_old_king")
    # ★ D2（v185 后续登记的**有意差异**）：世界门禁的「已通关」档原先查 `inst_clear_<地图id>`，
    #   而真实通关写入的是 `inst_clear_<inst 键>`（instance.py 通关结算 / instance_router 读档）
    #   ⇒ 该档线上**不可达**。修复后查 inst 键：与 instance.py 免钥匙真正同口径。
    #   行为变化（有意）：已通关的玩家徒步进副本图不再被拦（原先会被拦）。
    #   证据（修复前后各跑一次）：写真实键 拦截→放行；写地图 id 形式 放行→拦截（一套口径）。
    db.set_achievement(gid, qid, "inst_clear_inst_old_king_tomb", 1)
    out = m._instance_gate_block({}, gid, qid, {"id": "old_king_tomb", "type": C.MAP_TYPE_INSTANCE})
    check("★ D2：真实通关写入的键（inst_clear_<inst键>）能放行徒步进图", out == "", repr(out))
    check("★ D2：不是两套都认（老的地图 id 形式已不再被认可）",
          instance_gate.instance_cleared_qq(gid, qid, "old_king_tomb") is False)
    hit = next((k for k, v in C.INSTANCES.items()
                for q in C.MAIN_QUESTS
                if q.get("objective", {}).get("explore") == k[5:]), None)
    if hit:
        mk = next(q for q in C.MAIN_QUESTS if q.get("objective", {}).get("explore") == hit[5:])["id"]
        db.save_quests(gid, qid, {"main_quest": mk, "main_status": "active",
                                  "main_progress": {}, "daily": {}, "completed_main": [], "side": {}})
        out = m._instance_gate_block({}, gid, qid, {"id": hit[5:], "type": C.MAP_TYPE_INSTANCE})
        check(f"真调 world 门禁：主线 explore 目标放行（{hit[5:]} / {mk}）", out == "", repr(out))
    else:
        print("  ⚠️ 无「主线 explore == 副本图」的数据，跳过该状态")
    check("非副本图直接放行（不进链）",
          m._instance_gate_block({}, gid, qid, {"id": "oak_town", "type": C.MAP_TYPE_TOWN}) == "")
    clean_db()


def _join_sim(party=("1", "2"), my_key="2", leader_row=None, self_row="auto",
              player=None, enemies_alive=True):
    st = {"type": "instance", "inst_id": "inst_old_king_tomb", "members": ["1"],
          "players": {"1": {"hp": 100}}}
    if isinstance(leader_row, dict):
        st.update(leader_row)
    if self_row == "auto":
        self_row = {"state": {"inst_id": st.get("inst_id")}}
    return {
        "party_members": list(party),
        "my_key": my_key,
        "battle_of_leader": lambda: (None if leader_row == "none"
                                     else {"state": copy.deepcopy(st)}),
        "self_row": lambda: (None if self_row is None else copy.deepcopy(self_row)),
        # 命令层口径：无 battle 行 → 不可能与 inst_id 相等的哨兵
        "self_inst_id": lambda: (self_row["state"].get("inst_id") if self_row
                                 else "\x00no-instance-row"),
        "enemies_alive": lambda s: enemies_alive,
        "player": {"hp": 100} if player is None else player,
    }


def t4_join_matrix():
    print("\n[4] 加入战斗链：15 场景 逐格比对 (ok, rule, reason)")
    scs = [
        ("无队", dict(party=())),
        ("自己是队长", dict(party=("2", "2"), my_key="2")),
        ("队长无战斗行", dict(leader_row="none")),
        ("队长战斗非副本", dict(leader_row={"type": "wild"})),
        ("队员不在本副本（跨副本串台）", dict(self_row={"state": {"inst_id": "inst_other"}})),
        ("队员无 battle 行", dict(self_row=None)),
        ("战斗已结束", dict(leader_row={"over": True})),
        ("战斗已通关", dict(leader_row={"cleared": True})),
        ("战斗已撤退", dict(leader_row={"retreated": True})),
        ("重复加入", dict(leader_row={"players": {"2": {"hp": 100}}})),
        ("满员 4 人", dict(leader_row={"members": ["1", "2", "3", "4"]})),
        ("敌方全灭", dict(enemies_alive=False)),
        ("0 血", dict(player={"hp": 0})),
        ("空 player 档案", dict(player={})),
        ("正常加入", dict()),
    ]
    bad = []
    for name, kw in scs:
        old = _old_join_decision(_join_sim(**kw))
        new = _new_join_decision(_join_sim(**kw))
        cells_inc = 1 if old == new else 0
        globals()["cells"] += cells_inc
        if old != new:
            bad.append((name, old, new))
    print(f"  （场景 {len(scs)} 个）")
    check(f"★ 加入战斗链逐格全等（{len(scs)} 格 × ok/rule/reason）", not bad, str(bad))
    sim = _join_sim()
    ctx = {"party_members": sim["party_members"], "my_key": sim["my_key"],
           "battle_of_leader": sim["battle_of_leader"],
           "self_inst_id": sim["self_inst_id"],
           "enemies_alive": lambda: True, "player": sim["player"]}
    v = instance_gate.join_admission(ctx).check(ctx)
    check("★ 链内把队员视角的队长 st 写进 ctx['st']（命令层据此复用，不二次取数）",
          v.ok and isinstance(ctx.get("st"), dict)
          and ctx["st"].get("inst_id") == "inst_old_king_tomb", repr(ctx.get("st"))[:120])
    c2 = {"party_members": [], "my_key": "2", "battle_of_leader": lambda: None,
          "self_inst_id": lambda: None, "enemies_alive": lambda: True, "player": {"hp": 1}}
    instance_gate.join_admission(c2).check(c2)
    check("拒绝路径（无队）不写 ctx['st']", "st" not in c2)
    check("链规则序列与旧实现顺序一致（12 条，名称固定）",
          instance_gate.join_admission({"party_members": []}).rule_names()
          == ("party", "member_view", "has_battle", "same_inst", "not_over", "not_retreated",
              "is_instance", "not_dupe", "not_full", "enemy_alive", "hp", "profile"))


def t5_resume_matrix():
    print("\n[5] 恢复旧进度链：人数 / 等级 / 0 血 / 战斗中（★ 不查副业等待）")
    inst = C.INSTANCES["inst_secret_crypt"]  # min 3 max 4 lv 42
    party = ["1", "2", "3"]
    scs = [
        ("刚好 3 人全合格", dict(party=party, lv_delta=1)),
        ("人少（2 人）", dict(party=party[:2], lv_delta=1)),
        ("人多（5 人）", dict(party=party + ["4", "5"], lv_delta=1)),
        ("等级不足", dict(party=party, lv_delta=-1)),
        ("0 血", dict(party=party, hp=0)),
        ("战斗中", dict(party=party, in_battle=("2",))),
        ("★ 副业等待中（旧实现不查 → 仍可恢复）",
         dict(party=party, prof=(("2", {"finish": NOW + 60, "type": "mining"}),))),
    ]
    bad = []
    for name, kw in scs:
        members = _members_of(inst, kw.get("party", party), "1")
        old = _old_resume_decision(inst, members, _mk_sim(inst, "1", **kw))
        new = _new_resume_decision(inst, members, _mk_sim(inst, "1", **kw))
        globals()["cells"] += 1
        if old != new:
            bad.append((name, old, new))
    check(f"★ 恢复链逐格全等（{len(scs)} 格）", not bad, str(bad))
    check("恢复链不查副业等待（旧语义：等待中也能恢复）",
          _new_resume_decision(inst, party, _mk_sim(inst, "1", party=party,
                                                    prof=(("2", {"finish": NOW + 60,
                                                                 "type": "mining"}),))) is True)
    check("恢复链规则序列 = size + 每队员一条（无 key/entry/stamina）",
          instance_gate.resume_admission(
              {"inst": inst, "members": ["1", "2"], "now": NOW,
               "player_of": lambda m: {"level": 99, "hp": 9},
               "in_battle": lambda m: False}).rule_names() == ("size", "member:1", "member:2"))
    check("恢复链不查钥匙（ctx 里无需 key_entry/drop_key）",
          _new_resume_decision(inst, party, _mk_sim(inst, "1", party=party, key_held=False)) is True)


def t6_d1_white_deduct():
    print("\n[6] ★ 白扣反证（有意差异 D1）：位置拒绝 / 体力拒绝时旧实现已扣钥匙")
    inst = C.INSTANCES["inst_old_king_tomb"]  # 需钥匙、有入口
    party = _party_for(inst)
    cases = [
        ("位置不对但持钥匙", dict(party=party, key_held=True, at_entry=False, stamina=100)),
        ("体力不足但持钥匙", dict(party=party, key_held=True, at_entry=True, stamina=5)),
    ]
    for name, kw in cases:
        old_sim = _mk_sim(inst, "1", **kw)
        old = _old_open_decision(inst, "1", old_sim)
        new_sim = _mk_sim(inst, "1", **kw)
        new = _new_open_decision(inst, "1", new_sim)
        check(f"★ D1/{name}：旧实现已扣钥匙（白扣复现，旧行为证据 instance.py:2187-2191）",
              (not old[0]) and old_sim["drops"] == ["key"],
              f"ok={old[0]} rule={old[1]} drops={old_sim['drops']}")
        check(f"★ D1/{name}：新链不扣钥匙（drop_key 未被调用）",
              (not new[0]) and new_sim["drops"] == [],
              f"ok={new[0]} rule={new[1]} drops={new_sim['drops']}")
        check(f"★ D1/{name}：拒绝措辞与规则位置新旧逐字一致（只改副作用时机）",
              old[2] == new[2] and old[1] == new[1], f"{old[1]} vs {new[1]}")
        check(f"D1/{name}：两边都没扣体力（拒绝路径副作用全不执行）",
              old_sim["pays"] == [] and new_sim["pays"] == [])
    ok_sim = _mk_sim(inst, "1", party=party, key_held=True, at_entry=True, stamina=100)
    ok = _new_open_decision(inst, "1", ok_sim)
    check("全过时副作用按序各执行一次（钥匙 1 次 / 体力 1 次）",
          ok[0] and ok_sim["drops"] == ["key"] and ok_sim["pays"] == [20],
          f"drops={ok_sim['drops']} pays={ok_sim['pays']}")
    # 引擎形状级反证：Rule.consume 只在全过之后跑（check 用的 ctx 与构建用的一致）
    seq = []
    _c = {
        "members": ["1"], "inst": inst, "now": NOW,
        "player_of": lambda m: {"name": "我", "level": 99, "hp": 10},
        "in_battle": lambda m: False, "prof_wait": lambda m: None, "prof_label": lambda t: "副业",
        "key_entry": {"key": "k"}, "cleared": False, "entry_ok": False, "entry_hint": "位置不对",
        "stamina": 100, "stamina_cost": 20,
        "drop_key": lambda: seq.append("key"), "pay_stamina": lambda: seq.append("stamina")}
    v = instance_gate.open_admission(_c).check(_c)
    check("引擎链：key 关已通过但 entry 关拒绝 → drop_key/pay_stamina 都不执行（副作用延迟）",
          (not v.ok) and v.rule == "entry" and seq == [], f"{v.rule} {seq}")
    _c2 = dict(_c, entry_ok=True)
    v2 = instance_gate.open_admission(_c2).check(_c2)
    check("引擎链：全过时 consume 按声明序各跑一次（钥匙 → 体力）",
          v2.ok and seq == ["key", "stamina"], str(seq))


def t7_wiring():
    print("\n[7] 接线门禁：命令层不再有手写 if 链；措辞只在文案表 content/data/text_specs.json")
    # ★ P5F-REPOINT: 原读宿主壳 `game/commands/instance.py` / `base.py` / `world.py` /
    #   `game/core/instance_gate.py`（随删壳批消失）→ 包内真源四侧（登记面 + 实现面）：
    #   `content/instance_cmds.py`、`content/cmds_base_rules.py`、
    #   `content/world_cmds.py` + `content/cmds_world.py`、`content/flow/instance_gate.py`。
    #   断言逐条不变（原「壳 + 实现」两侧拼接 = 实现侧全集）。
    #   （副本 8 条的 handler 薄壳 `content/cmds_instance.py` 随声明式绑定迁删 —— 它本来只做
    #    「守卫声明 + 调包」，本段要的 `instance_gate.*` 真调用点全在实现面。）
    _PKG = "content"        # 包内真源（≡ 旧 `<插件根>/framework/games/orlandia/content`）

    def _read(rel):
        with open(os.path.join(_paths.PKG_ROOT, rel), encoding="utf-8") as f:
            return f.read()
    inst_src = _read(os.path.join(_PKG, "instance_cmds.py"))
    base_src = _read(os.path.join(_PKG, "cmds_base_rules.py"))
    world_src = (_read(os.path.join(_PKG, "world_cmds.py")) + "\n"
                 + _read(os.path.join(_PKG, "cmds_world.py")))
    gate_src = _read(os.path.join(_PKG, "flow", "instance_gate.py"))
    for needle in ("instance_gate.resolve_open_members", "instance_gate.open_admission",
                   "instance_gate.key_free_note", "instance_gate.resume_admission",
                   "instance_gate.join_admission", "instance_gate.text_entry_hint",
                   "instance_gate.find_instance_key_item", "instance_gate.instance_cleared_qq"):
        check(f"instance.py 调用 {needle}", needle in inst_src)
    check("world.py 调用 instance_gate.walk_admission", "instance_gate.walk_admission" in world_src)
    check("base.py 调用 instance_gate.stamina_short_msg（体力不足措辞唯一来源）",
          "instance_gate.stamina_short_msg" in base_src)
    leftover = [s for s in ("只有队长才能开启副本", "你还没有队伍", "别拿命加入战斗",
                            "这场战斗已经结束了", "附近没有可加入的战斗", "副本是封闭区域",
                            "战斗满员了", "敌人已经全部倒下", "你已在战斗中", "队友还没有角色",
                            "别拿命闯副本", "正在战斗中，先打完再来", "你的角色数据异常",
                            "被封印之门挡住", "人组队！先『组队", "请先到【") if s in inst_src]
    check("★ instance.py 里旧 if 链的 16 条措辞已全部迁走", not leftover, str(leftover))
    check("base.py 里不再内联体力不足三行", "体力不足！" not in base_src)
    check("world.py 里不再内联徒步拦截文案", "需接取相应任务" not in world_src)
    # ★ 文案真源 = 包内文案表 `content/data/text_specs.json`（部署期镜像 `game/data/text_specs.json`
    #   是保留资产，但**真源**在包内；P5F-REPOINT 起本文件直接读真源，单一来源）：
    #   本文件只传槽位，一句玩家可见文案都不许留在这两个 .py 里。
    texts_json = _read(os.path.join(_PKG, "data", "text_specs.json"))
    check("★ 迁移的措辞都落在文案表里（不是 .py）",
          all(s in texts_json for s in ("只有队长才能开启副本", "你还没有队伍", "别拿命加入战斗",
                                        "被封印之门挡住", "需接取相应任务",
                                        "体力每 1 分钟自然恢复 1 点")))
    check("★ instance_gate.py 已无玩家可见文案（老文案一句都不留）",
          not [s for s in ("只有队长才能开启副本", "你还没有队伍", "别拿命加入战斗", "被封印之门挡住",
                           "需接取相应任务", "体力不足！", "战斗满员了", "队友还没有角色",
                           "正在战斗中，先打完再来", "这场战斗已经结束了", "你的角色数据异常")
               if s in gate_src])
    check("★ instance_gate.py 的措辞函数全部走文案表（T.text / T.static）",
          gate_src.count("T.text(") >= 11 and gate_src.count("T.static(") >= 16
          and "from . import texts as T" in gate_src)
    check("★ 五条链仍在唯一真相源里（open/resume/join/walk + 成员规则工厂）",
          all(s in gate_src for s in ("def open_admission", "def resume_admission",
                                      "def join_admission", "def walk_admission",
                                      "def member_rule", "def resolve_open_members")))


# ══════════════════════════════════════════════════════════════════════════
# 六、真实 DB 端到端
# ══════════════════════════════════════════════════════════════════════════
async def _cmd(m, name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    res = await run(getattr(m, name), ev)
    return res[-1] if res else ""


def _has_key(gid, qid, inst):
    return instance_gate.find_instance_key_item(gid, qid, inst.get("key_item")) is not None


def _teardown(m, gid, qids):
    for q in qids:
        row = db.get_battle(gid, q)
        if row and (row["state"] or {}).get("type") == "instance":
            wid = (row["state"] or {}).get("world_id") or ""
            if wid.startswith("inst:"):
                for mm in (row["state"].get("members") or []):
                    try:
                        db.update_player(gid, mm, world_id="mainland")
                    except Exception:
                        pass
                C.destroy_instance_world(wid)
        m._unlock_battle(gid, q)
        db.clear_battle(gid, q)


async def t8_e2e():
    print("\n[8] 真实 DB 端到端：真调『副本 <名字>』『加入战斗』")
    clean_db()
    m = Main(None)
    gid = "g1"
    await _cmd(m, "register", gid, "i1", "注册 战士 队长 男")
    await _cmd(m, "register", gid, "i2", "注册 法师 队员 女")
    inst = C.INSTANCES["inst_old_king_tomb"]
    em, esa_name, esa = _entry_names(inst)
    hint = instance_gate.text_entry_hint(inst, em, esa_name, esa)

    db.update_player(gid, "i1", level=40, hp=500, stamina=100,
                     cur_map="oak_town", cur_subarea="oak_square", world_id="mainland")
    db.add_item(gid, "i1", "i_key_old_king", {"name": inst["key_item"], "type": "钥匙"}, 1)

    # 8.1 位置不对但持钥匙 → 逐字入口提示 + 钥匙保留（★ D1 新行为）
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 位置不对：提示与 text_entry_hint 逐字一致", out == hint, repr(out[:200]))
    check("★ e2e D1：位置拒绝后钥匙仍在背包（旧实现此处已扣走）", _has_key(gid, "i1", inst))
    check("e2e 位置拒绝后未开本", db.get_battle(gid, "i1") is None)

    # 8.2 体力不足但持钥匙 → 逐字体力提示 + 钥匙保留（★ D1 新行为）
    db.update_player(gid, "i1", cur_map="king_road", cur_subarea="king_road_3", stamina=5)
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 体力不足：提示与 stamina_short_msg 逐字一致",
          out == instance_gate.stamina_short_msg(20, 5, "进入副本"), repr(out[:200]))
    check("★ e2e D1：体力拒绝后钥匙仍在背包", _has_key(gid, "i1", inst))
    check("e2e 体力拒绝后未开本", db.get_battle(gid, "i1") is None)

    # 8.3 正常开本：钥匙消耗 + 体力扣减 + 开本文案
    db.update_player(gid, "i1", stamina=100)
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 正常开本成功", "副本开启" in out, repr(out[:200]))
    check("e2e 正常开本后钥匙已消耗", not _has_key(gid, "i1", inst))
    check("e2e 正常开本后体力扣 20（100→80）", db.get_player(gid, "i1").get("stamina") == 80)
    check("e2e 正常开本无免钥匙提示", "免钥匙" not in out)
    check("e2e 正常开本后战斗行存在", db.get_battle(gid, "i1") is not None)
    _teardown(m, gid, ["i1", "i2"])

    # 8.4 已通关免钥匙：无钥匙也开本 + 免钥匙提示
    db.set_achievement(gid, "i1", "inst_clear_inst_old_king_tomb", 1)
    db.update_player(gid, "i1", stamina=100, cur_map="king_road", cur_subarea="king_road_3")
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 已通关免钥匙开本成功 + 逐字提示",
          "副本开启" in out and "✅ 已通关副本，免钥匙入场！" in out, repr(out[:200]))
    _teardown(m, gid, ["i1", "i2"])

    # 8.4b 已通关 + **不在入口** → 位置红线放行（本轮实测回归点：只「跳过拒绝分支」而没把
    #      entry_ok 置 True，会让已通关老玩家被 entry 关拦下 → 这里用真命令钉住）
    db.update_player(gid, "i1", stamina=100, cur_map="oak_town", cur_subarea="oak_square")
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 已通关+位置不对：位置红线放行（免位置校验）", "副本开启" in out, repr(out[:200]))
    _teardown(m, gid, ["i1", "i2"])

    # 8.5 队伍人数不足（圣堂地窖 min 3）：逐字提示
    inst2 = C.INSTANCES["inst_secret_crypt"]
    db.party_create(gid, "i1", "i1")
    db.update_player(gid, "i1", level=50, stamina=100)
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 圣堂地窖")
    check("e2e 队伍人少：与 text_too_few 逐字一致",
          out == instance_gate.text_too_few(inst2, inst2["min_players"], 1), repr(out[:200]))
    db.party_leave(gid, "i1")
    db.party_leave(gid, "i2")

    # 8.6 非队长：逐字提示
    db.party_create(gid, "i2", "i1")
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 非队长：与 text_leader_only 逐字一致",
          out == instance_gate.text_leader_only(), repr(out[:200]))
    db.party_leave(gid, "i1")
    db.party_leave(gid, "i2")

    # 8.7 无钥匙未通关：与 text_key_seal 逐字一致
    clean_db("achievements")
    db.update_player(gid, "i1", stamina=100, cur_map="king_road", cur_subarea="king_road_3")
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 无钥匙未通关：与 text_key_seal 逐字一致",
          out == instance_gate.text_key_seal(inst, inst["key_item"],
                                             inst.get("key_source", "？？？")), repr(out[:200]))

    # 8.8 席位不足（0 血）与位置放行：真调命令覆盖成员关/入口关
    db.update_player(gid, "i1", hp=0)
    out = await _cmd(m, "instance_cmd", gid, "i1", "副本 旧王陵")
    check("e2e 0 血：与 text_member_dead 逐字一致",
          out == instance_gate.text_member_dead(db.get_player(gid, "i1")["name"]), repr(out[:200]))
    db.update_player(gid, "i1", hp=500)

    # 8.9 『加入战斗』：无队 → 逐字提示（链的第一条）
    out = await _cmd(m, "join_battle", gid, "i1", "加入战斗")
    check("e2e 加入战斗无队：与冻结基准逐字一致",
          out == "你还没有队伍！先『组队 <对方名字>』拉上队友，再一起并肩作战～", repr(out[:120]))
    _teardown(m, gid, ["i1", "i2"])
    clean_db()


async def main():
    print("== v185 副本准入链门禁：内容侧逐格一致（旧实现冻结比对） ==")
    t0_freeze_self_check()
    t1_open_matrix()
    t2_open_text_verbatim()
    t3_walk_matrix()
    t4_join_matrix()
    t5_resume_matrix()
    t6_d1_white_deduct()
    t7_wiring()
    await t8_e2e()
    print(f"\n===== 结果：通过 {passed} / {passed + failed}（逐格比对 {cells} 格）=====")
    return 1 if failed else 0


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
