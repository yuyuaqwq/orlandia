# -*- coding: utf-8 -*-
"""commands 层：v68 地契房产系统

验证：
  1. 地契大厅：在售列表 / 无房提示
  2. 买房：金币扣减 / 已有房拦截 / 金额不足
  3. 回家/出门：无房拦截 / 进入家地图 / 出门回城镇
  4. 家地图：map_view 定制面板 / 探索在家拦截 / 找 NPC 在家拦截
  5. 仓库：存取 / 非家地图拦截 / 取出
  6. 拜访：无房玩家去不了 / 进入对方家 / 家地图显示对方名字
  7. 铺面：家里摆摊 / 家面板显示摊位 / 当面购入
  8. 卖房：退一半 / 无房拦截
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
    await cmd(m, "register", "g1", "w2", "注册 法师 米娅 男")
    db.update_player("g1", "w1", level=5, gold=5000, cur_map="oak_town")
    db.update_player("g1", "w2", level=5, gold=100, cur_map="oak_town")

    print("【v68 地契：大厅】")
    out = await cmd(m, "deed_view", "g1", "w1", "地契")
    check("在售地皮列表", "橡木小屋" in out and "5000 金币" in out, out[:200])
    check("提示买房", "买房 <编号>" in out, out[:200])

    print("【v68 地契：买房】")
    out = await cmd(m, "deed_buy", "g1", "w1", "买房 1")
    check("买房成功", "恭喜置业" in out and "橡木小屋" in out, out[:200])
    check("金币扣减", db.get_player("g1", "w1")["gold"] == 0, str(db.get_player("g1", "w1")["gold"]))
    check("deed 已记录", db.get_player("g1", "w1").get("deed") == "prop_oak_01", str(db.get_player("g1", "w1").get("deed")))
    check("deed_lv 初始 1", db.get_player("g1", "w1").get("deed_lv") == 1, str(db.get_player("g1", "w1").get("deed_lv")))
    out = await cmd(m, "deed_buy", "g1", "w1", "买房 2")
    check("已有房拦截", "已经有一张地契" in out, out[:120])
    out = await cmd(m, "deed_view", "g1", "w1", "地契")
    check("地契大厅显示我的房产", "我的地契" in out and "回家" in out and "木屋 Lv.1" in out, out[:200])
    # 金币不足
    out = await cmd(m, "deed_buy", "g1", "w2", "买房 1")
    check("金币不足拦截", "需要 5000 金币" in out, out[:120])

    print("【v68 回家/出门】")
    out = await cmd(m, "go_home", "g1", "w2", "回家")
    check("无房回家拦截", "没有房产" in out, out[:120])
    out = await cmd(m, "go_home", "g1", "w1", "回家")
    check("回家成功", "回到了自己的家" in out, out[:120])
    check("在地图home", db.get_player("g1", "w1")["cur_map"] == "home_w1", str(db.get_player("g1", "w1")["cur_map"]))
    out = await cmd(m, "map_view", "g1", "w1", "地图")
    check("家地图面板", "我的家" in out and "木屋 Lv.1" in out and "铺面空着" in out and "仓库" in out, out[:300])
    out = await cmd(m, "explore", "g1", "w1", "探索")
    check("在家不能探索", "安心休息" in out, out[:120])
    out = await cmd(m, "find_npc", "g1", "w1", "找")
    check("在家找不到NPC", "家里没有 NPC" in out, out[:120])
    out = await cmd(m, "go_out", "g1", "w1", "出门")
    check("出门回城镇", "回到" in out and "橡木镇" in out, out[:120])
    check("回城镇地图", db.get_player("g1", "w1")["cur_map"] == "oak_town", str(db.get_player("g1", "w1")["cur_map"]))
    out = await cmd(m, "go_out", "g1", "w1", "出门")
    check("不在家出门提示", "不在家里" in out, out[:120])

    print("【v68 仓库】")
    db.add_item("g1", "w1", "mat_lang_pi", {"name": "狼皮", "type": "材料", "stackable": True}, 3)
    out = await cmd(m, "home_storage", "g1", "w1", "仓库")
    check("非家地图仓库拦截", "先『回家』" in out, out[:120])
    await cmd(m, "go_home", "g1", "w1", "回家")
    out = await cmd(m, "home_storage", "g1", "w1", "仓库 狼皮")
    check("存入成功", "已存入仓库" in out and "狼皮" in out, out[:120])
    check("背包扣减", db.count_item("g1", "w1", "狼皮") == 2, "")
    out = await cmd(m, "home_storage", "g1", "w1", "仓库")
    check("仓库列表", "狼皮" in out and "1." in out, out[:200])
    out = await cmd(m, "home_storage_take", "g1", "w1", "取出 1")
    check("取出成功", "取出【狼皮】" in out, out[:120])
    check("背包恢复", db.count_item("g1", "w1", "狼皮") == 3, "")

    print("【v68 拜访】")
    out = await cmd(m, "visit_home", "g1", "w1", "拜访 米娅")
    check("无房玩家拜访拦截", "还没有房产" in out, out[:120])
    out = await cmd(m, "visit_home", "g1", "w2", "拜访 旅人")
    check("拜访成功", "走进了 旅人 的家" in out, out[:120])
    check("在对方家", db.get_player("g1", "w2")["cur_map"] == "home_w1", str(db.get_player("g1", "w2")["cur_map"]))
    out = await cmd(m, "map_view", "g1", "w2", "地图")
    check("对方家面板", "旅人的家" in out, out[:300])
    out = await cmd(m, "go_out", "g1", "w2", "出门")
    check("拜访后出门", "回到" in out, out[:120])

    print("【v68 铺面（家里摆摊）】")
    db.add_item("g1", "w1", "eq_home_sword", {"name": "家传铁剑", "type": "武器", "slot": "weapon",
                                              "quality": "blue", "lv": 5, "atk": 20, "stackable": False}, 1)
    # v104R3 P2：铺面挂机位按房屋等级（木屋 0/石屋 1/庄园 2/宅邸 3）——木屋摆摊应被拦截，
    # 先验证拦截，再升级到石屋(Lv.2)验证摆摊成功（25 章房产案对齐）
    await cmd(m, "go_home", "g1", "w1", "回家")
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 家传铁剑 800")
    check("木屋无挂机位摆摊被拦截", "没有铺面挂机位" in out, out[:200])
    db.update_player("g1", "w1", deed_lv=2)
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 家传铁剑 800")
    check("石屋摆摊成功", "『家里』" in out and "800" in out, out[:200])
    out = await cmd(m, "map_view", "g1", "w1", "地图")
    check("家面板显示铺面", "铺面摊位" in out and "家传铁剑" in out, out[:300])
    # 当面买（w2 拜访 → 购入）
    db.update_player("g1", "w2", gold=2000)
    await cmd(m, "visit_home", "g1", "w2", "拜访 旅人")
    stalls = db.market_list("g1", "home_w1")
    check("铺面摊位入库", len(stalls) == 1, str(stalls))
    mid = stalls[0]["id"]
    out = await cmd(m, "market_buy", "g1", "w2", f"购入 {mid}")
    check("拜访后当面购入", "购入成功" in out and "家传铁剑" in out, out[:200])
    await cmd(m, "go_out", "g1", "w2", "出门")

    print("【v68 卖房】")
    out = await cmd(m, "deed_sell", "g1", "w2", "卖房")
    check("无房卖房拦截", "没有房产" in out, out[:120])
    await cmd(m, "go_out", "g1", "w1", "出门")
    db.update_player("g1", "w1", deed_lv=1)  # v104R3 P2：铺面测试升过石屋，卖房返还按木屋 50% 校验
    out = await cmd(m, "deed_sell", "g1", "w1", "卖房")
    check("卖房按等级返还", "退还 2500 金币" in out, out[:120])
    check("deed 清空", db.get_player("g1", "w1").get("deed") == "", str(db.get_player("g1", "w1").get("deed")))
    out = await cmd(m, "go_home", "g1", "w1", "回家")
    check("卖房后回家拦截", "没有房产" in out, out[:120])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
