# -*- coding: utf-8 -*-
"""v168 冒险手册：曾拥有物品(possessed)埋点 + 冒险手册/足迹指令测试。

覆盖：
1. add_item 入包 → possessed 记录（材料/消耗品/装备 uuid→原型归一）
2. 重复 add / remove 后不回退
3. 市场买入（_inv_upsert 路径）→ 买入方 possessed 记录
4. 『冒险手册』总览 / 『足迹』 / 『冒险手册 物品』 / 『冒险手册 怪物』 / 『图鉴』别名
"""
import sys, os, asyncio
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

def test_possessed_basic():
    """add_item 埋点 + 幂等 + 移除不回退"""
    clean_db()
    db.init_db()
    # 材料
    db.add_item("g1", "q1", "mat_tie_kuang_shi",
                {"name": "铁矿石", "type": "矿石", "stackable": True, "price": 5}, 12)
    # 消耗品
    db.add_item("g1", "q1", "i_treatment_potion",
                {"name": "治疗药水", "type": "消耗品", "stackable": True, "price": 20}, 2)
    p = db.get_possessed("q1")
    check("材料+消耗品入包即记", "mat_tie_kuang_shi" in p and "i_treatment_potion" in p, str(p))
    # 重复 add 幂等（count 不重复）
    db.add_item("g1", "q1", "mat_tie_kuang_shi",
                {"name": "铁矿石", "type": "矿石", "stackable": True, "price": 5}, 3)
    p2 = db.get_possessed("q1")
    check("重复 add 幂等", len(p2) == 2, str(p2))
    # 移除后不回退
    db.remove_item("g1", "q1", "mat_tie_kuang_shi", 5)
    p3 = db.get_possessed("q1")
    check("remove 后 possessed 不回退", "mat_tie_kuang_shi" in p3, str(p3))

def test_possessed_equip_uuid():
    """装备 uuid 实例 → 原型 key 归一"""
    clean_db()
    db.init_db()
    db.add_item("g1", "q1", "eq_72d48ebe",
                {"name": "铁剑", "slot": "weapon", "type": "装备", "quality": "white", "lv": 2})
    p = db.get_possessed("q1")
    check("装备 uuid 归一到原型 eq_tie_jian", "eq_tie_jian" in p and len(p) == 1, str(p))
    # 再拿一把同款（新 uuid）不重复
    db.add_item("g1", "q1", "eq_a1b2c3d4",
                {"name": "铁剑", "slot": "weapon", "type": "装备", "quality": "white", "lv": 2})
    p2 = db.get_possessed("q1")
    check("同原型重复 uuid 幂等", len(p2) == 1, str(p2))

def test_possessed_market_buy():
    """市场买入：买家从未 add_item，经 _inv_upsert 获得 → possessed 有记录"""
    clean_db()
    db.init_db()
    # 卖家挂单（卖家有金币要求无关；直接 market_add）
    it_data = {"name": "精铁", "type": "矿石", "stackable": True, "price": 100}
    db.market_add("g1", "sellerA", "mat_jing_tie", it_data, 100, map_id="oak_plain")
    mid = db.market_list_by_seller("g1", "sellerA")[0]["id"]
    # 买家（需玩家+金币）
    from conftest import make_player
    make_player("g1", "buyerB", name="买家", cls="战士", level=5)
    db.update_player("g1", "buyerB", gold=1000)
    ok, msg, item_name = db.market_buy_atomic("g1", "buyerB", mid)
    check("市场买入成功", ok, f"{msg}")
    p = db.get_possessed("buyerB")
    check("买家 possessed 有精铁", "mat_jing_tie" in p, str(p))
    # 卖家也应有（他 add_item 过——但测试里卖家没 add 直接挂单，所以没有也合理；只需验证买家侧）
    inv = db.get_inventory("g1", "buyerB")
    check("物品真入买家包", any(i["key"] == "mat_jing_tie" for i in inv), str([i["key"] for i in inv]))

async def test_commands():
    """指令层：冒险手册/足迹/图鉴别名"""
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    db.update_player("g1", "e1", cur_map="oak_town", cur_subarea="oak_town_3", level=5, gold=1000)
    # 埋数据
    db.add_item("g1", "e1", "mat_tie_kuang_shi",
                {"name": "铁矿石", "type": "矿石", "stackable": True, "price": 5}, 12)
    db.add_item("g1", "e1", "eq_72d48ebe",
                {"name": "铁剑", "slot": "weapon", "type": "装备", "quality": "white", "lv": 2})
    db.add_visited_subarea("g1", "e1", "oak_town", "oak_town_1")
    db.add_visited_subarea("g1", "e1", "oak_plain", "oak_plain_1")
    db.bump_bestiary("g1", "e1", "绿史莱姆")
    db.bump_bestiary("g1", "e1", "绿史莱姆")

    # 总览
    out = await cmd(m, "adventure_book", "g1", "e1", "冒险手册")
    check("总览有足迹", "足迹" in out and "1/" in out, out[:200])
    check("总览有怪物", "怪物" in out and "绿史莱姆" not in out and "1/345" in out, out[:200])
    check("总览有物品", "曾拥有" in out and "2 种" in out, out[:200])
    # 足迹
    out = await cmd(m, "footprint", "g1", "e1", "足迹")
    check("足迹含南境+橡木镇", "南境" in out and "橡木镇" in out and "冒险者广场" in out, out[:300])
    check("足迹含首访日期", "(0" in out or "月" in out or "(" in out, out[:300])
    # 冒险手册 区域 = 足迹
    out2 = await cmd(m, "adventure_book", "g1", "e1", "冒险手册 区域")
    check("冒险手册 区域 = 足迹", "我的足迹" in out2, out2[:200])
    # 物品视图
    out = await cmd(m, "adventure_book", "g1", "e1", "冒险手册 物品")
    check("物品含矿石类", "矿石" in out and "✅铁矿石" in out, out[:300])
    check("物品含装备", "装备" in out and "✅铁剑" in out, out[:400])
    # 怪物
    out = await cmd(m, "adventure_book", "g1", "e1", "冒险手册 怪物")
    check("怪物视图", "绿史莱姆" in out and "×2" in out, out[:300])
    # 图鉴别名（兼容老玩家）
    out = await cmd(m, "bestiary", "g1", "e1", "图鉴")
    check("图鉴别名=怪物", "绿史莱姆" in out, out[:300])
    out = await cmd(m, "bestiary", "g1", "e1", "图鉴 垂钓")
    check("图鉴 垂钓保留", "彩蛋收藏鱼" in out, out[:300])
    out = await cmd(m, "bestiary", "g1", "e1", "图鉴 收藏")
    check("图鉴 收藏保留", "收藏品" in out, out[:300])

async def main():
    print("【v168 possessed 埋点】")
    test_possessed_basic()
    print("【装备 uuid 归一】")
    test_possessed_equip_uuid()
    print("【市场买入埋点】")
    test_possessed_market_buy()
    print("【冒险手册/足迹指令】")
    await test_commands()
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    asyncio.run(main())
