# -*- coding: utf-8 -*-
"""v181「影舞·无间」改词裁定验收（2026-09-11）。

## 背景

`影舞·无间`（刺客·影舞者线 lv97 被动）原声明 `passive.proc = shadow_dance_cd / cdr 0.20`，
desc「影舞态中所有技能冷却 −20%」。**但影舞态本身就带 −20% CD**
（`EFFECT_RULES["shadow_dance"].cd_mult = 0.8`，`actions.py` 施法时读态声明取 min）——
两者完全重复；硬接就是 ×0.8×0.8 = −36%，超设计。

**裁定（改词）**：把该槽位改为「踏入影舞之境所需连段 5 → 3」（proc 改名
`shadow_dance_ease`，参数 `threshold`）。不叠乘区、纯收益、零引擎改动。

本测试锁住：数据改词正确 + 门槛行为正确（学/不学两态）+ 旧 proc 名不再出现。

跑法：python tests/test_v181_shadow_dance_ease.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_sde.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import Battle as B2, make_actor  # noqa: E402
from _engine_harness import boot as _eng_cfg  # noqa: E402
_eng_cfg()
from content.skills import skill_info  # noqa: E402
from content.mech import class_mech as CMP  # noqa: E402  (import 即注册动作)
from saintess_engine.battle.effects import ACTION_HANDLERS  # noqa: E402

CLS = "cls_ci_ke"

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk(learned):
    a = make_actor(uid="p1", name="影", side="player", kind="player",
                   human_controlled=True, class_name=CLS, level=97,
                   hp=2000, max_hp=2000, mp=200, max_mp=200,
                   atk=200, matk=100, spd=20, crit=0.05,
                   equipment={}, skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=3, attributes={},
                   **{"def": 40, "mdef": 30})
    a["effects"] = {}
    return a


def try_enter(learned, stacks):
    """跑导演动作：连段 = stacks 时能否进影舞态。返回 (是否进入, logs)。"""
    a = mk(learned)
    a["effects"]["lian_duan"] = {"stacks": stacks}
    b = B2(btype="monster", sides={"player": [a], "enemy": [mk_enemy()]})
    logs = []
    ACTION_HANDLERS['class_shadow_dance_enter'](b, a, None, {}, logs)
    return bool((a.get("effects") or {}).get("shadow_dance")), logs


def mk_enemy():
    e = make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                   hp=9999, max_hp=9999, atk=1, matk=1, spd=5, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 0, "mdef": 0})
    e["effects"] = {}
    return e


def test_data():
    print("【1. 数据改词】")
    info = skill_info(CLS, "影舞·无间")
    check("技能存在", bool(info), f"info={info}")
    ps = (info or {}).get("passive") or {}
    check("proc 已改为 shadow_dance_ease", ps.get("proc") == "shadow_dance_ease", f"proc={ps.get('proc')}")
    check("门槛参数 threshold = 3", int(ps.get("threshold", 0) or 0) == 3, f"ps={ps}")
    check("旧 proc 名 shadow_dance_cd 已不再出现", "shadow_dance_cd" not in str(ps), f"ps={ps}")
    check("旧 cdr 字段已删", "cdr" not in ps, f"ps={ps}")
    # 影舞态自带的 CD 减免仍在（改词没动它）
    from content.mech.params import EFFECT_RULES
    check("影舞态自带 cd_mult 0.8 保留（−20% 不丢）",
          float((EFFECT_RULES.get("shadow_dance") or {}).get("cd_mult", 1.0)) == 0.8,
          f"sd={EFFECT_RULES.get('shadow_dance')}")


def test_behavior():
    print("【2. 门槛行为】")
    ok, logs = try_enter(["暗影步"], 5)
    check("未学影舞·无间：连段 5 → 进入", ok, f"logs={logs}")
    ok, logs = try_enter(["暗影步"], 3)
    check("未学影舞·无间：连段 3 → 不进（原门槛 5）", not ok, f"logs={logs}")
    ok, logs = try_enter(["暗影步", "影舞·无间"], 3)
    check("学到影舞·无间：连段 3 → 进入（门槛降为 3）", ok, f"logs={logs}")
    ok, logs = try_enter(["暗影步", "影舞·无间"], 2)
    check("学到影舞·无间：连段 2 → 仍不进（门槛不是 0）", not ok, f"logs={logs}")
    ok, logs = try_enter(["暗影步", "影舞·无间"], 5)
    check("学到后连段 5 → 进入（不倒退）", ok, f"logs={logs}")
    _ok2, _logs2 = try_enter(["暗影步", "影舞·无间"], 2)
    check("未达门槛时日志给出实际门槛（/3，不是 /5）",
          any("/3" in str(x) for x in _logs2), f"logs={_logs2}")
    _ok3, _logs3 = try_enter(["暗影步"], 3)
    check("未学时门槛提示仍是 /5", any("/5" in str(x) for x in _logs3), f"logs={_logs3}")

    # 缺字段铁律：非刺客职业 / 无 learned_skills → 门槛回落 5，不炸
    a = mk([])
    a["effects"]["lian_duan"] = {"stacks": 4}
    b = B2(btype="monster", sides={"player": [a], "enemy": [mk_enemy()]})
    logs = []
    ACTION_HANDLERS['class_shadow_dance_enter'](b, a, None, {}, logs)
    check("无技能数据：门槛回落 5（连段 4 → 不进）",
          not (a.get("effects") or {}).get("shadow_dance"), f"logs={logs}")


if __name__ == "__main__":
    test_data()
    test_behavior()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
