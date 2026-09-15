# -*- coding: utf-8 -*-
"""v181.M-passive P6 测试——DOT 乘区（万毒归宗 dot_calc 引擎 N9.14 钩子）。

跑法：python tests/test_passive_p6.py（exit=0 全绿）
覆盖（旧语义源 = 旧 DOT 结算毒伤乘区；引擎改动 = schedule.py dot_calc + EVENTS）：
  1. 万毒归宗装配：dot_calc passive_dot_mult（judge dot_key poison）
  2. DOT 结算：毒跳伤害 ×1.35（enemy 中毒 → _settle_time_effects 推进）
  3. 对照组：无被动 → 毒跳无加成
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p6.db"))
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


def mk_poisoner(skills):
    a = make_actor(uid="p_1", name="毒刃", side="player", kind="player",
                   human_controlled=True, class_name="cls_ci_ke", level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=150, matk=30, spd=80, hp=3000, max_hp=3000, mp=200, max_mp=200)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_enemy(hp=10000):
    e = make_actor(uid="e_1", name="毒桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=hp, max_hp=hp)
    e['effects'] = {}
    return e


def run_dot_tick(b, e):
    """推进 DOT 一跳：毒 interval 1.0——首调登记下一跳，二调触发。"""
    from saintess_engine.battle.schedule import _settle_time_effects
    b._now = 0.5
    _settle_time_effects(b, [])
    b._now = 1.6
    logs = []
    _settle_time_effects(b, logs)
    return logs


def test_1_assemble():
    print("【1. 万毒归宗装配：dot_calc passive_dot_mult】")
    p = mk_poisoner(["万毒归宗"])
    apply_class_mech(p)
    dc = [t for t in (p.get("triggers") or {}).get("dot_calc", [])
          if t.get("type") == "passive_dot_mult"]
    check("万毒归宗挂 dot_calc（judge dot_key poison）",
          len(dc) == 1 and (dc[0].get("judge") or {}).get("dot_key") == "poison",
          repr(dc))


def test_2_poison_boost():
    print("【2. DOT 结算：毒跳伤害 ×1.35】")
    p = mk_poisoner(["万毒归宗"])
    apply_class_mech(p)
    e = mk_enemy(hp=10000)
    e['effects']['poison'] = {'stacks': 5, 'expire': None, 'pct': 0.02}  # 条目 pct 覆盖：2%×5=10% max_hp=1000
    #   （表内 poison 权威系数 = atk×0.8 flat 无 pct；本条用条目覆盖固定 2%，只验 dot_calc 乘区通道）
    b = B2("monster", sides={"player": [p], "enemy": [e]}, title_bonus={})
    logs = run_dot_tick(b, e)
    # DOT 落地：1000×1.35=1350 → hp 10000→8650
    check("毒跳 ×1.35 落地（hp 8650）", int(e.get("hp", 0)) == 8650,
          f"hp={e.get('hp')} logs={[l for l in logs if '毒' in l or 'DOT' in l][-2:]}")
    check("dot_calc 乘区日志", any("DOT" in l or "☠️" in l for l in logs),
          str(logs[-3:]))


def test_3_control():
    print("【3. 对照组：无被动 → 毒跳无加成】")
    p = mk_poisoner([])  # 没学万毒归宗
    apply_class_mech(p)
    e = mk_enemy(hp=10000)
    e['effects']['poison'] = {'stacks': 5, 'expire': None, 'pct': 0.02}  # 条目 pct 覆盖 2%（表内 flat 型无 pct）
    b = B2("monster", sides={"player": [p], "enemy": [e]}, title_bonus={})
    logs = run_dot_tick(b, e)
    check("毒跳无加成（hp 9000）", int(e.get("hp", 0)) == 9000,
          f"hp={e.get('hp')}")


def test_4_weaken():
    print("【4. 剧毒之触：目标毒≥5 → 减速降防 debuff】")
    p = mk_poisoner(["剧毒之触"])
    apply_class_mech(p)
    dc = [t for t in (p.get("triggers") or {}).get("dot_calc", [])
          if t.get("type") == "passive_poison_weaken"]
    check("剧毒之触挂 dot_calc", len(dc) == 1, repr(dc))
    e = mk_enemy(hp=10000)
    e['effects']['poison'] = {'stacks': 5, 'expire': None, 'pct': 0.02}  # 同上（本组验毒≥5 层的减速降防）
    e['spd'] = 100
    e['def'] = 50
    b = B2("monster", sides={"player": [p], "enemy": [e]}, title_bonus={})
    logs = run_dot_tick(b, e)
    sd = (e.get("effects") or {}).get("spd_down")
    dd = (e.get("effects") or {}).get("def_down")
    check("spd_down 减速 30%（spd×0.7）",
          isinstance(sd, dict) and abs(float(sd.get("mult") or 0) - 0.7) < 1e-9
          and sd.get("stat") == "spd", repr(sd))
    check("def_down 降防 20%（def×0.8）",
          isinstance(dd, dict) and abs(float(dd.get("mult") or 0) - 0.8) < 1e-9
          and dd.get("stat") == "def", repr(dd))


def test_5_weaken_low_layers():
    print("【5. 剧毒之触负向：毒层 <5 → 无 debuff】")
    p = mk_poisoner(["剧毒之触"])
    apply_class_mech(p)
    e = mk_enemy(hp=10000)
    e['effects']['poison'] = {'stacks': 3, 'expire': None, 'pct': 0.02}  # 3 层 < 5（验无减速；pct 覆盖仅为让毒跳有伤害）
    b = B2("monster", sides={"player": [p], "enemy": [e]}, title_bonus={})
    logs = run_dot_tick(b, e)
    sd = (e.get("effects") or {}).get("spd_down")
    check("毒层不足 → 无减速", sd is None, repr(sd))


def main():
    test_1_assemble()
    test_2_poison_boost()
    test_3_control()
    test_4_weaken()
    test_5_weaken_low_layers()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
