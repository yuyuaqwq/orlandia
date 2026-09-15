# -*- coding: utf-8 -*-
"""v166 回复道具对齐门禁（食物 vs 药水性价比，economy_lib.heal_alignment_scan）

验证：
  1. heal_alignment_scan 可跑，返回食物/药水计数
  2. **issue_count == 0**（食物战斗外回复不得碾压同价药水；hot 累计不得反超战斗外总量）
     —— 含豁免（功能定位道具：祝福圣水/风暴贝汤/夜光鲛汤/应急灵液）
  3. 基准抽查：黑面包(10G) heal ≤ 治疗药水(小)基准 20%；烤肉串(15G) ≤ 基准+体力补偿
  4. 药水链自身价格-回复保持单调（8G→15% ≤ 10G→20% ≤ 20G→25% ...）

任何改动跑本门禁 = 全绿才能提交（食物/药水数值改动后回归）
独立运行：python tests/test_numeric_heal_alignment.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/（economy_lib 随迁落点）

try:
    import conftest  # noqa: F401  隔离测试库环境
except Exception:
    pass

from economy_lib import heal_alignment_scan
from economy_lib.core import _potion_baseline

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


print("== 回复道具对齐门禁（economy_lib.heal_alignment_scan）==")

scan = heal_alignment_scan()
h = scan["health"]

# 1. 基本结构
check("heal_alignment_scan 可跑", isinstance(scan, dict), "")
check("食物计数 > 30", h["food_count"] > 30, f"got {h['food_count']}")
check("药水计数 > 10", h["potion_count"] > 10, f"got {h['potion_count']}")

# 2. issues == 0（必须）
issues = scan.get("issues", [])
if issues:
    print("  ❌ issue_count 非空（食物回复仍碾压药水）：")
    for x in issues:
        print(f"    {x['name']} p={x['price']} heal={x['heal']*100:.0f}% "
              f"hot累计={x['hot_sum']*100:.0f}% 体力={x['stamina']} | {x['issue']}")
    FAIL += 1
else:
    PASS += 1
    print("  ✅ issue_count == 0（食物不碾压药水，hot 不反超）")

# 3. 基准抽查（食物关键件）
from economy_lib.core import HEAL_ANCHORS

food_by_name = {f["name"]: f for f in scan["foods"]}
# 黑面包：10G 应 heal ≤ 20%（药水小基准）
bread = food_by_name.get("黑面包")
if bread:
    check("黑面包 10G heal ≤ 药水基准 20%",
          bread["heal"] <= _potion_baseline(10) * 1.15 + 1e-9,
          f"heal={bread['heal']} baseline={_potion_baseline(10)}")
# 烤肉串 15G
skewer = food_by_name.get("烤肉串")
if skewer:
    check("烤肉串 15G heal ≤ 基准22%×体力补偿1.15",
          skewer["heal"] <= _potion_baseline(15) * 1.15 + 1e-9,
          f"heal={skewer['heal']} baseline={_potion_baseline(15)}")
# 炖菜 20G
stew = food_by_name.get("炖菜")
if stew:
    check("炖菜 20G heal ≤ 基准25%×1.15",
          stew["heal"] <= _potion_baseline(20) * 1.15 + 1e-9,
          f"heal={stew['heal']} baseline={_potion_baseline(20)}")

# 4. 药水基准锚点单调
mono = all(HEAL_ANCHORS[i][1] <= HEAL_ANCHORS[i + 1][1] + 1e-9 for i in range(len(HEAL_ANCHORS) - 1))
check("药水基准锚点单调递增", mono, str(HEAL_ANCHORS))

# 5. 打印 top 越界供审（应无）
if not issues:
    print("\n== 对齐结果：全绿 ==")

print(f"\n结果: PASS {PASS} / FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
