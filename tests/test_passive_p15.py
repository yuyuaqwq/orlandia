# -*- coding: utf-8 -*-
"""v181.M-passive P15 测试——格斗士攻线破绽三被动（气力之心 / 破绽·极双段）。

背景：23 条推条技能数据（shaken_gain）已回填（commit ab48caf），推条消费链已接线
（battle_bar_procs，commit ff4289c）——本批补最后一个缺口 = 被动本体（原先
PASSIVE_PROC 表零条目），语义源 = 旧 battle.py `_deal_damage` / `_skill_hit_settle`
逐字（v153 §六 档位表）。

跑法：python tests/test_passive_p15.py（exit=0 全绿）
覆盖：
  1. 装配：学什么挂什么（气力之心 → dmg_calc；破绽·极 → dmg_calc + skill_hit 延长段）
  2. 气力之心：破绽 val ≥15 → 对其伤害 ×1.2（门槛读 passive.bar_at）
  3. 破绽·极乘区段：破防态（trigger_count>0 且免疫窗口内）→ ×1.5（broken_mult）
  4. 破绽·极延长段：本次命中触发破绽 → 免疫窗口 1 → 2（extend 1）
  5. 顺序契约：注入（bar_gain）先于被动后置段（延长段读得到刚触发的窗口）
  6. 零噪音/边界：未达门槛不增伤 / 未触发不延长 / 非拳师不挂
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p15.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine.battle.effect_triggers import fire  # noqa: E402
from content.mech import class_mech as CMP  # noqa: E402

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


def mk_player(learned, cls="cls_wu_seng"):
    return make_actor(uid="p1", name="拳师", side="player", kind="player",
                      human_controlled=True, class_name=cls, level=99,
                      hp=3000, max_hp=3000, mp=300, max_mp=300,
                      atk=100, matk=80, spd=20, crit=0.0,
                      equipment={}, skills=[], learned_skills=list(learned),
                      **{"def": 40, "mdef": 30})


def mk_enemy(hp=99999):
    e = make_actor(uid="e1", name="木桩怪", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                   level=20, **{"def": 0, "mdef": 0})
    e["dodge"] = 0.0
    return e


def new_battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def bar_of(a):
    from saintess_engine.gauge import bar_effect_key
    return (a.get("effects") or {}).get(bar_effect_key("shaken")) or {}


def dmg_calc_trigs(actor):
    return [x for x in ((actor.get("triggers") or {}).get("dmg_calc") or [])
            if isinstance(x, dict)
            and (x.get("type") or x.get("action")) == "passive_dmg_mult"]


def skill_hit_acts(actor, action):
    return [x for x in ((actor.get("triggers") or {}).get("skill_hit") or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == action]


def calc_mult(p, e, base_dmg=100):
    """按 saintess_engine 真实口径跑一次 dmg_calc 乘区钩子，返回累乘后 mult。

    fire() 内部对 ctx 做 dict 副本（事件总线约定）→ 乘区结果读 battle._fire_ctx。
    """
    b = new_battle(p, e)
    logs = []
    fire(b, "dmg_calc", {"actor": p, "target": e, "dmg": base_dmg, "info": {}, "mult": 1.0}, logs)
    return float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0), logs


def test_1_install():
    print("【1. 装配：学什么挂什么】")
    p = mk_player(["钢拳", "气力之心", "破绽·极"])
    CMP.apply_class_mech(p)
    ts = dmg_calc_trigs(p)
    labels = sorted(t.get("label") for t in ts)
    check("气力之心 + 破绽·极 各挂 1 条 dmg_calc 乘区", len(ts) == 2, f"trigs={ts}")
    check("标签来自技能名", labels == ["气力之心", "破绽·极"], f"labels={labels}")
    check("气力之心 judge=target_bar_ge/shaken",
          any((t.get("judge") or {}).get("kind") == "target_bar_ge"
              and (t.get("judge") or {}).get("bar") == "shaken" for t in ts),
          f"trigs={ts}")
    check("气力之心参数 bar_at=15 / mult=0.20（passive dict 并入）",
          any(t.get("bar_at") == 15 and abs(float(t.get("mult") or 0) - 0.20) < 1e-9
              for t in ts), f"trigs={ts}")
    check("破绽·极 judge=target_bar_broken/shaken",
          any((t.get("judge") or {}).get("kind") == "target_bar_broken" for t in ts),
          f"trigs={ts}")
    check("破绽·极参数 broken_mult=0.50 / extend=1",
          any(abs(float(t.get("broken_mult") or 0) - 0.5) < 1e-9 and t.get("extend") == 1
              for t in ts), f"trigs={ts}")
    ext = skill_hit_acts(p, "passive_bar_extend")
    check("破绽·极 also 段挂 skill_hit 延长动作", len(ext) == 1, f"ext={ext}")
    check("延长段 judge.bar=shaken / extend=1",
          ext and (ext[0].get("judge") or {}).get("bar") == "shaken" and ext[0].get("extend") == 1,
          f"ext={ext}")
    check("推条注入排在 skill_hit 首位（顺序契约）",
          (skill_hit_acts(p, "bar_gain") and
           ((p.get("triggers") or {}).get("skill_hit") or [{}])[0].get("action") == "bar_gain"),
          f"skill_hit={(p.get('triggers') or {}).get('skill_hit')}")
    # 反向：非拳师（战士学不到这些被动，模拟误配）不挂
    p2 = mk_player(["钢拳"], cls="cls_zhan_shi")
    CMP.apply_class_mech(p2)
    check("未学破绽被动 → 零乘区（零噪音）", not dmg_calc_trigs(p2), f"trigs={dmg_calc_trigs(p2)}")


def test_2_awareness():
    print("【2. 气力之心：破绽 ≥15 → 伤害 ×1.2】")
    p = mk_player(["钢拳", "气力之心"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    from saintess_engine.gauge import bar_gain as _bg
    _bg(e, "shaken", 15, [])
    m, logs = calc_mult(p, e)
    check("val=15 命中门槛 → mult 1.2", abs(m - 1.2) < 1e-9, f"mult={m} logs={logs}")
    check("被动生效日志", any("气力之心" in str(x) or "被动生效" in str(x) for x in logs),
          f"logs={logs}")
    # 边界：14（差 1 点）不增伤
    e2 = mk_enemy()
    _bg(e2, "shaken", 14, [])
    m2, _ = calc_mult(p, e2)
    check("val=14 未达门槛 → mult 1.0", abs(m2 - 1.0) < 1e-9, f"mult={m2}")
    # 边界：条不存在（从未被推过）不增伤
    e3 = mk_enemy()
    m3, _ = calc_mult(p, e3)
    check("无条状态 → mult 1.0", abs(m3 - 1.0) < 1e-9, f"mult={m3}")


def test_3_broken_mult():
    print("【3. 破绽·极乘区段：破防态 → ×1.5】")
    from saintess_engine.gauge import bar_effect_key
    p = mk_player(["钢拳", "破绽·极"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    # 触发后免疫窗口内（immune_until = 当刻 + 1）
    e.setdefault("effects", {})[bar_effect_key("shaken")] = {
        "val": 0.0, "threshold": 67, "trigger_count": 1, "immune_until": 1.0, "_at": 0.0}
    m, logs = calc_mult(p, e)
    check("破防态 → mult 1.5", abs(m - 1.5) < 1e-9, f"mult={m} logs={logs}")
    # 反例：触发过但免疫窗口已过
    e2 = mk_enemy()
    e2.setdefault("effects", {})[bar_effect_key("shaken")] = {
        "val": 0.0, "threshold": 67, "trigger_count": 1, "immune_until": 0.0, "_at": 0.0}
    m2, _ = calc_mult(p, e2)
    check("免疫窗口结束 → mult 1.0", abs(m2 - 1.0) < 1e-9, f"mult={m2}")
    # 反例：有积蓄但从未触发（trigger_count=0）
    e3 = mk_enemy()
    e3.setdefault("effects", {})[bar_effect_key("shaken")] = {
        "val": 0.0, "threshold": 67, "trigger_count": 0, "immune_until": 1.0, "_at": 0.0}
    m3, _ = calc_mult(p, e3)
    check("未触发过 → mult 1.0", abs(m3 - 1.0) < 1e-9, f"mult={m3}")


def test_4_extend():
    print("【4. 破绽·极延长段：本次触发 → 免疫窗口 1 → 2】")
    p = mk_player(["钢拳", "破绽·极"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = new_battle(p, e)
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 50}}, logs)
    bs = bar_of(e)
    check("推条满阈值 → 触发（trigger_count=1）", bs.get("trigger_count") == 1, f"bs={bs}")
    check("延长后免疫窗口 = 3.0（配置 2 + extend 1）",
          abs(float(bs.get("immune_until", 0)) - 3.0) < 1e-9, f"bs={bs}")
    check("延长日志在触发之后", any("破防持续 +1" in str(x) for x in logs), f"logs={logs}")
    check("落地 mode=skip 未受影响",
          ((e.get("effects") or {}).get("bar_skip:shaken") or {}).get("mode") == "skip",
          f"eff={e.get('effects')}")
    # 对照：未学破绽·极 → 免疫窗口 = 2（配置基线，不延长）
    p2 = mk_player(["钢拳"])
    CMP.apply_class_mech(p2)
    e2 = mk_enemy()
    b2 = new_battle(p2, e2)
    logs2 = []
    fire(b2, "skill_hit", {"actor": p2, "target": e2, "info": {"shaken_gain": 50}}, logs2)
    check("对照组（无破绽·极）免疫窗口 = 2", 
          abs(float(bar_of(e2).get("immune_until", 0)) - 2.0) < 1e-9,
          f"bs={bar_of(e2)}")
    # 边界：未触发（只推 5 点）→ 不延长、无日志
    p3 = mk_player(["钢拳", "破绽·极"])
    CMP.apply_class_mech(p3)
    e3 = mk_enemy()
    b3 = new_battle(p3, e3)
    logs3 = []
    fire(b3, "skill_hit", {"actor": p3, "target": e3, "info": {"shaken_gain": 5}}, logs3)
    check("未触发不延长（val=5 / 无免疫窗口）",
          bar_of(e3).get("val") == 5
          and float(bar_of(e3).get("immune_until", 0) or 0) == 0.0,
          f"bs={bar_of(e3)}")
    check("未触发无延长日志", not any("破防持续" in str(x) for x in logs3), f"logs={logs3}")


def test_5_combined():
    print("【5. 三段叠加：破防态下气力之心 + 破绽·极 = ×1.8】")
    from saintess_engine.gauge import bar_effect_key
    p = mk_player(["钢拳", "气力之心", "破绽·极"])
    CMP.apply_class_mech(p)
    e = mk_enemy()
    e.setdefault("effects", {})[bar_effect_key("shaken")] = {
        "val": 15.0, "threshold": 67, "trigger_count": 1, "immune_until": 1.0, "_at": 0.0}
    m, _ = calc_mult(p, e)
    check("×1.2（气力之心）×1.5（破绽·极）= 1.8", abs(m - 1.8) < 1e-9, f"mult={m}")


def main():
    test_1_install()
    test_2_awareness()
    test_3_broken_mult()
    test_4_extend()
    test_5_combined()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
