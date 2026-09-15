# -*- coding: utf-8 -*-
"""v169.9 主线 collect 面板实时查背包回归（意见#143：采到百合面板仍显示 0/1）

场景：q5_5 王后的花园 active 且 main_progress 空，
背包有 1 朵圣光百合 → 面板应显示『✅ 材料已齐』而非『收集：0/1』。
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run, make_player

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
    return "".join(str(x) for x in results)

async def main():
    clean_db()
    m = Main(None)
    # 玩家在 q5_5 active，main_progress 空
    p = make_player("g1", "p1")
    db.save_quests("g1", "p1", {"main_quest": "q5_5", "main_status": "active", "main_progress": {},
                                "side": {}, "completed_main": []})
    # 背包给 1 朵圣光百合（模拟采到）
    db.add_item("g1", "p1", "圣光百合", {"name": "圣光百合", "type": "材料", "stackable": True, "price": 30}, 1)
    out = await cmd(m, "quest_view", "g1", "p1", "任务")
    txt = "".join(str(x) for x in out) if isinstance(out, list) else str(out)
    print("--- 面板输出 ---")
    print(txt)
    print("----------------")
    check("面板含 王后的花园", "王后的花园" in txt, txt[:200])
    check("面板显示 材料已齐", "材料已齐" in txt, txt)
    check("不再显示 收集：0/1", "收集：0/1" not in txt, txt)
    check("提示找国王交付", "交付" in txt, txt)

if __name__ == "__main__":
    asyncio.run(main())
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)
