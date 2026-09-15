# -*- coding: utf-8 -*-
"""v84 房屋升级系统（25 章三）——阶段 4 房产实施

验证：
  1. 地契大厅显示房屋等级/升级条件
  2. 升级：金币不足拦截 / 材料不足拦截 / 成功升级（扣金币+材料+deed_lv+1）
  3. 满级拦截
  4. 回家恢复按等级（Lv.1 50% / Lv.2 100%）
  5. 仓库容量按等级（Lv.1 20 格满拦截；Lv.2 40 格）
  6. 卖房按等级返还（Lv.1 50% / Lv.2 40%）
  7. 无房升级拦截
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
        print(f"  ❌ {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    db.update_player("g1", "w1", level=10, gold=200000, cur_map="oak_town")
    # 给足材料（石材×20 / 精铁×10 / 秘银×5）
    db.add_item("g1", "w1", "mat_shi_cai", {"name": "石材", "type": "材料", "stackable": True}, 20)
    db.add_item("g1", "w1", "mat_jing_tie", {"name": "精铁", "type": "材料", "stackable": True}, 10)
    db.add_item("g1", "w1", "mat_mi_yin", {"name": "秘银", "type": "材料", "stackable": True}, 5)

    print("【v84 买房 + 无房升级拦截】")
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("无房升级拦截", "没有房产" in out, out[:120])
    out = await cmd(m, "deed_buy", "g1", "w1", "买房 1")
    check("买房橡木小屋", "橡木小屋" in out, out[:200])
    out = await cmd(m, "deed_view", "g1", "w1", "地契")
    check("大厅显示 Lv.1 与升级条件", "木屋 Lv.1" in out and "地契 升级" in out, out[:300])

    print("【v84 升级 Lv.1→2】")
    db.update_player("g1", "w1", gold=1000)
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("金币不足拦截", "需要 5000 金币" in out, out[:200])
    db.update_player("g1", "w1", gold=200000)
    # 材料不足：先扣掉石材
    db.remove_item("g1", "w1", "mat_shi_cai", 20)
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("材料不足拦截", "石材×20" in out and "去『挖掘』" in out, out[:200])
    db.add_item("g1", "w1", "mat_shi_cai", {"name": "石材", "type": "材料", "stackable": True}, 20)
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("升级成功石屋", "石屋" in out and "Lv.2" in out, out[:300])
    check("deed_lv=2", db.get_player("g1", "w1").get("deed_lv") == 2, str(db.get_player("g1", "w1").get("deed_lv")))
    check("石材扣减 20", db.count_item("g1", "w1", "石材") == 0, str(db.count_item("g1", "w1", "石材")))
    check("金币扣 5000", db.get_player("g1", "w1")["gold"] == 195000, str(db.get_player("g1", "w1")["gold"]))

    print("【v84 升级 Lv.2→3→4】")
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("升级庄园", "庄园" in out and "Lv.3" in out, out[:300])
    check("精铁扣减", db.count_item("g1", "w1", "精铁") == 0, str(db.count_item("g1", "w1", "精铁")))
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("升级宅邸", "宅邸" in out and "Lv.4" in out and "传送点" in out, out[:300])
    check("秘银扣减", db.count_item("g1", "w1", "秘银") == 0, str(db.count_item("g1", "w1", "秘银")))
    out = await cmd(m, "deed_view", "g1", "w1", "地契 升级")
    check("满级拦截", "满级" in out, out[:120])
    check("deed_lv=4", db.get_player("g1", "w1").get("deed_lv") == 4, str(db.get_player("g1", "w1").get("deed_lv")))

    print("【v84 仓库容量】")
    await cmd(m, "go_home", "g1", "w1", "回家")
    for i in range(10):
        db.add_item("g1", "w1", f"mat_demo_{i}", {"name": f"样品{i}", "type": "材料", "stackable": True}, 1)
    # Lv.4 宅邸容量 160，全部存入不超
    out = ""
    for i in range(10):
        out = await cmd(m, "home_storage", "g1", "w1", f"仓库 样品{i}")
    check("Lv.4 仓库可存 10 件", "10/160" in out or "已存入" in out, out[:200])
    # 新玩家 Lv.1 仓库满 20 拦截
    await cmd(m, "register", "g1", "w2", "注册 法师 米娅 男")
    db.update_player("g1", "w2", level=5, gold=50000, cur_map="oak_town")
    # v104 M09：房产全服唯一·先到先得——橡木小屋已被 w1 持有，w2 改买 2 号地皮（白鹿公寓）
    await cmd(m, "deed_buy", "g1", "w2", "买房 2")
    await cmd(m, "go_home", "g1", "w2", "回家")
    for i in range(20):
        db.add_item("g1", "w2", f"mat_fill_{i}", {"name": f"填满{i}", "type": "材料", "stackable": True}, 1)
        await cmd(m, "home_storage", "g1", "w2", f"仓库 填满{i}")
    db.add_item("g1", "w2", "mat_overflow", {"name": "溢出物", "type": "材料", "stackable": True}, 1)
    out = await cmd(m, "home_storage", "g1", "w2", "仓库 溢出物")
    check("Lv.1 仓库满 20 拦截", "仓库满了" in out and "20/20" in out, out[:200])

    print("【v84 回家恢复按等级】")
    db.update_player("g1", "w1", hp=1, mp=1)
    await cmd(m, "go_out", "g1", "w1", "出门")
    out = await cmd(m, "go_home", "g1", "w1", "回家")
    p = db.get_player("g1", "w1")
    check("Lv.4 回家恢复 100%", p["hp"] == p["max_hp"] and p["mp"] == p["max_mp"], f"hp={p['hp']}/{p['max_hp']}")
    await cmd(m, "go_out", "g1", "w1", "出门")
    # w2 是 Lv.1 → 50%
    db.update_player("g1", "w2", hp=1, mp=1)
    await cmd(m, "go_out", "g1", "w2", "出门")
    out = await cmd(m, "go_home", "g1", "w2", "回家")
    p2 = db.get_player("g1", "w2")
    check("Lv.1 回家恢复 50%", p2["hp"] >= p2["max_hp"] // 2 and p2["hp"] < p2["max_hp"], f"hp={p2['hp']}/{p2['max_hp']}")

    print("【v84 卖房按等级返还】")
    await cmd(m, "go_out", "g1", "w1", "出门")
    out = await cmd(m, "deed_sell", "g1", "w1", "卖房")
    check("Lv.4 卖房返还 20%", "退还 1000 金币" in out and "20%" in out, out[:200])
    await cmd(m, "go_out", "g1", "w2", "出门")
    out = await cmd(m, "deed_sell", "g1", "w2", "卖房")
    # w2 持有白鹿公寓（20000 金币）× Lv.1 返还 50% = 10000
    check("Lv.1 卖房返还 50%", "退还 10000 金币" in out and "50%" in out, out[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
