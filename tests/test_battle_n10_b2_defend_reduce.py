# -*- coding: utf-8 -*-
"""N10-B2：方向性防御 defend_reduce（v178 E6）——防御承伤按攻击技能自带值挡伤。

跑法：python tests/test_battle_n10_b2_defend_reduce.py（w1 内）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_n10b2.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import landing as L  # noqa: E402
from saintess_engine import actions as A  # noqa: E402
from saintess_engine.battle.actors import ActCtx  # noqa: E402

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


def mk_player(hp=5000):
    p = make_actor(uid="p1", name="勇者", side="player", kind="player",
                   human_controlled=True, class_name="cls_zhan_shi", level=20,
                   hp=hp, max_hp=hp, mp=200, max_mp=200,
                   atk=100, matk=80, spd=15, crit=0.0,
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   defending=True,  # 防御姿态
                   **{"def": 40, "mdef": 30})
    return p


def mk_monster(atk=200, matk=200):
    m = make_actor(uid="m1", name="风暴领主", side="enemy", kind="monster",
                   hp=99999, max_hp=99999, atk=atk, matk=matk, spd=10, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 10, "mdef": 10})
    return m


def test_default_half():
    print("【1. 无 defend_reduce 技能 → 防御挡 50%（旧行为）】")
    p = mk_player()
    m = mk_monster(atk=200)
    b = B2(btype="monster", sides={"player": [p], "enemy": [m]})
    # 普通技能（无 defend_reduce 字段）打防御玩家
    dmg0 = L.deal_damage(b, m, p, 200, [], dmg_kind="phys")
    check("默认防御挡 50% → 扣 ~100", 80 <= (5000 - p["hp"]) <= 120,
          f"lost={5000 - p['hp']} dmg0={dmg0}")


def test_defend_reduce_08():
    print("【2. 技能 defend_reduce=0.8 → 防御挡 80% 只受 20%】")
    p = mk_player()
    m = mk_monster(atk=200)
    b = B2(btype="monster", sides={"player": [p], "enemy": [m]})
    dmg0 = L.deal_damage(b, m, p, 200, [], dmg_kind="phys", defend_reduce=0.8)
    check("挡 80% → 扣 ~40", 30 <= (5000 - p["hp"]) <= 60,
          f"lost={5000 - p['hp']} dmg0={dmg0}")


def test_skill_pipeline_passes():
    print("【3. 技能管线真实传 defend_reduce（风暴之眼 0.8）】")
    # 干净构造：exprs 技能 + defend_reduce=0.8（管线只透传字段，不依赖数据格式）
    info = {"kind": "魔法", "power": 2.0, "exprs": ["matk*2.0"],
            "defend_reduce": 0.8, "name": "风暴之眼·风眼"}
    # 防御玩家
    pd = mk_player()
    md = mk_monster(atk=200, matk=300)
    bd = B2(btype="monster", sides={"player": [pd], "enemy": [md]})
    A.do_skill(bd, ActCtx(caster=md, action="skill", skill_name="风暴之眼·风眼",
                          info=info, target=pd))
    lost_def = 5000 - pd["hp"]
    # 非防御玩家（对照：不吃 defend_reduce，全伤 ~240-360）
    pn = mk_player()
    pn["defending"] = False
    mn = mk_monster(atk=200, matk=300)
    bn = B2(btype="monster", sides={"player": [pn], "enemy": [mn]})
    A.do_skill(bn, ActCtx(caster=mn, action="skill", skill_name="风暴之眼·风眼",
                          info=info, target=pn))
    lost_no = 5000 - pn["hp"]
    check("技能打出真实伤害", lost_no > 100, f"no_defend_lost={lost_no}")
    check("风暴之眼打防御玩家只受 ~20%", lost_def > 0 and lost_def * 2 < lost_no,
          f"defending_lost={lost_def} no_defend_lost={lost_no}")


if __name__ == "__main__":
    import random
    # v181 flaky 修复：玩家真实面板 ~3% 基础闪避（职业成长）——固定随机种子保证
    # 攻击命中序列确定（3% 闪避偶发会把数值断言打成假红）
    random.seed(20260909)
    test_default_half()
    test_defend_reduce_08()
    test_skill_pipeline_passes()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
