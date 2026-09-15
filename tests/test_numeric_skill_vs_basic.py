# -*- coding: utf-8 -*-
"""v156 数值门禁补丁：技能 DPS ≥ 普攻 × 1.1（绝对基准，v154 回归拦截）

背景（2026-09-01 群聊反馈：技能伤害普遍不如普攻）：
- v154 读条命中制把职业普攻 cast 砍到 0.3~1.0s（速度50基准），
  但技能 power 还是 v152 时代旧值 → 技能 DPS 全面落后普攻。
- 旧门禁全是"快照/纯普攻/上限"型：技能倍率快照只锁"变了没"，
  胜率矩阵 use_skill=False 根本不测技能 → v154 回归完全没拦住。

本测试：
1. 全职业基础技能 + 分支攻击技能：DPS（power×atk/cast，含技能等级成长）≥ 普攻 DPS × 1.1
2. 采样等级：Lv24（玩家实测反馈等级）全职业基础技能；Lv44/64/84 分支技能
3. 用真实引擎面板（player_final_stats）+ 真实技能表（skill_info）+ 真实 cast

运行：python tests/test_numeric_skill_vs_basic.py（exit=0 全绿）
注意：本测试现在【应该跑红】——数值修复后转绿，作为回归基准。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _engine_harness import C  # noqa: E402
from saintess_engine.battle.formulas import skill_power_mult, skill_flat_value
from content.panel import player_final_stats
from content.skills import skill_info# noqa: E402
from content.catalog_core import CLASSES  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


# 职业 → 主属性（物理投 str、魔法投 int），与 numeric_lib CLS_MAIN 一致
CLS_MAIN = {
    "cls_zhan_shi": "str", "cls_you_xia": "str", "cls_fa_shi": "int",
    "cls_mu_shi": "int", "cls_ci_ke": "str", "cls_wu_seng": "str",
}
# 采样档位：基础技能 Lv24（玩家反馈等级）/ 分支技能 Lv44/64/84
BASIC_LV = 24
BRANCH_LVS = [44, 64, 84]
# 绝对基准：技能 DPS ≥ 普攻 DPS × 1.1（技能该比普攻强，否则没理由花 MP/CD）
SKILL_BASIC_RATIO = 1.1


def attr_alloc(cls, lv):
    pts = 9 + 3 * (lv - 1)
    return {CLS_MAIN[cls]: pts}


def panel(cls, lv):
    """真实面板（裸装，主属性全投）——DPS 比值与装备无关（约掉）"""
    st = player_final_stats(cls, lv, {}, 0, attr_alloc(cls, lv),
                            evolve_path=0, title_bonus={}, race="human")
    return st


def _calc_dps_direct(st, power, cast, is_phys, flat=0):
    """DPS 直接口径（variance=0）：dps = calc_damage(atk*power + flat, 0) / cast。
    用 def=0 简化（防御在技能/普攻间同比例抵消，比值不变）。
    flat = v156 技能基础值（保底伤害），与引擎同口径。"""
    from saintess_engine.battle.formulas import calc_damage
    stat = st["atk"] if is_phys else st["matk"]
    d = calc_damage(int(stat * power) + flat, 0, variance=0.0,
                    dmg_type="phys" if is_phys else "magi")
    return d / max(cast, 0.01)


def _attack_skills(cls, lv, branch=False):
    """攻击技能清单（kind ∈ 物理/魔法/真伤，power>0，学习等级 ≤ lv）"""
    out = []
    if branch:
        br = getattr(C, "BRANCH_SKILLS", {}).get(cls, {})
        for bno, branches in br.get("branches", {}).items():
            for bname, skills in branches.items():
                for k, info in skills.items():
                    name = info.get("name", k)
                    need_lv = int(info.get("lv", 1) or 1)
                    if info.get("kind") in ("物理", "魔法", "真伤") and info.get("power", 0) > 0 \
                            and need_lv <= lv:
                        out.append((name, info))
        return out
    cls_data = C.PLAYER_SKILLS.get(cls, {})
    for k, info in cls_data.get("skills", {}).items():
        name = info.get("name", k)
        need_lv = int(info.get("lv", 1) or 1)
        if info.get("kind") in ("物理", "魔法", "真伤") and info.get("power", 0) > 0 \
                and need_lv <= lv:
            out.append((name, info))
    return out


def check_class(cls, lv, branch=False):
    """单职业单等级：所有攻击技能 DPS ≥ 普攻 × SKILL_BASIC_RATIO"""
    cname = C.PLAYER_SKILLS.get(cls, {}).get("name", cls)
    st = panel(cls, lv)
    is_phys = cls in ("cls_zhan_shi", "cls_you_xia", "cls_ci_ke", "cls_wu_seng")
    cast_atk = float(CLASSES.get(cls, {}).get("cast_atk", 1.0) or 1.0)
    # 普攻 DPS（def=0 口径）
    from saintess_engine.battle.formulas import calc_damage
    stat = st["atk"] if is_phys else st["matk"]
    dps_basic = calc_damage(int(stat), 0, variance=0.0,
                            dmg_type="phys" if is_phys else "magi") / cast_atk
    skills = _attack_skills(cls, lv, branch=branch)
    if not skills:
        return
    tag = "分支" if branch else "基础"
    for name, info in skills:
        # 技能等级 Lv3（玩家投入 2 点后的合理水平；v133 峰值口径同）
        power = float(info.get("power", 0)) * skill_power_mult(3, info)
        cast = float(info.get("cast", 1.6) or 1.6)
        # 多段技能：DPS 按段数乘（hits）
        multi = int(info.get("hits", info.get("multi", 1)) or 1)
        # v156 技能基础值（保底伤害）：与引擎同口径（flat = BASE + 玩家等级×PER + 技能等级×PER_SKILL）
        skill_flat = skill_flat_value(lv, 3, info)
        # 真伤：dmg_type=true（不吃防御）
        kind = info.get("kind", "")
        dps_skill = _calc_dps_direct(st, power * multi, cast,
                                     is_phys and kind != "真伤", flat=skill_flat)
        # 真伤技能用真伤口径
        if kind == "真伤":
            dps_skill = _calc_dps_direct(st, power * multi, cast, True, flat=skill_flat)
        ratio = dps_skill / max(dps_basic, 1)
        cond = ratio >= SKILL_BASIC_RATIO
        check(f"{cname} L{lv} {tag}『{name}』DPS={dps_skill:.1f} vs 普攻={dps_basic:.1f} "
              f"(x{ratio:.2f} ≥ {SKILL_BASIC_RATIO})", cond,
              f"→ 技能 DPS 低于普攻 {ratio:.2f}x，需调 power/cast")


def main():
    print(f"== 技能 DPS ≥ 普攻 × {SKILL_BASIC_RATIO} 绝对基准（v154 回归拦截）==")
    print(f"口径：真实面板（裸装主属性全投）、技能 Lv3、def=0（比值与装备无关）、速度50基准")
    print()
    for cls in CLS_MAIN:
        check_class(cls, BASIC_LV, branch=False)
    for lv in BRANCH_LVS:
        for cls in CLS_MAIN:
            check_class(cls, lv, branch=True)

    print(f"\n===== 结果：通过 {passed} / 断言 {passed + failed} =====")
    if failed:
        print("❌ 有技能 DPS 低于普攻！这是 v154 回归——需调数值（power 或 cast）")
        return 1
    print("✅ 全部技能 DPS ≥ 普攻 × 1.1，通过！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
