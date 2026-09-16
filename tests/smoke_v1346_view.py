# -*- coding: utf-8 -*-
"""v134.6 验证：『查看 <数字>』按 last_list 上下文路由（技能列表→技能详情 / 背包→物品详情）"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
_PRIVATE_DB = os.path.join(_paths.TESTS_DIR, ".private_dbs", "smoke_v1346_view.db")
os.makedirs(os.path.dirname(_PRIVATE_DB), exist_ok=True)
os.environ["GWEN_GAME_DB"] = _PRIVATE_DB
os.environ["GWEN_TEST_MODE"] = "1"
from conftest import db, clean_db, Main, FakeEvent, run, make_player

async def _go():
    m = Main()
    G, Q = "g1", "u1"
    clean_db()
    make_player(G, Q, "测试玩家", "法师")

    # ① 发技能列表（记录 last_list=技能列表）
    r = await run(m.skill, FakeEvent(G, Q, "技能 列表"))
    print("=== ① 技能列表（首行）===")
    print(r[0][:120])
    print()

    # ② 查看 5（应路由到技能详情）
    r2 = await run(m.item_detail, FakeEvent(G, Q, "查看 5"))
    print("=== ② 查看 5（技能上下文 → 技能详情？）===")
    print(r2[0][:250])
    print()

    # ③ 发背包（记录 last_list=背包）
    r3 = await run(m.inventory, FakeEvent(G, Q, "背包"))
    print("=== ③ 背包（首行）===")
    print(r3[0][:120])
    print()

    # ④ 查看 1（应路由到物品详情）
    r4 = await run(m.item_detail, FakeEvent(G, Q, "查看 1"))
    print("=== ④ 查看 1（背包上下文 → 物品详情？）===")
    print(r4[0][:250])
    print()

    # ⑤ 技能列表 → 查看 99（超范围应回退物品提示）
    await run(m.skill, FakeEvent(G, Q, "技能 列表"))
    r5 = await run(m.item_detail, FakeEvent(G, Q, "查看 99"))
    print("=== ⑤ 技能列表后 查看 99（超技能范围 → 物品兜底）===")
    print(r5[0][:200])

asyncio.run(_go())
