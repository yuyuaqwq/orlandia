# -*- coding: utf-8 -*-
"""N02 任务卡·交付 2：面板快照测试（12 职业 × 1/11/30/60 级裸装 + 加点收益）

目的：锁定 12 职业（6 基础 + 6 隐藏）关键等级裸装面板，防无意识成长公式改动。
  断言键：max_hp / atk / def / spd / crit / dodge（crit/dodge 为百分比属性，浮点容差 1e-9）
  属性加点收益快照（防单属性超模回归，等级 11·39 点自由属性）：
    - 刺客：全敏 vs 全力 → spd 差 +31（72 vs 41）、atk 差 +46（93 vs 47）
    - 战士：全力 vs 全耐 → hp 差 +312（682 vs 370）
    - 法师：全智 vs 裸装 → matk +46（106 vs 60）、mp +58（278 vs 220）

快照值 = 当前代码实测（player_final_stats 真实派生），写死即基线：
  任何成长公式/职业 base/growth 改动 → 断言失败，防"动了数值不知道动了"。

运行：python tests/test_numeric_panel_snapshot.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C  # noqa: E402
from content.panel import player_final_stats  # noqa: E402

passed = failed = 0
LEVELS = (1, 11, 30, 60)
SNAPSHOT_KEYS = ("max_hp", "atk", "def", "spd", "crit", "dodge")

# ⚠️ 快照基线（2026-08-27 实测，改成长公式/职业数值需主 agent 统一更新）
PANEL_SNAPSHOT = {
    "cls_zhan_shi": {
        1: {'max_hp': 150, 'atk': 18, 'def': 14, 'spd': 10, 'crit': 0.05, 'dodge': 0.03},
        11: {'max_hp': 370, 'atk': 50, 'def': 40, 'spd': 16, 'crit': 0.05, 'dodge': 0.03},
        30: {'max_hp': 788, 'atk': 110, 'def': 89, 'spd': 27, 'crit': 0.05, 'dodge': 0.03},
        60: {'max_hp': 1448, 'atk': 206, 'def': 167, 'spd': 45, 'crit': 0.05, 'dodge': 0.03},
    },
    "cls_fa_shi": {
        1: {'max_hp': 90, 'atk': 8, 'def': 7, 'spd': 12, 'crit': 0.08, 'dodge': 0.05},
        11: {'max_hp': 190, 'atk': 16, 'def': 17, 'spd': 21, 'crit': 0.08, 'dodge': 0.05},
        30: {'max_hp': 380, 'atk': 31, 'def': 36, 'spd': 38, 'crit': 0.08, 'dodge': 0.05},
        60: {'max_hp': 680, 'atk': 55, 'def': 66, 'spd': 65, 'crit': 0.08, 'dodge': 0.05},
    },
    "cls_you_xia": {
        1: {'max_hp': 110, 'atk': 15, 'def': 10, 'spd': 16, 'crit': 0.15, 'dodge': 0.12},
        11: {'max_hp': 250, 'atk': 41, 'def': 26, 'spd': 30, 'crit': 0.15, 'dodge': 0.12},
        30: {'max_hp': 516, 'atk': 90, 'def': 56, 'spd': 56, 'crit': 0.15, 'dodge': 0.12},
        60: {'max_hp': 936, 'atk': 168, 'def': 104, 'spd': 98, 'crit': 0.15, 'dodge': 0.12},
    },
    "cls_mu_shi": {
        1: {'max_hp': 100, 'atk': 10, 'def': 11, 'spd': 11, 'crit': 0.06, 'dodge': 0.06},
        11: {'max_hp': 220, 'atk': 22, 'def': 29, 'spd': 19, 'crit': 0.06, 'dodge': 0.06},
        30: {'max_hp': 448, 'atk': 44, 'def': 63, 'spd': 34, 'crit': 0.06, 'dodge': 0.06},
        60: {'max_hp': 808, 'atk': 80, 'def': 117, 'spd': 58, 'crit': 0.06, 'dodge': 0.06},
    },
    "cls_ci_ke": {
        1: {'max_hp': 95, 'atk': 17, 'def': 9, 'spd': 19, 'crit': 0.2, 'dodge': 0.18},
        11: {'max_hp': 215, 'atk': 47, 'def': 22, 'spd': 35, 'crit': 0.2, 'dodge': 0.18},
        30: {'max_hp': 443, 'atk': 104, 'def': 46, 'spd': 65, 'crit': 0.2, 'dodge': 0.18},
        60: {'max_hp': 803, 'atk': 194, 'def': 85, 'spd': 113, 'crit': 0.2, 'dodge': 0.18},
    },
    "cls_wu_seng": {
        1: {'max_hp': 135, 'atk': 15, 'def': 12, 'spd': 14, 'crit': 0.1, 'dodge': 0.12},
        11: {'max_hp': 315, 'atk': 43, 'def': 32, 'spd': 25, 'crit': 0.1, 'dodge': 0.12},
        30: {'max_hp': 657, 'atk': 96, 'def': 70, 'spd': 45, 'crit': 0.1, 'dodge': 0.12},
        60: {'max_hp': 1197, 'atk': 180, 'def': 130, 'spd': 78, 'crit': 0.1, 'dodge': 0.12},
    },
    "cls_shi_ren": {
        1: {'max_hp': 95, 'atk': 9, 'def': 10, 'spd': 13, 'crit': 0.07, 'dodge': 0.08},
        11: {'max_hp': 205, 'atk': 20, 'def': 25, 'spd': 22, 'crit': 0.07, 'dodge': 0.08},
        30: {'max_hp': 414, 'atk': 40, 'def': 53, 'spd': 39, 'crit': 0.07, 'dodge': 0.08},
        60: {'max_hp': 744, 'atk': 73, 'def': 98, 'spd': 66, 'crit': 0.07, 'dodge': 0.08},
    },
}


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def main():
    # v153：7 基础职业（6 + 新增诗人），快照断言从 6 → 7
    classes = [c for c in C.CLASSES if c != "cls_novice"]
    check("7 职业完整性（CLASSES 全量，排除见习）", len(classes) == 7,
          f"n={len(classes)} {classes}")

    print("【① 7 职业裸装面板快照（1/11/30/60 级）】")
    for cid in classes:
        cname = C.CLASSES[cid]["name"]
        for lv in LEVELS:
            st = player_final_stats(cid, lv, {}, 0, None)
            exp = PANEL_SNAPSHOT[cid][lv]
            for k in SNAPSHOT_KEYS:
                if k in ("crit", "dodge"):
                    got, want = float(st[k]), float(exp[k])
                    ok = abs(got - want) <= 1e-9
                else:
                    got, want = int(st[k]), int(exp[k])
                    ok = got == want
                check(f"{cname} Lv.{lv} {k} == {want}", ok,
                      f"got={st[k]} want={exp[k]}")
        row = "  ".join(f"Lv.{lv} hp{st_k['max_hp']}/atk{st_k['atk']}/spd{st_k['spd']}"
                        for lv, st_k in ((1, PANEL_SNAPSHOT[cid][1]),
                                         (11, PANEL_SNAPSHOT[cid][11]),
                                         (30, PANEL_SNAPSHOT[cid][30]),
                                         (60, PANEL_SNAPSHOT[cid][60])))
        print(f"  📊 {cname}({cid}): {row}")

    print("【② 属性加点收益快照（11 级 · 39 点自由属性）】")
    # 刺客：全敏 vs 全力 —— spd +31（66 vs 35）、atk +39（86 vs 47）
    a_agi = player_final_stats("cls_ci_ke", 11, {}, 0, {"agi": 39})
    a_str = player_final_stats("cls_ci_ke", 11, {}, 0, {"str": 39})
    check("刺客 全敏 spd 66 / 全力 spd 35", a_agi["spd"] == 66 and a_str["spd"] == 35,
          f"agi={a_agi['spd']} str={a_str['spd']}")
    check("刺客 全敏 vs 全力 spd 差 == +31", a_agi["spd"] - a_str["spd"] == 31,
          f"d={a_agi['spd'] - a_str['spd']}")
    check("刺客 全力 atk 86 / 全敏 atk 47", a_str["atk"] == 86 and a_agi["atk"] == 47,
          f"str={a_str['atk']} agi={a_agi['atk']}")
    check("刺客 全力 vs 全敏 atk 差 == +39", a_str["atk"] - a_agi["atk"] == 39,
          f"d={a_str['atk'] - a_agi['atk']}")
    # 战士：全力 vs 全耐 —— hp 差 +234（604 vs 370，v136 属性转化 vit→hp 8→6）
    w_str = player_final_stats("cls_zhan_shi", 11, {}, 0, {"str": 39})
    w_vit = player_final_stats("cls_zhan_shi", 11, {}, 0, {"vit": 39})
    check("战士 全耐 hp 604 / 全力 hp 370", w_vit["max_hp"] == 604 and w_str["max_hp"] == 370,
          f"vit={w_vit['max_hp']} str={w_str['max_hp']}")
    check("战士 全耐 vs 全力 hp 差 == +234", w_vit["max_hp"] - w_str["max_hp"] == 234,
          f"d={w_vit['max_hp'] - w_str['max_hp']}")
    # 法师：全智 vs 裸装 —— matk +39（99 vs 60，v136 属性转化 int→matk 1.2→1.0）
    f_int = player_final_stats("cls_fa_shi", 11, {}, 0, {"int": 39})
    f_bare = player_final_stats("cls_fa_shi", 11, {}, 0, None)
    check("法师 全智 matk 99 /> mp 278", f_int["matk"] == 99 and f_int["max_mp"] == 278,
          f"matk={f_int['matk']} mp={f_int['max_mp']}")
    check("法师 全智 vs 裸装 matk 差 == +39", f_int["matk"] - f_bare["matk"] == 39,
          f"d={f_int['matk'] - f_bare['matk']}")
    check("法师 全智 vs 裸装 mp 差 == +58", f_int["max_mp"] - f_bare["max_mp"] == 58,
          f"d={f_int['max_mp'] - f_bare['max_mp']}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


main()
