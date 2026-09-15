# -*- coding: utf-8 -*-
"""阶段四验证：交互彩蛋（每日 1 次）——锻造台材料/药柜药草/壁炉回血"""
import sys, os, asyncio, sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import FakeEvent, run, clean_db, TEST_DB, Main, db, C

passed = failed = 0
def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def main():
    clean_db()  # 已含 props_use
    db.init_db()
    m = Main(None)

    # 注册玩家
    ev = FakeEvent("g1", "1001", "注册 战士 甲 男")
    await run(m.register, ev)
    p = db.get_player("g1", "1001")
    check("注册玩家", p is not None)

    # 初始位置 oak_town（广场）
    # v87.15 星形可达：移动 2 → 老铁铁匠铺（oak_town_3，有 forge_table/anvil/bellows）
    ev = FakeEvent("g1", "1001", "前往 2")
    await run(m.move, ev)
    p = db.get_player("g1", "1001")
    check("移动到老铁铁匠铺", p["cur_subarea"] == "oak_town_3", str(p.get("cur_subarea")))

    # 交互 1（锻造台）→ 应给材料
    ev = FakeEvent("g1", "1001", "交互 1")
    r = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  锻造台交互:", r[:80])
    check("锻造台给材料", "翻到" in r or "发现" in r or "×1" in r, r[:80])

    inv = db.get_inventory("g1", "1001")
    mat_items = [v for v in inv if isinstance(v.get("data"), dict) and v["data"].get("type") in C.MATERIAL_KIND_TYPES]
    check("背包有材料", len(mat_items) >= 1, str([v.get("data", {}).get("name") for v in inv]))

    # 再交互 1 → 每日限制
    ev = FakeEvent("g1", "1001", "交互 1")
    r2 = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  再次交互:", r2[:80])
    check("每日限制提示", "今天已经" in r2, r2[:80])

    # v87.14 空间连接：场所只连广场 → 先回广场（移动 1）再移动 4 → 草药铺
    ev = FakeEvent("g1", "1001", "前往 1")
    await run(m.move, ev)
    ev = FakeEvent("g1", "1001", "前往 4")
    await run(m.move, ev)
    p = db.get_player("g1", "1001")
    check("移动到草药铺", p["cur_subarea"] == "oak_town_5", str(p.get("cur_subarea")))
    ev = FakeEvent("g1", "1001", "交互 1")
    r3 = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  药柜交互:", r3[:80])
    check("药柜给药草", "翻到" in r3 or "发现" in r3 or "×1" in r3, r3[:80])

    # v87.15 星形可达：移动 3 → 橡木桶旅店（oak_town_4，有 fireplace）——先回广场
    # 先扣血（直接 update_player 模拟受伤）
    p = db.get_player("g1", "1001")
    db.update_player("g1", "1001", hp=max(1, p["hp"] - 50))
    hurt_hp = db.get_player("g1", "1001")["hp"]
    ev = FakeEvent("g1", "1001", "前往 1")
    await run(m.move, ev)
    ev = FakeEvent("g1", "1001", "前往 3")
    await run(m.move, ev)
    # 旅店 PROPS 顺序：1吧台 2酒桶 3壁炉 → 交互 3 命中壁炉
    ev = FakeEvent("g1", "1001", "交互 3")
    r4 = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  壁炉交互:", r4[:100])
    check("壁炉回血", "恢复" in r4 and "❤️" in r4, r4[:100])
    p2 = db.get_player("g1", "1001")
    check("HP 增加", p2["hp"] > hurt_hp, f"{hurt_hp}→{p2['hp']}")

    # 再交互 3 → 每日限制
    ev = FakeEvent("g1", "1001", "交互 3")
    r5 = "".join(str(x) for x in await run(m.interact_prop, ev))
    check("壁炉每日限制", "今天已经" in r5, r5[:80])

    # props_use 表记录检查
    conn = sqlite3.connect(db.DB_PATH)
    row = conn.execute("SELECT used FROM props_use WHERE qq_id='1001'").fetchone()
    conn.close()
    check("props_use 有记录", row is not None and "oak_town" in (row[0] or ""), str(row))

    # 清理测试玩家
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("DELETE FROM players WHERE qq_id='1001'")
    conn.execute("DELETE FROM props_use WHERE qq_id='1001'")
    conn.commit(); conn.close()

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
