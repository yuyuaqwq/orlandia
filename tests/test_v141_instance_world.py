# -*- coding: utf-8 -*-
"""v141 大陆隔离架构验收测试（tests/test_v141_instance_world.py）

覆盖（对应 docs/CONTINENT_ISOLATION_v141.md §5 验收标准）：
1. Position 结构体单测：from_player 解析 / key() / is_instance / is_mainland /
   resolve_map（主大陆→MAP_BY_ID / 副本→克隆大陆）/ resolve_subareas / as_mainland
2. create/destroy 大陆实例：inst: 前缀 / get_instance_world / resolve_map_for 副本克隆
3. 开本→大陆：玩家 world_id=inst:<uuid>、大陆实例存在、st 挂在大陆、battle_state 镜像
4. 撤退→放弃进度：二次确认后清 battle + world_id 回 mainland + 大陆销毁（v173.3 #87）
5. 离开→大陆销毁：大陆实例销毁、玩家 world_id 回 mainland
6. 退队→world_id 回滚：队员退队后 world_id 回 mainland（大陆保留）
7. 多队并发隔离：两队各自 inst:<uuid>、大陆独立、互不干扰
8. 失败回城→大陆销毁（v141 补充验收）
9. 孤儿大陆自愈（v141 instance_cmd 入口自愈）

禁止修改 game/ 下任何源码；发现失败以 KNOWN-FAIL 标注并给出原因。
"""
import os
import sys
import time

# ⚠️ F2 副本入口设施化（v141.x）：开本现在要求队长站在入口位置（entry 字段），
# 本测试全部开本用例的 prep_player 落点是 oak_town（非入口），会被新位置校验拦截。
# 适配：开本前把玩家瞬移到哥布林营地入口（misty_swamp/misty_swamp_3），
# 其余断言与大陆隔离语义不变。
GOBLIN_ENTRY = ("misty_swamp", "misty_swamp_3")


def goto_goblin_entry(gid, *qids):
    """把若干玩家瞬移到哥布林营地入口（misty_swamp/misty_swamp_3）。"""
    for q in qids:
        db.update_player(gid, q, cur_map=GOBLIN_ENTRY[0], cur_subarea=GOBLIN_ENTRY[1])


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run  # noqa: E402
from content.position import Position as _Position  # REPOINT_MAP: game.content.Position → content.position

passed = failed = 0
known_fail = []


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")


def check_kf(name, cond, detail=""):
    """KNOWN-FAIL 判定：失败不计数 failed，但记录原因供主 agent 修复。"""
    global passed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        known_fail.append((name, str(detail)[:400]))
        print(f"  ⚠️  KNOWN-FAIL {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""


def prep_player(m, gid, qid, name, cls, level=20, gold=5000):
    """make_player + 预置（等级/金币/满血/体力/位置）。"""
    make_player(gid, qid, name=name, cls=cls, level=level)
    p = db.get_player(gid, qid)
    db.update_player(gid, qid, hp=p["max_hp"], mp=p["max_mp"], level=level, gold=gold,
                     cur_map="oak_town", cur_subarea="oak_town_1")
    return db.get_player(gid, qid)


def _cleanup_instance(m, gid, st):
    """清理战斗锁 + battle 行 + 销毁大陆（测试收尾，避免残留影响后续用例）。"""
    try:
        for mm in st.get("members") or []:
            m._unlock_battle(gid, mm)
            db.clear_battle(gid, mm)
    except Exception:
        pass
    try:
        wid = st.get("world_id") or ""
        if wid.startswith("inst:"):
            C.destroy_instance_world(wid)
            for mm in st.get("members") or []:
                db.update_player(gid, mm, world_id="mainland")
    except Exception:
        pass


# ============================================================
# 1. Position 结构体单测
# ============================================================

def check_position():
    print("【1. Position 结构体单测】")
    P = _Position
    # 隔离：直接构造独立大陆，避免与后面用例共享内存态
    _wid_tmp = C.create_instance_world("inst_goblin_camp", ["tmp"], {},
                                       now=int(time.time()), leader="tmp",
                                       st={"type": "instance", "leader": "tmp"},
                                       rooms={}, resources_pool={})
    try:
        # 1a. from_player 解析（inst 世界）
        pos = P.from_player({"world_id": "inst:abc123", "cur_map": "goblin_camp", "cur_subarea": "goblin_camp_1"})
        check("from_player 解析 world_id", pos.world_id == "inst:abc123", pos.world_id)
        check("from_player 解析 cur_map", pos.map_id == "goblin_camp", pos.map_id)
        check("from_player 解析 cur_subarea", pos.subarea_id == "goblin_camp_1", pos.subarea_id)
        check("key 格式 world:map:sa", pos.key() == "inst:abc123:goblin_camp:goblin_camp_1", pos.key())
        check("is_instance True", pos.is_instance(), "")
        check("is_mainland False", not pos.is_mainland(), "")

        # 1b. 主大陆（缺省 world_id 兜底 = mainland）
        posm = P.from_player({"cur_map": "oak_town", "cur_subarea": "oak_town_1"})
        check("缺省 world_id=mainland", posm.world_id == "mainland", posm.world_id)
        check("is_mainland True", posm.is_mainland(), "")
        check("is_instance False", not posm.is_instance(), "")

        # 1c. resolve_map：主大陆 → MAP_BY_ID
        rm = posm.resolve_map()
        check("主大陆 resolve_map 返回 MAP_BY_ID 地图", rm is not None and rm.get("id") == "oak_town", rm)
        check("主大陆 resolve_map 即全局对象", rm is C.MAP_BY_ID.get("oak_town"), "")

        # 1d. resolve_subareas：主大陆 → SUBAREAS
        sa = posm.resolve_subareas()
        check("主大陆 resolve_subareas 非空", len(sa) > 0, sa)
        check("主大陆 resolve_subareas 即全局对象", sa is C.SUBAREAS.get("oak_town"), "")

        # 1e. 副本世界 resolve_map/resolve_subareas → 克隆大陆（独立构造的大陆）
        posi = P.from_player({"world_id": _wid_tmp, "cur_map": "goblin_camp", "cur_subarea": "goblin_camp_1"})
        rm_i = posi.resolve_map()
        check("副本 resolve_map 返回克隆地图", rm_i is not None and rm_i.get("id") == "goblin_camp", rm_i)
        check("副本 resolve_map 克隆非全局", rm_i is not C.MAP_BY_ID.get("goblin_camp"), "")
        sa_i = posi.resolve_subareas()
        check("副本 resolve_subareas 3 房间", len(sa_i) == 3, sa_i)
        # 不存在的大陆 → None
        posi2 = P.from_player({"world_id": "inst:zzz999", "cur_map": "goblin_camp", "cur_subarea": "goblin_camp_1"})
        check("不存在大陆 resolve_map=None", posi2.resolve_map() is None, "")

        # 1f. as_mainland 重置 world_id（位置字段保留）
        am = pos.as_mainland()
        check("as_mainland world_id=mainland", am.world_id == "mainland", am.world_id)
        check("as_mainland 保留 map", am.map_id == "goblin_camp", am.map_id)
        check("as_mainland 保留 subarea", am.subarea_id == "goblin_camp_1", am.subarea_id)

        # 1g. with_map / with_subarea
        wm = pos.with_map("hill_mine", "hill_mine_1")
        check("with_map 同世界换地图", wm.world_id == "inst:abc123" and wm.map_id == "hill_mine" and wm.subarea_id == "hill_mine_1", wm)
        wsa = pos.with_subarea("goblin_camp_2")
        check("with_subarea 换子区域", wsa.map_id == "goblin_camp" and wsa.subarea_id == "goblin_camp_2", wsa)

        # 1h. to_db 序列化
        t = pos.to_db()
        check("to_db (cur_map, cur_subarea, world_id)", t == ("goblin_camp", "goblin_camp_1", "inst:abc123"), t)
    finally:
        C.destroy_instance_world(_wid_tmp)


# ============================================================
# 2. create/destroy 大陆实例
# ============================================================

async def check_world_crud(m):
    print("【2. create/destroy 大陆实例】")
    boss = C.build_monster(C.INSTANCES["inst_goblin_camp"]["boss"],
                           {"id": "inst_goblin_camp", "name": "哥布林营地", "area": "instance"})
    wid = C.create_instance_world("inst_goblin_camp", ["q1"], boss, now=int(time.time()),
                                  leader="q1", st={"type": "instance", "leader": "q1"},
                                  rooms={}, resources_pool={})
    check("create 返回 inst: 前缀", str(wid).startswith("inst:"), wid)
    check("get_instance_world 可取回", C.get_instance_world(wid) is not None, "")
    inst = C.get_instance_world(wid)
    check("大陆 name", inst.get("name") == "哥布林营地", inst.get("name"))
    check("大陆 maps 克隆副本图", inst.get("maps", {}).get("goblin_camp") is not None, "")
    check("大陆 maps 是克隆", inst.get("maps", {}).get("goblin_camp") is not C.MAP_BY_ID.get("goblin_camp"), "")
    check("大陆 subareas 克隆", inst.get("subareas", {}).get("goblin_camp") is not None, "")
    check("大陆 subareas 是克隆", inst.get("subareas", {}).get("goblin_camp") is not C.SUBAREAS.get("goblin_camp"), "")
    check("大陆 st 挂载", (inst.get("st") or {}).get("type") == "instance", "")
    check("大陆 retreated 初始 False", inst.get("retreated") is False, "")
    check("大陆 members 快照", inst.get("members") == ["q1"], inst.get("members"))
    # resolve_map_for：副本大陆 → 克隆地图；主大陆 → 全局
    rm = C.resolve_map_for(wid, "goblin_camp")
    check("resolve_map_for 副本返回克隆地图", rm is not None and rm.get("id") == "goblin_camp", rm)
    check("resolve_map_for 副本克隆非全局", rm is not C.MAP_BY_ID.get("goblin_camp"), "")
    rm_m = C.resolve_map_for("mainland", "oak_town")
    check("resolve_map_for 主大陆返回全局地图", rm_m is C.MAP_BY_ID.get("oak_town"), "")
    rm_none = C.resolve_map_for(wid, "no_such_map")
    check("resolve_map_for 未知地图 None", rm_none is None, "")
    # destroy
    C.destroy_instance_world(wid)
    check("destroy 后 get 返回 None", C.get_instance_world(wid) is None, "")
    check("destroy 后 resolve_map_for None", C.resolve_map_for(wid, "goblin_camp") is None, "")


# ============================================================
# 3. 开本 → 大陆（单人弹性副本 哥布林营地 1-2 人）
# ============================================================

async def check_start_world(m):
    print("【3. 开本→大陆】")
    prep_player(m, "g1", "q1", "战士", "战士", level=20)
    goto_goblin_entry("g1", "q1")  # F2：开本需站在副本入口
    out = await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    check("开本成功", "副本开启" in out, out[:200])
    p = db.get_player("g1", "q1")
    wid = p.get("world_id", "")
    check("玩家 world_id 是 inst: 前缀", str(wid).startswith("inst:"), wid)
    check("玩家位置同步副本入口", p.get("cur_map") == "goblin_camp" and p.get("cur_subarea") == "goblin_camp_1",
          f"{p.get('cur_map')}:{p.get('cur_subarea')}")
    inst = C.get_instance_world(wid)
    check("大陆实例存在", inst is not None, "")
    check("大陆 st 挂载（type=instance）", inst is not None and (inst.get("st") or {}).get("type") == "instance", "")
    st = (inst or {}).get("st") or {}
    check("st.world_id == 玩家 world_id", st.get("world_id") == wid, st.get("world_id"))
    check("大陆 members 含玩家", inst is not None and "q1" in (inst.get("members") or []), inst)
    check("大陆 rooms 挂载", inst is not None and inst.get("rooms") is not None, "")
    check("大陆 resources_pool 挂载", inst is not None and inst.get("resources_pool") is not None, "")
    b = db.get_battle("g1", "q1")
    check("battle_state 镜像存在", b is not None and b["state"].get("type") == "instance", b)
    check("battle_state 镜像 world_id 同步", b is not None and b["state"].get("world_id") == wid, b)
    # 副本 Position resolve_map → 克隆大陆
    posi = _Position.from_player(db.get_player("g1", "q1"))
    rm = posi.resolve_map()
    check("副本 resolve_map 返回克隆地图", rm is not None and rm.get("id") == "goblin_camp", rm)
    check("副本 resolve_map 克隆非全局", rm is not C.MAP_BY_ID.get("goblin_camp"), "")
    sa = posi.resolve_subareas()
    check("副本 resolve_subareas 3 房间", len(sa) == 3, sa)
    # 收尾：销毁大陆 + 解锁 + 清 battle
    _cleanup_instance(m, "g1", st)


# ============================================================
# 4. 撤退 → 大陆保留
# ============================================================

async def check_retreat_keep(m):
    """v173.3 意见#87（鱼鱼拍板）：撤退=放弃进度（二次确认），不再保留可恢复层进度。

    旧语义（v141）：撤退保留层进度+大陆实例，再次开本从原层恢复。
    新语义：第一次『撤退』弹确认（进度保留等待确认）；『确认撤退』清 battle +
    world_id 回 mainland + 销毁大陆实例（放弃本局，重新开本从头打）。
    通关后（cleared）撤退=等同『离开副本』（保留战利品）。
    """
    print("【4. 撤退→放弃进度（二次确认）】")
    prep_player(m, "g1", "q1", "战士", "战士", level=20)
    goto_goblin_entry("g1", "q1")  # F2：开本需站在副本入口
    await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    wid = db.get_player("g1", "q1").get("world_id", "")
    out = await cmd(m, "instance_retreat", "g1", "q1", "撤退")
    check("撤退输出弹确认", "确认撤退" in out, out[:200])
    # 第一次撤退后：未确认前 battle/大陆仍在（防误触）
    p = db.get_player("g1", "q1")
    check("确认前 world_id 仍是 inst:（未真正放弃）", str(p.get("world_id", "")).startswith("inst:"), p.get("world_id"))
    inst = C.get_instance_world(wid)
    check("确认前大陆实例仍存在", inst is not None, "")
    check("确认前 battle 仍活跃", m._instance_battle_for("g1", "q1") is not None, "")
    # 确认撤退 → 真正放弃
    out = await cmd(m, "instance_retreat_confirm", "g1", "q1", "确认撤退")
    check("确认撤退输出放弃", "放弃" in out, out[:200])
    p = db.get_player("g1", "q1")
    check("world_id 回 mainland", p.get("world_id") == "mainland", p.get("world_id"))
    check("大陆实例已销毁（进度放弃）", C.get_instance_world(wid) is None, "")
    check("battle 镜像已清", db.get_battle("g1", "q1") is None, "")


# ============================================================
# 5. 离开副本 → 大陆销毁
# ============================================================

async def check_leave_destroy(m):
    print("【5. 离开副本→大陆销毁】")
    prep_player(m, "g1", "q1", "战士", "战士", level=20)
    goto_goblin_entry("g1", "q1")  # F2：开本需站在副本入口
    await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    wid = db.get_player("g1", "q1").get("world_id", "")
    check("开本成功（前置）", str(wid).startswith("inst:"), wid)
    out = await cmd(m, "instance_leave", "g1", "q1", "离开副本")
    check("离开输出", "离开" in out, out[:200])
    p = db.get_player("g1", "q1")
    check("world_id 回 mainland", p.get("world_id") == "mainland", p.get("world_id"))
    check("大陆实例已销毁", C.get_instance_world(wid) is None, "")
    b = db.get_battle("g1", "q1")
    check("battle 镜像已清", b is None, "")


# ============================================================
# 6. 退队 → world_id 回滚
# ============================================================

async def check_party_leave_rollback(m):
    print("【6. 退队→world_id 回滚】")
    for q, nm, cls in (("q1", "战士", "战士"), ("q2", "法师", "法师")):
        prep_player(m, "g1", q, nm, cls, level=20)
    ok = db.party_create("g1", "q1", "q2")
    check("真实组队成功", ok, "")
    goto_goblin_entry("g1", "q1", "q2")  # F2：开本需站在副本入口
    await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    wid = db.get_player("g1", "q1").get("world_id", "")
    check("队长开本成功（前置）", str(wid).startswith("inst:"), wid)
    check("队员 world_id 同步 inst:", str(db.get_player("g1", "q2").get("world_id", "")).startswith("inst:"),
          db.get_player("g1", "q2").get("world_id"))
    check("队员同大陆", db.get_player("g1", "q2").get("world_id") == wid, "")
    out = await cmd(m, "party_leave", "g1", "q2", "退队")
    check("退队成功", "退出队伍" in out, out[:150])
    p2 = db.get_player("g1", "q2")
    check("退队后队员 world_id 回 mainland", p2.get("world_id") == "mainland", p2.get("world_id"))
    inst = C.get_instance_world(wid)
    check("退队后大陆实例仍存在（进度保留）", inst is not None, "")
    check("大陆 members 快照保留", inst is not None and "q2" in (inst.get("members") or []), inst)
    check("队长 world_id 仍 inst:", str(db.get_player("g1", "q1").get("world_id", "")).startswith("inst:"),
          db.get_player("g1", "q1").get("world_id"))
    st = (inst or {}).get("st") or {}
    _cleanup_instance(m, "g1", st)


# ============================================================
# 7. 多队并发隔离
# ============================================================

async def check_multi_team_isolation(m):
    print("【7. 多队并发隔离】")
    for q, nm, cls in (("q1", "战士", "战士"), ("q2", "法师", "法师"), ("q3", "弓手", "射手"), ("q4", "牧师", "牧师")):
        prep_player(m, "g1", q, nm, cls, level=20)
    db.party_create("g1", "q1", "q2")
    db.party_create("g1", "q3", "q4")
    # 队 A 开本（F2：开本需站在副本入口）
    goto_goblin_entry("g1", "q1", "q2")
    outA = await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    widA = db.get_player("g1", "q1").get("world_id", "")
    check("队A开本成功", "副本开启" in outA, outA[:150])
    check("队A world_id inst:", str(widA).startswith("inst:"), widA)
    # 队 B 开本（F2：队 B 也要站入口）
    goto_goblin_entry("g1", "q3", "q4")
    outB = await cmd(m, "instance_cmd", "g1", "q3", "副本 哥布林营地")
    widB = db.get_player("g1", "q3").get("world_id", "")
    check("队B开本成功", "副本开启" in outB, outB[:150])
    check("队B world_id inst:", str(widB).startswith("inst:"), widB)
    check("两队 world_id 不同", widA != widB, f"{widA} vs {widB}")
    instA = C.get_instance_world(widA)
    instB = C.get_instance_world(widB)
    check("两队大陆各自存在", instA is not None and instB is not None, "")
    check("队A大陆 members=q1,q2", sorted(instA.get("members") or []) == ["q1", "q2"], instA.get("members"))
    check("队B大陆 members=q3,q4", sorted(instB.get("members") or []) == ["q3", "q4"], instB.get("members"))
    stA = (instA or {}).get("st") or {}
    stB = (instB or {}).get("st") or {}
    check("队A st 独立 world_id", stA.get("world_id") == widA, stA.get("world_id"))
    check("队B st 独立 world_id", stB.get("world_id") == widB, stB.get("world_id"))
    check("队A battle 镜像未被队B覆盖", (db.get_battle("g1", "q1") or {}).get("state", {}).get("world_id") == widA,
          (db.get_battle("g1", "q1") or {}).get("state", {}).get("world_id"))
    check("队B q4 world_id 同步 inst:", str(db.get_player("g1", "q4").get("world_id", "")).startswith("inst:"),
          db.get_player("g1", "q4").get("world_id"))
    # 队B 队员 q4 移动（应被"队长带队"拦截，证明其位置在队B大陆、而非队A大陆串台）
    out = await cmd(m, "move", "g1", "q4", "移动 篝火营地")
    check("队B队员移动被队长带队拦截", "队长带队" in out, out[:120])
    check("q4 仍在队B大陆入口", db.get_player("g1", "q4").get("cur_subarea") == "goblin_camp_1",
          db.get_player("g1", "q4").get("cur_subarea"))
    # 队A 大陆 rooms 与队B 大陆 rooms 独立（互不干扰）
    check("两队大陆 rooms 独立对象", (instA or {}).get("rooms") is not (instB or {}).get("rooms"), "")
    _cleanup_instance(m, "g1", stA)
    _cleanup_instance(m, "g1", stB)


# ============================================================
# 8. 失败回城 → 大陆销毁（补充）
# ============================================================

async def check_fail_destroy(m):
    print("【8. 失败回城→大陆销毁】")
    # 独立玩家（不与前面用例复用 q1 的队伍残留）
    make_player("g1", "z1", name="独狼", cls="战士", level=20)
    p = db.get_player("g1", "z1")
    db.update_player("g1", "z1", hp=p["max_hp"], mp=p["max_mp"], level=20, gold=5000,
                     cur_map="oak_town", cur_subarea="oak_town_1")
    goto_goblin_entry("g1", "z1")  # F2：开本需站在副本入口
    await cmd(m, "instance_cmd", "g1", "z1", "副本 哥布林营地")
    wid = db.get_player("g1", "z1").get("world_id", "")
    check("开本成功（前置）", str(wid).startswith("inst:"), wid)
    # 探索遇怪
    out = ""
    for _ in range(8):
        out = await cmd(m, "explore", "g1", "z1", "探索")
        b = db.get_battle("g1", "z1")
        if b and (b["state"].get("enemies") or b["state"].get("boss")):
            break
    b = db.get_battle("g1", "z1")
    check("遇怪进入战斗（前置）", b is not None and len(b["state"].get("enemies") or []) > 0, out[:120])
    st = b["state"]
    # 压敌方 1（防反击打死玩家），玩家快照与 DB 血量都压 0 —— 模拟全队空血
    # N5b4-6/R4：副本行动从「大陆权威 st」（C.get_instance_st）恢复（router 4.1a），
    # 只改 db battle 行副本会被权威覆盖（"死不了"）。权威 st 与 db 行同源同步压。
    _wid = st.get("world_id") or ""
    _live = None
    if str(_wid).startswith("inst:"):
        try:
            _live = C.get_instance_st(_wid)
        except Exception:
            _live = None
    _targets = []
    if _live is not None:
        _targets.append(_live)
    _targets.append(st)
    for _t in _targets:
        _bsides = (_t.get("battle") or {}).get("sides") or {}
        for eu in (_bsides.get("enemy") or _t.get("enemies") or []):
            eu["hp"] = 1
            eu["atk"] = 1
            eu["matk"] = 1
            eu["ct"] = -99999.0
        for eu in (_t.get("enemies") or []):
            eu["hp"] = 1
            eu["atk"] = 1
            eu["matk"] = 1
            eu["ct"] = -99999.0
        for pa in (_bsides.get("player") or []):
            pa["hp"] = 0
            _q = str(pa.get("qq_id") or "")
            _t.setdefault("alive", {})[_q] = False
        for mk, snap in (_t.get("players") or {}).items():
            snap["hp"] = 0
            _t.setdefault("alive", {})[mk] = False
        _t["turn_time"] = int(time.time())
    if _live is not None:
        db.save_battle("g1", "z1", _live)
    else:
        db.save_battle("g1", "z1", st)
    db.update_player("g1", "z1", hp=0)
    if _live is not None:
        db.save_battle("g1", "z1", _live)
    cur = (_live or st)["members"][0]
    try:
        from content.flow import instance_battle as _IB
        nxt = _IB.next_actor_key(_live or st)
        if nxt:
            cur = nxt
    except Exception:
        pass
    out = await cmd(m, "attack", "g1", cur, "攻击")
    check("失败输出", "副本失败" in out or "全灭" in out, out[:200])
    p = db.get_player("g1", "z1")
    check("失败后 world_id 回 mainland", p.get("world_id") == "mainland", p.get("world_id"))
    check("失败后大陆销毁", C.get_instance_world(wid) is None, "")
    check("失败后 battle 已清", db.get_battle("g1", "z1") is None, "")


# ============================================================
# 9. 孤儿大陆自愈（v141 instance_cmd 入口）
# ============================================================

async def check_orphan_heal(m):
    print("【9. 孤儿大陆自愈】")
    prep_player(m, "g1", "q1", "战士", "战士", level=20)
    goto_goblin_entry("g1", "q1")  # F2：开本需站在副本入口
    await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    wid = db.get_player("g1", "q1").get("world_id", "")
    check("开本成功（前置）", str(wid).startswith("inst:"), wid)
    # 模拟异常路径：大陆销毁但 world_id 残留（正常离开会同时回滚，这里人为制造孤儿）
    C.destroy_instance_world(wid)
    check("大陆已销毁（前置）", C.get_instance_world(wid) is None, "")
    check("world_id 残留 inst:（前置）", str(db.get_player("g1", "q1").get("world_id", "")).startswith("inst:"),
          db.get_player("g1", "q1").get("world_id"))
    # 任意 instance_cmd 入口触发自愈
    out = await cmd(m, "instance_cmd", "g1", "q1", "副本")
    p = db.get_player("g1", "q1")
    check("自愈后 world_id 回 mainland", p.get("world_id") == "mainland", p.get("world_id"))
    # 自愈后正常出副本列表（不进入任何战斗/地图模式）
    check("自愈后入口正常出列表", ("副本" in out and "开本" not in out) or "没有" in out, out[:150])
    # 收尾清锁（自愈路径未解锁）
    try:
        m._unlock_battle("g1", "q1")
        db.clear_battle("g1", "q1")
    except Exception:
        pass


# ============================================================
# main
# ============================================================

async def main():
    clean_db()
    m = Main(None)
    check_position()
    await check_world_crud(m)
    await check_start_world(m)
    await check_retreat_keep(m)
    await check_leave_destroy(m)
    await check_party_leave_rollback(m)
    await check_multi_team_isolation(m)
    await check_fail_destroy(m)
    await check_orphan_heal(m)

    print(f"\n======== 结果: {passed} 通过 / {failed} 失败 ========")
    if known_fail:
        print(f"⚠️  KNOWN-FAIL {len(known_fail)} 项（不计入失败数，供主 agent 修复）：")
        for name, detail in known_fail:
            print(f"  - {name}: {detail}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
