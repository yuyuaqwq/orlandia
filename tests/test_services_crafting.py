# -*- coding: utf-8 -*-
"""P4-4 CraftingService 确定性直测（services/crafting.py，v181 P4-4）

直测 service 纯规则（不依赖 Main/FakeEvent）：
  1. compute_enhance_rate 确定性：
     - 无加成：率=基础率，craft_line=""，stones_used=[]
     - 副业加成（Lv.1 +0.5% / Lv.10 +5%）按 min(prof_lv,10)*0.005 封顶
     - 精炼石 +25% / 祝福 +15% 叠加（封顶 100%）；星铁必成不消耗石料
     - 率已 100% 时不消耗石料（v105 M11 P2 防浪费）
  2. enhance_fail_floor 确定性（对照 C.ENHANCE_FAIL_DROP 表）：
     - +1~+4 失败不掉级；+5/+6 掉 1 级；+7/+8 不掉级
     - 保护石存在且会掉级 → 保住等级 + protect_used=True
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, clean_db

from content.crafting import (
    compute_enhance_rate, enhance_fail_floor,
    ENHANCE_STONE_REFINE, ENHANCE_STONE_BLESSED, ENHANCE_STONE_PROTECT,
)

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
    clean_db()
    # 常量收敛：与 data/enhance.py、UPGRADE 配置同值（i_stone_* 字面量单点）
    check("ENHANCE_STONE_REFINE 常量 = i_stone_refine", ENHANCE_STONE_REFINE == "i_stone_refine")
    check("ENHANCE_STONE_BLESSED 常量 = i_stone_blessed", ENHANCE_STONE_BLESSED == "i_stone_blessed")
    check("ENHANCE_STONE_PROTECT 常量 = i_stone_upgrade", ENHANCE_STONE_PROTECT == "i_stone_upgrade")
    check("UPGRADE_STONE 与 refine 常量同源", C.UPGRADE_STONE == ENHANCE_STONE_REFINE)

    print("【1. compute_enhance_rate 基础/副业加成】")
    r = compute_enhance_rate(0.95, 0)
    check("Lv.0 无加成：率=0.95", abs(r["rate"] - 0.95) < 1e-9, str(r))
    check("Lv.0 无 craft_line", r["craft_line"] == "", str(r["craft_line"]))
    check("Lv.0 无消耗", r["stones_used"] == [], str(r["stones_used"]))
    r = compute_enhance_rate(0.95, 1)
    check("Lv.1 手艺 +0.5%：率=0.955", abs(r["rate"] - 0.955) < 1e-9, str(r))
    check("Lv.1 craft_line 含 Lv.1/+0.5%",
          "Lv.1" in r["craft_line"] and "+0.5%" in r["craft_line"], str(r["craft_line"]))
    r = compute_enhance_rate(0.95, 10)
    check("Lv.10 手艺 +5%：率=1.0 封顶", abs(r["rate"] - 1.0) < 1e-9, str(r))
    r = compute_enhance_rate(0.80, 20)
    check("Lv.20 按 min(10) 封顶 +5%：率=0.85", abs(r["rate"] - 0.85) < 1e-9, str(r))

    print("【2. compute_enhance_rate 强化石叠加】")
    r = compute_enhance_rate(0.80, 0, has_refine=True)
    check("精炼石 +25%：率=1.0 封顶", abs(r["rate"] - 1.0) < 1e-9, str(r))
    check("精炼石记入消耗", ENHANCE_STONE_REFINE in r["stones_used"], str(r["stones_used"]))
    r = compute_enhance_rate(0.80, 0, has_refine=True, has_blessed=True)
    check("精炼+祝福：0.80→1.0 封顶", abs(r["rate"] - 1.0) < 1e-9, str(r))
    # 原内联逐条判定：refine 先到 1.0 → 后续 blessed 的 <1.0 判定不成立 → 只耗精炼（等价）
    check("精炼先到 1.0 后祝福不再消耗（顺序判定等价原代码）",
          r["stones_used"] == [ENHANCE_STONE_REFINE], str(r["stones_used"]))
    r = compute_enhance_rate(0.50, 0, has_refine=True, has_blessed=True)
    check("0.50+25%+15%=0.90", abs(r["rate"] - 0.90) < 1e-9, str(r))
    r = compute_enhance_rate(0.60, 0, has_refine=True, has_blessed=True)
    check("0.60+25% 已 >0.85 仍叠祝福 → 1.0（原判定逐条 <1.0）",
          abs(r["rate"] - 1.0) < 1e-9, str(r))
    r = compute_enhance_rate(0.60, 0, has_refine=True, has_blessed=True, boost=True)
    check("星铁必成：不消耗任何石料", r["stones_used"] == [], str(r["stones_used"]))
    # boost=True 时副业加成/石料一律不叠加（原代码：_rate 保持 info[\"rate\"] 原值，掷骰直接必成）
    check("星铁必成：rate = 基础率原值（0.60，原代码不叠任何加成）",
          abs(r["rate"] - 0.60) < 1e-9, str(r))
    check("boost 标记透传", r["boost"] is True, str(r))
    r = compute_enhance_rate(1.0, 0, has_refine=True, has_blessed=True)
    check("率已 100%：不消耗石料（v105 M11 P2 防浪费）", r["stones_used"] == [], str(r["stones_used"]))
    r = compute_enhance_rate(0.85, 0, has_refine=True)
    check("0.85+25% 判定前 <1.0 → 消耗精炼封顶 1.0", r["stones_used"] == [ENHANCE_STONE_REFINE], str(r["stones_used"]))
    r = compute_enhance_rate(0.95, 0, has_refine=True)
    check("0.95+25%=1.0 消耗精炼", abs(r["rate"] - 1.0) < 1e-9 and r["stones_used"] == [ENHANCE_STONE_REFINE], str(r))

    print("【3. enhance_fail_floor 保级/降级】")
    # ENHANCE_FAIL_DROP = {5: 1, 6: 1}（v113.3：+5/+6 掉 1 级，+7/+8 大师保底）
    floor_map = {}
    for enh in range(0, 9):
        new_enh, used = enhance_fail_floor(enh)
        floor_map[enh] = (new_enh, used)
    check("+0~+4 失败不掉级", all(floor_map[e][0] == e and not floor_map[e][1] for e in range(0, 5)),
          str(floor_map))
    check("+5/+6 失败掉 1 级（对照 ENHANCE_FAIL_DROP）",
          floor_map[5][0] == 4 and floor_map[6][0] == 5, str(floor_map))
    check("+7/+8 失败不掉级（大师工艺保底）",
          floor_map[7][0] == 7 and floor_map[8][0] == 8, str(floor_map))
    check("与 C.ENHANCE_FAIL_DROP 逐档一致",
          all(floor_map[e][0] == max(0, e - C.ENHANCE_FAIL_DROP.get(e, 0)) for e in range(0, 9)),
          str(floor_map))
    new_enh, used = enhance_fail_floor(5, has_protect=True)
    check("+5 带保护：保住 +5 并消耗保护石", new_enh == 5 and used is True, f"{new_enh},{used}")
    new_enh, used = enhance_fail_floor(5, has_protect=False)
    check("+5 无保护：掉到 +4 不耗石", new_enh == 4 and used is False, f"{new_enh},{used}")
    new_enh, used = enhance_fail_floor(2, has_protect=True)
    check("+2 带保护但不掉级：不耗石", new_enh == 2 and used is False, f"{new_enh},{used}")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
