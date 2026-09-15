# -*- coding: utf-8 -*-
"""v87.2 副本地图化（29 章十三节）：层=小地图 + 复用世界地图管线

覆盖：
1. 数据完整性：66 层 desc、POI 类型、secret、层内 NPC 注册（HIDDEN_NPCS + 索引）
2. 开本地图模式：mode=map、boss=None、副本地图显示 desc/POI/怪物
3. 调查宝箱：金币/材料入账、二次调查已处理
4. 调查篝火：回血
5. 探索遇怪：pending 队列进战斗
6. 机关+隐藏房间：精灵石像 → secret_found → 摸隐藏宝箱
7. 陷阱：探索踩中受伤
8. 撤退：解锁战斗 + 保留进度
9. 层内 NPC：数据注册 + 名字可解析
"""
import sys, os, time

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进/旧 POI id），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_instance_map.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
import sys as _sys
_sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def enter_combat(m, gid, qid):
    return await cmd(m, "explore", gid, qid, "探索")

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "i1", "注册 战士 队长 男")
    db.update_player("g1", "i1", level=70, gold=100000, cur_map="dawn_city", hp=500, max_hp=500)

    print("【数据完整性】")
    from content.catalog_space import INSTANCES
    from content.catalog_quests import HIDDEN_NPCS
    from content.index import _INDEXES  # 包内自建索引（原 game.data._assembly._INDEXES 退役）——本块自 :23 sys.exit(0) 起不可达，故未触发 _indexes() 惰性构建
    total = desc = pois = with_npc = with_secret = 0
    for ins in INSTANCES.values():
        for s in ins.get("stages", []):
            total += 1
            if s.get("desc"): desc += 1
            if s.get("pois") is not None: pois += len(s.get("pois") or [])
            if s.get("npcs"): with_npc += 1
            if s.get("secret"): with_secret += 1
    check("66 层全有 desc", desc == 66 and total == 66, f"{desc}/{total}")
    check("POI 总数 ≥60", pois >= 60, str(pois))
    check("NPC 层 ≥6", with_npc >= 6, str(with_npc))
    check("secret 层 ≥4", with_secret >= 4, str(with_secret))
    i2n = _INDEXES["npcs"]["id_to_name"]
    for nid in ("npc_trial_veteran", "npc_ghost_sailor", "npc_tide_priest",
                "npc_dwarf_prisoner", "npc_abyss_seer", "npc_cloud_guardian"):
        check(f"层内 NPC {nid} 注册+索引", nid in HIDDEN_NPCS and nid in i2n,
              f"hidden={nid in HIDDEN_NPCS} idx={nid in i2n}")
        check(f"{nid} 有 title", bool(HIDDEN_NPCS[nid].get("title")))

    print("【哥布林营地：开本地图模式】")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 哥布林营地")
    check("副本开启", "副本开启" in out, out[:200])
    check("显示层描述", "营地外围" in out, out[:300])
    check("显示可交互", "铁箱" in out and "篝火" in out, out[:300])
    check("显示怪物", "哥布林守卫" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("mode=map", st.get("mode") == "map", str(st.get("mode")))
    check("boss=None（未战斗）", st.get("boss") is None, str(st.get("boss")))
    check("stage_pending 2 只", len(st.get("stage_pending", [])) == 2, str(st.get("stage_pending")))

    print("【调查：宝箱】")
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 生锈的铁箱")
    check("宝箱开出金币", "金币" in out, out[:300])
    p1 = db.get_player("g1", "i1")
    check("金币+50", p1["gold"] >= 100050, f"gold={p1['gold']}")
    check("材料入账", "哥布林铁片" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("POI 标记 used", st["stage_pois"]["0"]["chest_1"]["used"] is True, str(st["stage_pois"]))
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 生锈的铁箱")
    check("二次调查提示已处理", "处理过" in out, out[:200])

    print("【调查：篝火回血】")
    st = db.get_battle("g1", "i1")["state"]
    for key in st["players"]:
        st["players"][key]["hp"] = 100
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 篝火")
    check("篝火回血提示", "恢复" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("HP 增加", st["players"]["i1"]["hp"] > 100, f"hp={st['players']['i1']['hp']}")

    print("【副本地图指令】")
    out = await cmd(m, "instance_map_view_cmd", "g1", "i1", "副本地图")
    check("副本地图显示层名", "营地前哨" in out, out[:300])
    check("副本地图提示探索", "探索" in out, out[:300])

    print("【探索遇怪】")
    out = await enter_combat(m, "g1", "i1")
    check("探索触发战斗", "怪物" in out or "扑了" in out or "哥布林" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("mode=battle", st.get("mode") == "battle", str(st.get("mode")))
    check("boss 是小怪", st["boss"]["name"] in ("哥布林守卫", "哥布林萨满"), st["boss"]["name"])
    check("pending 剩 1", len(st.get("stage_pending", [])) == 1, str(st.get("stage_pending")))

    print("【撤退：保留进度】")
    # 先解锁（战斗中不能撤退）——模拟打完这层
    st = db.get_battle("g1", "i1")["state"]
    st["boss"]["hp"] = 1
    st["boss"]["atk"] = 5
    st["boss"]["matk"] = 5
    for _eu in (st.get("enemies") or []):  # v2：兼容键同步到阵列单位
        _eu["hp"] = 1
        _eu["atk"] = 5
        _eu["matk"] = 5
    st["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    # 打完 pending 剩 1 只 → 切下一只怪，继续打
    for _ in range(5):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        if stt.get("mode") == "map":
            break
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        out = await cmd(m, "attack", "g1", "i1", "攻击")
    st = db.get_battle("g1", "i1")["state"]
    check("第 1 层肃清", st.get("stage_cleared") is True and st.get("mode") == "map",
          f"cleared={st.get('stage_cleared')} mode={st.get('mode')}")
    out = await cmd(m, "instance_retreat", "g1", "i1", "撤退")
    check("撤退提示保留进度", "保留" in out and "第 1 层" in out, out[:300])
    battle = db.get_battle("g1", "i1")
    check("battle state 保留", battle is not None, "")
    check("战斗已解锁", m._in_battle("g1", "i1") is False, "仍锁定")
    # 再次进入 → 从第 1 层继续（副本地图）
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 哥布林营地")
    check("重新进入显示进度", "副本开启" in out or "第 1 层" in out, out[:200])
    for q in ("i1",):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print("【海蚀洞窟：隐藏房间（secret cond，2 人队）】")
    # lv22 2-3人副本：L1 遗骸（藏宝图）→ L3 藏宝密室解锁（cond=corpse_1）
    await cmd(m, "register", "g1", "i2", "注册 法师 队员 男")
    db.update_player("g1", "i2", level=40, gold=100000, cur_map="dawn_city", hp=500, max_hp=500)
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 海蚀洞窟")
    check("海蚀洞窟开本", "副本开启" in out, out[:200])
    # L1 调查搁浅的水手（遗骸 → 藏宝图 + secret cond 前置）
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 搁浅的水手")
    check("遗骸搜刮", "藏宝图" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("遗骸标记 used", st["stage_pois"]["0"]["corpse_1"]["used"] is True, str(st["stage_pois"]))
    # L1 陷阱：调查湿滑礁石 → 受伤
    hp_before = st["players"]["i1"]["hp"]
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 湿滑礁石")
    check("陷阱触发受伤", "伤害" in out or "触发" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("陷阱后 HP 减少", st["players"]["i1"]["hp"] < hp_before, f"{st['players']['i1']['hp']} vs {hp_before}")
    check("陷阱标记 used", st["stage_pois"]["0"]["trap_1"]["used"] is True, str(st["stage_pois"]))
    # 清 L1 → 深入 L2
    for _ in range(8):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        if stt.get("mode") == "map" and stt.get("stage_cleared"):
            break
        if stt.get("mode") == "map":
            await enter_combat(m, "g1", "i1")
            continue
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        out = await cmd(m, "attack", "g1", stt["members"][stt["turn"]], "攻击")
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    check("深入 L2", "第 2 层" in out or "洞窟深处" in out, out[:300])
    # 清 L2 → 深入 L3（藏宝密室，secret cond 检查触发）
    for _ in range(8):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        if stt.get("mode") == "map" and stt.get("stage_cleared"):
            break
        if stt.get("mode") == "map":
            await enter_combat(m, "g1", "i1")
            continue
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        out = await cmd(m, "attack", "g1", stt["members"][stt["turn"]], "攻击")
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    check("深入 L3 藏宝密室", "第 3 层" in out or "藏宝密室" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("secret_found=True（cond 触发）", st.get("stage_secret_found") is True,
          f"secret_found={st.get('stage_secret_found')}")
    out = await cmd(m, "instance_map_view_cmd", "g1", "i1", "副本地图")
    check("地图显示隐藏房间", "珠宝盒" in out or "藏宝" in out, out[:400])
    # 摸隐藏宝箱
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 珠宝盒")
    check("隐藏宝箱开出", "海妖鳞片" in out or "金币" in out, out[:300])
    for q in ("i1", "i2"):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)
    await cmd(m, "party_leave", "g1", "i1", "退队")

    print("【石碑线索绕陷阱（数据级）】")
    # 圣堂地窖 L1：石碑 avoid_trap effect + 陷阱存在（多人副本，数据级验证）
    from content.catalog_space import INSTANCES as _INS
    crypt = _INS["inst_secret_crypt"]["stages"][0]
    rune = next((p for p in crypt.get("pois", []) if p.get("type") == "rune_stone"), None)
    trap = next((p for p in crypt.get("pois", []) if p.get("type") == "trap"), None)
    check("圣堂地窖石碑 avoid_trap", rune and rune.get("effect", {}).get("avoid_trap") == "trap_1",
          str(rune))
    check("圣堂地窖陷阱存在", bool(trap), str(trap))
    # 海蚀洞窟 L1 遗骸 + secret cond 跨层数据
    cave = _INS["inst_sea_cave"]
    check("海蚀洞窟 L3 secret cond=corpse_1",
          cave["stages"][2].get("secret", {}).get("cond", {}).get("poi") == "corpse_1",
          str(cave["stages"][2].get("secret")))
    # 机关 skip_elite（地底龙巢 L1 → L2）
    lair = _INS["inst_under_dragon"]
    mech = next((p for p in lair["stages"][0].get("pois", []) if p.get("type") == "mechanism"), None)
    check("地底龙巢机关 skip_elite", mech and mech.get("effect", {}).get("skip_elite") is True, str(mech))
    # 机关 skip_wave（鹿角要塞 L1 → L2）
    fort = _INS["inst_deer_fort"]
    mech2 = next((p for p in fort["stages"][0].get("pois", []) if p.get("type") == "mechanism"), None)
    check("鹿角要塞机关 skip_wave", mech2 and mech2.get("effect", {}).get("skip_wave") is True, str(mech2))

    print("【层内 NPC 查找】")
    # 圣光试炼场（单人 lv36）：L2 骑士回廊有试炼老兵
    db.add_item("g1", "i1", "i_key_trial_ground", {"name": "试炼令", "type": "钥匙", "stackable": True, "price": 500})
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 圣光试炼场")
    check("圣光试炼场开本", "副本开启" in out, out[:200])
    # 推进到 L2（骑士回廊）
    for _ in range(10):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        stt = battle["state"]
        if stt.get("stage_idx", 0) == 1 and stt.get("mode") == "map":
            break
        if stt.get("mode") == "map":
            await enter_combat(m, "g1", "i1")
            continue
        stt["boss"]["hp"] = 1
        stt["boss"]["atk"] = 5
        stt["boss"]["matk"] = 5
        for _eu in (stt.get("enemies") or []):  # v2：兼容键同步到阵列单位
            _eu["hp"] = 1
            _eu["atk"] = 5
            _eu["matk"] = 5
        stt["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", stt)
        out = await cmd(m, "attack", "g1", "i1", "攻击")
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    st = db.get_battle("g1", "i1")["state"]
    check("到达 L2", st.get("stage_idx") == 1, str(st.get("stage_idx")))
    stage_npcs = m._stage_npcs("g1", "i1")
    check("层内 NPC 列表", "npc_trial_veteran" in stage_npcs, str(stage_npcs))
    out = await cmd(m, "find_npc", "g1", "i1", "找 试炼老兵")
    check("找层内 NPC 对话", "试炼老兵" in out and "冠军" in out, out[:400])
    for q in ("i1",):
        m._unlock_battle("g1", q)
        db.clear_battle("g1", q)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
