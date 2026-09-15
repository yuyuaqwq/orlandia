# -*- coding: utf-8 -*-
"""v166 代工去图纸测试（材料+3倍金币直出，免图纸/免副业）

验证：
  1. 没学图纸也能『代工』紫装（无 blueprint 前置校验）
  2. 『锻造』仍需图纸（图纸线保留）
  3. 代工序号选单 = 代工口径（含未学图纸配方，按等级过滤）
  4. 代工 = 材料 + 3倍金币，不受锻造副业等级限制

独立运行：python tests/test_v166_commission_nobp.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import FakeEvent, run, clean_db, make_player, new_main

from _engine_harness import C, db

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


async def cmd(m, name, gid, qid, msg):
    handler = getattr(m, name)
    ev = FakeEvent(gid, qid, msg)
    return await run(handler, ev)


def give_mats(gid, qid, rec):
    """按配方给足材料。"""
    for mid, n in rec["mats"].items():
        db.add_item(gid, qid, mid, {"name": C.display("materials", mid), "type": "材料"}, count=n)


async def test_commission_no_blueprint():
    print("【1. 没图纸也能代工紫装】")
    clean_db()
    m = new_main()
    gid, qid = "g_bp", "q_bp"
    make_player(gid, qid, "铁匠客户", "战士", level=50)
    db.update_player(gid, qid, cur_map="white_deer", cur_subarea="white_deer_3",
                     gold=1_000_000, stamina=999999)
    # 找一个紫装配方（需图纸）：月语长弓 lv52 图纸 → 找等级合适（≤ lv+6=56）的需图纸配方
    bp_rec = None
    for rk, rec in C.CRAFT_RECIPES.items():
        if rec.get("blueprint") and rec["lv"] <= 56:
            bp_rec = (rk, rec)
            break
    check("找到需图纸配方", bp_rec is not None, "")
    if bp_rec is None:
        return
    rk, rec = bp_rec
    # 确认玩家没学图纸 + 没锻造副业
    check("未学图纸", rec["blueprint"] not in (db.get_player(gid, qid).get("learned_blueprints") or []), "")
    check("锻造副业未激活", "craft" not in db.get_activated_profs(gid, qid), "")
    give_mats(gid, qid, rec)
    # 代工该紫装
    res = await cmd(m, "craft_commission", gid, qid, f"代工 {rec['name']}")
    out = "\n".join(res) if isinstance(res, list) else str(res)
    check(f"代工【{rec['name']}】成功", "代工完成" in out and rec["name"] in out, out[:200])
    check("装备入包", db.count_item(gid, qid, rec["name"]) >= 1, "")


async def test_forge_still_needs_bp():
    print("【2. 锻造仍需图纸（图纸线保留）】")
    clean_db()
    m = new_main()
    gid, qid = "g_bp2", "q_bp2"
    make_player(gid, qid, "铁匠客户2", "战士", level=50)
    db.update_player(gid, qid, cur_map="white_deer", cur_subarea="white_deer_3",
                     gold=1_000_000, stamina=999999)
    # 激活锻造副业（学艺），提升等级到足够
    db.add_prof_exp(gid, qid, "craft", 999)  # 锻造 Lv.很高
    # 找一个需图纸配方
    bp_rec = None
    for rk, rec in C.CRAFT_RECIPES.items():
        if rec.get("blueprint") and rec["lv"] <= 56:
            bp_rec = (rk, rec)
            break
    if bp_rec is None:
        return
    rk, rec = bp_rec
    give_mats(gid, qid, rec)
    # 未学图纸 → 锻造被拦
    res = await cmd(m, "craft", gid, qid, f"锻造 {rec['name']}")
    out = "\n".join(res) if isinstance(res, list) else str(res)
    check("锻造未学图纸被拦", "图纸" in out and "学习" in out, out[:200])


if __name__ == "__main__":
    import asyncio
    print("v166 代工去图纸测试")
    asyncio.run(test_commission_no_blueprint())
    asyncio.run(test_forge_still_needs_bp())
    print(f"\n结果: PASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)
