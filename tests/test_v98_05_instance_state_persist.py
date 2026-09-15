# -*- coding: utf-8 -*-
"""v101.28m #438 复测回归：副本战斗状态持久化（e_minions / round / resources）

根因：_instance_act / _instance_boss_one_turn 重建 Battle 时未传/未写回
e_minions / round / resources / cooldown / combo_seq →
  - Boss 召唤的援军回合结束蒸发（不挡刀不出手）
  - 副本内耗资源技能（如游侠致命狙击 35 精力）永远不可用
  - round 恒 0 → 按回合 Boss 机制（召唤/回血）失序

验证方式：真实走 handler（开本→探索→战斗），战斗中手动向 st 注入
援军/精力状态，验证跨回合传递与写回。
"""
import sys, os, time

# ⚠️ v137 副本彻底重构（副本地图化）：本测试基于旧副本结构（st["boss"]/st["turn"]/分层推进/旧 POI id），
# 已不适用于 v137（副本=多房间地图，怪物在 rooms 池，战斗在 enemies 阵列，推进靠移动）。
# 核心玩法验收由 tests/test_v137_dungeon.py 覆盖。保留本文件供历史参考，跳过执行。
print("⏭️ test_v98_05_instance_state_persist.py: v137 重构后旧结构测试已跳过（见 test_v137_dungeon.py）")
import sys as _sys
_sys.exit(0)

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

async def enter_combat(m, gid, qid):
    for _ in range(5):
        out = await cmd(m, "explore", gid, qid, "探索")
        if db.get_battle(gid, qid):
            return out
    return out

async def main():
    clean_db()
    m = Main(None)
    # 单人副本（哥布林营地 1-2 人可单开），少一层组队复杂度
    await cmd(m, "register", "g1", "i1", "注册 游侠 队长 男")
    db.update_player("g1", "i1", level=40, gold=10000, cur_map="dawn_city")
    await cmd(m, "instance_cmd", "g1", "i1", "副本 哥布林营地")
    st = db.get_battle("g1", "i1")["state"]
    check("单人开本成功", st["type"] == "instance" and len(st["members"]) == 1, str(st.get("type")))

    out = await enter_combat(m, "g1", "i1")
    st = db.get_battle("g1", "i1")["state"]
    check("进入战斗", st.get("boss") is not None, out[:120])

    # ---------- enemies 阵列持久化（v2）：注入援军单位 → 玩家攻击先打前排援军 ----------
    st["enemies"].append({"uid": "e_test_minion", "name": "测试爪牙", "hp": 500, "max_hp": 500,
                          "atk": 100, "matk": 0, "def": 0, "mdef": 0, "spd": 10, "crit": 0,
                          "dodge": 0, "rank": 1, "reach": 1, "buffs": {}, "stacks": {},
                          "defending": False, "charging": None})
    st["round"] = 5
    st["boss"]["hp"] = 999999  # 防测试期 Boss 被秒杀导致战斗结束
    for _eu in (st.get("enemies") or []):  # v2：兼容键同步（boss/enemies 深拷贝后脱节）
        if _eu.get("uid") != "e_test_minion":  # 测试爪牙保持 500 血验证被攻击扣血
            _eu["hp"] = 999999
            # 测试爪牙设为唯一前排（Boss 移后排 rank2）：formation.select_target 对同 rank
            # 目标随机选择（§4.1），Boss 与爪牙同 rank1 时玩家攻击 50% 打 Boss → 断言随机红。
            # rank2 后排 + 玩家 reach2 → 攻击必命中前排爪牙，验证"援军在前排被攻击"确定性。
            _eu["rank"] = 2
        _eu["spd"] = 999  # 敌方高速：玩家无额外行动，每次攻击都是正常回合（regen 生效）
        # v116 敌方蓄力接线后：技能池固定普攻（[]），排除"抽中蓄力技→本回合不行动"的随机性
        _eu["skills"] = []
    # v101.30c：注册角色 40 级默认仅 645 HP，Boss 阶段两轮即全灭销毁副本——
    # 注入高血量，保证 enemies/round/resources 持久化验证完整走完
    st["players"]["i1"]["hp"] = 99999
    st["players"]["i1"]["max_hp"] = 99999
    db.save_battle("g1", "i1", st)
    out = await cmd(m, "attack", "g1", "i1", "攻击")
    st2 = db.get_battle("g1", "i1")["state"]
    _minions = [u for u in (st2.get("enemies") or []) if u.get("uid") == "e_test_minion"]
    check("援军在前排被攻击", not _minions or _minions[0]["hp"] < 500,
          str([(u.get("name"), u.get("hp")) for u in (st2.get("enemies") or [])]))
    check("round 递增写回", st2.get("round", 0) == 6, f"round={st2.get('round')}")

    # ---------- 援军出手：敌方回合每单位行动 ----------
    out2 = await cmd(m, "attack", "g1", "i1", "攻击")  # 触发敌方回合（多怪各行动一次）
    check("援军行动日志", "测试爪牙" in out2, out2[:200])
    b3 = db.get_battle("g1", "i1")
    check("Boss 行动后战斗仍在", b3 is not None, "战斗意外结束")
    st3 = b3["state"] if b3 else {}
    check("敌方阵列仍写回", st3.get("enemies") is not None, str(st3.get("enemies"))[:120])

    # ---------- resources 持久化：注入精力 50 → 攻击后应保留且回复 ----------
    st3["resources"] = {"i1": {"energy": 50}}
    st3["enemies"] = [u for u in (st3.get("enemies") or []) if u.get("uid") != "e_test_minion"]  # 清援军避免干扰
    for _eu in (st3.get("enemies") or []):
        _eu["hp"] = 999999  # 防肃清导致无战斗（无 regen）
        _eu["spd"] = 999  # 敌方高速：玩家无额外行动（regen 生效）
    db.save_battle("g1", "i1", st3)
    out3 = await cmd(m, "attack", "g1", "i1", "攻击")
    st4 = db.get_battle("g1", "i1")["state"]
    en = st4.get("resources", {}).get("i1", {}).get("energy")
    check("精力跨回合累积", en is not None and en >= 75, f"energy={en}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
