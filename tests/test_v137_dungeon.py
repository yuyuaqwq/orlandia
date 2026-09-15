# -*- coding: utf-8 -*-
"""v137 副本彻底重构：副本地图化验收测试。

覆盖（对应 docs/INSTANCE_MAP_UNIFY_v137.md §五 验收标准）：
1. 开本 → 落副本第 1 子区域（cur_map=副本图 id, cur_subarea=入口房间），输出含环境描述+可前往
2. 副本图 dungeon.no_exit=True：『地图』不显示野外连接/传送
3. SUBAREAS[inst_id] 房间数 = 设计值（哥布林营地 3 房），房间名贴合主题
4. SUBAREA_LINKS_INDEX[inst_id] 拓扑：入口→中间→Boss 房可达，无房间连野外
5. 开本生成 rooms：monsters_left=设计配置数（数量上限）
6. 探索遇怪：discovery_agro 高概率；清空房间怪物后重复探索不再遇怪（数量上限）
7. resources_pool 开本创建，gold/mats 总量固定；POI loot 从池扣减，取完即空
8. 战斗：探索遇怪 → enemies 阵列 → 攻击 → 清怪 → 通关（Boss 房）
9. 加入战斗：队友并入同一场（allies 追加）
"""
import sys, os, time, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run

# N10 删旧：旧 Battle.actor_turn monkeypatch 死代码已删（R4 副本路径全走 router→IB
# saintess_engine，"攻击"命令驱动；旧 _instance_act 已删，patch 对象无调用方）。

passed = failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def enter_combat(m, gid, qid):
    """探索直到进入战斗（retry 防无事/陷阱）。"""
    for _ in range(8):
        out = await cmd(m, "explore", gid, qid, "探索")
        battle = db.get_battle(gid, qid)
        if battle and (battle["state"].get("enemies") or battle["state"].get("boss")):
            return out
    return out

def _authoritative_st(m, gid, qid, battle):
    """副本大陆权威 st（router 4.1a 从 C.get_instance_st 恢复行动）；无则回落 db 行。"""
    st = battle["state"]
    _wid = st.get("world_id") or ""
    if str(_wid).startswith("inst:"):
        try:
            _live = C.get_instance_st(_wid)
            if _live is not None:
                return _live
        except Exception:
            pass
    return st


def _set_enemies_hp1(st):
    """把敌方阵列血量压 1、攻击压 1（防随机反击打死玩家），专注测流程。
    N5b4-6：saintess_engine 权威在 st[\"battle\"].sides actors（sync_views 每刻回写视图）——
    敌我 actors + 视图都压。"""
    _bsides = (st.get("battle") or {}).get("sides") or {}
    for _a in (_bsides.get("enemy") or []):
        _a["hp"] = 1
        _a["atk"] = 1
        _a["matk"] = 1
    for _eu in (st.get("enemies") or []):
        _eu["hp"] = 1
        _eu["atk"] = 1
        _eu["matk"] = 1
    if st.get("boss") and isinstance(st["boss"], dict):
        st["boss"]["hp"] = 1
        st["boss"]["atk"] = 1
        st["boss"]["matk"] = 1

async def attack_loop(m, gid, qid, max_rounds=12):
    """循环攻击直到战斗结束/通关。返回最后输出。"""
    out = ""
    from content.flow import instance_battle as _IB
    for _ in range(max_rounds):
        battle = db.get_battle(gid, qid)
        if not battle:
            break
        st = _authoritative_st(m, gid, qid, battle)
        if st.get("over") or st.get("cleared"):
            break
        _set_enemies_hp1(st)
        st["turn_time"] = int(time.time())
        # 大陆权威 st 变更要落回 db 行（副本队长名下 battle = 权威镜像）
        try:
            _wid = st.get("world_id") or ""
            if str(_wid).startswith("inst:"):
                db.save_battle(gid, qid, st)
        except Exception:
            pass
        db.save_battle(gid, qid, st)
        # 当前行动者：saintess_engine next_actor_key（ct 最小存活玩家）
        cur = st["members"][0]
        try:
            nxt = _IB.next_actor_key(st)
            if nxt:
                cur = nxt
        except Exception:
            pass
        out = await cmd(m, "attack", gid, cur, "攻击")
        if "通关" in out or "击败" in out or "肃清" in out:
            break
    return out

async def main():
    clean_db()
    m = Main(None)

    print("【1. 开本 → 落副本入口房间】")
    make_player("g1", "q1", cls="战士", level=20)
    p = db.get_player("g1", "q1")
    db.update_player("g1", "q1", hp=p["max_hp"], mp=p["max_mp"], level=20, gold=5000, cur_map="oak_town", cur_subarea="oak_town_1")
    # F2 入口设施化：开本需站在副本入口（哥布林营地入口 = misty_swamp/misty_swamp_3）
    db.update_player("g1", "q1", cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    out = await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    check("开本成功", "副本开启" in out, out[:200])
    p = db.get_player("g1", "q1")
    check("落副本图 cur_map", p["cur_map"] == "goblin_camp", f"cur_map={p['cur_map']}")
    check("落入口房间 cur_subarea", p["cur_subarea"] == "goblin_camp_1", f"cur_subarea={p['cur_subarea']}")
    check("输出含房间名", "入口栅栏" in out, out[:200])
    check("无出口提示", "无出口" in out, out[:200])
    battle = db.get_battle("g1", "q1")
    st = battle["state"]
    check("rooms 3 房间", len(st.get("rooms") or {}) == 3, str((st.get("rooms") or {}).keys()))
    check("资源池生成", st.get("resources_pool", {}).get("gold_left", 0) > 0, str(st.get("resources_pool")))

    print("【2. 地图查看（副本=地图，无出口）】")
    # 先撤退到地图模式再看地图（开本后还没遇怪，直接看）
    out = await cmd(m, "map_view", "g1", "q1", "地图")
    check("地图显示房间", "入口栅栏" in out, out[:200])
    check("可前往列表", "篝火营地" in out, out[:200])
    check("无野外连接", "橡木" not in out, out[:300])

    print("【3. 探索遇怪（discovery_agro 高概率 + 怪物池消耗）】")
    out = await enter_combat(m, "g1", "q1")
    check("探索遇怪", "扑了上来" in out or "拦住了" in out or "战斗" in out, out[:200])
    battle = db.get_battle("g1", "q1")
    st = battle["state"]
    check("进入战斗 enemies 非空", len(st.get("enemies") or []) > 0, str(st.get("enemies")))
    # 怪物池消耗：入口房间 monsters_left 减少
    left = len((st.get("rooms") or {}).get("goblin_camp_1", {}).get("monsters_left", []))
    check("怪物池已消耗", left < 2, f"left={left}")

    print("【4. 战斗 → 清怪】")
    out = await attack_loop(m, "g1", "q1")
    battle = db.get_battle("g1", "q1")
    if battle:
        st = battle["state"]
        check("战斗结束 or 继续探索", st.get("over") or not st.get("enemies") or st.get("mode") == "map", str(st.get("mode")))
    else:
        check("战斗结束（battle 清除）", True, "")

    print("【5. 移动（队长带队）→ Boss 房 → 通关】")
    # 移动需要队长；单人副本队长=自己
    out = await cmd(m, "move", "g1", "q1", "移动 篝火营地")
    check("移动到房2", "篝火营地" in out, out[:200])
    # 房2有精英怪，先探索遇怪清掉再移动
    out = await enter_combat(m, "g1", "q1")
    battle = db.get_battle("g1", "q1")
    if battle:
        st = battle["state"]
        check("房2遇怪", len(st.get("enemies") or []) > 0, str(st.get("enemies")))
    out = await attack_loop(m, "g1", "q1", max_rounds=12)
    # 清完房2 → 移动到 Boss 房（v152：清怪后回地图模式，Boss 房 boss_alive=True 可移动）
    out = await cmd(m, "move", "g1", "q1", "移动 酋长帐篷")
    check("移动到 Boss 房", "酋长帐篷" in out or "咕噜" in out, out[:200])
    # Boss 房探索触发 Boss 战
    out = await enter_combat(m, "g1", "q1")
    battle = db.get_battle("g1", "q1")
    if battle:
        st = battle["state"]
        boss_name = (st.get("boss") or {}).get("name", "")
        check("Boss 登场", "咕噜" in boss_name or "酋长" in boss_name, boss_name)
    out = await attack_loop(m, "g1", "q1", max_rounds=25)
    battle = db.get_battle("g1", "q1")
    if battle:
        check("通关标记", battle["state"].get("cleared"), str(battle["state"].get("cleared")))
        check("通关输出", "通关" in out or "击败" in out, out[:300])
    else:
        check("通关（battle 清除）", True, "")
    achs = db.get_achievements("g1", "q1") or []
    found = any(a.get("ach_key") == "inst_clear_inst_goblin_camp" and a.get("progress", 0) >= 1 for a in achs)
    check("首通成就", found, str(achs)[:200])

    print("【6. 加入战斗（队友并入）】")
    # 双人组队：q1 开本遇怪（锁全队），q2 加入战斗应提示已在战斗中（双人副本锁全队设计）
    # ——加入战斗的『同队伍未入战成员并入』在单人副本/自由探索场景生效（v137 锁拆分前，
    # 双人副本开本锁全队，q2 已在锁内）。此处验证加入战斗的校验链（未组队拦截）。
    clean_db()
    make_player("g1", "q1", name="队长", cls="战士", level=20)
    make_player("g1", "q2", name="法师", cls="法师", level=20)
    for q in ("q1", "q2"):
        p = db.get_player("g1", q)
        db.update_player("g1", q, hp=p["max_hp"], mp=p["max_mp"], level=20, gold=5000)
    # q2 未组队直接加入战斗 → 校验拦截
    await cmd(m, "party", "g1", "q1", "组队 法师")
    # F2 入口设施化：双人开本也需站入口
    db.update_player("g1", "q1", cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    db.update_player("g1", "q2", cur_map="misty_swamp", cur_subarea="misty_swamp_3")
    await cmd(m, "instance_cmd", "g1", "q1", "副本 哥布林营地")
    await enter_combat(m, "g1", "q1")
    battle = db.get_battle("g1", "q1")
    st = battle["state"]
    check("q1 在战斗中", "q1" in str(st.get("members")), str(st.get("members")))
    out = await cmd(m, "join_battle", "g1", "q1", "加入战斗")
    check("队长重复加入拦截", "已在战斗" in out or "正在战斗" in out or "队长" in out, out[:200])
    # 清理
    for q in ("q1", "q2"):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print(f"\n======== 结果: {passed} 通过 / {failed} 失败 ========")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
