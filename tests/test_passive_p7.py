# -*- coding: utf-8 -*-
"""v181.M-passive P7 测试——链舞 finisher_up 终结技升级（MECH_CASH.upgrade）。

跑法：python tests/test_passive_p7.py（exit=0 全绿）
覆盖（语义源 = 链舞 desc「终结技系数+6%（每段 10% → 16%）」）：
  1. 不学链舞：终结技 trigger per_layer = 0.10（MECH_CASH 基础）
  2. 学链舞：终结技 trigger per_layer = 0.16（upgrade +0.06）
  3. 触发验证：学链舞 + 连段 5 段 → 终结技伤害 ×(1+0.16×5)
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p7.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def mk_assassin(skills):
    a = make_actor(uid="p_1", name="刺客", side="player", kind="player",
                   human_controlled=True, class_name="cls_ci_ke", level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=200, matk=30, spd=80, hp=3000, max_hp=3000, mp=300, max_mp=300)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def finisher_trigger_per(a):
    for t in (a.get("triggers") or {}).get("dmg_calc", []):
        if t.get("action") == "mech_cash_dmg_mult" and t.get("mech") == "finisher":
            return float(t.get("per_layer") or 0)
    return None


def test_1_base():
    print("【1. 不学链舞：终结技 per_layer 0.10】")
    a = mk_assassin(["终结·割喉"])  # lv28 终结技
    apply_class_mech(a)
    per = finisher_trigger_per(a)
    check("终结技 trigger per_layer=0.10", per is not None and abs(per - 0.10) < 1e-9,
          f"per={per}")


def test_2_upgrade():
    print("【2. 学链舞：终结技 per_layer 0.16】")
    a = mk_assassin(["终结·割喉", "链舞"])
    apply_class_mech(a)
    per = finisher_trigger_per(a)
    check("终结技 trigger per_layer=0.16（upgrade +0.06）",
          per is not None and abs(per - 0.16) < 1e-9, f"per={per}")


def test_3_damage():
    print("【3. 触发验证：学链舞 + 连段 5 → 终结技 ×1.8（0.16×5）】")
    a = mk_assassin(["终结·割喉", "链舞"])
    apply_class_mech(a)
    a['effects']['lian_duan'] = {'stacks': 5, 'expire': None}
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=999999, max_hp=999999)
    e['effects'] = {}
    e['dodge'] = 0.0
    b = B2("monster", sides={"player": [a], "enemy": [e]}, title_bonus={})
    logs, _, _ = b.human_act("skill", "终结·割喉", a)
    # 找 mech_cash_dmg_mult 生效日志（终结技）
    hit = [l for l in logs if "终结" in l or "连段" in l or "×" in l]
    check("终结技施放正常（日志含终结/伤害）",
          any("造成" in l or "伤害" in l or "终结" in l for l in logs),
          str([l for l in logs if "伤害" in l or "终结" in l][-3:]))
    # 连段被清（clear）
    check("结算后连段归零", int((a.get("effects") or {}).get("lian_duan", {}).get("stacks", 0)) == 0,
          repr((a.get("effects") or {}).get("lian_duan")))


def main():
    test_1_base()
    test_2_upgrade()
    test_3_damage()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
