# -*- coding: utf-8 -*-
"""v116 阶段四补强验证：场景 PROPS 每日功能（v116 · 高频场所元素带每日小效益）。

补充 v87.12：锻造台/壁炉/药柜之外，再为高频场所元素（酒桶/圣像/雕像）
配『每日 1 次』材料/祝福效果，仍靠 props_use 每日去重防刷。
"""
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
    clean_db()
    db.init_db()
    m = Main(None)

    ev = FakeEvent("g1", "1001", "注册 战士 甲 男")
    await run(m.register, ev)
    check("注册玩家", db.get_player("g1", "1001") is not None)

    # ---- 1) 酒桶（oak_town_4：1吧台 2酒桶 3壁炉）→ 每日给材料 ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_4")
    ev = FakeEvent("g1", "1001", "交互 2")  # 酒桶
    r1 = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  酒桶交互:", r1[:80])
    check("酒桶给材料", ("翻到" in r1 or "摸到" in r1 or "发现" in r1) and "×1" in r1, r1[:80])

    ev = FakeEvent("g1", "1001", "交互 2")
    r2 = "".join(str(x) for x in await run(m.interact_prop, ev))
    check("酒桶每日限制", "今天已经" in r2, r2[:80])

    inv = db.get_inventory("g1", "1001")
    mat_items = [v for v in inv if isinstance(v.get("data"), dict) and v["data"].get("type") in C.MATERIAL_KIND_TYPES]
    check("背包有酒桶材料", len(mat_items) >= 1, str(len(mat_items)))

    # ---- 2) 圣像（white_deer_4：1烛台 2圣像）→ 每日小额祝福回血 ----
    db.update_player("g1", "1001", cur_map="white_deer", cur_subarea="white_deer_4")
    p = db.get_player("g1", "1001")
    db.update_player("g1", "1001", hp=max(1, p["hp"] - 60))
    hurt_hp = db.get_player("g1", "1001")["hp"]
    ev = FakeEvent("g1", "1001", "交互 2")  # 圣鹿神像
    r3 = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  圣像交互:", r3[:100])
    check("圣像祝福回血", "恢复" in r3 and "❤️" in r3, r3[:100])
    p2 = db.get_player("g1", "1001")
    check("HP 增加", p2["hp"] > hurt_hp, f"{hurt_hp}→{p2['hp']}")

    ev = FakeEvent("g1", "1001", "交互 2")
    r4 = "".join(str(x) for x in await run(m.interact_prop, ev))
    check("圣像每日限制", "今天已经" in r4, r4[:80])

    # ---- 3) 雕像（oak_town_2：1雕像 2挂毯 3烛台）→ 每日祝福回血 ----
    db.update_player("g1", "1001", cur_map="oak_town", cur_subarea="oak_town_2")
    p = db.get_player("g1", "1001")
    db.update_player("g1", "1001", hp=50)
    ev = FakeEvent("g1", "1001", "交互 1")  # 橡木开拓者雕像
    r5 = "".join(str(x) for x in await run(m.interact_prop, ev))
    print("  雕像交互:", r5[:100])
    check("雕像祝福回血", "恢复" in r5 and "❤️" in r5, r5[:100])
    p3 = db.get_player("g1", "1001")
    check("雕像 HP 增加", p3["hp"] > 50, f"50→{p3['hp']}")

    ev = FakeEvent("g1", "1001", "交互 1")
    r6 = "".join(str(x) for x in await run(m.interact_prop, ev))
    check("雕像每日限制", "今天已经" in r6, r6[:80])

    # props_use 逐元素去重检查（三个不同元素各自独立计数）
    conn = sqlite3.connect(db.DB_PATH)
    rows = [r[0] for r in conn.execute("SELECT used FROM props_use WHERE qq_id='1001'").fetchall()]
    conn.close()
    keys = "|".join(rows or [])
    check("多元素各自入表", all(k in keys for k in ("oak_town:oak_town_4:ale_barrel", "white_deer:white_deer_4:holy_icon", "oak_town:oak_town_2:statue")), keys)

    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("DELETE FROM players WHERE qq_id='1001'")
    conn.execute("DELETE FROM props_use WHERE qq_id='1001'")
    conn.commit(); conn.close()

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
