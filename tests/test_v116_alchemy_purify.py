# -*- coding: utf-8 -*-
"""v116 炼金材料提纯（3 份同档低质 → 1 份高档，19 章 2.5『转的乐趣』）

验证：
  1. 『炼金 提纯』 列表只列提纯配方（不含普通合成）
  2. 合成提纯：3 份低档材料 → 1 份高档材料（背包数量断言）
  3. 材料不足拦截（不扣体力/不发产物）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import db, clean_db, Main, FakeEvent, run

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


def inv_count(gid, qid, name):
    return sum(it["count"] for it in db.get_inventory(gid, qid) if it["data"].get("name") == name)


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "e1", "注册 法师 炼金 男")
    db.update_player("g1", "e1", cur_map="oak_town", cur_subarea="oak_town_3",
                     level=20, gold=50000, apprentices=["alchemy"])
    # 炼金等级拉到 5（覆盖所有提纯配方门槛 2/5）
    for _ in range(300):
        db.add_prof_exp("g1", "e1", "alchemy", 1)
    prof_lv = db.get_prof_level("g1", "e1", "alchemy")
    check("炼金等级 >=5", prof_lv >= 5, f"Lv.{prof_lv}")

    print("【炼金 提纯 列表过滤】")
    out = await cmd(m, "alchemy", "g1", "e1", "炼金 提纯")
    check("提纯标题", "提纯" in out and "→ 1 份高档" in out, out[:150])
    check("仅列提纯配方", "鲸须草提纯" in out and "治疗药水" not in out, out[:200])
    # 普通炼金列表不含提纯配方
    out2 = await cmd(m, "alchemy", "g1", "e1", "炼金")
    check("普通列表不含提纯", "鲸须草提纯" not in out2 and "治疗药水" in out2, out2[:200])

    print("【提纯成功：3 鲸须草 → 1 珍珠贝】")
    db.add_item("g1", "e1", "mat_jing_xu_cao",
                {"name": "鲸须草", "type": "材料", "stackable": True, "price": 20}, 3)
    out = await cmd(m, "alchemy_craft", "g1", "e1", "合成 鲸须草提纯")
    check("提纯成功提示", "提纯成功" in out and "珍珠贝" in out and "鲸须草提纯" in out, out[:250])
    check("背包：鲸须草清零", inv_count("g1", "e1", "鲸须草") == 0, str(inv_count("g1", "e1", "鲸须草")))
    check("背包：珍珠贝 +1", inv_count("g1", "e1", "珍珠贝") == 1, str(inv_count("g1", "e1", "珍珠贝")))

    print("【提纯成功：3 珍珠贝 → 1 雷晶砂（蓝→紫）】")
    db.add_item("g1", "e1", "mat_zhen_zhu_bei",
                {"name": "珍珠贝", "type": "材料", "stackable": True, "price": 35}, 3)
    out = await cmd(m, "alchemy_craft", "g1", "e1", "合成 珍珠贝提纯")
    check("雷晶砂产出", "雷晶砂" in out, out[:250])
    check("背包：珍珠贝剩 1（3+1 原有 -3）", inv_count("g1", "e1", "珍珠贝") == 1, str(inv_count("g1", "e1", "珍珠贝")))
    check("背包：雷晶砂 +1", inv_count("g1", "e1", "雷晶砂") == 1, str(inv_count("g1", "e1", "雷晶砂")))

    print("【提纯失败：材料不足】")
    db.add_item("g1", "e1", "mat_hai_zao",
                {"name": "海藻", "type": "材料", "stackable": True, "price": 15}, 2)
    out = await cmd(m, "alchemy_craft", "g1", "e1", "合成 海藻提纯")
    check("材料不足提示", "材料不足" in out and "海藻" in out, out[:250])
    check("背包：海藻仍 2", inv_count("g1", "e1", "海藻") == 2, str(inv_count("g1", "e1", "海藻")))
    check("背包：神秘鳞片未产出", inv_count("g1", "e1", "神秘鳞片") == 0, str(inv_count("g1", "e1", "神秘鳞片")))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
