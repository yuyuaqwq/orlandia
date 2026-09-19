# -*- coding: utf-8 -*-
"""v181.M-passive P12 测试——刺客影舞态批（暗影步进态 + CD−20% + 暗影步·极）。

跑法：python tests/test_passive_p12.py（exit=0 全绿）
覆盖（v153 影舞者线）：
  1. 暗影步：连段 <5 → 不进态；连段 ≥5 → 进入（effects.shadow_dance）
  2. 态内 CD−20%（cd_mult 0.8 引擎修正）
  3. 暗影步·极：态内 act_cast → spd ×1.25 buff；非态清
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p12.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_assassin(skills):
    a = make_actor(uid="p_1", name="刺客", side="player", kind="player",
                   human_controlled=True, class_name="cls_ci_ke", level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=200, matk=30, spd=80, hp=3000, max_hp=3000, mp=300, max_mp=300)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(a):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=99999, max_hp=99999)
    e['effects'] = {}
    e['dodge'] = 0.0
    return B2("monster", sides={"player": [a], "enemy": [e]}, title_bonus={})


def test_1_enter():
    print("【1. 暗影步进态条件】")
    # 连段不足
    a = mk_assassin(["暗影步"])
    apply_class_mech(a)
    a['effects']['lian_duan'] = {'stacks': 3, 'expire': None}
    b = mk_battle(a)
    a2 = b.sides_of("player")[0]
    logs, _, _ = b.human_act("skill", "暗影步", a2)
    check("连段 3/5 → 不进态",
          (a2.get("effects") or {}).get("shadow_dance") is None,
          repr((a2.get("effects") or {}).get("shadow_dance")))
    # 连段满
    a3 = mk_assassin(["暗影步"])
    apply_class_mech(a3)
    a3['effects']['lian_duan'] = {'stacks': 5, 'expire': None}
    b3 = mk_battle(a3)
    a4 = b3.sides_of("player")[0]
    logs3, _, _ = b3.human_act("skill", "暗影步", a4)
    check("连段 5/5 → 进入影舞态",
          (a4.get("effects") or {}).get("shadow_dance") is not None,
          repr((a4.get("effects") or {}).get("shadow_dance")))


def test_2_cd_mult():
    print("【2. 影舞态内技能 CD−20%（cd_mult 0.8）】")
    from saintess_engine.battle.battle import _now_of
    # 用暗影步自身 cd=16：先不进态时施放记 cd 16；进态后放带 cd 技能
    a = mk_assassin(["暗影步", "幻影连刺"])
    apply_class_mech(a)
    a['effects']['lian_duan'] = {'stacks': 5, 'expire': None}
    b = mk_battle(a)
    a2 = b.sides_of("player")[0]
    logs, _, _ = b.human_act("skill", "暗影步", a2)  # 进态
    check("暗影步后态在", (a2.get("effects") or {}).get("shadow_dance") is not None, "")
    # 幻影连刺 cd 查数据
    from content.skills import skill_info
    info = skill_info("cls_ci_ke", "幻影连刺") or {}
    base_cd = int(info.get("cd", 0) or 0)
    logs2, _, _ = b.human_act("skill", "幻影连刺", a2)
    now = _now_of(b)
    cd_end = float((a2.get("cooldown") or {}).get("幻影连刺", 0) or 0)
    if base_cd > 0:
        now = _now_of(b)
        full_cd_end = now + base_cd
        check("态内 CD 有折扣（cd_end < 满值，且接近 ×0.8）",
              cd_end < full_cd_end - 1 and cd_end > now + base_cd * 0.5,
              f"cd_end={cd_end:.1f} full={full_cd_end:.1f} base={base_cd}")
    else:
        check("幻影连刺有 cd 可测", False, f"cd={base_cd}")


def test_3_shadow_bonus():
    print("【3. 暗影步·极：态内 spd ×1.25】")
    from saintess_engine.battle.stats import actor_stats as _as
    a = mk_assassin(["暗影步·极", "影刃"])
    apply_class_mech(a)
    base_spd = float((_as(None, a) or {}).get("spd", 0) or 0)
    a['effects']['shadow_dance'] = {'stacks': 1, 'expire': None}
    a['effects']['lian_duan'] = {'stacks': 5, 'expire': None}
    b = mk_battle(a)
    a2 = b.sides_of("player")[0]
    logs, _, _ = b.human_act("skill", "影刃", a2)
    sd = (a2.get("effects") or {}).get("_shadow_spd")
    check("态内写 spd ×1.25 buff", isinstance(sd, dict)
          and abs(float(sd.get("mult") or 0) - 1.25) < 1e-9, repr(sd))
    after_spd = float((_as(b, a2) or {}).get("spd", 0) or 0)
    check("面板 spd ×1.25", abs(after_spd - base_spd * 1.25) < 1.0,
          f"base={base_spd} after={after_spd}")
    # 非态 → 清
    a2['effects'].pop("shadow_dance", None)
    b2 = mk_battle(a2)
    # 新战斗 = 新时间轴 → 清残留冷却（口径同 test_passive_p3.test_1）
    a2['cooldown'] = {}
    logs2, _, _ = b2.human_act("skill", "影刃", a2)
    check("非态 → 清 spd buff",
          (a2.get("effects") or {}).get("_shadow_spd") is None, "")


def main():
    test_1_enter()
    test_2_cd_mult()
    test_3_shadow_bonus()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
