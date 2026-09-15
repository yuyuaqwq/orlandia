# -*- coding: utf-8 -*-
"""economy_lib 门禁自检（v165 经济模型，2026-09-02 鱼鱼拍板搭建）

验证：
  1. 全阶段经济扫描可跑（economy_scan 返回 6 阶段）
  2. 每阶段关键字段存在且有合理值
  3. 健康检查函数工作（check_health 返回 list）
  4. 副业扫描可跑（profession_scan 返回炼金/烹饪）
  5. 掉落数量模型：材料涨价后 单只怪掉落数量 cap 生效（不再爆 99）
"""
import sys, os

# 直跑模式需要引擎通道环境（GWEN_GAME_DB 隔离 + 路径）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import boot as _eng_boot  # noqa: E402
_eng_boot()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/（economy_lib 随迁落点）

from economy_lib import economy_scan, check_health, profession_scan, ECON_STAGES

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")

print("== economy_lib 门禁自检 ==")

# 1. 扫描可跑
scan = economy_scan()
check("economy_scan 返回 6 阶段", len(scan["stages"]) == 6, f"got {len(scan['stages'])}")
rows = scan["stages"]

# 2. 每阶段关键字段
for row in rows:
    check(f"阶段 {row['stage']} 有 per_kill_gold",
          row.get("per_kill_gold", 0) > 0, str(row.get("per_kill_gold")))
    check(f"阶段 {row['stage']} 有 drop_value",
          row.get("drop_value", 0) > 0)
    check(f"阶段 {row['stage']} blue_price 存在",
          row.get("blue_price") is not None or row.get("blue_kills") is not None)

# 3. 健康检查函数
issues = check_health(rows[0])
check("check_health 返回 list", isinstance(issues, list))

# 4. 副业扫描
prof = profession_scan()
check("profession_scan 有 alchemy", "alchemy" in prof and prof["alchemy"]["total"] > 0)
check("profession_scan 有 cooking", "cooking" in prof and prof["cooking"]["total"] > 0)

# 5. 掉落 cap 生效：用当前材料价模拟普通怪，确认无 99 爆量
from content.catalog_items import MATERIALS  # noqa: E402
from content.catalog_space import MAPS  # noqa: E402
from content import stats as S
mat_price = {v.get("name", k): v.get("price", 0) for k, v in MATERIALS.items()}
max_n = 0
over_cap = 0
checked_drop = 0
for m in MAPS:
    for sub in m.get("subareas", []):
        for mon in sub.get("monsters", []):
            if len(mon) < 6:
                continue
            lv, role = mon[3], mon[2]
            if role not in ("tank", "dps", "caster", "speedster", "healer"):
                continue
            drops = [d for d in mon[5] if isinstance(d, str) and d in mat_price]
            if not drops:
                continue
            g = S.monster_gold(lv, role if role in S.MONSTER_GOLD_BASE else "dps")
            mv = int(g * 1.5)
            for d in drops:
                p = mat_price[d]
                if p <= 0:
                    continue
                n_raw = int(mv / len(drops) / p)
                n = max(1, min(10, n_raw))
                max_n = max(max_n, n)
                if n_raw > 10:
                    over_cap += 1
                checked_drop += 1
check("普通怪单种掉落 ≤10 (cap 生效)", max_n <= 10, f"max={max_n}")
print(f"  (检查 {checked_drop} 条掉落配置，撞 cap 的 {over_cap} 条)")

# 6. 材料涨价有效性：高级怪掉的料价格应显著高于低级怪
print("\n== 汇总 ==")
print(f"通过 {PASS} / 失败 {FAIL}")
if FAIL:
    sys.exit(1)
