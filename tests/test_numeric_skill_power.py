# -*- coding: utf-8 -*-
"""N03·交付3 技能倍率快照（v130.9 数值测试框架）

锁定 12 职业（PLAYER_SKILLS 全量键）各 2 个代表技能的 power / mp / lv / SKILL_UP.p：
  基础技 = lv==1 的技能（无 lv1 则取排序首个）
  成型技 = lv∈[10,15] 档位最高的技能（无该档则取排序末个）
断言值 = 当前代码实测锁定（打印后写死，2026-08-27 baseline）。

数据现状说明：6 个隐藏职业（龙裔誓约/时咒法师/星语者/暗影神谕/暮影行者/淬势者）
在 PLAYER_SKILLS 仅登记 lv40 觉醒被动（星语者等 4 职仅 1 个技能），
其成型技能档位在 BRANCH_SKILLS（lv≥32）——按卡要求只取 PLAYER_SKILLS[cls]['skills']，
故隐藏职业快照为 lv40 被动现状（power=0），防误调同样生效。

运行：python tests/test_numeric_skill_power.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conftest import C  # noqa: E402

passed = failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

# 锁定表：cid -> (基础技, 成型技)，每项 = (技能名, lv, power, mp, SKILL_UP.p)
# v153 职业重做：7 基础职业数值按 v153 新表实测锁定（2026-09-01 baseline 重生成）
LOCK = {
    "cls_zhan_shi":     (("挥砍", 1, 0.82, 6, 12), ("铁壁", 12, 1.0, 5, 0)),
    "cls_fa_shi":       (("火球术", 1, 1.16, 6, 12), ("元素引爆", 12, 1.16, 10, 12)),
    "cls_you_xia":      (("连射", 1, 0.41, 0, 12), ("猎网陷阱", 12, 1.17, 0, 12)),
    "cls_mu_shi":       (("圣光弹", 1, 0.6, 4, 10), ("圣光护盾", 12, 1.0, 12, 0)),
    "cls_ci_ke":        (("刺击", 1, 0.66, 6, 12), ("双刃乱舞", 12, 0.46, 10, 12)),
    "cls_wu_seng":      (("直拳", 1, 0.63, 6, 12), ("连招三连", 12, 0.29, 12, 9)),
    "cls_shi_ren":      (("战歌", 1, 1.0, 6, 0), ("拨弦", 12, 1.0, 8, 0)),
}

def select(cls_skills):
    """与锁定表同口径的选择：基础技=lv1（无则首个）；成型技=[10,15]最高（无则末个）。"""
    rows = sorted(((i.get("lv", 0), i.get("name", ""), i) for i in cls_skills.values()))
    base = next((r for r in rows if r[0] == 1), rows[0] if rows else None)
    in_range = [r for r in rows if 10 <= r[0] <= 15]
    mature = in_range[-1] if in_range else (rows[-1] if rows else None)
    return base, mature

def main():
    cls_ids = list(C.PLAYER_SKILLS.keys())
    check("PLAYER_SKILLS 恰 7 职业", len(cls_ids) == 7, f"n={len(cls_ids)} ids={cls_ids}")
    for cid in LOCK:
        check(f"职业 {cid} 存在于 PLAYER_SKILLS", cid in C.PLAYER_SKILLS)

    print("【14 职业 × 2 代表技能 power/mp/lv + SKILL_UP.p 快照】")
    for cid, (ebase, emature) in LOCK.items():
        info = C.PLAYER_SKILLS[cid]
        cn = info.get("name", cid)
        skills = info.get("skills", {})
        bsel, msel = select(skills)
        for tag, sel, exp in (("基础技", bsel, ebase), ("成型技", msel, emature)):
            if sel is None:
                check(f"{cid}({cn}) {tag} 存在", False, "PLAYER_SKILLS 无技能条目")
                continue
            name = sel[1]
            # v181 P0B-C：SKILL_UP key 已改稳定 id → p 从条目 name 匹配取值（语义不变）
            _up_cfg = next((v for v in C.SKILL_UP.values()
                            if isinstance(v, dict) and v.get("name") == name), {})
            got = (name, sel[0], sel[2].get("power", 0), sel[2].get("mp", 0),
                   _up_cfg.get("p", 0))
            check(f"{cid}({cn}) {tag}『{name}』lv={exp[1]} power={exp[2]} mp={exp[3]} p={exp[4]}",
                  got == exp, f"got={got}")
            print(f"    {cn:6s} {tag}『{name}』 lv={got[1]} power={got[2]} mp={got[3]} p={got[4]}")

    print(f"\n===== 结果：通过 {passed} / 断言 {passed + failed} =====")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)