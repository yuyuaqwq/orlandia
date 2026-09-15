# -*- coding: utf-8 -*-
"""N02 CTB 行动频率门禁 —— 速度差 → 行动频率比（**防站桩回归**）。

口径（纯观测，不自己算频率）
--------------------------
双方 actor 都设 `human_controlled=True`（都不自动出手）→ 由引擎 `Battle.advance()`
决定"下一个该行动的人"，我们显式让它出手一次并计数。于是
`ratio = 怪出手次数 / 玩家出手次数`（窗口 = 玩家出手 20 次）是**引擎实测**的结果。

| 组 | ratio（怪/玩家） | 玩家每行动几次怪动 1 次 |
|---|---|---|
| 刺客 spd72 vs 怪 spd31 | 0.600 | 1.67 |
| spd41 vs 怪 spd31 | 0.850 | 1.18 |
| 同级 spd31 vs spd31 | 0.950 | 1.05 |

防什么回归
----------
**站桩**：v130.10 之前的相对时钟模型下，速度差被放大到 15:1（20 回合怪只动 3 次），
慢怪等于站着不动。本次实测速度差 2.32 倍 → 频率比 1.67 倍（**次线性**，无放大）；
若引擎退回旧行为，`ratio(72v31)` 会掉到 ~0.07 → 硬闸门（≥0.35）立刻红。

顺带锁：**同级同频**（ratio ≈ 1.0）—— 防"同速度不同出手"的调度偏差。

跑法：python tests/test_numeric_ctb_freq.py（约 1s）
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import numeric_sim as NS  # noqa: E402  (触发引擎路径装配)
from saintess_engine import Battle as B2, make_actor  # noqa: E402

WINDOW = 20                    # 玩家出手多少次后停止计数
RATIO_TOL = 0.005
# (组名, 玩家spd, 怪spd, 基线 ratio)
GROUPS = [
    ("spd72 vs spd31", 72, 31, 0.600),
    ("spd41 vs spd31", 41, 31, 0.850),
    ("同级 spd31 vs spd31", 31, 31, 0.950),
]

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def count_actions(p_spd: int, e_spd: int, window: int = WINDOW):
    """跑一段战斗，返回 (玩家出手数, 怪出手数, 总刻数)。双方高血低攻 → 不会分出胜负。"""
    p = make_actor(uid="p1", name="玩家", side="player", kind="player", human_controlled=True,
                   hp=1000000, max_hp=1000000, atk=1, matk=1, spd=p_spd, level=11,
                   **{"def": 0, "mdef": 0})
    e = make_actor(uid="e1", name="怪", side="enemy", kind="monster", human_controlled=True,
                   hp=1000000, max_hp=1000000, atk=1, matk=1, spd=e_spd, level=11,
                   **{"def": 0, "mdef": 0})
    b = B2("monster", sides={"player": [p], "enemy": [e]})
    counts = {"p1": 0, "e1": 0}
    guard = 0
    while b.result is None and counts["p1"] < window and guard < 5000:
        guard += 1
        who = b.advance([])                  # 引擎决定下一个该行动的人控 actor
        if who is None:
            break
        b.human_act("defend", None, who)      # 让它出手一次（推 ct）
        counts[str(who.get("uid"))] += 1
    return counts["p1"], counts["e1"], round(b._now, 2)


def main():
    t0 = time.time()
    print(f"【N02 CTB 行动频率：玩家出手 {WINDOW} 次内怪出手几次】")
    got = {}
    for label, ps, es, exp in GROUPS:
        p_acts, e_acts, now = count_actions(ps, es)
        ratio = e_acts / max(1, p_acts)
        got[label] = ratio
        print(f"  {label}: 玩家 {p_acts} / 怪 {e_acts} → ratio={ratio:.3f} "
              f"（怪动 1 次需玩家动 {1 / ratio:.2f} 次）now={now}")
        check(f"{label} 窗口完整（玩家出手 {WINDOW} 次）", p_acts == WINDOW, f"got={p_acts}")
        check(f"{label} ratio ≈ 基线 {exp:.3f}", abs(ratio - exp) <= RATIO_TOL,
              f"got={ratio:.3f}")

    print("\n【硬闸门】")
    r_big = got["spd72 vs spd31"]
    check(f"最大速度差组无放大（ratio ≥ 0.35，防慢怪站桩）", r_big >= 0.35, f"got={r_big:.3f}")
    check(f"最大速度差组玩家更快（ratio ≤ 0.75）", r_big <= 0.75, f"got={r_big:.3f}")
    check("频率比随速度差单调递减（同级 > 41v31 > 72v31）",
          got["同级 spd31 vs spd31"] > got["spd41 vs spd31"] > got["spd72 vs spd31"],
          f"{got['同级 spd31 vs spd31']:.3f} / {got['spd41 vs spd31']:.3f} / {r_big:.3f}")
    r_same = got["同级 spd31 vs spd31"]
    check("同级同频（0.85 ≤ ratio ≤ 1.15）", 0.85 <= r_same <= 1.15, f"got={r_same:.3f}")

    print(f"\n===== 结果：通过 {passed} / {passed + failed}（耗时 {time.time() - t0:.1f}s）=====")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
