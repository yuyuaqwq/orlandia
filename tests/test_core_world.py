# -*- coding: utf-8 -*-
"""core 层 · 世界族：垂钓 / 传送

验证 roll_fish / portal_cost 等世界交互逻辑。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C

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
    print("【core·世界族：垂钓】")
    rf = getattr(C, "roll_fish", None)
    if rf:
        f = rf()
        check("roll_fish 返回 dict", isinstance(f, dict) and "name" in f, str(f)[:80])
    else:
        check("roll_fish 可访问", False, "未暴露")

    print("【core·世界族：传送】")
    pc = getattr(C, "portal_cost", None)
    if pc:
        m = {"lv": 5}
        check("portal_cost 正数", pc(m) > 0, str(pc(m)))
        m2 = {"lv": 20}
        check("portal_cost 等级更高更贵", pc(m2) >= pc(m), "%s vs %s" % (pc(m), pc(m2)))
    else:
        check("portal_cost 可访问", False, "未暴露")

    print("【v56.2 怪物等级段曲线（乱秒修复）+ v131 新模板 + v169.3 承伤修复】")
    ms = getattr(C, "monster_stats", None)
    if ms:
        m1 = ms(10, "dps")
        m15 = ms(15, "dps")
        m30 = ms(30, "dps")
        m60 = ms(60, "dps")
        # v131：dps hp 成长 15→30/级，≤15 段等级段曲线仍无加成（315=10×30+15 尾差）
        check("Lv10 dps hp=315（v131 模板 30/级）", m1["hp"] == 315, "hp=%s" % m1["hp"])
        check("Lv15 dps hp=465（v131 模板）", m15["hp"] == 465, "hp=%s" % m15["hp"])
        # v162：16-30 段每级 +0.145（NORMAL_HP_STAGE_MULT 更新），Lv30 ×3.175
        # Lv30 hp = int((45+30×29) × hp_stage_mult 1.75) × 3.175 = 5083
        check("30级怪 hp 放大(5083)", 4900 < m30["hp"] < 5300, "hp=%s" % m30["hp"])
        check("60级怪 hp 继续放大", m60["hp"] > m30["hp"] * 2, "%s vs %s" % (m60["hp"], m30["hp"]))
        # v169.3 承伤修复（2026-09-03 鱼鱼拍板）：dps atk growth 5.0→9.0/级、
        # atk_stage_mult 31+ 负斜率改正斜率（+0.4%/级，取消"越高级越弱"）
        #   Lv30（≤30 段 atk_stage=1.0）atk = int(12+9.0×29) = 273
        #   Lv60 atk = int(12+9.0×59) × atk_stage_mult(60)=1.12 = 608 ≥ 线性（不再放缓）
        check("30级怪 atk 线性(273)", ms(30, "dps")["atk"] == int(12 + 9.0 * 29), "atk=%s" % ms(30, "dps")["atk"])
        check("60级怪 atk 正斜率(608, ≥线性)", ms(60, "dps")["atk"] >= 12 + 9.0 * 59, "atk=%s" % ms(60, "dps")["atk"])
        e1 = getattr(C, "monster_exp", None)
        if e1:
            check("30级怪经验补偿", e1(30, "dps") > 9 * 28 * 1.5, "exp=%s" % e1(30, "dps"))
    else:
        check("monster_stats 可访问", False, "未暴露")

    print("\n结果: %d 通过, %d 失败" % (passed, failed))
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
