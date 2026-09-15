# -*- coding: utf-8 -*-
"""N03 装备依赖门禁 —— 战士 11 级「裸装 vs 满装（铁港套装 5 槽）」：面板提升 + 同级胜率。

装备（固定名册 + 固定生成种子，可复现；与 `scripts/_tmp_lv_scan.py` 的 N03 锁定同源）：

| 槽 | id | 名 |
|---|---|---|
| weapon | `eq_wan_dao` | 弯刀（Lv.14 蓝） |
| helm | `eq_chuan_zhang_mao` | 船长帽（Lv.14 蓝） |
| armor | `eq_shui_shou_jia_ke` | 水手夹克（Lv.15 蓝） |
| legs | `eq_shui_shou_hu_tui` | 水手护腿（Lv.14 蓝） |
| boots | `eq_hai_dao_xue` | 海盗靴（Lv.14 蓝） |

面板（`player_final_stats`，39 点全力量）：

| 项 | 裸装 | 满装 | 提升 |
|---|---|---|---|
| max_hp | 370 | 713 | +92.7% |
| atk | 89 | 152 | +70.8% |
| def | 40 | 108 | +170.0% |
| spd | 16 | 38 | +137.5% |

同级胜率（11v11 普通 dps 怪，seeds=6 纯普攻）：裸装 **2/6** → 满装 **6/6**。

防什么回归
----------
1. **装备无意义** —— 面板提升塌到区间下限以下（穿不穿一个样）
2. **数值爆炸** —— 面板提升冲破区间上限（一件装备顶十个等级）
3. **胜率反转 / 装配链断裂** —— 满装胜率不升反降，或提升幅度 <3 场

跑法：python tests/test_numeric_equip_dependency.py（约 1s）
"""
import os
import random
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

import numeric_sim as NS  # noqa: E402
from conftest import C  # noqa: E402

CLS, LV = "战士", 11
ATTR = NS.STD_ATTR[CLS]
SEEDS = 6

FULL_RIDS = {"weapon": "eq_wan_dao", "helm": "eq_chuan_zhang_mao",
             "armor": "eq_shui_shou_jia_ke", "legs": "eq_shui_shou_hu_tui",
             "boots": "eq_hai_dao_xue"}

# 面板快照（实测锁定 2026-09-12）：{属性: (裸装, 满装)}
PANEL_LOCK = {"max_hp": (370, 713), "atk": (89, 152), "def": (40, 108), "spd": (16, 38)}
# 提升幅度健康带（%）：下限防「装备无意义」，上限防「数值爆炸」
GAIN_RANGE = {"max_hp": (50, 250), "atk": (30, 150), "def": (80, 350), "spd": (60, 300)}
WIN_LOCK = {"裸装": 2, "满装": 6}

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def make_full_equip() -> dict:
    """铁港套装 5 槽（固定生成种子，可复现）。"""
    equip = {}
    for i, (slot, rid) in enumerate(FULL_RIDS.items(), start=1):
        random.seed(100 + i)
        equip[slot] = C.generate_roster_equip(rid)
    return equip


def main():
    t0 = time.time()
    print("【N03 装备依赖：战士 11 级 裸装 vs 满装（铁港套装）】")
    naked, full = {}, make_full_equip()
    st_n = NS.player_panel(CLS, LV, ATTR, naked)
    st_f = NS.player_panel(CLS, LV, ATTR, full)
    print("  项         裸装      满装     提升")
    gains = {}
    for k in ("max_hp", "atk", "def", "spd"):
        a, b = st_n[k], st_f[k]
        gains[k] = (b / a - 1) * 100
        print(f"  {k:8s} {a:6d}  {b:6d}  {gains[k]:+7.1f}%")

    for k, exp in PANEL_LOCK.items():
        check(f"面板快照 {k} == 裸装 {exp[0]} / 满装 {exp[1]}",
              (st_n[k], st_f[k]) == exp, f"got={(st_n[k], st_f[k])}")
    for k, (lo, hi) in GAIN_RANGE.items():
        check(f"{k} 提升幅度在健康带 {lo}~{hi}%（实测 {gains[k]:.1f}%）",
              lo <= gains[k] <= hi, f"got={gains[k]:.1f}%")

    print(f"\n  同级胜率（11v11 dps，seeds={SEEDS} 纯普攻）：")
    wins = {}
    for label, eq in (("裸装", naked), ("满装", full)):
        w, r = NS.class_battle_matrix(CLS, LV, ATTR, eq, "dps", 11, seeds=SEEDS)
        wins[label] = w
        print(f"    {label}: {w}/{SEEDS}  avg={r}")
    for label, exp in WIN_LOCK.items():
        check(f"{label} 胜场 == 基线 {exp}/{SEEDS}", wins[label] == exp,
              f"got={wins[label]}/{SEEDS}")
    check("满装显著优于裸装（≥ +3 场，防装配链断裂）",
          wins["满装"] - wins["裸装"] >= 3, f"{wins['裸装']} → {wins['满装']}")
    check("满装非必胜（同级怪仍有威胁，防数值爆炸）", wins["满装"] <= SEEDS,
          f"got={wins['满装']}/{SEEDS}")

    print(f"\n===== 结果：通过 {passed} / {passed + failed}（耗时 {time.time() - t0:.1f}s）=====")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
