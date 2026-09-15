# -*- coding: utf-8 -*-
"""N01 跨级胜率矩阵门禁 —— 6 基础职业 × 4 档 dps 怪（同级 / +5 / -5 / +11），seeds=8 纯普攻。

列 |
  职业    同级(11)   +5(16)   -5(6)    +11(22)
  战士     3/8        0/8      8/8      0/8
  法师     3/8        0/8      8/8      0/8
  牧师     1/8        0/8      8/8      0/8
  刺客     0/8        0/8      8/8      0/8
  游侠     0/8        0/8      8/8      0/8
  拳师     4/8        0/8      8/8      0/8

锁定什么
--------
11 级标准 39 点加点（`numeric_sim.STD_ATTR`）、**纯普攻**（use_skill=False）、固定种子
0..7 下的「胜场/8 + 平均回合」24 格快照 + 三条方向性约束。

防什么回归
----------
1. **平衡快照漂移** —— 任何数值改动都让对应格子变红，必须显式更新基线（不允许静默改数值）
2. **等级差方向倒挂** —— 低 5 级怪该赢、高 5/11 级怪该败；胜率随等级差**单调递减**
3. **极端失衡** —— -5 档 <7/8（连低 5 级都打不过）；+11 档 >1/8（跨 11 级能赢 = 碾压）

⚠️ 本表是**当前口径的快照**，不是设计目标：+5 档全败 / 同级偏难是 v169.3 起怪物攻击
上调后的现状（纯普攻口径；用技能是另一回事）。调整数值请按 `docs/NUMERIC_TEST.md`
§基线更新流程 —— 先跑一遍看实测、确认与设计意图一致、再更新本表。

跑法：python tests/test_numeric_battle_matrix.py（约 1s；`run_numeric_tests.py --fast` 即跑它）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numeric_sim as NS  # noqa: E402

CLASSES = ["战士", "法师", "牧师", "刺客", "游侠", "拳师"]
TIERS = [("同级", 11), ("+5", 16), ("-5", 6), ("+11", 22)]
SEEDS = 8
ROUND_TOL = 0.02          # avg_round 浮点容差（固定种子下确定，留舍入余量）

# 实测基线（2026-09-12；numeric_sim 迁移到新引擎签名 + 装配与生产同源后的首轮）
MATRIX = {
    "战士": {"同级": (3, 9.62), "+5": (0, 5.88), "-5": (8, 4.25), "+11": (0, 3.62)},
    "法师": {"同级": (3, 5.50), "+5": (0, 3.50), "-5": (8, 3.50), "+11": (0, 2.12)},
    "牧师": {"同级": (1, 5.75), "+5": (0, 3.50), "-5": (8, 4.00), "+11": (0, 3.00)},
    "刺客": {"同级": (0, 6.62), "+5": (0, 4.12), "-5": (8, 4.38), "+11": (0, 3.12)},
    "游侠": {"同级": (0, 7.12), "+5": (0, 3.75), "-5": (8, 5.75), "+11": (0, 3.88)},
    "拳师": {"同级": (4, 9.12), "+5": (0, 5.62), "-5": (8, 4.12), "+11": (0, 3.38)},
}

# 方向性约束（防失衡的硬闸门，与快照独立——快照被更新也要满足）
MIN_WIN_RATE = {"-5": 7}   # 低 5 级怪：至少 7/8（打不过低 5 级 = 成长无感）
MAX_WIN_RATE = {"+11": 1}  # 跨 11 级怪：至多 1/8（能赢 = 碾压失衡）

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def main():
    t0 = time.time()
    print("【N01 跨级胜率矩阵：11 级标准 39 点 × dps 怪 × seeds=8 纯普攻】")
    print("  职业   " + "".join(f"{lb:>12s}" for lb, _ in TIERS))
    got = {}
    for cls in CLASSES:
        row = {}
        for label, mlv in TIERS:
            wins, avg = NS.class_battle_matrix(cls, 11, NS.STD_ATTR[cls], {}, "dps", mlv,
                                               seeds=SEEDS)
            row[label] = (wins, avg)
        got[cls] = row
        print(f"  {cls}   " + "".join(
            f"{row[lb][0]:>4d}/8 {row[lb][1]:>5.2f}" for lb, _ in TIERS))

    print("\n【快照：24 格逐格锁定】")
    for cls in CLASSES:
        for label, _mlv in TIERS:
            exp_w, exp_r = MATRIX[cls][label]
            w, r = got[cls][label]
            check(f"{cls} {label} 胜场 == 基线 {exp_w}/8", w == exp_w, f"got={w}/8")
            check(f"{cls} {label} 平均回合 ≈ {exp_r}", abs(r - exp_r) <= ROUND_TOL,
                  f"got={r} exp={exp_r}")

    print("\n【硬闸门：等级差方向 + 极端失衡】")
    for cls in CLASSES:
        row = got[cls]
        lo5, same, up5, up11 = row["-5"][0], row["同级"][0], row["+5"][0], row["+11"][0]
        check(f"{cls} 胜率随等级差单调递减（-5 ≥ 同级 ≥ +5 ≥ +11）",
              lo5 >= same >= up5 >= up11, f"-5={lo5} 同级={same} +5={up5} +11={up11}")
        check(f"{cls} 低 5 级怪可碾压（-5 ≥ {MIN_WIN_RATE['-5']}/8）",
              lo5 >= MIN_WIN_RATE["-5"], f"got={lo5}/8")
        check(f"{cls} 跨 11 级怪不被碾压（+11 ≤ {MAX_WIN_RATE['+11']}/8）",
              up11 <= MAX_WIN_RATE["+11"], f"got={up11}/8")
        check(f"{cls} 高 5 级怪不可碾压（+5 ≤ 2/8）", up5 <= 2, f"got={up5}/8")

    dt = time.time() - t0
    print(f"\n===== 结果：通过 {passed} / {passed + failed}（耗时 {dt:.1f}s）=====")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
