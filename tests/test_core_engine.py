# -*- coding: utf-8 -*-
"""core 层 · 数值引擎：经验曲线 / 怪物数值

验证 stats.py 的 exp_to_next / monster_exp / monster_gold / monster_stats 单调性与结构。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C  # noqa: F401  (设置 sys.path)
from content import stats as core_stats

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ %s" % name)
    else:
        failed += 1
        print("  ❌ %s %s" % (name, detail))


def main():
    print("【core·数值引擎：经验曲线】")
    check("exp_to_next(1) 有值", core_stats.exp_to_next(1) > 0, str(core_stats.exp_to_next(1)))
    check("exp_to_next 递增", core_stats.exp_to_next(10) > core_stats.exp_to_next(5),
          "%s→%s" % (core_stats.exp_to_next(5), core_stats.exp_to_next(10)))
    check("exp_to_next 高等级不归零", core_stats.exp_to_next(50) > 0, str(core_stats.exp_to_next(50)))

    print("【core·数值引擎：怪物数值】")
    check("monster_exp 递增", core_stats.monster_exp(10, "dps") > core_stats.monster_exp(1, "dps"))
    check("monster_gold 递增", core_stats.monster_gold(10, "dps") > core_stats.monster_gold(1, "dps"))
    ms = core_stats.monster_stats(5, "dps")
    check("monster_stats 含 hp/atk", "hp" in ms and "atk" in ms, str(ms)[:80])
    check("monster_stats 数值为正", ms.get("hp", 0) > 0 and ms.get("atk", 0) > 0, str(ms)[:80])

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
