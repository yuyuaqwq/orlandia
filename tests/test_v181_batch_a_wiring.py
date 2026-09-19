# -*- coding: utf-8 -*-
"""批 A 接线验收（2026-09-11）：三条「声明了没人读」的死字段真的生效了吗？

覆盖（任意一条变红 = 接线被改坏或退回死字段）：
  1. `debuff_scale`「每层承伤 +N%」→ landing.deal_damage 逐状态累加乘区
     （猎印 +8%/层 cap3、魂印 +6%/层、骨噬诅咒 +20%）——对称 stat_scale
  2. `period.dmg_type`「真伤 DOT」→ schedule DOT 结算**透传** dmg_kind
     （用 monkeypatch 抓实参，证明透传真的发生；并证明真伤跳过物免/魔免/格挡）
  3. `immune_dots` 异常免疫名单 → effects.act_apply 前置拦截
     （名单命中 = 不施加；未命中/无名单 = 照旧施加）
  4. **零变化回归**：无状态 / 无声明 / 无名单时，三条路径行为与接线前一致

跑法：python tests/test_v181_batch_a_wiring.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_batch_a.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine.battle.landing import deal_damage  # noqa: E402
from saintess_engine.battle.effects import apply_action  # noqa: E402
from saintess_engine.battle.schedule import _settle_time_effects  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_player():
    return make_actor(uid="p1", name="游侠", side="player", kind="player",
                      human_controlled=True, class_name="cls_you_xia", level=40,
                      hp=5000, max_hp=5000, mp=500, max_mp=500,
                      atk=100, matk=80, spd=20, crit=0.0,
                      equipment={}, skills=[], learned_skills=[],
                      **{"def": 40, "mdef": 30})


def mk_enemy(hp=100000):
    e = make_actor(uid="e1", name="木桩怪", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=10, matk=10, spd=10, crit=0.0, level=40,
                   **{"def": 10, "mdef": 10})
    e["effects"] = {}
    e["dodge"] = 0.0
    e["block"] = 0.0
    return e


def mk_battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


# ============================================================
# 1. debuff_scale：每层承伤 +N%
# ============================================================

def test_1_debuff_scale():
    print("【1. debuff_scale：每层承伤 +N%（landing 逐状态累加乘区）】")
    p = mk_player()
    e = mk_enemy()
    b = mk_battle(p, e)

    base = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("无状态：100 → 100（零变化）", base == 100, f"base={base}")

    e["effects"] = {"hunt_mark": {"stacks": 3}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("猎印 3 层：100 → 124（+8%/层 cap3）", d == 124, f"d={d}")

    e["effects"] = {"soul_mark": {"stacks": 3}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("魂印 3 层：100 → 118（+6%/层 cap3）", d == 118, f"d={d}")

    e["effects"] = {"curse": {"stacks": 1}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("骨噬诅咒 1 层：100 → 120（+20% cap1）", d == 120, f"d={d}")

    e["effects"] = {"hunt_mark": {"stacks": 3}, "curse": {"stacks": 1}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("两状态同挂：100 → 144（1+0.24+0.20）", d == 144, f"d={d}")

    # 半层不生效（stacks=0 的残留条目）
    e["effects"] = {"hunt_mark": {"stacks": 0}, "curse": {"stacks": 0}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("0 层残留条目：不算（100）", d == 100, f"d={d}")

    # 数据驱动：无 debuff_scale 声明的状态零影响（如 poison 只有 period）
    e["effects"] = {"poison": {"stacks": 5}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("无 debuff_scale 声明的状态（毒 5 层）：零影响（100）", d == 100, f"d={d}")

    # 声明来源只认表（EFFECT_RULES），条目自带同名字段不越权
    e["effects"] = {"poison": {"stacks": 5, "debuff_scale": {"dmg_taken": 0.5}}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("条目自带 debuff_scale 不生效（只认 EFFECT_RULES 表）：100", d == 100, f"d={d}")

    # 层数上限由数据侧 cap 决定（引擎不另设帽）：cap 外注入仍按实际 stacks 算
    e["effects"] = {"hunt_mark": {"stacks": 5}}
    d = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("超 cap 注入（5 层）按实际层数算：100 → 140", d == 140, f"d={d}")


# ============================================================
# 2. period.dmg_type → dmg_kind 透传
# ============================================================

def test_2_dmg_type_passthrough():
    print("【2. period.dmg_type：DOT 结算透传 dmg_kind（真伤语义成立）】")
    p = mk_player()
    e = mk_enemy()
    b = mk_battle(p, e)

    # 先证明「真伤 vs 非真伤」在 landing 里的差异
    e["phys_reduce"] = 0.4
    e["magic_reduce"] = 0.4
    hit_phys = deal_damage(b, p, e, 100, [], dmg_kind="phys")
    check("物免 40% + phys：100 → 60", hit_phys == 60, f"={hit_phys}")
    hit_true = deal_damage(b, p, e, 100, [], dmg_kind="true")
    check("物免 40% + true：100 → 100（真伤跳过）", hit_true == 100, f"={hit_true}")
    hit_none = deal_damage(b, p, e, 100, [], dmg_kind="")
    check("物免 40% + 空 kind：100 → 100（DOT 旧行为）", hit_none == 100, f"={hit_none}")

    # 透传是否真的发生：monkeypatch landing.deal_damage 抓 schedule 的实参
    import saintess_engine.battle.landing as L
    from saintess_engine import config as _cfg
    cap = {}
    orig = L.deal_damage

    def spy(battle, source, target, amount, logs, **kw):
        cap["kind"] = kw.get("dmg_kind", "<MISSING>")
        return orig(battle, source, target, amount, logs, **kw)

    L.deal_damage = spy
    try:
        e2 = mk_enemy()
        # 真伤 DOT 条目（动态 period 声明）
        e2["effects"] = {"burn": {"stacks": 1,
                                  "period": {"dir": "damage", "interval": 1.0,
                                             "pct_max_hp": 0.05, "dmg_type": "true"}}}
        b2 = mk_battle(p, e2)
        b2._now = 0.0
        _settle_time_effects(b2, [])          # 首次：登记下一跳
        b2._now = 1.0
        _settle_time_effects(b2, [])          # 到点：跳伤害
        check("带 dmg_type=true 的 DOT：透传 dmg_kind=\"true\"",
              cap.get("kind") == "true", f"kind={cap.get('kind')!r}")

        cap.clear()
        e3 = mk_enemy()
        e3["effects"] = {"burn": {"stacks": 1,
                                  "period": {"dir": "damage", "interval": 1.0,
                                             "pct_max_hp": 0.05}}}
        b3 = mk_battle(p, e3)
        b3._now = 0.0
        _settle_time_effects(b3, [])
        b3._now = 1.0
        _settle_time_effects(b3, [])
        check("不带 dmg_type 的 DOT：dmg_kind 为空串（零变化）",
              cap.get("kind") == "", f"kind={cap.get('kind')!r}")
    finally:
        L.deal_damage = orig

    # 数据侧声明存在（corros = 真伤轴）
    from content.mech.params import EFFECT_RULES
    _c = (EFFECT_RULES.get("corros") or {}).get("period") or {}
    check("数据侧 corros 仍声明 dmg_type=true（真伤轴）",
          _c.get("dmg_type") == "true", f"period={_c}")


# ============================================================
# 3. immune_dots：异常免疫名单
# ============================================================

def test_3_immune_dots():
    print("【3. immune_dots：DOT 类状态施加前置拦截】")
    p = mk_player()

    # 无名单 → 照旧施加（零变化）
    e = mk_enemy()
    b = mk_battle(p, e)
    apply_action(b, p, e, "apply",
                 {"key": "burn", "op": "add", "amount": 2, "on": "target"}, [])
    check("无 immune_dots：burn 正常加 2 层",
          int((e["effects"].get("burn") or {}).get("stacks", 0)) == 2,
          f"ef={e['effects'].get('burn')}")

    # 名单命中 → 不施加
    e2 = mk_enemy()
    e2["immune_dots"] = ["burn"]
    b2 = mk_battle(p, e2)
    logs = []
    apply_action(b2, p, e2, "apply",
                 {"key": "burn", "op": "add", "amount": 2, "on": "target"}, logs)
    check("immune_dots=[burn]：burn 未被施加",
          int((e2["effects"].get("burn") or {}).get("stacks", 0)) == 0,
          f"ef={e2['effects'].get('burn')}")
    check("拦截有日志提示", any("免疫" in str(x) for x in logs), f"logs={logs}")

    # 名单只免指定类型：免 burn 不免 poison
    logs = []
    apply_action(b2, p, e2, "apply",
                 {"key": "poison", "op": "add", "amount": 2, "on": "target"}, logs)
    check("名单只免指定类型：poison 正常加 2 层",
          int((e2["effects"].get("poison") or {}).get("stacks", 0)) == 2,
          f"ef={e2['effects'].get('poison')}")

    # 非 DOT 状态不受名单影响（period.dir != damage，控制型走 mode 分支）
    e3 = mk_enemy()
    e3["immune_dots"] = ["burn", "poison", "bleed", "corros", "freeze"]
    b3 = mk_battle(p, e3)
    apply_action(b3, p, e3, "apply",
                 {"key": "freeze", "mode": "skip", "turns": 1, "on": "target"}, [])
    check("控制型（freeze, mode=skip）不受 immune_dots 影响",
          (e3["effects"].get("freeze") or {}).get("mode") == "skip",
          f"ef={e3['effects'].get('freeze')}")

    # 名单为空列表 = 不免（与无键等价）
    e4 = mk_enemy()
    e4["immune_dots"] = []
    b4 = mk_battle(p, e4)
    apply_action(b4, p, e4, "apply",
                 {"key": "corros", "op": "add", "amount": 1, "on": "target"}, [])
    check("immune_dots=[]（空名单）：corros 正常施加",
          int((e4["effects"].get("corros") or {}).get("stacks", 0)) == 1,
          f"ef={e4['effects'].get('corros')}")


# ============================================================
# 4. 零变化回归
# ============================================================

def test_4_zero_change():
    print("【4. 零变化回归：缺省数据时三条路径与接线前一致】")
    p = mk_player()
    e = mk_enemy()
    b = mk_battle(p, e)
    # 木桩（无 effects / 无 immune_dots / 无 dmg_type 声明）→ 伤害逐字等于传入值
    for amount in (1, 7, 100, 999):
        got = deal_damage(b, p, e, amount, [], dmg_kind="")
        check(f"无任何状态声明：{amount} → {amount}", got == amount, f"got={got}")
    # 数据侧三处声明仍在（防被误删）
    from content.mech.params import EFFECT_RULES
    check("hunt_mark 仍声明 debuff_scale 0.08",
          ((EFFECT_RULES.get("hunt_mark") or {}).get("debuff_scale") or {}).get("dmg_taken") == 0.08,
          f"={EFFECT_RULES.get('hunt_mark')}")
    check("soul_mark 仍声明 debuff_scale 0.06",
          ((EFFECT_RULES.get("soul_mark") or {}).get("debuff_scale") or {}).get("dmg_taken") == 0.06,
          f"={EFFECT_RULES.get('soul_mark')}")
    check("curse 仍声明 debuff_scale 0.20",
          ((EFFECT_RULES.get("curse") or {}).get("debuff_scale") or {}).get("dmg_taken") == 0.20,
          f"={EFFECT_RULES.get('curse')}")


def main():
    test_1_debuff_scale()
    test_2_dmg_type_passthrough()
    test_3_immune_dots()
    test_4_zero_change()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
