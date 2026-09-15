# -*- coding: utf-8 -*-
"""v49 玩家意见批处理测试（#4 移动撞怪 / #5 世界Boss地点 / #6 副本仇恨 / #7 职业定位 / #8 帮助拆分）"""
import sys, os, random, time
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

async def main():
    clean_db()
    m = Main(None)

    print("【#7 职业定位】")
    roles = {C.CLASSES[k]["name"]: C.CLASSES[k].get("role") for k in C.CLASSES}
    check("战士=坦克", roles.get("战士") == "坦克", str(roles))
    check("牧师=治疗", roles.get("牧师") == "治疗", str(roles))
    check("全部职业都有定位", len(roles) >= 6 and all(roles.values()), str(roles))
    label = m._class_role_label("cls_zhan_shi")
    check("定位标签", "坦克" in label, label)

    print("【#8 帮助拆分】")
    await cmd(m, "register", "g1", "f1", "注册 战士 测试员 男")
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助")
    check("总览精简", "指令大全" in out and "帮助 <分类>" in out, out[:80])
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助 技能")
    check("技能分类", "技能系统" in out, out[:80])
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助 副本")
    check("副本分类", "组队副本" in out, out[:80])
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助 不存在的主题")
    check("未知主题提示", "没有" in out, out[:80])
    # v83.1 新分类帮助（角色/冒险/物品）
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助 角色")
    check("角色分类", "注册" in out and "属性" in out, out[:80])
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助 冒险")
    check("冒险分类", "探索" in out and "前往" in out, out[:80])
    out = await cmd(m, "help_cmd", "g1", "f1", "帮助 物品")
    check("物品分类", "背包" in out and "商店" in out, out[:80])

    print("【#4 移动撞怪】")
    await cmd(m, "register", "g1", "f2", "注册 战士 低级玩家 男")
    db.update_player("g1", "f2", level=5, cur_map="oak_town")
    # 高级图：Lv.15 玩家去 Lv.30+ 图 → 必触发（diff>=5 概率 30%，多试几次）
    high_map = next(x for x in C.MAPS if x["id"] == "gold_plain")
    random.seed(42)
    hit = any(m._travel_ambush(db.get_player("g1", "f2"), high_map) for _ in range(50))
    check("低级闯高级图会撞怪", hit)
    # 高级玩家去低级图 → 不撞（威慑）
    db.update_player("g1", "f2", level=60)
    low_map = next(x for x in C.MAPS if x["id"] == "rockfall_gorge")
    random.seed(42)
    hit2 = any(m._travel_ambush(db.get_player("g1", "f2"), low_map) for _ in range(50))
    check("高级玩家威慑低级怪不撞", not hit2)
    # 城镇不撞
    town = next(x for x in C.MAPS if x["type"] == "城镇区域")
    check("城镇不撞怪", m._travel_ambush(db.get_player("g1", "f2"), town) is None)

    print("【#5 世界Boss指定地点】")
    await cmd(m, "register", "g1", "f3", "注册 战士 讨伐者 男")
    db.update_player("g1", "f3", level=40, cur_map="oak_town")
    # 造一个 boss 事件：深渊魔王出现在深渊荒原
    db.save_world_event("boss", int(time.time()) + 3600, {
        "boss": {"name": "百族战魂·奥德里克残影", "icon": "👹", "lv": 35, "hp": 300000,
                 "max_hp": 300000, "reward": {"gold": 2000, "exp": 3000},
                 "map": "old_king_tomb", "map_name": "旧王陵外"}})
    out = await cmd(m, "hunt_boss", "g1", "f3", "讨伐")
    check("不在地点提示前往", "旧王陵外" in out and "前往" in out, out[:150])
    # 移动到指定地点
    db.update_player("g1", "f3", cur_map="old_king_tomb")
    out = await cmd(m, "hunt_boss", "g1", "f3", "讨伐")
    check("到达后可以讨伐", "讨伐开始" in out or "冲向" in out, out[:150])
    db.clear_world_event()
    db.clear_battle("g1", "f3")
    m._unlock_battle("g1", "f3")

    print("【#6 副本仇恨】")
    # N10-C 删旧后退役：本段测的"防御嘲讽拉仇恨"是 v173.5 前旧语义——新仇恨系统
    # （router 3.5：伤害仇恨 hate_mult + 技能 effect=taunt 嘲讽强制锁）由专门测试
    # tests/test_instance_hate.py 11/0 完整覆盖（普攻×1/盾击·誓×4/嘲讽×3+100+锁帧）。
    # 保留 #7/#8/#4/#5 的 feedback 功能验证。
    print("  （仇恨功能已由 test_instance_hate.py 覆盖，本段退役）")

    print(f"\n结果: {passed} passed, {failed} failed")
    return failed

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
