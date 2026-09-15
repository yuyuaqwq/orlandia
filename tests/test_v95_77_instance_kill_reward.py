# -*- coding: utf-8 -*-
"""v95r77 #363：副本击杀奖励回归测试（格温+影刃双实锤：副本小怪/精英击杀零播报）

验证：
  1. 切怪分支：击杀小怪后输出含 经验+/拾取材料
  2. 层肃清分支：击杀最后一只怪输出含 经验+ 与 肃清 提示
  3. 经验落库 / 击杀统计（kills）递增
"""
import sys, os, time

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进/旧 POI id），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_v95_77_instance_kill_reward.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
import sys as _sys
_sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# R3 P3-4：独立私有测试库——不与 v95_76 及并行 agent 测试共享 test_game_data.db
# （共享库顺序执行残留数据曾致 v95_77 开本后 get_battle 为 None 崩）；conftest
# 已改 setdefault 尊重此预置
os.environ["GWEN_GAME_DB"] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "test_game_data_v95_77.db")
from conftest import C, db, clean_db, Main, FakeEvent, run

def _fake_spend(self, gid, qid, cost, player, action="行动"):
    return True, self._stamina(player)
Main._spend_stamina = _fake_spend

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
    await cmd(m, "register", "g1", "i1", "注册 战士 队长 男")
    await cmd(m, "register", "g1", "i2", "注册 法师 队员 男")
    db.update_player("g1", "i1", level=40, gold=10000, cur_map="dawn_city")
    db.update_player("g1", "i2", level=40, gold=10000, cur_map="dawn_city")
    for _ in range(5):
        db.add_item("g1", "i1", "i_key_old_king", {"name": "王陵钥匙", "type": "钥匙", "stackable": True, "price": 500})

    # 开本 + 探索触发战斗
    out = await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("开本", "副本开启" in out, out[:150])
    out = await cmd(m, "explore", "g1", "i1", "探索")
    st = db.get_battle("g1", "i1")["state"]

    # 第 1 层：杀第 1 只怪（切怪分支）→ 应出现击杀奖励
    st["boss"]["hp"] = 1
    st["boss"]["atk"] = 1
    st["boss"]["matk"] = 1
    for _eu in (st.get("enemies") or []):  # v2：兼容键同步到阵列单位（boss/enemies 深拷贝后脱节）
        _eu["hp"] = 1
        _eu["atk"] = 1
        _eu["matk"] = 1
    st["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", st)
    cur = st["members"][st["turn"]]
    out = await cmd(m, "attack", "g1", cur, "攻击")
    check("切怪分支击杀奖励", "经验 +" in out, out[:400])
    check("切怪分支材料", "拾取材料" in out, out[:400])

    # 杀第 2 只怪（层肃清分支）→ 应出现击杀奖励 + 肃清
    st = db.get_battle("g1", "i1")["state"]
    st["boss"]["hp"] = 1
    st["boss"]["atk"] = 1
    st["boss"]["matk"] = 1
    for _eu in (st.get("enemies") or []):  # v2：兼容键同步到阵列单位
        _eu["hp"] = 1
        _eu["atk"] = 1
        _eu["matk"] = 1
    st["turn_time"] = int(time.time())
    db.save_battle("g1", "i1", st)
    cur = st["members"][st["turn"]]
    out = await cmd(m, "attack", "g1", cur, "攻击")
    check("层肃清击杀奖励", "经验 +" in out, out[:400])
    check("层肃清提示", "肃清" in out, out[:400])

    # 验证击杀统计/经验落库
    p = db.get_player("g1", "i1")
    check("经验已入账", p["exp"] > 0, str(p["exp"]))
    stats = db.get_stats("g1", "i1")
    check("击杀统计", stats and stats.get("kills", 0) >= 2, str(stats))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

import asyncio
asyncio.run(main())
