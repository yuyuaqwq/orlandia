# -*- coding: utf-8 -*-
"""v101.27 #341：夜晚 NPC 不在场禁止隔空交付（采药女·小荨 condition.time=['morning','day'] 实锤）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run

# ★ P5D-REPOINT：原宿主薄壳 `game/services/quests_flow.py` 的注入
#   `quests_svc = game.services.quests` 随 game/** 删除而消失。按 REPOINT_MAP §2，
#   真源 = `content.profession_quests`（bump_daily_progress / settle_daily_quest）。
from content import profession_quests as _profession_quests  # noqa: E402
from content import quests_flow as _quests_flow  # noqa: E402
_quests_flow.bind_host(quests_svc=_profession_quests)

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
    await cmd(m, "register", "g1", "i1", "注册 战士 格温 男")
    # 直接构造 s36 采药女的心愿（giver=w_forest_girl，condition.time=['morning','day']）
    db.add_item("g1", "i1", "mat_yue_guang_cao", {"name": "月光草", "type": "材料", "stackable": True, "price": 20}, 10)
    db.save_quests("g1", "i1", {
        "main_quest": "", "main_status": "none", "main_progress": 0,
        "daily": {}, "completed_main": [],
        "side": {"s36": {"status": "ready"}},
    })
    # 玩家在采药女所在图（白鹿森林）
    db.update_player("g1", "i1", cur_map="white_deer_forest", gold=100)

    # 夜晚：NPC 不在场 → 拒绝交付（mock 时段为 night——注意 base_conditions_met 内部
    # 用 core.wild 模块级 current_period 引用，必须 mock wild 模块而非 C 聚合层）
    from content import wild as W
    orig = W.current_period
    W.current_period = lambda: "night"
    try:
        out = await cmd(m, "turn_in", "g1", "i1", "交付任务")
    finally:
        W.current_period = orig
    check("夜晚隔空交付被拦", "不在这里" in out, out[:200])
    # 确认材料还在（没被扣）
    have = db.count_item("g1", "i1", "mat_yue_guang_cao")
    check("材料未被扣", have == 10, str(have))

    # 白天：NPC 在场 → 正常交付
    W.current_period = lambda: "day"
    try:
        out = await cmd(m, "turn_in", "g1", "i1", "交付任务")
        check("白天正常交付", "完成" in out or "奖励" in out or "金币" in out, out[:300])
        q = db.get_quests("g1", "i1")
        st = (q.get("side") or {}).get("s36", {}).get("status")
        check("任务已交付", st == "done", str(st))
    finally:
        W.current_period = orig

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

import asyncio
asyncio.run(main())
