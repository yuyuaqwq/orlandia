# -*- coding: utf-8 -*-
"""副本通关奖励数值门禁 test_numeric_instance_reward —— v173 问题C（2026-09-03）。

覆盖（公式：economy_lib.instance_reward，模型锚 = monster_gold/monster_exp × 系数）：
  1. economy_lib.instance_reward 函数可用：gold/exp 与手算公式一致
  2. 22 本 data/instances.py gold/exp 全部落在模型带内（±12% 容差，四舍五入误差）
  3. 通关奖励为正值、跨级单调不怪（lv 升 → gold/exp 不降，同 lv 同位）
  4. 通关金/经验相对野外同级 Boss 怪金/怪经的比例在锚定带（gold 25-35%、exp 2.5-3.0×）
     —— 防"退回手填脱模型"式回归
运行：python tests/test_numeric_instance_reward.py（exit=0 全绿；由 run_numeric_tests.py 自动纳入门禁）
"""
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))          # tests/
_PLUGIN_DIR = os.path.dirname(_SCRIPT_DIR)                        # dragonfall/
_SCRIPTS_DIR = os.path.dirname(_SCRIPT_DIR)   # tests/（economy_lib 随迁落点）
for _p in (_SCRIPTS_DIR, _PLUGIN_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("GWEN_GAME_DB", os.path.join(_SCRIPT_DIR, "test_game_data.db"))

from economy_lib.env import setup_env  # noqa: E402,F401
from economy_lib.core import instance_reward, INSTANCE_GOLD_MULT, INSTANCE_EXP_MULT  # noqa: E402
from content.catalog_space import INSTANCES  # noqa: E402
from content import stats as _stats  # noqa: E402
monster_gold, monster_exp, exp_to_next = _stats.monster_gold, _stats.monster_exp, _stats.exp_to_next

passed, failed = 0, 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed")


print("【1. instance_reward 函数公式】")
for lv in (15, 22, 35, 52, 74, 90, 94):
    r = instance_reward(lv)
    expect = {
        "gold": int(monster_gold(lv, "boss") * INSTANCE_GOLD_MULT),
        "exp": int(monster_exp(lv, "boss") * INSTANCE_EXP_MULT),
    }
    check(f"lv{lv} gold 公式一致", r["gold"] == expect["gold"], f"{r} vs {expect}")
    check(f"lv{lv} exp 公式一致", r["exp"] == expect["exp"], f"{r} vs {expect}")

print("【2. 22 本 gold/exp 落模型带（±12% 容差）】")
insts = sorted(INSTANCES.items(), key=lambda kv: kv[1].get("lv", 0))
by_lv = {}
for iid, inst in insts:
    lv = int(inst.get("lv", 0))
    g, e = int(inst.get("gold", 0)), int(inst.get("exp", 0))
    m = instance_reward(lv)
    tol_g = max(3, int(m["gold"] * 0.12))
    tol_e = max(5, int(m["exp"] * 0.12))
    ok_g = abs(g - m["gold"]) <= tol_g
    ok_e = abs(e - m["exp"]) <= tol_e
    check(f"{iid} gold {g}∈带[{m['gold']}-{tol_g}, {m['gold']}+{tol_g}]",
          ok_g, f"model={m['gold']}")
    check(f"{iid} exp {e}∈带[{m['exp']}-{tol_e}, {m['exp']}+{tol_e}]",
          ok_e, f"model={m['exp']}")
    by_lv.setdefault(lv, []).append((iid, g, e))
    # 正值
    check(f"{iid} 奖励为正", g > 0 and e > 0, f"g={g} e={e}")

print("【3. 跨级单调 & 同级同位】")
prev = None
for lv in sorted(by_lv):
    row = by_lv[lv]
    g0 = max(x[1] for x in row)
    if prev is not None:
        check(f"Lv{lv} 金≥Lv{prev}（单调不降）", g0 >= prev["g"], f"{g0} vs {prev['g']}")
        check(f"Lv{lv} 经≥Lv{prev}（单调不降）", row[0][2] >= prev["e"], f"{row[0][2]} vs {prev['e']}")
    prev = {"g": g0, "e": row[0][2]}
if len(by_lv.get(90, [])) > 1:
    gs = {x[1] for x in by_lv[90]}
    es = {x[2] for x in by_lv[90]}
    check("Lv90 四本同位奖励一致", len(gs) == 1 and len(es) == 1, f"g={gs} e={es}")

print("【4. 锚定带防脱模型】")
for iid, inst in insts:
    lv = int(inst.get("lv", 0))
    g, e = int(inst.get("gold", 0)), int(inst.get("exp", 0))
    bg, be = monster_gold(lv, "boss"), monster_exp(lv, "boss")
    gr = g / max(bg, 1)
    er = e / max(be, 1)
    check(f"{iid} 金占比 {gr:.2f}∈[0.25,0.35]", 0.25 <= gr <= 0.35, f"{gr:.3f}")
    check(f"{iid} 经倍数 {er:.2f}∈[2.5,3.0]", 2.5 <= er <= 3.0, f"{er:.3f}")
    # 升级占比（只作为观感记录：4-30% 区间；40+ 高级本 ≥2%）
    pct = e / max(exp_to_next(lv), 1)
    check(f"{iid} exp/升级 {pct:.1%}∈[2%,30%]", 0.02 <= pct <= 0.30, f"{pct:.3f}")

print()
print(f"通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
