# -*- coding: utf-8 -*-
"""落地接口层测试：saintess_engine/landing.py 统一收口行为。

覆盖 deal_damage：
- 护盾先吸收再扣血
- 等级压制（高打低增伤/低打高削）
- 死亡判定（_on_actor_dead 触发）
- defending 减半
覆盖 heal_actor：
- clamp max_hp
- 禁疗 heal_down 修正
- 无 hp 容器不可治疗

跑法：python tests/test_battle_landing.py
"""
import os
import sys
import random

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_landing.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from saintess_engine import landing as L                        # noqa: E402

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


def mk_actor(uid, name, side, hp=1000, max_hp=1000, level=1, atk=100, **kw):
    return make_actor(uid=uid, name=name, side=side, kind="monster", level=level,
                      hp=hp, max_hp=max_hp, atk=atk, **{"def": kw.pop("def", 5)},
                      matk=10, mdef=5, spd=5, crit=0.05, **kw)


def test_damage_shield_first():
    print("【L1 伤害落地：护盾先吸收 → 再扣血】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    src = mk_actor("p", "打手", "player", hp=500)
    tgt = mk_actor("e", "靶", "enemy", hp=100)
    tgt["shields"]["test"] = {"value": 30, "halve": False}
    logs = []
    real = L.deal_damage(b, src, tgt, 50, logs)
    # 返回 = 实际扣 hp = 20（护盾 30 是中间吸收，不计数）
    check("护盾吸收 30，实际扣血 20", real == 20, f"real={real}")
    check("target hp 100-20=80", tgt["hp"] == 80, f"hp={tgt['hp']}")
    check("护盾耗尽移除", "test" not in tgt.get("shields", {}))
    # 护盾全挡
    tgt2 = mk_actor("e2", "靶2", "enemy", hp=100)
    tgt2["shields"]["s"] = {"value": 100, "halve": False}
    logs2 = []
    real2 = L.deal_damage(b, src, tgt2, 50, logs2)
    check("护盾全挡不扣血", real2 == 0 and tgt2["hp"] == 100, f"real={real2} hp={tgt2['hp']}")


def test_damage_lv_pressure():
    print("【L2 伤害落地：等级压制双向曲线】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    # 高打低：25 级打 5 级（def=0 无减伤）→ ×1.02^20
    high = mk_actor("p", "高级", "player", level=25, atk=100)
    low = mk_actor("e", "低级", "enemy", level=5, hp=100000, max_hp=100000, atk=10, **{"def": 0})
    logs = []
    real = L.deal_damage(b, high, low, 100, logs)
    expect = int(100 * (1.02 ** 20))
    check(f"高打低 def=0 ×1.02^20 = {expect}", real == expect, f"real={real} expect={expect}")
    # 低打高：5 级打 25 级 → 削（<100）
    lv2 = mk_actor("p2", "低级攻", "player", level=5, atk=100)
    hi2 = mk_actor("e2", "高级靶", "enemy", level=25, hp=100000, max_hp=100000, atk=10, **{"def": 0})
    logs2 = []
    real2 = L.deal_damage(b, lv2, hi2, 100, logs2)
    check("低打高 被削 < 100", real2 < 100, f"real={real2}")


def test_damage_death():
    print("【L3 伤害落地：死亡判定触发】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    b.killed_actors = []
    src = mk_actor("p", "打手", "player", hp=500)
    tgt = mk_actor("e", "残血", "enemy", hp=20)
    b._on_actor_dead = lambda a, logs=None: b.killed_actors.append(a)
    logs = []
    real = L.deal_damage(b, src, tgt, 50, logs)
    check("致死：hp=0", tgt["hp"] == 0, f"hp={tgt['hp']}")
    check("实际扣血 20（不超血条）", real == 20, f"real={real}")
    check("死亡钩子触发", len(b.killed_actors) == 1)


def test_damage_defending():
    print("【L4 伤害落地：defending 减半】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    src = mk_actor("p", "打手", "player", hp=500)
    tgt = mk_actor("e", "防御中", "enemy", hp=100)
    tgt["defending"] = True
    logs = []
    real = L.deal_damage(b, src, tgt, 60, logs)
    check("defending 60 → 30", real == 30, f"real={real} hp={tgt['hp']}")


def test_heal_clamp():
    print("【L5 治疗落地：clamp max_hp】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    tgt = mk_actor("e", "伤者", "enemy", hp=50, max_hp=100)
    logs = []
    real = L.heal_actor(b, tgt, 30, logs)
    check("heal 30 → hp 80", real == 30 and tgt["hp"] == 80, f"real={real} hp={tgt['hp']}")
    real2 = L.heal_actor(b, tgt, 100, logs)
    check("heal 100 clamp → hp 100，实回 20", real2 == 20 and tgt["hp"] == 100,
          f"real={real2} hp={tgt['hp']}")


def test_heal_anti():
    print("【L6 治疗落地：禁疗 heal_down 修正】")
    b = BT_NEW(btype="monster", sides={"player": [], "enemy": []})
    tgt = mk_actor("e", "被禁疗", "enemy", hp=50, max_hp=100)
    tgt["effects"]["heal_down"] = {"stacks": 2}  # 禁疗 2 层 → -20%（v2 数值容器 state，N9 收编）
    logs = []
    real = L.heal_actor(b, tgt, 50, logs)
    check("heal_down 2 层 → 治疗 -20% → 40", real == 40, f"real={real} hp={tgt['hp']}")



def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


def main():
    print("=== saintess_engine landing 落地接口层测试 ===")
    test_damage_shield_first()
    test_damage_lv_pressure()
    test_damage_death()
    test_damage_defending()
    test_heal_clamp()
    test_heal_anti()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
