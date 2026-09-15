# -*- coding: utf-8 -*-
"""v84 PVP 红名与荣誉商店（26 章）——阶段 4 PVP 实施

验证：
  1. 新手保护：Lv.<10 不能攻击/被攻击
  2. 荣誉商店：列表显示 / 荣誉不足拦截 / 兑换勋章（honor_medal 标记）/ 兑换药剂 / 兑换清除券
  3. PVP 击杀 → 攻击者红名 30 分钟
  4. 红名不能进城镇（移动拦截）
  5. 击杀红名者 → 荣誉 +50
  6. 红名清除券：使用后不再红名
  7. 红名死亡额外掉金币（上限 2000）
"""
import sys, os, sqlite3, time, json
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
        safe = detail.encode("utf-8", "replace").decode("utf-8", "replace") if detail else ""
        print(f"  ❌ {name} {safe}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    import random
    # v181 flaky 修复：PVP 战斗含闪避/暴击随机——固定种子保证 40 轮内分出胜负确定，
    # 避免偶发拖轮超限把"w2 被打败"打成假红
    random.seed(20260909)
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 铁拳 男")
    await cmd(m, "register", "g1", "w2", "注册 法师 米娅 男")
    await cmd(m, "register", "g1", "w3", "注册 刺客 夜莺 男")
    # w1/w2 升到 10+ 级，w3 保持 5 级（新手）
    db.update_player("g1", "w1", level=15, gold=5000, cur_map="misty_swamp")
    db.update_player("g1", "w2", level=15, gold=5000, cur_map="misty_swamp")
    db.update_player("g1", "w3", level=5, gold=5000, cur_map="misty_swamp")

    print("【v84 新手保护】")
    out = await cmd(m, "attack", "g1", "w1", "攻击 夜莺")
    check("攻击新手被拦", "新手保护" in out, out[:200])
    out = await cmd(m, "attack", "g1", "w3", "攻击 铁拳")
    check("新手攻击被拦", "新手保护" in out, out[:200])
    out = await cmd(m, "attack", "g1", "w1", "攻击 米娅")
    check("同级可发起 PVP", "发起攻击" in out, out[:300])

    print("【v84 荣誉商店】")
    out = await cmd(m, "honor_shop", "g1", "w1", "荣誉")
    check("荣誉商店列表", "荣誉商店" in out and "荣誉勋章" in out and "300" in out, out[:300])
    out = await cmd(m, "honor_shop", "g1", "w1", "荣誉 兑换 1")
    check("荣誉不足拦截", "荣誉不足" in out, out[:200])
    db.set_event_state("honor_w1", str(1500))
    out = await cmd(m, "honor_shop", "g1", "w1", "荣誉 兑换 1")
    check("兑换荣誉勋章", "你兑换了" in out and "荣誉勋章" in out, out[:300])
    check("honor_medal 标记", db.get_event_state("honor_medal_w1") == "1", str(db.get_event_state("honor_medal_w1")))
    check("荣誉扣减 1200", db.get_event_state("honor_w1") == "1200", str(db.get_event_state("honor_w1")))
    out = await cmd(m, "honor_shop", "g1", "w1", "荣誉 兑换 3")
    check("兑换荣誉药剂", "你兑换了" in out and "荣誉药剂" in out, out[:300])
    out = await cmd(m, "honor_shop", "g1", "w1", "荣誉 兑换 4")
    check("兑换红名清除券", "你兑换了" in out and "红名清除券" in out, out[:300])
    out = await cmd(m, "honor_shop", "g1", "w1", "荣誉 兑换 9")
    check("无效编号拦截", "没有第 9 件商品" in out, out[:200])
    # 荣誉勋章称号可装备（title 列表 + 装备）
    out = await cmd(m, "titles", "g1", "w1", "称号")
    check("称号列表含荣誉勋章", "荣誉勋章" in out, out[:300])
    out = await cmd(m, "titles", "g1", "w1", "称号 装备 荣誉勋章")
    check("装备荣誉勋章", "佩戴上了称号" in out and "荣誉勋章" in out, out[:300])

    print("【v84 PVP 击杀 → 红名】")
    # w1 攻击 米娅 发起 PVP（轮流制：w1/w2 交替出手直到分出胜负）
    out = await cmd(m, "attack", "g1", "w1", "攻击 米娅")
    out = ""
    for i in range(40):
        who = "w1" if i % 2 == 0 else "w2"
        out = await cmd(m, "attack", "g1", who, "攻击")
        if "被击败了" in out or "击败" in out:
            break
    check("w2 被打败", "被击败了" in out, out[:300])
    check("w1 红名 30 分钟", m._is_redname("w1"), "")
    # 红名不能进城镇（翡翠森林 → 相邻城镇白鹿城被拦）
    db.update_player("g1", "w1", cur_map="emerald_forest")
    out = await cmd(m, "move", "g1", "w1", "前往 白鹿城")
    check("红名进城镇被拦", "守卫" in out and "红名" in out, out[:300])
    # F1 H0-S1：败方同样进入 PVP 袭击 CD（胜方 w1 已在结算处设 CD，本轮败方 w2 也应进入 CD，
    # 阻断两账号交替互杀无限对刷荣誉）。w1 为攻击方，其 CD 在 _pvp_finish 已设。
    check("攻击方 w1 进入袭击 CD", m._pvp_cd_left("w1") > 0, f"cd={m._pvp_cd_left('w1')}")
    check("败方 w2 进入袭击 CD", m._pvp_cd_left("w2") > 0, f"cd={m._pvp_cd_left('w2')}")
    # 二次交替攻击应被 CD 拦下（w2 上轮战败进入 CD，立即再袭击被拒）
    out = await cmd(m, "attack", "g1", "w2", "攻击 铁拳")
    check("战败方立即再袭击被拒", "秒后才能再次袭击" in out, out[:200])

    print("【v84 击杀红名 → 荣誉 +50】")
    # 清理上轮 PVP 双方袭击 CD，避免影响本段荣誉验证（本段目标：击杀红名 +50 荣誉）
    db.set_event_state("pvp_cd_w1", "0")
    db.set_event_state("pvp_cd_w2", "0")
    # w2 复活打红名的 w1（w3 是新手不能攻击，用 w2）
    # v94.1：get_player 会 clamp hp 到 max_hp（#41 修复），hp=99999 作弊不再生效，
    # 因此把红名 w1 的 hp 设为 1，确保 w2 一击必杀（测试意图：击杀红名得荣誉）
    db.update_player("g1", "w2", level=15, gold=5000, hp=99999, mp=99999, cur_map="misty_swamp")
    db.update_player("g1", "w1", level=15, gold=5000, hp=1, mp=100, cur_map="misty_swamp")
    honor_before = m._get_honor("w2")
    out = await cmd(m, "attack", "g1", "w2", "攻击 铁拳")
    out = ""
    for i in range(40):
        who = "w2" if i % 2 == 0 else "w1"
        out = await cmd(m, "attack", "g1", who, "攻击")
        if "被击败了" in out or "击败" in out:
            break
    honor_after = m._get_honor("w2")
    check("击杀红名荣誉 +50", honor_after - honor_before == 50, f"before={honor_before} after={honor_after}")

    print("【v84 红名清除券】")
    check("w1 当前红名", m._is_redname("w1"), "")
    # w1 之前兑换过清除券（在背包里）
    out = await cmd(m, "use", "g1", "w1", "使用 红名清除券")
    check("清除券生效", "不再是红名" in out, out[:300])
    check("w1 已洗白", not m._is_redname("w1"), "")

    print("【v84 红名死亡额外掉损】")
    db.set_event_state(f"red_w2", str(int(time.time()) + 3600))
    db.update_player("g1", "w2", gold=50000, hp=100, mp=100, cur_map="misty_swamp")
    # 直接迭代 _handle_defeat 模拟红名死亡（普通 generator）
    p2 = db.get_player("g1", "w2")
    ev = FakeEvent("g1", "w2", "攻击")
    out = ""
    for r in m._handle_defeat(ev, "g1", "w2", p2, {"name": "野狼"}, "你被击败了"):
        out = r if r else out
    check("红名死亡提示", "额外损失" in out, out[:300])
    check("红名死亡扣 10%", db.get_player("g1", "w2")["gold"] == 43000, str(db.get_player("g1", "w2")["gold"]))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
