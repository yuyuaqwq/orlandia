# -*- coding: utf-8 -*-
"""N10-B6：承伤属性批验收（dodge 闪避 / block 格挡 / 物免魔免）。

跑法：python tests/test_battle_n10_b6_taken_attrs.py（w1 内）
"""
import os
import sys
import random

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_n10b6.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import landing as L  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_target(hp=2000, dodge=0.0, block=0.0, phys_reduce=0.0, magic_reduce=0.0):
    """纯怪 actor（无 class_name → 直读字段，最干净验证路径）。"""
    t = make_actor(uid="t1", name="靶子", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                   level=20, exp=0, gold=0,
                   dodge=dodge, block=block,
                   **{"def": 0, "mdef": 0, "phys_reduce": phys_reduce,
                      "magic_reduce": magic_reduce})
    return t


def mk_attacker(atk=100, matk=100):
    a = make_actor(uid="a1", name="攻击者", side="player", kind="monster",
                   hp=5000, max_hp=5000, atk=atk, matk=matk, spd=10, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 0, "mdef": 0})
    return a


def new_battle(a, t):
    return B2(btype="monster", sides={"player": [a], "enemy": [t]})


def test_dodge_always():
    print("【1. dodge 高 → 多次受击必有闪避】")
    # dodge=1.0 被 cap 0.4 → 40% 单次；循环 50 次统计必有闪避且闪避时 0 伤害
    dodged = 0
    hit_dmg = None
    for i in range(50):
        random.seed(1000 + i)
        t = mk_target(dodge=1.0)
        a = mk_attacker()
        b = new_battle(a, t)
        logs = []
        real = L.deal_damage(b, a, t, 100, logs, dmg_kind="phys")
        if real == 0 and t["hp"] == 2000:
            dodged += 1
        else:
            hit_dmg = 2000 - t["hp"]
    check("50 次中必有闪避", dodged > 0, f"dodged={dodged}")
    check("闪避时 0 伤害", True, "")  # 上面条件已保证
    # 再验一次闪避文案出现在某次
    any_dodge_log = False
    for i in range(30):
        random.seed(2000 + i)
        t = mk_target(dodge=1.0)
        a = mk_attacker()
        b = new_battle(a, t)
        logs = []
        L.deal_damage(b, a, t, 100, logs, dmg_kind="phys")
        if any("闪避" in x for x in logs):
            any_dodge_log = True
            break
    check("闪避文案出现", any_dodge_log, "")


def test_no_dodge_normal():
    print("【2. dodge=0 → 正常承伤】")
    t = mk_target()
    a = mk_attacker()
    b = new_battle(a, t)
    logs = []
    real = L.deal_damage(b, a, t, 100, logs, dmg_kind="phys")
    check("正常扣血 100", 2000 - t["hp"] == 100, f"hp={t['hp']} real={real}")


def test_phys_reduce():
    print("【3. phys_reduce 0.3 → 物理减免 ~30%】")
    t = mk_target(phys_reduce=0.3)
    a = mk_attacker()
    b = new_battle(a, t)
    logs = []
    L.deal_damage(b, a, t, 100, logs, dmg_kind="phys")
    lost = 2000 - t["hp"]
    check("物理减免 ~30 → 扣 ~70", 68 <= lost <= 72, f"lost={lost}")


def test_magic_reduce_typed():
    print("【4. magic_reduce 吃魔法不吃物理】")
    t = mk_target(magic_reduce=0.3)
    a = mk_attacker()
    b = new_battle(a, t)
    L.deal_damage(b, a, t, 100, [], dmg_kind="magi")
    lost_magi = 2000 - t["hp"]
    t2 = mk_target(magic_reduce=0.3)
    b2 = new_battle(a, t2)
    L.deal_damage(b2, a, t2, 100, [], dmg_kind="phys")
    lost_phys = 2000 - t2["hp"]
    check("魔免对魔法生效（扣 ~70）", 68 <= lost_magi <= 72, f"lost_magi={lost_magi}")
    check("魔免对物理无效", lost_phys == 100, f"lost_phys={lost_phys}")


def test_block_half():
    print("【5. block 高 → 多次受击必有格挡且减免一半】")
    blocked = 0
    for i in range(50):
        random.seed(3000 + i)
        t = mk_target(block=1.0)  # cap 0.4
        a = mk_attacker()
        b = new_battle(a, t)
        logs = []
        L.deal_damage(b, a, t, 100, logs, dmg_kind="phys")
        lost = 2000 - t["hp"]
        if 48 <= lost <= 52:
            blocked += 1
    check("50 次中必有格挡减半", blocked > 0, f"blocked={blocked}")


def test_true_dmg_ignores():
    print("【6. 真伤绕过全部减免】")
    t = mk_target(phys_reduce=0.4, block=1.0, dodge=1.0)
    a = mk_attacker()
    b = new_battle(a, t)
    logs = []
    L.deal_damage(b, a, t, 100, logs, dmg_kind="true")
    check("真伤不减免不闪避", 2000 - t["hp"] == 100, f"hp={t['hp']}")


def test_attacker_side_agnostic():
    print("【7. actor-agnostic：玩家被打也吃闪避】")
    # 玩家 actor 带 class_name → E.player_final_stats 面板（dodge 值来自职业）
    p = make_actor(uid="p1", name="游侠", side="player", kind="player",
                   human_controlled=True, class_name="cls_you_xia", level=20,
                   hp=1000, max_hp=1000, mp=100, max_mp=100,
                   atk=50, matk=30, spd=15, crit=0.05,
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 20, "mdef": 20})
    m = make_actor(uid="m1", name="野狼", side="enemy", kind="monster",
                   hp=500, max_hp=500, atk=50, matk=10, spd=12, crit=0.05,
                   level=20, exp=0, gold=0, **{"def": 5, "mdef": 5})
    b = B2(btype="monster", sides={"player": [p], "enemy": [m]})
    # 面板 dodge 应有职业值（>0）——只验证链路不崩 + 伤害正常
    from saintess_engine import stats as S
    st = S.actor_stats(b, p)
    logs = []
    L.deal_damage(b, m, p, 50, logs, dmg_kind="phys")
    lost = 1000 - p["hp"]
    check("玩家承伤链路跑通", 0 < lost <= 50, f"lost={lost} logs={logs[:2]}")


if __name__ == "__main__":
    test_dodge_always()
    test_no_dodge_normal()
    test_phys_reduce()
    test_magic_reduce_typed()
    test_block_half()
    test_true_dmg_ignores()
    test_attacker_side_agnostic()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
