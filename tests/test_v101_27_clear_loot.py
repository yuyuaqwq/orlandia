"""v101.27 #390 通关停留搜刮测试：战利品堆 / 隐藏暗格墙砖 / 密室宝箱 / 离开副本 / 0 血拦截 / 深入拦截
运行：python tests/test_v101_27_clear_loot.py（从插件根目录用 astrbot python）
"""
import sys, os, time, random

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进/旧 POI id），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_v101_27_clear_loot.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
import sys as _sys
_sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

passed = 0
failed = 0

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

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "i1", "注册 战士 格温 男")
    db.update_player("g1", "i1", level=25, gold=10000, cur_map="iron_harbor_city")

    # 旧王陵（Lv.35 分层副本）单人强制开本（测试直接造状态）
    inst = C.INSTANCES["inst_old_king_tomb"]
    boss = C.build_monster(inst["boss"], {"id": "inst_old_king_tomb", "name": "x", "area": "instance"})
    boss["max_hp"] = int(boss["max_hp"] * 1.6)
    boss["hp"] = boss["max_hp"]
    boss["atk"] = 1
    boss["matk"] = 1
    st = m._instance_build_state("inst_old_king_tomb", inst, ["i1"], boss, int(time.time()), "i1")
    st["players"]["i1"] = {
        "name": "格温", "qq_id": "i1", "class_name": "战士", "level": 25,
        "hp": 500, "max_hp": 500, "mp": 100, "max_mp": 100,
        "atk": 50, "def": 30, "matk": 10, "mdef": 20, "spd": 10,
        "equipment": {}, "skills": [], "learned_skills": [], "class_tier": 0,
        "evolve_path": 0, "attributes": None, "title_bonus": {}, "race": None,
    }
    st["members"] = ["i1"]
    st["acted"] = [False]
    st["turn"] = 0
    # 直接推进到最后一层 Boss 房（第 3 层），清空 pending（无残留怪，杀 Boss 即通关）
    st["stage_idx"] = 2
    st["stage_cleared"] = True
    st["stage_pending"] = []
    st["mode"] = "battle"
    st["boss"] = boss
    st["enemy"] = boss
    st["enemies"] = [dict(boss)]  # v2：敌方阵列（boss/enemy 为兼容键）
    st["round"] = 1
    st["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", st)

    print("【通关结算 + 停留搜刮】")
    # 杀掉 Boss → 通关（v2：Boss mech=summon 会召爪牙，enemies 阵列需全部清空，多次攻击）
    for _ in range(12):
        battle = db.get_battle("g1", "i1")
        if not battle:
            break
        st = battle["state"]
        st["boss"]["hp"] = 1
        st["boss"]["atk"] = 1
        st["boss"]["matk"] = 1
        for _eu in (st.get("enemies") or []):  # v2：兼容键同步到阵列单位（boss/enemies 深拷贝后脱节）
            _eu["hp"] = 1
            _eu["atk"] = 1
            _eu["matk"] = 1
        st["turn_time"] = int(time.time())
        db.save_battle("g1", "i1", st)
        out = await cmd(m, "attack", "g1", "i1", "攻击")
        if "通关" in out:
            break
    check("通关播报", "通关" in out, out[:200])
    check("通关后提示搜刮", "战利品堆" in out, out[:300])
    b = db.get_battle("g1", "i1")
    check("通关后状态保留", b is not None and b["state"].get("cleared"), str(b)[:150])
    st = b["state"]
    check("战利品堆已生成", st.get("loot_pile") is True, str(st.get("loot_pile")))
    check("暗格状态已初始化", "secret_crack" in st and st.get("secret_chest") is None, str(st))

    # 副本地图显示搜刮项
    out = await cmd(m, "instance_map_view_cmd", "g1", "i1", "副本地图")
    check("地图显示战利品堆", "战利品堆" in out, out[:300])

    # 搜刮战利品堆
    gold_before = db.get_player("g1", "i1")["gold"]
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 战利品堆")
    check("战利品堆给金币", "金币 +" in out, out[:200])
    check("战利品堆金币入账", db.get_player("g1", "i1")["gold"] > gold_before, "")
    b = db.get_battle("g1", "i1")
    check("战利品堆已关闭", b["state"].get("loot_pile") is False, "")

    # 深入被拦截
    out = await cmd(m, "instance_advance", "g1", "i1", "深入")
    check("通关后深入拦截", "已通关" in out, out[:150])

    # 探索被拦截
    out = await cmd(m, "explore", "g1", "i1", "探索")
    check("通关后探索拦截", "已通关" in out or "没有敌人" in out, out[:150])

    # 重复搜刮拦截
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 战利品堆")
    check("重复搜刮提示无", "没有" in out, out[:150])

    print("【隐藏暗格墙砖】")
    # 人为打开暗格（强制 secret_crack=True）
    st = db.get_battle("g1", "i1")["state"]
    st["secret_crack"] = True
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 墙砖")
    check("暗格触发守卫战", "精英守卫" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("暗格标记已消费", st.get("secret_crack") is False, "")
    check("守卫战进行中", st.get("mode") == "battle" and st.get("secret_guard_pending") is True, str(st.get("mode")))

    # 打死守卫 → 宝箱出现
    st["boss"]["hp"] = 1
    st["boss"]["atk"] = 1
    st["boss"]["matk"] = 1
    for _eu in (st.get("enemies") or []):  # v2：兼容键同步到阵列单位
        _eu["hp"] = 1
        _eu["atk"] = 1
        _eu["matk"] = 1
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    check("守卫击杀提示宝箱", "神秘宝箱" in out, out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("宝箱已出现", st.get("secret_chest") is True, str(st.get("secret_chest")))
    check("守卫标记已清", st.get("secret_guard_pending") is False, "")

    # 开宝箱（确定性：不依赖随机——直接验证任意结果都在合法集）
    # 合法集（instance.py _instance_secret_chest）：星灵蝶蛋 5% / 图纸残页 45% / 稀有符文 30% / 专属材料 20%
    out = await cmd(m, "instance_investigate", "g1", "i1", "调查 宝箱")
    check("宝箱打开", ("图纸残页" in out) or ("符文" in out) or ("材料" in out) or ("星灵蝶蛋" in out), out[:300])
    st = db.get_battle("g1", "i1")["state"]
    check("宝箱已清", st.get("secret_chest") is None, "")

    print("【离开副本】")
    out = await cmd(m, "instance_leave", "g1", "i1", "离开副本")
    check("离开副本成功", "离开" in out, out[:150])
    b = db.get_battle("g1", "i1")
    check("战斗状态已清", b is None, str(b)[:100])

    print("【0 血进本拦截 #393】")
    db.update_player("g1", "i1", hp=0)
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 哥布林营地")
    check("0 血进本拦截", "生命值为 0" in out, out[:200])
    db.update_player("g1", "i1", hp=500)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


import asyncio
asyncio.run(main())
