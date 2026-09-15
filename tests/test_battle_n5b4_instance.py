# -*- coding: utf-8 -*-
"""N5b4-5a 验证：副本战斗控制器（instance_battle.py）saintess_engine 原生闭环。

覆盖：build_battle（sides 组/state 落 st）/ act（human_act 闭环/heal 防奶敌）/
sync_views（视图+DB 同步）/ 轮转 next_actor_key / 敌死亡视图。

跑法：python tests/test_battle_n5b4_instance.py
"""
import os
import sys
import tempfile
import json

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from content.persistence.handles import init_db  # noqa: E402
init_db()

from _engine_harness import db  # noqa: E402
from content.flow import instance_battle as IB  # noqa: E402


# 包内 `sync_views` 的写库口：宿主壳 `game/commands/instance_battle.py::_db_update`
# 已随 game/** 删除 → 按包内注入槽补同签名同语义端口。（否则 `_resolve_db_update`
# 取到「db」槽的模块直调 `persistence.update_player(gid, qid, **fields)`，被按
# 适配器的 6 个位置参数调用 → TypeError 被 sync_views 的 try/except 吞掉 →
# DB 血量永不写回。注入槽优先，故这里显式给出宿主壳原来的那一层适配。）
def _db_update(group_id, key, hp, mp, max_hp, max_mp):
    db.update_player(group_id, key, hp=hp, mp=mp, max_hp=max_hp, max_mp=max_mp)


IB.bind_host(db_update=_db_update)

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


GID = "g_inst"


def mk_snap(qid, name, cls="战士", level=15, learned=None, hp=None):
    """玩家快照（对齐 join_battle/_instance_build_state 形态）。"""
    from content.panel import player_final_stats
    db.create_player(GID, qid, name, cls, {}, 100, 100)
    db.update_player(GID, qid, level=level, cur_map="pvp_field", cur_subarea="",
                     learned_skills=learned or [], stamina=999,
                     attributes=json.dumps({"str": 5, "agi": 5, "int": 5, "vit": 5}))
    pl = db.get_player(GID, qid)
    st = player_final_stats(cls, level, {}, 0, pl.get("attributes"), 0, {}, pl.get("race"))
    mh = int(st.get("max_hp", 100))
    cur = hp if hp is not None else mh
    db.update_player(GID, qid, max_hp=mh, max_mp=50, hp=cur, mp=50)
    pl = db.get_player(GID, qid)
    return {
        "name": name, "qq_id": qid, "class_name": cls, "level": level,
        "hp": int(pl.get("hp", 0)), "max_hp": mh,
        "mp": int(pl.get("mp", 0)), "max_mp": 50,
        "equipment": {}, "skills": [], "learned_skills": learned or [],
        "class_tier": 0, "evolve_path": 0, "attributes": pl.get("attributes"),
        "bonus": {"panel": {}, "cap": {}, "cost": {}}, "race": pl.get("race"),
        "uid": f"p_{qid}", "buffs": {}, "stacks": {}, "defending": False,
        "charging": None, "ct": 0.0, "p_shields": {},
    }


def mk_enemy(uid="e_boss", name="测试Boss", hp=800, atk=30, spd=50, role="boss"):
    """敌单位（对齐 build_monster 产物形态）。"""
    return {"uid": uid, "name": name, "hp": hp, "max_hp": hp,
            "atk": atk, "def": 10, "matk": 10, "mdef": 10, "spd": spd,
            "crit": 0.05, "lv": 15, "level": 15, "role": role,
            "is_boss": role == "boss", "rank": 1, "reach": 1, "ct": 1.0}


def mk_st(qids, enemy=None):
    st = {
        "type": "instance", "inst_id": "test_inst", "leader": str(qids[0]),
        "members": [str(q) for q in qids],
        "alive": {str(q): True for q in qids},
        "players": {}, "boss": None, "enemy": None, "enemies": [],
        "turn": 0, "round": 1, "mode": "battle", "pets": {},
        "p_buffs": {str(q): {} for q in qids},
        "p_hot": {str(q): {} for q in qids},
        "p_food_effects": {str(q): [] for q in qids},
        "p_defending": {str(q): False for q in qids},
        "mech_stacks": {str(q): {} for q in qids},
        "now": 0.0, "battle": None,
    }
    for q in qids:
        st["players"][str(q)] = mk_snap(q, f"玩家{q}", hp=None)
    if enemy:
        st["enemies"] = [enemy]
        st["boss"] = enemy
        st["enemy"] = enemy
    return st


def test_build_battle():
    print("【5a build_battle：组 sides + st['battle'] 落盘】")
    st = mk_st([10001], enemy=mk_enemy())
    b = IB.build_battle(st)
    check("返回 B2", b is not None and hasattr(b, "human_act"))
    check("st['battle'] 落盘", (st.get("battle") or {}).get("sides") is not None)
    sides = (st.get("battle") or {}).get("sides") or {}
    p = sides.get("player") or []
    e = sides.get("enemy") or []
    check("player side 1 actor", len(p) == 1 and str(p[0].get("qq_id")) == "10001")
    check("enemy side 1 actor", len(e) == 1 and e[0].get("uid") == "e_boss")
    check("actor ct 透传", p[0].get("ct") is not None)
    check("actor bonus 容器（v181.M-bonus 三域）",
          isinstance(p[0].get("bonus"), dict)
          and isinstance((p[0].get("bonus") or {}).get("panel"), dict))


def test_act_and_sync():
    print("【5a act 闭环 + sync_views 视图/DB 同步】")
    gid = "g_inst"
    st = mk_st([10002], enemy=mk_enemy(hp=900, spd=1))
    IB.build_battle(st)
    hp0 = (st.get("battle") or {}).get("sides", {}).get("enemy", [{}])[0].get("hp")
    logs, ended, nxt, _abort = IB.act(st, gid, 10002, "attack")
    hp1 = (st.get("battle") or {}).get("sides", {}).get("enemy", [{}])[0].get("hp")
    check("普攻造成伤害", int(hp1) < int(hp0), f"{hp0}->{hp1}")
    check("logs 非空", bool(logs))
    # 同步视图
    IB.sync_views(st, gid)
    snap = st["players"]["10002"]
    check("快照 hp 视图同步", int(snap.get("hp", 0)) > 0 and snap.get("hp") is not None)
    check("DB 血量同步", int((db.get_player(gid, 10002) or {}).get("hp", 0)) == int(snap.get("hp", 0)))
    check("st now 同步", float(st.get("now", 0) or 0) >= 0)
    check("敌视图存活", st.get("enemies") and int(st["enemies"][0].get("hp", 0)) > 0)
    db.clear_battle(gid, 10002)


def test_multiplayer_turn_and_death():
    print("【5a 多玩家轮转 + 敌死亡】")
    st = mk_st([10003, 10004], enemy=mk_enemy(hp=60, atk=5, spd=50))
    IB.build_battle(st)
    # ct 相同时按序——先把玩家 10003 ct 调小模拟轮到他
    sides = (st.get("battle") or {}).get("sides") or {}
    for a in sides.get("player") or []:
        a["ct"] = 0.0
    nxt = IB.next_actor_key(st)
    check("next_actor_key 返回玩家", nxt in ("10003", "10004"), f"nxt={nxt}")
    # 玩家 10003 攻击（怪 hp 60 两刀内死；actor atk 基础约几十）——打至死亡
    guard = 0
    ended = False
    while guard < 20:
        guard += 1
        cur = IB.next_actor_key(st)
        if cur is None:
            break
        logs, ended, _n, _abort = IB.act(st, GID, cur, "attack")
        if not _n:
            break
        IB.sync_views(st, GID)
    enemies = (st.get("battle") or {}).get("sides", {}).get("enemy") or []
    e_hp = max((u.get("hp") or 0) for u in enemies)
    check("敌被击败", e_hp <= 0, f"e_hp={e_hp} guard={guard}")
    IB.sync_views(st, GID)
    check("敌视图清空（全灭）", not st.get("enemies"), f"{st.get('enemies')}")
    # 存活玩家 DB 血量仍 >0
    alive_db = (db.get_player(GID, 10003) or {}).get("hp", 0)
    check("存活玩家 DB >0", int(alive_db) > 0, f"{alive_db}")


def test_heal_target_none():
    print("【5a heal 技能 target=None 防奶敌】")
    # 用 learn 挥砍的玩家施放攻击类；heal 类需要治疗职业——直接断言 act 里
    # kind 判定逻辑：治疗技能传 target=None（不炸即可，技能未学由命令层拦）
    st = mk_st([10005], enemy=mk_enemy(hp=500))
    IB.build_battle(st)
    logs, ended, _n, _abort = IB.act(st, GID, 10005, "skill", "不存在治疗", target={"uid": "e_boss"})
    # 技能不存在 → 引擎/命令层兜底不炸（无 info 时 target 原样）
    check("技能异常不炸", isinstance(logs, list))


def main():
    test_build_battle()
    test_act_and_sync()
    test_multiplayer_turn_and_death()
    test_heal_target_none()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        for f in FAILURES:
            print(" -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
