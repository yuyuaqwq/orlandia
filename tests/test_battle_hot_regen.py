# -*- coding: utf-8 -*-
"""V 系列统一：hot 正向持续恢复（effects["regen_hot"] + period 声明，schedule 周期结算）。

V 系列后 hot 不再用独立 actor["hot"] 容器——食物/料理挂 effects["regen_hot"] 条目：
  {"stacks": 1, "period": {"dir": "heal", "interval": 1.0, "heal_pct": x,
                            "mana_pct": y, "turns": N}}
schedule 统一周期段按 interval 绝对时刻循环补跳（damage/heal/mana 方向分流），
turns 次后自动清层。对齐旧引擎 v179 P3 每秒墙钟 tick 语义（N 刻 = N 秒）。

覆盖：
- 挂 hot 后首跳延迟 1s（dot_next 登记）
- 到点回血/回蓝（百分比×max，clamp 上限）
- 跨多刻补跳多次（now 一次性推远 → 循环补跳）
- turns 跳满自动清层
- 同刻重复 settle 不重复跳

跑法：python tests/test_battle_hot_regen.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_hot_regen.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import C            # noqa: E402
from content.panel import player_final_stats
from ext_combat import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_player(cls="战士", level=10, hp_ratio=0.5, mp_ratio=1.0):
    st = player_final_stats(cls, level, {}, 0, {}, 1)
    p = make_actor(uid="p_q1", name="测试勇者", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=level,
                   hp=int(st["max_hp"] * hp_ratio),
                   max_hp=int(st["max_hp"]),
                   mp=int(st["max_mp"] * mp_ratio), max_mp=int(st["max_mp"]),
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=1, class_tier=0, attributes={},
                   **{k: st[k] for k in ("atk", "matk", "def", "mdef", "spd", "crit") if k in st})
    return p


def mk_monster(hp=100000, atk=1, spd=1):
    return make_actor(uid="e_0", name="木桩", side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=atk, **{"def": 0},
                      matk=0, mdef=0, spd=spd, crit=0.0, level=1)


def _mk_battle(p, m=None):
    return BT_NEW(btype="monster", sides={"player": [p], "enemy": [m or mk_monster()]})


def _hang_hot(p, heal=0.1, mana=0.0, turns=3):
    """挂 regen_hot 条目（V 系列形态：period 声明 + 动态数值随条目）。"""
    p.setdefault("effects", {})["regen_hot"] = {
        "stacks": 1,
        "period": {"dir": "heal", "interval": 1.0,
                   "heal_pct": heal, "mana_pct": mana,
                   "turns": turns},
    }


def test_hot_first_jump_delay():
    """首跳延迟：挂 hot 后同刻不跳，dot_next 登记 now+1。"""
    print("【V-HOT.1 首跳延迟：挂 hot 同刻不跳，登记 now+interval】")
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    p = mk_player(hp_ratio=0.5)
    b = _mk_battle(p)
    _hang_hot(p)
    hp0 = p["hp"]
    b._now = 0.0
    _ste(b, [])
    check("同刻不跳（首跳延迟）", p["hp"] == hp0, f"hp {hp0} → {p['hp']}")
    check("dot_next 登记 1.0", abs(float(p["dot_next"].get("regen_hot", 0)) - 1.0) < 1e-9,
          f"dot_next={p.get('dot_next')}")


def test_hot_heal_and_mana():
    """到点回血回蓝（百分比×max，clamp 上限）。"""
    print("【V-HOT.2 到点跳：回血 + 回蓝 + clamp】")
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    p = mk_player(hp_ratio=0.5, mp_ratio=0.5)
    mx_hp = p["max_hp"]
    mx_mp = p["max_mp"]
    b = _mk_battle(p)
    _hang_hot(p, heal=0.1, mana=0.1, turns=2)
    hp0, mp0 = p["hp"], p["mp"]
    logs = []
    b._now = 0.0
    _ste(b, [])  # 登记
    b._now = 1.0
    _ste(b, logs)
    gain_hp = int(mx_hp * 0.1)
    gain_mp = int(mx_mp * 0.1)
    check("回血 10%max", p["hp"] == hp0 + gain_hp, f"{hp0} → {p['hp']} (期望+{gain_hp})")
    check("回蓝 10%max", p["mp"] == mp0 + gain_mp, f"{mp0} → {p['mp']} (期望+{gain_mp})")
    check("有恢复日志", any("持续恢复" in x for x in logs), f"logs={logs}")


def test_hot_catchup_multijump():
    """跨多刻补跳：now 推远 → while 循环补跳满 turns 次后自动清层。"""
    print("【V-HOT.3 跨多刻补跳 + turns 跳满清层】")
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    p = mk_player(hp_ratio=0.1)
    mx_hp = p["max_hp"]
    b = _mk_battle(p)
    _hang_hot(p, heal=0.1, mana=0.0, turns=3)
    hp0 = p["hp"]
    b._now = 0.0
    _ste(b, [])  # 登记
    b._now = 5.0  # 推远 5s → 应跳 3 次（t=1,2,3），第 3 次后 turns 满自动清层
    _ste(b, [])
    check("turns 跳满自动清层", "regen_hot" not in (p.get("effects") or {}),
          f"effects={p.get('effects')}")
    expect = hp0 + int(mx_hp * 0.1) * 3
    check("血量 = 3 次总量", p["hp"] == expect, f"{p['hp']} vs {expect}")


def test_hot_clamp_max():
    """clamp：恢复不超过 max_hp/max_mp。"""
    print("【V-HOT.4 clamp：恢复封顶 max】")
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    p = mk_player(hp_ratio=0.95)
    b = _mk_battle(p)
    _hang_hot(p, heal=0.1, mana=0.0, turns=3)
    b._now = 0.0
    _ste(b, [])  # 登记
    b._now = 1.0
    _ste(b, [])
    b._now = 2.0
    _ste(b, [])
    b._now = 3.0
    _ste(b, [])
    check("hp 封顶 max_hp", p["hp"] == p["max_hp"], f"{p['hp']}/{p['max_hp']}")


def test_hot_no_repeat_same_now():
    """同刻重复 settle 不重复跳（绝对时刻推进语义）。"""
    print("【V-HOT.5 同刻重复 settle 不重复跳】")
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    p = mk_player(hp_ratio=0.5)
    b = _mk_battle(p)
    _hang_hot(p, heal=0.1, mana=0.0, turns=3)
    b._now = 0.0
    _ste(b, [])  # 登记
    hp0 = p["hp"]
    b._now = 1.0
    _ste(b, [])
    hp1 = p["hp"]
    check("now=1 跳 1 次", hp1 > hp0)
    _ste(b, [])  # 同刻再 settle
    check("同刻不重复跳", p["hp"] == hp1, f"{hp1} → {p['hp']}")


def main():
    print("=== V-HOT saintess_engine hot 持续恢复（effects period 统一）测试 ===")
    test_hot_first_jump_delay()
    test_hot_heal_and_mana()
    test_hot_catchup_multijump()
    test_hot_clamp_max()
    test_hot_no_repeat_same_now()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
