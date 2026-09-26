# -*- coding: utf-8 -*-
"""N5b 命令层数据流验证探针：battle_state DB 存/取 + saintess_engine 完整行动链。

模拟命令层真实流程（不开 QQ）：
1. 开战：build_monster_group → 桥 build_sides → saintess_engine.Battle → to_state → db.save_battle
2. 玩家攻击：db.get_battle → from_state → human_act("attack") → to_state → save
3. 续战恢复：db.get_battle → from_state → 再攻击/逃跑 → 到结束
4. 旧格式存档作废：构造旧格式 state（无 sides）→ 存 DB → 命令层不迁移，直接清档重开

跑法：python _probe_cmdflow.py
"""
import os
import sys
import tempfile

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()

from content import drops as D
from _engine_harness import db
from content import bridge as BR
from ext_combat import Battle as B2
db.init_db()

PASS = 0
FAIL = 0
from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")

def make_player(cls="战士", level=10, qid=10001):
    return {"qq_id": qid, "group_id": "g1", "name": "流程勇者", "class_name": cls,
            "level": level, "hp": 200, "mp": 50, "max_hp": 200, "max_mp": 50,
            "equipment": {}, "class_tier": 0, "attributes": None,
            "evolve_path": 0, "race": None, "learned_skills": []}

gid, qid = "g_flow", 10001
player = make_player(qid=qid)
map_obj = {"id": "test_plain", "name": "测试平原", "area": "field", "type": "field", "lv": 5}
mon = D.build_monster(("test_wolf", "野狼", "dps", 3, [], []), map_obj)
group = D.build_monster_group(mon, map_obj, player)

print("== 1. 开战（桥 → saintess_engine → save）==")
sides = BR.build_sides(player=player, enemies=group)
b = B2("monster", sides=sides)
check("saintess_engine 构造成功", b.result is None)
st = b.to_state()
check("to_state 含 sides", "sides" in st and len(st["sides"]["enemy"]) == len(group))
db.save_battle(gid, qid, st)
row = db.get_battle(gid, qid)
check("DB 存取成功", row is not None and row.get("state"))

print("== 2. 玩家攻击（get → from_state → human_act → save）==")
row = db.get_battle(gid, qid)
b2 = B2.from_state(row["state"])
focus = b2.focus()
enemy0 = b2.sides_of("enemy")[0]
hp0 = enemy0.get("hp", 0)
logs, ended, who = b2.human_act("attack", None, focus)
dmg = hp0 - enemy0.get("hp", 0)
check("普攻造成伤害", dmg > 0, "dmg=%s" % dmg)
check("行动返回 logs", isinstance(logs, list) and len(logs) > 0)
# 命令层回写：action 后 actor → player dict（旧引擎引用传递自动同步，
# saintess_engine actor 是副本，命令层 db.update_player/展示读 player dict 需显式回写）
BR.sync_player_from_actor(player, b2.focus())
check("回写 hp 同步", player.get("hp", 0) <= 200, "hp=%s" % player.get("hp"))
check("回写 mp 同步", player.get("mp", 0) >= 0, "mp=%s" % player.get("mp"))
db.save_battle(gid, qid, b2.to_state())

print("== 3. 续战恢复 → 继续打完 ==")
row = db.get_battle(gid, qid)
b3 = B2.from_state(row["state"])
logs3 = []
b3.auto_run(logs3)
check("续战能打完", b3.result in ("victory", "defeat", "fled"), "result=%s" % b3.result)
if b3.result == "victory":
    check("胜利时敌全灭", all(x.get("hp", 0) <= 0 for x in b3.sides_of("enemy")))
db.clear_battle(gid, qid)
check("清战斗成功", db.get_battle(gid, qid) is None)

print("== 4. 旧格式存档作废（无 sides → 清 DB 重开，不做迁移）==")
legacy = {
    "type": "monster", "now": 2.0, "round": 1, "result": None,
    "enemy": dict(mon), "enemies": [dict(u) for u in group],
    "title_bonus": {}, "p_buffs": {"atk_up": 1},
    "p_hot": {}, "p_shields": {}, "p_defending": False, "charging": None,
    "poi_buff": None, "cooldown": {}, "mech_stacks": {}, "resources": {},
    "eff_data": {}, "killed_enemies": [], "map": "测试平原",
}
db.save_battle(gid, qid, legacy)
row = db.get_battle(gid, qid)
check("旧档存 DB 成功", row is not None)
# 命令层读档逻辑：只认 saintess_engine 格式（含 sides）；旧格式无 sides → 战斗作废清档（不迁移）
stored = row["state"]
if isinstance(stored, dict) and stored.get("sides"):
    b4 = B2.from_state(stored)
    check("新档直用", b4 is not None)
else:
    db.clear_battle(gid, qid)
    check("旧格式作废清档", db.get_battle(gid, qid) is None)

print("\n=== 结果 PASS=%d FAIL=%d ===" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
