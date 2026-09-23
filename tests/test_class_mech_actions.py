# -*- coding: utf-8 -*-
"""职业机制装配层 R1a 测试（v181.M）——finisher 兑现双通道（样板）。

跑法：python tests/test_class_mech_actions.py（exit=0 全绿）
覆盖：
  1. 装配：学有终结技的 actor → triggers 挂 dmg_calc + skill_hit
  2. 无终结技 actor → 不挂（零噪音）
  3. dmg_calc 乘区：连段 5 → 伤害 ×1.5（每段 +10%）
  4. 非 finisher 技能不触发乘区
  5. skill_hit 命中后清层（连段归零）
  6. keep_on_kill 技能保留连段
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_mech_proc.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor
from ext_combat.battle.effect_triggers import fire
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_assassin(learned=("终结·割喉",)):
    a = make_actor(uid="p1", name="影舞", side="player", kind="player",
                   human_controlled=True, class_name="cls_ci_ke", level=60,
                   hp=3000, max_hp=3000, mp=300, max_mp=300,
                   atk=200, matk=100, spd=15, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 60, "mdef": 40})
    apply_class_mech(a)
    return a


def mk_enemy():
    return make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                      hp=99999, max_hp=99999, atk=1, matk=1, spd=5, crit=0.0,
                      level=60, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def t_assemble():
    print("【1. 装配：学有终结技 → 双通道 triggers（声明驱动参数化）】")
    p = mk_assassin()
    tr = p.get("triggers") or {}
    dm = [x for x in tr.get("dmg_calc", []) if x.get("action") == "mech_cash_dmg_mult"]
    cl = [x for x in tr.get("skill_hit", []) if x.get("action") == "mech_cash_clear"]
    check("dmg_calc 挂参数化执行器（mech=finisher/key=lian_duan/per=0.10）",
          len(dm) == 1 and dm[0].get("mech") == "finisher"
          and dm[0].get("key") == "lian_duan" and abs(float(dm[0].get("per_layer")) - 0.10) < 1e-6,
          repr(dm))
    check("skill_hit 挂清层执行器", len(cl) == 1 and cl[0].get("key") == "lian_duan", repr(cl))


def t_no_finisher():
    print("【2. 无终结技 actor 不装配】")
    p = mk_assassin(learned=("刺击",))
    tr = p.get("triggers") or {}
    check("无 dmg_calc 条目", not tr.get("dmg_calc"), repr(tr))
    check("无 skill_hit 条目", not tr.get("skill_hit"), repr(tr))


def t_dmg_mult():
    print("【3. dmg_calc 乘区：连段 5 → ×1.5】")
    p = mk_assassin()
    e = mk_enemy()
    b = _battle(p, e)
    p.setdefault("effects", {})["lian_duan"] = {"stacks": 5, "expire": 99999}
    info = {"mech": "finisher", "name": "终结·割喉", "kind": "物理"}
    logs = []
    fire(b, "dmg_calc", {"actor": p, "target": e, "dmg": 100, "is_crit": False,
                         "info": info, "mult": 1.0}, logs)
    m = float(getattr(b, "_fire_ctx", {}).get("mult", 1.0))
    check("mult == 1.5", abs(m - 1.5) < 1e-6, f"mult={m}")
    check("文案含终结技", any("终结技" in str(x) for x in logs), repr(logs))


def t_non_finisher_no_mult():
    print("【4. 非 finisher 技能不触发乘区】")
    p = mk_assassin()
    e = mk_enemy()
    b = _battle(p, e)
    p.setdefault("effects", {})["lian_duan"] = {"stacks": 3, "expire": 99999}
    logs = []
    fire(b, "dmg_calc", {"actor": p, "target": e, "dmg": 100, "is_crit": False,
                         "info": {"mech": "lian_duan", "name": "刺击"}, "mult": 1.0}, logs)
    m = float(getattr(b, "_fire_ctx", {}).get("mult", 1.0))
    check("mult 保持 1.0", abs(m - 1.0) < 1e-6, f"mult={m}")


def t_clear():
    print("【5. skill_hit 命中后连段归零】")
    p = mk_assassin()
    e = mk_enemy()
    b = _battle(p, e)
    p.setdefault("effects", {})["lian_duan"] = {"stacks": 5, "expire": 99999}
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "dmg": 200,
                          "info": {"mech": "finisher", "name": "终结·割喉"}}, logs)
    st = (p.get("effects") or {}).get("lian_duan", {}).get("stacks", 99)
    check("连段归零", st == 0, f"stacks={st}")


def t_keep_on_kill():
    print("【6. keep_on_kill 保留连段】")
    p = mk_assassin()
    e = mk_enemy()
    b = _battle(p, e)
    p.setdefault("effects", {})["lian_duan"] = {"stacks": 5, "expire": 99999}
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "dmg": 200,
                          "info": {"mech": "finisher", "keep_on_kill": True}}, logs)
    st = (p.get("effects") or {}).get("lian_duan", {}).get("stacks", 0)
    check("连段保留 5", st == 5, f"stacks={st}")


def main():
    print("== 职业机制装配 R1a finisher 兑现 ==")
    t_assemble()
    t_no_finisher()
    t_dmg_mult()
    t_non_finisher_no_mult()
    t_clear()
    t_keep_on_kill()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
