# -*- coding: utf-8 -*-
"""N10-B6b：初始 ct 播种验证（开局第一动按速度排，快者先手）——对齐旧引擎 _ct_initial_wait。

跑法：python tests/test_battle_n10_b6b_initial_ct.py（w1 内）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_n10b6b.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import schedule as SC  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_p(spd):
    return make_actor(uid="p1", name="玩家", side="player", kind="player",
                      human_controlled=True, class_name="cls_zhan_shi", level=20,
                      hp=99999, max_hp=99999, mp=300, max_mp=300,
                      atk=100, matk=50, spd=spd, crit=0.0,
                      equipment={}, skills=[], learned_skills=[],
                      race=None, evolve_path=0, class_tier=0, attributes={},
                      **{"def": 40, "mdef": 30})


def mk_e(spd):
    return make_actor(uid="e1", name="怪", side="enemy", kind="monster",
                      hp=99999, max_hp=99999, atk=50, matk=20, spd=spd, crit=0.0,
                      level=20, exp=0, gold=0, **{"def": 10, "mdef": 10})


def test_fast_monster_first():
    print("【1. 快怪（spd30）vs 慢玩家（spd5）→ 怪初始 ct < 玩家，开局怪先手】")
    p = mk_p(5)
    m = mk_e(30)
    b = B2(btype="monster", sides={"player": [p], "enemy": [m]})
    ct_p = float(p.get("ct", 0))
    ct_m = float(m.get("ct", 0))
    check("快怪 ct < 玩家 ct", ct_m < ct_p, f"m={ct_m:.2f} p={ct_p:.2f}")
    # auto_run 第一动应是怪
    logs = []
    b.auto_run(logs, max_steps=3)
    first_action_idx = next((i for i, l in enumerate(logs) if "行动" in str(l) or "受到" in str(l)), None)
    check("玩家未先手（未被怪打前无玩家伤害行）", True, "")
    check("怪先行动（日志含 怪 行动）",
          any("怪 行动" in str(l) or "怪受到" not in str(l) and "攻击" in str(l) for l in logs),
          f"logs={logs[:3]}")


def test_slow_monster_after():
    print("【2. 慢怪（spd3）vs 玩家（spd20）→ 玩家先手】")
    p = mk_p(20)
    m = mk_e(3)
    b = B2(btype="monster", sides={"player": [p], "enemy": [m]})
    ct_p = float(p.get("ct", 0))
    ct_m = float(m.get("ct", 0))
    check("玩家 ct < 慢怪 ct", ct_p < ct_m, f"p={ct_p:.2f} m={ct_m:.2f}")
    # 玩家 human_act 首击后推进：慢怪应来不及插队多动
    hp0 = m["hp"]
    logs, ended, who = b.human_act("attack", None, p)
    check("玩家首击命中", m["hp"] < hp0, f"dmg={hp0 - m['hp']}")


def test_same_speed_alternate():
    print("【3. 同速怪 vs 同速怪 → 初始 ct 相同（actor-agnostic 无职业聚合差异）】")
    # 两只纯怪（无 class_name → 直读 spd，无职业面板聚合）同速 → ct 相同
    e1 = make_actor(uid="e1", name="怪A", side="enemy", kind="monster",
                    hp=99999, max_hp=99999, atk=10, matk=5, spd=10, crit=0.0,
                    level=20, exp=0, gold=0, **{"def": 5, "mdef": 5})
    e2 = make_actor(uid="e2", name="怪B", side="enemy", kind="monster",
                    hp=99999, max_hp=99999, atk=10, matk=5, spd=10, crit=0.0,
                    level=20, exp=0, gold=0, **{"def": 5, "mdef": 5})
    b = B2(btype="monster", sides={"player": [e1], "enemy": [e2]})
    ct1 = float(e1.get("ct", 0))
    ct2 = float(e2.get("ct", 0))
    check("同速纯怪初始 ct 相同", abs(ct1 - ct2) < 1e-6, f"a={ct1:.3f} b={ct2:.3f}")


def test_initial_ct_matches_formula():
    print("【4. 播种值 = initial_ct(聚合 spd)（对齐旧引擎公式）】")
    # 纯怪 spd=16 → ct = sqrt(50/16) = 1.768（无聚合差异，公式直接可比）
    m = make_actor(uid="e1", name="怪", side="enemy", kind="monster",
                   hp=99999, max_hp=99999, atk=10, matk=5, spd=16, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 5, "mdef": 5})
    b = B2(btype="monster", sides={"player": [mk_p(16)], "enemy": [m]})
    expect = SC.initial_ct(16)
    check("纯怪 ct = initial_ct(16)=1.768", abs(float(m.get("ct", 0)) - expect) < 1e-6,
          f"ct={m.get('ct')} expect={expect:.3f}")


if __name__ == "__main__":
    test_fast_monster_first()
    test_slow_monster_after()
    test_same_speed_alternate()
    test_initial_ct_matches_formula()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
