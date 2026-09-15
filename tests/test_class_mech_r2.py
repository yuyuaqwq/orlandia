# -*- coding: utf-8 -*-
"""职业机制装配层 R2a 测试（v181.M）——资源自然回/开局满额/消耗链路（游侠 energy 样板）。

跑法：python tests/test_class_mech_r2.py（exit=0 全绿）
覆盖：
  1. start_full：游侠装配 → effects energy 开局满 100（非游侠无此条目）
  2. regen period dir=gain：每刻 +18，clamp cap 100
  3. 0 层也回（绕过 n<=0 拦截，防耗干卡死）
  4. 游侠技能 res_cost 扣 energy（真实消费端）
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_mech_r2.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from saintess_engine import Battle as B2, make_actor
from saintess_engine import actions as A
from saintess_engine.battle.actors import ActCtx
from saintess_engine.battle.schedule import _settle_time_effects
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

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


def mk_ranger(learned=()):
    a = make_actor(uid="p1", name="游侠", side="player", kind="player",
                   human_controlled=True, class_name="cls_you_xia", level=40,
                   hp=2500, max_hp=2500, mp=200, max_mp=200,
                   atk=180, matk=60, spd=15, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 30})
    apply_class_mech(a)
    return a


def mk_warrior():
    a = make_actor(uid="p9", name="战士", side="player", kind="player",
                   human_controlled=True, class_name="cls_zhan_shi", level=30,
                   hp=3000, max_hp=3000, mp=100, max_mp=200,
                   atk=150, matk=50, spd=10, crit=0.05,
                   skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 50, "mdef": 30})
    apply_class_mech(a)
    return a


def mk_enemy():
    return make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                      hp=99999, max_hp=99999, atk=1, matk=1, spd=5, crit=0.0,
                      level=40, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(*actors):
    sides = {"player": [], "enemy": []}
    for a in actors:
        sides[a.get("side") or "enemy"].append(a)
    b = B2(btype="monster", sides=sides)
    b._now = 0.0
    return b


def _advance(b, t):
    """把战斗时钟推到 t 并结算时间效果（返回日志）。"""
    b._now = float(t)
    logs = []
    _settle_time_effects(b, logs)
    return logs


def t_start_full():
    print("【1. start_full：游侠开局满 100】")
    p = mk_ranger()
    ef = (p.get("effects") or {}).get("energy")
    check("energy 条目开局满 100", isinstance(ef, dict) and int(ef.get("stacks", 0)) == 100, repr(ef))
    w = mk_warrior()
    check("非 start_full 职业无 energy 条目", "energy" not in (w.get("effects") or {}), repr(w.get("effects")))


def t_regen():
    print("【2. regen period dir=gain：每刻 +18 clamp cap】")
    p = mk_ranger()
    e = mk_enemy()
    b = _battle(p, e)
    p["effects"]["energy"]["stacks"] = 50
    _advance(b, 1.0)          # 首跳登记（dnext = now+1）
    _advance(b, 2.5)          # 到跳 → +18
    st = p["effects"]["energy"]["stacks"]
    check("50 → 68", st == 68, f"stacks={st}")
    _advance(b, 3.5)          # 再跳 → 86
    st = p["effects"]["energy"]["stacks"]
    check("68 → 86", st == 86, f"stacks={st}")
    _advance(b, 4.5)          # 86+18=104 → clamp 100
    st = p["effects"]["energy"]["stacks"]
    check("86+18 clamp 100", st == 100, f"stacks={st}")


def t_regen_zero():
    print("【3. 0 层也回（绕过 n<=0 拦截）】")
    p = mk_ranger()
    e = mk_enemy()
    b = _battle(p, e)
    p["effects"]["energy"]["stacks"] = 0
    _advance(b, 1.0)
    _advance(b, 2.5)
    st = p["effects"]["energy"]["stacks"]
    check("0 → 18", st == 18, f"stacks={st}")


def t_spend():
    print("【4. 游侠技能 res_cost 扣 energy（真实消费端）】")
    p = mk_ranger(learned=("疾风连射",))
    e = mk_enemy()
    b = _battle(p, e)
    info = {"kind": "物理", "mech": "spd_down", "res_cost": {"energy": 22},
            "name": "疾风连射", "exprs": ["atk*0.9"]}
    A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="疾风连射", info=info, target=e))
    st = p["effects"]["energy"]["stacks"]
    check("100 → 78", st == 78, f"stacks={st}")
    # 消耗后自然回链路：78 → 96
    _advance(b, 1.0)
    _advance(b, 2.5)
    st = p["effects"]["energy"]["stacks"]
    check("78 → 96（消耗后可回）", st == 96, f"stacks={st}")


def main():
    print("== 职业机制装配 R2a 资源渠道 ==")
    t_start_full()
    t_regen()
    t_regen_zero()
    t_spend()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
