# -*- coding: utf-8 -*-
"""v130.2e.1：『套装』面板渲染 effect 型 bonus_2 不崩溃（审计 P0 回归防线）

回归场景：玩家穿戴 effect 型 bonus_2 套装（如血誓战团 2 件）后发『套装』，
v130.2e 前 economy.set_view 对 bonus_2 逐键 int(v*100) 直接 ValueError 崩玩家面板。
"""
import os
os.environ.setdefault("GWEN_GAME_DB", os.path.abspath("test_v1302e_setview.db"))

import asyncio
import sys
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _engine_harness import C, run, FakeEvent, clean_db

from _engine_harness import db
from _engine_harness import Main
from content.catalog_items import EQUIP_ROSTER


def check(name, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f" | {detail}" if detail else ""))
    return cond


async def main():
    clean_db()
    db.init_db()
    m = Main(None)
    ec = m
    ok = True

    await run(m.register, FakeEvent("g1", "u1", "注册 测试战士 男"))
    # 穿 2 件血誓战团（effect 型 bonus_2 套装）
    pcs = [(rid, r) for rid, r in EQUIP_ROSTER.items() if r.get("set") == "血誓战团"][:2]
    assert len(pcs) == 2, f"血誓战团部件数异常: {len(pcs)}"
    eq = {}
    for slot, (rid, r) in zip(["weapon", "armor"], pcs):
        eq[slot] = {"name": r["name"], "slot": slot, "lv": r["lv"],
                    "quality": r.get("quality", "purple"), "stats": {"atk": 30},
                    "set": r["set"], "affixes": [], "price": 1}
    db.update_player("g1", "u1", equipment=eq)

    # 『套装』面板渲染：不得抛异常，且展示 effect 语义（desc）
    msgs = await run(ec.set_view, FakeEvent("g1", "u1", "套装"))
    txt = "".join(str(x) for x in msgs)
    ok &= check("set_view 渲染不崩溃", len(txt) > 50, f"len={len(txt)}")
    ok &= check("展示套装名 血誓战团", "血誓战团" in txt, txt[:60])
    ok &= check("展示 2 件效果语义(受击回怒)", "受击回怒" in txt, txt[:120])

    print("\n结果:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))