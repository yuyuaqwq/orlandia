# -*- coding: utf-8 -*-
"""v116 任务系统改进回归（test_v116_quest_abandon.py）

覆盖：
 1. /放弃 <序号>：放弃进行中的支线（从 side dict 移除、落库）
 2. /放弃 <序号>：放弃每日任务（从 daily 移除 active 任务）
 3. 主线不可放弃：『放弃 主线』/『放弃 <主线名>』给明确拒绝提示
 4. 每日防刷上限：今日已完成 ≥ DAILY_LIMIT 时『每日』不再抽新任务
 5. 每日重复衰减：同任务重复完成 → _bump_daily_progress 发奖打折并输出衰减提示

运行：py tests/test_v116_quest_abandon.py（exit=0 全绿）
"""
import sys, os, datetime, sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run, make_player

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
    return str(results[-1]) if results else ""

async def main():
    clean_db()
    m = Main(None)

    # ---------- 1. 放弃进行中的支线 ----------
    print("\n[1] 放弃进行中的支线")
    make_player("g1", "q1", "格温", "战士")
    sq0 = next((q for q in C.SIDE_QUESTS if not q.get("board") and not q.get("min_level")), None)
    check("找到一条无门槛支线", sq0 is not None, str(sq0))
    qs = db.get_quests("g1", "q1")
    qs["side"] = {sq0["id"]: {"status": "active", "progress": {}}}
    db.save_quests("g1", "q1", qs)
    out = await cmd(m, "quest_abandon", "g1", "q1", "放弃 1")
    check("支线已放弃", "已放弃任务" in out, out)
    after = db.get_quests("g1", "q1").get("side", {})
    check("side dict 为空（已移除）", sq0["id"] not in after, str(after))

    # ---------- 2. 放弃每日任务 + 主线拒绝 ----------
    print("\n[2] 放弃每日任务 / 主线不可放弃")
    today = datetime.date.today().isoformat()
    qs = db.get_quests("g1", "q1")
    qs["daily"] = {"_date": today, "d0": {"name": "采集任务", "desc": "采集 5 份材料",
                                          "objective": {"collect_any": 5},
                                          "reward_exp": 300, "reward_gold": 150, "repeat": 0, "progress": 0}}
    db.save_quests("g1", "q1", qs)
    out = await cmd(m, "quest_abandon", "g1", "q1", "放弃 1")
    check("每日任务已放弃", "已放弃任务" in out, out)
    dq = db.get_quests("g1", "q1").get("daily", {})
    check("daily 仅剩元数据键", all(k in ("_date", "_completed", "_repeat") for k in dq), str(dq))
    # 主线拒绝
    out = await cmd(m, "quest_abandon", "g1", "q1", "放弃 主线")
    check("『放弃 主线』被拒", "主线任务无法放弃" in out, out)

    # ---------- 3. 每日防刷上限 ----------
    print("\n[3] 每日防刷上限")
    from content.profession_quests import DAILY_LIMIT  # noqa: E402（REPOINT_MAP: game.core.daily 常量真源）
    qs = db.get_quests("g1", "q1")
    qs["daily"] = {"_date": today, "_completed": DAILY_LIMIT, "_repeat": {}}
    db.save_quests("g1", "q1", qs)
    out = await cmd(m, "daily", "g1", "q1", "每日")
    check("达到上限提示明再来", f"已完成 {DAILY_LIMIT}/{DAILY_LIMIT}" in out, out)
    dq = db.get_quests("g1", "q1").get("daily", {})
    check("未抽新任务", all(k in ("_date", "_completed", "_repeat") for k in dq), str(dq))

    # ---------- 4. 每日重复衰减（bump 发奖打折） ----------
    print("\n[4] 每日重复衰减")
    make_player("g1", "q2", "罗兰", "战士")
    qs = db.get_quests("g1", "q2")
    qs["daily"] = {"_date": today, "_completed": 1, "_repeat": {"行会委托": 1},
                   "d0": {"name": "行会委托", "desc": "完成 2 条支线任务",
                          "objective": {"complete_side": 2},
                          "reward_exp": 420, "reward_gold": 180,  # 首刷 700/300 × 60%
                          "repeat": 1, "progress": 2}}
    db.save_quests("g1", "q2", qs)
    gold0 = db.get_player("g1", "q2")["gold"]
    lines = []
    m._bump_daily_progress("g1", "q2", "complete_side", lines)
    fin = db.get_quests("g1", "q2").get("daily", {})
    check("衰减提示输出（第 2 次发 60%）", any("重复完成，奖励衰减 60%" in l for l in lines), str(lines))
    check("衰减提示含折后经验/金币", any("经验 +420 金币 +180" in l for l in lines), str(lines))
    check("_completed 计数 +1", int(fin.get("_completed", 0)) == 2, str(fin.get("_completed")))
    check("奖励按 60% 发放入账", db.get_player("g1", "q2")["gold"] == gold0 + 180,
          f"gold {gold0}->{db.get_player('g1','q2')['gold']}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
