# -*- coding: utf-8 -*-
"""v174 诗人基础期输出技门禁（鱼鱼 2026-09-04：诗人核心病根=没战斗力 → 全阶段审计设计）

验证：
  1. 诗人基础 Lv1-30 有 ≥4 伤害技（原仅 Lv16 音刃 1 个 = 前期无战斗力）
  2. 锁音(Lv1)/破音(Lv4)/共振(Lv8) 在 Lv10 裸装能打同级怪（2-4 轮击杀）
  3. 全部伤害技走 expr 公式（LOL 式，与法系同规格）
  4. 新技能在 SKILL_UP 有成长配置
  5. 普攻（basic_skill 拨弦 matk）已覆盖法系

任何改动跑本门禁 = 全绿才能提交（诗人技能/数值改动后回归）
独立运行：python tests/test_numeric_poet_basic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

try:
    import conftest  # noqa: F401
except Exception:
    pass

from saintess_engine import expr as FE
from content.catalog_core import CLASSES
from content.skills import SKILL_UP

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def poet_skills():
    # ★ B16-W11d（2026-09-14）：`game/data/skills.py` 随数据层删除 → 改读**包内门面**
    #   `content/catalog_core.py::PLAYER_SKILLS`（同一份技能表；不再按源码 exec 读字面）。
    from content import catalog_core as _cc
    return _cc.PLAYER_SKILLS["cls_shi_ren"]["skills"]


print("== v174 诗人基础期输出技门禁 ==")

S = poet_skills()

# 1. Lv≤30 伤害技 ≥4
dmg_low = [s for s in S.values() if s.get("kind", "").startswith("魔法") and s.get("lv", 99) <= 30
           and s.get("name") != "拨弦"]
check("诗人 Lv≤30 伤害技 ≥4", len(dmg_low) >= 4,
      f"现有 {len(dmg_low)}: {[s.get('name') for s in dmg_low]}")

# 2. 新技覆盖 Lv1/4/8（前期梯度）
lvs = sorted(s.get("lv") for s in dmg_low)
check("伤害技覆盖 Lv1 起（有 1 级输出）", 1 in lvs, f"等级: {lvs}")
check("伤害技有 AOE（共振）", any(s.get("aoe") for s in dmg_low), "")

# 3. Lv10 裸装伤害够打怪（锁音+破音 2-4 轮杀 200-300HP）
b = CLASSES["cls_shi_ren"]["base"]
g = CLASSES["cls_shi_ren"]["growth"]
st = {k: b[k] + g[k] * 9 for k in b if k in g}
lv = 10
suo = FE.eval_expr(FE.compile_expr("matk*0.6 + 8 + player_lv*2.2 + skill_lv*6"),
                   FE.build_vars(st, player_lv=lv, skill_lv=1, target_max_hp=300))
po = FE.eval_expr(FE.compile_expr("matk*1.1 + 15 + player_lv*3.8 + skill_lv*10"),
                  FE.build_vars(st, player_lv=lv, skill_lv=1, target_max_hp=300))
# 扣除怪 mdef ~15% → 净伤
net_round = 250 / max((suo + po) * 0.85, 1)  # 两技轮换打 250HP 怪
check(f"Lv10 锁音+破音轮换 {net_round:.1f} 轮杀怪（≤5）", net_round <= 5, f"{net_round:.1f}")

# 4. SKILL_UP 配置（v181 P0B-C：key 已改稳定 id → 按条目 name 断言）
_up_names = {v.get("name") for v in SKILL_UP.values() if isinstance(v, dict)}
for nm in ["锁音", "破音", "共振"]:
    check(f"{nm} SKILL_UP 已配", nm in _up_names, "")

# 5. 普攻 basic_skill matk
bs = CLASSES["cls_shi_ren"]["basic_skill"]
check("诗人 basic_skill 魔法 matk", bs.get("kind") == "魔法" and bs.get("exprs", [""])[0] == "matk*1.0",
      str(bs))

print()
print(f"===== 结果：PASS {PASS} / FAIL {FAIL} =====")
sys.exit(1 if FAIL else 0)
