# -*- coding: utf-8 -*-
"""v60：锻造列表指令修复 + 锻造/强化支持背包序号（玩家意见 2026-08-05）

验证：
  1. 『锻造列表』是独立列表指令（修复：原 _strip_cmd 剥"锻造"剩"列表"→ 报找不到配方）
  2. 『锻造列表 N』/『锻造列表N』翻页（免空格粘页码）
  3. 『锻造 N』= 锻造可锻造列表第 N 个配方（序号与列表显示一致，1-based）
  4. 『强化 N』= 强化背包第 N 件（与『物品详情 N』同语义，全背包连续编号）
  5. 强化序号越界 / 指向非装备的提示
"""
import sys, os
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
    await cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    # v95 起副业需拜师解锁；老测试直接模拟已激活（老玩家场景）
    db.activate_prof("g1", "e1", "craft")
    db.activate_prof("g1", "e1", "enhance")
    db.update_player("g1", "e1", cur_map="oak_town", cur_subarea="oak_town_3", level=5, gold=100000)

    print("【锻造列表指令（v60 修复）】")
    out = await cmd(m, "craft", "g1", "e1", "锻造列表")
    check("锻造列表=可锻造列表", "当前可锻造" in out, out[:200])
    check("不再报找不到配方", "没有找到" not in out, out[:200])
    check("提示锻造(随机库)", "💡" in out and "锻造" in out, out[:200])

    print("【锻造列表 翻页】")
    # level=5 时配方足够多（>5 件）才有多页；无条件翻页应退到最后一页不报错
    out = await cmd(m, "craft", "g1", "e1", "锻造列表 2")
    check("锻造列表 2 翻页", "第 2/" in out or "第 1/1" in out, out[:200])
    out = await cmd(m, "craft", "g1", "e1", "锻造列表2")
    check("免空格锻造列表2", "第 2/" in out or "第 1/1" in out, out[:200])
    out = await cmd(m, "craft", "g1", "e1", "锻造列表 99")
    check("超页翻页兜底不报错", "📄 第 " in out, out[:200])

    print("【锻造 N 序号锻造】")
    out = await cmd(m, "craft", "g1", "e1", "锻造")
    first_line = [l for l in out.splitlines() if l.strip() and not l.startswith(("🔨", "━", "📄", "💡"))][0]
    name_in_list = first_line.split(". ", 1)[-1] if ". " in first_line else first_line
    check("列表首条有名字", len(name_in_list) > 2, first_line[:120])
    # 『锻造 1』应走锻造流程（材料不足/成功/金币不足），而不是"没有找到『1』的配方"
    out = await cmd(m, "craft", "g1", "e1", "锻造 1")
    check("锻造 1 走锻造流程", "没有找到" not in out, out[:200])
    check("锻造 1 有配方响应", ("不足" in out or "成功" in out or "铁匠铺" in out or "Lv." in out), out[:200])
    # 越界
    out = await cmd(m, "craft", "g1", "e1", "锻造 999")
    check("锻造 999 越界提示", "没有第 999 个" in out, out[:200])

    print("【强化 N 背包序号】")
    # 背包第 1 件 = 材料（非装备）→ 提示不是装备
    db.add_item("g1", "e1", "mat_lang_pi", {"name": "狼皮", "type": "材料", "stackable": True, "price": 8}, 5)
    out = await cmd(m, "enhance", "g1", "e1", "强化 1")
    check("强化 1 指向材料提示", "不是装备" in out, out[:200])
    # 第 2 件 = 装备 → 走强化流程
    eq = C.craft_recipe_make(C.craft_recipe_search("铁剑"))
    db.add_item("g1", "e1", "eq_test", eq)
    out = await cmd(m, "enhance", "g1", "e1", "强化 2")
    check("强化 2 走强化流程", ("强化成功" in out or "强化失败" in out or "极限" in out or "需要" in out), out[:200])
    # 越界
    out = await cmd(m, "enhance", "g1", "e1", "强化 999")
    check("强化 999 越界提示", "背包里没有第 999 件" in out, out[:200])
    # 原名字强化仍可用
    out = await cmd(m, "enhance", "g1", "e1", "强化 铁剑")
    check("强化 名字仍可用", len(out) > 5, out[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
