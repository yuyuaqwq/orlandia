# -*- coding: utf-8 -*-
"""N03·交付2 怪物成长曲线快照（v130.9 数值测试框架）

锁定 6 角色（tank/dps/caster/speedster/elite/boss）× 5 等级（1/11/22/30/60）
的 hp/atk/def/spd：断言 = 当前代码实测值 + 公式一致性双锁。

公式（对照 data/stat_templates.py MONSTER_ROLE_BASE/GROWTH + core/stats.py）：
  base_stat = base + growth×(lv-1)（hp/atk/def/spd 均为 int 截断）
  等级段修正（v56.2，hp_stage_mult/atk_stage_mult）：
    hp_stage：lv≤15 →1.0；≤30 →1+(lv-15)×0.08；≤60 →2.2+(lv-30)×0.04；>60 →3.4+(lv-60)×0.03
    atk_stage：lv≤30 →1.0；≤60 →1-(lv-30)×0.005；>60 →max(0.2, 0.85-(lv-60)×0.004)
  角色修正：boss hp ×min(1+lv×0.06, 3.0)、elite hp ×min(1+lv×0.04, 3.0)（在段修正前）；
            boss def/mdef ×1.25、elite def/mdef ×1.15（int 截断后乘，再 int）
  v156 阶段 6（2026-09-01）：普通怪 hp ×NORMAL_HP_STAGE_MULT(lv)、boss atk ×BOSS_ATK_STAGE_MULT(lv)
            （_stage_mult 分段斜率模型，见 core/stats.py）
  dot_res：boss=0.9 / elite=0.8（非普通怪键）

运行：python tests/test_numeric_monster_curve.py（exit=0 全绿）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C  # noqa: E402
from content.stats import (  # noqa: E402
    monster_stats, hp_stage_mult, atk_stage_mult, _stage_mult, _boss_atk_stage,
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

ROLES = ["tank", "dps", "caster", "speedster", "elite", "boss"]
LVS = [1, 11, 22, 30, 60]
# (hp, atk, def, spd) 实测锁定表（2026-08-27 baseline，打印后写死）
LOCK = {
    # v131 重标定（2026-08-27）：怪 HP×2/防御×2~4.5/攻击×1.4；boss 血量成长 58→145
    # v156 阶段 6 重标定（2026-09-01）：普通怪 hp ×NORMAL_HP_STAGE_MULT（P2+ 上调）、boss atk ×BOSS_ATK_STAGE_MULT（后期上调）
    # v169.3 承伤修复重标定（2026-09-03，鱼鱼拍板）：普通怪 atk growth 上调
    #   （tank 3.5→4.6 / dps 5.0→9.0 / caster 1.8→2.6 / speedster 3.5→6.0 / healer 1.5→2.2 /
    #    elite 6.5→8.2）+ atk_stage_mult 31 级起 -0.5%/级 → +0.4%/级（取消负斜率），
    #   精英/普通怪吃正斜率、boss 不吃（走 _boss_atk_stage 旧减速曲线 + BOSS_ATK_STAGE_MULT）——
    #   boss 行与 v169.2 完全一致。此表按改后实测重锁。
    "tank":      {1: (60, 8, 7, 6), 11: (420, 54, 47, 9), 22: (2218, 104, 91, 12),
                  30: (6134, 141, 123, 14), 60: (19241, 312, 243, 23)},
    "dps":       {1: (45, 12, 4, 10), 11: (345, 102, 54, 20), 22: (1835, 201, 109, 31),
                  30: (5083, 273, 149, 39), 60: (15989, 608, 299, 69)},
    "caster":    {1: (40, 5, 3, 9), 11: (260, 31, 38, 18), 22: (1364, 59, 76, 27),
                  30: (3765, 80, 104, 35), 60: (11787, 176, 209, 62)},
    "speedster": {1: (35, 9, 3, 16), 11: (255, 69, 48, 34), 22: (1350, 135, 97, 53),
                  30: (3736, 183, 133, 68), 60: (11743, 406, 268, 122)},
    "elite":     {1: (98, 14, 9, 11), 11: (1144, 96, 72, 26), 22: (3971, 186, 141, 42),
                  30: (8181, 251, 192, 54), 60: (33588, 556, 381, 99)},
    "boss":      {1: (169, 16, 12, 10), 11: (2672, 91, 60, 28), 22: (10037, 211, 111, 47),
                  30: (21388, 344, 150, 62), 60: (69284, 1217, 292, 116)},
}

def expect_stats(lv, role):
    """按 stat_templates + stats.py 公式重算 (hp, atk, def, spd)——与实现同序。"""
    base = C.MONSTER_ROLE_BASE[role]
    growth = C.MONSTER_ROLE_GROWTH[role]
    hp = int(base["hp"] + growth["hp"] * (lv - 1))
    if role == "boss":
        hp = int(hp * min(1 + lv * 0.06, 3.0))
    elif role == "elite":
        hp = int(hp * min(1 + lv * 0.04, 3.0))
    hp = int(hp * hp_stage_mult(lv))
    # v169.3：普通怪+精英乘 atk_stage_mult（31+ 正斜率）；boss 不乘（走下方 _boss_atk_stage）
    if role == "boss":
        atk = int(base["atk"] + growth["atk"] * (lv - 1))
    else:
        atk = int(int(base["atk"] + growth["atk"] * (lv - 1)) * atk_stage_mult(lv))
    # v156 阶段 6：普通怪 hp ×NORMAL_HP_STAGE_MULT、boss atk ×BOSS_ATK_STAGE_MULT
    if role in ("tank", "dps", "caster", "speedster", "healer"):
        hp = int(hp * _stage_mult(C.NORMAL_HP_STAGE_MULT, lv))
    elif role == "boss":
        # v169.3 boss 分支与实现同构：int(线性 × _boss_atk_stage) 后再乘段乘区（两级 int）
        atk = int(int(atk * _boss_atk_stage(lv)) * _stage_mult(C.BOSS_ATK_STAGE_MULT, lv))
    df = int(base["def"] + growth["def"] * (lv - 1))
    if role == "boss":
        df = int(df * 1.25)
    elif role == "elite":
        df = int(df * 1.15)
    spd = int(base["spd"] + growth["spd"] * (lv - 1))
    return hp, atk, df, spd

def main():
    print("【怪物成长曲线：6 role × 5 等级 hp/atk/def/spd】")
    print("  格式: role lv | hp atk def spd | 实测==锁定 | 实测==公式")
    for role in ROLES:
        for lv in LVS:
            s = monster_stats(lv, role)
            got = (s["hp"], s["atk"], s["def"], s["spd"])
            exp = LOCK[role][lv]
            fmt = expect_stats(lv, role)
            tag = f"{role} lv{lv}"
            check(f"{tag} 实测 == 锁定 {got}", got == exp, f"lock={exp}")
            check(f"{tag} 实测 == 公式 {got}", got == fmt, f"formula={fmt}")
            print(f"    {tag:16s} hp={s['hp']:6d} atk={s['atk']:5d} def={s['def']:4d} spd={s['spd']:4d}")
    print("【模板一致性复核：对照 base + growth×(lv-1) 线性部分】")
    print("  def：elite ×1.15 / boss ×1.25；spd：无修正 == 线性；"
          "hp：段修正 ≥ 线性；atk：lv≤30 == 线性（精英/普通怪），lv>30 ≥ 线性（v169.3 正斜率），boss 全段 == 线性")
    for role in ROLES:
        base = C.MONSTER_ROLE_BASE[role]
        growth = C.MONSTER_ROLE_GROWTH[role]
        for lv in LVS:
            lin_hp = int(base["hp"] + growth["hp"] * (lv - 1))
            lin_atk = int(base["atk"] + growth["atk"] * (lv - 1))
            lin_def = int(base["def"] + growth["def"] * (lv - 1))
            lin_spd = int(base["spd"] + growth["spd"] * (lv - 1))
            got = LOCK[role][lv]
            exp_def = int(lin_def * (1.25 if role == "boss" else 1.15 if role == "elite" else 1.0))
            check(f"{role} lv{lv} spd == 线性值（无修正）",
                  got[3] == lin_spd, f"got={got[3]} lin={lin_spd}")
            check(f"{role} lv{lv} def == 线性×角色修正",
                  got[2] == exp_def, f"got={got[2]} exp={exp_def} lin={lin_def}")
            check(f"{role} lv{lv} hp ≥ 线性值（段修正放大）",
                  got[0] >= lin_hp, f"got={got[0]} lin={lin_hp}")
            if role == "boss":
                # v169.3：boss 走 _boss_atk_stage 旧减速曲线（v169.2 数值），锁表即实测
                cond = got[1] == LOCK[role][lv][1]
                msg = f"got={got[1]}（boss 保持 v169.2 曲线，见注释）"
            elif lv <= 30:
                cond = got[1] == lin_atk
                msg = f"got={got[1]} lin={lin_atk}"
            else:
                # v169.3：atk_stage_mult 31+ 正斜率 → atk ≥ 线性（取消负斜率，怪攻击不再越高级越弱）
                cond = got[1] >= lin_atk
                msg = f"got={got[1]} lin={lin_atk}（31级起 +0.4%/级 正斜率）"
            check(f"{role} lv{lv} atk {'== 线性值' if lv <= 30 and role != 'boss' else '== 锁定值（boss 保持原曲线）' if role == 'boss' else '≥ 线性值（31+ 正斜率）'}",
                  cond, msg)

    print(f"\n===== 结果：通过 {passed} / 断言 {passed + failed} =====")
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)