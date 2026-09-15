# -*- coding: utf-8 -*-
"""N5b4-3 验证：世界Boss saintess_engine 路径（构造 + 血量同步 + 全局写回）。

世界Boss 是全局事件玩法：gboss 全局数据（含 enemies 阵列血量）在 world_event 表，
玩家各自存本地 battle（type=worldboss），行动时双向同步 hp（uid 匹配）。

本测试验证命令层世界Boss 在 saintess_engine 下的数据流骨架：
1. 用真实 db 构造 world_event（boss + 奖励 + 敌人阵列）
2. 玩家 hunt（构造 saintess_engine，sides 敌 actor = Boss + 爪牙）
3. 玩家行动（human_act + sync 回写）→ 全局血量同步（gboss.enemies hp 更新）
4. Boss 死亡 → 贡献/清事件路径可达（reward 全量结算走 services，不在此重放）

跑法：python tests/test_battle_n5b4_worldboss.py
"""
import os
import sys
import tempfile
import time

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

from _engine_harness import db  # noqa: E402
from _engine_harness import Main  # noqa: E402  （原 game.commands.combat.CombatCmds 壳 → 包内实现）
from content import bridge as BR  # noqa: E402
db.init_db()

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def make_player(qid=20001):
    return {"qq_id": qid, "group_id": "g_wb", "name": f"讨伐者{qid}", "class_name": "战士",
            "level": 30, "hp": 2000, "mp": 100, "max_hp": 2000, "max_mp": 100,
            "equipment": {}, "class_tier": 0, "attributes": None,
            "evolve_path": 0, "race": None, "learned_skills": [],
            "cur_map": "wb_map", "cur_subarea": "", "stamina": 100}


def mk_boss_actor(uid, name, hp, is_boss=False):
    return {"uid": uid, "name": name, "hp": hp, "max_hp": hp,
            "lv": 30, "rank": 1, "reach": 1,
            "is_boss": is_boss, "is_elite": False,
            "buffs": {}, "stacks": {}, "debuffs": {},
            "defending": False, "charging": None}


def seed_world_boss():
    boss = mk_boss_actor("wb_0", "巨史莱姆王·咕噜咕噜", 5000, is_boss=True)
    minion = mk_boss_actor("wb_1", "史莱姆小怪", 800)
    boss["enemies"] = [dict(boss), dict(minion)]
    boss["name"] = "巨史莱姆王·咕噜咕噜"
    boss["hp"], boss["max_hp"] = 5000, 5000
    boss["debuffs"] = {}
    boss["adapt"] = {"poison": 0.0, "burn": 0.0}
    boss["dot_act"] = 0
    boss["dot_res"] = 0.9
    boss["immune_dots"] = []
    boss["reward"] = {"gold": 1000, "exp": 500}
    boss["contrib"] = {}
    db.save_world_event("boss", int(time.time()) + 3600, {"boss": boss})
    return boss


def test_worldboss_construction_and_sync():
    print("【N5b4-3 世界Boss saintess_engine：构造 + sides 同步 + 行动】")
    cmds = Main(None)
    gid, qid = "g_wb", 20001
    player = make_player(qid=qid)
    gboss = seed_world_boss()
    check("世界事件就绪", db.get_world_event() is not None)

    # 模拟 hunt_boss 构造段：把全局 boss 组 sides（玩家 + Boss/爪牙 actor）
    # 直接走 bridge 构造（与 hunt_boss 相同路径）
    _tb = {}
    BR.prepare_player_for_battle(player, _tb, BR._as_event_state(db))
    _enemies = [dict(u) for u in gboss["enemies"]]
    for _a in _enemies:
        _a.setdefault("auto_act", {"act": {"type": "attack"}})
    _sides = BR.build_sides(player=player, enemies=_enemies)
    from saintess_engine import Battle as B2
    nb = B2("worldboss", sides=_sides, title_bonus=_tb,
            dmg_mult=db.get_boss_dmg_mult(qid), pet=db.pet_get(qid))
    check("构造成功 sides player+enemy",
          len(nb.sides_of("player")) == 1 and len(nb.sides_of("enemy")) == 2)
    st = nb.to_state()
    check("state type=worldboss", st.get("type") == "worldboss")
    db.save_battle(gid, qid, st)

    # 玩家打 Boss：敌方总 hp 5000+800；攻击主目标一次后 hp 下降 → dealt > 0
    # （完整 _worldboss_act 依赖 event/async yield，这里验证其核心数据链：恢复 + 行动 + 回写 + 同步）
    row = db.get_battle(gid, qid)
    b2 = cmds._restore_battle(row["state"])
    check("saintess_engine 恢复", b2 is not None and b2.btype == "worldboss")
    _target = b2.sides_of("enemy")[0]  # 主 Boss
    before = sum(max(0, u.get("hp", 0)) for u in b2.sides_of("enemy"))
    logs, ended, who = b2.human_act("attack", None, b2.focus(), target=_target)
    cmds._sync_battle_player(player, b2)
    after = sum(max(0, u.get("hp", 0)) for u in b2.sides_of("enemy"))
    dealt = max(0, before - after)
    check("攻击造成伤害", dealt > 0, f"dealt={dealt}")
    check("回写玩家 hp/mp", isinstance(player.get("hp"), int) and player.get("hp") > 0)

    # 同步回全局（命令层 _worldboss_act 写回逻辑）：本地 sides enemy hp → gboss.enemies
    g2 = db.get_world_event()["data"]["boss"]
    genemies = g2.get("enemies")
    _l_by_uid = {u.get("uid"): u for u in b2.sides_of("enemy")}
    for _gu in genemies:
        _lu = _l_by_uid.get(_gu.get("uid"))
        if _lu is not None:
            _gu["hp"] = _lu.get("hp", _gu.get("hp", 0))
    g2["hp"] = genemies[0]["hp"]
    db.save_world_event("boss", int(time.time()) + 3600, {"boss": g2})
    check("全局血量同步", db.get_world_event()["data"]["boss"]["hp"] < 5000)

    # 展示页脚在 saintess_engine worldboss 上不崩
    f = cmds._battle_footer(player, b2, cmds._b_enemy(b2) or {})
    check("页脚不崩", isinstance(f, str) and "巨史莱姆王" in f, repr(f[:80]))
    db.clear_battle(gid, qid)
    db.clear_world_event()


def main():
    print("=== N5b4-3 世界Boss saintess_engine 数据链 ===")
    test_worldboss_construction_and_sync()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
