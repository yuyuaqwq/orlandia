# -*- coding: utf-8 -*-
"""v181 渠道条件攒取（channel `when`）：装配透传 + 动作侧谓词求值验证。

覆盖：
1. 装配器透传：资源条目声明 when → 生成的 trigger 带 when；无声明不写键（零默认值）
2. 动作遵条件：条件不满足 → 本次不攒；满足 → 攒
3. cap clamp 仍生效（条件满足但已满层 → 不加）
4. 未知 judge kind → fail-closed（不攒，不静默放行）
5. 多谓词 AND（任一不满足即不攒）+ res_ge 谓词可用
6. 无 when 声明的旧渠道行为零变化（回归）
7. 归属过滤不受影响（非本职业不装配 → 不白拿）

背景：磐核「守御姿态下受击 +1」（v153 §六）需要「按姿态攒资源」，
而渠道声明原本不支持条件过滤（_CHANNEL_EVENTS 的 extra 只有 kind/not_basic）。

★ 本测试走真实契约：先 apply_class_channels 装配 → 取装配产物当 params → 直调动作。
   （fire() 派发时正是把 trigger dict 逐条传给动作；_owner 由 fire 注入声明者自己。）

跑法：python tests/test_v181_channel_when.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_v181_channel_when.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from ext_combat.battle import effects as EFX  # noqa: E402
from ext_combat import Battle as B2, make_actor
from content.mech import class_mech as CM  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []

CLASS = "cls_test_guard"


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


# ---- 测试用规则表（注入 config；机制测试独立于真实数据）----
WHEN_STANCE = [{"judge": {"kind": "has_effect", "key": "stance_guard"}}]
RULES = {
    "guard_core": {
        "name": "磐核", "cap": 5, "start_classes": [CLASS],
        # 混合形态：受击需姿态（条件），技能命中无条件（简写）
        "channels": {"taken": {"gain": 1, "when": WHEN_STANCE}, "skill_hit": 1},
    },
    "plain_res": {          # 全简写（无条件，回归对照）
        "name": "普通资源", "cap": 3, "start_classes": [CLASS],
        "channels": {"taken": 2},
    },
    "multi_res": {          # 多谓词 AND + res_ge
        "name": "双门资源", "cap": 5, "start_classes": [CLASS],
        "channels": {"taken": {"gain": 1, "when": [
            {"judge": {"kind": "has_effect", "key": "stance_guard"}},
            {"judge": {"kind": "res_ge", "res": "guard_core", "ge_field": "stacks"},
             "stacks": 2}]}},
    },
    "bad_res": {            # 未知 kind（fail-closed 对照）
        "name": "坏条件资源", "cap": 5, "start_classes": [CLASS],
        "channels": {"taken": {"gain": 1, "when": [{"judge": {"kind": "no_such_kind"}}]}},
    },
    "frac_res": {           # float gain（每刻 0.4 类小数攒取）
        "name": "小数资源", "cap": 5, "start_classes": [CLASS],
        "channels": {"taken": {"gain": 0.4, "when": WHEN_STANCE}},
    },
}


def mk_battle(rules=None):
    """建战斗 + 已装配渠道的 actor（真实装配路径）。"""
    _b2c.set_config("effect_rules", rules if rules is not None else RULES)
    a = make_actor(uid="p1", name="拳师", side="player", kind="player",
                   human_controlled=True, class_name=CLASS, level=30,
                   hp=9999, max_hp=9999, mp=100, max_mp=100,
                   atk=100, matk=50, spd=10, crit=0.0,
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 30})
    e = make_actor(uid="e1", name="怪", side="enemy", kind="monster",
                   hp=9999, max_hp=9999, atk=50, matk=20, spd=10, crit=0.0,
                   level=30, exp=0, gold=0, **{"def": 10, "mdef": 10})
    b = B2(btype="monster", sides={"player": [a], "enemy": [e]})
    CM.apply_class_channels(a, rules if rules is not None else RULES)
    return b, a


def assembled(actor, res):
    """取装配产物中该资源的 trigger（无 → None）。"""
    for t in ((actor.get("triggers") or {}).get("on_taken") or []):
        if isinstance(t, dict) and t.get("res") == res:
            return t
    return None


def fire_gain(battle, actor, res):
    """按 fire() 的契约派发：装配产物 + _owner 注入 → 直调动作。"""
    # 旧宿主壳 `class_mech_proc.install()` 是幂等空委托（真语义 = 包内 import 期即注册
    # 39 个动作）；改口后 `from content.mech import class_mech` 已完成同一注册，调用随之退休。
    t = assembled(actor, res)
    if t is None:
        return None
    params = dict(t)
    params.setdefault("_owner", actor)      # fire() 的注入语义
    h = EFX.ACTION_HANDLERS["class_res_channel_gain"]
    logs = []
    h(battle, actor, actor, params, logs)
    return logs


def st(actor, key):
    e = (actor.get("effects") or {}).get(key)
    return float(e.get("stacks", 0) or 0) if isinstance(e, dict) else 0.0


def enter_stance(actor, on=True):
    ef = actor.setdefault("effects", {})
    if on:
        ef["stance_guard"] = {"stacks": 1, "expire": 999.0}
    else:
        ef.pop("stance_guard", None)


def test_1_assembler_passthrough():
    print("【1. 装配器透传 when（有声明带键 / 无声明不写键）】")
    b, a = mk_battle()
    g = assembled(a, "guard_core") or {}
    check("guard_core 渠道已装配", bool(g), str(a.get("triggers")))
    check("when 透传进 trigger", g.get("when") == WHEN_STANCE, str(g.get("when")))
    check("gain 值来自声明(1)", g.get("gain") == 1, str(g.get("gain")))
    # 同资源不同渠道：skill_hit 无条件（简写）→ 装配到 skill_hit 事件、不带 when
    sh = [t for t in ((a.get("triggers") or {}).get("skill_hit") or [])
          if isinstance(t, dict) and t.get("res") == "guard_core"]
    check("同资源可混用：skill_hit 装配在 skill_hit 事件", len(sh) == 1, str(sh))
    check("skill_hit 渠道无 when（简写形态不写键）", sh and "when" not in sh[0], str(sh[:1]))
    check("skill_hit gain=1", sh and sh[0].get("gain") == 1, str(sh[:1]))
    p = assembled(a, "plain_res") or {}
    check("全简写渠道 → 不写 when 键（零默认值）", "when" not in p, str(p))
    check("plain_res gain=2（无声明仍装配）", p.get("gain") == 2, str(p.get("gain")))


def test_2_condition_gates_gain():
    print("【2. 动作遵条件：无态不攒 / 进态才攒 / 退态停攒】")
    b, a = mk_battle()
    fire_gain(b, a, "guard_core")
    check("无守护姿态 → 未攒", st(a, "guard_core") == 0, f"stacks={st(a,'guard_core')}")
    enter_stance(a)
    fire_gain(b, a, "guard_core")
    check("守护姿态中 → 攒 +1", st(a, "guard_core") == 1, f"stacks={st(a,'guard_core')}")
    fire_gain(b, a, "guard_core")
    check("连续攒 +1", st(a, "guard_core") == 2, f"stacks={st(a,'guard_core')}")
    enter_stance(a, False)
    fire_gain(b, a, "guard_core")
    check("姿态消失 → 停止攒", st(a, "guard_core") == 2, f"stacks={st(a,'guard_core')}")


def test_3_cap_still_clamps():
    print("【3. 条件满足但满层 → cap clamp 仍生效】")
    b, a = mk_battle()
    enter_stance(a)
    for _ in range(8):
        fire_gain(b, a, "guard_core")
    check("攒到 cap(5) 封顶", st(a, "guard_core") == 5, f"stacks={st(a,'guard_core')}")


def test_4_unknown_kind_fail_closed():
    print("【4. 未知 judge kind → fail-closed（不攒，不静默放行）】")
    b, a = mk_battle()
    enter_stance(a)
    fire_gain(b, a, "bad_res")
    check("未知条件 → 不攒", st(a, "bad_res") == 0, f"stacks={st(a,'bad_res')}")


def test_5_multi_predicate_and():
    print("【5. 多谓词 AND：任一不满足即不攒（含 res_ge 谓词）】")
    b, a = mk_battle()
    enter_stance(a)                       # 姿态 ✓ / guard_core=0 < 2
    fire_gain(b, a, "multi_res")
    check("姿态 ✓ 但资源<2 → 不攒", st(a, "multi_res") == 0, f"stacks={st(a,'multi_res')}")
    a["effects"]["guard_core"] = {"stacks": 2, "expire": 999.0}
    fire_gain(b, a, "multi_res")
    check("两门都满足 → 攒", st(a, "multi_res") == 1, f"stacks={st(a,'multi_res')}")
    enter_stance(a, False)                # 资源仍足但姿态消失
    fire_gain(b, a, "multi_res")
    check("姿态消失 → 不攒（AND 语义）", st(a, "multi_res") == 1, f"stacks={st(a,'multi_res')}")


def test_6_legacy_no_when_unchanged():
    print("【6. 无 when 声明的旧渠道行为零变化（回归）】")
    b, a = mk_battle()
    fire_gain(b, a, "plain_res")
    check("无声明 → 无条件攒（旧行为）", st(a, "plain_res") == 2, f"stacks={st(a,'plain_res')}")
    fire_gain(b, a, "plain_res")
    check("无声明 → 继续攒", st(a, "plain_res") == 3, f"stacks={st(a,'plain_res')}")
    fire_gain(b, a, "plain_res")
    check("cap(3) 封顶", st(a, "plain_res") == 3, f"stacks={st(a,'plain_res')}")


def test_8_fractional_gain():
    print("【8. float gain（0.4/刻 类小数攒取）——非整数不被装配器丢弃】")
    b, a = mk_battle()
    f = assembled(a, "frac_res")
    check("0.4 渠道已装配（int() 截断不再丢）", bool(f), str(a.get("triggers")))
    check("gain 保持 0.4", f and abs(float(f.get("gain")) - 0.4) < 1e-9, str(f))
    enter_stance(a)
    fire_gain(b, a, "frac_res")
    check("姿态中 → +0.4", abs(st(a, "frac_res") - 0.4) < 1e-9, f"stacks={st(a,'frac_res')}")
    fire_gain(b, a, "frac_res")
    check("累加到 0.8（精度保真）", abs(st(a, "frac_res") - 0.8) < 1e-9, f"stacks={st(a,'frac_res')}")
    enter_stance(a, False)
    fire_gain(b, a, "frac_res")
    check("退态 → 停止攒", abs(st(a, "frac_res") - 0.8) < 1e-9, f"stacks={st(a,'frac_res')}")


def test_7_start_classes_guard_unchanged():
    print("【7. 归属过滤不受影响（非本职业不装配 → 不白拿）】")
    b, a = mk_battle()
    a["class_name"] = "cls_other"
    a["triggers"] = {}
    CM.apply_class_channels(a, RULES)
    check("非声明职业 → 不装配", not (a.get("triggers") or {}).get("on_taken"),
          str(a.get("triggers")))


if __name__ == "__main__":
    test_1_assembler_passthrough()
    test_2_condition_gates_gain()
    test_3_cap_still_clamps()
    test_4_unknown_kind_fail_closed()
    test_5_multi_predicate_and()
    test_6_legacy_no_when_unchanged()
    test_7_start_classes_guard_unchanged()
    test_8_fractional_gain()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
