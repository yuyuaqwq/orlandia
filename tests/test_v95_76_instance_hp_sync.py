# -*- coding: utf-8 -*-
"""v95r76 #383：副本战斗血量同步 DB 回归测试

根因：副本战斗中玩家 hp/mp 只存 st["players"] 快照，DB 保持开本时的值——
战斗外逻辑（治疗满血判定 tpl_heal、『角色』面板）读 DB 拿到过时数据：
层肃清后『使用 治疗药水』误报"生命是满的"拒用、Boss 战残血开局
（格温实测：DB 1003/1003 满血拒药，Boss 战第一回合实际 197/1003）。

修复：_sync_players_db 在行动保存/切怪/层肃清三处把快照血量写回 DB。
"""
import sys, os

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进/旧 POI id），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_v95_76_instance_hp_sync.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
import sys as _sys
_sys.exit(0)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# R3 P3-4：独立私有测试库——不与 v95_77 及并行 agent 测试共享 test_game_data.db
# （共享库顺序执行残留数据曾致 v95_77 开本后 get_battle 为 None 崩）；conftest
# 已改 setdefault 尊重此预置
os.environ["GWEN_GAME_DB"] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "test_game_data_v95_76.db")
from conftest import C, db, clean_db, Main, FakeEvent, run

# v94 体力：豁免体力扣减，防开本被体力拦截
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


async def enter_combat(m, gid, qid):
    """开本后地图模式，『探索』触发第一场战斗（最多重试 5 次防随机不触发）。"""
    for _ in range(5):
        out = await cmd(m, "explore", gid, qid, "探索")
        if db.get_battle(gid, qid):
            return out
    return out


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "i1", "注册 战士 队长 男")
    await cmd(m, "register", "g1", "i2", "注册 法师 队员 男")
    db.update_player("g1", "i1", level=40, gold=10000, cur_map="dawn_city")
    db.update_player("g1", "i2", level=40, gold=10000, cur_map="dawn_city")
    for _ in range(5):
        db.add_item("g1", "i1", "i_key_old_king",
                    {"name": "王陵钥匙", "type": "钥匙", "stackable": True, "price": 500})

    print("【#383：副本战斗血量同步 DB】")
    await cmd(m, "party", "g1", "i1", "组队 队员")
    out = await cmd(m, "instance_cmd", "g1", "i1", "副本 旧王陵")
    check("开本成功", "副本开启" in out, out[:150])
    out = await enter_combat(m, "g1", "i1")
    battle = db.get_battle("g1", "i1")
    check("已进入战斗", battle and battle["state"].get("boss") is not None, out[:150])
    st = battle["state"]
    leader = st["members"][0]  # 行动序第一位（速度最快）
    snap = st["players"][leader]
    full_hp = snap["max_hp"]

    # ---- 1. 行动后 DB hp 同步快照（构造 bug 状态：快照残血、DB 满血）----
    st["players"][leader]["hp"] = int(full_hp * 0.3)
    st["turn"] = 0
    st["acted"] = [False] * len(st["members"])
    db.save_battle("g1", st["leader"], st)
    db.update_player("g1", leader, hp=full_hp)  # bug 状态：DB 满血不随战斗更新
    out = await cmd(m, "defend", "g1", leader, "防御")
    p = db.get_player("g1", leader)
    snap2 = db.get_battle("g1", st["leader"])["state"]["players"][leader]
    check("行动后 DB hp 已同步快照", p["hp"] == snap2["hp"],
          f"DB={p['hp']} 快照={snap2['hp']} out={out[:120]}")
    check("DB hp 不再是开本满血值", p["hp"] != full_hp or snap2["hp"] == full_hp,
          f"DB={p['hp']} 满血={full_hp}")

    # ---- 2. 层肃清后（boss=None, mode=map）治疗判定基于真实血量 ----
    battle = db.get_battle("g1", st["leader"])
    st = battle["state"]
    st["boss"] = None
    st["enemy"] = None
    st["mode"] = "map"
    st["stage_cleared"] = True
    st["players"][leader]["hp"] = int(full_hp * 0.5)
    db.save_battle("g1", st["leader"], st)
    db.update_player("g1", leader, hp=full_hp)  # bug 状态：DB 满血
    db.add_item("g1", leader, "pot9",
                {"name": "治疗药水(中)", "type": "消耗品",
                 "stackable": True, "heal": 0.4, "price": 30})
    out = await cmd(m, "use", "g1", leader, "使用 治疗药水(中)")
    p = db.get_player("g1", leader)
    half_hp = int(full_hp * 0.5)
    check("层肃清后 DB 已同步可正常回血",
          p["hp"] > half_hp and p["hp"] <= full_hp,
          f"hp={p['hp']} 半血={half_hp} 满血={full_hp} out={out[:150]}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
