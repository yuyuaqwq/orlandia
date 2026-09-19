# -*- coding: utf-8 -*-
"""数值门禁：挂敌身条（破绽）时间制 + 容器安全（v181 破绽改造）。

防退化基线（任意一条变红 = 机制被改坏）：
  1. 衰减口径：每刻 −1.7 连续结算（小数累计，不是 int 截断的 −1/行动）
  2. 推进节奏：连招三连（+15/次）约 4.5 次出手触发一次（v153 §六 验算）
  3. 阈值序列：50 → 67 → 90 → 121 → 125（×1.35，封顶 ×2.5）
  4. 条上限容得下封顶阈值（max ≥ threshold_base × threshold_cap）
  5. 免疫窗口：触发后 2 刻内不再积蓄；到期即可再触发
  6. 自锁防护：触发当帧注入 = 0
  7. 容器安全：条键不与 EFFECT_RULES 撞键；条目不带 expire/period/stat/mode/stacks
  8. 容器位置：条状态存 effects["bar:*"]，不新建 buffs 死容器

跑法：python tests/test_numeric_bar_decay.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_numeric_bar.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402  ★ P5C-REPOINT：宿主装配壳已删
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine.battle.effect_triggers import fire  # noqa: E402
from content.mech import class_mech as CMP  # noqa: E402  ★ P5C-REPOINT：直取包内真源
from saintess_engine.gauge import (bar_def, bar_effect_key, bar_gain, bar_settle,# noqa: E402
                                   bar_state, _state_prefix)
from content.catalog_rules import ENEMY_BAR_CFG  # noqa: E402  ★ P5C-REPOINT：真源 = 包内聚合层（同值，域 `rules/game_config.json` 的 battle_config 组）
from saintess_engine.battle.state_effects import all_state_effects  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_player(learned=("钢拳",)):
    return make_actor(uid="p1", name="拳师", side="player", kind="player",
                      human_controlled=True, class_name="cls_wu_seng", level=20,
                      hp=2000, max_hp=2000, mp=200, max_mp=200,
                      atk=100, matk=80, spd=15, crit=0.0,
                      equipment={}, skills=[], learned_skills=list(learned),
                      **{"def": 40, "mdef": 30})


def mk_enemy(hp=99999):
    e = make_actor(uid="e1", name="木桩怪", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0, level=20,
                   **{"def": 10, "mdef": 10})
    e["effects"] = {}
    return e


def mk_battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def bar_of(e):
    return (e.get("effects") or {}).get(bar_effect_key("shaken")) or {}


def test_1_decay_rate():
    print("【1. 衰减口径：每刻 −1.7 连续结算（小数累计）】")
    bd = bar_def("shaken")
    check("配置 decay_per_turn = 1.7", abs(float(bd.get("decay_per_turn", 0)) - 1.7) < 1e-9,
          f"bd={bd.get('decay_per_turn')}")
    e = mk_enemy()
    e["effects"] = {}
    bar_gain(e, "shaken", 30, [], now=0.0)
    bar_settle(e, "shaken", 2.0)
    v = float(bar_of(e).get("val", -1))
    check("2 刻后衰减 3.4（30 → 26.6，非 28）", abs(v - 26.6) < 1e-6, f"val={v}")
    bar_settle(e, "shaken", 2.2)
    v2 = float(bar_of(e).get("val", -1))
    check("每刻步进 = 1.7（不是 int 截断的 1）", abs((v - v2) - 0.34) < 1e-6, f"Δ={v - v2}")


def test_2_pace():
    print("【2. 推进节奏：连招三连（+15/次）× 2.2 刻/次 ≈ 4.5 次出手触发】")
    p = mk_player()
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = mk_battle(p, e)
    casts = 0
    while casts < 20:
        casts += 1
        fire(b, "skill_hit", {"actor": p, "target": e,
                              "info": {"shaken_gain": 15, "hits": 1}}, [])
        if bar_of(e).get("trigger_count", 0) > 0:
            break
        # 一次循环 2.2 刻（v153 §六 拳师循环）→ 时钟推进结算衰减
        dt = 2.2
        b._now = float(b._now) + dt
        fire(b, "time_advance", {"dt": dt, "now": b._now}, [])
    check(f"首触发 ≈ 4.5 次出手（实测 {casts} 次）", 4 <= casts <= 5, f"casts={casts}")
    check("触发时 val 清零 + 计数 1", float(bar_of(e).get("val", -1)) == 0.0
          and bar_of(e).get("trigger_count") == 1, f"bs={bar_of(e)}")


def test_3_threshold_sequence():
    print("【3. 阈值序列：50 → 67 → 90 → 121 → 125（封顶 ×2.5）】")
    bd = bar_def("shaken")
    base = float(bd.get("threshold_base", 0))
    inc = float(bd.get("threshold_inc", 0))
    cap = float(bd.get("threshold_cap", 0))
    seq = [int(base)]
    thr = int(base)
    from math import floor
    for _ in range(4):
        thr = int(min(floor(base * cap), floor(thr * inc)))
        seq.append(thr)
    check("序列 = [50, 67, 90, 121, 125]", seq == [50, 67, 90, 121, 125], f"seq={seq}")
    # 实跑对照（真实 API 走一遍，防公式漂移）
    p = mk_player()
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = mk_battle(p, e)
    got = []
    now = 0.0
    for i in range(4):
        th = int(bar_of(e).get("threshold", 50) or 50)
        got.append(th)
        bar_gain(e, "shaken", th + 1, [], now=now)
        fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 1}}, [])
        now += 3.0
    check("实跑阈值序列与公式一致", got == [50, 67, 90, 121], f"got={got}")


def test_4_max_holds_cap():
    print("【4. 条上限容得下封顶阈值（原 max 50 的第二次触发死锁已修）】")
    bd = bar_def("shaken")
    need = float(bd.get("threshold_base", 0)) * float(bd.get("threshold_cap", 0))
    mx = float(bd.get("max", 0))
    check(f"max({int(mx)}) ≥ threshold_base × threshold_cap({int(need)})", mx + 1e-9 >= need,
          f"max={mx} need={need}")


def test_5_immune_window():
    print("【5. 免疫窗口：触发后 2 刻内不再积蓄；到期可再触发】")
    bd = bar_def("shaken")
    check("配置 immune_secs = 2.0（v153 §六）", abs(float(bd.get("immune_secs", 0)) - 2.0) < 1e-9,
          f"bd={bd.get('immune_secs')}")
    p = mk_player()
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = mk_battle(p, e)
    bar_gain(e, "shaken", 50, [], now=0.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 1}}, [])
    check("触发后免疫截止 = 当刻 + 2", abs(float(bar_of(e).get("immune_until", -1)) - 2.0) < 1e-9,
          f"bs={bar_of(e)}")
    bar_gain(e, "shaken", 20, [], now=1.0)
    check("免疫期内注入忽略（val 仍 0）", float(bar_of(e).get("val", -1)) == 0.0, f"bs={bar_of(e)}")
    bar_gain(e, "shaken", 20, [], now=2.5)
    check("免疫到期后注入生效（val=20）", float(bar_of(e).get("val", -1)) == 20.0, f"bs={bar_of(e)}")


def test_6_no_inject_on_trigger():
    print("【6. 自锁防护：触发当帧注入 = 0】")
    p = mk_player()
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = mk_battle(p, e)
    bar_gain(e, "shaken", 50, [], now=0.0)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 15}}, [])
    check("触发当帧（now=0）注入被吞（val=0 而非 15）",
          float(bar_of(e).get("val", -1)) == 0.0 and bar_of(e).get("trigger_count") == 1,
          f"bs={bar_of(e)}")


def test_7_container_safety():
    print("【7. 容器安全：不与 EFFECT_RULES 撞键 / 条目不带容器自动化字段】")
    rules = all_state_effects()
    pfx = _state_prefix()
    for k in ENEMY_BAR_CFG:
        check(f"条键 {pfx}{k} 不在 EFFECT_RULES（防被折算/清理/周期跳误伤）",
              (pfx + k) not in rules, f"keys={pfx}{k}")
    p = mk_player()
    CMP.apply_class_mech(p)
    e = mk_enemy()
    b = mk_battle(p, e)
    fire(b, "skill_hit", {"actor": p, "target": e, "info": {"shaken_gain": 10}}, [])
    entry = bar_of(e)
    check("条条目字段集受控", set(entry.keys()) <= {"val", "threshold", "trigger_count",
                                                 "_at", "immune_until", "_no_inject_at"},
          f"keys={sorted(entry.keys())}")
    for bad in ("expire", "period", "mode", "stacks", "stat", "mult"):
        check(f"条条目不带 {bad}（避开容器自动化）", bad not in entry, f"entry={entry}")
    # 面板折算不受污染：有破绽条的单位 spd/atk 不因条变化
    from saintess_engine.battle.stats import actor_stats
    s1 = dict(actor_stats(b, e))
    bar_gain(e, "shaken", 40, [], now=b._now)
    s2 = dict(actor_stats(b, e))
    check("条不影响敌方面板（stats 不读条容器）",
          s1.get("atk") == s2.get("atk") and s1.get("spd") == s2.get("spd"),
          f"{s1.get('atk')}/{s1.get('spd')} vs {s2.get('atk')}/{s2.get('spd')}")


def test_8_container_location():
    print("【8. 容器位置：条写进 effects[bar:*]，不新建 buffs 死容器】")
    e = mk_enemy()
    e["effects"] = {}
    e.pop("buffs", None)
    bar_gain(e, "shaken", 10, [], now=0.0)
    check("条在 effects[bar:shaken]", isinstance(bar_of(e), dict) and bar_of(e).get("val") == 10,
          f"effects={list((e.get('effects') or {}).keys())}")
    check("未创建 buffs 键（V 系列已删容器）", "buffs" not in e, f"keys={sorted(e.keys())[:8]}")


def main():
    test_1_decay_rate()
    test_2_pace()
    test_3_threshold_sequence()
    test_4_max_holds_cap()
    test_5_immune_window()
    test_6_no_inject_on_trigger()
    test_7_container_safety()
    test_8_container_location()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
