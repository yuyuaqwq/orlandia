# -*- coding: utf-8 -*-
"""v101.27 背包品质 emoji 显示测试：符文（新格式 ID + 旧格式中文）都显示品质标记"""
import sys, os, json
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

async def main():
    clean_db()
    m = Main(None)
    ev = FakeEvent("g1", "i1", "注册 战士 格温 男")
    await run(m.register, ev)
    # 旧格式中文品质符文 + 新格式 ID 符文 + 无品质杂物
    db.add_item("g1", "i1", "rune_old", {"name": "稀有符文·铁壁 II", "type": "符文", "quality": "稀有", "price": 425}, 1)
    db.add_item("g1", "i1", "rune_new", {"name": "传说符文·连锁 III", "type": "符文", "quality": "orange", "price": 900}, 1)
    db.add_item("g1", "i1", "misc_x", {"name": "破旧布条", "type": "材料", "quality": "white", "price": 5}, 1)
    out = m._bag_view("g1", "i1", "")
    check("旧格式中文品质符文显示 emoji", "🔵稀有符文·铁壁 II" in out, out[:300])
    check("新格式 ID 品质符文显示 emoji", "🟠传说符文·连锁 III" in out, out[:300])
    check("白档不显示 emoji", "⚪破旧布条" not in out, out[:300])
    # 符文筛选视图
    out2 = m._bag_view("g1", "i1", "符文")
    check("符文筛选也有 emoji", "🔵稀有符文·铁壁 II" in out2, out2[:300])
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

import asyncio
asyncio.run(main())
